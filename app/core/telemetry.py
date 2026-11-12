"""OpenTelemetry tracing, metrics, and runtime instrumentation setup."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.system_metrics import SystemMetricsInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

if TYPE_CHECKING:
    from fastapi import FastAPI
    from sqlalchemy import Engine

_TELEMETRY_CONFIGURED = False


def setup_telemetry(app: FastAPI, engine: Engine) -> None:
    """Configure OpenTelemetry SDK when OTEL_EXPORTER_OTLP_ENDPOINT is provided."""
    global _TELEMETRY_CONFIGURED

    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if not otlp_endpoint:
        return

    service_name = os.getenv("OTEL_SERVICE_NAME", "chronostore-api-fastapi")
    environment = os.getenv("APP_ENV", "local")

    if not _TELEMETRY_CONFIGURED:
        resource = Resource.create(
            {
                "service.name": service_name,
                "service.version": "1.0.0",
                "service.namespace": "chronostore",
                "deployment.environment": environment,
                "backend.stack": "python-fastapi",
            }
        )

        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(tracer_provider)

        metric_reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(),
            export_interval_millis=int(os.getenv("OTEL_METRIC_EXPORT_INTERVAL", "15000")),
        )
        meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
        metrics.set_meter_provider(meter_provider)

        SQLAlchemyInstrumentor().instrument(engine=engine)
        SystemMetricsInstrumentor().instrument()
        _TELEMETRY_CONFIGURED = True

    FastAPIInstrumentor.instrument_app(app, excluded_urls="health/live")

