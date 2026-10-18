# TwinPulse v2 room simulation implementation and pending UI acceptance

## Natural language SIM goal acceptance

Baseline v1.0.286 connects supported offline chat navigation to the existing ProductWorkflow, current v2 scene, bounded planner, registered SIM plan and Run/Stop path. Final actual10 accepts this increment, not the full C2 generation journey or a physical demo. Earlier sections are source-specific history.

### Product behavior

Supported examples are `Go to the bed`, `Go to x=-0.3 y=-0.25` and `Go from x=0 y=-2 to the bed`. These use bounded offline rules, not an LLM call or arbitrary-language understanding. Unsupported targets, incomplete coordinates, missing starts and inaccessible goals record precise reasons without guessing a destination. Korean furniture/Stop input aliases live separately from the English interface.

Targets bind to current object IDs and group furniture collision parts. Sixteen exterior approaches are checked with the unchanged .10 m grid/.22 m clearance SIM planner; the shortest feasible candidate among that bounded set is selected, not a globally optimal path. Duplicate generic names produce an inline choice/Cancel card. Selection recomputes against the exact current scene and start; changed scenes reject old choices without generation, Build or movement.

Initial starts require explicit coordinates or validated saved Burger SIM placement. Later goals use connected current-scene idle PhysX pose; unavailable telemetry, safety latches, movement or disconnection reject planning instead of falling back to old placement. Runtime also checks actual start pose before Run. Saved placement remains illustrative, not measured localization. v1/v2 serialization and real guards are unchanged.

Request/choice/plan/error history is durable and idempotent, with additive defaults for older conversation-1.0 files. Only an acknowledged user action supplies a fresh executable Web preview. Run acknowledgement consumes that preview, including read-only recovery after response loss. Polling, restored history and reload never rearm or automatically execute it.

The top-down review shows dashed amber planning separately from teal SIM observations; the right pane is still the real Isaac 3D render. Explicit chat `Stop simulation` immediately invokes the same SIM pause path independently of journal delivery. Restored Stop text does not execute; the journal warns that its message is not proof of stopping. REAL conversation cannot substitute a SIM mission or invoke this SIM Stop method.

### Final evidence

- `scripts/verify_site_simulation.py artifacts/c2-site-simulation-20261005-10 --browser`: built React, real local API and installed Isaac PASS. Synthetic saved room recipe/existing Burger PhysX; provider calls=0, robot connections=0. Initial chat coordinate goal reached distance 0.0396309126 m at simulation time 11.7167 s. Subsequent bed exterior goal approximately (0.12,-0.2996), planned from current SIM pose, reached distance 0.0396012303 m at 8.15 s. These are simulator observations, not physical room measurements.
- The same browser checks blocked-goal reason/Run lock, no automatic Run after preview, live 3D/task/asset, Twin collapse with Stop available, explicit chat Stop and repeated unchanged paused pose, reload without restored approval, 390-pixel layout without horizontal overflow, and zero browser page errors. Final object-arrival/mobile screenshots were visually inspected. Legend contrast, rounded display coordinates (exact execution coordinates retained) and SIM header were corrected. A 6.8 FPS displayed snapshot is not sustained performance acceptance.
- Final `result.json`/`browser.json`: all **19 source/3 Web hashes match** current files. Host PASS; supervisor `stopped`, backend/engine `not_started` and null PIDs after cleanup. No test-owned processes remain.
- Selected Python: `python -m unittest tests.integration.test_simulation_goal tests.integration.test_site_simulation tests.integration.test_chat_conversation tests.integration.test_h2b2_site_review`: **77 PASS**. Covers coordinate validity, exterior/grouped targets, duplicate clarification, exact scene recheck, live pose override/loss, unchanged scene/physical authority, REAL rejection, restored history, idempotency and journal-only Stop. A real local API fixture with two beds produces a three-choice card, selects the second exact object and registers its route without Build/generation/movement. This is not actual Isaac multi-choice UI acceptance.
- Final Web: **37 files/286 PASS**, including acknowledged chat preview without auto Run, consumption/no rearming from polling and explicit imperative Stop without mount execution, plus previous readiness/unknown-delivery gates. TypeScript/build PASS; JS538.59kB/gzip158.65kB, existing >500kB warning remains.

### Corrections and remaining acceptance

Duplicate-kind regressions reproduced an implicit choice and prefix grouping collision, both fixed. English-copy regression found input aliases in a React screen file; they moved to the existing multilingual intent module without weakening the check. Early test attempts also had temporary-file sandbox permission, wrong module name and missing mandatory fixture-field errors. Final related suites were rerun completely; these fixture/execution corrections are not physical evidence. Actual07–09 intermediate PASS and older failures remain preserved; only actual10 certifies the final combined source/build.

**C1/C2 PARTIAL; whole readiness=false.** Accepted: supported offline chat goal → current-scene route review → explicit SIM Run/PhysX arrival → chat/button Stop/reload boundaries. Remaining: arbitrary LLM goal interpretation, generic supported asset selection, fresh photo/text → Q1 → generation → Build/Run journey, staging/checklist/repair/project-switch gaps, actual runtime timeout/unstable-pose/scene-change/reset faults and actual Web/Isaac multi-object choice. Next is the full generation journey and its prerequisite/failure acceptance; robot power is unnecessary.

