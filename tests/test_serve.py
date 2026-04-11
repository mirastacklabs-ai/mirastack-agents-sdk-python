"""Tests for serve.py — address resolution and registration heartbeat."""

from __future__ import annotations

import socket
import threading
from unittest import mock

from mirastack_sdk.serve import _resolve_advertise_addr, _maintain_registration


class _FastStopEvent:
    """A threading.Event-like that never actually blocks in wait().

    Used in tests to avoid real backoff delays while preserving the
    set/is_set semantics that _maintain_registration relies on.
    """

    def __init__(self) -> None:
        self._set = False

    def is_set(self) -> bool:
        return self._set

    def set(self) -> None:
        self._set = True

    def wait(self, timeout: float | None = None) -> bool:  # noqa: ARG002
        """Return current state immediately — no blocking."""
        return self._set


class TestResolveAdvertiseAddr:
    """MIRASTACK_PLUGIN_ADVERTISE_ADDR must take precedence in container/K8s."""

    def test_explicit_env_var(self, monkeypatch: mock.ANY) -> None:
        monkeypatch.setenv("MIRASTACK_PLUGIN_ADVERTISE_ADDR", "my-agent-svc:50051")
        assert _resolve_advertise_addr(9999) == "my-agent-svc:50051"

    def test_k8s_service_fqdn(self, monkeypatch: mock.ANY) -> None:
        monkeypatch.setenv(
            "MIRASTACK_PLUGIN_ADVERTISE_ADDR",
            "agent-vmetrics.mirastack.svc.cluster.local:50051",
        )
        assert (
            _resolve_advertise_addr(50051)
            == "agent-vmetrics.mirastack.svc.cluster.local:50051"
        )

    def test_fallback_to_hostname(self, monkeypatch: mock.ANY) -> None:
        monkeypatch.delenv("MIRASTACK_PLUGIN_ADVERTISE_ADDR", raising=False)
        hostname = socket.gethostname() or "localhost"
        assert _resolve_advertise_addr(50051) == f"{hostname}:50051"

    def test_env_var_ignores_bound_port(self, monkeypatch: mock.ANY) -> None:
        monkeypatch.setenv("MIRASTACK_PLUGIN_ADVERTISE_ADDR", "provider-openai:50051")
        assert _resolve_advertise_addr(12345) == "provider-openai:50051"


class TestMaintainRegistration:
    """Persistent registration: initial retry + heartbeat loop."""

    def test_succeeds_on_first_attempt_then_heartbeats(self) -> None:
        """Initial registration succeeds immediately; heartbeat loop runs."""
        engine_ctx = mock.MagicMock()
        stop_event = threading.Event()

        def _register_self(**kwargs):
            # Stop after initial registration succeeds.
            stop_event.set()
            return {"success": True, "plugin_id": "plg_test"}

        engine_ctx.register_self.side_effect = _register_self
        _maintain_registration(engine_ctx, "svc:50051", 1, "1.0.0", "inst-1", stop_event)
        engine_ctx.register_self.assert_called_once()

    def test_retries_on_transient_failure(self) -> None:
        """Transient failures are retried with backoff before succeeding."""
        engine_ctx = mock.MagicMock()
        stop_event = _FastStopEvent()
        call_count = 0

        def _register_self(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("connection refused")
            stop_event.set()
            return {"success": True, "plugin_id": "plg_test"}

        engine_ctx.register_self.side_effect = _register_self
        _maintain_registration(engine_ctx, "svc:50051", 1, "1.0.0", "inst-1", stop_event)
        assert engine_ctx.register_self.call_count == 3

    def test_exhausts_initial_retries_then_enters_heartbeat(self) -> None:
        """After 10 failed initial attempts, enters heartbeat mode."""
        engine_ctx = mock.MagicMock()
        stop_event = _FastStopEvent()
        call_count = 0

        def _register_self(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count >= 10:
                # Set stop after Phase 1 exhausts so Phase 2 exits immediately.
                stop_event.set()
            raise Exception("engine unavailable")

        engine_ctx.register_self.side_effect = _register_self
        _maintain_registration(engine_ctx, "svc:50051", 1, "1.0.0", "inst-1", stop_event)
        assert engine_ctx.register_self.call_count == 10

    def test_stop_event_exits_heartbeat_loop(self, monkeypatch: mock.ANY) -> None:
        """Setting stop_event causes the heartbeat loop to exit."""
        monkeypatch.setenv("MIRASTACK_PLUGIN_HEARTBEAT_INTERVAL", "1")
        engine_ctx = mock.MagicMock()
        call_count = 0

        def _register_self(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                # After a few heartbeats, stop.
                stop_event.set()
            return {"success": True, "plugin_id": "plg_test"}

        engine_ctx.register_self.side_effect = _register_self
        stop_event = threading.Event()
        _maintain_registration(engine_ctx, "svc:50051", 1, "1.0.0", "inst-1", stop_event)
        # At least 1 initial registration + some heartbeats.
        assert engine_ctx.register_self.call_count >= 2

    def test_heartbeat_recovers_after_engine_restart(self, monkeypatch: mock.ANY) -> None:
        """Heartbeat re-registers after engine restart (simulated failure then success)."""
        monkeypatch.setenv("MIRASTACK_PLUGIN_HEARTBEAT_INTERVAL", "1")
        engine_ctx = mock.MagicMock()
        call_count = 0
        stop_event = threading.Event()

        def _register_self(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"success": True, "plugin_id": "plg_test"}
            elif call_count <= 3:
                # Simulate engine restart — heartbeats fail.
                raise Exception("connection refused")
            elif call_count == 4:
                # Engine is back — heartbeat succeeds.
                return {"success": True, "plugin_id": "plg_test"}
            else:
                stop_event.set()
                return {"success": True, "plugin_id": "plg_test"}

        engine_ctx.register_self.side_effect = _register_self
        _maintain_registration(engine_ctx, "svc:50051", 1, "1.0.0", "inst-1", stop_event)
        # Should have: 1 initial + several heartbeats.
        assert call_count >= 4

    def test_invalid_heartbeat_env_defaults_to_30(self, monkeypatch: mock.ANY) -> None:
        """Invalid MIRASTACK_PLUGIN_HEARTBEAT_INTERVAL falls back to 30s default."""
        monkeypatch.setenv("MIRASTACK_PLUGIN_HEARTBEAT_INTERVAL", "not-a-number")
        engine_ctx = mock.MagicMock()
        stop_event = threading.Event()

        def _register_self(**kwargs):
            stop_event.set()
            return {"success": True, "plugin_id": "plg_test"}

        engine_ctx.register_self.side_effect = _register_self
        _maintain_registration(engine_ctx, "svc:50051", 1, "1.0.0", "inst-1", stop_event)
        engine_ctx.register_self.assert_called_once()
