import json
from contextlib import asynccontextmanager

import httpx
import pytest
import respx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from bank_contracts.tools import (
    TOOL_COMPARE_PRODUCTS,
    TOOL_GET_CUSTOMER_FIELDS,
    TOOL_GET_CUSTOMER_PROFILE,
    TOOL_GET_PRODUCT,
    TOOL_LIST_PRODUCTS,
)
from mcp_bank.server import create_server

APIM = "https://apim.test"
SUBSCRIPTION_KEY = "test-subscription-key"
PERSONA_JWT = "Bearer persona.jwt.token"


def product(product_id: str, category: str = "credit_card") -> dict:
    return {
        "id": product_id,
        "name": f"Producto {product_id}",
        "category": category,
        "annual_rate_pct": 28.5,
        "monthly_fee_clp": 4500,
        "requirements": ["Renta mínima 800.000"],
        "valid_from": "2026-01-01",
    }


PROFILE = {
    "customer_id": "C-1042",
    "segment": "personas",
    "income_type": "dependiente",
    "products": ["CTA-SUELDO"],
    "customer_tenure_months": 38,
}


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def apim():
    # Unmatched requests are answered and recorded, so `not apim.calls` really proves APIM was never reached.
    with respx.mock(base_url=APIM, assert_all_called=False, assert_all_mocked=False) as mock:
        yield mock


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setenv("APIM_BASE_URL", APIM)
    monkeypatch.setenv("APIM_SUBSCRIPTION_KEY", SUBSCRIPTION_KEY)
    return create_server()


@asynccontextmanager
async def connect(server, headers: dict[str, str] | None = None):
    """MCP client over the real streamable HTTP app, in process, so transport headers reach the tools."""
    transport = httpx.ASGITransport(app=server.streamable_http_app())

    async with server.session_manager.run():
        async with httpx.AsyncClient(transport=transport, headers=headers) as http_client:
            async with streamable_http_client("http://mcp-bank.test/mcp", http_client=http_client) as (
                read,
                write,
                _,
            ):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield session


async def call(server, tool: str, arguments: dict, headers: dict[str, str] | None = None):
    async with connect(server, headers) as session:
        return await session.call_tool(tool, arguments)


pytestmark = pytest.mark.anyio


async def test_exposes_exactly_the_contract_tools(server):
    async with connect(server) as session:
        tools = (await session.list_tools()).tools

    assert {t.name for t in tools} == {
        TOOL_GET_PRODUCT,
        TOOL_LIST_PRODUCTS,
        TOOL_COMPARE_PRODUCTS,
        TOOL_GET_CUSTOMER_PROFILE,
        TOOL_GET_CUSTOMER_FIELDS,
    }


async def test_no_tool_takes_identity_as_an_argument(server):
    async with connect(server) as session:
        tools = (await session.list_tools()).tools

    arguments = {name.lower() for t in tools for name in t.inputSchema["properties"]}
    assert not arguments & {"authorization", "token", "jwt", "advisor", "sub", "persona"}


async def test_get_product_calls_apim_with_subscription_key(server, apim):
    route = apim.get("/products-api/products/TC-ORO").respond(json=product("TC-ORO"))

    result = await call(server, TOOL_GET_PRODUCT, {"product_id": "TC-ORO"})

    assert not result.isError
    assert result.structuredContent["id"] == "TC-ORO"
    assert route.calls.last.request.headers["Ocp-Apim-Subscription-Key"] == SUBSCRIPTION_KEY


async def test_get_unknown_product_is_tool_error(server, apim):
    apim.get("/products-api/products/NOPE").respond(404, json={"detail": "product not found"})

    result = await call(server, TOOL_GET_PRODUCT, {"product_id": "NOPE"})

    assert result.isError


async def test_product_id_cannot_traverse_apim_paths(server, apim):
    result = await call(server, TOOL_GET_PRODUCT, {"product_id": "../../customers-api/customers/C-1042/profile"})

    assert result.isError
    assert not apim.calls


async def test_list_products_filters_by_category(server, apim):
    route = apim.get("/products-api/products", params={"category": "account"}).respond(
        json=[product("CTA-SUELDO", "account")]
    )

    result = await call(server, TOOL_LIST_PRODUCTS, {"category": "account"})

    assert route.called
    assert [p["id"] for p in result.structuredContent["result"]] == ["CTA-SUELDO"]


async def test_list_products_without_category_sends_no_filter(server, apim):
    route = apim.get("/products-api/products").respond(json=[product("TC-ORO")])

    await call(server, TOOL_LIST_PRODUCTS, {})

    assert "category" not in route.calls.last.request.url.params


