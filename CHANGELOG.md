# Changelog

All notable changes to `mirastack-agents-sdk` (Python) are recorded in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Release Cadence — Lockstep With Go SDK

`mirastack-agents-sdk` (Python) and
[`mirastack-agents-sdk-go`](https://github.com/mirastacklabs-ai/mirastack-agents-sdk-go)
**ship together at matching `MAJOR.MINOR` tags**. Every minor or major bump
in either SDK forces a paired release of the other so plugin authors writing
in either language consume the same engine handshake contract.

Patch (`Z`) versions are independent: a Python-only or Go-only patch fix
(e.g. mypy/ruff lint, build-only fix) MAY ship without bumping the
counterpart SDK as long as the wire contract is unchanged.

When this SDK has no functional change for a paired minor bump, the
release is a *version-alignment* tag — the package is republished with
the matching version number, the CHANGELOG records the alignment, and
the README links to the counterpart's release notes for the actual
feature.

All MIRASTACK agents — Python and Go — MUST be on the latest paired SDK
minor before the engine cuts a release; the engine's CI gate enforces this.

## [1.8.0] — 2026-05-01

This release **realigns the Python SDK with `mirastack-agents-sdk-go v1.8.0`**.
Versions 1.6.x and 1.7.x are intentionally skipped so that future
engineering work tracks a single Go ↔ Python version axis. The Python
SDK previously did not expose `LicenseContext` at all, so the Go-side
breaking rename of `MaxDataSourceTypes` → `MaxIntegrationTypes`
introduced in Go v1.8.0 lands here as a brand-new typed surface
(`LicenseContext`, `LicenseQuotas`) rather than a rename.

### Added
- `LicenseContext` and `LicenseQuotas` dataclasses
  (`mirastack_sdk.LicenseContext`, `mirastack_sdk.LicenseQuotas`)
  mirroring `mirastack-agents-sdk-go/gen/pluginv1`'s shape:
  `active`, `effective_tier`, `issued_tier`, `grace_mode`,
  `expires_at` (epoch ms), `org_id`, `site_id`, `region`,
  `region_kind`, and `quotas` with `max_tenants`,
  `max_integration_types`, `max_agentic_sessions_per_day`.
- `LicenseContext.from_dict` parser. The engine returns `RegisterPlugin`
  and `Heartbeat` responses as JSON; agents that want a typed view of
  the licence snapshot wrap the returned dict with this classmethod.
- `serve()` now logs the engine's licence snapshot once at startup and
  on every heartbeat-driven re-registration so operators can see
  `effective_tier`, `grace_mode`, and `expires_at` in plugin logs
  without changing plugin code.
- The currently-known licence snapshot is exposed on the `Plugin`
  instance as `plugin._engine_license_context` (mirrors Go's
  `LicenseContext` access pattern). Plugins that want to short-circuit
  work the engine would reject can read this attribute.

### Notes
- Python SDK consumers writing new agents SHOULD pin
  `mirastack-agents-sdk>=1.8.0` to opt into the typed `LicenseContext`
  surface and the lockstep policy.

## [1.5.2] — 2026-04

### Fixed
- Removed tracked `__pycache__` directories from the published
  distribution (already in `.gitignore`).

## [1.5.1] — 2026-04

### Fixed
- Added `CacheGetBatch` proto stubs to the hand-written `plugin_pb2.py`
  for mypy compliance.

## [1.5.0] — 2026-04

### Added
- `EngineContext.cache_get_batch` (MGET) for batched cache lookups.
- `EngineContext.call_plugin_with_time_range` so cross-plugin calls
  preserve the ingress anchor time.
- Dedicated `Heartbeat` RPC separate from `RegisterPlugin`.
- gRPC keepalive on both server and `EngineContext` client.
- Multi-tenant `tenant_id` propagation (matches Go SDK v1.6.0 wire
  contract). Set `MIRASTACK_PLUGIN_TENANT_SLUG` (preferred) or
  `MIRASTACK_PLUGIN_TENANT_ID`. The SDK auto-stamps `tenant_id` on
  every outbound gRPC call.

## [1.4.0] — 2026-03

### Added
- Initial production-grade self-registration with retry/backoff and
  Service-address support (`MIRASTACK_PLUGIN_ADVERTISE_ADDR`).
- OpenTelemetry tracing via `init_otel`.

[1.8.0]: https://github.com/mirastacklabs-ai/mirastack-agents-sdk-python/releases/tag/v1.8.0
[1.5.2]: https://github.com/mirastacklabs-ai/mirastack-agents-sdk-python/releases/tag/v1.5.2
[1.5.1]: https://github.com/mirastacklabs-ai/mirastack-agents-sdk-python/releases/tag/v1.5.1
[1.5.0]: https://github.com/mirastacklabs-ai/mirastack-agents-sdk-python/releases/tag/v1.5.0
[1.4.0]: https://github.com/mirastacklabs-ai/mirastack-agents-sdk-python/releases/tag/v1.4.0
