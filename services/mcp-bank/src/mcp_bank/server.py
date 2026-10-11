from typing import Annotated

import httpx
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import Field
from starlette.applications import Starlette

from bank_contracts.models import (
    CUSTOMER_ID_PATTERN,
    CustomerFields,
    CustomerProfile,
    FieldsDenied,
    Level2Field,
    Product,
    ProductCategory,
)
from bank_contracts.settings import require_env
from bank_contracts.tools import (
    TOOL_COMPARE_PRODUCTS,
    TOOL_GET_CUSTOMER_FIELDS,
    TOOL_GET_CUSTOMER_PROFILE,
    TOOL_GET_PRODUCT,
    TOOL_LIST_PRODUCTS,
)

# Tool arguments come from the model; the pattern keeps them from rewriting the APIM path.
ProductId = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
CustomerId = Annotated[str, Field(pattern=CUSTOMER_ID_PATTERN)]


def _persona_authorization(ctx: Context) -> str:
    request = ctx.request_context.request
    authorization = request.headers.get("authorization") if request is not None else None
    if not authorization:
        raise ToolError("persona authorization is required for customer data")
    return authorization


def _ok(response: httpx.Response) -> httpx.Response:
    if not response.is_success:
        raise ToolError(f"{response.request.url.path} returned {response.status_code}")
    return response


def create_server() -> FastMCP:
    apim_base_url = require_env("APIM_BASE_URL").rstrip("/")
    subscription_key = require_env("APIM_SUBSCRIPTION_KEY")
    # Stateless JSON responses let any replica serve any request; there are no server-initiated messages.
    server = FastMCP("mcp-bank", host="0.0.0.0", stateless_http=True, json_response=True)

    async def apim(method: str, path: str, authorization: str | None = None, **kwargs) -> httpx.Response:
        headers = {"Ocp-Apim-Subscription-Key": subscription_key}
        if authorization is not None:
            headers["Authorization"] = authorization
        async with httpx.AsyncClient(base_url=apim_base_url, timeout=10) as client:
            return await client.request(method, path, headers=headers, **kwargs)

    async def fetch_product(product_id: str) -> Product:
        return Product.model_validate(_ok(await apim("GET", f"/products-api/products/{product_id}")).json())

    @server.tool(name=TOOL_GET_PRODUCT)
    async def get_product(product_id: ProductId) -> Product:
        """Current features of one bank product: rate, monthly fee and requirements."""
        return await fetch_product(product_id)

    @server.tool(name=TOOL_LIST_PRODUCTS)
    async def list_products(category: ProductCategory | None = None) -> list[Product]:
        """Bank products, optionally filtered by category."""
        params = {"category": category} if category is not None else {}
        response = _ok(await apim("GET", "/products-api/products", params=params))
        return [Product.model_validate(p) for p in response.json()]

    @server.tool(name=TOOL_COMPARE_PRODUCTS)
    async def compare_products(
        product_ids: Annotated[list[ProductId], Field(min_length=2, max_length=3)],
    ) -> list[Product]:
        """Two or three products side by side."""
        return [await fetch_product(product_id) for product_id in product_ids]

    @server.tool(name=TOOL_GET_CUSTOMER_PROFILE)
    async def get_customer_profile(customer_id: CustomerId, ctx: Context) -> CustomerProfile:
        """Level 1 profile of the customer being served: segment, income type, products and tenure."""
        authorization = _persona_authorization(ctx)
        response = _ok(await apim("GET", f"/customers-api/customers/{customer_id}/profile", authorization))
        return CustomerProfile.model_validate(response.json())

    @server.tool(name=TOOL_GET_CUSTOMER_FIELDS)
    async def get_customer_fields(
        customer_id: CustomerId,
        fields: Annotated[list[Level2Field], Field(min_length=1)],
        ctx: Context,
    ) -> CustomerFields | FieldsDenied:
        """Level 2 values covered by a live supervisor grant; otherwise the fields that were denied."""
        authorization = _persona_authorization(ctx)
        response = await apim(
            "POST", f"/customers-api/customers/{customer_id}/fields", authorization, json={"fields": fields}
        )
        if response.status_code == 403:
            return FieldsDenied.model_validate(response.json())
        return CustomerFields.model_validate(_ok(response).json())

    return server


def app_from_env() -> Starlette:
    return create_server().streamable_http_app()
