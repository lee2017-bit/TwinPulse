# Changelog

## 0.1.0 R4 authenticated loopback bridge

- Add the managed Isaac adapter and worker-thread bridge client while keeping USD, PhysX, compiler and runtime mutation on the Kit update thread.
- Add product/engine role separation, session/stage/revision/lease/TTL checks, deduplication, reconciliation telemetry, cancellation/expiry handling, and a bounded command queue.
- Disable competing legacy product controls in managed mode and pause locally when the backend/lease disappears; reconnect never resumes motion automatically.
- Pass actual-Isaac HTTP Build/Run/Pause/Reset/GetState/Focus, owned-backend-loss watchdog, three lifecycle/reconnect cycles, and all preserved regressions.

## 0.1.0 R3 application-service compatibility

- Route generation, draft persistence and Build eligibility through the UI-independent `twinpulse_app.ApplicationService` while retaining the legacy Isaac window.
- Move Windows credential storage and one-time non-secret provider-settings migration behind application adapters without changing the credential target.
- Add pure schema 1.0 command, receipt and simulation-snapshot contracts for the later loopback bridge; no bridge or React UI is introduced in R3.
- Preserve R1 stale-input/error/cancel behavior and pass the existing actual-Isaac Extension smoke regression.

## 0.1.0 R2 stage identity and runtime safety

- Replace scene-ID-only reuse with a canonical build fingerprint, authored-content validation and a success-only build receipt.
- Repair changed/corrupt owned content, preserve external prims, and restore geometry, identity, bundle and receipt after replacement failure.
- Reject incompatible user stages without changing their up-axis, units or foreign `/World/TwinPulse` content.
- Bind runtime commands to the active matching stage and add Reset-required off-route/unstable safety latches.
- Add actual-Isaac coverage for same-ID changes, idempotence, reload/new-stage handling, rollback, ownership and safety-stop bypass.

## 0.1.0 M2-D measurement guard hardening

- Select high image detail automatically for dimensioned plans and technical-drawing cues while retaining low detail for ordinary photos.
- Load strict sibling `<stem>.measurements.json` constraints when a drawing is attached.
- Reject mismatched LLM tool arguments before local registry execution and keep generated Build unavailable.
- Label inputs without independent measurements as `exact dimensions unverified` instead of implying precision.
- Add provider and Isaac-runner defense-in-depth checks for measurement validation evidence.

## 0.1.0 M2-D dimensioned-plan evaluation harness

- Add a deterministic metric top-down warehouse plan generator and hash-pinned PNG fixture manifest.
- Generalize the provider/Isaac fixture runners to non-empty fixture sets and PNG/JPG/WEBP MIME selection.
- Add an exact-coordinate plan scorer and an explicitly non-provider reference extrusion path.
- Verify the reference plan as 29/29 coordinate checks and a 90-prim Isaac episode with an 8 m completed route and zero collision samples.
- Record the one real provider attempt as authentication-rejected; do not claim diagram-reading success and do not retry automatically.

## 0.1.0 M2-C three-image evaluation harness

- Add an attributed, hash-pinned three-image fixture manifest without committing image binaries.
- Add explicit fixture download, one-attempt provider generation, and multi-scene Isaac physics runners.
- Confirm three different image observations/tool plans and three completed generated-scene episodes with collision, route, attitude, Pause, and Reset metrics.
- Add an intentional collision measurement regression; routine verification remains free of paid provider calls.

## 0.1.0 generated-floor physics stability repair

- Compile floor boxes as actual-size closed USD meshes with identity scale instead of non-uniformly scaled cube colliders.
- Add an 18 x 12 m floor geometry contract and long-route physics regression.
- Verify the persisted one-image 8 m generated route completes without the former roll instability.

## 0.1.0 RobotProfile v2 and automated 3D acceptance repair

- Replace the unstable two-contact AGV with a vetted two-driven-wheel/two-passive-caster profile.
- Keep mass, center of mass, inertia, support geometry, and attitude limits outside LLM-authored plans.
- Resolve persisted `agv_compact_diff_v1` plans to the canonical v2 profile and force a scene rebuild when profile metadata changes.
- Add roll/pitch safety stops, 3D pose sampling, geometric collision checks, support-structure checks, and per-run artifacts.
- Separate allowlisted scene, robot-selection, and task-intent domains; keep MCP as an optional external adapter.

## 0.1.0 M2-B image-first tool-orchestration correction

- Replace direct LLM-authored scene bundles with a strict allowlisted scene-tool plan and deterministic local execution.
- Treat the attached image as primary evidence and natural language as optional constraints.
- Persist the last valid generated plan with integrity metadata across reloads without storing prompts, images, paths, or credentials.
- Remove the generated Build path's silent sample fallback and expose image/tool/object/source audit data.
- Expand rack rows and pallet stacks into supported local geometry before route validation and USD compilation.
- Align provider-side numeric constraints with local tool limits, strengthen clear-route planning guidance, and expose the exact secret-free local rejection reason without an automatic paid retry.

- Add persistent LLM Settings and Windows Credential Manager API-key storage.
- Add PNG/JPG/WEBP attachment preview and modern Responses API multimodal generation.
- Apply validated generated bundles while preserving the live PhysicsScene prim.
- Add one approximation warning per Extension session before Build.

## 0.1.0 M2-A Copilot UI revision

- Replace the compact control box with a dark prompt-first workflow panel.
- Add natural-language entry and deterministic local mock draft validation.
- Show provider state, structured bundle preview, and explicit M2-B image boundary.
- Retain the exact 0.1.0 manifest version required by the existing Isaac enable pin.

## 0.1.0 visible-scene revision

- Add a TwinPulse-owned overview camera and warehouse lighting.
- Focus the active viewport after Build and expose a manual Focus Scene action.
- Increase the fixed route to 1.5 m and add a visible goal marker.
- Yield one UI update before heavier Build, Run, and Reset actions.

## 0.1.0 initial M1

- Add M1 Extension lifecycle and minimal control window.
- Add idempotent fixed-scene compiler scoped to `/World/TwinPulse`.
- Add procedural differential-drive AGV with physics wheel drives.
