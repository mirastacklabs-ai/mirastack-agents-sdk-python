"""Tests for mirastack_sdk.grpc_msgsize — gRPC message-size ceiling."""

from __future__ import annotations

from mirastack_sdk.grpc_msgsize import (
    DEFAULT_BYTES,
    ENV_VAR,
    resolve_max_message_bytes,
)


def test_default_when_unset(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    assert resolve_max_message_bytes() == 67108864
    assert resolve_max_message_bytes() == DEFAULT_BYTES


def test_parsed_when_set(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "8388608")
    assert resolve_max_message_bytes() == 8388608


def test_whitespace_trimmed(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "  16777216  ")
    assert resolve_max_message_bytes() == 16777216


def test_non_numeric_falls_back_without_raising(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "abc")
    assert resolve_max_message_bytes() == DEFAULT_BYTES


def test_zero_falls_back_without_raising(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "0")
    assert resolve_max_message_bytes() == DEFAULT_BYTES


def test_negative_falls_back_without_raising(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "-1")
    assert resolve_max_message_bytes() == DEFAULT_BYTES


def test_empty_string_falls_back(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "")
    assert resolve_max_message_bytes() == DEFAULT_BYTES
