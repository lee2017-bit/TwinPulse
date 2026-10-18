# Current chat room inspection and survey separation

Baseline v1.0.294, 2026-10-05 KST. The chat can now bind an explicit inspection request to its current generated room and reuse the existing bounded observed-mission worker. This increment completes the survey-only connection bundle, **not all C4 or the physical demo**. No robot, SSH, serial, real sensor/motor operation, deployment, paid call, installation, commit/push or new agent was used. Heartbeat remains PAUSED.

## Connected product behavior

The room adapter reads the current checked chat draft and registered scene, including edits, inventory completeness and input/photo/scene revisions. It does not silently substitute the historical default bedroom. The source identity participates in the existing mission revision guard. Existing standalone saved-room analysis loaders remain available, but App automatic-room operations now require the current chat room when that workflow is configured.

A newly acknowledged REAL generation arms a room-only Isaac Build. Restored history and passive polling do not arm it. A restored ready draft instead offers an explicit **Display current room in Isaac · no robot command** button. The component checks Build readiness, sends at most one command, waits for its receipt and independently waits for the matching idle room snapshot. Unknown delivery is reported without retransmission. This path never sends Run, sensor or motor commands. Its orchestration has unit coverage; actual REAL-room Isaac Build/viewport acceptance was NOT_RUN in this increment.

The inspection question appears only when the current room is applied in the engine, this owner's preparation is LINKED and the production observed adapter is available. Missing reviewed release registration is displayed as `REVIEWED_OBSERVED_RELEASE_NOT_REGISTERED`, not hidden behind a request to turn on the robot. Scene/link/revision binding and a fresh expiring click are checked again before the shared worker starts. A failed durable chat save cannot start a worker. Duplicate requests, reload and polling do not repeat inspection.

One explicit question approves at most 45 seconds of local survey and photo alignment only. It does **not** approve goal travel. After a failure or expired choice, **Refresh inspection readiness · no robot command** can create a fresh question without running another check, collection or mission. The previous failure and raw/report history remain unchanged. The robot's local admission checks still run on a future mission; LINKED alone is not physical authority.

## Explicit survey contract

The additive `observed-mission-scope-4.0` contract requires `SURVEY_ONLY`, a zero placeholder XY, no prior reference/alignment and a checked nominal room. That placeholder is not a destination. Legacy v1/v2/v3 scope rules and old navigation modes remain separate; old v2 cannot accept the new mode. App, remote scope packaging and robot-local factory dispatch recognize the new mode.

The shared cold-start implementation surveys, returns locally, fits independently held-out observations while publishing zero, then requires a fresh tracking candidate from current odom/scan. Finite pose/transform, current source identity and existing sensor/input guards are checked. `VERIFY_SURVEY` ends in `SURVEY_COMPLETE_NO_GOAL_COMMAND`; it never creates the placeholder goal route. Internal shared-loop terminal `MISSION_ARRIVED` is exposed as **SURVEY_COMPLETE** only with the survey-complete diagnostics, alignment candidate and saved report.

This new survey-only mode is **align_only**. Bounded wall correction/derived revision remains supported by the older survey-then-goal path but has not yet been connected to the new survey-only chat task. It is not silently inferred or marked complete.

Local offline reports preserve the actual fit result and survey map/keyframes as well as decisions and observations. The remote align-only path currently supplies visual/diagnostic events, not the full fit/map report transfer; that remaining transport integration must be completed before claiming full field analysis/replay readiness.

## Status and stopping

The English chat shows the inspection task, stage, view count, alignment reason and original/cleanup/report faults. Faults produce the existing dismissible global error alert. Summary observations are refreshed at five-second intervals, with immediate state/fault changes. An unavailable current battery reading remains NOT_OBSERVED; the separately labelled preparation voltage snapshot is not substituted for live task telemetry.

Terminal pose is historical: chat clears current pose/scan and never grants future navigation permission from it. Active public visuals also expire after 200 ms without a fresh update; a stalled worker cannot keep an old pose labelled current. The task retains its original scene identity even if the current chat room subsequently changes. Cleanup or report-save failure cannot become a completed inspection.

The existing authenticated robot Stop endpoint routes an owned active inspection directly to the mission worker, independently of chat persistence, LLM or renderer. Ordinary Stop requests the existing bounded segment finish; Force STOP can supersede it. Requested and confirmed stop are distinct, and ordinary Stop is never automatically promoted to Force STOP. Existing scan 200 ms, input 250 ms, segment 50 ms, autonomous 0.03 m/s, 0.20 rad/s and 45 s limits are unchanged. No physical braking claim is made.

