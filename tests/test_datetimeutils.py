"""Tests for mirastack_sdk.datetimeutils."""

from datetime import datetime, timezone

from mirastack_sdk.datetimeutils import (
    format_epoch_seconds,
    format_epoch_millis,
    format_epoch_micros,
    format_epoch_nanos,
    format_rfc3339,
    format_rfc3339_nano,
    format_date,
    format_datetime,
    format_custom,
    format_in_timezone,
    format_lookback_millis,
    to_datetime,
    from_datetime,
)


# 2026-04-02T12:30:00Z in epoch ms
TEST_MS = 1774973400000


def test_format_epoch_seconds():
    assert format_epoch_seconds(TEST_MS) == "1774973400.000"


def test_format_epoch_millis():
    assert format_epoch_millis(TEST_MS) == "1774973400000"


def test_format_epoch_micros():
    assert format_epoch_micros(TEST_MS) == "1774973400000000"


def test_format_epoch_nanos():
    assert format_epoch_nanos(TEST_MS) == "1774973400000000000"


def test_format_rfc3339():
    assert format_rfc3339(TEST_MS) == "2026-04-02T12:30:00Z"


def test_format_rfc3339_nano():
    assert format_rfc3339_nano(TEST_MS) == "2026-04-02T12:30:00.000Z"


def test_format_date():
    assert format_date(TEST_MS) == "2026-04-02"


def test_format_datetime():
    assert format_datetime(TEST_MS) == "2026-04-02 12:30:00"


def test_format_custom():
    assert format_custom(TEST_MS, "%d/%m/%Y") == "02/04/2026"


def test_format_in_timezone():
    result = format_in_timezone(TEST_MS, "Asia/Kolkata")
    assert result == "2026-04-02T18:00:00+05:30"


def test_format_lookback_millis():
    start = TEST_MS - 3600000  # 1 hour before
    assert format_lookback_millis(start, TEST_MS) == "3600000"


def test_to_datetime():
    dt = to_datetime(TEST_MS)
    assert dt.year == 2026
    assert dt.month == 4
    assert dt.day == 2
    assert dt.hour == 12
    assert dt.minute == 30
    assert dt.tzinfo == timezone.utc


def test_from_datetime():
    dt = datetime(2026, 4, 2, 12, 30, 0, tzinfo=timezone.utc)
    assert from_datetime(dt) == TEST_MS


def test_roundtrip():
    dt = to_datetime(TEST_MS)
    assert from_datetime(dt) == TEST_MS
