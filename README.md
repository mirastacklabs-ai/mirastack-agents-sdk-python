# MIRASTACK SDK for Python

Python SDK for building **MIRASTACK** plugins. Async-native with gRPC transport, providing base plugin class, engine context proxy, and server bootstrap.

## Installation

```bash
pip install mirastack-sdk
```

## Quick Start

```python
from mirastack_sdk import BasePlugin, PluginInfo, Permission, DevOpsStage, serve

class MyPlugin(BasePlugin):
    def info(self) -> PluginInfo:
        return PluginInfo(
            name="my-plugin",
            version="0.1.0",
            permission=Permission.READ,
            devops_stage=DevOpsStage.OBSERVE,
        )

    async def execute(self, action: str, params: dict) -> dict:
        return {"result": "done"}

if __name__ == "__main__":
    serve(MyPlugin())
```

## SDK Components

| File | Purpose |
|------|---------|
| `plugin.py` | Base plugin class + data models |
| `context.py` | Engine context proxy (config, cache, events) |
| `serve.py` | gRPC server bootstrap |
| `gen/` | Generated protobuf Python types |

## Plugin Base Class

```python
class BasePlugin:
    def info(self) -> PluginInfo: ...
    def get_schema(self) -> Schema: ...
    async def execute(self, action: str, params: dict) -> dict: ...
    async def health_check(self) -> bool: ...
    async def config_updated(self, config: dict) -> None: ...
```

## Engine Context

```python
# Read configuration
url = await ctx.get_config("victoriametrics.url")

# Cache operations
await ctx.cache_set("key", "value", ttl=300)
value = await ctx.cache_get("key")

# Publish results
await ctx.publish_result(result)

# Request approval
approved = await ctx.request_approval("Delete old data?", Permission.MODIFY)
```

## Requirements

- Python 3.12+
- grpcio, protobuf, httpx

## License

AGPL v3 — see [LICENSE](LICENSE).
