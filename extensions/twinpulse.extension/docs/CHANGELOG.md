# Changelog

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
