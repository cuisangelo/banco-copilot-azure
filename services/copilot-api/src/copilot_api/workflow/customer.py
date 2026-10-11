import time
import uuid
from datetime import UTC, datetime

from agent_framework import Executor, WorkflowContext, handler, response_handler
from bank_contracts.models import AccessRequest, ChatAnswer, FieldsDenied, Level2Field
from pydantic import BaseModel, Field, ValidationError

from copilot_api.mcp_bank import ToolFailed
from copilot_api.prompts import load_prompt
from copilot_api.workflow.trace import emit_trace
from copilot_api.workflow.turn import Services, Turn, TurnResult, take_tool_call

CUSTOMER_ROUTES = ("customer", "mixed")
TURN_STATE_KEY = "turn"
APPROVED_STATUSES = ("approved", "partially_approved")

NEEDS_PERSONA = "Para consultar datos de un cliente debes ingresar como Asesor."
NEEDS_CUSTOMER_ID = "Indica el id del cliente en atención (formato C-1234) para consultar sus datos."
CUSTOMER_UNAVAILABLE = "No pude obtener los datos del cliente {customer_id}; verifica el identificador."
ACCESS_REQUIRED = (
    "Para responder necesito acceso a datos sensibles del cliente {customer_id}: {fields}. "
    "Envié la solicitud a un Supervisor; retomaré la consulta cuando la decida."
)


class CustomerPlan(BaseModel):
    fields: list[Level2Field]
    purpose: str = Field(min_length=10, max_length=300)


