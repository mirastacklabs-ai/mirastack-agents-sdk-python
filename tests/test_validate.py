"""Tests for mirastack_sdk.validate (Agent quality gates)."""

from __future__ import annotations

import pytest

from mirastack_sdk.plugin import (
    Action,
    ConfigParam,
    DevOpsStage,
    Permission,
    PluginInfo,
)
from mirastack_sdk.validate import validate_plugin


# ── Helpers ────────────────────────────────────────────────────────────────

def _valid_info() -> PluginInfo:
    """Return a fully-populated PluginInfo that passes all quality gates."""
    return PluginInfo(
        name="query_vmetrics",
        version="1.0.0",
        description="Query VictoriaMetrics TSDB for instant and range PromQL queries",
        devops_stages=[DevOpsStage.OBSERVE],
        actions=[
            Action(
                id="query_instant",
                description="Run an instant PromQL query",
                permission=Permission.READ,
                stages=[DevOpsStage.OBSERVE],
            ),
        ],
    )


# ── Valid cases ────────────────────────────────────────────────────────────

class TestValidAgent:
    def test_minimal_valid(self):
        assert validate_plugin(_valid_info()) == []

    def test_multiple_actions(self):
        info = _valid_info()
        info.actions.append(
            Action(
                id="query_range",
                description="Run a range PromQL query",
                permission=Permission.READ,
                stages=[DevOpsStage.OBSERVE],
            )
        )
        assert validate_plugin(info) == []

    def test_with_config_params(self):
        info = _valid_info()
        info.config_params = [
            ConfigParam(key="url", description="VictoriaMetrics URL"),
            ConfigParam(key="api_key", description="API key for auth", is_secret=True),
        ]
        assert validate_plugin(info) == []


# ── Plugin-level gates ─────────────────────────────────────────────────────

class TestPluginLevelGates:
    def test_empty_name(self):
        info = _valid_info()
        info.name = ""
        errs = validate_plugin(info)
        assert any("plugin name" in e for e in errs)

    def test_empty_version(self):
        info = _valid_info()
        info.version = ""
        errs = validate_plugin(info)
        assert any("plugin version" in e for e in errs)

    def test_empty_description(self):
        info = _valid_info()
        info.description = ""
        errs = validate_plugin(info)
        assert any("plugin description" in e for e in errs)

    def test_whitespace_description(self):
        info = _valid_info()
        info.description = "   "
        errs = validate_plugin(info)
        assert any("plugin description" in e for e in errs)

    def test_no_devops_stages(self):
        info = _valid_info()
        info.devops_stages = []
        errs = validate_plugin(info)
        assert any("at least one DevOps stage" in e for e in errs)

    def test_no_actions(self):
        info = _valid_info()
        info.actions = []
        errs = validate_plugin(info)
        assert any("at least one action" in e for e in errs)


# ── Per-action gates ──────────────────────────────────────────────────────

class TestActionGates:
    def test_missing_id(self):
        info = _valid_info()
        info.actions = [Action(id="", description="Something", stages=[DevOpsStage.OBSERVE])]
        errs = validate_plugin(info)
        assert any("ID must not be empty" in e for e in errs)

    def test_duplicate_id(self):
        info = _valid_info()
        info.actions = [
            Action(id="query", description="A", stages=[DevOpsStage.OBSERVE]),
            Action(id="query", description="B", stages=[DevOpsStage.OBSERVE]),
        ]
        errs = validate_plugin(info)
        assert any("duplicate action ID" in e for e in errs)

    def test_missing_description(self):
        info = _valid_info()
        info.actions = [Action(id="query_instant", description="", stages=[DevOpsStage.OBSERVE])]
        errs = validate_plugin(info)
        assert any("description must not be empty" in e for e in errs)

    def test_missing_stages(self):
        info = _valid_info()
        info.actions = [Action(id="query_instant", description="Query metrics", stages=[])]
        errs = validate_plugin(info)
        assert any("at least one DevOps stage" in e for e in errs)


# ── ConfigParam gates ─────────────────────────────────────────────────────

class TestConfigParamGates:
    def test_empty_key(self):
        info = _valid_info()
        info.config_params = [ConfigParam(key="", description="something")]
        errs = validate_plugin(info)
        assert any("key must not be empty" in e for e in errs)

    def test_empty_description(self):
        info = _valid_info()
        info.config_params = [ConfigParam(key="url", description="")]
        errs = validate_plugin(info)
        assert any("config_param[0] (url): description must not be empty" in e for e in errs)


# ── Multiple errors ───────────────────────────────────────────────────────

class TestMultipleErrors:
    def test_collects_all_violations(self):
        info = PluginInfo(name="", version="")
        errs = validate_plugin(info)
        assert len(errs) >= 4  # name, version, description, stages, actions
        assert any("plugin name" in e for e in errs)
        assert any("plugin version" in e for e in errs)
        assert any("description" in e for e in errs)
        assert any("action" in e for e in errs)
