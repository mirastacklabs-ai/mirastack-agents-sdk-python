"""gRPC server bootstrap for MIRASTACK plugins.

Usage::

    from mirastack_sdk import Plugin, serve

    class MyPlugin(Plugin):
        ...

    if __name__ == "__main__":
        serve(MyPlugin())
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import socket
import sys
import threading
import uuid
from concurrent import futures

import grpc

from mirastack_sdk.context import EngineContext
from mirastack_sdk._otel import init_otel, get_tracer
from mirastack_sdk.tenantid import id_from_slug
from mirastack_sdk.plugin import (
    Plugin,
    ExecuteRequest,
    ExecutionMode,
    ParamSchema,
    TimeRange,
)

logger = logging.getLogger("mirastack_sdk")


def serve(plugin: Plugin, *, max_workers: int = 10) -> None:
    """Start the plugin gRPC server and block until shutdown.

    This is the main entry point for plugin processes.
    The engine launches plugin processes and communicates via gRPC.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    info = plugin.info()
    if info is None:
        logger.fatal("plugin.info() must not return None")
        sys.exit(1)

    # ── Quality gate ──────────────────────────────────────────────────
    from mirastack_sdk.validate import validate_plugin  # noqa: E402

    gate_errors = validate_plugin(info)
    if gate_errors:
        logger.fatal(
            "Quality gate failed:\n  - %s", "\n  - ".join(gate_errors)
        )
        sys.exit(1)

    # ── Tenant ID resolution ──────────────────────────────────────────
    # MIRASTACK_PLUGIN_TENANT_ID must be set to the UUID5 of the tenant.
    # MIRASTACK_PLUGIN_TENANT_SLUG may be provided instead; the SDK derives
    # the UUID5 deterministically so operators need not compute it manually.
    tenant_id = os.environ.get("MIRASTACK_PLUGIN_TENANT_ID", "").strip()
    if not tenant_id:
        slug = os.environ.get("MIRASTACK_PLUGIN_TENANT_SLUG", "").strip()
        if not slug:
            logger.fatal(
                "MIRASTACK_PLUGIN_TENANT_ID is required — set it to the UUID5 of "
                "the tenant this plugin serves, or set MIRASTACK_PLUGIN_TENANT_SLUG "
                "to derive it"
            )
            sys.exit(1)
        tenant_id = id_from_slug(slug)
        logger.info("Resolved tenant ID from slug: slug=%s tenant_id=%s", slug, tenant_id)

    listen_addr = os.environ.get("MIRASTACK_PLUGIN_ADDR", "[::]:0")
    # Normalize bare ":port" to "0.0.0.0:port" — grpcio 1.72+ rejects empty host.
    if listen_addr.startswith(":"):
        listen_addr = "0.0.0.0" + listen_addr

    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=max_workers),
        options=[
            ("grpc.keepalive_time_ms", 30000),           # send keepalive ping every 30s
            ("grpc.keepalive_timeout_ms", 10000),        # wait 10s for ping ack
            ("grpc.keepalive_permit_without_calls", 1),  # allow pings with no active RPCs
            ("grpc.http2.min_recv_ping_interval_without_data_in_seconds", 20),  # allow client pings every 20s
        ],
    )

    # Register the PluginService adapter that delegates to the Plugin interface.
    # We dynamically build a gRPC servicer that bridges sync gRPC calls
    # to the async Plugin methods using a dedicated event loop running in a
    # background daemon thread.  asyncio.run_coroutine_threadsafe() requires
    # the target loop to be actively running; without this thread the future
    # returned by run_coroutine_threadsafe would never resolve.
    loop = asyncio.new_event_loop()
    loop_thread = threading.Thread(target=loop.run_forever, daemon=True, name="mirastack-async-loop")
    loop_thread.start()
    adapter = _PluginServiceAdapter(plugin, loop)

    try:
        from mirastack_sdk.gen import plugin_pb2_grpc  # type: ignore[import-untyped]
        plugin_pb2_grpc.add_PluginServiceServicer_to_server(adapter, server)
    except ImportError:
        # Generated proto stubs not yet available — register via generic handler.
        # This uses the method routing approach so the server still responds
        # to PluginService RPC calls.
        handler = _build_generic_handler(adapter)
        server.add_generic_rpc_handlers([handler])

    port = server.add_insecure_port(listen_addr)

    # Initialize OpenTelemetry (no-op when MIRASTACK_OTEL_ENABLED != "true")
    otel_shutdown = init_otel(info.name)

    # Write the actual port to stdout for the engine to discover
    print(f"MIRASTACK_PLUGIN_PORT={port}", flush=True)

    # Connect to engine for EngineContext callbacks (if address provided)
    engine_addr = os.environ.get("MIRASTACK_ENGINE_ADDR", "")
    engine_ctx: EngineContext | None = None
    instance_id = str(uuid.uuid4())
    if engine_addr:
        try:
            engine_ctx = EngineContext(engine_addr, info.name, tenant_id)
            plugin._engine_context = engine_ctx  # type: ignore[attr-defined]
            logger.info("Connected to engine for callbacks: %s", engine_addr)
        except Exception:
            logger.warning("Failed to connect to engine, callbacks unavailable", exc_info=True)

    server.start()

    logger.info("Plugin serving: %s v%s on port %d tenant_id=%s", info.name, info.version, port, tenant_id)

    # Maintain persistent registration with the engine in a background thread.
    # Registration must not block the gRPC server — the plugin must be ready to
    # accept Execute / HealthCheck calls immediately.  After initial
    # registration, the thread enters a heartbeat loop that periodically
    # re-registers.  This ensures the plugin survives engine restarts: when the
    # engine comes back, the next heartbeat re-establishes the registration.
    # In container and Kubernetes environments every replica should set
    # MIRASTACK_PLUGIN_ADVERTISE_ADDR to the Service name (e.g.
    # "agent-query-vmetrics:50051") so the engine dials the infrastructure
    # load-balancer, not an ephemeral pod/container address.
    stop_event = threading.Event()
    if engine_ctx is not None:
        advertise_addr = _resolve_advertise_addr(port)
        reg_thread = threading.Thread(
            target=_maintain_registration,
            args=(engine_ctx, advertise_addr, 1, info.version, instance_id, stop_event),
            daemon=True,
            name="mirastack-register",
        )
        reg_thread.start()

    # Handle shutdown signals
    def _signal_handler(sig: int, frame: object) -> None:
        logger.info("Shutting down plugin (signal %d)", sig)
        # Stop the registration heartbeat loop.
        stop_event.set()
        # Deregister from engine before stopping
        if engine_ctx is not None:
            try:
                engine_ctx.deregister_self(instance_id)
                logger.info("Deregistered from engine")
            except Exception:
                logger.warning("Deregistration from engine failed", exc_info=True)
        otel_shutdown()
        server.stop(grace=5)

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    server.wait_for_termination()
    loop.call_soon_threadsafe(loop.stop)
    loop_thread.join(timeout=5)
    loop.close()


