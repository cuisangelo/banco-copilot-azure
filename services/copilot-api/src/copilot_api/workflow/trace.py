import time

from agent_framework import WorkflowContext, WorkflowEvent
from bank_contracts.models import TraceEvent
from opentelemetry import trace

from copilot_api.workflow.llm import Usage

TRACE_EVENT_TYPE = "trace"
SPAN_ATTRIBUTES = {
    "guardrail": "guardrail.layer",
    "authz.decision": "authz.decision",
    "access_request.status": "access_request.status",
}


async def emit_trace(
    ctx: WorkflowContext,
    node: str,
    started: float,
    data: dict,
    usage: Usage | None = None,
) -> None:
    """Publish a node's inspector event and tag the executor span.

    `data` carries field names only, never level-2 values.
    """
    span = trace.get_current_span()
    for key, attribute in SPAN_ATTRIBUTES.items():
        if key in data:
            span.set_attribute(attribute, data[key])
    if usage:
        span.set_attribute("cost_usd_estimate", usage.cost_usd)
    event = TraceEvent(
        node=node,
        duration_ms=int((time.perf_counter() - started) * 1000),
        data=data,
        tokens_in=usage.tokens_in if usage else 0,
        tokens_out=usage.tokens_out if usage else 0,
        cost_usd=usage.cost_usd if usage else 0.0,
    )
    await ctx.add_event(WorkflowEvent(TRACE_EVENT_TYPE, data=event))
