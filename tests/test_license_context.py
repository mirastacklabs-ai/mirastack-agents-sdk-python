"""Tests for LicenseContext / LicenseQuotas dataclass parsers.

The Python SDK's ``LicenseContext`` mirrors the canonical Go SDK
``pluginv1.LicenseContext`` (see ``mirastack-agents-sdk-go/gen/pluginv1/types.go``).
These tests pin the JSON wire shape so the two SDKs stay byte-compatible
under the lockstep release policy.
"""

from __future__ import annotations

import dataclasses

from mirastack_sdk.plugin import LicenseContext, LicenseQuotas


class TestLicenseQuotasFromDict:
    """Quotas survive the engine JSON round-trip exactly."""

    def test_full_payload(self) -> None:
        q = LicenseQuotas.from_dict(
            {
                "max_tenants": 50,
                "max_integration_types": 10,
                "max_agentic_sessions_per_day": 200,
            }
        )
        assert q.max_tenants == 50
        assert q.max_integration_types == 10
        assert q.max_agentic_sessions_per_day == 200

    def test_unlimited_sentinel_minus_one_is_preserved(self) -> None:
        q = LicenseQuotas.from_dict(
            {
                "max_tenants": -1,
                "max_integration_types": -1,
                "max_agentic_sessions_per_day": -1,
            }
        )
        assert q.max_tenants == -1
        assert q.max_integration_types == -1
        assert q.max_agentic_sessions_per_day == -1

    def test_omitted_session_quota_defaults_to_zero(self) -> None:
        q = LicenseQuotas.from_dict(
            {"max_tenants": 1, "max_integration_types": 3}
        )
        assert q.max_agentic_sessions_per_day == 0

    def test_none_returns_zero_value_instance(self) -> None:
        q = LicenseQuotas.from_dict(None)
        assert q == LicenseQuotas()

    def test_empty_dict_returns_zero_value_instance(self) -> None:
        q = LicenseQuotas.from_dict({})
        assert q == LicenseQuotas()

    def test_max_data_source_types_is_not_recognised(self) -> None:
        """Engine v1.8.0+ never sends the legacy key — the SDK ignores it.

        This guards against a regression where the rebrand from
        ``max_data_source_types`` to ``max_integration_types`` is silently
        undone in the Python SDK.
        """
        q = LicenseQuotas.from_dict(
            {
                "max_tenants": 1,
                "max_data_source_types": 99,
                "max_integration_types": 7,
            }
        )
        assert q.max_integration_types == 7


class TestLicenseContextFromDict:
    """Engine snapshot parsed into a typed ``LicenseContext``."""

    def test_full_payload_matches_go_sdk_shape(self) -> None:
        raw = {
            "active": True,
            "effective_tier": "pro",
            "issued_tier": "pro",
            "grace_mode": False,
            "expires_at": 1893456000000,
            "org_id": "org-1",
            "site_id": "site-1",
            "region": "us-east-1",
            "region_kind": "public",
            "quotas": {
                "max_tenants": 10,
                "max_integration_types": 5,
                "max_agentic_sessions_per_day": 50,
            },
        }
        ctx = LicenseContext.from_dict(raw)
        assert ctx is not None
        assert ctx.active is True
        assert ctx.effective_tier == "pro"
        assert ctx.issued_tier == "pro"
        assert ctx.grace_mode is False
        assert ctx.expires_at == 1893456000000
        assert ctx.org_id == "org-1"
        assert ctx.site_id == "site-1"
        assert ctx.region == "us-east-1"
        assert ctx.region_kind == "public"
        assert ctx.quotas.max_integration_types == 5

    def test_grace_mode_after_expiry(self) -> None:
        raw = {
            "active": True,
            "effective_tier": "neo",
            "issued_tier": "pro",
            "grace_mode": True,
            "expires_at": 0,
            "quotas": {"max_tenants": 1, "max_integration_types": 3},
        }
        ctx = LicenseContext.from_dict(raw)
        assert ctx is not None
        assert ctx.grace_mode is True
        assert ctx.effective_tier == "neo"
        assert ctx.issued_tier == "pro"

    def test_none_returns_none(self) -> None:
        assert LicenseContext.from_dict(None) is None

    def test_empty_dict_yields_zero_value_context(self) -> None:
        ctx = LicenseContext.from_dict({})
        assert ctx is not None
        assert ctx.active is False
        assert ctx.effective_tier == ""
        assert ctx.quotas == LicenseQuotas()

    def test_round_trip_via_asdict_preserves_shape(self) -> None:
        """``dataclasses.asdict`` of a parsed snapshot equals the input dict."""
        raw = {
            "active": True,
            "effective_tier": "pro",
            "issued_tier": "pro",
            "grace_mode": False,
            "expires_at": 1893456000000,
            "org_id": "org-1",
            "site_id": "site-1",
            "region": "us-east-1",
            "region_kind": "public",
            "quotas": {
                "max_tenants": 10,
                "max_integration_types": 5,
                "max_agentic_sessions_per_day": 50,
            },
        }
        ctx = LicenseContext.from_dict(raw)
        assert ctx is not None
        assert dataclasses.asdict(ctx) == raw
