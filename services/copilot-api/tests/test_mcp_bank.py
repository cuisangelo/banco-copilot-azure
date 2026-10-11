"""McpBankTools against an in-process FastMCP server over real streamable HTTP."""

from contextlib import asynccontextmanager

import httpx
import pytest
from bank_contracts.models import CustomerFields, CustomerProfile, FieldsDenied, Level2Field, Product
from mcp.server.fastmcp import Context, FastMCP

from copilot_api.mcp_bank import McpBankTools, ToolFailed

TOKEN = "persona.jwt.value"

PRODUCT = Product(
    id="TC-ORO",
    name="Tarjeta Oro",
    category="credit_card",
    annual_rate_pct=28.5,
    monthly_fee_clp=4500,
    requirements=["Renta mínima de 800.000"],
    valid_from="2026-01-01",
)


def build_server(seen: list[dict]) -> FastMCP:
    server = FastMCP("fake-bank", stateless_http=True, json_response=True)

    def record(ctx: Context, tool: str, arguments: dict) -> None:
        seen.append({
            "tool": tool,
            "arguments": arguments,
            "authorization": ctx.request_context.request.headers.get("authorization"),
        })

    @server.tool()
    def get_product(product_id: str, ctx: Context) -> Product:
        record(ctx, "get_product", {"product_id": product_id})
        if product_id != "TC-ORO":
            raise ValueError("product not found")
        return PRODUCT

    @server.tool()
    def list_products(category: str | None, ctx: Context) -> list[Product]:
        record(ctx, "list_products", {"category": category})
        return [PRODUCT]

    @server.tool()
    def get_customer_profile(customer_id: str, ctx: Context) -> CustomerProfile:
        record(ctx, "get_customer_profile", {"customer_id": customer_id})
        return CustomerProfile(
            customer_id=customer_id, segment="personas", income_type="dependiente", products=[], customer_tenure_months=30
        )

    @server.tool()
    def get_customer_fields(customer_id: str, fields: list[Level2Field], ctx: Context) -> CustomerFields | FieldsDenied:
        record(ctx, "get_customer_fields", {"customer_id": customer_id, "fields": fields})
        if "current_debt" in fields:
            return FieldsDenied(customer_id=customer_id, denied_fields=["current_debt"])
        return CustomerFields(customer_id=customer_id, values={"monthly_income": 1_500_000}, grant_id="g-1")

    return server


@asynccontextmanager
async def connected_tools(seen: list[dict], token: str | None):
    server = build_server(seen)
    app = server.streamable_http_app()
    async with server.session_manager.run():
        http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000")
        async with McpBankTools.connect("http://localhost:8000/mcp", token=token, http_client=http, backoff_seconds=0) as tools:
            yield tools


async def test_jwt_travels_in_the_transport_header_and_never_in_tool_arguments():
    seen: list[dict] = []
    async with connected_tools(seen, TOKEN) as tools:
        await tools.get_customer_profile("C-1001")
        await tools.get_customer_fields("C-1001", ["monthly_income"])

    assert [call["authorization"] for call in seen] == [f"Bearer {TOKEN}"] * 2
    assert all(TOKEN not in repr(call["arguments"]) for call in seen)
    assert seen[1]["arguments"] == {"customer_id": "C-1001", "fields": ["monthly_income"]}


async def test_anonymous_calls_carry_no_authorization():
    seen: list[dict] = []
    async with connected_tools(seen, None) as tools:
        await tools.get_product("TC-ORO")

    assert seen[0]["authorization"] is None


async def test_structured_results_parse_into_contract_models():
    seen: list[dict] = []
    async with connected_tools(seen, TOKEN) as tools:
        assert await tools.get_product("TC-ORO") == PRODUCT
        assert await tools.list_products(None) == [PRODUCT]
        assert await tools.get_customer_fields("C-1001", ["monthly_income"]) == CustomerFields(
            customer_id="C-1001", values={"monthly_income": 1_500_000}, grant_id="g-1"
        )
        assert await tools.get_customer_fields("C-1001", ["current_debt"]) == FieldsDenied(
            customer_id="C-1001", denied_fields=["current_debt"]
        )


async def test_tool_errors_are_retried_twice_then_raised():
    seen: list[dict] = []
    async with connected_tools(seen, TOKEN) as tools:
        with pytest.raises(ToolFailed):
            await tools.get_product("NO-EXISTE")

    assert len(seen) == 3
