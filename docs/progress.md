# TwinPulse progress

- Updated: 2026-09-13 KST
- M0-A: PASS
- M0-B: limited PASS
- M1-A: PASS
- M1-B: PASS (local MinimalRendering/CPU physics + user-run Full-app interactive visual)
- M2-A: PASS; corrected compact UI confirmed in the user-run Full app
- M2-B: PASS for one real image. The user-run Luna request produced 14 allowlisted calls/59 objects, built 134 generated prims, and restored the same persisted plan after restart.
- M2 robot-dynamics repair: PASS in local headless Isaac. `agv_compact_2wd_caster_v2` separates two driven wheels from two passive supports, adds fixed center-of-mass/inertia and an attitude safety stop, and records automated episode evidence. Core 23/23, provider 8/8, lifecycle 3/3, short run/reset 3/3, generated/fallback/rollback, and 6.9 m route passed. Long-route maximum pitch 0.0306 deg, roll 0.0433 deg, cross-track error 0.000825 m, goal error 0.049306 m, geometric collision samples 0.
- Distribution checkpoint: the full local verification repeated PASS on 2026-09-13 (`artifacts/runs/20260913-231705`, intentionally git-ignored). A company-PC installation guide and configurable Isaac root were added for handoff.
- Next: reproduce the Extension on the company PC, then investigate generated-layout-specific robot stability before the three distinct image fixtures required for M2-C.

## Implemented

- New project repository layout separating pure core and Isaac Extension code.
- Versioned SceneSpec, RobotProfile, TaskSpec, JSON round-trip, validation limits, and fixed fixture.
- `twinpulse.extension-0.1.0` with Build Scene, Run / Resume, Pause, and Reset UI.
- The compatible `twinpulse.extension-0.1.0` visible-scene revision adds an overview camera, dome/sun lighting, goal marker, automatic viewport focus, and a 1.5 m visible route. The manifest stays at 0.1.0 because the existing Isaac enable list pins that exact package version.
- Idempotent `/World/TwinPulse` scene compiler with floor/walls/racks/box and procedural wheeled AGV.
- Finite core and Isaac runtime verification scripts.
- Provider-neutral request/capability/result contracts, deterministic mock, modern OpenAI Responses adapter, timeout/cancel/stale-response handling, and eight provider tests.
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

## Current constraints

- This PC remains below the Isaac Sim bundled VRAM/RAM minimum; M1 passed only for a small fixture with MinimalRendering and CPU physics.
- The final runtime log contains two failed online Extension registry index sync attempts. Local dependency resolution and all TwinPulse checks still passed.
- The headless harness retains Python frame references during its first immediate disable, producing one object-lifetime warning; all three shutdown callbacks complete and physics subscriptions are released. An interactive UI unload check remains advisable.
- User-run Full-app acceptance confirmed 28 prims, visible camera/light/warehouse/AGV/goal, Focus Scene, AGV movement during Run, Reset recovery, and a responsive 43-74 FPS viewport.
- The old Isaac 5.1 safety backup remains outside this repository because recursive cleanup was policy-blocked.
- No API key was created, read into logs, or entered by Codex. The user initiated one Luna request that returned a valid draft; Codex did not initiate it. No cloud resource, ROS2/Lab installation, or physical AGV command was used.
- The corrected scene-tool-plan and RobotProfile v2 path has 23/23 core tests, 8/8 provider tests, and an Isaac regression PASS (54 generated regression prims, fallback rejection, rollback, three lifecycle/physics cycles, and a stable 6.9 m route).
- The user-run real image path passed generation, generated Build, and persisted draft restore. The post-fix motion still needs one interactive visual confirmation; the three-fixture diversity/measurement gate remains open.
- A deterministic replay of that same persisted real-image plan later stopped as `unstable` after 187 frames (maximum roll 9.0393 deg, goal error 7.809 m). The stable fixed 6.9 m acceptance route still passes, so this is a generated-layout/initialization limitation rather than proof that arbitrary generated plans are physically safe. Do not use generated scenes for physical deployment.
- a.biz endpoint protocol/model/vision/schema behavior remains unverified. The current custom-Base-URL path requires modern Responses API compatibility.

## Current approval boundary

- Repository changes are allowed under `C:\Users\jaewo\Documents\Codex\TwinPulse` for the requested Extension implementation.
- TwinPulse runtime scratch/install work is allowed under existing `C:\isaacsim`.
- System files, drivers, WSL, Docker, firewall, ROS2/Lab installation, external paid API/VM use, publication, and physical AGV control remain separate approval gates.