class _PluginServiceAdapter:
    """Bridges the Python Plugin interface to gRPC PluginService RPCs.

    gRPC Python uses synchronous servicers running in a ThreadPoolExecutor.
    Plugin methods are async, so we run them on a dedicated event loop.
    """

    def __init__(self, plugin: Plugin, loop: asyncio.AbstractEventLoop) -> None:
        self._plugin = plugin
        self._loop = loop

    def _run_async(self, coro):
        """Run an async coroutine on the adapter's event loop from a sync context."""
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()

    # -- PluginService RPCs --

    def Info(self, request, context):
        """Handle PluginService.Info RPC."""
        info = self._plugin.info()
        resp = {
            "name": info.name,
            "version": info.version,
            "description": info.description,
            "permission": (info.permissions[0].value + 1) if info.permissions else 1,
            "devops_stages": [s.value + 1 for s in info.devops_stages],
            "default_intents": [
                {
                    "pattern": ip.pattern,
                    "confidence": ip.priority / 10.0,
                    "description": ip.description,
                    "priority": ip.priority,
                }
                for ip in info.intents
            ],
        }
        if info.actions:
            resp["actions"] = [_action_to_dict(act) for act in info.actions]
        if info.prompt_templates:
            resp["prompt_templates"] = [
                {
                    "name": pt.name,
                    "description": pt.description,
                    "content": pt.content,
                }
                for pt in info.prompt_templates
            ]
        if info.config_params:
            resp["config_schema"] = [
                {
                    "key": cp.key,
                    "type": cp.type,
                    "required": cp.required,
                    "default": cp.default,
                    "description": cp.description,
                    "is_secret": cp.is_secret,
                }
                for cp in info.config_params
            ]
        return resp

    def GetSchema(self, request, context):
        """Handle PluginService.GetSchema RPC."""
        schema = self._plugin.schema()
        resp = {
            "params_json_schema": json.dumps(
                [_param_to_dict(p) for p in schema.input_params]
            ).encode(),
            "result_json_schema": json.dumps(
                [_param_to_dict(p) for p in schema.output_params]
            ).encode(),
        }
        if schema.actions:
            resp["actions"] = [_action_to_dict(act) for act in schema.actions]
        return resp

    def Execute(self, request, context):
        """Handle PluginService.Execute RPC."""
        tracer = get_tracer()
        action_id = request.get("action_id", "")
        execution_id = request.get("execution_id", "")

        span_ctx = None
        span = None
        if tracer is not None:
            from opentelemetry import trace as _trace

            span_ctx = tracer.start_span(
                "plugin.execute",
                kind=_trace.SpanKind.INTERNAL,
                attributes={
                    "plugin.action": action_id,
                    "plugin.execution_id": execution_id,
                },
            )
            span = span_ctx
            context_api = _trace.context_api
            # Activate span in current context
            token = context_api.attach(  # noqa: F841
                _trace.set_span_in_context(span)
            )

        try:
            result = self._execute_inner(request, context)
            if span is not None:
                span.set_attribute("plugin.success", True)
            return result
        except Exception as exc:
            if span is not None:
                span.record_exception(exc)
                from opentelemetry.trace import StatusCode

                span.set_status(StatusCode.ERROR, str(exc))
            raise
        finally:
            if span is not None:
                span.end()

    def _execute_inner(self, request, context):
        params = json.loads(request.get("params_json", b"{}"))
        mode_val = request.get("mode", 1)

        req = ExecuteRequest(
            execution_id=request.get("execution_id", ""),
            workflow_id=request.get("workflow_id", ""),
            step_id=request.get("step_id", ""),
            action_id=request.get("action_id", ""),
            params=params if isinstance(params, dict) else {},
            mode=ExecutionMode(max(0, mode_val - 1)),
            tenant_id=request.get("tenant_id", ""),
        )

        # Map proto TimeRange to SDK TimeRange
        tr_data = request.get("time_range")
        if tr_data and isinstance(tr_data, dict):
            req.time_range = TimeRange(
                start_epoch_ms=tr_data.get("start_epoch_ms", 0),
                end_epoch_ms=tr_data.get("end_epoch_ms", 0),
                timezone=tr_data.get("timezone", ""),
                original_expression=tr_data.get("original_expression", ""),
            )

        resp = self._run_async(self._plugin.execute(req))

        if isinstance(resp.output, bytes):
            result_json = resp.output
        elif resp.output:
            result_json = json.dumps(resp.output).encode()
        else:
            result_json = b"{}"
        logs = resp.logs or []
        return {
            "result_json": result_json,
            "logs": logs,
            "success": True,
        }

    def HealthCheck(self, request, context):
        """Handle PluginService.HealthCheck RPC."""
        try:
            self._run_async(self._plugin.health_check())
            return {"healthy": True}
        except Exception as e:
            return {"healthy": False, "message": str(e)}

    def ConfigUpdated(self, request, context):
        """Handle PluginService.ConfigUpdated RPC."""
        # The engine sends config as a map[string]string with JSON key "config"
        # (see pluginv1.ConfigUpdatedRequest in the Go SDK).  When transmitted
        # via the JSON codec the field arrives as a plain dict, not as bytes
        # requiring json.loads().
        config = request.get("config", {})
        if isinstance(config, bytes):
            config = json.loads(config)
        self._run_async(self._plugin.config_updated(config))
        return {}


