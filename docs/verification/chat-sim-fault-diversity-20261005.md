# SIM runtime faults and scene diversity verification

2026-10-05 · Baseline v1.0.290. The approved offline runtime-fault, rollback and scene-selection increment is implemented in the existing chat, API, provider and Isaac paths. Actual local Isaac verifies failed-build restoration, fault stopping and a furnished living-room journey. This is not whole-demo, new photo-inference, general robot-catalog or physical acceptance.

## Product changes

A failed visual composition now restores the exact owned USD backup and rebinds its checked compiler receipt instead of recompiling the previous scene. Recompilation could change the restored state. Removing the entire owned root also invalidated Isaac's cached PhysicsScene prim: the actual transaction rehearsal reproduced `Accessed invalid expired 'PhysicsScene' prim`. Copying the backup over the existing owned root preserves that prim; a subsequent actual PhysX Run succeeds. Restoration does not reinstate a route, controller or execution approval. Non-owned prims remain unchanged.

During a physics-step exception, the runtime zeroes wheel targets and pauses the timeline even when zeroing succeeds. Zero targets alone are not proof that residual simulation motion has stopped. Original fault causes remain observable. Geometry identity loss clears the current run and pose and retains its reason. The chat now renders a current engine fault independently of `run_id`, so invalidation cannot hide the error behind “No active motion task.” Connection loss, engine identity change and runtime faults invalidate the reviewed route. Recovery does not automatically reuse an old approval or resume Run.

The selected existing Nebius site-provider profile now requests tool-plan 2.1, using the existing `place_furniture` catalog. Its planner describes bed, wardrobe, desk, chair, sofa, dining table and storage as parametric approximations and explicitly avoids treating every home as warehouse racks. The default 2.0 schema and older 1.0/2.0 stored plans are unchanged; legacy non-site provider configuration remains separate. Pure planner/schema tests and an explicit fake provider validate this new contract. No new paid generation call or photo interpretation was performed.

SIM robot selection now explains why the existing Burger was selected. Recognized unsupported text requests, such as a drone or quadruped, produce an inline alternative-selection question and wait before generation. Selecting “Use TurtleBot3 Burger instead” continues the existing generation path. This is a bounded text rule, not visual recognition, comprehensive model matching or a new runnable model. Current room SIM still qualifies only the existing Burger.

## Final evidence

| Check | Evidence | Result and boundary |
| --- | --- | --- |
| Actual USD transaction and runtime fault | `artifacts/chat-sim-fault-transactions-20261005-04/result.json` | PASS: bedroom 12 objects, living room 17, warehouse 9; exact USD/identity restoration, valid PhysicsScene after rollback, external prim unchanged, actual Run then injected pose fault, zero wheel targets and paused timeline, duplicate Run cached, explicit Reset and geometry-loss invalidation |
| Actual Web fault and lost Run response | `artifacts/chat-sim-fault-browser-20261005-final/result.json` | PASS: production chat/API/Isaac with a test-only injected physics pose exception; one accepted Run response deliberately dropped, read-only receipt recovery without resend, English alert, current pose absent, Run locked, reload without resume |
| Furnished living-room product journey | `artifacts/chat-sim-living-room-20261005-final/result.json` | PASS: fresh text, inline robot question, explicit fixture generation, automatic room Build/static Burger, explicit PhysX Run and arrival, current-pose sofa goal, Stop with viewer folded, reload/mobile and explicit Reset |
| Final source and Web binding | Same two browser receipts | Each 29 source/four built Web SHA256 values match the final checkout; lower transaction receipt's six sources also match |
| Test-owned cleanup | Same two browser receipts | Supervisor stopped; backend and engine ownership false. No unrelated process was terminated |
| Related Python regression | Command below | 192 tests PASS, including provider contracts, selection, chat, startup, manager, site simulation and goals |
| Web regression and build | Existing local Vitest/TypeScript/Vite | 37 files / 293 tests PASS; production build PASS. Existing bundle-size warning remains |
| Existing six browser/API cases | `artifacts/chat-c1-fault-diversity-20261005-final/verification.json` | Image, text, REAL selection, failure, cancellation and saved-edit PASS; explicit fixtures, Isaac NOT_RUN in this separate harness |

