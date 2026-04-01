"""Base plugin interface for MIRASTACK plugins."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any


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
class PluginInfo:
    name: str
    version: str
    description: str = ""
    permissions: list[Permission] = field(default_factory=list)
    devops_stages: list[DevOpsStage] = field(default_factory=list)
    intents: list[IntentPattern] = field(default_factory=list)


@dataclass
class PluginSchema:
    input_params: list[ParamSchema] = field(default_factory=list)
    output_params: list[ParamSchema] = field(default_factory=list)


@dataclass
class ExecuteRequest:
    execution_id: str
    workflow_id: str
    step_id: str
    params: dict[str, str] = field(default_factory=dict)
    mode: ExecutionMode = ExecutionMode.GUIDED


@dataclass
class ExecuteResponse:
    output: dict[str, str] = field(default_factory=dict)
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
