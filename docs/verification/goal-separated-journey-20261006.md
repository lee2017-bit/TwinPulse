# Separated App, actual Isaac and native goal journey

**Current follow-up:** Baseline1.0.305 passes the final actual separated two-goal journey, reload/delayed-data refusal, five archive reviews and normal cleanup, with selected Python165/113.903s and41 frozen sources. Synthetic qualification only; physical0/C4 PARTIAL/whole readiness=false. See [current verification and remaining work](goal-separated-latency-20261006.md). The v304 failures and results below remain historical evidence, not the current acceptance result.

This increment connects the existing built chat UI, separate App backend, authenticated Bridge and existing Isaac runtime to a local native worker with reactive **synthetic** sensor observations. It does not qualify a physical robot, localization accuracy or a deployment. Physical qualification is an explicit isolated test double; the production qualification gate remains closed without target evidence.

**Final-source selected regression PASS; separated actual journey FAIL. C4 remains PARTIAL; whole readiness=false.** Robot connections, SSH, serial, real sensors/motors, deployment, paid calls, installs, settings, commit/push and new agents are zero. Original survey bytes, existing dirty edits and all failed attempts are retained. Heartbeat remains PAUSED.

## Connected fixes

1. An explicit goal preview owns a bounded engine lease and waits for the Bridge's Build permit. Polling/restore cannot acquire or resurrect a lease; another owner's lease is never taken over. Stop, close and terminal execution stop this keeper. Its bounded review lifetime does not reset the native 45-second active budget.
2. Full observation decoding and validation no longer hold the controller input/Stop lock. The receiver rechecks the exact query, job, scope and stop state before publishing. All processing time remains inside the freshness bound. Late data can remain raw evidence but cannot restore a current pose after Stop.
3. Per-tick receipt checking no longer reloads the full room, photo and Burger assets. The independent source fingerprint still checks the current room token, project geometry/assets and correction ledger. Initial admission fully reopens the scene; changed source, engine, lease, stage or Stop rejects execution. Only `project.conversation.json` is excluded from geometric fingerprints: writing a chat answer is not a room edit.
4. Accepted native idle keepalives now retain their sequence/action/source age, just like the driving loop. PC generation/write and robot acceptance use explicitly separate clock domains; absolute PC and robot clocks are not subtracted.
5. Reviewed-goal motor preparation is a zero-output tick. After arming, the native worker rechecks sensor/source/age and returns zero; the owning loop pumps input and receives new observations before the next movement decision. Already-enabled reviewed ticks avoid redundant arming/duplicate decisions. The first nonzero boundary still validates the original review and current sensor envelope. Gate, command timestamp, mission budget, 200ms scan/pose, 250ms input, 50ms segment, .03m/s/.20rad/s limits are unchanged.
6. That additive preparation reason is accepted only as a zero-output adaptive decision with the existing strict navigation evidence shape. Legacy decision reasons remain unchanged. Unvalidated current pose/scan/route stay absent; historical trajectory remains available.
7. Failed return admission records query, upper-bound evidence age, full round trip and elapsed time since receipt before cleanup closes the journal. Handoff failures record the substage and original cause. No retry, re-stamp or saved-pose substitution is introduced.
8. The adopted exact-goal worker now has an independent scoped watch sender. Report/event copies cannot block its input renewal. It runs the same owner/source/engine checks, reads latched Stop again under the sender lock, permits Force STOP escalation and preserves the original guard failure. The old idle keeper is stopped on adoption; its final sequence read/write is atomic. No automatic reconnect, fresh budget or wider authority is introduced.
9. Receiver validation rejection retains decode/binding/commit-wait timings and the conservative evidence age before cleanup. These diagnostic clocks never change the freshness calculation or acceptance result.

## Test harness and boundaries

`scripts/verify_goal_separated_journey.py` starts only owned local subprocesses: existing Python App backend, existing Isaac host and existing headless Chrome. State/project/history/output roots are isolated. Test secrets stay in memory/environment and are excluded from result files. Normal owned stop files are used before bounded cleanup; unrelated processes are never terminated.

The browser uses actual built UI goal text and Confirm buttons. Intended acceptance is two distinct exact Isaac Build/Run/Pause reviews, fresh native handoff/arrival using the same approved route, reload without a new worker/Build/Run/current pose, and delayed observation rejection without motion or retry. Terminal failure is now reported immediately instead of waiting out an arrival timeout. The verifier freezes 22 runtime/fixture sources plus the built Web files and also requires the actual engine's final result.

The synthetic link's first arming spin generates new causal raycast and odometry samples at zero velocity, matching the real callback servicing pattern. It does not re-stamp an old frame or give the matcher the private world pose. Separate stable-estimator doubles remain explicitly test-only negative-test fixtures; they do not qualify measured localization.

## Preserved failures and what they establish

All attempts remain under `artifacts/verification/goal-separated-20261006-01` through `-13`. Earlier source versions are historical, not final-source acceptance. Final diagnostic/test additions after 13 were verified by the regression below, not by another actual runtime attempt.

