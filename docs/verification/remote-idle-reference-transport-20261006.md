# Full survey reference transfer and current idle localization

Date: 2026-10-06 KST. Baseline v1.0.300. Robot OFF. No SSH, serial, actual sensors, motors, deployment, paid calls, installation, system changes or new agents. Original measurements, prior failures, existing dirty changes and physical motion locks remain preserved.

## Implemented path and limits

The existing App and chat goal source now has a production factory method for transferring its accepted survey reference to the fixed robot worker and explicitly requesting a fresh position with wheels disabled. Full selected survey maps, tracking endpoints and alignment reports are preserved rather than reduced to the legacy bootstrap limit. This is a no-motion localization path, not a completed physical goal mission.

**C4 remains PARTIAL and whole readiness=false.** Exact reviewed-plan idle-to-driving handoff and actual exact-plan Isaac 3D demonstration receipts remain unimplemented. Physical Confirm stays locked. Actual Chrome, Isaac, target build and field acceptance are NOT_RUN in this increment. Web source/build were not changed; no new Web build acceptance is claimed.

## Product connections

1. The additive `observed-mission-scope-6.0` describes only `IDLE_LOCALIZATION_ONLY`, with a placeholder zero target that cannot execute a mission. Original scope versions and their serialization remain unchanged. The server owns the accepted reference loader and current room revision. The reference binds the original report key, map and alignment revisions, project and exact payload digest; no browser-supplied source or file path can register an observation adapter.
2. The existing fixed `teleop.sh` and worker accept `localize`. The robot validates the compact bootstrap, boot, reviewed release and calibration, then receives the entire bounded reference before device initialization. Ordered 6,000-byte upload chunks preserve the existing 16KiB input line budget. Length, nonce, index, full digest, original fit and causal held-out sequences are checked. Upload has a separate bounded 30-second deadline and supports cancellation; no automatic retry or deployment is added.
3. The worker uses existing isolated scan preparation, ROS observation window and native sampler. Existing autonomous profile, same-boot stop qualification, independent Motor OFF, source and sensor guards remain required. The local idle loop never enables motors, consumes a mission or publishes a direction. Fresh watch inputs retain the unchanged 250ms deadline; query and chunk acknowledgements do not renew it. The idle loop is bounded to 45 seconds and request expiry; it never reconnects automatically.
4. The PC waits for acknowledgement of the first watch input before querying. Each explicit query samples again. Observations are losslessly compressed, hashed and transmitted without grid truncation. Large observations use fixed 40,000-byte output chunks within the existing 64KiB stdout limit; PC upload size is unchanged. The data envelope is bounded to 4MiB and retained packets to 8MiB per session. Exceeding a budget rejects the operation rather than silently dropping data.
5. Query receipt and issue times are robot-monotonic; the PC measures its own full round-trip duration. Robot query receipt plus the entire PC round trip bounds the robot time at PC receipt without comparing absolute PC and robot clocks. Robot processing duration must fit that round trip. Current source identity, alignment, session and unchanged 200ms acquisition-age limit are checked again after processing and before use. Stored survey pose is never injected as current position.
6. Query failures close the owned keeper and worker while preserving the original cause. Another owner's request cannot close the existing session. Both normal and exception termination preserve localization failure fields. Cancellation, worker termination and cleanup invalidate current observation caches. Session history verifies retained packet hashes and labels them historical with `current_pose_valid=false` and `motion_authorized=false`. Existing raw ROS export/recovery files remain a separate evidence path; these localization packets are not a replacement for serialized raw ROS data.

## Verification

Final frozen-source Python regression passed: 126 tests in 214.105 seconds, exit code 0. Web full regression passed: 316 tests in 42 files, 24.36 seconds, exit code 0. This is Vitest/jsdom coverage, not actual browser or engine acceptance. Both owned test processes completed. Tests needing temporary directories and local subprocesses used scoped local execution permission; no hardware/network or system configuration action was performed.

Python used the bundled runtime with `-B -m unittest -q` and explicit ReferenceWireTests, RemoteIdleTests, IdleLoopSafetyTests, IdleCurrentTests, CurrentGoalPreviewTests, ChatGoalTests, ProtocolTests, TransportTests, HistoryTests, MissionTransportTests, MissionEvidenceTests, test_robot_source_identity, AutomaticMissionTests and RemoteCorrectionTests. Web used the existing `pnpm test` in `apps/twinpulse-web`.

