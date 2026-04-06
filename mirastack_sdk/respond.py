"""Convenience constructors for ExecuteResponse with typed output."""

from __future__ import annotations

import json
from typing import Any

from mirastack_sdk.plugin import ExecuteResponse


def respond_map(data: dict[str, Any]) -> ExecuteResponse:
    """Return an ExecuteResponse whose output is a JSON-serialised dict."""
    return ExecuteResponse(output=json.dumps(data).encode())


def respond_json(obj: Any) -> ExecuteResponse:
    """Return an ExecuteResponse whose output is a JSON-serialised object."""
    return ExecuteResponse(output=json.dumps(obj).encode())


def respond_error(message: str) -> ExecuteResponse:
    """Return an ExecuteResponse representing an error."""
    return ExecuteResponse(output=json.dumps({"error": message}).encode())


def respond_raw(data: bytes) -> ExecuteResponse:
    """Return an ExecuteResponse whose output is raw bytes."""
    return ExecuteResponse(output=data)
