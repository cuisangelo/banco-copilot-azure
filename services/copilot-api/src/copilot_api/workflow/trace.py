import time

from agent_framework import WorkflowContext, WorkflowEvent
from bank_contracts.models import TraceEvent

from copilot_api.workflow.llm import Usage

TRACE_EVENT_TYPE = "trace"


async def emit_trace(
    ctx: WorkflowContext,
    node: str,
    started: float,
    data: dict,
    usage: Usage | None = None,
) -> None:
    """Publish a node's inspector event. `data` must carry field names only, never level-2 values."""
    event = TraceEvent(
        node=node,
        duration_ms=int((time.perf_counter() - started) * 1000),
        data=data,
        tokens_in=usage.tokens_in if usage else 0,
        tokens_out=usage.tokens_out if usage else 0,
    )
    await ctx.add_event(WorkflowEvent(TRACE_EVENT_TYPE, data=event))
