# Chat-driven robot preparation

Baseline v1.0.292, 2026-10-05 KST. The existing chat now connects robot selection to the existing read-only diagnostics and fixed qualification controller. This is a tested C3 integration increment, **not completion of C3 or the physical demo**. The robot stayed OFF: no SSH, serial, deployment, sensor or motor operation ran in this work. No paid calls, installation, commit/push or new agents were used.

## Connected product path

1. In a configured REAL project, selecting Burger starts one read-only connection check alongside room generation. The check observes PC prerequisites, SSH/board, battery and reviewed release identity. Rendering, polling and reopening never start it again. An unconfigured backend reports `PHYSICAL_PREPARATION_NOT_CONFIGURED` instead of pretending a check is running.
2. Fresh, matching boot/release evidence and idle/battery conditions produce a chat question for one bounded forward-and-stop trial. The selected qualification click has a short expiry and a durable idempotency record before the worker starts. A current matching passed stop record is reused; failed records are not rewritten as PASS or automatically retried. Source mismatch does not trigger deployment.
3. The existing `PhysicalController` receives exactly one `qualify` input and bounded keepalives. Results, cleanup, local journal and raw-export outcomes remain separate. A passed current trial produces one observation question. The user's normal/problem answer does not send a motor command. Problem reports stay latched for the same boot/release.
4. `LINKED` means connection/stop evidence has been reviewed, not current navigation authority. `physical_authority=false` and `demo_ready=false` remain. Sensor absence, room calibration, autonomous admission and target-binary qualification are not implied by a board snapshot.
5. A saved REAL project can explicitly request a fresh read-only check after backend restart without generating the room again. Old qualification questions expire; history never restores transport ownership or motion permission.

The adapter is `packages/twinpulse_app/src/twinpulse_app/chat_robot_preparation.py`, wired through the existing `api.py` and `conversation_service.py`. The English chat uses `ChatRobotStatus.tsx`; existing advanced diagnostics/manual control remain available. Battery is labeled as a voltage-based snapshot, not measured capacity or live telemetry.

## Stop and failure behavior

The authenticated `/v1/product/conversation/robot/stop` route bypasses conversation persistence and provider work. It reaches the existing owned qualification, manual or mission worker, but does not create a new SSH/off task when no owned worker is active. Ordinary Stop sends `finish_stop`; Force STOP sends `force_stop` independently, including while an ordinary request is pending. Sequence reservation uses the controller lock so a concurrent keepalive cannot invalidate Stop as old input.

Ordinary Stop waits for the worker's cleanup without silently escalating to Force STOP. Cleanup wait is bounded; unconfirmed cleanup is reported as such. The browser request has a 1.5-second delivery timeout, not an assertion that the robot physically stopped. Global Force STOP remains accessible when the mobile Twin pane hides the chat. Both physical stop modes retain their existing worker/robot guard semantics.

Failures identify their stage and cause: PC prerequisites, SSH connection, reviewed release, board/battery, stop qualification, operator problem, changed identity, save failure and cleanup/export failure. A missing sensor is not made into a coordinate/alignment PASS. First failure and cleanup failure are preserved separately. Reply loss/reload does not replay qualification. Failed connection does not cancel independent room generation.

## Verification

| Check | Final result and scope |
| --- | --- |
| Python scoped regression | 98 tests PASS across chat preparation/conversation, diagnostics and existing physical transport/HTTP classes. Includes delayed ordinary-Stop cleanup without Force escalation. |
| Existing PC controller | Injected fixed child transport exercised the real `PhysicalController` orchestration and saved `session.jsonl`, `robot-report.json` and `result.json`. `real_transport=false`, `physical_verified=false`; not a robot runtime test. |
| Web regression | 39 files / 299 tests PASS; TypeScript and Vite production build PASS. Existing >500 kB bundle warning remains. |
| Actual Chrome / built Web / local API | Six preparation cases PASS: normal, SSH failure, release mismatch, failed stop+cleanup, operator problem and Stop during qualification. Explicit reactive offline robot transport; mobile/reload/no-repeat checks included. |
| Existing chat browser regression | Six cases PASS: image, text, REAL selection with unconfigured backend, failed generation, cancellation and saved edits. Explicit offline generation fixture; no paid model or Isaac runtime. |
| Final bindings | Both final receipts' 25 source and four built-Web hashes match the checkout. Test-owned servers and Chrome processes closed by their harnesses. |
| Whitespace | `git diff --check` PASS; existing CRLF notices are not failures. |
| Isaac / robot / target build | Isaac runtime NOT_RUN, physical tests 0, target ROS/C++ build NOT_RUN. |

