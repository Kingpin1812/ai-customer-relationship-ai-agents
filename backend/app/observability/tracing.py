from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.core.config import get_settings

_configured = False


def configure_tracing() -> None:
    """Install the SDK once per process. Spans export only if an OTLP endpoint is configured."""
    global _configured
    if _configured:
        return
    provider = TracerProvider(resource=Resource.create({"service.name": "workflow-backend"}))
    endpoint = get_settings().otel_exporter_otlp_endpoint
    if endpoint:
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)
    _configured = True


def instrument_app(app: FastAPI) -> None:
    configure_tracing()
    FastAPIInstrumentor.instrument_app(app, excluded_urls="/metrics,/api/v1/health/.*")
