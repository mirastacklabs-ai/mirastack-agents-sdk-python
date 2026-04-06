"""Hand-written message types mirroring plugin.proto.

These classes support JSON serialization for the MIRASTACK JSON gRPC codec.
Each message class provides:
  - Keyword-argument construction: ``GetConfigRequest(plugin_name="my-plugin")``
  - ``SerializeToString()`` → bytes (JSON encoded)
  - ``FromString(data)`` class method → instance from JSON bytes

When ``buf generate`` produces real protobuf stubs, this file is replaced.
"""

from __future__ import annotations

import json
from typing import Any


# ---------------------------------------------------------------------------
# Base helper
# ---------------------------------------------------------------------------

class _Msg:
    """Mixin providing JSON (de)serialisation that matches the JSON gRPC codec."""

    def SerializeToString(self) -> bytes:
        return json.dumps(self._to_dict()).encode()

    @classmethod
    def FromString(cls, data: bytes) -> "_Msg":
        d = json.loads(data) if data else {}
        return cls(**{k: v for k, v in d.items() if k in cls.__init__.__code__.co_varnames})

    def _to_dict(self) -> dict[str, Any]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# PluginService messages
# ---------------------------------------------------------------------------

class InfoRequest(_Msg):
    def _to_dict(self) -> dict[str, Any]:
        return {}


class InfoResponse(_Msg):
    def __init__(
        self,
        name: str = "",
        version: str = "",
        description: str = "",
        permission: int = 0,
        devops_stages: list[int] | None = None,
        default_intents: list[dict[str, Any]] | None = None,
        metadata: dict[str, str] | None = None,
    ) -> None:
        self.name = name
        self.version = version
        self.description = description
        self.permission = permission
        self.devops_stages = devops_stages or []
        self.default_intents = default_intents or []
        self.metadata = metadata or {}

    def _to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "permission": self.permission,
            "devops_stages": self.devops_stages,
            "default_intents": self.default_intents,
            "metadata": self.metadata,
        }


class GetSchemaRequest(_Msg):
    def _to_dict(self) -> dict[str, Any]:
        return {}


class GetSchemaResponse(_Msg):
    def __init__(
        self,
        params_json_schema: bytes = b"",
        result_json_schema: bytes = b"",
    ) -> None:
        self.params_json_schema = params_json_schema
        self.result_json_schema = result_json_schema

    def _to_dict(self) -> dict[str, Any]:
        return {
            "params_json_schema": self.params_json_schema.decode() if isinstance(self.params_json_schema, bytes) else self.params_json_schema,
            "result_json_schema": self.result_json_schema.decode() if isinstance(self.result_json_schema, bytes) else self.result_json_schema,
        }


class ExecuteRequest(_Msg):
    def __init__(
        self,
        execution_id: str = "",
        step_id: str = "",
        workflow_id: str = "",
        params_json: bytes = b"{}",
        mode: int = 1,
        context: dict[str, str] | None = None,
        time_range: dict[str, Any] | None = None,
    ) -> None:
        self.execution_id = execution_id
        self.step_id = step_id
        self.workflow_id = workflow_id
        self.params_json = params_json
        self.mode = mode
        self.context = context or {}
        self.time_range = time_range

    def _to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "execution_id": self.execution_id,
            "step_id": self.step_id,
            "workflow_id": self.workflow_id,
            "params_json": self.params_json.decode() if isinstance(self.params_json, bytes) else self.params_json,
            "mode": self.mode,
            "context": self.context,
        }
        if self.time_range:
            d["time_range"] = self.time_range
        return d


class ExecuteResponse(_Msg):
    def __init__(
        self,
        success: bool = True,
        result_json: bytes = b"{}",
        error: str = "",
        duration_ms: int = 0,
    ) -> None:
        self.success = success
        self.result_json = result_json
        self.error = error
        self.duration_ms = duration_ms

    def _to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "result_json": self.result_json.decode() if isinstance(self.result_json, bytes) else self.result_json,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


class HealthCheckRequest(_Msg):
    def _to_dict(self) -> dict[str, Any]:
        return {}


class HealthCheckResponse(_Msg):
    def __init__(
        self,
        healthy: bool = True,
        message: str = "",
        details: dict[str, str] | None = None,
    ) -> None:
        self.healthy = healthy
        self.message = message
        self.details = details or {}

    def _to_dict(self) -> dict[str, Any]:
        return {"healthy": self.healthy, "message": self.message, "details": self.details}


class ConfigUpdatedRequest(_Msg):
    def __init__(
        self,
        config: dict[str, str] | None = None,
        config_json: bytes = b"{}",
        version: int = 0,
    ) -> None:
        self.config = config or {}
        self.config_json = config_json
        self.version = version

    def _to_dict(self) -> dict[str, Any]:
        return {
            "config": self.config,
            "config_json": self.config_json.decode() if isinstance(self.config_json, bytes) else self.config_json,
            "version": self.version,
        }


class ConfigUpdatedResponse(_Msg):
    def __init__(self, acknowledged: bool = True, error: str = "") -> None:
        self.acknowledged = acknowledged
        self.error = error

    def _to_dict(self) -> dict[str, Any]:
        return {"acknowledged": self.acknowledged, "error": self.error}


# ---------------------------------------------------------------------------
# EngineService messages
# ---------------------------------------------------------------------------

class GetConfigRequest(_Msg):
    def __init__(self, plugin_name: str = "") -> None:
        self.plugin_name = plugin_name

    def _to_dict(self) -> dict[str, Any]:
        return {"plugin_name": self.plugin_name}