- 01: owned launch/sandbox browser exit without a result; not product acceptance. A read-only ownership check later confirmed its owned Kit had exited.
- 02: harness lacked an isolated engine state root and read a legacy project; corrected in the harness without modifying that original. UTF-8 result reading was also corrected.
- 03–06: actual Isaac/UI preview reached completion, but current observation/admission or native input expiry rejected movement. Bulk lock and repeated full-room loading were identified in the PC path and corrected. One run overlapped regression CPU load; later runs were isolated. Failures are not dismissed as Wi-Fi faults.
- 07: native `NAVIGATION_OBSERVATION_MISSING`, zero movement output and confirmed cleanup. Matcher measurements were about 47ms, not evidence of a 500ms estimator. This supported separating preparation and fresh first output, not weakening limits.
- 08–10: mixed fresh-query age and native input-expiry failures remained. In 10, a query had a full PC round-trip upper bound of about 171ms and a sample already about 20ms old; a later caller correctly rejected it after the 200ms bound. Receiving a raw packet is not enough to call its pose current. Native output stayed zero and cleanup was confirmed.
- First 92-test expanded regression after preparation splitting: five failures on `INVALID_SESSION_EVENT`; the new zero-output reason/navigation evidence had not been connected to the strict log validator. This was fixed without accepting a moving preparation event. The corrected focused 47-test run passed.
- 11: PC watch generation had a 266ms gap while native accepted-input gaps were about 125ms. Reporting and renewal shared one loop; the independent scoped sender separates them. This identifies a PC scheduling boundary, not a Wi-Fi cause.
- 12: actual built UI/Isaac preview completed, but a new Confirm query failed `GOAL_PREVIEW_CURRENT_EVIDENCE_STALE` before handoff. Raw receipt was retained, but receiver commit was too late; decode/binding/commit timing was added for the next attempt. Sources (22), built Web and owned-process exit checks passed. This does not yet establish the independent sender's combined-runtime arrival.
- 13: first actual built-UI/Isaac preview completed; Confirm's later fresh query failed `IDLE_OBSERVATION_SOURCE_OR_TRANSPORT_CHANGED` before handoff. The broad rejection branch was subsequently instrumented to distinguish transport time, source context, reference and authority. No claim is made that timing alone was definitively isolated in this attempt. Both synthetic peers retained zero nonzero movement outputs and confirmed wheel/sensor cleanup. Backend original-survey bytes and actual engine terminal checks passed; 22 source hashes and built Web matched; all owned children exited normally without forced cleanup. The overall browser journey remained FAIL and the second goal/reload/delayed-fault acceptance was not reached.

These are local synthetic scheduling/processing observations, **not measured Wi-Fi latency or target CPU performance**. They do not prove that powering the robot alone resolves the remaining integration issue.

## Regression and exact remaining work

- Initial selected 66-test run passed in 245.664s before later source changes; historical only.
- Intermediate 58 tests passed in 4.974s before the expanded run exposed the log-contract gap; not final combined acceptance.
- Corrected protocol and native-handoff selection: 47 tests passed in 59.805s, including reactive matcher/parked handoff arrival, Force STOP, post-enable pose change, lost SIM receipt and legacy gate cases; intermediate source version.
- Scoped-sender native selection: 10 tests passed in 69.767s, including deliberately blocking report recording for 350ms while fresh watches continue to reactive arrival; intermediate source version.
- Final frozen-source selection: **94 tests PASS in 118.380s; all 28 captured source hashes unchanged before/after.** Covers protocol, engine lease/receipt, room-source guards, reference transport, distinct rejected-query raw diagnostics, idle safety, exact native handoff/reactive arrival/Force STOP/receipt loss/pose changes/parked review and chat handoff lifecycle. Selection includes inherited/imported test classes; it is not the entire repository suite. Evidence: `artifacts/verification/goal-separated-20261006-final-regression.json`. Mission-runtime source is additionally frozen in the actual-attempt 22-source records.
- Built production Web source/dist is unchanged. The earlier v303 319-test/build result is historical; no new Web regression result is claimed here.

Remaining, in order:

1. Resolve/profile the reproduced fresh-query decode/commit/transport scheduling boundary under actual concurrent App/Chrome/Isaac load, preserving 200ms/250ms limits and original samples. This is local integration work; robot power or more target raw data is not needed to investigate it.
2. Pass the separated actual journey: two distinct exact SIM reviews and native synthetic arrivals, reload without replay, and delayed-observation rejection. Component tests do not replace this currently failing acceptance.
3. Complete goal progress summaries, C5 loop policy and C6 normal/failure product acceptance.
4. Separately review the target release/profile/frames/timing and perform bounded on-site acceptance under new explicit authorization. No physical readiness is inferred from an offline PASS.

The next local scheduling diagnosis should use the new stage timers and a scoped concurrent stack/profile capture, rather than repeated blind restarts or loosening freshness bounds. All owned test processes have exited; no automatic robot retry or background mission remains.
