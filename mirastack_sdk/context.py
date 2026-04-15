"""Engine context — proxy for engine services via gRPC callbacks.

Plugins use EngineContext to access cache, publish results, request approvals,
and log events. Plugins NEVER access Kine or Valkey directly.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import timedelta
from typing import Any

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
        self._channel = grpc.insecure_channel(
            engine_addr,
            options=[
                ("grpc.keepalive_time_ms", 30000),
                ("grpc.keepalive_timeout_ms", 10000),
                ("grpc.keepalive_permit_without_calls", 1),
            ],
        )

        # Config cache
        self._config_cache: dict[str, str] | None = None
        self._config_cached_at: float = 0.0
        self._config_ttl: float = float(
            os.environ.get("MIRASTACK_SDK_CONFIG_CACHE_TTL", str(_DEFAULT_CONFIG_CACHE_TTL))
        )

        # Attempt to import generated stubs; fall back to generic invocation.
        self._stub: Any = None
        try:
            from mirastack_sdk.gen import plugin_pb2_grpc  # type: ignore[import-untyped]
            self._stub = plugin_pb2_grpc.EngineServiceStub(self._channel)
        except ImportError:
            pass

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

        # Cache miss — call engine (sync gRPC, offloaded to thread pool to
        # avoid blocking the async event loop).
        config = await asyncio.to_thread(self._fetch_config)

        # Update cache
        self._config_cache = config
        self._config_cached_at = time.monotonic()

        if keys:
            return {k: v for k, v in config.items() if k in keys}
        return config

    async def cache_get(self, key: str) -> str | None:
        """Retrieve a value from the engine's Valkey cache."""
        return await asyncio.to_thread(self._cache_get_sync, key)

    async def cache_set(self, key: str, value: str, ttl: timedelta | None = None) -> None:
        """Store a value in the engine's Valkey cache."""
        await asyncio.to_thread(self._cache_set_sync, key, value, ttl)

    async def publish_result(self, execution_id: str, output: dict[str, str]) -> None:
        """Send execution output back to the engine."""
        await asyncio.to_thread(self._publish_result_sync, execution_id, output)

    async def request_approval(self, execution_id: str, reason: str) -> bool:
        """Pause execution and wait for human approval."""
        return await asyncio.to_thread(self._request_approval_sync, execution_id, reason)

    async def log_event(self, level: str, message: str, fields: dict[str, str] | None = None) -> None:
        """Send a log entry to the engine's event stream."""
        await asyncio.to_thread(self._log_event_sync, level, message, fields)

    async def call_plugin(self, target_plugin: str, params: dict[str, str]) -> dict[str, str]:
        """Invoke another plugin through the engine and return its output."""
        return await self.call_plugin_with_time_range(target_plugin, params, None)

    async def call_plugin_with_time_range(
        self,
        target_plugin: str,
        params: dict[str, str],
        time_range: dict | None = None,
    ) -> dict[str, str]:
        """Invoke another plugin, propagating the given TimeRange.

        Use this when orchestrating agent-to-agent calls from within an
        execute() handler to prevent time drift. Pass the time_range dict
        from the original ExecuteRequest to maintain absolute time context.

        Args:
            target_plugin: Name of the plugin to invoke.
            params: Key-value parameters for the target plugin.
            time_range: Optional dict with start_epoch_ms, end_epoch_ms,
                        timezone, original_expression. Pass
                        ``dataclasses.asdict(req.time_range)`` from the
                        incoming ExecuteRequest.

        Returns:
            Dictionary of output key-value pairs from the target plugin.
        """
        return await asyncio.to_thread(
            self._call_plugin_with_time_range_sync, target_plugin, params, time_range,
        )

    # ------------------------------------------------------------------
    # Private synchronous helpers — executed via asyncio.to_thread() so
    # that blocking gRPC calls do not stall the async event loop.
    # ------------------------------------------------------------------

    def _fetch_config(self) -> dict[str, str]:
        if self._stub is not None:
            from mirastack_sdk.gen import plugin_pb2  # type: ignore[import-untyped]
            req = plugin_pb2.GetConfigRequest(plugin_name=self._plugin_name)
            resp = self._stub.GetConfig(req)
            return json.loads(resp.config_json) if resp.config_json else {}

        resp = self._call_unary(
            "/mirastack.plugin.v1.EngineService/GetConfig",
            {"plugin_name": self._plugin_name},
        )
        return json.loads(resp.get("config_json", b"{}"))

    def _cache_get_sync(self, key: str) -> str | None:
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

    def _cache_set_sync(self, key: str, value: str, ttl: timedelta | None = None) -> None:
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

    def _publish_result_sync(self, execution_id: str, output: dict[str, str]) -> None:
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

    def _request_approval_sync(self, execution_id: str, reason: str) -> bool:
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

    def _log_event_sync(self, level: str, message: str, fields: dict[str, str] | None = None) -> None:
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

    def _call_plugin_with_time_range_sync(
        self,
        target_plugin: str,
        params: dict[str, str],
        time_range: dict | None = None,
    ) -> dict[str, str]:
        params_json = json.dumps(params).encode()
        if self._stub is not None:
            from mirastack_sdk.gen import plugin_pb2  # type: ignore[import-untyped]
            kwargs: dict = {
                "caller_plugin": self._plugin_name,
                "target_plugin": target_plugin,
                "params_json": params_json,
            }
            if time_range is not None:
                kwargs["time_range"] = plugin_pb2.TimeRange(
                    start_epoch_ms=time_range.get("start_epoch_ms", 0),
                    end_epoch_ms=time_range.get("end_epoch_ms", 0),
                    timezone=time_range.get("timezone", ""),
                    original_expression=time_range.get("original_expression", ""),
                )
            resp = self._stub.CallPlugin(plugin_pb2.CallPluginRequest(**kwargs))
            if not resp.success:
                raise RuntimeError(f"Plugin {target_plugin!r} returned error: {resp.error}")
            return json.loads(resp.result_json)

        request: dict = {
            "caller_plugin": self._plugin_name,
            "target_plugin": target_plugin,
            "params_json": params_json,
        }
        if time_range is not None:
            request["time_range"] = time_range
        resp = self._call_unary(
            "/mirastack.plugin.v1.EngineService/CallPlugin",
            request,
        )
        if not resp.get("success"):
            raise RuntimeError(f"Plugin {target_plugin!r} returned error: {resp.get('error', '')}")
        return json.loads(resp.get("result_json", b"{}"))

    async def close(self) -> None:
        """Clean up the gRPC channel."""
        if self._channel is not None:
            self._channel.close()
            self._channel = None  # type: ignore[assignment]

    def register_self(
        self,
        grpc_addr: str,
        plugin_type: int,
        version: str,
        instance_id: str,
    ) -> dict:
        """Announce this plugin to the engine so it joins the active registry.

        Args:
            grpc_addr: Externally reachable address (e.g. "plugin-host:50051").
            plugin_type: 1=Agent, 2=Provider, 3=Connector.
            version: Semantic version of the plugin.
            instance_id: Unique instance identifier for this process.

        Returns:
            Response dict with 'success', 'plugin_id', and optional 'error'.
        """
        return self._call_unary(
            "/mirastack.plugin.v1.EngineService/RegisterPlugin",
            {
                "name": self._plugin_name,
                "version": version,
                "grpc_addr": grpc_addr,
                "plugin_type": plugin_type,
                "instance_id": instance_id,
            },
        )

    def deregister_self(self, instance_id: str) -> dict:
        """Tell the engine this plugin is shutting down.

        Args:
            instance_id: The same instance identifier passed during registration.

        Returns:
            Response dict with 'acknowledged' boolean.
        """
        return self._call_unary(
            "/mirastack.plugin.v1.EngineService/DeregisterPlugin",
            {
                "name": self._plugin_name,
                "instance_id": instance_id,
            },
        )

    def heartbeat(self, instance_id: str) -> dict:
        """Send a lightweight liveness signal to the engine.

        Unlike register_self, this does NOT trigger a full registration handshake.
        If the engine doesn't recognize this plugin (e.g. after engine restart),
        the response will have 're_register_required' set to True.

        Args:
            instance_id: The instance identifier for this process.

        Returns:
            Response dict with 'acknowledged', 're_register_required',
            and 'heartbeat_interval_seconds'.
        """
        return self._call_unary(
            "/mirastack.plugin.v1.EngineService/Heartbeat",
            {
                "name": self._plugin_name,
                "instance_id": instance_id,
            },
        )

    def _call_unary(self, method: str, request: dict) -> dict:
        """Invoke a unary gRPC method without generated stubs (dict↔dict via JSON codec).

        The engine uses a JSON wire format (not protobuf), so we must supply
        explicit serializer/deserializer functions that encode dicts as JSON
        bytes and decode JSON bytes back to dicts.
        """
        callable_rpc = self._channel.unary_unary(
            method,
            request_serializer=lambda req: json.dumps(req).encode("utf-8"),
            response_deserializer=lambda data: json.loads(data),
        )
        return callable_rpc(request)
