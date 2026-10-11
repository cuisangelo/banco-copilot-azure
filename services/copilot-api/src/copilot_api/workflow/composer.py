import time

from agent_framework import Executor, WorkflowContext, handler
from bank_contracts.models import ChatAnswer, Citation, Product
from pydantic import BaseModel

from copilot_api.prompts import load_prompt
from copilot_api.workflow.escalation import ESCALATION_EXECUTOR_ID, EscalationCase
from copilot_api.workflow.trace import emit_trace
from copilot_api.workflow.turn import Services, Turn

NO_SOURCES_MESSAGE = "No tengo fuentes vigentes para responder esta consulta. Puedo ayudarte a escalarla."


class DraftClaim(BaseModel):
    text: str
    citation_ids: list[str]
    subject: str | None = None
    attribute: str | None = None
    value: str | None = None
    customer_meets: bool | None = None


class ComposerOutput(BaseModel):
    message: str
    requirements: list[DraftClaim]
    steps: list[DraftClaim]


def _product_snippet(product: Product) -> str:
    rate = f"{product.annual_rate_pct}% anual" if product.annual_rate_pct is not None else "sin tasa"
    fee = f"${product.monthly_fee_clp:,} mensual".replace(",", ".") if product.monthly_fee_clp is not None else "sin cargo"
    return f"{product.name}: tasa {rate}; mantención {fee}; requisitos: {'; '.join(product.requirements)}"


def build_citations(turn: Turn) -> list[Citation]:
    """Number every piece of evidence S1..Sn; claims may only point at these ids."""
    sources: list[tuple[str, str, str]] = [
        ("doc", f"{chunk.doc_id} §{chunk.section}", chunk.content) for chunk in turn.chunks
    ]
    sources += [("product", f"producto:{product.id}", _product_snippet(product)) for product in turn.products]
    if turn.profile is not None:
        profile = turn.profile
        products = [
            f"{turn.product_names[product_id]} ({product_id})" if product_id in turn.product_names else product_id
            for product_id in profile.products
        ]
        sources.append((
            "customer",
            f"cliente:{profile.customer_id} perfil",
            f"segmento {profile.segment}; renta {profile.income_type}; productos: {', '.join(products) or 'ninguno'}; "
            f"antigüedad como cliente: {profile.customer_tenure_months} meses",
        ))
    if turn.customer_fields is not None:
        customer_id = turn.customer_fields.customer_id
        sources += [
            ("customer", f"cliente:{customer_id} {name}", f"{name}: {value}")
            for name, value in turn.customer_fields.values.items()
        ]
    return [
        Citation(id=f"S{number}", kind=kind, ref=ref, snippet=snippet)
        for number, (kind, ref, snippet) in enumerate(sources, start=1)
    ]


def _render_sources(citations: list[Citation]) -> str:
    return "\n\n".join(f"[{citation.id}] ({citation.ref})\n{citation.snippet}" for citation in citations)


class Composer(Executor):
    def __init__(self, services: Services) -> None:
        super().__init__(id="composer")
        self._services = services
        self._system = load_prompt("composer")

    @handler
    async def run(self, turn: Turn, ctx: WorkflowContext[Turn | EscalationCase]) -> None:
        started = time.perf_counter()
        turn.citations = build_citations(turn)
        if not turn.citations:
            await emit_trace(ctx, "composer", started, {"citations": 0})
            answer = ChatAnswer(status="insufficient", message=NO_SOURCES_MESSAGE)
            await ctx.send_message(EscalationCase(turn, answer, reason="sin fuentes"), target_id=ESCALATION_EXECUTOR_ID)
            return
        turn.composed, usage = await self._services.llm.structured(
            ComposerOutput,
            system=self._system,
            user=f"Consulta del asesor:\n{turn.message}\n\nFuentes:\n{_render_sources(turn.citations)}",
        )
        claims = turn.composed.requirements + turn.composed.steps
        await emit_trace(ctx, "composer", started, {"citations": len(turn.citations), "claims": len(claims)}, usage)
        await ctx.send_message(turn, target_id="verifier")