The selected Python suite covers full upload and native worker parsing; two new source queries from the actual local PC controller and synthetic native worker subprocess; lossless large observation chunks; delayed response rejection; ownership and missing registration; full reference/report preservation; historical packet hash tampering; direction rejection, missing watch, expiry, backwards clock, changed motor state and sampler cleanup. Existing manual protocols, PC transport/history, mission evidence, source archive identity, current-goal/chat, automatic mission and remote correction regressions are included.

The subprocess uses explicit synthetic observations, fake calibration and test-only registration in a local command. It runs the production parser, controller, native factory and idle loop, but does not qualify production SSH admission, actual ROS callbacks, wireless latency or physical cleanup. No synthetic result is a physical success.

## Preserved intermediate failures

- Sandboxed temporary-directory tests hit Windows EACCES. Scoped local test execution was used afterward; no permission or WSL service workaround was attempted. The earlier focused 18-test suite passed in 14.610 seconds.
- An initial six-test run had five passes and one `REFERENCE_TRANSPORT_BYTE_BUDGET` error in 23.923 seconds. The initial 1MiB observation envelope could not preserve the already allowed full grid. It was replaced with bounded lossless 4MiB data transfer, not a larger command or sensor-age allowance.
- A subsequent nine-test run had six passes and three failures/errors in 23.195 seconds. It exposed first-watch/query ordering and failure-lifecycle coverage gaps. A focused normal subprocess test passed separately in 23.571 seconds. The next nine-test run had eight passes and one stale large-observation failure in 28.680 seconds. Robot processing time had been counted twice in the conservative time bound. Query-receipt timing fixed that calculation without changing 200ms; a later focused nine-test run passed in 28.841 seconds.
- The first broad 126-test run had 124 passes and two failures/errors in 215.014 seconds: small output chunks left too little freshness margin and an exception path discarded the localization error field. Fixed output chunks now use the existing larger stdout budget without changing stdin or safety limits.
- The next broad 126-test run had 125 passes and one failure in 214.431 seconds. Normal termination preserved the error field, but an exception-thread race still replaced it. Both terminal paths now preserve those fields. These failed runs are not recorded as full passes.

## Source identity and next work

Reviewed robot source changed and has not been deployed. Previous reviewed source or stop qualification cannot silently authorize this new release. These source hashes were unchanged during the final run and rechecked afterward. No original report, raw measurement or prior failure is rewritten.

| Source | SHA256 |
| --- | --- |
| `reference_transport.py` | `25f3581b12f03d7f94aaf4c981006dc88cd27831b9d9efd6459d7901a9be61f1` |
| `adaptive_mission_contract.py` | `32a5cef55bf3385bed70fd7a7848f2bb65bfbe20a1ca6ad648901b5891fe3b41` |
| `mission_runtime.py` | `44097729280ff8437d8eef1b6b09af71130a330e6ee4ce38a24c3b0e2a3ebac3` |
| `observed_runtime.py` | `ee12e6b6383ba7e2231f3166483a1b68a600b7861eb2f6df03f87fcfe15e2180` |
| `teleop_worker.py` | `2495b1b0b39f8263020fa00d674c0a9c1fcd319fcdab57405c4de14633f08054` |
| `physical_controller.py` | `b6ae9efc1747e5d509c6e12514d8cb5be20c926da1c1a86e6eda548b2527d2fd` |
| `remote_observed_adapter.py` | `42466ecbfa9f894cc3cf98ee86fabc57fb0c2953a341ee24a2938cab2496a65f` |
| `session_history.py` | `286620c94c6aa4c727d6f5544ca913f66cd536a397d808ca80abf6fe076eac9b` |
| `test_reference_transport.py` | `e9d29e103cbf68270cc1defcd9bcb657017791a3264b90addcea57d77523f6ec` |
| `idle_reference_robot_process.py` | `ee61d64af73c905e4e660053c436d72f51ad7e79611ee17905558c0c805e2744` |

The next offline implementation is exact reviewed-plan transfer from the owned idle worker into driving, with fresh source/map/pose revalidation before the first output. Actual Isaac 3D execution and its exact stage/engine/plan receipt must precede physical Confirm. Goal five-second summaries, persistent C5 Loop and C6 normal/failure integrated acceptance then remain, together with separate C3 target/profile and field qualification. Robot power is not needed for those next code connections; powering on alone does not finish the physical demo.
