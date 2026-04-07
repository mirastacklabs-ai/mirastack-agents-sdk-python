# mirastack-agents-sdk

Python SDK for building **MIRASTACK agents** — the external gRPC plugins that perform READ, MODIFY, and ADMIN actions on platform engineering systems. Agents are pure compute: they receive params via gRPC and use the `EngineContext` proxy to interact with the engine.

**License:** GNU AGPL v3 — see [LICENSE](LICENSE).

## Installation

```bash
pip install mirastack-agents-sdk
```

## Quick Start

```python
from mirastack_sdk import (
    Plugin, PluginInfo, PluginSchema, Action, IntentPattern,
    Permission, DevOpsStage, ExecuteRequest, ExecuteResponse,
    respond_map, serve,
)

class MyAgent(Plugin):
    def info(self) -> PluginInfo:
        return PluginInfo(
            name="my-agent",
            version="0.1.0",
            description="Example observability agent",
            actions=[
                Action(
                    id="query",
                    description="Query metrics for a service",
                    permission=Permission.READ,
                    stages=[DevOpsStage.OBSERVE],
                    input_params=[{"name": "service", "type": "string", "required": True}],
                ),
            ],
            intents=[
                IntentPattern(pattern=r"query.*metrics|show.*metrics", description="Query metrics", priority=1),
            ],
        )

    def schema(self) -> PluginSchema:
        return PluginSchema(actions=self.info().actions)

    async def execute(self, req: ExecuteRequest) -> ExecuteResponse:
        service = req.params.get("service", "")
        return respond_map({"service": service, "status": "ok"})

    async def health_check(self) -> None: pass

    async def config_updated(self, config: dict) -> None: pass

if __name__ == "__main__":
    serve(MyAgent())
```

## Plugin Interface

```python
class Plugin(ABC):
    def info(self) -> PluginInfo: ...
    def schema(self) -> PluginSchema: ...
    async def execute(self, req: ExecuteRequest) -> ExecuteResponse: ...
    async def health_check(self) -> None: ...
    async def config_updated(self, config: dict[str, str]) -> None: ...
```

## Response Helpers

```python
from mirastack_sdk import respond_map, respond_json, respond_error, respond_raw

return respond_map({"metric": 42.0, "service": "api"})   # typed dict response
return respond_json(my_dataclass)                         # any serialisable type
return respond_error("backend unavailable")               # error response
return respond_raw(b'{"raw": "json"}')                    # raw JSON passthrough
```

## Agent-Specific Features

### Actions — Tool Catalog Registration

```python
Action(
    id="restart_service",
    description="Restart a Kubernetes deployment",
    permission=Permission.MODIFY,   # READ | MODIFY | ADMIN
    stages=[DevOpsStage.OPERATE],
    input_params=[
        {"name": "namespace",  "type": "string", "required": True},
        {"name": "deployment", "type": "string", "required": True},
    ],
    output_params=[{"name": "status", "type": "string"}],
)
```

### Intent Patterns — Natural Language Routing

```python
IntentPattern(
    pattern=r"restart.*deployment|rollout.*restart",
    description="Restart a Kubernetes deployment",
    priority=10,
)
```

### Prompt Templates

```python
from mirastack_sdk import PromptTemplate

PromptTemplate(
    name="my_agent_analysis",
    description="Analysis prompt contributed to the engine PromptTemplate Store",
    content="Analyse the following data: {{ data }}",
)
```

## Engine Context

```python
from mirastack_sdk import EngineContext

class MyAgent(Plugin):
    def set_engine_context(self, ctx: EngineContext) -> None:
        self._ctx = ctx

    async def execute(self, req: ExecuteRequest) -> ExecuteResponse:
        url   = await self._ctx.get_config("backend.url")
        await   self._ctx.cache_set("key", "value", ttl=300)
        val   = await self._ctx.cache_get("key")
        await   self._ctx.publish_result({"data": val})
        ok    = await self._ctx.request_approval("Proceed?", Permission.MODIFY)
        await   self._ctx.log_event("action_completed", {"action": "query"})
```

## DateTime Utilities

Convert `req.time_range` to backend-specific formats — never parse time in a plugin:

```python
from mirastack_sdk import datetimeutils

start = datetimeutils.format_epoch_seconds(req.time_range.start_epoch_ms)  # VictoriaMetrics
start = datetimeutils.format_epoch_micros(req.time_range.start_epoch_ms)   # VictoriaTraces
start = datetimeutils.format_rfc3339(req.time_range.start_epoch_ms)        # VictoriaLogs
```

## SDK Components

| Module | Purpose |
|--------|---------| 
| `plugin.py` | `Plugin` ABC, `PluginInfo`, `Action`, `IntentPattern`, `PromptTemplate` |
| `context.py` | `EngineContext` proxy — config, cache, publish, approval, audit log |
| `respond.py` | `respond_map`, `respond_json`, `respond_error`, `respond_raw` helpers |
| `serve.py` | gRPC server bootstrap — call `serve(agent)` from `__main__` |
| `datetimeutils.py` | Time format converters for all MIRASTACK backends |
| `gen/` | Hand-written gRPC proto stubs (will be replaced by `buf generate`) |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MIRASTACK_ENGINE_ADDR` | `localhost:50051` | Engine gRPC address |
| `MIRASTACK_PLUGIN_PORT` | `50052` | Port this agent listens on |
