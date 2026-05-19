"""Tests for the agent-side observability helpers."""

from __future__ import annotations

import pytest

from mirastack_sdk._metrics import init_meter_provider
from mirastack_sdk._otel import init_otel
from mirastack_sdk.obs import start_action
from mirastack_sdk.obs.obs import _err_class


def test_init_otel_disabled_by_default(monkeypatch):
    monkeypatch.delenv("MIRASTACK_OTEL_ENABLED", raising=False)
    shutdown = init_otel("test-plugin")
    # No-op shutdown must not raise
    shutdown()


def test_init_meter_provider_disabled_by_default(monkeypatch):
    monkeypatch.delenv("MIRASTACK_OTEL_ENABLED", raising=False)
    shutdown = init_meter_provider("test-plugin")
    shutdown()


def test_start_action_success_path():
    with start_action("query_metrics", "rate", "READ") as span:
        # Should always yield a wrapper (real or no-op)
        assert span is not None
        span.set_attribute("custom.attr", "value")


def test_start_action_propagates_exception():
    class CustomError(Exception):
        pass

    with pytest.raises(CustomError):
        with start_action("query_metrics", "rate", "READ"):
            raise CustomError("boom")


def test_err_class_returns_qualified_name():
    class MyErr(Exception):
        pass

    err = MyErr("x")
    cls = _err_class(err)
    # Builtins are unqualified, custom exceptions carry their module path
    assert "MyErr" in cls


def test_err_class_handles_builtin():
    err = ValueError("x")
    assert _err_class(err) == "ValueError"
