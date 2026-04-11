"""Hand-written gRPC service stubs mirroring plugin.proto.

Provides:
  - ``add_PluginServiceServicer_to_server(servicer, server)``
  - ``EngineServiceStub(channel)``

Uses the generic-handler approach with JSON (de)serialisation to match the
MIRASTACK JSON gRPC codec. When ``buf generate`` produces real protobuf stubs,
this file is replaced.
"""

from __future__ import annotations

import json
from typing import Any

import grpc

from mirastack_sdk.gen import plugin_pb2


# ---------------------------------------------------------------------------
# JSON serialization helpers for gRPC
# ---------------------------------------------------------------------------

def _json_request_deserializer(cls):
    """Return a deserializer that builds a message class from JSON bytes."""
    def _deserialize(data: bytes):
        d = json.loads(data) if data else {}
        if isinstance(d, dict):
            return cls(**{k: v for k, v in d.items()
                          if k in cls.__init__.__code__.co_varnames})
        return cls()
    return _deserialize


def _json_response_serializer(obj: Any) -> bytes:
    """Serialize a response (dict or _Msg) to JSON bytes."""
    if isinstance(obj, dict):
        return json.dumps(obj).encode()
    if hasattr(obj, "_to_dict"):
        return json.dumps(obj._to_dict()).encode()
    return json.dumps(obj).encode()


def _json_request_serializer(obj: Any) -> bytes:
    """Serialize a request (_Msg or dict) to JSON bytes."""
    if hasattr(obj, "SerializeToString"):
        return obj.SerializeToString()
    if isinstance(obj, dict):
        return json.dumps(obj).encode()
    return json.dumps(obj).encode()


def _json_response_deserializer(cls):
    """Return a deserializer that builds a response class from JSON bytes."""
    def _deserialize(data: bytes):
        d = json.loads(data) if data else {}
        if isinstance(d, dict):
            return cls(**{k: v for k, v in d.items()
                          if k in cls.__init__.__code__.co_varnames})
        return cls()
    return _deserialize


# ---------------------------------------------------------------------------
# PluginService — Servicer base class
# ---------------------------------------------------------------------------

class PluginServiceServicer:
    """Base class for PluginService implementations.

    Plugin authors should not use this directly — the ``_PluginServiceAdapter``
    in ``serve.py`` bridges the async Plugin interface to these RPC methods.
    """

    def Info(self, request, context):
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Info not implemented")
        raise NotImplementedError("Info not implemented")

    def GetSchema(self, request, context):
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("GetSchema not implemented")
        raise NotImplementedError("GetSchema not implemented")

    def Execute(self, request, context):
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Execute not implemented")
        raise NotImplementedError("Execute not implemented")

    def HealthCheck(self, request, context):
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("HealthCheck not implemented")
        raise NotImplementedError("HealthCheck not implemented")

    def ConfigUpdated(self, request, context):
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("ConfigUpdated not implemented")
        raise NotImplementedError("ConfigUpdated not implemented")


def add_PluginServiceServicer_to_server(servicer, server):
    """Register a PluginServiceServicer with a gRPC server.

    Uses generic RPC handlers with JSON (de)serialisation, matching the
    MIRASTACK JSON gRPC codec used by the engine and Go SDK.
    """
    service_name = "mirastack.plugin.v1.PluginService"

    method_handlers = {
        f"/{service_name}/Info": grpc.unary_unary_rpc_method_handler(
            servicer.Info,
            request_deserializer=_json_request_deserializer(plugin_pb2.InfoRequest),
            response_serializer=_json_response_serializer,
        ),
        f"/{service_name}/GetSchema": grpc.unary_unary_rpc_method_handler(
            servicer.GetSchema,
            request_deserializer=_json_request_deserializer(plugin_pb2.GetSchemaRequest),
            response_serializer=_json_response_serializer,
        ),
        f"/{service_name}/Execute": grpc.unary_unary_rpc_method_handler(
            servicer.Execute,
            request_deserializer=_json_request_deserializer(plugin_pb2.ExecuteRequest),
            response_serializer=_json_response_serializer,
        ),
        f"/{service_name}/HealthCheck": grpc.unary_unary_rpc_method_handler(
            servicer.HealthCheck,
            request_deserializer=_json_request_deserializer(plugin_pb2.HealthCheckRequest),
            response_serializer=_json_response_serializer,
        ),
        f"/{service_name}/ConfigUpdated": grpc.unary_unary_rpc_method_handler(
            servicer.ConfigUpdated,
            request_deserializer=_json_request_deserializer(plugin_pb2.ConfigUpdatedRequest),
            response_serializer=_json_response_serializer,
        ),
    }

    class _Handler(grpc.GenericRpcHandler):
        def service(self, handler_call_details):
            return method_handlers.get(handler_call_details.method)

    server.add_generic_rpc_handlers([_Handler()])


