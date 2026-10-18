# Exact reviewed goal demonstration in Isaac

Baseline v1.0.301 connects an explicit REAL chat goal request to the existing broker and Isaac Burger PhysX execution. It carries the reviewed room-space waypoints unchanged, waits for observed arrival, pauses the owned SIM run and issues an engine/stage/scene/run-bound completion receipt. Polling, restart and restored conversation cards never start a demonstration.

**C4 remains PARTIAL and whole readiness=false.** The exact remote idle-to-driving handoff is still unimplemented, so physical Confirm stays disabled even after a successful Isaac demonstration. This increment uses synthetic sensor evidence and actual Isaac physics, not measured room reconstruction, live localization or physical travel. Actual Chrome/UI journey and target build were NOT_RUN. Robot transport, deployment, paid calls, installs, system changes, commit/push and new agents were zero.

## Product connection

1. `goal_simulation.py` derives a SIM-only execution plan from the exact current-goal review. Scene, source-review digest, complete route, reviewed start/yaw and fixed Burger asset hashes are retained. It does not call a second planner or replace the approved route with a similar one. The additive schema leaves existing `site-simulation-1.0` plans unchanged. SIM speed remains the existing .15 m/s and .6 rad/s; the nested physical candidate stays .03 m/s and .20 rad/s.
2. `GoalDemonstration` owns one bounded thread, existing product lease and broker operations. Explicit goal preparation starts Build, then Run only after the correct Build receipt and applied revision. A Run receipt alone is not completion. Successful live PhysX arrival must be followed by an acknowledged pause and matching frozen arrival observation. Scene/engine/stage/lease changes, runtime faults, timeout, cancellation or missing telemetry reject completion.
3. The in-memory receipt binds review/simulation IDs, project, engine, stage, room revision, Build/Run/Pause command IDs, terminal snapshot sequence/position, route SHA and asset hashes. It has `physical_authority=false`. Reset, stage replacement, another run, room edits, changed frozen pose or lost lease invalidate its current applicability. A saved checksum or browser checkbox cannot manufacture this receipt. No approval is restored on process restart.
4. The existing API constructs this service for production `ChatGoalNavigation`. Its completed receipt takes precedence over the legacy injected adapter boolean used by offline tests. A separate `supports_exact_goal_handoff` gate remains false in the production remote factory; this increment cannot unlock real driving.
5. Chat reports preparation/running/completion/failure, with an English progress indicator, separate primary and cleanup errors and the existing error banner. The existing authenticated viewport displays the Isaac stage; a review line is authored only below `/World/TwinPulse/Presentation/GoalRoutePreview`, with a historical-start/no-authority annotation. The 2D view remains a candidate review, not a live physical pose.
6. Cancel and independent Stop also cancel an owned active demonstration. Queued commands are cancelled; a claimed Run is observed within a bounded cleanup budget and only its matching SIM run may be paused. No Run retry, lease renewal, unrelated-stage write or physical command is issued by cleanup. Unconfirmed cleanup remains a separate failure. API shutdown closes the owned worker.

## Actual Isaac result

The final [runtime result](../../artifacts/runs/goal-demonstration-isaac-20261006-r4/verification.json) and [saved stage](../../artifacts/runs/goal-demonstration-isaac-20261006-r4/goal-demonstration-stage.usda) are from the existing `C:/isaacsim/python.bat`, a new owned headless process and the actual production runtime/broker/demonstration service. Input evidence and room are explicit test fixtures. No robot adapter or network transport was used.

| Goal from reviewed start 0 and minus 1.8 m | Observed terminal XY m | Physics steps | Observed poses | Receipt |
| --- | --- | --- | --- | --- |
| 0.30 and minus 1.8 m | 0.2605345 and minus 1.8000126 | 205 | 207 | COMPLETED after Pause |
| 0 and minus 1.35 m | 0.0021051 and minus 1.3895705 | 487 | 492 | COMPLETED after Pause |

Both runs use exactly one Build, Run and Pause, preserve every reviewed waypoint and original review, and verify the referenced Burger articulation through actual PhysX observations. Completion uses the existing SIM tolerance of .04 m, not exact-coordinate equality or physical acceptance. Their service elapsed times were 4.125 s and 8.657 s. Replacing the engine stage invalidates the second receipt. The unrelated `/ExternalKeep` marker remains unchanged.

Nine runtime/source hashes in the result match the final source. Actual Chrome interaction, embedded-viewer presentation QA, combined real-localization/Isaac/Confirm and live robot paths remain unaccepted. Existing earlier saved-room/viewport receipts retain their original scope.

