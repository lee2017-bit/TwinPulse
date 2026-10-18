# Chat stationary collection and raw-transfer recovery

Baseline v1.0.293, 2026-10-05 KST. The existing chat now connects the existing no-motion collector and saved-file recovery services. This completes this collection/recovery integration bundle, **not all C3 or the physical demo**. The robot remained OFF. No SSH, serial, deployment, real sensor/motor operation, paid call, installation, commit/push or new agent was used for verification.

## Connected behavior

In a configured REAL Burger project, the chat offers one explicit stationary source-transfer/collection action. It uses the existing `RobotReadiness` and `scripts/run_robot_readiness.py`: local preflight → reviewed source preparation and idle observation → bounded passive odom/scan/TF collection → offline analysis. The future field action may transfer reviewed project source; it does not automatically start the LiDAR driver, enable motors, drive, align the room or unlock a mission. Read-only connection testing remains a different, non-deploying action. Rendering, polling, reload and old history do not trigger either collection or recovery.

The chat shows four collection stages and individual odom, scan, tf and tf_static outcomes, including available machine reasons and fault counts. Acquisition, analysis and raw export are separate:

- An interrupted raw transfer no longer hides collected sensor diagnostics. Safe local analysis continues when the saved observation is available, without another robot operation. The original collector failure remains unchanged.
- Changed boot/release identity retains observations as unbound evidence, never current-coordinate evidence. A missing publisher or rejected odom is not a PASS.
- A failed prerequisite prevents dependent robot work. Unexecuted stages explain their dependency; known local preflight failure is `BLOCKED_LOCAL`, not an invented uncertain remote state that requires power cycling.

Collection invalidates the chat's old link/qualification question because reviewed source can change. Sensor records and transfer completion never grant physical authority: `motion_authorized=false`, `alignment_verified=false`, `demo_ready=false` remain.

## Transfer-only recovery

The chat can resume the current saved stationary report, or the owned saved qualification's existing raw export. The stationary route derives the report path on the server from the saved collection job; a client cannot supply arbitrary paths. It validates the bounded preparation artifact path, symlinks, report schema/action/no-motion boundary, run identity and size. A fresh, expiring request and durable fsynced reservation are required before a transfer worker starts. Replayed requests and backend restart do not automatically start a transfer.

Stationary recovery invokes the existing `prepare_robot.py --mode resume-evidence --saved-report <validated report>` only. It does not invoke preparation/collection again, driver start, Motor OFF or movement. The report SHA is checked before and after transfer. COMPLETE requires the same-run binding, copied-file outcomes and verified offline raw replay; a timeout, changed source, invalid receipt or save failure retains an explicit cause. Recovery does not overwrite the original collection result or physical qualification failure.

The English UI distinguishes **Initial raw export: INCOMPLETE** from **Recovery: COMPLETE**, explains that the original failure is historical and removes the completed recovery button. A failed recovery still shows its reason and preserves sensor faults. Shared robot-operation gates block simultaneous collection, qualification, diagnostics and raw recovery, including another owner's active recovery thread hidden from the scoped snapshot. Existing independent Stop and Force STOP behavior is unchanged.

## Final verification

| Check | Result and boundary |
| --- | --- |
| Related Python regression | 154 tests PASS in 56.778 s: chat preparation/conversation, diagnostics, physical transport/HTTP, readiness service/HTTP/CLI, export and recovery. Explicit fake runners/transports, local API and real persistence/orchestration; no robot transport. |
| Web regression | 39 files / 301 tests PASS. TypeScript and Vite production build PASS; existing >500 kB bundle warning remains. |
| Actual Chrome / built Web / local API | Nine scoped cases PASS: normal, SSH failure, release mismatch, stop+cleanup failure, operator problem, Stop during qualification, stationary collection+recovery, recovery failure and local preflight failure. Robot and collector replies are explicitly offline fixtures. |
| Existing chat browser regression | Six cases PASS: image, text, REAL/unconfigured backend, generation failure, cancellation and saved edits. Generation is an explicit fixture, not paid/photo inference. |
| Final source/build binding | Each final receipt's 30 source / four built-Web SHA256 values match the checkout. Harnesses completed and closed their owned servers/browser sessions. Desktop/mobile collection screenshots inspected; collection/transfer and current-frame absence remain explicit. |
| Whitespace | Scoped `git diff --check` PASS; existing CRLF notice is not a failure. |
| Isaac, target build and physical acceptance | Isaac runtime NOT_RUN in this increment; ROS/C++ target build NOT_RUN; physical tests 0. |