# ---------------------------------------------------------------------------
# EngineService — Client stub (plugins use this to call back to the engine)
# ---------------------------------------------------------------------------

class EngineServiceStub:
    """Typed client for engine callback RPCs.

    Uses JSON serialisation matching the MIRASTACK JSON gRPC codec.
    """

    def __init__(self, channel: grpc.Channel) -> None:
        self.GetConfig = channel.unary_unary(
            "/mirastack.plugin.v1.EngineService/GetConfig",
            request_serializer=_json_request_serializer,
            response_deserializer=_json_response_deserializer(plugin_pb2.GetConfigResponse),
        )
        self.CacheGet = channel.unary_unary(
            "/mirastack.plugin.v1.EngineService/CacheGet",
            request_serializer=_json_request_serializer,
            response_deserializer=_json_response_deserializer(plugin_pb2.CacheGetResponse),
        )
        self.CacheSet = channel.unary_unary(
            "/mirastack.plugin.v1.EngineService/CacheSet",
            request_serializer=_json_request_serializer,
            response_deserializer=_json_response_deserializer(plugin_pb2.CacheSetResponse),
        )
        self.PublishResult = channel.unary_unary(
            "/mirastack.plugin.v1.EngineService/PublishResult",
            request_serializer=_json_request_serializer,
            response_deserializer=_json_response_deserializer(plugin_pb2.PublishResultResponse),
        )
        self.RequestApproval = channel.unary_unary(
            "/mirastack.plugin.v1.EngineService/RequestApproval",
            request_serializer=_json_request_serializer,
            response_deserializer=_json_response_deserializer(plugin_pb2.RequestApprovalResponse),
        )
        self.LogEvent = channel.unary_unary(
            "/mirastack.plugin.v1.EngineService/LogEvent",
            request_serializer=_json_request_serializer,
            response_deserializer=_json_response_deserializer(plugin_pb2.LogEventResponse),
        )
        self.CallPlugin = channel.unary_unary(
            "/mirastack.plugin.v1.EngineService/CallPlugin",
            request_serializer=_json_request_serializer,
            response_deserializer=_json_response_deserializer(plugin_pb2.CallPluginResponse),
        )
        self.Heartbeat = channel.unary_unary(
            "/mirastack.plugin.v1.EngineService/Heartbeat",
            request_serializer=_json_request_serializer,
            response_deserializer=_json_response_deserializer(plugin_pb2.HeartbeatResponse),
        )


# ---------------------------------------------------------------------------
# PluginService — Client stub (engine uses this to call plugins)
# ---------------------------------------------------------------------------

class PluginServiceStub:
    """Typed client for plugin RPCs — used by the engine.

    Uses JSON serialisation matching the MIRASTACK JSON gRPC codec.
    """

    def __init__(self, channel: grpc.Channel) -> None:
        self.Info = channel.unary_unary(
            "/mirastack.plugin.v1.PluginService/Info",
            request_serializer=_json_request_serializer,
            response_deserializer=_json_response_deserializer(plugin_pb2.InfoResponse),
        )
        self.GetSchema = channel.unary_unary(
            "/mirastack.plugin.v1.PluginService/GetSchema",
            request_serializer=_json_request_serializer,
            response_deserializer=_json_response_deserializer(plugin_pb2.GetSchemaResponse),
        )
        self.Execute = channel.unary_unary(
            "/mirastack.plugin.v1.PluginService/Execute",
            request_serializer=_json_request_serializer,
            response_deserializer=_json_response_deserializer(plugin_pb2.ExecuteResponse),
        )
        self.HealthCheck = channel.unary_unary(
            "/mirastack.plugin.v1.PluginService/HealthCheck",
            request_serializer=_json_request_serializer,
            response_deserializer=_json_response_deserializer(plugin_pb2.HealthCheckResponse),
        )
        self.ConfigUpdated = channel.unary_unary(
            "/mirastack.plugin.v1.PluginService/ConfigUpdated",
            request_serializer=_json_request_serializer,
            response_deserializer=_json_response_deserializer(plugin_pb2.ConfigUpdatedResponse),
        )