C3–C6 REAL qualification/survey/correction/route confirmation/five-second summaries/TaskLoop remain separate. Raw/failures, real-photo fit failures, measured profile/target gaps, physical stop/scan200ms/input250ms/segment50ms/.03m/s/.20rad/s/45s and default physical lock are preserved. No robot SSH/serial/sensor/motor/power/deployment, paid call, new installation, commit/push or new agent. Heartbeat stays PAUSED.

## Current result after readiness corrections

Baseline v1.0.285: the previously failing explicit-coordinate chat SIM flow now passes on the final source and Web build. This does not complete C2's natural-language or full generation journey. The v284 checkpoint below remains failure history, not the current result.

The new card regression reproduced the race: Build returned a successful receipt while its engine snapshot still described the old scene, and the UI sent Run prematurely. Preparation now waits for a connected engine, owned lease, the exact applied revision, idle `built / paused / completed` state, SIM capability and no safety latch. The broker, serialization and physical thresholds were not weakened. Closing preparation prevents a later Run.

Run transmission is bounded to 15 seconds; timeout means delivery unknown, not a rejected or repeatable command. Read-only receipt observation has one request in flight and a 45-second budget, then offers an explicit read-only check. It never resubmits Run. Stop remains separate from receipt observation. These failure behaviors are component/API regressions, not deliberately injected failures in the real Isaac runtime.

Actual screen inspection also identified and corrected missing SIM task/asset status and a dismissed error still displayed as active. Current engine safety failures now show their original reason even when pose telemetry is unavailable; dismissed issues remain in collapsed history. Coordinate labels use readable chat colors. These display corrections do not grant movement authority.

### Final executed evidence

- Git base HEAD `5c42899a95a0bf2422550bd17df7556a92ab3232`, plus pre-existing dirty work preserved. No commit or push.
- `scripts/verify_site_simulation.py artifacts/c2-site-simulation-20261005-06 --browser`: actual installed Isaac, built React and real local API PASS. One explicit Run prepares the current v2 room and drives the existing Burger through PhysX. Final observed goal distance is 0.0396297132 m at simulation time 11.8667 s. This is synthetic saved-room input, not a new photo interpretation or physical calibration.
- The same actual browser run checks blocked-goal rejection, live render during movement, current task/asset display, viewer collapse with Stop available, return-route Stop and repeated unchanged pose, paused reload without automatic Run, and 390-pixel mobile layout without horizontal overflow. No browser page errors. Screenshots: `actual-sim-running.png`, `actual-sim-arrived.png`, `actual-sim-mobile.png` in that directory; visually inspected. One running screenshot reports reduced frame rate at 4.9 FPS; this run is not a fresh acceptance of a guaranteed 5 FPS performance target.
- Final `result.json` and `browser.json` contain observations and checks. All fourteen recorded product/verifier source hashes and three Web build hashes match the current files. Host result PASS; supervisor state `stopped`, both owned components `not_started` after cleanup. No test-owned processes remain.
- Final Web regression `pnpm test`: 37 files, 284 tests PASS. Fourteen additions over v284 cover preparation ordering/idle/safety/closure, lost Run response, definite rejection, bounded receipt lookup/read-only recovery, independent Stop, transmission fetch/body timeout, current/stale SIM task display and missing-telemetry safety popup. Tests were added before their fixes and reproduced the corresponding defects.
- Selected Python regression remains 64 PASS: `python -m unittest tests.integration.test_site_simulation tests.integration.test_h2b2_site_review tests.integration.test_chat_conversation -q` executed this turn. No backend/runtime code was changed after it.
- Final `pnpm build`: TypeScript and build PASS; JS 535.29 kB / gzip 157.44 kB. The existing >500 kB bundle warning remains.
- Actual runs 04 and 05 also passed their respective intermediate builds. Run03's `simulation_not_ready` failure and run01's verifier lease error remain intact; later PASS is not retroactive proof of those builds.

### Remaining product work and authority

C1/C2 remain PARTIAL and whole readiness=false. The newly accepted boundary is **explicit-coordinate route preview → current-room preparation → actual Burger Physics Run/arrival → Stop/reload**. Natural-language goals and route visualization, generic supported asset selection, the complete photo/text → SIM question → generation → Run journey, C1 staging/checklist/repair/project-switch gaps, actual runtime timeout/unstable-pose/scene-change/reset fault acceptance, and C3–C6 REAL features remain. The next product implementation is natural-language SIM goals and route review in the existing chat, not another physical test. No robot power is needed for it.

Robot connections, paid provider calls, installation, deployment and new agents were zero; heartbeat remains PAUSED. Write-page guidance influenced the record by separating current acceptance, historical failure, component failure tests and actual runtime evidence. Existing room/raw originals, physical guards and v1/v2 contracts were preserved. A rollback must remove only this turn's UI/API changes and new regressions while preserving pre-existing dirty work; no destructive repository reset is appropriate.