Final receipts:

- `artifacts/chat-collection-20261005-final02/verification.json`
- `artifacts/chat-c1-20261005-v293-final03/verification.json`

The collection case runs one stationary fixture and one transfer fixture, then reloads without repeating either. Original export INCOMPLETE and odom/scan gaps remain after recovery COMPLETE. Python regressions additionally cover reservation-save failure, source mutation, unverified COMPLETE, wrong/outside report binding, restart/no replay and another owner's active transfer. Qualification/Stop tests retain their earlier scope and safeguards.

Reproduce using the existing runtimes, with a fresh output directory:

```text
python -B scripts/verify_chat_c1.py --robot-cases --output artifacts/<fresh-collection-output>
python -B scripts/verify_chat_c1.py --output artifacts/<fresh-chat-output>
```

In `apps/twinpulse-web`, run `pnpm test` and `pnpm build`. The browser options above use offline fixtures only; they are not the field entrypoint. Related Python classes are `ChatRobotTests`, `ChatConversationTests`, `RobotDiagnosticsTests`, `TransportTests`, `PhysicalHttpTests`, `ReadinessServiceTests`, `ReadinessHttpTests`, `ReadinessTests`, `EvidenceExportTests`, `RecoveryTests` and `RecoveryHttpTests` in the existing integration modules. Select classes explicitly to avoid imported test duplication.

## Failed attempts retained

Initial regressions exposed identity-mismatched evidence being treated as current, an obsolete expectation that export failure must skip local analysis, an incomplete fake export receipt and a TypeScript fixture type error. These were corrected before final acceptance. A final cross-owner guard patch initially had an indentation error; import failed without starting any operation, then the indentation and dedicated regression were fixed. Earlier browser receipts remain preserved as intermediate source snapshots; only the final receipts above bind the final code. No failed attempt was converted into physical success or an original raw report rewritten.

## Remaining implementation and field boundary

1. **C3 is still partial:** this bundle connects stationary passive collection and saved transfer recovery, not the full moving field-suite DAG. Reviewed target binary/protocol/profile qualification and measured mounting/footprint/timing evidence remain. Passive collection cannot promise `/scan` when its driver is off.
2. **Next independent C4 work:** connect the current generated chat room, not an old sample, to survey-only execution, current-session alignment/correction, semantic goals, digest-bound route preview/Confirm and existing robot-local mission/3D/status paths. This offline integration can proceed without robot power or waiting for the target-build blocker.
3. **C5:** persistent A↔B TaskLoop with battery/stall/obstacle/transport/storage/Stop boundaries; not browser timer-based repeated Start.
4. **C6:** same-package full SIM and separately authorized REAL acceptance. Actual telemetry, measured profile and field outcome remain required. C1/C2 retain their previously documented partial status; whole readiness stays false.

Previous native ROS/C++ PATH/WSL permission blockers are not bypassed or reclassified as success. Photos, raw originals, dirty work, old failures, v1/v2 serialization/hash, physical mission locks and scan 200 ms / input 250 ms / segment 50 ms / 0.03 m/s / 0.20 rad/s / 45 s limits are preserved. Heartbeat remains PAUSED. No robot-power request is needed for the next offline implementation.
