"""Tests for serve.py — address resolution and registration heartbeat."""

from __future__ import annotations

import socket
import threading
from typing import Any
from unittest import mock

from mirastack_sdk.plugin import (
    ExecuteRequest,
    ExecuteResponse,
    Plugin,
    PluginInfo,
    PluginSchema,
)
from mirastack_sdk.serve import (
    _absorb_license_snapshot,
    _maintain_registration,
    _resolve_advertise_addr,
)


class _StubPlugin(Plugin):
    """Minimal Plugin implementation used to host the absorbed license snapshot.

    Real plugins inherit from :class:`mirastack_sdk.Plugin`; the stub here
    keeps the test focused on the registration loop's licence-handling
    behaviour rather than on plugin business logic.
    """

    def info(self) -> PluginInfo:  # pragma: no cover - never called in these tests
        return PluginInfo(name="stub", version="0.0.0")

    def schema(self) -> PluginSchema:  # pragma: no cover
        return PluginSchema()

    async def execute(self, req: ExecuteRequest) -> ExecuteResponse:  # pragma: no cover
        return ExecuteResponse()


def _new_stub_plugin() -> _StubPlugin:
    return _StubPlugin()


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
        _maintain_registration(
            engine_ctx, "svc:50051", 1, "1.0.0", "inst-1", stop_event, _new_stub_plugin()
        )
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
        _maintain_registration(
            engine_ctx, "svc:50051", 1, "1.0.0", "inst-1", stop_event, _new_stub_plugin()
        )
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
        _maintain_registration(
            engine_ctx, "svc:50051", 1, "1.0.0", "inst-1", stop_event, _new_stub_plugin()
        )
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
        _maintain_registration(
            engine_ctx, "svc:50051", 1, "1.0.0", "inst-1", stop_event, _new_stub_plugin()
        )
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
        _maintain_registration(
            engine_ctx, "svc:50051", 1, "1.0.0", "inst-1", stop_event, _new_stub_plugin()
        )
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
        _maintain_registration(
            engine_ctx, "svc:50051", 1, "1.0.0", "inst-1", stop_event, _new_stub_plugin()
        )
        engine_ctx.register_self.assert_called_once()


class TestAbsorbLicenseSnapshot:
    """Engine licence snapshot is parsed and stashed on the plugin instance.

    Mirrors :func:`mirastack-agents-sdk-go/serve.go`'s consumption of the
    ``LicenseContext`` field on ``RegisterPluginResponse`` and
    ``HeartbeatResponse``: SDK-v1.8.0 plugins read the typed snapshot at
    ``plugin._engine_license_context`` after a successful registration.
    """

    def test_typed_snapshot_is_attached_on_first_observation(self) -> None:
        plugin = _new_stub_plugin()
        raw = {
            "active": True,
            "effective_tier": "pro",
            "issued_tier": "pro",
            "grace_mode": False,
            "expires_at": 1893456000000,
            "org_id": "org-1",
            "site_id": "site-1",
            "region": "us-east-1",
            "region_kind": "public",
            "quotas": {
                "max_tenants": 10,
                "max_integration_types": 5,
                "max_agentic_sessions_per_day": 50,
            },
        }
        _absorb_license_snapshot(plugin, raw)

        ctx: Any = plugin._engine_license_context  # type: ignore[attr-defined]
        assert ctx is not None
        assert ctx.active is True
        assert ctx.effective_tier == "pro"
        assert ctx.quotas.max_integration_types == 5
        assert ctx.quotas.max_tenants == 10

    def test_none_snapshot_keeps_previous(self) -> None:
        plugin = _new_stub_plugin()
        raw = {
            "active": True,
            "effective_tier": "pro",
            "quotas": {"max_tenants": 10, "max_integration_types": 5},
        }
        _absorb_license_snapshot(plugin, raw)
        original = plugin._engine_license_context  # type: ignore[attr-defined]
        _absorb_license_snapshot(plugin, None)
        assert plugin._engine_license_context is original  # type: ignore[attr-defined]

    def test_unexpected_shape_keeps_previous(self) -> None:
        plugin = _new_stub_plugin()
        raw = {
            "active": True,
            "effective_tier": "pro",
            "quotas": {"max_tenants": 10, "max_integration_types": 5},
        }
        _absorb_license_snapshot(plugin, raw)
        original = plugin._engine_license_context  # type: ignore[attr-defined]
        _absorb_license_snapshot(plugin, "not-a-dict")
        assert plugin._engine_license_context is original  # type: ignore[attr-defined]

    def test_active_flip_to_false_logs_warning(self, caplog: Any) -> None:
        import logging

        plugin = _new_stub_plugin()
        active_raw = {
            "active": True,
            "effective_tier": "pro",
            "quotas": {"max_tenants": 10, "max_integration_types": 5},
        }
        _absorb_license_snapshot(plugin, active_raw)

        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="mirastack_sdk"):
            _absorb_license_snapshot(
                plugin,
                {**active_raw, "active": False},
            )
        assert any(
            "active True->False" in rec.message and rec.levelno == logging.WARNING
            for rec in caplog.records
        )

    def test_grace_mode_transition_logs_warning(self, caplog: Any) -> None:
        import logging

        plugin = _new_stub_plugin()
        ok = {
            "active": True,
            "effective_tier": "pro",
            "grace_mode": False,
            "quotas": {"max_tenants": 10, "max_integration_types": 5},
        }
        _absorb_license_snapshot(plugin, ok)

        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="mirastack_sdk"):
            _absorb_license_snapshot(
                plugin,
                {**ok, "grace_mode": True, "effective_tier": "neo"},
            )
        assert any(
            "grace_mode False->True" in rec.message and rec.levelno == logging.WARNING
            for rec in caplog.records
        )

    def test_no_change_emits_no_log(self, caplog: Any) -> None:
        import logging

        plugin = _new_stub_plugin()
        raw = {
            "active": True,
            "effective_tier": "pro",
            "quotas": {"max_tenants": 10, "max_integration_types": 5},
        }
        _absorb_license_snapshot(plugin, raw)

        caplog.clear()
        with caplog.at_level(logging.INFO, logger="mirastack_sdk"):
            _absorb_license_snapshot(plugin, raw)
        assert not [rec for rec in caplog.records if "license" in rec.message.lower()]
