# TwinPulse goal execution chat progress verification

Goal execution updates one owned chat message every five seconds. Stop requests, location loss, arrival and failure appear on the next authenticated poll without waiting for that interval. Cleanup and report failures remain separate from the original cause. Finished or restarted missions cannot leave prior poses labeled current. This completes the scoped progress connection, not persistent loops or physical demo acceptance.

Baseline 1.0.306 remains **C4 PARTIAL, whole readiness=false, physical validation NOT_RUN and robot source NOT_DEPLOYED**. Current receipts lack live battery and next waypoint, so those are explicitly unavailable. No robot, SSH, serial, physical sensor/motor operation, deployment, paid call, installation, system change, commit/push or new agent was used. Heartbeat remains PAUSED.

## Product behavior

`ConversationService` reads the existing owned navigation snapshot. The first periodic summary appears after five seconds; delayed polling emits one latest summary rather than a backlog. Updates replace the same message. Important terminal changes create separate history. This uses no LLM calls, motion commands, mission renewal or authorization changes.

Recent worker coordinates and scan returns are distinct from stale, missing or localizing frames. The display checks PC receipt age within 200ms, not acquisition timing or physical localization qualification; transport delay remains unmeasured. Goal separation means straight-line distance, not remaining route length. Recorded trace distance is bounded history.

Worker activity and visual age are transient snapshot fields, excluded from immutable mission reports. Ended progress is historical; restored pending progress becomes interrupted history. Saved events suppress duplicate terminal notices but cannot restore ownership, pose, approval or execution. Isaac demonstration messages are persisted when polling changes their state. Production Web source/build did not change.

## Verification

Final frozen-source selection: **129 tests PASS in 145.620s; 44 source hashes unchanged**. Imported/inherited tests are included; this is not the entire repository suite. Coverage includes authenticated cadence, single-message updates, five terminal states, location loss, Stop, late cleanup failure, distinct causes, persistence failures, restart, bounded/nonfinite formatting, goal confirmation/handoff, mission/report/observation boundaries, latency, lease rotation and conversation persistence. [Regression and source hashes](../../artifacts/verification/goal-progress-20261006-final-regression.json).

The initial sandbox run could not access generated temporary fixture files. The first authorized selection exposed a fixture missing `demonstration` during teardown and a nonfinite fixture HTTP response rejected by JSON. These attempts were not PASS. The fixture was corrected and nonfinite formatting tested directly. Incremental 21-test passes are not added to the final count; product guards were not relaxed.

Actual built App, authenticated Bridge, actual Isaac engine and existing Chrome passed both distinct goal journeys in isolated owned roots. Each completed an Isaac route preview, one UI Confirm, fresh native synthetic execution and arrival. Each mission updated one progress message and showed arrival in chat. Reload caused no new execution or duplicated terminal. [Actual result](../../artifacts/verification/goal-progress-20261006-01/verification.json).

Moving peers arrived with 48 and 113 nonzero synthetic publications; parked previews remained zero-output. Delayed observation visibly rejected with `IDLE_LOCALIZATION_QUERY_TIMEOUT`; the negative native peer failed on `INPUT_DEADLINE_EXPIRED` with zero motion and confirmed cleanup. Five archives reopened; all wheel/sensor cleanup receipts passed. Original survey bytes, 29 runtime sources and four built Web files were unchanged. All owned children exited normally; screenshots are saved beside the result.

Reactive synthetic scans/odometry and test-only qualification are not physical acceptance. Maximum synthetic servicing intervals of approximately 62–63ms include scheduling and do not establish physical timing, command duration or braking. Existing scan200ms/input250ms/segment50ms/.03m/s/.20rad/s/45s, qualification/source/Stop gates are unchanged.

## Remaining sequence

1. C5 persistent A/B task loop with current observations per leg, Stop/Force STOP and battery/obstacle/torque/freshness/source failure refusal; no automatic fault restart. Two separated synthetic goals do not qualify a loop.
2. Current task telemetry, including live battery and executable next waypoint, without substituting saved preparation observations.
3. C6 normal/failure acceptance, changed starting positions, dynamic obstacles, restore and target package/profile checks.
4. Separately authorized target release, real coordinate/timing/localization/current-room alignment and bounded physical execution. Robot power alone does not complete these checks.

Next software stages can proceed with the robot off. No verification worker remains running.