def _param_to_dict(p: ParamSchema) -> dict:
    return {
        "name": p.name,
        "type": p.type,
        "required": p.required,
        "description": p.description,
    }


def _action_to_dict(act) -> dict:
    d: dict = {
        "id": act.id,
        "description": act.description,
        "permission": act.permission.value + 1,
        "stages": [s.value + 1 for s in act.stages],
        "intents": [
            {
                "pattern": ip.pattern,
                "confidence": ip.priority / 10.0,
                "description": ip.description,
                "priority": ip.priority,
            }
            for ip in act.intents
        ],
    }
    if act.input_params:
        d["input_params"] = json.dumps(
            [_param_to_dict(p) for p in act.input_params]
        ).encode()
    if act.output_params:
        d["output_params"] = json.dumps(
            [_param_to_dict(p) for p in act.output_params]
        ).encode()
    return d


def _build_generic_handler(adapter: _PluginServiceAdapter) -> grpc.GenericRpcHandler:
    """Build a generic gRPC handler for PluginService when proto stubs are unavailable.

    This registers unary-unary handlers for all 5 PluginService RPCs using JSON
    codec serialization, matching the Go SDK's approach.
    """
    from grpc import unary_unary_rpc_method_handler

    service_name = "mirastack.plugin.v1.PluginService"

    method_handlers = {
        f"/{service_name}/Info": unary_unary_rpc_method_handler(adapter.Info),
        f"/{service_name}/GetSchema": unary_unary_rpc_method_handler(adapter.GetSchema),
        f"/{service_name}/Execute": unary_unary_rpc_method_handler(adapter.Execute),
        f"/{service_name}/HealthCheck": unary_unary_rpc_method_handler(adapter.HealthCheck),
        f"/{service_name}/ConfigUpdated": unary_unary_rpc_method_handler(adapter.ConfigUpdated),
    }

    class _Handler(grpc.GenericRpcHandler):
        def service(self, handler_call_details):
            return method_handlers.get(handler_call_details.method)

    return _Handler()


