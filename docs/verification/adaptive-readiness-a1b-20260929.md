# Adaptive A1b increment — simulation feature versus current readiness

Date: 2026-09-29 KST. This is an **offline partial A1b implementation**, not runtime or physical acceptance. Robot was reported OFF; no SSH, sensor, motor, deployment, paid provider or Isaac execution occurred.

## Connected product path

- The existing `SimulationSnapshot` wire format remains unchanged. Pure core `evaluate_engine_feature()` uses the current snapshot plus broker-verified connected/session/stage identity to classify `runtime_disconnected`, `runtime_snapshot_missing`, `runtime_identity_stale`, `capability_unavailable`, `runtime_safety_latched`, `runtime_command_unavailable`, or `ready` for existing legacy/site/bedroom preview features. It does not expose a physical-mission feature or grant physical authority.
- The existing command broker now uses the same evaluator for `site_scene_capable()` and site/bedroom Build preflight. Its additive `public_state.engine_readiness` reports the reason to the existing authenticated product-state API; command ownership, leases, revisions, and server-side Build checks remain in force. A missing/old snapshot does not become a capability PASS.
- The bedroom React panel consumes the additive result when present, with its old-snapshot fallback retained. It explains disconnected/stale/missing-feature/safety states. `runtime_command_unavailable` does **not** disable the initial Build button, because that click is how the UI obtains the lease; after acquiring it, the existing bounded fresh-state poll and server checks still decide whether Build runs. A newly added test caught this dependency before closeout.
- The v1 planner's narrow route wording now comes from the same core constants used by `validate_current_controller_route`: z=0, equal y, more than 0.2m and at most 10m positive-X, axis-aligned floor/clear corridor. No arbitrary-XY promise, v2 goal shift, route-validation loosening or planner/provider call was introduced.
- Compatibility: `ENGINE_SCHEMA_VERSION` and snapshot serialization, v1/v2 tool schema digests/revisions, stop logic, and real mission lock are unchanged. Older simulation snapshots with `simulation` plus `build_scene` permission still classify legacy Build as ready; v2 features require their explicit capability strings.

## Verification and preserved failures

- Focused Python engine/broker/API/provider tests: `29 passed, 4 subtests passed`; core full discovery: `173 passed`. New UI stale-stage and pre-lease button tests: `BedroomTwin` 13 passed.
- A sandboxed Web test/build attempt failed to start with Windows `spawn EPERM`. Approved normal-permission Web rerun passed 123 tests/build before the last UI addition; final targeted 13/build and a later frozen-source full [offline verifier run](../../artifacts/runs/20260929-025858/) passed (`TWINPULSE_VERIFY_RESULT=PASS`, core 173, Web 125/125, production build and existing integration groups). The first new integration test collection lacked the provider import path; this harness error was corrected and focused tests then passed.
- Actual Isaac adapter/UI round trip, physics and real robot: **NOT_RUN**. The broker API tests exercise local fake snapshots, not an Isaac runtime. Existing real stop-test FAIL and missing odom/TF/calibration/deployment remain unchanged.

## A1b still open

This increment does not create an automatic ModelProfile probe, a physical calibration readiness classifier, or a mode-by-mode descriptor sourced from a running Isaac adapter. The additive product-state classification is simulation-only. Its real-adapter behavior and the unchanged v1/v2 planner semantics still need actual Isaac evidence before A1b runtime PASS. Next safe offline work should prioritize A2 reusable project persistence and recipe/evidence isolation, without restoring leases, approvals or physical readiness from a saved project.
