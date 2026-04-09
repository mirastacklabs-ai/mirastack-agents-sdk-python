"""OpenTelemetry auto-instrumentation for MIRASTACK Python plugins.

When ``MIRASTACK_OTEL_ENABLED=true``, the SDK automatically initializes a
TracerProvider with an OTLP/gRPC exporter — plugin authors get distributed
tracing for FREE with zero code changes.

The module mirrors the Go SDK ``otel.go`` pattern: an ``init_otel()`` function
called from ``serve()`` that returns a shutdown callable.
"""

from __future__ import annotations

import logging
import os
from typing import Callable

logger = logging.getLogger("mirastack_sdk.otel")

TRACER_NAME = "mirastack.plugin"

# Sentinel that indicates OTel is not active
def _NOOP_SHUTDOWN() -> None:
    pass


def otel_enabled() -> bool:
    """Return True when MIRASTACK_OTEL_ENABLED is ``"true"``."""
    return os.environ.get("MIRASTACK_OTEL_ENABLED", "").lower() == "true"


def init_otel(plugin_name: str) -> Callable[[], None]:
    """Initialize OpenTelemetry tracing for the plugin process.

    Returns a shutdown callable that flushes pending spans.
    If OTel is disabled or the SDK packages are unavailable,
    returns a no-op callable.
    """
    if not otel_enabled():
        logger.debug("OTel tracing disabled for plugin")
        return _NOOP_SHUTDOWN

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import (
            ParentBasedTraceIdRatio,
        )
    except ImportError:
        logger.warning(
            "opentelemetry packages not installed — install "
            "mirastack-agents-sdk[otel] for auto-tracing"
        )
        return _NOOP_SHUTDOWN

    service_name = os.environ.get("OTEL_SERVICE_NAME", plugin_name or "mirastack-plugin")
    service_version = os.environ.get("OTEL_SERVICE_VERSION", "dev")

    resource = Resource.create(
        {
            SERVICE_NAME: service_name,
            SERVICE_VERSION: service_version,
        }
    )

    sampler_ratio = _sampler_ratio()
    sampler = ParentBasedTraceIdRatio(sampler_ratio)

    provider = TracerProvider(resource=resource, sampler=sampler)
    exporter = OTLPSpanExporter()
    provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)

    logger.info(
        "OTel tracing enabled for plugin: service=%s version=%s ratio=%.2f",
        service_name,
        service_version,
        sampler_ratio,
    )

    def shutdown() -> None:
        provider.shutdown()

    return shutdown


def get_tracer():
    """Return the MIRASTACK plugin tracer (no-op if OTel is not configured)."""
    try:
        from opentelemetry import trace

        return trace.get_tracer(TRACER_NAME)
    except ImportError:
        return None


def _sampler_ratio() -> float:
    """Read OTEL_TRACES_SAMPLER_ARG and return a float in [0, 1]."""
    raw = os.environ.get("OTEL_TRACES_SAMPLER_ARG", "")
    if not raw:
        return 1.0
    try:
        ratio = float(raw)
    except ValueError:
        return 1.0
    if ratio < 0 or ratio > 1:
        return 1.0
    return ratio
