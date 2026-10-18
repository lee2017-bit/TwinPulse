# H2b-3 — explicit v2 provider profile and scene-only Build boundary

- Date: 2026-09-26 KST. Status: **LOCAL_CONTRACT_AND_WEB_PASS / ACTUAL_ISAAC_NOT_RUN / H2b_PARTIAL**.
- [One-page implementation image](H2b-3-versioned-build-flow.png) ([SVG source](H2b-3-versioned-build-flow.svg)) is a code-flow diagram, **not** an Isaac screenshot.

## Implemented

- Preserved the existing Nebius v1 profile. Added an explicit `nebius_site_v2` profile that requests the SiteToolPlan 2.0 schema and does not force a robot, route, or +X goal. `GenerationService` parses v2 separately. The existing `ApplicationService` remains the only generation owner and persists the validated site draft. Trusted measurement sidecars are rejected for v2 until a versioned constraint contract exists; they are not silently ignored.
- Review acknowledgement is bound to the current input and scene revision. The broker registers only the validated `SceneRevision` as a separate immutable artifact, and accepts `build_site_scene` only when the connected engine snapshot advertises `site_scene_build_v2` and permits the command. Old engines fail closed. The payload and successful receipt must carry the same scene revision.
- The Isaac adapter advertises the new capability and routes the v2 command to a scene-only compiler under `/World/TwinPulse`. The compiler does not invent a driven robot, task, goal or Run entitlement. It checks authored geometry and preserves/restores an existing owned root on failure. The runtime and broker both reject Run for a v2-only scene. The React review card exposes this geometry-only Build only after acknowledgement and capability; a successful v2 Build does not navigate to the legacy Simulate screen.

## Local checks

- Core 42/42, provider 29/29 including two-stage fake Nebius v2 transport, H2b integration 5/5, S3c provider/settings 5/5, R4 broker/API 6/6, R5 product API 10/10, web 20/20 plus TypeScript/Vite production build PASS. Python compileall and `git diff --check` PASS (only CRLF notices).
- Negative checks: missing engine capability, wrong Build receipt revision, and direct broker Run after v2 scene Build are rejected. Existing Nebius v1 planner tests remain green.

## Limits and next gate

- **No actual Isaac 6.0.1 process was launched**. Scene compiler USD/PhysX behavior, rollback, and in-window presentation are therefore code-reviewed and syntax-checked, **not** accepted as runtime PASS. H2c must exercise a scene-only v2 fixture and an optional-robot proposal in a clean stage; verify no Robot/Task prims, stable scene revision, receipt/fingerprint, idempotent rebuild, rollback on injected fault, and v1 Build/Run regression.
- No paid Nebius v2 call was made. The provider's strict JSON-schema acceptance and image-grounded quality are unverified; run a bounded single request only after explicit cost/test approval. A v1-to-v2 replay promotion is not exposed in product UI; old replay remains v1 and gains no v2 authority.
- No ROS, physical TurtleBot, installer, company workstation, commit, or push action occurred in this step.
