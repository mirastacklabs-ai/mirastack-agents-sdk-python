"""Tests for serve.py — address resolution and registration retry."""

from __future__ import annotations

import socket
from unittest import mock

from mirastack_sdk.serve import _resolve_advertise_addr, _register_with_retry


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


class TestRegisterWithRetry:
    """Background registration should retry on failure with backoff."""

    def test_succeeds_on_first_attempt(self) -> None:
        engine_ctx = mock.MagicMock()
        engine_ctx.register_self.return_value = {
            "success": True,
            "plugin_id": "plg_test",
        }
        _register_with_retry(engine_ctx, "svc:50051", 1, "1.0.0", "inst-1")
        engine_ctx.register_self.assert_called_once()

    def test_retries_on_transient_failure(self) -> None:
        engine_ctx = mock.MagicMock()
        engine_ctx.register_self.side_effect = [
            Exception("connection refused"),
            Exception("connection refused"),
            {"success": True, "plugin_id": "plg_test"},
        ]
        with mock.patch("mirastack_sdk.serve._register_with_retry.__module__"):
            pass
        # Run with patched sleep to avoid real delays
        with mock.patch("time.sleep"):
            _register_with_retry(engine_ctx, "svc:50051", 1, "1.0.0", "inst-1")
        assert engine_ctx.register_self.call_count == 3

    def test_exhausts_retries_and_logs_error(self) -> None:
        engine_ctx = mock.MagicMock()
        engine_ctx.register_self.side_effect = Exception("engine unavailable")
        with mock.patch("time.sleep"):
            _register_with_retry(engine_ctx, "svc:50051", 1, "1.0.0", "inst-1")
        assert engine_ctx.register_self.call_count == 10
