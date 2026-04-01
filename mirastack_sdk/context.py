"""Engine context — proxy for engine services via gRPC callbacks.

Plugins use EngineContext to access cache, publish results, request approvals,
and log events. Plugins NEVER access Kine or Valkey directly.
"""

from __future__ import annotations

from datetime import timedelta


class EngineContext:
    """Proxy for engine gRPC services available to plugins."""

    def __init__(self, engine_addr: str, plugin_name: str) -> None:
        if not engine_addr:
            raise ValueError("engine_addr is required")
        self._engine_addr = engine_addr
        self._plugin_name = plugin_name
        # TODO(phase-2): Establish gRPC channel to engine

    async def cache_get(self, key: str) -> str | None:
        """Retrieve a value from the engine's Valkey cache."""
        # TODO(phase-2): Implement via EngineService.CacheGet gRPC call
        raise NotImplementedError

    async def cache_set(self, key: str, value: str, ttl: timedelta | None = None) -> None:
        """Store a value in the engine's Valkey cache."""
        # TODO(phase-2): Implement via EngineService.CacheSet gRPC call
        raise NotImplementedError

    async def publish_result(self, execution_id: str, output: dict[str, str]) -> None:
        """Send execution output back to the engine."""
        # TODO(phase-2): Implement via EngineService.PublishResult gRPC call
        raise NotImplementedError

    async def request_approval(self, execution_id: str, reason: str) -> bool:
        """Pause execution and wait for human approval."""
        # TODO(phase-4): Implement via EngineService.RequestApproval gRPC call
        raise NotImplementedError

    async def log_event(self, level: str, message: str, fields: dict[str, str] | None = None) -> None:
        """Send a log entry to the engine's event stream."""
        # TODO(phase-2): Implement via EngineService.LogEvent gRPC call
        raise NotImplementedError

    async def close(self) -> None:
        """Clean up the gRPC channel."""
        # TODO(phase-2): Close gRPC channel
        pass
