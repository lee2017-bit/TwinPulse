# R2 stage identity and runtime safety verification

- Date: 2026-09-16 KST
- Scope: `TWINPULSE_APP_MIGRATION_PLAYBOOK.md` Step 2 only
- Result: **PASS on local Isaac Sim 6.0.1 headless/CPU physics**
- Excluded: paid provider calls, visible UI review, R3 app service/API, GitHub push, physical robot control

## Failure reproduced before the fix

The dedicated actual-Isaac regression built fixture A, then created a fresh `SceneCompiler` and applied fixture B with the same `scene.id` but a changed `rack_north` position and height. Before the fix, the authored rack scale remained `(2.0, 0.6000000238, 1.5)` instead of changing to 1.8 m. This reproduced F4: scene ID alone was incorrectly treated as proof that the stage matched the requested content.

After the fix the same test authored `(2.0, 0.6000000238, 1.7999999523)`. The assertion uses a tolerance only for USD float representation; the build fingerprint does not round dimensions.

## Implemented contract

- A build fingerprint binds the canonical expanded bundle digest, compiler version, asset-catalog version, resolved RobotProfile schema and full resolved profile digest.
- `/World/TwinPulse` receives explicit ownership, fingerprint, compiler/catalog version and authored-static-content digest only after the actual USD content validates.
- A typed in-memory `StageBuildReceipt` is issued only after metadata and stage content match. A failed replacement restores the previous receipt as well as the previous bundle and geometry.
- Identical content on the current stage is idempotent. A changed bundle, corrupt fingerprint, missing owned prim, modified geometry or damaged gravity metadata is revalidated and rebuilt/repaired.
- Replacement snapshots only TwinPulse-owned mutable paths. A successful transaction preserves the live PhysicsScene prim; a failed transaction distinguishes complete rollback from rollback failure and preserves external prims.
- Empty/dedicated stages are made Z-up and meter-based. Incompatible stages containing user content, an external PhysicsScene, or an unowned `/World/TwinPulse` are rejected without changing units or adopting/removing the content.
- Runtime command validity is bound to the active stage and verified authored content. Stage close/change invalidates the compiler binding, robot/controller cache and physics subscription.
- `off_route` and `unstable` are independent safety latches. Pause does not clear them, Run is refused, and only a successful Reset against the matching stage clears the latch.

## Actual Isaac acceptance

`C:\isaacsim\python.bat -B scripts\verify_r2_stage_identity.py` passed all of these groups:

1. same scene ID with changed rack dimensions and position;
2. repeat-build prim-count/fingerprint idempotence;
3. manual geometry damage, missing prim, corrupt fingerprint and damaged PhysicsScene repair;
4. intentional mid-replacement failure with previous geometry, identity, bundle, receipt and external prim preserved;
5. new stage, exported/reopened stage, Z-up/meters, incompatible user stage and foreign owned-path protection;
6. off-route and tilt latch, Pause-to-Run bypass rejection, Reset gate and stage-change invalidation.

The general Isaac regression `scripts\verify_m1_extension.py` also passed:

- Extension lifecycle/shutdown: 3/3;
- short Run/Pause/Reset episodes: 3/3;
- generated bundle, no sample fallback and failed replacement preservation: PASS;
- 18 x 12 m mesh floor and 6.9 m long route: PASS;
- final goal error 0.049289 m, maximum cross-track error 0.004352 m, maximum roll 0.076246 degrees, maximum pitch 0.066773 degrees, collision samples 0;
- two driven wheels plus two passive support wheels remained unchanged.

Pure regressions also passed:

- R1 integration workflow: 9/9;
- Core: 24/24;
- Provider: 13/13;
- compileall and `git diff --check`.

The final combined `scripts\verify_twinpulse.ps1` run returned `TWINPULSE_VERIFY_RESULT=PASS`; its machine artifacts are under the git-ignored `artifacts/runs/20260916-125318/` directory. MinimalRendering intentionally did not produce a screenshot.

## Limits and next gate

This proves the tested local stage-identity, rollback and runtime-safety contracts. It does not prove arbitrary generated-scene quality, general navigation, UI/bridge behavior, a fresh paid multimodal result, or physical-robot safety. R3 remains unstarted and requires a separate user request.
