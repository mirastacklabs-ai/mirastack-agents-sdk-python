"""gRPC message-size ceiling for MIRASTACK Python plugins.

Reads MIRASTACK_PLUGIN_MAX_MESSAGE_BYTES (default 64 MiB). Invalid values
fall back to the default and log a warning — never raise.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("mirastack_sdk.grpc_msgsize")

ENV_VAR = "MIRASTACK_PLUGIN_MAX_MESSAGE_BYTES"
DEFAULT_BYTES = 67108864


def resolve_max_message_bytes() -> int:
    """Return the configured max gRPC message size in bytes.

    Empty / unset → DEFAULT_BYTES.
    Non-numeric, zero, or negative → DEFAULT_BYTES + warning (never raises).
    """
    raw = os.environ.get(ENV_VAR)
    if raw is None:
        return DEFAULT_BYTES
    raw = raw.strip()
    if raw == "":
        return DEFAULT_BYTES
    try:
        n = int(raw)
    except ValueError:
        logger.warning(
            "invalid %s=%r — falling back to default %d",
            ENV_VAR,
            raw,
            DEFAULT_BYTES,
        )
        return DEFAULT_BYTES
    if n <= 0:
        logger.warning(
            "invalid %s=%r (must be > 0) — falling back to default %d",
            ENV_VAR,
            raw,
            DEFAULT_BYTES,
        )
        return DEFAULT_BYTES
    return n
