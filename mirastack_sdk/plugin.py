"""Base plugin interface for MIRASTACK plugins."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Mapping


class Permission(IntEnum):
    READ = 0
    MODIFY = 1
    ADMIN = 2


class DevOpsStage(IntEnum):
    PLAN = 0
    CODE = 1
    BUILD = 2
    TEST = 3
    RELEASE = 4
    DEPLOY = 5
    OPERATE = 6
    OBSERVE = 7


class ExecutionMode(IntEnum):
    MANUAL = 0
    GUIDED = 1
    AUTONOMOUS = 2


@dataclass
class ParamSchema:
    name: str
    type: str  # "string", "number", "boolean", "json"
    required: bool = False
    description: str = ""


@dataclass
class IntentPattern:
    pattern: str
    description: str = ""
    priority: int = 0


@dataclass
class ConfigParam:
    """Declares a configuration parameter the plugin accepts.

    The engine reads these from info() during registration and seeds them
    into the unified settings store at plugin.{name}.{key}.
    """
    key: str
    type: str = "string"      # "string", "int", "bool", "duration", "json"
    required: bool = False
    default: str = ""
    description: str = ""
    is_secret: bool = False


@dataclass
class PromptTemplate:
    """A prompt template contributed by a plugin.

    The engine auto-ingests these during plugin registration and makes them
    available through the Prompt Template Store for LLM interactions.
    """
    name: str
    description: str = ""
    content: str = ""


@dataclass
class PluginInfo:
    name: str
    version: str
    description: str = ""
    permissions: list[Permission] = field(default_factory=list)
    devops_stages: list[DevOpsStage] = field(default_factory=list)
    intents: list[IntentPattern] = field(default_factory=list)
    actions: list[Action] = field(default_factory=list)
    prompt_templates: list[PromptTemplate] = field(default_factory=list)
    config_params: list[ConfigParam] = field(default_factory=list)


@dataclass
class Action:
    """Describes a discrete operation a plugin can perform.

    Actions are first-class entities that the engine maps intents to.
    A plugin may declare zero or more actions. When actions are declared,
    the engine registers their intents and routes matching user messages
    directly to the plugin with the action_id set on ExecuteRequest.
    """
    id: str
    description: str = ""
    permission: Permission = Permission.READ
    stages: list[DevOpsStage] = field(default_factory=list)
    intents: list[IntentPattern] = field(default_factory=list)
    input_params: list[ParamSchema] = field(default_factory=list)
    output_params: list[ParamSchema] = field(default_factory=list)


@dataclass
class PluginSchema:
    input_params: list[ParamSchema] = field(default_factory=list)
    output_params: list[ParamSchema] = field(default_factory=list)
    actions: list[Action] = field(default_factory=list)


@dataclass
class TimeRange:
    """Pre-parsed, absolute UTC time range delivered by the engine.

    Plugins receive this on ExecuteRequest and use SDK datetimeutils to format
    epochs for their specific backends (Prometheus, Jaeger, VictoriaLogs, etc.).
    """
    start_epoch_ms: int = 0
    end_epoch_ms: int = 0
    timezone: str = ""
    original_expression: str = ""


@dataclass
class ExecuteRequest:
    execution_id: str
    workflow_id: str
    step_id: str
    action_id: str = ""
    params: dict[str, str] = field(default_factory=dict)
    mode: ExecutionMode = ExecutionMode.GUIDED
    time_range: TimeRange | None = None
    # UUID5 of the tenant this execution belongs to. The engine stamps this on
    # every ExecuteRequest; plugins must treat it as authoritative and must
    # never derive tenant from params or context.
    tenant_id: str = ""


@dataclass
class ExecuteResponse:
    output: Any = field(default_factory=dict)
    logs: list[str] = field(default_factory=list)


class Plugin(abc.ABC):
    """Base class for all MIRASTACK plugins.

    Plugin authors subclass this and implement the abstract methods::

        class MyPlugin(Plugin):
            def info(self) -> PluginInfo:
                return PluginInfo(name="my-plugin", version="1.0.0")

            def schema(self) -> PluginSchema:
                return PluginSchema(input_params=[...])

            async def execute(self, req: ExecuteRequest) -> ExecuteResponse:
                ...
                return ExecuteResponse(output={"result": "done"})
    """

    @abc.abstractmethod
    def info(self) -> PluginInfo:
        """Return static plugin metadata."""
        ...

    @abc.abstractmethod
    def schema(self) -> PluginSchema:
        """Return the plugin's input/output parameter schema."""
        ...

    @abc.abstractmethod
    async def execute(self, req: ExecuteRequest) -> ExecuteResponse:
        """Execute the plugin's action with the given parameters."""
        ...

    async def health_check(self) -> None:
        """Return None if healthy, raise an exception otherwise."""
        pass

    async def config_updated(self, config: dict[str, str]) -> None:
        """Called when the engine pushes new configuration."""
        pass