## Previous implementation checkpoint

The SIM execution path now connects the existing v2 room, fixed local Burger asset, bounded path planner, command broker and actual Isaac PhysX. This is a partial implementation checkpoint, not a completed demo or final UI acceptance. Work was interrupted by the user's model-capacity question after the first actual Web acceptance failed.

## Implemented scope

- Additive `site-simulation-1.0` plans bind the exact scene revision, nine local asset hashes, explicit start/goal/yaw, deterministic route and SIM-only limits. v1/v2 serialization and physical guards are unchanged. Ordinary scene-only Run remains forbidden.
- ProductWorkflow validates the current draft; broker checks registered plan, capability, current applied revision, idle state, lease and absence of a safety latch. Duplicate requests return their original operation. Owned request lookup supports response-loss diagnosis without execution.
- Isaac references the existing Burger `physx` variant under `/World/TwinPulse/SimBurger`, drives its real wheel joints and reads live PhysX pose. It checks arrival, tilt, progress, bounded time and scene identity. Stop zeros wheel targets and pauses; reset removes the SIM robot. No physical robot connection is involved.
- A SIM route card in the existing chat provides explicit coordinate preview, same-scene preparation, Run and Stop. The card is not a natural-language goal resolver. Initial coordinates are user-entered; fresh SIM telemetry supplies later starts. REAL conversation cannot execute this binding.

## Executed evidence

| Evidence | Result and limitation |
| --- | --- |
| `artifacts/c2-site-simulation-20261005-01/result.json` | FAIL. Test runner failed to renew the unchanged three-second lease during preparation. Retained, not overwritten. |
| `artifacts/c2-site-simulation-20261005-02/result.json` | Actual owned installed Isaac PASS on the source hashes recorded there. Synthetic saved photo-room recipe; provider calls and robot connections zero. Existing Burger rotated and moved from approximately (-0.3,-1.2) toward (-0.3,-0.25); final distance 0.03963193 m, simulation time 11.6 s. Duplicate Run returned the same command. Return-route Stop was acknowledged; repeated live poses after pause were equal; an embedded-viewer frame existed for the same revision. This precedes the final UI/runtime refinements and does not certify their final combined build. |
| Selected Python regression | `python -m unittest tests.integration.test_site_simulation tests.integration.test_h2b2_site_review tests.integration.test_chat_conversation -q`: 64 tests PASS. Includes ten new SIM tests; no actual-engine claim from unit tests. |
| Web regression | `pnpm test`: 36 files, 270 tests PASS. These are existing regressions, not new SIM card acceptance. |
| Web build | PASS, JS 533.62 kB / gzip 156.93 kB; existing >500 kB warning remains. |
| `artifacts/c2-site-simulation-20261005-03/result.json` and `browser.json` | Actual final Web/API/Isaac FAIL. Blocked goal surfaced an error and kept Run disabled. On the valid route, Build succeeded but Run was rejected with `simulation_not_ready`; the browser never observed Physics running. The screenshot confirms the reason is visible. Stop/mobile/reload parts of this attempt were therefore NOT_RUN, not PASS. |

Installed runtime is the existing local Isaac 6.0.1 RC. The official [wheeled robot API](https://docs.isaacsim.omniverse.nvidia.com/6.0.0/py/source/extensions/isaacsim.robot.experimental.wheeled_robots/docs/index.html) documents differential-controller wheel targets and articulation actions; the installed asset's USD supplies nominal wheel radius .033 m, track .160 m, wheel joint names and articulation path. These are simulation asset parameters, not measured physical calibration. Source assets are not modified.

## Immediate next fix and acceptance

The Web preparation waits for a successful Build receipt, but its readiness loop does not also require the latest engine snapshot's `applied_revision` to equal the scene revision. A receipt can arrive before that snapshot. The observed rejection is consistent with this race, but the exact predicate has not yet been isolated. Fix and regression-test the receipt-before-snapshot ordering; do not weaken broker readiness. Then rerun `scripts/verify_site_simulation.py` into a fresh artifact directory with `--browser`, and inspect all recorded snapshots and actual screenshots. Add SIM card component tests for delayed snapshots, no automatic Run, lost response and Stop. Also verify timeout/pose-invalid/scene-change/reset handling in the final actual runtime rather than claiming them from code alone.

Remaining C2 product work includes natural-language target interpretation, route visualization/selection, generic simulation asset selection and the full photo/text → SIM question → generation → Build → Run journey. C1 staging/checklist/project-switch gaps and C3–C6 REAL qualification, survey, plan confirmation, summaries and TaskLoop remain. Whole readiness stays false. Robot power is not needed for the immediate next work.

All test-owned processes were stopped. Existing dirty changes and prior failures are preserved. No robot, paid provider, installation, deployment, commit/push or new agent was used. Existing heartbeat stays PAUSED. Model-capacity errors are an app/model-service issue separate from the product's `simulation_not_ready` failure.
