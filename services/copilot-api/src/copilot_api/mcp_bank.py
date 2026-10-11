import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from agent_framework import MCPStreamableHTTPTool
from agent_framework.exceptions import ToolExecutionException
from bank_contracts.models import CustomerFields, CustomerProfile, FieldsDenied, Level2Field, Product
from bank_contracts.tools import (
    TOOL_COMPARE_PRODUCTS,
    TOOL_GET_CUSTOMER_FIELDS,
    TOOL_GET_CUSTOMER_PROFILE,
    TOOL_GET_PRODUCT,
    TOOL_LIST_PRODUCTS,
)
from mcp import types
from pydantic import TypeAdapter

RETRIES = 2

_products = TypeAdapter(list[Product])


class ToolFailed(Exception):
    pass


def _structured_json(result: types.CallToolResult) -> str:
    if result.isError:
        return "\n".join(block.text for block in result.content if isinstance(block, types.TextContent))
    payload = result.structuredContent
    # FastMCP wraps non-object return values (lists, unions) as {"result": value}.
    if isinstance(payload, dict) and payload.keys() == {"result"}:
        payload = payload["result"]
    return json.dumps(payload)


class McpBankTools:
    """Typed read-only access to mcp-bank.

    The persona JWT is set on the MCP transport headers when connecting; it is never a tool argument,
    so nothing the model chooses can carry or alter the identity customers-api authorizes.
    """

    def __init__(self, tool: MCPStreamableHTTPTool, *, backoff_seconds: float) -> None:
        self._tool = tool
        self._backoff_seconds = backoff_seconds

    @classmethod
    @asynccontextmanager
    async def connect(
        cls,
        url: str,
        *,
        token: str | None,
        http_client: httpx.AsyncClient | None = None,
        backoff_seconds: float = 0.5,
    ) -> AsyncIterator["McpBankTools"]:
        tool = MCPStreamableHTTPTool(
            name="mcp-bank",
            url=url,
            load_prompts=False,
            http_client=http_client,
            static_headers={"Authorization": f"Bearer {token}"} if token else None,
            parse_tool_results=_structured_json,
        )
        async with tool:
            yield cls(tool, backoff_seconds=backoff_seconds)

    async def _call(self, name: str, **arguments) -> object:
        for attempt in range(RETRIES + 1):
            try:
                return json.loads(await self._tool.call_tool(name, **arguments))
            except ToolExecutionException as error:
                if attempt == RETRIES:
                    raise ToolFailed(f"{name} failed: {error}") from error
                await asyncio.sleep(self._backoff_seconds * 2**attempt)
        raise AssertionError("unreachable")

    async def get_product(self, product_id: str) -> Product:
        return Product.model_validate(await self._call(TOOL_GET_PRODUCT, product_id=product_id))

    async def list_products(self, category: str | None) -> list[Product]:
        return _products.validate_python(await self._call(TOOL_LIST_PRODUCTS, category=category))

    async def compare_products(self, product_ids: list[str]) -> list[Product]:
        return _products.validate_python(await self._call(TOOL_COMPARE_PRODUCTS, product_ids=product_ids))

    async def get_customer_profile(self, customer_id: str) -> CustomerProfile:
        return CustomerProfile.model_validate(await self._call(TOOL_GET_CUSTOMER_PROFILE, customer_id=customer_id))

    async def get_customer_fields(self, customer_id: str, fields: list[Level2Field]) -> CustomerFields | FieldsDenied:
        payload = await self._call(TOOL_GET_CUSTOMER_FIELDS, customer_id=customer_id, fields=fields)
        if "denied_fields" in payload:
            return FieldsDenied.model_validate(payload)
        return CustomerFields.model_validate(payload)
