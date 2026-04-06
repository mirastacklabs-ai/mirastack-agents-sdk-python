"""Engine context — proxy for engine services via gRPC callbacks.

Plugins use EngineContext to access cache, publish results, request approvals,
and log events. Plugins NEVER access Kine or Valkey directly.
"""

from __future__ import annotations

import json
import os
import time
from datetime import timedelta

import grpc

# Default config cache TTL in seconds.
_DEFAULT_CONFIG_CACHE_TTL = 15


class EngineContext:
    """Proxy for engine gRPC services available to plugins."""

    def __init__(self, engine_addr: str, plugin_name: str) -> None:
        if not engine_addr:
            raise ValueError("engine_addr is required")
        self._engine_addr = engine_addr
        self._plugin_name = plugin_name
        self._channel = grpc.insecure_channel(engine_addr)

        # Config cache
        self._config_cache: dict[str, str] | None = None
        self._config_cached_at: float = 0.0
        self._config_ttl: float = float(
            os.environ.get("MIRASTACK_SDK_CONFIG_CACHE_TTL", str(_DEFAULT_CONFIG_CACHE_TTL))
        )

        # Attempt to import generated stubs; fall back to generic invocation.
        try:
            from mirastack_sdk.gen import plugin_pb2_grpc  # type: ignore[import-untyped]
            self._stub = plugin_pb2_grpc.EngineServiceStub(self._channel)
        except ImportError:
            self._stub = None

    async def get_config(self, keys: list[str] | None = None) -> dict[str, str]:
        """Retrieve configuration values from the engine's settings store.

        Results are cached locally with a configurable TTL (default 15s, set via
        MIRASTACK_SDK_CONFIG_CACHE_TTL env var in seconds). On cache hit the gRPC
        round-trip is skipped entirely.

        Args:
            keys: Optional list of specific config keys. If None, returns all
                  plugin-scoped configuration.

        Returns:
            Dictionary of configuration key-value pairs.
        """
        # Check local cache
        if (
            self._config_cache is not None
            and (time.monotonic() - self._config_cached_at) < self._config_ttl
        ):
            config = self._config_cache
            if keys:
                return {k: v for k, v in config.items() if k in keys}
            return dict(config)

        # Cache miss — call engine
        if self._stub is not None:
            # Use generated stub
            from mirastack_sdk.gen import plugin_pb2  # type: ignore[import-untyped]
            req = plugin_pb2.GetConfigRequest(plugin_name=self._plugin_name)
            resp = self._stub.GetConfig(req)
            config = json.loads(resp.config_json) if resp.config_json else {}
        else:
            # Generic invocation without generated code
            config = self._call_unary(
                "/mirastack.plugin.v1.EngineService/GetConfig",
                {"plugin_name": self._plugin_name},
            )
            config = json.loads(config.get("config_json", b"{}"))

        # Update cache
        self._config_cache = config
        self._config_cached_at = time.monotonic()

        if keys:
            return {k: v for k, v in config.items() if k in keys}
        return config

    async def cache_get(self, key: str) -> str | None:
        """Retrieve a value from the engine's Valkey cache."""
        if self._stub is not None:
            from mirastack_sdk.gen import plugin_pb2  # type: ignore[import-untyped]
            resp = self._stub.CacheGet(plugin_pb2.CacheGetRequest(key=key))
            return resp.value.decode() if resp.found else None

        resp = self._call_unary(
            "/mirastack.plugin.v1.EngineService/CacheGet",
            {"key": key},
        )
        if resp.get("found"):
            return resp.get("value", b"").decode()
        return None

    async def cache_set(self, key: str, value: str, ttl: timedelta | None = None) -> None:
        """Store a value in the engine's Valkey cache."""
        ttl_seconds = int(ttl.total_seconds()) if ttl else 0
        if self._stub is not None:
            from mirastack_sdk.gen import plugin_pb2  # type: ignore[import-untyped]
            self._stub.CacheSet(plugin_pb2.CacheSetRequest(
                key=key, value=value.encode(), ttl_seconds=ttl_seconds,
            ))
            return

        self._call_unary(
            "/mirastack.plugin.v1.EngineService/CacheSet",
            {"key": key, "value": value.encode(), "ttl_seconds": ttl_seconds},
        )

    async def publish_result(self, execution_id: str, output: dict[str, str]) -> None:
        """Send execution output back to the engine."""
        result_json = json.dumps(output).encode()
        if self._stub is not None:
            from mirastack_sdk.gen import plugin_pb2  # type: ignore[import-untyped]
            self._stub.PublishResult(plugin_pb2.PublishResultRequest(
                execution_id=execution_id, result_json=result_json, success=True,
            ))
            return

        self._call_unary(
            "/mirastack.plugin.v1.EngineService/PublishResult",
            {"execution_id": execution_id, "result_json": result_json, "success": True},
        )

    async def request_approval(self, execution_id: str, reason: str) -> bool:
        """Pause execution and wait for human approval."""
        if self._stub is not None:
            from mirastack_sdk.gen import plugin_pb2  # type: ignore[import-untyped]
            resp = self._stub.RequestApproval(plugin_pb2.RequestApprovalRequest(
                execution_id=execution_id, description=reason,
            ))
            return resp.approved

        resp = self._call_unary(
            "/mirastack.plugin.v1.EngineService/RequestApproval",
            {"execution_id": execution_id, "description": reason},
        )
        return resp.get("approved", False)

    async def log_event(self, level: str, message: str, fields: dict[str, str] | None = None) -> None:
        """Send a log entry to the engine's event stream."""
        data_json = json.dumps(fields or {}).encode()
        if self._stub is not None:
            from mirastack_sdk.gen import plugin_pb2  # type: ignore[import-untyped]
            self._stub.LogEvent(plugin_pb2.LogEventRequest(
                plugin_name=self._plugin_name,
                event_type=message,
                data_json=data_json,
                severity=level,
            ))
            return

        self._call_unary(
            "/mirastack.plugin.v1.EngineService/LogEvent",
            {
                "plugin_name": self._plugin_name,
                "event_type": message,
                "data_json": data_json,
                "severity": level,
            },
        )

    async def call_plugin(self, target_plugin: str, params: dict[str, str]) -> dict[str, str]:
        """Invoke another plugin through the engine and return its output."""
        params_json = json.dumps(params).encode()
        if self._stub is not None:
            from mirastack_sdk.gen import plugin_pb2  # type: ignore[import-untyped]
            resp = self._stub.CallPlugin(plugin_pb2.CallPluginRequest(
                caller_plugin=self._plugin_name,
                target_plugin=target_plugin,
                params_json=params_json,
            ))
            if not resp.success:
                raise RuntimeError(f"Plugin {target_plugin!r} returned error: {resp.error}")
            return json.loads(resp.result_json)

        resp = self._call_unary(
            "/mirastack.plugin.v1.EngineService/CallPlugin",
            {
                "caller_plugin": self._plugin_name,
                "target_plugin": target_plugin,
                "params_json": params_json,
            },
        )
        if not resp.get("success"):
            raise RuntimeError(f"Plugin {target_plugin!r} returned error: {resp.get('error', '')}")
        return json.loads(resp.get("result_json", b"{}"))

    async def close(self) -> None:
        """Clean up the gRPC channel."""
        if self._channel is not None:
            self._channel.close()
            self._channel = None

    def _call_unary(self, method: str, request: dict) -> dict:
        """Invoke a unary gRPC method without generated stubs (dict↔dict via JSON codec)."""
        return self._channel.unary_unary(method)(request)