# ---------------------------------------------------------------------------
# Licensing snapshot (added in SDK v1.8.0 to mirror Go SDK pluginv1)
#
# The engine sends a `license` field on every RegisterPluginResponse and
# HeartbeatResponse. The wire format is JSON (see EngineContext._call_unary
# in context.py for the codec). These dataclasses give Python plugin authors
# a typed view that is byte-for-byte identical to the Go SDK's
# `pluginv1.LicenseContext` / `pluginv1.LicenseQuotas` structs and survives
# the round-trip through `dataclasses.asdict`.
# ---------------------------------------------------------------------------


@dataclass
class LicenseQuotas:
    """Engine-enforced licence caps. ``-1`` means unlimited.

    AI Box counts are deliberately omitted: per the engine's licensing
    rules they are marketing labels and never enforced at runtime. Only
    fields the engine actively meters appear here.
    """

    max_tenants: int = 0
    max_integration_types: int = 0
    max_agentic_sessions_per_day: int = 0

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "LicenseQuotas":
        """Build a typed quotas value from the engine's JSON dict.

        Returns a zero-valued instance when ``data`` is ``None`` or empty —
        the engine omits the field for unlimited tiers and the SDK should
        not raise.
        """
        if not data:
            return cls()
        return cls(
            max_tenants=int(data.get("max_tenants", 0) or 0),
            max_integration_types=int(data.get("max_integration_types", 0) or 0),
            max_agentic_sessions_per_day=int(
                data.get("max_agentic_sessions_per_day", 0) or 0
            ),
        )


@dataclass
class LicenseContext:
    """Engine licensing snapshot served at registration and heartbeat.

    Field semantics:

      * ``active``: ``True`` iff the engine considers the license
        currently enforceable (signed, not revoked, not past expiry).
      * ``effective_tier``: tier the engine is currently honouring.
        During the post-expiry grace period this degrades to ``"neo"``
        while the payload still carries the originally-issued tier.
      * ``grace_mode``: ``True`` when the license has expired and the
        engine is serving from grace; the SDK warns at startup.
      * ``quotas``: distilled hard caps the SDK MAY use to choose
        between paths (e.g. skip a feature a "neo" install cannot run).
        ``-1`` in any quota means unlimited.

    See ``mirastack-agents-sdk-go/gen/pluginv1.LicenseContext`` for the
    canonical Go-side struct this dataclass mirrors.
    """

    active: bool = False
    effective_tier: str = ""
    issued_tier: str = ""
    grace_mode: bool = False
    expires_at: int = 0  # epoch ms
    org_id: str = ""
    site_id: str = ""
    region: str = ""
    region_kind: str = ""
    quotas: LicenseQuotas = field(default_factory=LicenseQuotas)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "LicenseContext | None":
        """Build a typed context from the engine's JSON dict.

        Returns ``None`` when ``data`` is ``None`` (engine could not
        resolve the active license — boot race) so callers can keep
        using the last-known snapshot.
        """
        if data is None:
            return None
        return cls(
            active=bool(data.get("active", False)),
            effective_tier=str(data.get("effective_tier", "")),
            issued_tier=str(data.get("issued_tier", "")),
            grace_mode=bool(data.get("grace_mode", False)),
            expires_at=int(data.get("expires_at", 0) or 0),
            org_id=str(data.get("org_id", "")),
            site_id=str(data.get("site_id", "")),
            region=str(data.get("region", "")),
            region_kind=str(data.get("region_kind", "")),
            quotas=LicenseQuotas.from_dict(data.get("quotas")),
        )
