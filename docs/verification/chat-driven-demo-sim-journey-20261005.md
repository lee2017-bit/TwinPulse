# Fresh chat generation to SIM execution

2026-10-05 · Baseline v1.0.287 · selected offline C1/C2 journey PASS, not whole-demo acceptance.

Later v1.0.288 completes the pre-Run visual Burger and explicit Reset path; see [current evidence](chat-sim-burger-preview-20261005.md). Results and remaining statements below describe the earlier v287 source, not the latest complete product status.

## Outcome and evidence boundary

The existing chat product now connects fresh text or image input → inline robot-presence question → chosen SIM generation → checked illustrative spawn/route → automatic current-room Build → explicit Run → actual Burger PhysX arrival → next chat goal → chat Stop. Reload does not repeat Build/Run or restore Run approval. No robot is required for this path.

Generation responses came from an explicit local v2 room fixture through the real GenerationService validation path. Image upload, storage and request binding were exercised, but the fixture does not interpret pixels. The API, workflow, broker, compiler, owned installed Isaac runtime, renderer, built React application and Chrome interactions were real. This is neither a live LLM/photo-inference acceptance nor physical movement evidence.

## Product changes

- `simulation_goal.preview_review` searches bounded deterministic interior candidates and validates a short route through the existing clearance planner. It never assumes an unchecked origin. Exhausted/no-clear-route cases retain their exact rejection. Scene geometry and v2 serialization are unchanged.
- `ProductWorkflowService.simulation_preview` binds the current generated v2 revision and hash-checked existing Burger asset to the broker plan. An ephemeral same-revision SIM spawn supports the first chat goal; subsequent goals prefer current idle PhysX pose. Lost, stale and REAL contexts retain existing rejection rules.
- Conversation generation records its originating accepted request, creates one preview on successful SIM completion, and exposes the selected existing Burger plus English progress. The text-choice alias now carries the original request ID as well. Legacy v1 output remains legacy and reports that v2 is required; it is not silently converted.
- Only a locally acknowledged generation choice in the mounted chat can hand its matching completion to the Run card. Restored history and unrelated polling cannot prepare or execute a simulation.
- The card automatically acquires the existing lease, acknowledges and Builds the current generated room once, then waits for its matching applied/idle/capability/safety snapshot. It explicitly says when the Twin is ready. Run remains a separate user action. Busy/stop phases take priority over old Physics completion text.
- Auto-Build prepares and renders the room. The actual PhysX Burger is instantiated by explicit Run, not during generation. Pre-Run robot placement in the 3D render is still a visual requirement to finish; selection and the illustrative spawn/route are available before Run.

## Final validation

| Boundary | Final evidence | Result |
| --- | --- | --- |
| Fresh text Web/API/Isaac journey | `artifacts/chat-sim-journey-20261005-text-03/result.json` | PASS; goal residual 0.03966252634 m, simulation time 4.4667 s |
| Fresh image Web/API/Isaac journey | `artifacts/chat-sim-journey-20261005-image-01/result.json` | PASS; goal residual 0.03966288487 m, simulation time 4.5667 s |
| Each journey's source/build identity | 26 source hashes + 3 built Web hashes | All match final files |
| Actual frame delivery | browser receipts and arrival screenshots | 70/73 observations; more than 3 unique current-revision frames in each case; not a frame-rate guarantee |
| Browser interaction | both journey receipts | Q1 waits; one Build and zero Run before click; explicit arrival; current-pose goal; Stop while Twin folded; paused pose unchanged; reload no repeat; 390 px no horizontal overflow; zero page errors |
| Python regression | simulation_goal, site_simulation, chat_conversation, h2b2_site_review | 81 PASS |
| Web regression | 37 files | 288 PASS |
| Production Web build | TypeScript + Vite | PASS; existing >500 kB chunk warning remains |
| Existing six built-Web/API cases | `artifacts/c1-chat-20261005-v287-final/verification.json` | image/text/REAL selection/failure/cancel/saved PASS; 21 source + 3 build hashes |
| Owned runtime cleanup | both final journey supervisors/host receipts | supervisor stopped, owned backend/engine cleared; host PASS |

Screenshots `generated-ready.png`, `generated-physics-arrived.png` and `journey-mobile.png` in both final journey directories were inspected. They show the existing generated room and, after explicit Run, the Burger in the actual Isaac render. Readiness, current task and English controls are visible. The ready screenshot's initial FPS is not evidence of sustained performance. Mobile screenshots show the responsive Twin pane; no public/mobile network access is claimed.

Reproduction using the existing bundled Python and installed Isaac:

```powershell
python scripts/verify_chat_sim_journey.py artifacts/<fresh-text-output> --case text
python scripts/verify_chat_sim_journey.py artifacts/<fresh-image-output> --case image
python scripts/verify_chat_c1.py --output artifacts/<fresh-regression-output>
```

The journey harness requires explicit fixture mode in its isolated backend child. It does not change the production default provider, enable REAL, use paid calls or contact a robot. Both output directories must be fresh; failed evidence is retained rather than overwritten.

## Failures retained and corrected

- Initial restricted-shell Python tests encountered temporary-directory permission failures. A reviewed scoped local test execution succeeded; this was not relabeled as a product failure or bypassed after denial.
- A regression exposed the missing request ID in the text-choice alias. The product was corrected and the complete selected Python suite passed.
- `chat-sim-journey-20261005-text-01` failed on an obsolete image-alt selector after generation/Build. The correct current render selector was used; text-02 and final text-03 passed. Those artifacts remain.
- `c1-chat-20261005-v287` failed because its old selector expected an active inline error after Dismiss. Current UI intentionally keeps the original diagnosis in collapsed “Earlier issue · dismissed”. The test now expands that retained error and requires its original `provider_missing` reason. Final six cases pass; the earlier failed receipt remains.

## Remaining work and next sequence

1. Finish pre-Run visual Burger placement without starting Physics or restoring motion permission; broaden supported scene/robot selection and actual runtime fault/reset acceptance.
2. Complete C1 prerequisite manifest, approved self-repair/failure matrix and owned engine project-switch acceptance. Verify real configured v2 provider photo/text output separately; no paid call was authorized here.
3. C3–C6: real-robot connection/qualification in chat, autonomous survey and corrected Twin, exact displayed-route physical confirmation, five-second summaries and bounded task loop remain incomplete. Existing saved sensor evidence does not accept these live behaviors.

C1/C2 remain PARTIAL and whole-demo readiness=false. The next code work is offline; do not ask for robot power merely to close it. Existing dirty changes, raw evidence, historical failures, v1/v2/hash contracts and physical guards (scan 200 ms, input 250 ms, segment 50 ms, .03 m/s, .20 rad/s, 45 s) are preserved. Robot/SSH/serial/sensors/motors/deployment/paid calls/install/system setting/commit/push/new agents: zero this increment. Existing heartbeat remains PAUSED.
