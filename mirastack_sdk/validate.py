"""Quality gate validation for MIRASTACK Agent plugins.

Called by ``serve()`` before the gRPC server starts — a failing gate causes
an immediate ``sys.exit(1)`` with a clear error message so the developer
sees the problem in their terminal.

The same rules are enforced by the engine at registration time
(defense-in-depth), but SDK-side validation gives instant local feedback.
"""

from __future__ import annotations

from mirastack_sdk.plugin import PluginInfo


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
