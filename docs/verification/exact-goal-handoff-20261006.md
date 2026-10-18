# Exact reviewed goal handoff in the existing worker

Baseline v1.0.302 adds the missing product connection from a current-owner disabled-wheel localization worker to the reviewed goal mission. A single explicit chat Confirm can transfer the complete immutable review into that same worker, using the existing full accepted survey reference, native guard, input gate, device ownership and cleanup path.

**C4 remains PARTIAL; whole readiness=false.** This is offline implementation and regression evidence. This increment does not qualify real localization noise, the target binary/profile, physical movement or the combined actual chat/embedded-Isaac/native journey. Robot/SSH/serial/sensor/motor/deployment, paid calls, installs, settings, commit/push, other-process termination and new agents were zero. Existing raw data, dirty edits and failed records are preserved. Heartbeat remains PAUSED.

## Connected product path

1. Existing chat goal review and engine/stage/run-bound Isaac completion receipt are checked by the server. The busy exception applies only to the same owner, same accepted reference and READY idle worker. Code capability alone does not unlock Confirm; missing qualification, failed SIM receipt or no matching worker remains locked.
2. The registered remote factory is used instead of starting a legacy reduced-reference mission. It rereads current reference/room evidence and samples fresh disabled-wheel localization again. Exact pose, transform, map/cells, source context, review digest and complete route must match. No saved terminal pose or restored chat approval is used.
3. The PC saves the full handoff document before sending it. Ordered 6,000-byte upload chunks carry its SHA256/byte descriptor and a fresh nonce. The native worker checks the original idle scope/job, complete payload, goal, alignment and fresh evidence again. Additive scope7 cannot be bootstrapped independently; scopes1–6 remain intact.
4. Native execution retains the original InputGate and original 45-second idle/session budget. Transfer data is not heartbeat or renewed consent. Fresh scan/pose200ms, input250ms, mission segment50ms, .03m/s and .20rad/s remain unchanged. Transfer timeout, Stop, wrong nonce, source/room/pose change or expiry prevents execution.
5. Existing ObservedMission compares the first current route with the reviewed route, then follows the existing local reactive planning/obstacle protection. A second approval check after Motor Enable and immediately before the first nonzero publish prevents an enable-time position change from escaping the guard. The first successful publish consumes that check; later movement still uses existing fresh source, pose-jump, collision and replan checks.
6. App safety continuously checks the transient Isaac receipt and current revisions. Polling retains owner liveness, not per-command consent. Stop/Force STOP remain independent; failure never automatically retries or reconnects. The same PC/native job retains both historical scope6 and scope7 records.
7. Saved handoff raw bytes are cross-checked against request/scope/review hashes, ordered sent chunks, acceptance ordering and the new mission scope. Archive review remains historical-only, physical_authority=false. Raw or journal modification cannot restore live approval.

## Final verification

Final frozen-source Python regression: **55 tests /145.055s PASS**. All16 code/test hashes match before and after execution; every test-owned worker completed. This result is selected-suite offline acceptance, not whole-product or physical acceptance.

- Selected suites: ReferenceWireTests, RemoteIdleTests, IdleLoopSafetyTests, CurrentGoalPreviewTests, ChatGoalTests, AutomaticMissionTests, GoalDemonstrationTests, SourceIdentityTests, AdmissionTests, CleanupWallTimeTests; new GoalHandoffContractTests and RemoteGoalHandoffTests plus the single new ChatGoalHandoffTests handoff test. Inherited chat tests are not counted twice.
- New virtual-time transfer test covers retained gate/sequence and original budget, Force STOP, input deadline, expiry and nonce failure without enabling or moving any device.
- New actual local subprocess tests exercise existing PC controller, stdin transport, native worker loop and ROS-shaped synthetic link. Positive arrival uses an **explicit stable synthetic estimator double** until first publish. This is not real localization accuracy or field acceptance.
- The existing raycast matcher, without the stable double, changes its exact pose binding slightly and is rejected. The test verifies this rejection and zero output; it is not a successful real navigation test.
- Other new cases: Force STOP without reconnect, pose change during Motor Enable with zero nonzero output, lost SIM receipt with no handoff, wrong owner/reference, changed review/alignment and raw-byte tampering.
- Web regression this turn: **318 tests /42 files /24.11s PASS**. No Web source changes this increment; no new build claimed. All three existing Vite build-manifest hashes match, including JS `6a5f4d64868da51bae28f22a89c465636853cf6e691c7d8a14f584bd31dfc63b`.
- No actual Isaac or Chrome run this increment. The [v301 actual Isaac two-route result](exact-goal-demonstration-20261006.md) remains scoped to its own input/source and does not establish this combined journey.

## Failures and corrections retained

