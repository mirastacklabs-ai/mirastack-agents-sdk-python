"""OpenTelemetry MeterProvider for MIRASTACK Python plugins.

Same gating semantics as ``_otel.py`` — only initialized when
``MIRASTACK_OTEL_ENABLED=true``. Uses the OTLP/gRPC exporter with a
PeriodicExportingMetricReader on a 60-second interval.
"""

from __future__ import annotations

import logging
import os
from typing import Callable

from mirastack_sdk._otel import COMPONENT_KIND, otel_enabled

logger = logging.getLogger("mirastack_sdk.metrics")

METRICS_INTERVAL_MS = 60_000


def _noop_shutdown() -> None:
    pass


def init_meter_provider(plugin_name: str) -> Callable[[], None]:
    """Initialize an OTLP/gRPC MeterProvider on the plugin process.

    Returns a shutdown callable. No-op when OTel is disabled or the
    opentelemetry-sdk packages are not installed.
    """
    if not otel_enabled():
        logger.debug("OTel metrics disabled for plugin")
        return _noop_shutdown

    try:
        from opentelemetry import metrics
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
            OTLPMetricExporter,
        )
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import (
            Resource,
            SERVICE_NAME,
            SERVICE_VERSION,
        )
    except ImportError:
        logger.warning(
            "opentelemetry metrics packages not installed — install "
            "mirastack-agents-sdk[otel] for metrics"
        )
        return _noop_shutdown

    service_name = os.environ.get("OTEL_SERVICE_NAME", plugin_name or "mirastack-plugin")
    service_version = os.environ.get("OTEL_SERVICE_VERSION", "dev")

    resource = Resource.create(
        {
            SERVICE_NAME: service_name,
            SERVICE_VERSION: service_version,
            "mirastack.component_kind": COMPONENT_KIND,
        }
    )
    exporter = OTLPMetricExporter()
    reader = PeriodicExportingMetricReader(exporter, export_interval_millis=METRICS_INTERVAL_MS)
    provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(provider)

    logger.info(
        "OTel metrics enabled for plugin: service=%s interval=%dms",
        service_name,
        METRICS_INTERVAL_MS,
    )

    def shutdown() -> None:
        provider.shutdown()

    return shutdown
