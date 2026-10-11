import time
from dataclasses import dataclass, field
from typing import Literal

from agent_framework import Executor, WorkflowContext, handler
from bank_contracts.models import Product, ProductCategory
from pydantic import BaseModel, ValidationError

from copilot_api.mcp_bank import ToolFailed
from copilot_api.prompts import load_prompt
from copilot_api.workflow.trace import emit_trace
from copilot_api.workflow.turn import Services, Turn, take_tool_call

PRODUCT_ROUTES = ("product", "mixed")
PRODUCTS_UNAVAILABLE = "No pude consultar la API de productos; la respuesta no incluye datos vigentes de productos."


class ProductCall(BaseModel):
    tool: Literal["get_product", "list_products", "compare_products"]
    product_id: str | None = None
    category: ProductCategory | None = None
    product_ids: list[str] | None = None


class ProductPlan(BaseModel):
    calls: list[ProductCall]


@dataclass
class ProductFindings:
    """product_agent's half of the fan-in. It runs beside customer_agent on the same Turn, so it writes
    only the shared tool budget there and hands everything else to the composer."""

    products: list[Product] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class Products(Executor):
    def __init__(self, services: Services) -> None:
        super().__init__(id="product_agent")
        self._services = services
        self._system = load_prompt("products")

    async def _call(self, call: ProductCall) -> list[Product]:
        bank = self._services.bank
        if call.tool == "get_product":
            return [await bank.get_product(call.product_id)]
        if call.tool == "list_products":
            return await bank.list_products(call.category)
        return await bank.compare_products(call.product_ids)

    @handler
    async def run(self, turn: Turn, ctx: WorkflowContext[ProductFindings]) -> None:
        findings = ProductFindings()
        if turn.route.route not in PRODUCT_ROUTES:
            await ctx.send_message(findings)
            return
        started = time.perf_counter()
        plan, usage = await self._services.llm.structured(
            ProductPlan, system=self._system, user=f"Consulta del asesor:\n{turn.route.search_query}"
        )
        executed, failed = [], False
        for call in plan.calls:
            if not take_tool_call(turn):
                break
            arguments = call.model_dump(exclude={"tool"}, exclude_none=True)
            executed.append({"tool": call.tool, "arguments": arguments, "result_kind": "ok"})
            await self._services.store.audit(
                actor=turn.actor,
                event="tool_call",
                data={"session_id": turn.session_id, "tool": call.tool, "arguments": arguments},
            )
            try:
                found = await self._call(call)
            except (ToolFailed, ValidationError):
                failed = True
                executed[-1]["result_kind"] = "error"
                continue
            known = {product.id for product in findings.products}
            findings.products.extend(product for product in found if product.id not in known)
        if failed:
            findings.notes.append(PRODUCTS_UNAVAILABLE)
        await emit_trace(ctx, "product_agent", started, {"tool_calls": executed}, usage)
        await ctx.send_message(findings)
