"""Tenant identifier utilities for MIRASTACK plugins.

Provides :func:`id_from_slug` — a helper that derives the canonical UUID5
tenant identifier from a human-readable slug without requiring a live engine
connection.

The derivation MUST be byte-for-byte identical to the engine's
``internal/tenants/IDFromSlug`` in Go, so the same namespace UUID and
normalisation (lower-case + strip) are applied.
"""

from __future__ import annotations

import uuid

# Namespace UUID — frozen forever. MUST match the engine's nameSpaceTenant
# constant in internal/tenants/id.go. Derived from:
#   uuid.uuid5(uuid.NAMESPACE_URL, "https://mirastack.ai/ns/tenants/v1")
_NAMESPACE_TENANT = uuid.UUID("f9f3a4d4-2c64-5b9e-9e25-8a8b6f6f6f6f")


def id_from_slug(slug: str) -> str:
    """Derive the canonical UUID5 tenant identifier for *slug*.

    The slug is normalised (lower-cased, stripped) before hashing so that
    ``id_from_slug("ACME")`` and ``id_from_slug("acme")`` always produce the
    same result — matching the engine's behaviour.

    Returns the 36-character UUID string
    (e.g. ``"3a7b8f00-1234-5678-abcd-..."``) that the engine uses as the
    authoritative tenant identifier in every gRPC message.
    """
    normalised = slug.strip().lower()
    return str(uuid.uuid5(_NAMESPACE_TENANT, "tenant:" + normalised))
