import json
import logging

import httpx
import pytest
from agent_framework.observability import enable_instrumentation, enable_sensitive_telemetry
from agent_framework.openai import OpenAIChatCompletionClient
from openai import AsyncOpenAI
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from copilot_api.pricing import cost_usd
from copilot_api.telemetry import PiiMaskingFilter, PiiMaskingSpanExporter
from copilot_api.workflow.llm import Llm
from copilot_api.workflow.router import RouteDecision

RUT = "12.345.678-9"
PAN = "4111 1111 1111 1111"


@pytest.fixture(scope="module")
def exported() -> InMemorySpanExporter:
    """The process-wide tracer provider, exporting through the masking exporter like production does."""
    memory = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(PiiMaskingSpanExporter(memory)))
    trace.set_tracer_provider(provider)
    enable_instrumentation()
    enable_sensitive_telemetry()
    return memory


def _exported_values(memory: InMemorySpanExporter) -> list[str]:
    values = []
    for span in memory.get_finished_spans():
        values += [str(value) for value in span.attributes.values()]
        for event in span.events:
            values += [str(value) for value in (event.attributes or {}).values()]
    return values


def _chat_completions(request: httpx.Request) -> httpx.Response:
    decision = RouteDecision(route="procedure", search_query="requisitos de crédito de consumo")
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-1",
            "object": "chat.completion",
            "created": 1760000000,
            "model": "gpt-4.1-mini",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": decision.model_dump_json()},
                }
            ],
            "usage": {"prompt_tokens": 1000, "completion_tokens": 200, "total_tokens": 1200},
        },
    )


async def test_real_chat_client_spans_mask_rut_and_card_and_report_cost(exported):
    openai = AsyncOpenAI(
        api_key="test",
        base_url="https://aoai.example/openai/v1/",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(_chat_completions)),
    )
    llm = Llm(OpenAIChatCompletionClient(model="gpt-4.1-mini", async_client=openai), model="gpt-4.1-mini")
    exported.clear()

    decision, usage = await llm.structured(
        RouteDecision, system="Clasifica.", user=f"Cliente RUT {RUT}, tarjeta {PAN}, quiere crédito de consumo"
    )

    assert decision.route == "procedure"
    assert usage.cost_usd == pytest.approx(1000 * 0.40 / 1e6 + 200 * 1.60 / 1e6)
    values = _exported_values(exported)
    assert any("[RUT]" in value for value in values), "the prompt must reach the spans for this test to mean anything"
    assert not any(RUT in value or PAN in value for value in values)


def test_customer_values_attributes_never_leave_the_process(exported):
    exported.clear()
    with trace.get_tracer("test").start_as_current_span("customer_agent") as span:
        span.set_attribute("customer.values.monthly_income", 1850000)
        span.set_attribute("customer.values", json.dumps({"current_debt": 420000}))
        span.set_attribute("authz.decision", "allowed")

    (finished,) = exported.get_finished_spans()
    assert dict(finished.attributes) == {"authz.decision": "allowed"}


def test_log_records_are_masked():
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "asesor escribió %s y %s", (RUT, "ana@correo.cl"), None)

    PiiMaskingFilter().filter(record)

    assert record.getMessage() == "asesor escribió [RUT] y [EMAIL]"


def test_pricing_uses_the_versioned_table():
    assert cost_usd("gpt-4.1-mini", 1_000_000, 1_000_000) == pytest.approx(2.00)
    assert cost_usd("text-embedding-3-small", 1_000_000, 0) == pytest.approx(0.02)
    with pytest.raises(KeyError):
        cost_usd("gpt-unknown", 1, 1)
