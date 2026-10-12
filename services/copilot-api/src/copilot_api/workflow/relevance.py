import time
from typing import Literal

from agent_framework import Executor, WorkflowContext, handler
from bank_contracts.models import ChatAnswer
from pydantic import BaseModel

from copilot_api.prompts import load_prompt
from copilot_api.workflow.trace import emit_trace
from copilot_api.workflow.turn import Services, Turn, TurnResult, level2_values

RELEVANCE_EXECUTOR_ID = "relevance"
CANNOT_ANSWER_MESSAGE = (
    "No puedo responder eso con la información que tengo. Puedo ayudarte con requisitos y pasos de productos y "
    "trámites de Banco Austral, comparar productos y, con permiso, revisar datos de un cliente."
)
PARTIAL_NOTE = "\nNo encontré respaldo para esta parte de la consulta: {missing}."


class RelevanceVerdict(BaseModel):
    verdict: Literal["answers", "partial", "off_topic"]
    missing: str | None


def _render(turn: Turn) -> str:
    answer = turn.answer
    claims = "\n".join(f"- {claim.text}" for claim in answer.requirements + answer.steps)
    return (
        f"Consulta del asesor:\n{turn.message}\n\nEntendida como:\n{turn.route.search_query}\n\n"
        f"Respuesta:\n{answer.message}\n{claims}"
    )


class Relevance(Executor):
    """Checks that a verified answer answers the question asked, not a neighbouring one.

    Citations and groundedness prove each claim comes from a source; they cannot tell that every claim
    is about something else ("which documents do you have" answered with the documents a customer brings).
    """

    def __init__(self, services: Services) -> None:
        super().__init__(id=RELEVANCE_EXECUTOR_ID)
        self._services = services
        self._system = load_prompt("relevance")

    @handler
    async def run(self, turn: Turn, ctx: WorkflowContext[Turn, TurnResult]) -> None:
        started = time.perf_counter()
        verdict, usage = await self._services.llm.structured(RelevanceVerdict, system=self._system, user=_render(turn))
        await emit_trace(
            ctx,
            RELEVANCE_EXECUTOR_ID,
            started,
            {"verdict": verdict.verdict} | ({"guardrail": "relevance"} if verdict.verdict == "off_topic" else {}),
            usage,
        )
        if verdict.verdict == "off_topic":
            await ctx.yield_output(TurnResult(ChatAnswer(status="rejected", message=CANNOT_ANSWER_MESSAGE)))
            return
        answer = turn.answer
        if verdict.verdict == "partial" and verdict.missing:
            answer = answer.model_copy(update={"message": answer.message + PARTIAL_NOTE.format(missing=verdict.missing)})
        await ctx.yield_output(TurnResult(answer, level2_values(turn)))
