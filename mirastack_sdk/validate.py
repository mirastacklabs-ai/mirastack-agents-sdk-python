"""Quality gate validation for MIRASTACK Agent plugins.

Called by ``serve()`` before the gRPC server starts — a failing gate causes
an immediate ``sys.exit(1)`` with a clear error message so the developer
sees the problem in their terminal.

The same rules are enforced by the engine at registration time
(defense-in-depth), but SDK-side validation gives instant local feedback.
"""

from __future__ import annotations

import re

from mirastack_sdk.plugin import PluginInfo

_DOMAIN_RE = re.compile(r"^[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*)+$")
_MAX_DOMAIN_LEN = 128
_MAX_USE_CASE_LEN = 256
_MAX_LIST_ITEMS = 64


def _normalize_domain(value: str) -> str:
    return (value or "").strip().lower()


def _validate_domain_list(values: list[str], field: str) -> list[str]:
    if len(values) > _MAX_LIST_ITEMS:
        raise ValueError(f"{field} exceeds max items {_MAX_LIST_ITEMS}")
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        domain = _normalize_domain(value)
        if not domain:
            continue
        if len(domain) > _MAX_DOMAIN_LEN:
            raise ValueError(f"{field} item {domain!r} exceeds max length {_MAX_DOMAIN_LEN}")
        if not _DOMAIN_RE.match(domain):
            raise ValueError(f"{field} item {domain!r} is not namespaced")
        if domain in seen:
            raise ValueError(f"{field} contains duplicate domain {domain!r}")
        seen.add(domain)
        normalized.append(domain)
    normalized.sort()
    return normalized


def _validate_use_cases(values: list[str], field: str) -> list[str]:
    if len(values) > _MAX_LIST_ITEMS:
        raise ValueError(f"{field} exceeds max items {_MAX_LIST_ITEMS}")
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = (value or "").strip()
        if not text:
            continue
        if len(text) > _MAX_USE_CASE_LEN:
            raise ValueError(f"{field} item {text!r} exceeds max length {_MAX_USE_CASE_LEN}")
        if text in seen:
            raise ValueError(f"{field} contains duplicate use case {text!r}")
        seen.add(text)
        normalized.append(text)
    normalized.sort()
    return normalized


def validate_plugin(info: PluginInfo) -> list[str]:
    """Return a list of human-readable quality gate violations.

    An empty list means the plugin passes all gates.
    """
    errs: list[str] = []

    # ── Plugin-level gates ─────────────────────────────────────────────
    if not info.name:
        errs.append("plugin name must not be empty")
    if not info.version:
        errs.append("plugin version must not be empty")
    if not (info.description or "").strip():
        errs.append("plugin description must not be empty")
    if not info.devops_stages:
        errs.append("plugin must declare at least one DevOps stage")
    if not info.actions:
        errs.append("agent must declare at least one action")

    # ── Per-action gates ───────────────────────────────────────────────
    seen_ids: set[str] = set()
    for i, act in enumerate(info.actions):
        if not act.id:
            errs.append(f"action[{i}]: ID must not be empty")
            continue
        if act.id in seen_ids:
            errs.append(f"action[{i}]: duplicate action ID {act.id!r}")
        seen_ids.add(act.id)

        if not (act.description or "").strip():
            errs.append(
                f"action[{i}] ({act.id}): description must not be empty"
            )
        if not act.stages:
            errs.append(
                f"action[{i}] ({act.id}): must declare at least one DevOps stage"
            )
        try:
            schema_version = (act.routing.schema_version or "").strip()
            if not schema_version:
                raise ValueError("routing schema_version is required")
            if schema_version != "mirastack.routing_semantics/v1":
                raise ValueError(
                    f"unsupported routing schema_version {schema_version!r}"
                )
            accepted = _validate_domain_list(
                list(act.routing.accepted_intent_domains),
                "accepted_intent_domains",
            )
            if not accepted:
                raise ValueError(
                    "accepted_intent_domains must contain at least one domain"
                )
            capability = _normalize_domain(act.routing.capability_domain)
            if not capability:
                raise ValueError("capability_domain is required")
            if len(capability) > _MAX_DOMAIN_LEN:
                raise ValueError(
                    f"capability_domain {capability!r} exceeds max length {_MAX_DOMAIN_LEN}"
                )
            if not _DOMAIN_RE.match(capability):
                raise ValueError(
                    f"capability_domain {capability!r} is not namespaced"
                )
            positive = _validate_use_cases(
                list(act.routing.positive_use_cases), "positive_use_cases"
            )
            if not positive:
                raise ValueError(
                    "positive_use_cases must contain at least one use case"
                )
            _validate_use_cases(
                list(act.routing.negative_use_cases), "negative_use_cases"
            )
            _validate_domain_list(
                list(act.routing.signal_domains), "signal_domains"
            )
            _validate_domain_list(
                list(act.routing.backend_domains), "backend_domains"
            )
            _validate_domain_list(
                list(act.routing.entity_types), "entity_types"
            )
        except ValueError as exc:
            errs.append(
                f"action[{i}] ({act.id}): invalid routing semantics: {exc}"
            )

    # ── ConfigParam gates (when declared) ──────────────────────────────
    for i, cp in enumerate(info.config_params):
        if not cp.key:
            errs.append(f"config_param[{i}]: key must not be empty")
            continue
        if not (cp.description or "").strip():
            errs.append(
                f"config_param[{i}] ({cp.key}): description must not be empty"
            )

    return errs
