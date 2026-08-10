"""OpenTelemetry log bridge for MIRASTACK Python plugins."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable

from mirastack_sdk._otel import COMPONENT_KIND, otel_enabled

logger = logging.getLogger("mirastack_sdk.logging")


def _noop_shutdown() -> None:
    pass


def init_logging_handler(plugin_name: str) -> Callable[[], None]:
    """Attach an OTLP LoggingHandler to the SDK logger."""
    if not otel_enabled():
        logger.debug("OTel logs disabled for plugin")
        return _noop_shutdown

    try:
        from opentelemetry import _logs
        from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
        from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
        from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
    except ImportError:
        logger.warning(
            "opentelemetry logging packages not installed — install "
            "mirastack-agents-sdk[otel] for logs"
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

    provider = LoggerProvider(resource=resource)
    provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
    _logs.set_logger_provider(provider)

    sdk_logger = logging.getLogger("mirastack_sdk")
    handler = LoggingHandler(level=logging.NOTSET, logger_provider=provider)
    sdk_logger.addHandler(handler)

    logger.info("OTel logs enabled for plugin: service=%s", service_name)

    def shutdown() -> None:
        sdk_logger.removeHandler(handler)
        handler.close()
        provider.shutdown()

    return shutdown
