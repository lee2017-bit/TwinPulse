# Chat-driven demo C1 implementation and evidence

2026-10-05 KST · Baseline v1.0.282 · `C1_SCOPED_BROWSER_API_PASS / C1_PARTIAL`.

## Outcome and boundary

The normal App now opens a chat workspace, not the former multi-form dashboard. Text/image input, inline robot-presence and Burger-selection questions, generation, saved history, project navigation and bounded furniture edits use the existing authenticated App and ProductWorkflow. No alternate generator or robot-control server was introduced.

This is not the complete 12-step demo. The embedded live Isaac viewport, v2 physics Run, qualified physical connection, survey/path confirmation, live summaries and TaskLoop remain later implementation work. The real provider was not called; physical tests and deployment were not performed. Whole-demo readiness remains false. The passing browser fixtures below exercise actual built React and the actual local API with an explicitly identified deterministic provider, not a real photo interpretation.

## Implemented product behavior

- A light English chat-first layout, typed inline question buttons, image picker/drop/paste/thumbnail/removal, Enter/Shift+Enter/IME handling, persistent text draft, collapsible Twin pane and mobile chat-first view. WASD in the composer has no physical-control handler.
- Q1 waits for Simulation only or Use my robot. REAL requires the registered Burger choice Q2 before scene generation; it does not contact the robot or pretend C3 is ready. Clear text answers to Q1/Q2 are also supported; they are not physical approvals.
- Accepted intent is journaled before starting the existing generation service. Request IDs are bound to body digests; duplicate requests query the same result and a conflicting body is rejected. Response loss triggers observation, never automatic resubmission. An absent receipt remains Delivery unknown rather than falsely proving non-execution.
- Project-scoped messages, cards, event cursor, request ledger and generation history persist in an atomic conversation sidecar. Images are validated by the existing input validator; public polling contains metadata and authenticated thumbnail URLs, not raw base64. The generic release allowlist does not copy project conversation/data sidecars.
- Restart preserves questions and outcomes but interrupts an in-flight generation without resuming it. A corrupt nested record is preserved and mutations are blocked with a visible cause. Storage failure is reported and does not restart an accepted operation. The write budget is bounded to the same 20 MiB restore budget.
- New protects an existing scene. Projects creates a separate empty project and Open requests the existing owned-launcher switch; active jobs block switching with a reason. The current project is not replaced by creation. Lost create responses are checked in the catalog without repeating the write.
- Saved v2 scenes can reopen through the existing revision/input-bound review path. Add/Change currently accepts one furniture kind with explicit `x=`, `y=` and optional `yaw=`. The server previews/validates an edit and requires Apply edit or Cancel in the conversation. The original scene, image and non-target objects are preserved.
- One text Add/Change request can be queued during generation. It does not replace the current job; only after terminal state and worker cleanup is a review preview offered. Restart does not execute a pending edit. Missing placement is clarified, not inferred as measured geometry.
- Input changes outside the conversation invalidate old Q1/Q2 cards instead of silently replacing the newer input. Scene-edit cards carry operation and parent-revision bindings; stale apply is rejected without changing the scene.
- Provider, engine, storage and edit failures remain visible in the conversation and a deduplicated error banner. Dismissal does not resolve them. Cancellation is visible immediately while worker cleanup is tracked separately. A browser-discarded response is not another server failure or a repeated mutation.
- The runtime checklist uses actual launcher observations: configured executables/extension/Web presence, pinned-version metadata, free space, an owned temporary flushed-write probe, engine/provider state and explicit pending viewer/robot scope. Existing cancel-startup and limited owned restart controls are connected. No installer or permission change runs.

## Verified evidence