class Customer(Executor):
    def __init__(self, services: Services) -> None:
        super().__init__(id="customer_agent")
        self._services = services
        self._system = load_prompt("customer")

    async def _audit(self, turn: Turn, event: str, **data) -> None:
        await self._services.store.audit(actor=turn.actor, event=event, data={"session_id": turn.session_id, **data})

    async def _without_customer_data(self, turn: Turn, ctx: WorkflowContext, message: str) -> None:
        """A customer-only question cannot be answered; a mixed one goes on with documents and products."""
        if turn.route.route == "customer":
            await ctx.yield_output(TurnResult(ChatAnswer(status="insufficient", message=message)))
            return
        turn.notes.append(message)
        await ctx.send_message(turn)

    async def _tool(self, turn: Turn, calls: list[dict], tool: str, *, reserved: bool = False, **arguments) -> object:
        """Run one customer tool inside the turn budget, recording it for the audit log and the inspector."""
        if not reserved and not take_tool_call(turn):
            raise ToolFailed("tool call budget exhausted")
        calls.append({"tool": tool, "arguments": arguments, "result_kind": "error"})
        await self._audit(turn, "tool_call", tool=tool, **arguments)
        result = await getattr(self._services.bank, tool)(**arguments)
        calls[-1]["result_kind"] = "denied" if isinstance(result, FieldsDenied) else "ok"
        return result

    @handler
    async def run(self, turn: Turn, ctx: WorkflowContext[Turn, TurnResult]) -> None:
        if turn.route.route not in CUSTOMER_ROUTES:
            await ctx.send_message(turn)
            return
        if turn.actor is None:
            await self._without_customer_data(turn, ctx, NEEDS_PERSONA)
            return
        if turn.customer_id is None:
            await self._without_customer_data(turn, ctx, NEEDS_CUSTOMER_ID)
            return
        started = time.perf_counter()
        plan, usage = await self._services.llm.structured(
            CustomerPlan, system=self._system, user=f"Consulta del asesor:\n{turn.route.search_query}"
        )
        turn.customer_plan = plan
        calls: list[dict] = []
        try:
            turn.profile = await self._tool(turn, calls, "get_customer_profile", customer_id=turn.customer_id)
        except ToolFailed:
            await emit_trace(ctx, "customer_agent", started, {"tool_calls": calls}, usage)
            await self._without_customer_data(turn, ctx, CUSTOMER_UNAVAILABLE.format(customer_id=turn.customer_id))
            return
        if turn.profile.products:
            await self._name_products(turn, calls)
        denied = await self._read_fields(turn, calls, plan.fields) if plan.fields else None
        # The retry after approval resumes from a snapshot of this turn, taken while product_agent may
        # still be spending the shared budget: claim the retry's call now so the turn stays within it.
        if denied and not take_tool_call(turn):
            turn.notes.append(CUSTOMER_UNAVAILABLE.format(customer_id=turn.customer_id))
            denied = None
        data = {"tool_calls": calls, "authz.decision": "denied" if denied else "allowed"}
        if denied:
            data["access_request.status"] = "pending"
        await emit_trace(ctx, "customer_agent", started, data, usage)
        if denied:
            await self._request_access(turn, plan, denied, ctx)
            return
        await ctx.send_message(turn)

    async def _name_products(self, turn: Turn, calls: list[dict]) -> None:
        """The profile lists product ids but advisors write names; cite both, taking names only from the API."""
        try:
            catalog = await self._tool(turn, calls, "list_products", category=None)
        except (ToolFailed, ValidationError):
            return
        turn.product_names = {product.id: product.name for product in catalog if product.id in turn.profile.products}

    async def _read_fields(
        self, turn: Turn, calls: list[dict], fields: list[Level2Field], *, reserved: bool = False
    ) -> FieldsDenied | None:
        try:
            result = await self._tool(
                turn, calls, "get_customer_fields", reserved=reserved, customer_id=turn.customer_id, fields=fields
            )
        except ToolFailed:
            turn.notes.append(CUSTOMER_UNAVAILABLE.format(customer_id=turn.customer_id))
            return None
        if isinstance(result, FieldsDenied):
            return result
        turn.customer_fields = result
        return None

    async def _request_access(self, turn: Turn, plan: CustomerPlan, denied: FieldsDenied, ctx: WorkflowContext) -> None:
        request = AccessRequest(
            id=str(uuid.uuid4()),
            customer_id=turn.customer_id,
            fields=denied.denied_fields,
            purpose=plan.purpose,
            requested_by=turn.actor,
            status="pending",
            created_at=datetime.now(UTC),
        )
        await self._services.store.create_access_request(request)
        await self._audit(turn, "access_request_created", access_request_id=request.id, fields=request.fields)
        ctx.set_state(TURN_STATE_KEY, turn)
        message = ACCESS_REQUIRED.format(customer_id=turn.customer_id, fields=", ".join(request.fields))
        await ctx.yield_output(TurnResult(ChatAnswer(status="access_required", message=message, access_request=request)))
        await ctx.request_info(request, AccessRequest, request_id=request.id)

    @response_handler
    async def on_decision(
        self, requested: AccessRequest, decided: AccessRequest, ctx: WorkflowContext[Turn, TurnResult]
    ) -> None:
        """Retry the read once: fields that were never denied plus the ones the Supervisor approved."""
        started = time.perf_counter()
        turn: Turn = ctx.get_state(TURN_STATE_KEY)
        approved = set(decided.approved_fields) if decided.status in APPROVED_STATUSES else set()
        turn.unauthorized_fields = [field for field in requested.fields if field not in approved]
        retry = [field for field in turn.customer_plan.fields if field not in requested.fields or field in approved]
        calls: list[dict] = []
        if retry:
            denied = await self._read_fields(turn, calls, retry, reserved=True)
            if denied is not None:
                turn.unauthorized_fields += [f for f in denied.denied_fields if f not in turn.unauthorized_fields]
        await emit_trace(
            ctx,
            "customer_agent",
            started,
            {
                "access_request.status": decided.status,
                "tool_calls": calls,
                "authz.decision": "denied" if turn.unauthorized_fields else "allowed",
                "unauthorized_fields": turn.unauthorized_fields,
            },
        )
        await ctx.send_message(turn)