## Verification

| Check | Result and boundary |
| --- | --- |
| Related Python group | 85 tests PASS in 138.868 s: existing chat/preparation, automatic saved analysis/photo/comparison/display and old observed/correction contracts. Explicit classes avoid imported-test duplication. |
| Mission and survey group | 21 tests PASS in 281.287 s: new survey contract and current-room chat cases plus existing automatic mission and cold-start correction/navigation regressions. Output-reactive synthetic observations; not physical qualification. |
| Final focused API/status | Five tests PASS in 4.575 s, including independent Stop despite chat save failure, no automatic escalation, terminal historical pose and active 200 ms expiry, cleanup/storage failure, fresh readiness, stale/expired confirmation and missing target registration. Three overlap the prior mission group; do not sum these groups as unique tests. |
| Preserved survey evidence | Two tests PASS in 44.179 s; two different room scales/start positions run the actual shared controller, held-out fit and fresh tracking checks. Each saves command/raw observation and mission report files. No injected success/transform or goal route; final command zero. |
| Web | 40 files / 305 tests PASS; TypeScript and Vite build PASS. Existing >500 kB bundle warning remains. Fresh Build, receipt/snapshot ordering, unknown delivery/no retransmission, unavailable engine and restored-history no auto-Build have unit coverage. |
| Actual Chrome and local API | Final preparation/collection/inspection ten cases plus existing chat six cases PASS. The inspection fixture starts exactly one SURVEY_ONLY worker, displays admission failure, explicitly refreshes a question and reloads without repetition. Desktop/mobile inspected; sensor/robot/engine observations are fixtures, not actual Isaac or robot evidence. |
| Final identity | Both final receipts bind 41 source and four built-Web SHA256 values; compare against the final checkout before handoff. Scoped whitespace check PASS; existing CRLF notice is not failure. |
| External execution | Physical tests 0; actual Isaac runtime and ROS/C++ target build NOT_RUN in this increment. |

Final browser receipts:

- `artifacts/chat-inspection-20261005-final06/verification.json`
- `artifacts/chat-c1-20261005-v294-final05/verification.json`

Preserved synthetic raw/report pairs:

- `artifacts/demo-preflight/v294-survey-only/5043faf2867341c2a37ede1840085ddf/`
- `artifacts/demo-preflight/v294-survey-only/d1abdecd8ecd4b2d95edf42dd96b3752/`

Each folder has `synthetic-raw.json` and `mission-report.json`. Private raycast truth is a test fixture, not live robot odometry or measured map ground truth. The files explicitly identify that boundary.

Earlier browser runs remain intact. The first inspection browser assertion looked for a dialog although the existing popup uses an accessible alert; the actual cause was visible, the locator was corrected and the final run passed. Initial test bootstrap/fixture mistakes, a missing canonical hash import and local temporary-directory permission failure were corrected without physical operations or installation. Older receipts bind earlier source snapshots and are not final acceptance.

## Remaining implementation in order

1. **Continue C4 without robot power:** current generated-room survey-only wall correction/derived revision and saved/remote fit-map replay; preserve original geometry and ambiguity/failure.
2. **C4 goal task:** current observations → semantic target → constrained route/actual SIM demonstration → exact digest/revision-bound Confirm → existing robot-local mission. Do not use terminal survey pose as a current navigation lease. Add end-to-end changed start/direction, hand relocation, symmetry, new obstacle, changed photo, delay/drop, storage and cleanup cases through the App path.
3. **C4 viewer and diagnosis:** current/sensor map versus photo model, correction/revision-aware live 3D, mismatched saved-photo diagnosis and narrowly scoped missing-information questions. This increment's summary and active visual hooks do not complete that acceptance.
4. **C5/C6:** persistent bounded-leg A↔B TaskLoop with battery/stall/obstacle/transport/storage/Stop policies, then same-package full SIM and separately authorized REAL acceptance.

C1/C2/C3/C4 remain PARTIAL; whole readiness stays false. Full moving field-suite, reviewed target binary/protocol/profile and measured field evidence remain C3 gaps. Target build/WSL permission blockers are not bypassed; they do not block the next independent offline C4/C5 implementation. Preserve dirty changes, user photos/raw originals, historical failures, v1/v2 hash/serialization and physical mission locks. No request for robot power is needed yet.