Final receipts:

- `artifacts/chat-real-preparation-20261005-final02/verification.json`
- `artifacts/chat-c1-20261005-v292-final02/verification.json`

The normal browser case recorded one `READ_ONLY` collection, one `qualify` worker and one `qualify` input. The Stop case ended `STOPPED`. The mobile normal-result screenshot was inspected: chat result, explicit snapshot/test labeling and global Stop are visible without horizontal clipping.

Reproduce with the existing local Python runtime and these repository-root commands; these browser options use only explicit offline fixtures:

```text
python -B -m unittest tests.integration.test_chat_robot_preparation.ChatRobotTests tests.integration.test_chat_conversation.ChatConversationTests tests.integration.test_robot_diagnostics.RobotDiagnosticsTests tests.integration.test_physical_controller.TransportTests tests.integration.test_physical_controller.PhysicalHttpTests
python -B scripts/verify_chat_c1.py --robot-cases --output artifacts/<fresh-robot-output>
python -B scripts/verify_chat_c1.py --output artifacts/<fresh-chat-output>
```

In `apps/twinpulse-web`, run `pnpm build` and `pnpm test`. Output folders must be fresh. The existing field-suite entrypoint was not replaced by another field script.

## Preserved failed attempts

The `...-01` robot browser matrix failed because the mobile Twin pane hid chat controls; a separate initial-state typing race also appeared. Global Force STOP and authenticated-state waiting were added. The older `...-02` and `...-final` robot receipts belong to intermediate source snapshots. The old `chat-c1-20261005-v292-final` REAL case failed on an obsolete assertion expecting an integration-pending message; it now checks the explicit unconfigured-backend state. All these artifacts remain intact. Only `final02` receipts bind the final code.

A final review also found that adapter cancellation could upgrade ordinary Stop to Force STOP while cleanup was pending. The delayed-cleanup regression now proves it does not. No failed attempt was converted into physical success.

## Remaining work, in dependency order

1. **C3 remainder:** chat actions for full bounded collector results and interrupted raw-transfer resume, including independent safe checks after a dependent failure. The current chat displays existing journal/export/recovery results but does not provide that full collection/resume orchestration. Validate reviewed binary/release/protocol/measured profile identity before asking for field time.
2. **Target build blocker:** read-only tool inventory found `wsl.exe`, but no native `cl.exe`, `gcc.exe`, `g++.exe`, `colcon` or `cmake` on PATH. Previous WSL `Wsl/Service/E_ACCESSDENIED` was not bypassed or retried. This does not certify every installed tool location as absent. No candidate was built or deployed; target-build acceptance remains NOT_RUN/BLOCKED, not a mock PASS.
3. **C4 offline integration:** connect the current generated room to `survey_only`, current-session alignment/correction, semantic goal and digest-bound preview/Confirm, existing robot-local mission and current 3D/status updates. Do not use the old sample room as if it were the current chat room.
4. **C5 offline integration:** persistent A↔B TaskLoop with battery/stall/obstacle/transport/storage/Stop boundaries; not a UI timer repeatedly pressing Start.
5. **C6 acceptance:** same-package full SIM and authorized REAL field matrix. Fresh real telemetry/coordinates and the measured profile are still required; turning on the robot alone is not enough.

Independent C4/C5 offline work does not require robot power and need not wait for the external target-build blocker. C1/C2 remain partial in their previously documented scope. Whole readiness and physical mission locks remain false/locked. Raw photos, history, existing dirty work, v1/v2 contracts, scan 200 ms, input 250 ms, segment 50 ms, 0.03 m/s, 0.20 rad/s and 45-second mission limits are unchanged. The existing heartbeat remains PAUSED.
