import logging
from collections.abc import Mapping, Sequence

from agent_framework.observability import configure_otel_providers
from azure.monitor.opentelemetry.exporter import AzureMonitorTraceExporter
from opentelemetry.sdk.trace import Event, ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

from copilot_api.guards.pii_mask import mask_pii

DROPPED_ATTRIBUTE_PREFIX = "customer.values"


def _mask_value(value):
    if isinstance(value, str):
        return mask_pii(value)
    if isinstance(value, Sequence) and not isinstance(value, bytes):
        return tuple(mask_pii(item) if isinstance(item, str) else item for item in value)
    return value


def _sanitize(attributes: Mapping | None) -> dict:
    return {
        key: _mask_value(value)
        for key, value in (attributes or {}).items()
        if not key.startswith(DROPPED_ATTRIBUTE_PREFIX)
    }


def _sanitized_span(span: ReadableSpan) -> ReadableSpan:
    return ReadableSpan(
        name=span.name,
        context=span.context,
        parent=span.parent,
        resource=span.resource,
        attributes=_sanitize(span.attributes),
        events=[Event(event.name, _sanitize(event.attributes), event.timestamp) for event in span.events],
        links=span.links,
        kind=span.kind,
        status=span.status,
        start_time=span.start_time,
        end_time=span.end_time,
        instrumentation_scope=span.instrumentation_scope,
    )


class PiiMaskingSpanExporter(SpanExporter):
    """Masks RUT, card numbers and e-mails and drops customer.values* before any span leaves the process.

    Wraps the exporter rather than adding a processor so it sees each span's final attributes.
    """

    def __init__(self, inner: SpanExporter) -> None:
        self._inner = inner

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        return self._inner.export([_sanitized_span(span) for span in spans])

    def shutdown(self) -> None:
        self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._inner.force_flush(timeout_millis)


class PiiMaskingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = mask_pii(record.getMessage())
        record.args = None
        return True


def configure_telemetry(connection_string: str) -> None:
    exporter = PiiMaskingSpanExporter(AzureMonitorTraceExporter(connection_string=connection_string))
    configure_otel_providers(service_name="copilot-api", enable_sensitive_data=False, exporters=[exporter])
    for handler in logging.getLogger().handlers:
        handler.addFilter(PiiMaskingFilter())