- Initial sandbox fixture run failed TEMP EACCES before product execution. The approved local test run then passed25 tests/19.385s. No permission bypass or new installation was used.
- First five new cases had two passes and three failures. A fixture omitted a required evidence state; the real PC writer treated the data-only begin packet as a manual sequence packet, causing KeyError(sequence) and INPUT_CLOSED_OR_OVERFLOW. Corrected by separate handoff begin/chunk journaling, without changing watchdog or approval limits.
- Focused five then passed33.677s; expanded seven passed36.828s before the final archive-hardening edits. These are intermediate results, not final-source acceptance.
- Broad pre-hardening47 ran115.489s with46 passes and one stale-current-evidence error on the second large observation. Later isolated large-transfer checks passed. This does not establish the cause or eliminate scheduling/processing latency; the stale sample was rejected and never made current by relaxation/retry.
- The added virtual contract test initially lacked the native import path; the corrected two contract tests passed0.209s.
- One intermediate command selected a nonexistent chat method and ended13 tests/one loader error. Corrected to the existing new method; not counted as a product failure.
- Archive-hardening introduced an imported `decode` shadowing the existing journal decoder. The intermediate55-test run ended145.024s with49 passes/six errors and corresponding thread tracebacks. The payload decoder now uses a distinct alias. The final run must prove the correction; intermediate failures are not overwritten.
- A non-mutating process inventory request was denied. It was not escalated or used to terminate processes.

## Exact remaining sequence

1. Define and test a noise-aware review admission policy and review/Isaac timing lifecycle offline. Current exact pose/cell equality still rejects small estimator jitter, and SIM preparation/review counts against the unchanged 45s session. Do not silently loosen geometry, freshness or physical qualification. This is a usability/contract gap, not a request to power the robot now.
2. Exercise one combined current-localization→actual chat/embedded Isaac exact-route demonstration→single Confirm→native execution and cleanup journey, including scene change, receipt loss, Stop, stale transport and reload. Use explicit synthetic input scope first; actual engine success is not physical success.
3. Connect goal five-second summaries, persistent bounded return/target legs and C5/C6 normal/fault/reload acceptance.
4. Separately prepare/qualify the reviewed target binary/profile and fresh on-site validation of geometry, scan/odom/TF, stop, latency, autonomous travel and loop. Changed robot source is **NOT_DEPLOYED**. Power alone does not guarantee the complete demo.

## Frozen source SHA256

The following16 code/test files were frozen before the final regression and all match after execution. Documentation changes are excluded. Tracked diff whitespace checks pass; pre-existing unrelated dirty and untracked files are preserved.

| File | SHA256 |
| --- | --- |
| `packages/twinpulse_core/src/twinpulse_core/adaptive_mission_contract.py` | `7ffa64fe8357562be8f01b583ff40f31ed4c6bd169bb6ea87ef2055fb8685c33` |
| `packages/twinpulse_core/src/twinpulse_core/reference_transport.py` | `3582dc422ee9b8246f1e8ea8618236f644223cfdfc56bfc4a12c7fa791007225` |
| `packages/twinpulse_core/src/twinpulse_core/observed_mission.py` | `39270a43f757d5797152c597466221abb94aa49f1f8a88aa4d490b637e6f3023` |
| `packages/twinpulse_robot_safety/observed_runtime.py` | `a648172cf302756004b1c92d2d49feac641799ca088a0ab4d6bcb874c23bf77f` |
| `packages/twinpulse_robot_safety/mission_runtime.py` | `538a86a1ef9dd1927d96f83a49e43f7c1f272a34999c535473b7555982cfdf1d` |
| `packages/twinpulse_robot_safety/teleop_worker.py` | `5421cb3c79228a52fdb0a7fc8e78ee0315d45b3382882cb9c4f166d0b4d71699` |
| `packages/twinpulse_robot_safety/teleop_ros.py` | `56148911bab77d523fac36f433c11132c9e2075d657a505c89f915076491bd78` |
| `packages/twinpulse_app/src/twinpulse_app/physical_controller.py` | `848a6b690fb6e4a2c34b2851108f705494bf1a8f2492de71ffa4139b1c1de11b` |
| `packages/twinpulse_app/src/twinpulse_app/remote_observed_adapter.py` | `5fdbb2d50e0adbb5baa52662fc94a5a3e77c43adc6a134c0aff2a2ceac2f63a0` |
| `packages/twinpulse_app/src/twinpulse_app/automatic_mission_service.py` | `3d812576d4cd84e4e533b37e8cf0419494879c5ab756e6a5ba01034060efe9da` |
| `packages/twinpulse_app/src/twinpulse_app/chat_robot_preparation.py` | `3dfdf16624210db5874f0736331db23ba89b12f29eb18db798acebe231c9e3ef` |
| `packages/twinpulse_app/src/twinpulse_app/chat_goal_navigation.py` | `ff2ba1605861fde55da736e97eba323bc292d859540abbe026d2730ef18bbafb` |
| `packages/twinpulse_app/src/twinpulse_app/conversation_service.py` | `c04bd7e9f85f1ef7972450a7c7b6ef1a606fa98d78336dd41e51094037c13b44` |
| `packages/twinpulse_app/src/twinpulse_app/session_history.py` | `c8ecbb59446c77fd57ae0563691bd47504c55a6a685f1091ab1540d101c75865` |
| `tests/integration/test_goal_handoff.py` | `dff2b287eab2bce408339ec54e13786de489023725198851c057cb7b0cea529c` |
| `tests/fixtures/idle_reference_robot_process.py` | `737c893e523da50096e845ff33790ca18df1fe3d6d90169b84003f651c4d8569` |
