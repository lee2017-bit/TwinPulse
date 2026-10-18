# Current-goal review and confirmation — 2026-10-06

## Result and boundary

Baseline v1.0.298. The existing REAL chat now has a current-observation goal-review contract, target-choice cards, exact-plan confirmation gates and an independent Stop path. The shared local mission rechecks the approval before its first nonzero output. A reproduced PC qualification-termination race is also corrected.

**C4 remains PARTIAL; whole readiness=false.** The production remote factory does not yet provide idle current localization/preview handoff, and there is no actual exact-plan Isaac route-preview receipt. Physical goal execution stays locked. Robot power alone will not complete these missing implementations. No robot transport, deployment, motors, paid provider, installation, system change, commit/push or new agent was used. Chrome, Isaac runtime and target build were **NOT_RUN in this increment**. Earlier runtime receipts and failures retain their original scope.

## Implemented product paths

1. `current_goal_preview.py` reuses the existing semantic goal resolver and observed-grid planner. Supported goals use the current sensor pose, not a supplied user start or a saved terminal pose. Ambiguous objects produce an explicit target choice; object goals use an exterior approach. Nominal scene obstacles and unknown/occupied observed cells both constrain the route. Physical clearance uses the shared mission profile, not the SIM footprint.
2. A candidate plan binds scene/room, source context, map/alignment revision, pose, transform, footprint, grid semantics and route in a digest. A sample at or beyond 200 ms is rejected. Movement, yaw, semantic grid or source/revision changes invalidate approval; metadata-only cell-counter changes do not. A candidate has `physical_authority=false`.
3. `AutomaticMissionService` accepts current observations only from a server-registered adapter contract. There is no HTTP observation-injection endpoint. Missing production support returns `current_goal_preview_unavailable`; saved evidence is not substituted. The existing map/room prerequisite validation remains in use.
4. `ChatGoalNavigation` and the existing conversation service connect target selection, reviewed route, exact confirmation, cancellation and job observation. Reviews are memory-only, owner-bound and consumed on confirmation attempt; durable conversation reservation precedes external execution. Reload expires execution cards rather than resuming motion. Changed scenes, expired decisions, unavailable qualification and stale observations remain typed failures.
5. The English chat shows a **2D geometric review**, explicitly not live position or an executed Isaac 3D preview. Confirm cannot enable until the registered backend reports a successful exact-plan 3D receipt. Production has no such implementation yet. Independent Stop/Force STOP selects an active goal worker without requiring a successful conversation write.
6. The shared `ObservedMission` checks the approved plan against fresh evidence and recomputed route before consuming approval or producing nonzero output. Existing scan/input/segment, speed, duration, collision and physical-lock conditions are unchanged. An adapter with the remote `run` path rejects an approved preview with `REMOTE_IDLE_PREVIEW_HANDOFF_NOT_IMPLEMENTED`; legacy mission paths are preserved.

## Reproduced termination race

The PC qualification worker could report `FINISHED` while its journal/export/cleanup thread was still busy. The preparation loop then sent another watch input; the controller rejected it as `physical_stopping`, causing a normal completion to be displayed as failure.

The loop now sends no further input after `FINISHED`, `STOPPING`, `FAILED`, `CONNECTION_LOST` or `REJECTED`, waits within the original overall budget for cleanup, and validates the original result. It does not manufacture a pass, replay qualification or loosen a stop criterion. A deterministic delayed-cleanup fixture verifies no post-finish input. This is **not proof that every field Wi-Fi interruption or `INPUT_DEADLINE_EXPIRED` had this cause**.

## Final frozen-source validation

Final Python command used the existing interpreter and module path and selected these suites:

```text
tests.integration.test_current_goal_preview.CurrentGoalPreviewTests
tests.integration.test_chat_goal_navigation.ChatGoalTests
tests.integration.test_chat_conversation.ChatConversationTests
tests.integration.test_simulation_goal.SimulationGoalTests
packages.twinpulse_core.tests.test_observed_mission.ObservedMissionTests
tests.integration.test_automatic_mission_service.AutomaticMissionTests
tests.integration.test_chat_inspection.ChatInspectionTests
tests.integration.test_chat_inspection_visual.CurrentRoomVisualTests
tests.integration.test_robot_source_identity
```

- Python: **110 tests, 142.519 s, PASS**.
- Web: **42 files / 316 tests, 23.69 s, PASS**.
- TypeScript/Vite production build: PASS. Existing bundle-size warning remains a warning, not a runtime acceptance.
- Built JS: `index-PrO8b7Vx.js`, SHA256 `28e5f2d30d623e29344c744b29e8c1c83dc809945c39eaa8531346fb587a6b73`.
- Built CSS: `index-DjLK5Ycj.css`. All three listed build-manifest files matched their recorded hashes.
- Owned test sessions completed; heartbeat remains PAUSED.

New focused coverage: current-grid clearance/unknown rejection, semantic exterior/ambiguous goals, source/pose/yaw/transform/grid invalidation, exact 200 ms boundary, immutable digest, first-output rejection, synthetic closed-loop arrival from two starts and repositioning; authenticated chat/API, missing current adapter, disabled 3D confirmation, saved-state expiry/no replay, durable-write failure, exact one execution using an explicit receipt fixture, independent Stop, typed adapter timeout and delayed qualification cleanup.

The execution fixture reports `OFFLINE_FIXTURE_NO_TRANSPORT`. Its receipt boolean is an explicit test double, **not an Isaac stage/engine receipt or physical acceptance**. Synthetic arrival checks planning/control contracts only. Existing raw files, failed reports and immutable source history were not replaced.

## Earlier failures retained

- First core run: 27 tests, one failure at the 200 ms floating-point boundary. Corrected with a strict conservative comparison; no deadline relaxation.
- First integrated API run: 114 tests with seven errors, including incomplete test storage fixtures and a real missing-storage error escaping the HTTP path. Added explicit fixture storage and typed availability checks.
- Focused follow-up: two failures from treating the existing independent-busy guard as a context manager. Corrected to its actual normal-call contract; follow-up seven tests passed.
- First broad run: 107 tests, 106 passed and one existing qualification failure (`physical_stopping`). Standalone success did not erase the broad failure; the subsequent deterministic cleanup test reproduced and fixed the termination race. Final 110-test run above passed.
- Initial sandbox temporary-file access needed scoped permission for local test subprocess writes. No denied path or WSL service was bypassed.

## Exact remaining sequence

1. **Production current-localization handoff:** an owned, no-motion idle observation lifecycle and robot-local preview/execution handoff; do not revive a terminal pose. Reuse the accepted survey report/full map through checked references rather than relying only on the legacy automatic-map store. This code work can continue with the robot OFF.
2. **Actual exact-plan Isaac 3D demonstration:** display/run the bound route using the current derived room and bind stage, engine, revision and plan digest into a checked receipt. The new 2D review alone must never unlock physical execution. Add actual Web/API/Isaac acceptance before claiming this complete.
3. **Goal journey and C5/C6:** five-second goal transcript summaries, persistent return/target loop with battery/obstacle/torque/Stop policy and no automatic restart after faults, then combined normal/failure/reload acceptance.
4. **Separate target/field qualification:** reviewed ROS/runtime/profile and real current localization, clearance, timing, measured alignment and goal/loop tests under a new scoped on-site approval. Exact pose matching may prove too sensitive to real localization noise; it remains unqualified and must not be silently weakened.

The new contract rejects unsupported or unsafe conditions explicitly. It is not yet the user's completed real-robot demo journey.
