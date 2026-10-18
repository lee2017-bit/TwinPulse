# TwinPulse repeating goal task verification

An arrival now offers one inline **Repeat A ↔ B** or **Finish task** choice. One repeat approval owns an upper task that alternates fresh bounded goal workers; it does not renew an expired worker or replay recorded wheel commands. A is the first approved room start and B is its target. This is the C5 orchestration connection, not physical demo acceptance.

Baseline 1.0.307 remains **C4 and C5 PARTIAL, whole readiness=false, physical validation NOT_RUN, robot source NOT_DEPLOYED**. No robot connection, SSH, serial, physical sensor/motor operation, deployment, paid call, installation, system change, commit/push or new agent is authorized by this work. Heartbeat remains PAUSED.

## Execution and stopping

Every leg uses the existing registered current localization, checked route, actual exact-route Isaac preview and same-worker native handoff. Only arrival with finished cleanup and a saved report allows the next leg. Watchdog, timeout, source/frame/room change, failed cleanup or failed storage stops the task; no failed leg is retried. Source, room and alignment are fixed to the immutable survey reference. The visibility-grid hash can change with new scans, but the new grid and complete route still pass the existing checks.

The task preserves scan200ms/input250ms/segment50ms/.03m/s/.20rad/s/active45s and all qualification/first-output/Stop gates. A conservative route-duration estimate rejects legs that exceed the bounded budget; it does not guarantee arrival. Each leg reacquires observations and runs its preview, so there is an idle transition, not uninterrupted wheel output.

Ordinary Stop cancels upcoming commands and legs and requests the existing segment stop. Force STOP can upgrade a pending Stop. The independent API works during preparation and does not depend on saving chat. Browser presence uses a separate authenticated, bounded heartbeat; internal task snapshots cannot impersonate the browser. A lost owner fails closed. Task history is created exclusively and synced before each admission, with bounded storage. Saved journals and chat cannot restore execution permission. Ended or restarted pending messages are historical/interrupted.

## Battery and unsupported measurements

Native idle observations optionally carry `task-resources-1.0`, using the original ROS SensorState receipt and source ages. Both preview and post-Isaac admission require values younger than 200ms and motor-disabled evidence. Legacy evidence remains unchanged when this capability is absent; missing resources refuse repetition instead of borrowing a readiness snapshot.

The existing voltage estimate and 20% rule do not represent measured capacity. The task's stricter rearm condition is voltage above 11.2V, preserving the existing greater-than-11.1V sensor guard and board protection. Failure stops locally rather than blindly returning home. Displayed leg resource values are dated history, not continuously observed battery. Actual current/load measurement is unsupported; torque-enabled is not torque/load. A separately qualified progress-stall detector and live next-waypoint/battery summaries remain unfinished.

## Verification

Final post-pump selected Python regression: **153 tests PASS / 154.637s**, all **50 source hashes unchanged** across the final freeze, actual runtime and regression. [Final frozen-source record](../../artifacts/verification/goal-task-loop-20261006-final-regression.json). This selected contract/integration suite is not the whole repository. Targeted `git diff --check` passed; Git only reported its existing LF/CRLF conversion warning.

Pre-pump selected Python regression: **148 tests PASS / 153.384s**, with all **50 source hashes unchanged** before and after that run. [Preserved pre-pump regression](../../artifacts/verification/goal-task-loop-20261006-pre-arm-pump-regression.json). The later native pump change was followed by the final 153-test regression above; this earlier count and the prior 144/147 runs are not added to it.

Web: **320 tests across 42 files PASS / 23.14s**, TypeScript and production build PASS. Coverage includes the typed task review, dated resource/history display, and task fault state. These results do not test robot hardware.

Final-source actual Chrome/App/Bridge/Isaac/native continuity **[attempt 04 PASS](../../artifacts/verification/goal-task-loop-20261006-04/verification.json)**: actual built chat first goal/Isaac PhysX review/native synthetic arrival → one inline repeat approval → return A → return B → ordinary Stop during leg 3 preparation → saved history/reload without automatic Build or worker restart. Ended repeat messages are no longer pending. Each worker starts from the preceding raycaster's final pose in one continuous synthetic world; that private world pose is not supplied to the matcher.

All **35 runtime source hashes and four built Web files unchanged**, original survey bytes unchanged, seven archived sessions reopened, all seven peers' motor/sensor cleanup confirmed and owned App/Chrome/Isaac/backend children exited normally, without forced cleanup. The task completed two repeat legs and ended `STOPPED`, worker inactive, no task/cleanup errors. The native first goal/return A/return B produced 48/185/187 nonzero synthetic outputs; preparation peers produced none. Maximum synthetic servicing gaps of about 63ms and reported robot-accept gaps of 125ms are test-process observations, not qualified physical command-segment, ROS hardware or network timing.

Unit tests cover missing/stale/low resources, changed source or frame, exhausted duration, ownership loss, report/cleanup/storage failure, approval replay and Stop during preparation. They are not actual combined runtime or physical fault qualifications. Attempt 04 is a successful scoped run, not proof that all concurrent latency cases or the field Wi-Fi issue have been resolved.

The first actual integration attempt failed with `TASK_FRAME_OR_REVISION_CHANGED`: the initial upper contract treated a current visibility-grid hash as a fixed coordinate-frame identifier. The existing tracker hashes deskewed current cells, which legitimately change after driving. The fix keeps survey identity, source/epoch, room/alignment and transform fixed while rechecking fresh grids and routes. The failed attempt is preserved at [attempt 01](../../artifacts/verification/goal-task-loop-20261006-01/verification.json); it is not physical failure or PASS.

[Attempt 02](../../artifacts/verification/goal-task-loop-20261006-02/verification.json) passed the actual built UI/Isaac loop, but preceded the pending-chat history correction. [Attempt 03](../../artifacts/verification/goal-task-loop-20261006-03/verification.json) subsequently failed at the first return leg with `INPUT_DEADLINE_EXPIRED` and zero nonzero outputs; it is preserved, not retried automatically or converted to success. PC watch events continued at roughly 50–80ms, but no new robot challenge was serviced after entering that first native decision. The exact slow subphase is not established from that trace. Offline pure replay of the archived route recheck took approximately 18ms under profiling, which is not a concurrent runtime or field timing qualification.

The native tick now pumps original queued keepalives/Stop after current matching/whole-route checking and before paying arming latency as well. It keeps the same InputGate, original command timestamp, 200ms sensor age, 250ms input expiry and 45s session budget; it cannot revive an expired input. Focused regression covers a partially aged original input with a genuinely fresh queued watch, expired-input refusal, and Stop before arming. Initial test-fixture callback timestamp/skew errors were corrected using new synthetic messages, not relaxed source rules. These deterministic tests do not prove the entire concurrent timing issue is resolved.

## Remaining work

1. C5 live resource/next-waypoint telemetry and a separately qualified progress-stall policy. Its full acceptance also requires three actual PhysX round trips, the combined battery/stall/storage/Stop fault matrix and a 30-minute wall-time memory/log run. Attempt 04 completed **two repeat legs (one return-and-go cycle)**, not those complete requirements. No invented load measurement or physical blocked-wheel test.
2. C6 actual combined fault cases, Force STOP while a leg is running, dynamic obstacles, changed starts, owner/source loss and target package/profile acceptance; the unit fault passes do not replace these.
3. Separately authorized target release and actual timing, coordinate/current-room localization, battery and bounded physical mission acceptance. Robot power alone does not finish these steps.

The next software checks can continue with the robot off. Synthetic continuity and actual Isaac PhysX are not physical movement or measured room reconstruction.