The living-room generator response is an explicit local fixture, not a model's interpretation of a fresh request. The browser and backend, USD composition, rendering and PhysX motion are actual installed runtime paths. The three-family lower test uses explicit local tool plans; it is not a three-family natural-language acceptance. Runtime fault injection requires the separate test host's explicit flag and is not enabled by the production launcher.

The lost response test distinguishes accepted Run from successful navigation: the command receipt succeeds because Run was accepted, but the later injected runtime fault fails motion and locks further Run. A successful receipt must not be relabeled as completed navigation. This increment does not claim a complete fresh browser retry to arrival after the injected fault; Reset is verified separately in the lower actual-runtime and normal browser journeys.

## Failure records and reproduction

Transaction attempts `...-01` and `...-02` failed because the new harness initially supplied an invalid source reference and unsupported source label. Attempt `...-03` exposed the actual expired PhysicsScene defect. These records remain unchanged. Only `...-04` is the final lower transaction acceptance. Earlier browser/living-room runs are intermediate source snapshots; the two `...-final` receipts bind the final implementation.

The first Web regression run retained an old expectation that a failed safety/readiness state could recover and continue the previous Run approval automatically. That expectation was replaced with explicit rejection and a fresh review after recovery. Safety and readiness requirements were not relaxed. Isaac can close with process status zero after a caught test exception; the saved JSON verdict, not exit status alone, determines actual acceptance.

```powershell
python -m unittest packages.twinpulse_provider.tests.test_nebius_pipeline packages.twinpulse_provider.tests.test_provider packages.twinpulse_provider.tests.test_tool_catalog_compat tests.integration.test_site_furniture_generation tests.integration.test_sim_robot_selection tests.integration.test_chat_conversation tests.integration.test_s3c_product_wiring tests.integration.test_chat_startup_checks tests.integration.test_r6_process_manager tests.integration.test_simulation_goal tests.integration.test_site_simulation
pnpm test
pnpm build
python scripts/verify_chat_sim_journey.py artifacts/<fresh-fault-output> --case text --fault
python scripts/verify_chat_sim_journey.py artifacts/<fresh-living-output> --case text --layout living_room
python scripts/verify_chat_c1.py --output artifacts/<fresh-chat-output>
C:\isaacsim\python.bat scripts/verify_sim_fault_transactions.py artifacts/<fresh-transaction-output>
```

Run pnpm in `apps/twinpulse-web` with the existing local dependencies. Replace placeholder output paths with fresh directories. Tests use isolated owned outputs; no installation, live provider or robot permission is implied. Source/build hashes in the final receipts were compared with current files after execution. The separate six-case receipt also matches its 21 source/four Web hashes; its older fixed remaining-work list is not the current milestone status. `git diff --check` passed; existing CRLF warnings are not whitespace failures.

## Remaining work

1. Complete the prerequisite and package matrix, native launcher-window handoff and another-PC acceptance. Current local startup checks are not clean-install qualification or arbitrary automatic repair.
2. Accept real provider interpretation and wider natural-language staging separately when authorized. New 2.1 schema/prompt acceptance is offline only; unknown robots and photo-derived robot matching remain unsupported. A genuinely different runnable robot needs its own checked asset/controller/runtime acceptance, not another display name.
3. Connect and accept C3–C6 REAL chat qualification, survey/correction, exact-route confirmation, five-second summaries and loop tasks. Existing measured profile, real-photo alignment and field requirements remain unresolved.

C1/C2 remain PARTIAL; whole-demo readiness=false. The selected runtime/rollback and living-room paths above pass, but not the entire 12-step demo. The next offline code work does not require robot power. Existing dirty changes, raw originals, old failures, v1/v2 serialization and real mission locks are preserved. Physical guard limits remain scan 200 ms, input 250 ms, segment 50 ms, 0.03 m/s, 0.20 rad/s and 45 s. Robot/SSH/serial/sensors/motors/power/deployment/paid calls/install/system changes/commit/push/new agents: zero. Existing heartbeat remains PAUSED.
