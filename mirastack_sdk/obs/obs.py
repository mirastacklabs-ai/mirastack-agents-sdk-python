"""Implementation of the agent-side observability helper.

The Python ``start_action`` context manager mirrors the Go SDK
``obs.StartAction`` helper: open a span, time the work, classify any
exception by its type name (PII-safe), and emit the canonical metric
pair ``mirastack_agent_actions_total`` +
``mirastack_agent_action_latency_seconds``.

Vocabulary owned by this module is declared in
``developer/engine-agents-connectors-providers/notes/mirastack-observability-semconv.md``
§3.2 (span name ``agent.action``) and §4.2 (metric names).
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator, Optional

TRACER_NAME = "github.com/mirastacklabs-ai/mirastack-agents-sdk-python"
METER_NAME = TRACER_NAME


class ActionSpan:
    """Thin wrapper around the OTel span.

    Nil-safe: when the OTel SDK is missing or ``MIRASTACK_OTEL_ENABLED``
    is not ``"true"`` every method is a no-op.
    """

    def __init__(self, span: Optional[object]) -> None:
        self._span = span
        self._input_bytes: int = 0
        self._output_bytes: int = 0

    def set_attribute(self, key: str, value: object) -> None:
        if self._span is None:
            return
        try:
            self._span.set_attribute(key, value)  # type: ignore[attr-defined]
        except Exception:
            pass

    def set_io_bytes(self, input_bytes: int, output_bytes: int) -> None:
        self._input_bytes = input_bytes
        self._output_bytes = output_bytes


def _err_class(exc: BaseException) -> str:
    """Return a PII-safe classification of the exception."""
    cls = type(exc)
    mod = getattr(cls, "__module__", "")
    name = getattr(cls, "__qualname__", cls.__name__)
    return f"{mod}.{name}" if mod and mod != "builtins" else name


@contextmanager
def start_action(plugin_name: str, action_id: str, permission: str) -> Iterator[ActionSpan]:
    """Open an ``agent.action`` span + emit the canonical metric pair."""
    try:
        from opentelemetry import metrics as _metrics
        from opentelemetry import trace as _trace
    except ImportError:
        yield ActionSpan(None)
        return

    tracer = _trace.get_tracer(TRACER_NAME)
    meter = _metrics.get_meter(METER_NAME)
    counter = meter.create_counter("mirastack_agent_actions_total")
    histogram = meter.create_histogram(
        "mirastack_agent_action_latency_seconds", unit="s"
    )

    start = time.monotonic()
    outcome = "ok"
    wrapper = ActionSpan(None)
    with tracer.start_as_current_span(
        "agent.action",
        attributes={
            "agent.plugin": plugin_name,
            "agent.action": action_id,
            "agent.permission": permission,
        },
    ) as span:
        wrapper._span = span
        try:
            yield wrapper
        except BaseException as exc:
            outcome = "error"
            try:
                from opentelemetry.trace import Status, StatusCode

                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, _err_class(exc)))
            except Exception:
                pass
            raise
        finally:
            elapsed = time.monotonic() - start
            try:
                span.set_attribute("agent.outcome", outcome)
                span.set_attribute("agent.input_bytes", wrapper._input_bytes)
                span.set_attribute("agent.output_bytes", wrapper._output_bytes)
                span.set_attribute("agent.latency_ms", int(elapsed * 1000))
            except Exception:
                pass
            metric_attrs = {
                "plugin": plugin_name,
                "action": action_id,
                "outcome": outcome,
            }
            try:
                counter.add(1, attributes=metric_attrs)
                histogram.record(elapsed, attributes=metric_attrs)
            except Exception:
                pass