## Final regression

Final Python selection, using the existing bundled interpreter, `-B`, the existing repository module paths and explicit classes:

```text
tests.integration.test_goal_demonstration.GoalDemonstrationTests
tests.integration.test_site_simulation.SiteSimulationTests
tests.integration.test_chat_goal_navigation.ChatGoalTests
tests.integration.test_current_goal_preview.CurrentGoalPreviewTests
tests.integration.test_chat_conversation.ChatConversationTests
tests.integration.test_chat_inspection_visual.CurrentRoomVisualTests
tests.integration.test_automatic_mission_service.AutomaticMissionTests
tests.integration.test_robot_source_identity
```

- Python: **82 tests, 117.593 s, PASS**. New tests cover unchanged route projection/digests, no completion from admission, foreign owner/project, capability/room/engine change, cancellation/fault/timeout and production chat failure with no boolean receipt bypass or polling retry. Related legacy paths remain covered.
- Web: **42 files, 318 tests, 23.80 s, PASS**. The attempted two-file pnpm invocation ran the entire existing suite; 318 is the full-suite count, not 318 new tests.
- TypeScript/Vite production build: PASS. JS `index-BrigQ2lQ.js` SHA256 `6a5f4d64868da51bae28f22a89c465636853cf6e691c7d8a14f584bd31dfc63b`. All three build-manifest entries match. The existing over-500-kB bundle warning remains.
- `git diff --check`: PASS for tracked changes, with existing CRLF warnings. Untracked source is additionally covered by the executed tests and runtime hashes; the tracked diff is not a whole-repository audit.

All owned test processes completed. Existing dirty changes, original raw data, prior failures, v1/v2 and older mission contracts, scan200ms/input250ms/segment50ms/.03m/s/.20rad/s/45s and physical mission locks were preserved. No robot deployment occurred. The existing heartbeat remains PAUSED.

## Failures retained and corrected

- First Python command: 15 tests, 11 PASS and four setup errors because the new snapshot fixture omitted required `safety_reason`. The fixture was corrected; subsequent focused 15 passed.
- First chat/current-goal command: 20 tests, 12 PASS and eight failures from a real missing string-concatenation operator in the new chat explanation. Corrected without changing approval policy; focused combined 35 then passed.
- [Isaac first attempt](../../artifacts/runs/goal-demonstration-isaac-20261006-r1/verification.json): first run completed, second Run failed. The primary cause was hidden by truncating an entire receipt starting with long identity fields. Command failures now prioritize error code and message. The failure record is not replaced.
- [Isaac second attempt](../../artifacts/runs/goal-demonstration-isaac-20261006-r2/verification.json): first run completed, second Run failed with `SIM_ROBOT_PATH_ALREADY_EXISTS`. The same-scene compiler fast path preserved the previous SimBurger while Build cleared its Python plan. Runtime Build now removes only its recognized prior owned SIM articulation after successful compilation. Foreign prims are not removed. Constant curve-width interpolation also fixes the initial route-line warning.
- The third runtime passed its then-current source. The fourth is the final-source acceptance above. Intermediate passes are not substituted for final source bindings.
- Isaac still reports Fabric value-extraction and tensor-view invalidation warnings during replacement of the old owned articulation. Both final runs reached observed arrival and paused; those warnings are not claimed eliminated.

## Exact remaining work

1. Implement additive, full-reference, exact approved-plan idle-to-driving transfer through the existing PC/native worker. Match owner, current qualification, source context, reference and scene/route digest; fresh robot evidence and first nonzero-output validation remain mandatory. The current production factory still rejects `SURVEY_REFERENCE_REMOTE_FULL_HANDOFF_REQUIRED` and the service retains `REMOTE_IDLE_PREVIEW_HANDOFF_NOT_IMPLEMENTED`. Do not advertise handoff support until implemented and tested.
2. Validate the combined current-localization, chat, actual embedded Isaac preview, single Confirm and robot-local execution journey. The current exact pose-binding policy is still unqualified for real localization noise and the idle worker's 45-second lifetime. No tolerance/deadline is silently relaxed, and a receipt is not permission to reuse an old pose. This code work does not require robot power.
3. Connect five-second goal summaries, persistent bounded return/target legs and C5/C6 normal/fault/reload integration acceptance. Stop, battery, scan loss, obstacle/torque and no-restart rules remain mandatory.
4. Separately qualify the reviewed target binary/profile and real clearance, timing, alignment, travel and loop under a fresh on-site scope. Powering on alone is not a guarantee of the full demo.
