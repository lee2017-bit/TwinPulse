# TwinPulse progress

- Updated: 2026-09-16 KST
- App migration R0/R1/R2/R3: **PASS for the tested local scope.** D1 is local React web App + separate Isaac 3D window; D2 is this GitHub-connected clone as the sole development root. R1 fixed input/measurement/draft/receipt integrity. R2 passed actual-Isaac stage identity, rollback and Reset-required safety acceptance. R3 extracted a UI-independent application service, credential-free project/settings persistence and strict engine command/receipt/snapshot contracts; the existing Extension now uses the service and its actual-Isaac legacy regression passed. R4-R10 and the React UI remain NOT RUN. See `docs/verification/R3-application-service-contracts.md`.
- M0-A: PASS
- M0-B: limited PASS
- M1-A: PASS
- M1-B: PASS (local MinimalRendering/CPU physics + user-run Full-app interactive visual)
- M2-A: PASS; corrected compact UI confirmed in the user-run Full app
- M2-B: PASS for one real image. The user-run Luna request produced 14 allowlisted calls/59 objects, built 134 generated prims, and restored the same persisted plan after restart.
- M2-C: PASS for three distinct rights-cleared images. Codex initiated exactly one saved-key provider request per fixture; all three produced different validated image observations/tool plans and all three generated scenes completed headless Isaac physics with zero collision samples, zero Pause drift, and zero Reset error.
- M2-D dimensioned plan: PARTIAL. One real Luna request produced 10 calls/32 objects and the resulting 84-prim Isaac scene completed its 8 m route, but both 3.0 m rack heights were read as 2.0 m, giving 27/29. The post-failure repair sends drawing-like inputs at high detail and enforces an independent sibling measurement sidecar before tool execution. Replaying the bad plan now blocks Build at the rack-height mismatch, and a clean Full-app restart loaded the repaired Extension to `app ready`. A fresh paid request has not been made.
- M2 robot-dynamics repair: PASS in local headless Isaac. `agv_compact_2wd_caster_v2` separates two driven wheels from two passive supports, adds fixed center-of-mass/inertia and an attitude safety stop, and records automated episode evidence. Core 23/23, provider 8/8, lifecycle 3/3, short run/reset 3/3, generated/fallback/rollback, and 6.9 m route passed. Long-route maximum pitch 0.0306 deg, roll 0.0433 deg, cross-track error 0.000825 m, goal error 0.049306 m, geometric collision samples 0.
- Generated-layout floor repair: PASS. The persisted real-image plan exposed a PhysX contact defect caused by compiling a large, thin floor as a non-uniformly scaled cube. Floors are now authored as actual-size closed meshes with identity scale. The same 8 m route completed in 1,889 frames with maximum roll 0.0862 deg, pitch 0.0738 deg, and final goal error 0.2465 m (within the 0.25 m task tolerance).
- Distribution checkpoint: the post-repair full local verification passed on 2026-09-13 (`artifacts/runs/20260913-234455`, intentionally git-ignored) and the repair was published as GitHub main commit `1c5ed27`. Its 18 x 12 m floor regression confirmed Mesh geometry with no scale operation; the 6.9 m route completed with maximum roll 0.0762 deg, pitch 0.0668 deg, cross-track error 0.00435 m, goal error 0.04929 m, and zero geometric collision samples.
- Next: only when the user approves it, execute R4 loopback API and actual Isaac bridge. Do not start the React UI ahead of the bridge contract. A fresh paid drawing evaluation remains deferred to R9; general navigation and obstacle avoidance remain future work.

## Implemented

