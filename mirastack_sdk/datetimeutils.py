"""Time format conversion utilities for MIRASTACK plugins.

The engine parses user time expressions and delivers pre-resolved UTC epoch
milliseconds in the TimeRange proto message. Plugins use this module to
convert those epochs into the format their backend expects.

This module is purely a formatter — it never parses user input.
Parsing is the engine's responsibility.

Usage in a plugin::

    from mirastack_sdk.datetimeutils import (
        format_epoch_seconds,
        format_epoch_micros,
        format_rfc3339,
    )

    # From ExecuteRequest time_range start_epoch_ms
    prom_ts = format_epoch_seconds(start_ms)    # → "1743580800.000"
    rfc = format_rfc3339(start_ms)              # → "2026-04-02T00:00:00Z"
    jaeger_ts = format_epoch_micros(start_ms)   # → "1743580800000000"
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo


def format_epoch_seconds(epoch_ms: int) -> str:
    """Convert UTC epoch milliseconds to epoch seconds string.

    Used by: Prometheus, VictoriaMetrics (query_range start/end).
    """
    return f"{epoch_ms / 1000:.3f}"


def format_epoch_millis(epoch_ms: int) -> str:
    """Convert UTC epoch milliseconds to epoch milliseconds string.

    Used by: Jaeger dependencies endpoint (endTs parameter).
    """
    return str(epoch_ms)


def format_epoch_micros(epoch_ms: int) -> str:
    """Convert UTC epoch milliseconds to epoch microseconds string.

    Used by: Jaeger trace search (start/end parameters).
    """
    return str(epoch_ms * 1000)


def format_epoch_nanos(epoch_ms: int) -> str:
    """Convert UTC epoch milliseconds to epoch nanoseconds string.

    Used by: OpenTelemetry native formats.
    """
    return str(epoch_ms * 1_000_000)


def format_rfc3339(epoch_ms: int) -> str:
    """Convert UTC epoch milliseconds to an RFC3339 string.

    Used by: REST APIs, JSON responses, general-purpose interchange.
    """
    dt = datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def format_rfc3339_nano(epoch_ms: int) -> str:
    """Convert UTC epoch milliseconds to an RFC3339 string with millisecond precision.

    Used by: High-precision timestamp logging.
    """
    dt = datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{epoch_ms % 1000:03d}Z"


def format_date(epoch_ms: int) -> str:
    """Convert UTC epoch milliseconds to a date string "YYYY-MM-DD".

    Used by: Date-only queries, partition keys.
    """
    dt = datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d")


def format_datetime(epoch_ms: int) -> str:
    """Convert UTC epoch milliseconds to "YYYY-MM-DD HH:MM:SS".

    Used by: Human-readable logs, audit trails.
    """
    dt = datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def format_custom(epoch_ms: int, fmt: str) -> str:
    """Convert UTC epoch milliseconds using a custom strftime format.

    Used by: Plugin-specific formats not covered by the standard functions.
    """
    dt = datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc)
    return dt.strftime(fmt)


def format_in_timezone(epoch_ms: int, tz: str) -> str:
    """Convert UTC epoch milliseconds to RFC3339 in a specific timezone.

    Args:
        epoch_ms: UTC epoch milliseconds.
        tz: IANA timezone name (e.g., "Asia/Kolkata").

    Returns:
        RFC3339 string with timezone offset.

    Raises:
        KeyError: If the timezone name is invalid.
    """
    dt = datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc)
    local_dt = dt.astimezone(ZoneInfo(tz))
    offset = local_dt.strftime("%z")
    # Format offset as +HH:MM
    offset_str = f"{offset[:3]}:{offset[3:]}" if len(offset) == 5 else offset
    return local_dt.strftime(f"%Y-%m-%dT%H:%M:%S{offset_str}")


def format_lookback_millis(start_ms: int, end_ms: int) -> str:
    """Return duration between start and end as milliseconds string.

    Used by: Jaeger dependencies endpoint (lookback parameter).
    """
    return str(end_ms - start_ms)


def to_datetime(epoch_ms: int) -> datetime:
    """Convert UTC epoch milliseconds to a Python datetime (UTC)."""
    return datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc)


def from_datetime(dt: datetime) -> int:
    """Convert a Python datetime to UTC epoch milliseconds."""
    return int(dt.timestamp() * 1000)


def now_utc_ms() -> int:
    """Return the current time as UTC epoch milliseconds.

    Use this for default time windows instead of time.time() or
    datetime.now() in plugin code.
    """
    return int(datetime.now(tz=timezone.utc).timestamp() * 1000)
