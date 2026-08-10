"""OpenTelemetry MeterProvider for MIRASTACK Python plugins.

Same gating semantics as ``_otel.py`` — only initialized when
``MIRASTACK_OTEL_ENABLED=true``. Uses the OTLP/gRPC exporter with a
PeriodicExportingMetricReader on a 60-second interval.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable

from mirastack_sdk._otel import COMPONENT_KIND, otel_enabled

logger = logging.getLogger("mirastack_sdk.metrics")

DEFAULT_METRICS_INTERVAL_MS = 60_000


def _noop_shutdown() -> None:
    pass


def _parse_duration_ms(raw: str) -> int | None:
    value = raw.strip().lower()
    if not value:
        return None
    units = (
        ("ms", 1),
        ("s", 1_000),
        ("m", 60_000),
        ("h", 3_600_000),
    )
    for suffix, factor in units:
        if value.endswith(suffix):
            number = value[: -len(suffix)].strip()
            if not number:
                return None
            try:
                parsed = float(number)
            except ValueError:
                return None
            if parsed <= 0:
                return None
            return int(parsed * factor)
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def _metrics_interval_ms() -> int:
    raw = os.environ.get("MIRASTACK_OTEL_METRIC_EXPORT_INTERVAL", "").strip()
    if not raw:
        return DEFAULT_METRICS_INTERVAL_MS
    parsed = _parse_duration_ms(raw)
    if parsed is None:
        logger.warning(
            "invalid MIRASTACK_OTEL_METRIC_EXPORT_INTERVAL; using SDK default: %s",
            raw,
        )
        return DEFAULT_METRICS_INTERVAL_MS
    return parsed


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
            SERVICE_NAME,
            SERVICE_VERSION,
            Resource,
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
    interval_ms = _metrics_interval_ms()
    reader = PeriodicExportingMetricReader(exporter, export_interval_millis=interval_ms)
    provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(provider)

    logger.info(
        "OTel metrics enabled for plugin: service=%s interval=%dms",
        service_name,
        interval_ms,
    )

    def shutdown() -> None:
        provider.shutdown()

    return shutdown
