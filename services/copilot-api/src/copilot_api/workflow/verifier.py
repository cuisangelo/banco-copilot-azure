import time
from itertools import combinations

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
GROUNDED_LEAD_IN = "Esto es lo que respaldan las fuentes:"
FIELD_LABELS = {
    "monthly_income": "renta mensual",
    "current_debt": "deuda vigente",
    "payment_behavior": "comportamiento de pago",
    "employment_tenure_months": "antigüedad laboral",
}
assert FIELD_LABELS.keys() == set(LEVEL2_FIELDS)


def _normalize(text: str) -> str:
    return " ".join(text.casefold().split())


def _overlaps(text: str, segments: list[str]) -> bool:
    normalized = _normalize(text)
    return any(segment in normalized or normalized in segment for segment in segments)


def _dropped_note(count: int) -> str:
    return f"\nOmití {count} {'afirmación' if count == 1 else 'afirmaciones'} que las fuentes no respaldan."


def find_contradiction(claims: list[DraftClaim], customer_citation_ids: set[str]) -> str | None:
    """The first attribute on which two sources disagree in a way that changes the conclusion, if any.

    Only values backed by disjoint bank sources conflict: one sheet listing several documents is a
    list, not a contradiction, and customer data is cited by both sides so it does not count. Without
    a customer verdict every conflict matters; with one, sources that disagree on the value but agree on
    whether this customer meets it lead to the same answer, which then cites both.
    """
    groups: dict[tuple[str, str], list[tuple[str, frozenset[str], bool | None]]] = {}
    names: dict[tuple[str, str], str] = {}
    for claim in claims:
        if claim.attribute and claim.value:
            # The same attribute on two products (minimum age of Oro vs Platinum) is not a conflict.
            key = (_normalize(claim.subject or ""), _normalize(claim.attribute))
            names.setdefault(key, claim.attribute.strip())
            sources = frozenset(claim.citation_ids) - customer_citation_ids
            groups.setdefault(key, []).append((_normalize(claim.value), sources, claim.customer_meets))
    for key, entries in groups.items():
        for (value_a, sources_a, meets_a), (value_b, sources_b, meets_b) in combinations(entries, 2):
            disjoint = sources_a and sources_b and sources_a.isdisjoint(sources_b)
            if value_a != value_b and disjoint and (meets_a is None or meets_b is None or meets_a != meets_b):
                return names[key]
    return None


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
        if not claims:
            # Nothing cited means nothing verified: "not in the documentation" is a miss, never an ok.
            await emit_trace(ctx, "verifier", started, {"claims": 0})
            answer = ChatAnswer(status="insufficient", message=composed.message + _caveats(turn))
            await ctx.send_message(
                EscalationCase(turn, answer, reason="respuesta sin afirmaciones respaldadas"),
                target_id=ESCALATION_EXECUTOR_ID,
            )
            return
        known = {citation.id for citation in turn.citations}
        parts = [composed.message, *(claim.text for claim in claims)]
        groundedness = await self._services.safety.groundedness(
            "\n".join(parts), [citation.snippet for citation in turn.citations], query=turn.message
        )
        segments = [segment for segment in map(_normalize, groundedness.segments) if segment]
        dropped = [claim for claim in claims if _overlaps(claim.text, segments)]
        # A flagged passage that is neither the message nor inside a claim cannot be removed claim by claim.
        unattributed = any(not any(_overlaps(part, [segment]) for part in parts) for segment in segments)
        kept_requirements = [claim for claim in composed.requirements if claim not in dropped]
        kept_steps = [claim for claim in composed.steps if claim not in dropped]
        kept = kept_requirements + kept_steps
        ungrounded = unattributed or not kept or len(dropped) * 2 > len(claims)
        uncited = [claim.text for claim in claims if not claim.citation_ids or not set(claim.citation_ids) <= known]
        customer_ids = {citation.id for citation in turn.citations if citation.kind == "customer"}
        conflict = None if ungrounded or uncited else find_contradiction(kept, customer_ids)
        await emit_trace(
            ctx,
            "verifier",
            started,
            {
                "uncited_claims": len(uncited),
                "dropped_claims": len(dropped),
                "contradiction": conflict,
                "ungrounded_percentage": round(groundedness.percentage, 2),
            }
            | ({"guardrail": "groundedness"} if groundedness.percentage > 0 else {}),
        )
        if ungrounded or uncited:
            answer = ChatAnswer(status="insufficient", message=UNSUPPORTED_MESSAGE + _caveats(turn))
            reason = "respuesta sin sustento en las fuentes" if ungrounded else "afirmaciones sin cita"
            await ctx.send_message(EscalationCase(turn, answer, reason=reason), target_id=ESCALATION_EXECUTOR_ID)
            return
        message = (GROUNDED_LEAD_IN if _overlaps(composed.message, segments) else composed.message) + (
            _dropped_note(len(dropped)) if dropped else ""
        )
        if conflict:
            answer = ChatAnswer(
                status="contradiction",
                message=CONTRADICTION_MESSAGE.format(attribute=conflict) + _caveats(turn),
                requirements=_claims(kept_requirements),
                steps=_claims(kept_steps),
                citations=turn.citations,
            )
            await ctx.send_message(
                EscalationCase(turn, answer, reason=f"contradicción sobre {conflict}"), target_id=ESCALATION_EXECUTOR_ID
            )
            return
        answer = ChatAnswer(
            status="ok",
            message=message + _caveats(turn),
            requirements=_claims(kept_requirements),
            steps=_claims(kept_steps),
            citations=turn.citations,
        )
        await ctx.yield_output(TurnResult(answer, level2_values(turn)))