class GetConfigResponse(_Msg):
    def __init__(
        self,
        config: dict[str, str] | None = None,
        config_json: bytes = b"{}",
        version: int = 0,
    ) -> None:
        self.config = config or {}
        self.config_json = config_json
        self.version = version

    def _to_dict(self) -> dict[str, Any]:
        return {
            "config": self.config,
            "config_json": self.config_json.decode() if isinstance(self.config_json, bytes) else self.config_json,
            "version": self.version,
        }


class CacheGetRequest(_Msg):
    def __init__(self, key: str = "") -> None:
        self.key = key

    def _to_dict(self) -> dict[str, Any]:
        return {"key": self.key}


class CacheGetResponse(_Msg):
    def __init__(self, value: bytes = b"", found: bool = False) -> None:
        self.value = value
        self.found = found

    def _to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value.decode() if isinstance(self.value, bytes) else self.value,
            "found": self.found,
        }


class CacheSetRequest(_Msg):
    def __init__(self, key: str = "", value: bytes = b"", ttl_seconds: int = 0) -> None:
        self.key = key
        self.value = value
        self.ttl_seconds = ttl_seconds

    def _to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value.decode() if isinstance(self.value, bytes) else self.value,
            "ttl_seconds": self.ttl_seconds,
        }


class CacheSetResponse(_Msg):
    def __init__(self, success: bool = True) -> None:
        self.success = success

    def _to_dict(self) -> dict[str, Any]:
        return {"success": self.success}


class PublishResultRequest(_Msg):
    def __init__(
        self,
        execution_id: str = "",
        step_id: str = "",
        result_json: bytes = b"{}",
        success: bool = True,
        error: str = "",
    ) -> None:
        self.execution_id = execution_id
        self.step_id = step_id
        self.result_json = result_json
        self.success = success
        self.error = error

    def _to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "step_id": self.step_id,
            "result_json": self.result_json.decode() if isinstance(self.result_json, bytes) else self.result_json,
            "success": self.success,
            "error": self.error,
        }


class PublishResultResponse(_Msg):
    def __init__(self, acknowledged: bool = True) -> None:
        self.acknowledged = acknowledged

    def _to_dict(self) -> dict[str, Any]:
        return {"acknowledged": self.acknowledged}


class RequestApprovalRequest(_Msg):
    def __init__(
        self,
        execution_id: str = "",
        step_id: str = "",
        description: str = "",
        required_permission: int = 0,
        context_json: bytes = b"{}",
        timeout_seconds: int = 0,
    ) -> None:
        self.execution_id = execution_id
        self.step_id = step_id
        self.description = description
        self.required_permission = required_permission
        self.context_json = context_json
        self.timeout_seconds = timeout_seconds

    def _to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "step_id": self.step_id,
            "description": self.description,
            "required_permission": self.required_permission,
            "context_json": self.context_json.decode() if isinstance(self.context_json, bytes) else self.context_json,
            "timeout_seconds": self.timeout_seconds,
        }


class RequestApprovalResponse(_Msg):
    def __init__(
        self,
        approved: bool = False,
        timed_out: bool = False,
        reviewer: str = "",
        comment: str = "",
    ) -> None:
        self.approved = approved
        self.timed_out = timed_out
        self.reviewer = reviewer
        self.comment = comment

    def _to_dict(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "timed_out": self.timed_out,
            "reviewer": self.reviewer,
            "comment": self.comment,
        }


class LogEventRequest(_Msg):
    def __init__(
        self,
        plugin_name: str = "",
        event_type: str = "",
        data_json: bytes = b"{}",
        severity: str = "",
    ) -> None:
        self.plugin_name = plugin_name
        self.event_type = event_type
        self.data_json = data_json
        self.severity = severity

    def _to_dict(self) -> dict[str, Any]:
        return {
            "plugin_name": self.plugin_name,
            "event_type": self.event_type,
            "data_json": self.data_json.decode() if isinstance(self.data_json, bytes) else self.data_json,
            "severity": self.severity,
        }


class LogEventResponse(_Msg):
    def __init__(self, acknowledged: bool = True) -> None:
        self.acknowledged = acknowledged

    def _to_dict(self) -> dict[str, Any]:
        return {"acknowledged": self.acknowledged}


class CallPluginRequest(_Msg):
    def __init__(
        self,
        caller_plugin: str = "",
        target_plugin: str = "",
        params_json: bytes = b"{}",
        timeout_seconds: int = 0,
    ) -> None:
        self.caller_plugin = caller_plugin
        self.target_plugin = target_plugin
        self.params_json = params_json
        self.timeout_seconds = timeout_seconds

    def _to_dict(self) -> dict[str, Any]:
        return {
            "caller_plugin": self.caller_plugin,
            "target_plugin": self.target_plugin,
            "params_json": self.params_json.decode() if isinstance(self.params_json, bytes) else self.params_json,
            "timeout_seconds": self.timeout_seconds,
        }


class CallPluginResponse(_Msg):
    def __init__(
        self,
        success: bool = True,
        result_json: bytes = b"{}",
        error: str = "",
        duration_ms: int = 0,
    ) -> None:
        self.success = success
        self.result_json = result_json
        self.error = error
        self.duration_ms = duration_ms

    def _to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "result_json": self.result_json.decode() if isinstance(self.result_json, bytes) else self.result_json,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }
