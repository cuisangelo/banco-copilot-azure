import time
import uuid
from dataclasses import dataclass

from agent_framework import Executor, WorkflowContext, handler, response_handler
from bank_contracts.models import LEVEL2_FIELDS, ChatAnswer, Citation, EscalationDecision, EscalationDraft

from copilot_api.workflow.trace import emit_trace
from copilot_api.workflow.turn import Services, Turn, TurnResult, level2_values

ESCALATION_EXECUTOR_ID = "escalation"
ESCALATION_STATE_KEY = "escalation"
AREAS = {
    "procedure": "procedimientos",
    "product": "productos",
    "customer": "clientes",
    "mixed": "procedimientos",
}


@dataclass
class EscalationCase:
    turn: Turn
    answer: ChatAnswer
    reason: str


@dataclass
class EscalationOutcome:
    ticket_id: str | None
    discarded: bool


def _redacted(citation: Citation) -> Citation:
    """Tickets leave the session: level-2 values are replaced, the field name stays."""
    field = citation.ref.rsplit(" ", 1)[-1]
    if citation.kind == "customer" and field in LEVEL2_FIELDS:
        return citation.model_copy(update={"snippet": f"{field}: [reservado]"})
    return citation


class Escalation(Executor):
    def __init__(self, services: Services) -> None:
        super().__init__(id=ESCALATION_EXECUTOR_ID)
        self._services = services

    @handler
    async def run(self, case: EscalationCase, ctx: WorkflowContext[None, TurnResult]) -> None:
        started = time.perf_counter()
        turn = case.turn
        draft = EscalationDraft(
            id=str(uuid.uuid4()),
            area=AREAS[turn.route.route],
            summary=f"Consulta del asesor: {turn.message}\nMotivo: {case.reason}",
            evidence=[_redacted(citation) for citation in case.answer.citations or turn.citations],
        )
        ctx.set_state(ESCALATION_STATE_KEY, {"actor": turn.actor, "session_id": turn.session_id})
        await emit_trace(ctx, "escalation", started, {"escalation_id": draft.id, "reason": case.reason})
        answer = case.answer.model_copy(update={"escalation": draft})
        await ctx.yield_output(TurnResult(answer, level2_values(turn)))
        await ctx.request_info(draft, EscalationDecision, request_id=draft.id)

    @response_handler
    async def on_decision(
        self, draft: EscalationDraft, decision: EscalationDecision, ctx: WorkflowContext[None, EscalationOutcome]
    ) -> None:
        origin = ctx.get_state(ESCALATION_STATE_KEY)
        ticket_id = f"TCK-{uuid.uuid4().hex[:8].upper()}" if decision.approve else None
        data = {"session_id": origin["session_id"], "escalation_id": draft.id, "approved": decision.approve}
        if ticket_id:
            data["ticket_id"] = ticket_id
        await self._services.store.audit(actor=origin["actor"], event="escalation_decision", data=data)
        await ctx.yield_output(EscalationOutcome(ticket_id=ticket_id, discarded=not decision.approve))