def _resolve_advertise_addr(bound_port: int) -> str:
    """Determine the address the engine should use to reach this plugin via gRPC.

    Order of precedence:

        1. ``MIRASTACK_PLUGIN_ADVERTISE_ADDR`` — explicit, always wins.
           In containerized (Docker/Podman) and Kubernetes deployments this
           MUST be set to the Service DNS name (e.g.
           ``agent-query-vmetrics:50051`` for Compose or
           ``agent-query-vmetrics.ns.svc.cluster.local:50051`` for K8s).
           For horizontal scaling every replica advertises the same Service
           address; the infrastructure (kube-proxy, Compose DNS round-robin)
           handles load-balancing across pods/containers.
        2. ``socket.gethostname()`` + bound port — suitable for native
           (bare-metal / VM) installs where the OS hostname is DNS-resolvable.
    """
    addr = os.environ.get("MIRASTACK_PLUGIN_ADVERTISE_ADDR", "")
    if addr:
        return addr
    hostname = socket.gethostname() or "localhost"
    return f"{hostname}:{bound_port}"


def _maintain_registration(
    engine_ctx: EngineContext,
    advertise_addr: str,
    plugin_type: int,
    version: str,
    instance_id: str,
    stop_event: threading.Event,
) -> None:
    """Perform initial registration then maintain a persistent heartbeat.

    Phase 1: Initial registration with exponential backoff (2 s → 30 s cap,
    up to 10 attempts).
    Phase 2: Persistent heartbeat loop that re-registers every interval
    (default 30 s, configurable via MIRASTACK_PLUGIN_HEARTBEAT_INTERVAL).

    This ensures the plugin survives engine restarts: when the engine comes
    back, the next heartbeat re-establishes the registration.
    Runs in a daemon thread so the gRPC server is not blocked.
    """
    max_attempts = 10
    max_backoff = 30.0
    backoff = 2.0

    heartbeat_interval_str = os.environ.get("MIRASTACK_PLUGIN_HEARTBEAT_INTERVAL", "30")
    try:
        heartbeat_interval = max(1.0, float(heartbeat_interval_str))
    except ValueError:
        heartbeat_interval = 30.0

    # Phase 1: Initial registration with bounded retries.
    registered = False
    for attempt in range(1, max_attempts + 1):
        if stop_event.is_set():
            return
        try:
            resp = engine_ctx.register_self(
                grpc_addr=advertise_addr,
                plugin_type=plugin_type,
                version=version,
                instance_id=instance_id,
            )
            if resp.get("success"):
                logger.info(
                    "Self-registered with engine: plugin_id=%s addr=%s",
                    resp.get("plugin_id", ""),
                    advertise_addr,
                )
                registered = True
                break
            logger.warning(
                "Self-registration rejected: %s", resp.get("error", "unknown")
            )
        except Exception:
            if attempt == max_attempts:
                logger.error(
                    "Initial registration exhausted all retries (%d) — "
                    "entering heartbeat mode, will keep trying",
                    max_attempts,
                    exc_info=True,
                )
                break
            logger.warning(
                "Self-registration attempt %d failed, retrying in %.0fs",
                attempt,
                backoff,
                exc_info=True,
            )

        if stop_event.wait(timeout=backoff):
            return
        backoff = min(backoff * 2, max_backoff)

    if registered:
        logger.info(
            "Entering registration heartbeat loop (interval=%.0fs)",
            heartbeat_interval,
        )

    # Phase 2: Persistent heartbeat loop.
    # Sends a lightweight Heartbeat RPC instead of full RegisterPlugin.
    # If the engine responds with re_register_required (e.g. engine restarted
    # and lost in-memory state), the SDK performs a full register_self to
    # re-establish the plugin in the engine's registry.
    # If the engine returns a non-zero heartbeat_interval_seconds, the SDK
    # adopts it (unless overridden by env var).
    env_override = os.environ.get("MIRASTACK_PLUGIN_HEARTBEAT_INTERVAL", "") != ""
    consecutive_failures = 0
    while not stop_event.wait(timeout=heartbeat_interval):
        try:
            resp = engine_ctx.heartbeat(instance_id=instance_id)

            # Adopt engine-recommended heartbeat interval (if no env override).
            engine_interval = resp.get("heartbeat_interval_seconds", 0)
            if not env_override and engine_interval and engine_interval > 0:
                new_interval = float(engine_interval)
                if new_interval != heartbeat_interval:
                    heartbeat_interval = new_interval
                    logger.info(
                        "Adopted engine-recommended heartbeat interval: %.0fs",
                        heartbeat_interval,
                    )

            if resp.get("re_register_required"):
                logger.info("Engine requested re-registration, performing full RegisterPlugin")
                try:
                    reg_resp = engine_ctx.register_self(
                        grpc_addr=advertise_addr,
                        plugin_type=plugin_type,
                        version=version,
                        instance_id=instance_id,
                    )
                    if reg_resp.get("success"):
                        logger.info(
                            "Re-registered with engine: plugin_id=%s",
                            reg_resp.get("plugin_id", ""),
                        )
                    else:
                        consecutive_failures += 1
                        logger.warning(
                            "Re-registration rejected: %s",
                            reg_resp.get("error", "unknown"),
                        )
                        continue
                except Exception:
                    consecutive_failures += 1
                    logger.warning(
                        "Re-registration after heartbeat failed",
                        exc_info=True,
                    )
                    continue

            if consecutive_failures > 0:
                logger.info(
                    "Heartbeat recovered after %d failures",
                    consecutive_failures,
                )
            consecutive_failures = 0
        except Exception:
            consecutive_failures += 1
            if consecutive_failures == 1 or consecutive_failures % 10 == 0:
                logger.warning(
                    "Heartbeat failed (failures=%d)",
                    consecutive_failures,
                    exc_info=True,
                )
