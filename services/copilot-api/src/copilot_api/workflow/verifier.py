import time

from agent_framework import Executor, WorkflowContext, handler
from bank_contracts.models import LEVEL2_FIELDS, ChatAnswer, Claim

from copilot_api.workflow.composer import DraftClaim
from copilot_api.workflow.escalation import ESCALATION_EXECUTOR_ID, EscalationCase
from copilot_api.workflow.trace import emit_trace
from copilot_api.workflow.turn import Services, Turn, TurnResult, level2_values

UNSUPPORTED_MESSAGE = (
    "No encuentro respaldo suficiente en las fuentes para responder con seguridad. Te propongo escalar la consulta."
)
CONTRADICTION_MESSAGE = (
    "Las fuentes se contradicen sobre «{attribute}». Te muestro ambas y te propongo escalar para confirmar cuál rige."
)
FIELD_LABELS = {
    "monthly_income": "renta mensual",
    "current_debt": "deuda vigente",
    "payment_behavior": "comportamiento de pago",
    "employment_tenure_months": "antigüedad laboral",
}
assert FIELD_LABELS.keys() == set(LEVEL2_FIELDS)


def _normalize(text: str) -> str:
    return " ".join(text.casefold().split())


def find_contradiction(claims: list[DraftClaim]) -> str | None:
    """The first attribute whose conflicting values change the conclusion, if any.

    Without a customer verdict every conflict matters; with one, sources that disagree on the value but
    agree on whether this customer meets it lead to the same answer, which then cites both.
    """
    values: dict[tuple[str, str], set[str]] = {}
    verdicts: dict[tuple[str, str], set[bool | None]] = {}
    names: dict[tuple[str, str], str] = {}
    for claim in claims:
        if claim.attribute and claim.value:
            # The same attribute on two products (minimum age of Oro vs Platinum) is not a conflict.
            key = (_normalize(claim.subject or ""), _normalize(claim.attribute))
            names.setdefault(key, claim.attribute.strip())
            values.setdefault(key, set()).add(_normalize(claim.value))
            verdicts.setdefault(key, set()).add(claim.customer_meets)
    return next(
        (names[key] for key, seen in values.items() if len(seen) > 1 and (None in verdicts[key] or len(verdicts[key]) > 1)),
        None,
    )


def _claims(drafts: list[DraftClaim]) -> list[Claim]:
    return [Claim(text=draft.text, citation_ids=draft.citation_ids) for draft in drafts]


def _caveats(turn: Turn) -> str:
    lines = [*turn.notes]
    lines += [f"{FIELD_LABELS[field]}: no autorizado — verificar con el cliente" for field in turn.unauthorized_fields]
    return "".join(f"\n{line}" for line in lines)


class Verifier(Executor):
    def __init__(self, services: Services) -> None:
        super().__init__(id="verifier")
        self._services = services

    @handler
    async def run(self, turn: Turn, ctx: WorkflowContext[EscalationCase, TurnResult]) -> None:
        started = time.perf_counter()
        composed = turn.composed
        claims = composed.requirements + composed.steps
        known = {citation.id for citation in turn.citations}
        text = "\n".join([composed.message, *(claim.text for claim in claims)])
        ungrounded = await self._services.safety.ungrounded(
            text, [citation.snippet for citation in turn.citations], query=turn.message
        )
        uncited = [claim.text for claim in claims if not claim.citation_ids or not set(claim.citation_ids) <= known]
        conflict = None if ungrounded or uncited else find_contradiction(claims)
        await emit_trace(
            ctx,
            "verifier",
            started,
            {"uncited_claims": len(uncited), "contradiction": conflict}
            | ({"guardrail": "groundedness"} if ungrounded else {}),
        )
        if ungrounded or uncited:
            answer = ChatAnswer(status="insufficient", message=UNSUPPORTED_MESSAGE + _caveats(turn))
            reason = "respuesta sin sustento en las fuentes" if ungrounded else "afirmaciones sin cita"
            await ctx.send_message(EscalationCase(turn, answer, reason=reason), target_id=ESCALATION_EXECUTOR_ID)
            return
        if conflict:
            answer = ChatAnswer(
                status="contradiction",
                message=CONTRADICTION_MESSAGE.format(attribute=conflict) + _caveats(turn),
                requirements=_claims(composed.requirements),
                steps=_claims(composed.steps),
                citations=turn.citations,
            )
            await ctx.send_message(
                EscalationCase(turn, answer, reason=f"contradicción sobre {conflict}"), target_id=ESCALATION_EXECUTOR_ID
            )
            return
        answer = ChatAnswer(
            status="ok",
            message=composed.message + _caveats(turn),
            requirements=_claims(composed.requirements),
            steps=_claims(composed.steps),
            citations=turn.citations,
        )
        await ctx.yield_output(TurnResult(answer, level2_values(turn)))
