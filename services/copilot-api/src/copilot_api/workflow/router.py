import time
from typing import Literal, Self

from agent_framework import Executor, WorkflowContext, handler
from bank_contracts.models import ChatAnswer
from pydantic import BaseModel, model_validator

from copilot_api.prompts import load_prompt
from copilot_api.workflow.trace import emit_trace
from copilot_api.workflow.turn import Services, Turn, TurnResult

Route = Literal["procedure", "product", "customer", "mixed", "out_of_scope", "missing_context"]

OUT_OF_SCOPE_MESSAGE = (
    "Esta consulta está fuera de lo que puedo responder: solo trabajo con productos y procedimientos "
    "vigentes de Banco Austral."
)


class RouteDecision(BaseModel):
    route: Route
    search_query: str
    # Checkpoints written before this field existed still load.
    topics: list[str] = []
    customer_id: str | None = None
    clarification_question: str | None = None

    @model_validator(mode="after")
    def _question_when_context_is_missing(self) -> Self:
        if self.route == "missing_context" and not self.clarification_question:
            raise ValueError("missing_context requires clarification_question")
        return self


def render_history(turn: Turn) -> str:
    lines = [f"Asesor: {entry.question}\nCopiloto: {entry.answer}" for entry in turn.history]
    return "\n\n".join(lines) or "(sin historial)"


class Router(Executor):
    def __init__(self, services: Services) -> None:
        super().__init__(id="router")
        self._services = services
        self._system = load_prompt("router")

    @handler
    async def run(self, turn: Turn, ctx: WorkflowContext[Turn, TurnResult]) -> None:
        started = time.perf_counter()
        customer = f"Cliente en atención: {turn.customer_id}\n\n" if turn.customer_id else ""
        decision, usage = await self._services.llm.structured(
            RouteDecision,
            system=self._system,
            user=f"{customer}Historial:\n{render_history(turn)}\n\nConsulta actual:\n{turn.message}",
        )
        data = {"route": decision.route, "understood_as": decision.search_query, "topics": decision.topics}
        if decision.route == "out_of_scope":
            data["guardrail"] = "router_out_of_scope"
        await emit_trace(ctx, "router", started, data, usage)
        turn.route = decision
        turn.customer_id = decision.customer_id or turn.customer_id
        if decision.route == "out_of_scope":
            await ctx.yield_output(TurnResult(ChatAnswer(status="rejected", message=OUT_OF_SCOPE_MESSAGE)))
            return
        await ctx.send_message(turn)