- New project repository layout separating pure core and Isaac Extension code.
- Versioned SceneSpec, RobotProfile, TaskSpec, JSON round-trip, validation limits, and fixed fixture.
- `twinpulse.extension-0.1.0` with Build Scene, Run / Resume, Pause, and Reset UI.
- The compatible `twinpulse.extension-0.1.0` visible-scene revision adds an overview camera, dome/sun lighting, goal marker, automatic viewport focus, and a 1.5 m visible route. The manifest stays at 0.1.0 because the existing Isaac enable list pins that exact package version.
- Idempotent `/World/TwinPulse` scene compiler with floor/walls/racks/box and procedural wheeled AGV.
- Large generated floors use actual-size closed USD meshes rather than non-uniformly scaled cube colliders, avoiding asymmetric PhysX wheel/caster contact.
- Finite core and Isaac runtime verification scripts.
- Provider-neutral request/capability/result contracts, deterministic mock, modern OpenAI Responses adapter, timeout/cancel/stale-response handling, and thirteen provider tests.
- A pre-Nav2 route gate rejects sideways, reverse, overlong, off-floor, tilted-collider, and blocked paths that the current positive-X controller cannot safely execute.
- Copilot-inspired prompt-first UI with structured draft preview and explicit mock/provider state.
- Initial UI visual review failed because the Isaac font replaced Korean/symbol glyphs and auto-sized stacks expanded vertically. The correction uses ASCII-only UI text and explicit pixel dimensions; runtime regression remains PASS.
- Persistent Base URL/Model ID/reasoning settings, Windows Credential Manager API-key storage, one-image picker/preview, strict JSON Schema generation, and generated-bundle compilation with a stable PhysicsScene.
- Image-first scene-tool-plan output with eight allowlisted operations, deterministic local registry execution, generated draft plan-hash persistence, source/image/tool/object audit, and no implicit sample fallback.
- Provider JSON Schema numeric bounds now mirror the local tool limits, and invalid plans report the exact bounded semantic reason rather than a generic parse failure. No automatic paid retry is performed.
- The generated AGV controller now uses live WXYZ pose/yaw feedback, 2D goal distance, heading correction, live aisle-error status, and a Reset-required off-route safety stop instead of fixed equal wheel velocities.
- RobotProfile v2 owns drive/support contacts, center of mass, diagonal inertia, and an attitude safety limit. The current profile has two driven wheels plus front/rear passive ball casters; legacy plan IDs are upgraded by the local catalog.
- Tool calls now have explicit scene/robot/task domains and an auditable execution receipt. MCP remains an optional external adapter rather than the in-process physics/control mechanism.
- `scripts/verify_twinpulse.ps1` runs compile, core, provider, and Isaac checks and stores a manifest, structured result, and transcript per run.
- The M2-C manifest plus fetch/provider/Isaac runners reproduce the three-image gate without requiring manual screenshot relay. The API key remains in Windows Credential Manager and paid retries are disabled.
- The generalized manifest runners also accept PNG and any non-empty fixture count. `create_m2d_floorplan_fixture.py`, `evaluate_m2d_floorplan_result.py`, and the explicitly non-provider reference report isolate diagram-reading accuracy from deterministic 3D compiler/physics behavior.
- Dimensioned inputs use high-detail image inference and optional trusted `<stem>.measurements.json` constraints. The Extension labels unconstrained images as exact-dimensions-unverified; constrained mismatches stop before the tool registry and Isaac Build.
- Applied USD now carries explicit TwinPulse ownership, canonical build fingerprint, compiler/catalog versions and an authored-static-content digest. A matching receipt is published only after the actual stage validates.
- Runtime commands are invalidated on stage change. Off-route/unstable states remain latched through Pause and require a successful Reset before Run.
- `twinpulse_app` now owns generation epochs, immutable input promotion, active-project persistence and Build eligibility without importing Isaac modules. `twinpulse_core.engine_contracts` defines the versioned R4-facing command, receipt and simulation snapshot vocabulary.

## Current constraints

- This PC remains below the Isaac Sim bundled VRAM/RAM minimum; M1 passed only for a small fixture with MinimalRendering and CPU physics.
- The final runtime log contains two failed online Extension registry index sync attempts. Local dependency resolution and all TwinPulse checks still passed.
- The headless harness retains Python frame references during its first immediate disable, producing one object-lifetime warning; all three shutdown callbacks complete and physics subscriptions are released. An interactive UI unload check remains advisable.
- User-run Full-app acceptance confirmed 28 prims, visible camera/light/warehouse/AGV/goal, Focus Scene, AGV movement during Run, Reset recovery, and a responsive 43-74 FPS viewport.
- The old Isaac 5.1 safety backup remains outside this repository because recursive cleanup was policy-blocked.
- No API key was printed, serialized, or committed. For the user-approved M2-C test, Codex loaded the existing saved credential and initiated exactly three Luna requests, one per fixture, with no automatic retry. No cloud compute resource, ROS2/Lab installation, or physical AGV command was used.
- The corrected scene-tool-plan and RobotProfile v2 path has 23/23 core tests, 8/8 provider tests, and an Isaac regression PASS (54 generated regression prims, fallback rejection, rollback, three lifecycle/physics cycles, and a stable 6.9 m route).
- The original user-run real image path and the three new Codex-run fixtures passed generation, generated Build, and deterministic headless motion. Full-app visual confirmation remains optional; the M2-C diversity/measurement gate is closed for the tested fixtures.
- The former persisted-plan failure (roll 9.0393 deg at frame 187) was isolated to the large non-uniformly scaled floor cube and is resolved by the mesh-floor compiler. This verifies the tested plan, not arbitrary future generated scenes. Do not use generated scenes for physical deployment.
- a.biz endpoint protocol/model/vision/schema behavior remains unverified. The current custom-Base-URL path requires modern Responses API compatibility.
- The Windows credential target contains a value and the later one-attempt M2-D request authenticated successfully. No secret was printed or serialized. The current acceptance blocker is the 27/29 rack-height reading, not authentication.
- R3 general-Python tests passed 9/9 and the full actual-Isaac runner passed at `artifacts/runs/20260916-152550` (git-ignored). Wheel construction was not run because neither available Python environment contains `setuptools`; package metadata was parsed and dependency declarations were tested instead. This is a packaging-toolchain gap for a later distribution gate, not a wheel PASS.

## Current approval boundary

- The canonical repository is `C:\Users\jaewo\Documents\TwinPulse`; the older `C:\Users\jaewo\Documents\Codex\TwinPulse` copy is preserved history and is not the development root.
- TwinPulse runtime scratch/install work is allowed under existing `C:\isaacsim`.
- System files, drivers, WSL, Docker, firewall, ROS2/Lab installation, external paid API/VM use, publication, and physical AGV control remain separate approval gates.
