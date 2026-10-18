# C2 Isaac viewport implementation evidence

2026-10-05 KST · Baseline v1.0.283 · actual viewer technical check PASS · C1 and C2 remain partial.

## Outcome

The existing owned Isaac host now sends fresh rendered frames to the default chat workspace. The authenticated right pane displays the current stage, supports eight registered camera actions, and removes old pixels when reception or stage identity is lost. This is an actual local Isaac and built React integration, not a slideshow or mocked renderer.

This check used a synthetic saved v2 room and the existing visual Burger asset. It did not generate a new interpretation of the user's photo, execute Physics Run, move a robot, or call a paid provider. The current chat does not yet automatically Build and Run every generated room. Whole-demo readiness remains false.

## Connected product path

The production `twinpulse_engine_host.py` schedules native Kit capture on the main thread. A separate display I/O thread copies one bounded RGBA buffer, encodes a bounded JPEG and uses the existing engine authentication. The App retains only the latest image in memory. Its metadata includes engine session, stage epoch, applied revision, frame ID, capture time, camera sequence and image hash.

The product API uses the existing session, Host and CSRF boundaries. Read-only frame reception and camera commands do not acquire or renew a control lease. Camera commands are an allowlist, not arbitrary code; they modify only `/World/TwinPulse/Presentation/Camera`. Sixteen recent metadata entries permit a click on a still-fresh displayed frame while a newer frame arrives; old image bytes are not retained. Camera requests expire, have bounded rate and idempotent request IDs, and are never automatically repeated after a lost response.

The React viewer starts only after App authentication. It runs one metadata/image request chain at a time, revokes replaced object URLs, and stops reception when the pane is folded. Source age of one second removes the displayed image even when a request hangs. Viewer errors and camera-operation errors are separate; a new successful image does not erase a failed camera command. Rendering does not grant physical authority or prove simulation movement.

Native buffer capture follows NVIDIA's [Kit capture callback documentation](https://docs.omniverse.nvidia.com/kit/docs/omni.kit.viewport.utility/latest/omni.kit.viewport.utility/omni.kit.viewport.utility.capture_viewport_to_buffer.html). The installed RC SDK callback and actual execution were checked; no new SDK, Docker streaming service or dependency installation was used.

## Defects found and corrected

- A static v2 room intentionally has no driven `/World/TwinPulse/Robot`. The existing production host nevertheless read its position and exited with `TwinPulse robot prim is missing`. Position observation now follows a compiled v1 driven scene only. A visual Burger does not become physical telemetry, and a missing driven v1 robot still fails loudly.
- Mounting the viewer before bootstrap completed caused a false session-expired error. App connection now gates viewer mounting; a regression verifies no early viewer request.
- Exact latest-frame camera binding could reject an otherwise fresh click when a new render arrived. Metadata-only history fixes this without restoring expired image bytes or accepting another stage/revision.
- Fixed-interval polling could waste a second interval after a slow response. A bounded sequential schedule preserves one in-flight request without that gap.
- A rapid sequence could enable the next camera button before the server's 200 ms rate interval, and the resulting error was erased by a new frame. The UI now waits conservatively after acceptance and retains camera errors independently. The server limit is unchanged.
- A successful camera-only transport poll could erase a GPU capture error. Capture and transport diagnoses are now kept separately in the owned host result.
- Interrupted image responses now close the response instead of attempting a second HTTP error response. This does not retry a mutation.

## Final verification

| Check | Result | Boundary |
| --- | --- | --- |
| Full Web regression | 270 tests in 36 files PASS | Includes authentication ordering, error persistence, expiry, legacy UI and English-default checks. |
| Selected Python integration | 83 tests PASS | Conversation, startup, R5/R6, rejection/delivery, viewer/API and capture-error preservation; not the whole repository suite. |
| TypeScript and Vite build | PASS | JS 527.55 kB, gzip 155.17 kB. Existing greater-than-500 kB warning remains. |
| Actual owned Isaac and Chrome | PASS | All eight camera actions, changed captures, collapse/expand/reload, reception loss/removal and read-only recovery. No Run or physical command. |
| Continuous display measurement | 5.62 FPS, p95 185.72 ms | Native image-load events over one four-second window on this PC; not an enduring performance guarantee or control deadline. |
| Final chat regression | Six scenarios and 34 grouped checks PASS | Built Web plus real authenticated API; deterministic provider fixture, not live provider acceptance. |

The final actual result is `artifacts/c2-viewport-20261005-10/result.json`; its browser report and three PNGs are adjacent. The host sent 72 frames, dropped zero queued buffers and reported no final display error. Browser observation recorded 52 distinct frames, metadata-source rate 6.18 FPS and no page exceptions. Eleven scoped source hashes and three built-Web hashes matched the final checkout.

The final chat regression is `artifacts/c1-chat-c2-regression-20261005-03/verification.json`. Its source/build receipt is distinct from the earlier C1 record, which is preserved. The runner now accepts a fresh output directory so repeating a regression does not overwrite that earlier evidence.

Attempts 01 through 09 are retained. They include fixture ordering, an unobserved lease/capability, the real missing-robot host failure, outdated C1 test selectors, and the rapid camera-rate failure. Attempt 07 passed functional viewer checks but measured 4.76 FPS, below the proposed five-FPS target; its result must not be promoted to a performance PASS. Final attempt 10 met the target in its measured window. No stop, scan, input, mission or physical acceptance threshold was relaxed.

## Remaining work in implementation order

1. Finish C2's separate executable SIM binding for the v2 room: asset articulation/collision inspection, versioned execution binding, actual Physics stepping, measured simulated pose, goal arrival and Stop. The current visual Burger has no proved Physics Run.
2. Connect normal chat generation and saved-room selection to revision-bound Build, asset choice, Run and natural-language goal/Stop cards. The current viewer technical test submits the existing Build API explicitly; it does not accept the full user journey 1 through 5.
3. Close remaining C1 staging, full prerequisite/approved-repair matrix and actual project-switch/restart UI acceptance. Broader viewer fault/load/mobile and source/package acceptance are also still needed; this receipt is not a new version of the v279 package acceptance.
4. Continue C3 qualification, C4 survey/path preview/physical confirmation/five-second summaries, C5 TaskLoop and C6 same-package/field acceptance. Real-photo mismatch, target compiler and measured sensor/body/profile gaps remain unchanged.

These first three items can proceed with the robot off. Robot power is not the current product-code blocker. Fresh on-site mission approval is still required before any future physical test. Robot contact, deployment, paid calls, installation, commit/push and unrelated process termination were all zero in this increment. The existing heartbeat remains paused.
