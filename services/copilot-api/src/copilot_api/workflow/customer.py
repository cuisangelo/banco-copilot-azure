import time
import uuid
from datetime import UTC, datetime

from agent_framework import Executor, WorkflowContext, handler, response_handler
from bank_contracts.models import AccessRequest, ChatAnswer, FieldsDenied, Level2Field
from pydantic import BaseModel, Field

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
        try:
            if not take_tool_call(turn):
                raise ToolFailed("tool call budget exhausted")
            await self._audit(turn, "tool_call", tool="get_customer_profile", customer_id=turn.customer_id)
            turn.profile = await self._services.bank.get_customer_profile(turn.customer_id)
        except ToolFailed:
            await emit_trace(ctx, "customer_agent", started, {"authz.decision": "error", "level": 1}, usage)
            await self._without_customer_data(turn, ctx, CUSTOMER_UNAVAILABLE.format(customer_id=turn.customer_id))
            return
        if not plan.fields:
            await emit_trace(ctx, "customer_agent", started, {"authz.decision": "permitido", "level": 1}, usage)
            await ctx.send_message(turn)
            return
        result = await self._read_fields(turn, plan.fields)
        if isinstance(result, FieldsDenied):
            await emit_trace(
                ctx, "customer_agent", started, {"authz.decision": "403", "fields": result.denied_fields}, usage
            )
            await self._request_access(turn, plan, result, ctx)
            return
        await emit_trace(ctx, "customer_agent", started, {"authz.decision": "permitido", "fields": plan.fields}, usage)
        await ctx.send_message(turn)

    async def _read_fields(self, turn: Turn, fields: list[Level2Field]) -> FieldsDenied | None:
        if not take_tool_call(turn):
            turn.notes.append(CUSTOMER_UNAVAILABLE.format(customer_id=turn.customer_id))
            return None
        await self._audit(turn, "tool_call", tool="get_customer_fields", customer_id=turn.customer_id, fields=fields)
        try:
            result = await self._services.bank.get_customer_fields(turn.customer_id, fields)
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
        if retry:
            denied = await self._read_fields(turn, retry)
            if denied is not None:
                turn.unauthorized_fields += [f for f in denied.denied_fields if f not in turn.unauthorized_fields]
        await emit_trace(
            ctx,
            "customer_agent",
            started,
            {"authz.decision": decided.status, "fields": retry, "unauthorized": turn.unauthorized_fields},
        )
        await ctx.send_message(turn)
