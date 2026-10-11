import time

from agent_framework import Executor, WorkflowContext, handler
from bank_contracts.models import ChatAnswer

from copilot_api.workflow.trace import emit_trace
from copilot_api.workflow.turn import Turn, TurnResult


class Clarifier(Executor):
    """Returns the router's question; the advisor's reply re-enters the router with the session history."""

    def __init__(self) -> None:
        super().__init__(id="clarifier")

    @handler
    async def run(self, turn: Turn, ctx: WorkflowContext[None, TurnResult]) -> None:
        started = time.perf_counter()
        await emit_trace(ctx, "clarifier", started, {})
        await ctx.yield_output(
            TurnResult(ChatAnswer(status="clarification", message=turn.route.clarification_question))
        )