async def test_compare_products_returns_each_product(server, apim):
    apim.get("/products-api/products/TC-ORO").respond(json=product("TC-ORO"))
    apim.get("/products-api/products/TC-PLATINUM").respond(json=product("TC-PLATINUM"))

    result = await call(server, TOOL_COMPARE_PRODUCTS, {"product_ids": ["TC-ORO", "TC-PLATINUM"]})

    assert [p["id"] for p in result.structuredContent["result"]] == ["TC-ORO", "TC-PLATINUM"]


@pytest.mark.parametrize("ids", [["TC-ORO"], ["A", "B", "C", "D"]], ids=["one", "four"])
async def test_compare_products_needs_two_or_three_ids(server, apim, ids):
    result = await call(server, TOOL_COMPARE_PRODUCTS, {"product_ids": ids})

    assert result.isError
    assert not apim.calls


async def test_customer_profile_forwards_persona_authorization(server, apim):
    route = apim.get("/customers-api/customers/C-1042/profile").respond(json=PROFILE)

    result = await call(server, TOOL_GET_CUSTOMER_PROFILE, {"customer_id": "C-1042"}, {"Authorization": PERSONA_JWT})

    assert result.structuredContent == PROFILE
    sent = route.calls.last.request.headers
    assert sent["Authorization"] == PERSONA_JWT
    assert sent["Ocp-Apim-Subscription-Key"] == SUBSCRIPTION_KEY


async def test_customer_profile_without_authorization_is_tool_error(server, apim):
    result = await call(server, TOOL_GET_CUSTOMER_PROFILE, {"customer_id": "C-1042"})

    assert result.isError
    assert not apim.calls


async def test_malformed_customer_id_is_tool_error_without_calling_apim(server, apim):
    result = await call(server, TOOL_GET_CUSTOMER_PROFILE, {"customer_id": "1042"}, {"Authorization": PERSONA_JWT})

    assert result.isError
    assert not apim.calls


async def test_unknown_customer_is_tool_error(server, apim):
    apim.get("/customers-api/customers/C-9999/profile").respond(404, json={"detail": "customer not found"})

    result = await call(server, TOOL_GET_CUSTOMER_PROFILE, {"customer_id": "C-9999"}, {"Authorization": PERSONA_JWT})

    assert result.isError


async def test_customer_profile_drops_keys_outside_the_contract(server, apim):
    apim.get("/customers-api/customers/C-1042/profile").respond(json=PROFILE | {"rut": "12.345.678-9"})

    result = await call(server, TOOL_GET_CUSTOMER_PROFILE, {"customer_id": "C-1042"}, {"Authorization": PERSONA_JWT})

    assert "12.345.678-9" not in json.dumps(result.model_dump())


async def test_customer_fields_returns_granted_values(server, apim):
    route = apim.post("/customers-api/customers/C-1042/fields").respond(
        json={"customer_id": "C-1042", "values": {"monthly_income": 1450000}, "grant_id": "ar-1"}
    )

    result = await call(
        server,
        TOOL_GET_CUSTOMER_FIELDS,
        {"customer_id": "C-1042", "fields": ["monthly_income"]},
        {"Authorization": PERSONA_JWT},
    )

    assert not result.isError
    assert result.structuredContent["result"]["values"] == {"monthly_income": 1450000}
    assert json.loads(route.calls.last.request.content) == {"fields": ["monthly_income"]}
    assert route.calls.last.request.headers["Authorization"] == PERSONA_JWT


async def test_customer_fields_denied_is_structured_result_not_error(server, apim):
    denied = {"customer_id": "C-1042", "denied_fields": ["monthly_income"]}
    apim.post("/customers-api/customers/C-1042/fields").respond(403, json=denied)

    result = await call(
        server,
        TOOL_GET_CUSTOMER_FIELDS,
        {"customer_id": "C-1042", "fields": ["monthly_income"]},
        {"Authorization": PERSONA_JWT},
    )

    assert not result.isError
    assert result.structuredContent["result"] == denied


async def test_customer_fields_rejects_unknown_field_names(server, apim):
    result = await call(
        server,
        TOOL_GET_CUSTOMER_FIELDS,
        {"customer_id": "C-1042", "fields": ["rut"]},
        {"Authorization": PERSONA_JWT},
    )

    assert result.isError
    assert not apim.calls


async def test_missing_apim_base_url_fails_at_startup(monkeypatch):
    monkeypatch.delenv("APIM_BASE_URL", raising=False)
    monkeypatch.setenv("APIM_SUBSCRIPTION_KEY", SUBSCRIPTION_KEY)
    with pytest.raises(RuntimeError, match="APIM_BASE_URL is required"):
        create_server()
