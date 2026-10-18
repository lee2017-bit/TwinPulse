# H2c — actual Isaac scene-only Build and v1 regression

- Date: 2026-09-26 KST. Source HEAD before this dirty step: `5c42899a95a0bf2422550bd17df7556a92ab3232`.
- Status: **ACTUAL_ISAAC_HEADLESS_TESTED_SCOPE_PASS / H2_OVERALL_PARTIAL**. This is an isolated local Isaac Sim 6.0.1 test, not an interactive viewport review or a live-provider workflow.
- Entry point: `scripts/verify_h2c_site_scene.py`. It creates its own headless Kit process and stage; no user stage, real robot, or paid provider is used.

## What was exercised

The deterministic v2 fixture has a floor and two perpendicular walls forming an L. It also contains an optional robot proposal and a goal inside a wall. The SiteToolPlan keeps that goal at `(2.5, 0.7, 0.0)` rather than silently relocating it. The actual Isaac `build_site_scene` command authors only the reviewed `SceneRevision` geometry: **13 owned prims**, no `/World/TwinPulse/Robot` and no `/World/TwinPulse/Task`. The returned applied revision is `990f00125c1757659764104eed6edd4ef7a109bc5a5d5add4044b2088d0b3efb`; the build fingerprint is `2a8a53e5760f11253bcc454f3d4151cb2e0a2de38f0137d666e30751723108bd`.

- Adapter capability/snapshot advertises `site_scene_build_v2`, permits Build and scene Reset, but not Run. Direct Run and stale-revision Run/Build commands return failed receipts. Scene Reset preserves the geometry, receipt identity and Run block. Repeating the same Build is idempotent.
- An injected failure on the second replacement object restores the prior site geometry, revision, receipt, and unrelated `/ExternalKeep` prim. `compile_site_scene` now preserves the live PhysicsScene prim during v1/v2 replacements so Isaac's SimulationManager does not retain an expired prim reference.
- v2 → v1 uses the existing bridge command and produces **32 prims**. The v1 controller takes **32 physics steps**; Run, Pause, Reset pass. v1 → v2 removes the robot/task again and blocks Run. USD export/reopen retains the site identity. Manual wall transform damage is detected and repaired. A foreign Y-up/cm stage is rejected without changing its unrelated content.
- The existing R2 actual-Isaac suite passes its identity, rollback, stage ownership and off-route/unstable safety gates after the shared compiler change.

## Reproduction and outcome

Set `TWINPULSE_TEST_TMP` to a writable test directory, then run `C:\isaacsim\python.bat -B scripts\verify_h2c_site_scene.py` from the repository root. Require the `H2C_RESULT` JSON marker with `status=PASS` and `provider_calls=0`; do not infer success from a filtered shell pipeline's exit code alone. For v1 safety regression run `C:\isaacsim\python.bat -B scripts\verify_r2_stage_identity.py` and require `R2 SAFETY PASS:`.

During this step, the first Isaac run exposed missing v2 Reset permission. A later run exposed an expired PhysicsScene pointer when switching back to v1 after site replacement. Both defects were corrected and the full acceptance script rerun; the final run printed all five H2C PASS markers and the result JSON. Local H2b integration 5/5, R4 broker/API 6/6 and R5 product API 10/10 also passed. Python compile and whitespace checks are recorded separately in the task result.

## Not proven

No live Nebius v2 schema/API request, actual image grounding or visual-fidelity judgment, interactive Isaac viewport capture, full browser-to-Isaac v2 run, company workstation install, ROS, TurtleBot motor command, commit, or GitHub push. H2b's explicit legacy-record-to-v2 promotion is not a product action yet; an old replay remains v1 without v2 authority. The H2c headless runtime PASS must not be described as completion of those gates.