| Check | Result | Scope |
| --- | --- | --- |
| TypeScript and Vite build | PASS | Existing dependencies; final JS 523.79 kB / gzip 153.93 kB. Existing >500 kB warning retained. |
| Full Web regression | 266/266 PASS, 35 files | Includes existing LegacyApp coverage, English-default guard and new chat/project cases. |
| Selected Python integration regression | 76/76 PASS | Conversation, startup checklist, R5 API, R6 process manager, HTTP rejection/delivery. |
| Built Web + authenticated API | Six scenarios PASS, 34 grouped checks | Image+text, text-only, REAL Q1/Q2, provider/engine failure, cancellation, saved v2 Add/Change. |
| Owned startup failure/retry browser | PASS | Actual local backend and owned engine process intentionally unable to import Isaac; failure attributed to `isaac_import`, diagnostics/retry request/new owner and ticket verified. Successful Isaac recovery is NOT_RUN. |
| Target ROS/C++ build availability | UNAVAILABLE / NOT_RUN | Existing compiler commands not found in current PC path; no installation, WSL permission workaround or robot build attempted. |

Actual Chrome sizes: 1920×1080, 1280×800, 390×844. Browser assertions verify Q1/Q2 gating, reload of question/thumbnail/outcome, accepted-response loss recovery with one POST, separate project creation and explicit switch request, Add apply once/Change cancellation, failure dismissal without resolution, cancellation history, Shift+Enter/IME, and incoming events without reading-scroll/composer-focus theft. Screenshots were inspected locally. No browser exceptions were recorded in the six passing cases.

- Source and final Web hashes: `artifacts/c1-chat-20261005/verification.json` (listed source scope only).
- Per-case browser results, public conversation/workflow outcomes and screenshots: `artifacts/c1-chat-20261005/{image,text,real,failed,cancel,saved}/`.
- Startup diagnosis, owned cleanup and retry evidence: `artifacts/c1-startup-final-20261005/result.json`.
- Historical failed browser attempts are retained under `artifacts/c1-chat-20261005/failed-attempts/`. Intermediate failures included an unapplied delay fixture and an ambiguous test locator matching both historical and current Cancel buttons. They were fixed without relaxing acceptance. A terminal/cleanup race exposed by Python regression was corrected in the service. The English guard and TypeScript target failures were fixed without changing their checks or runtime target.

## Remaining implementation, not a request to power the robot

1. Close the remaining C1 gaps: broader natural edit/staging integration in the chat path, complete prerequisite/manifest and reviewed self-repair matrix, UI details for all error/timeout variants and owned project-switch success with actual Isaac. Existing drag/rotation editor remains in Advanced tools; it was not claimed as chat-first placement acceptance.
2. C2: connect the same stage to an authenticated continuous viewport and real v2 robot physics Run, natural goals and simulation Stop. No static screenshot or paused-physics receipt may substitute for this acceptance.
3. C3–C5: registered-device parallel readiness/qualification cards, survey-only inspection, simulation route preview then physical Confirm, 5-second summaries, and a persistent TaskLoop with bounded children. Existing physical locks and limits stay intact.
4. C6: same final packaged source/build full matrix and a separately authorized field bundle. The previous v279 package evidence is historical and not a package verification of these new chat sources.

No robot data was needed for the verified C1 work. Powering the robot does not resolve unfinished C1/C2 product work or the target-build/measurement/profile gates.

## Reproduction commands

Use the existing bundled Python, existing Node/pnpm and Chrome; do not install anything to reproduce. Set `TWINPULSE_TEST_TMP` to an owned directory under this repo for the existing integration harness.

```powershell
pnpm --dir apps/twinpulse-web run build
pnpm --dir apps/twinpulse-web test
python -m unittest tests.integration.test_chat_conversation.ChatConversationTests tests.integration.test_chat_startup_checks.StartupChecklistTests tests.integration.test_r5_product_api.R5ProductApiTests tests.integration.test_r6_process_manager tests.integration.test_http_rejection_delivery -q
python scripts/verify_chat_c1.py
python scripts/verify_startup_failure_browser.py --artifact-dir artifacts/c1-startup-new-attempt
```

The browser runners own and clean up only their isolated API/Chrome/launcher processes. `verify_chat_c1.py` makes zero paid calls and never contacts a robot. The startup runner intentionally uses a non-Isaac Python; its failure/retry PASS is not successful simulation execution.
