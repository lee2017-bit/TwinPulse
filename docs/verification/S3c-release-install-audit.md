# S3c pre-push defect and installation audit — 2026-09-25

## Scope and finding

- Canonical root: `C:\Users\jaewo\Documents\TwinPulse`; all changes since the last R5 commit are part of the local pending release. Runtime `artifacts/`, `.venv`, `node_modules`, and generated `dist` must not be committed.
- The live Nebius draft built 90 Isaac prims and its 2WD route completed, but the source-photo interpretation placed two rack rows with overlapping floor footprints. A successful route is not proof of visual fidelity.
- The tool registry now rejects overlapping rack-row physical footprints before a draft can be built. This is a fail-closed quality gate; it does not automatically invent corrected rack coordinates or fix the already-built stage.
- Other-PC setup previously required several manual commands and an installed pnpm. `Install-TwinPulse.cmd` now drives a checked, repository-local install and launch. Isaac Sim 6.0.1, Python 3.12, Node.js, Git, and initial package network access remain prerequisites. No API key is copied.

## Direct checks on development PC

- `scripts/install_twinpulse.ps1 -IsaacRoot C:\isaacsim -CheckOnly`: PASS.
- `scripts/install_twinpulse.ps1 -IsaacRoot C:\isaacsim`: PASS; Pillow 12.3.0 hash lock satisfied, pnpm 11.19.0 frozen lock install, React production build. The first sandboxed Vite attempt was denied by local process restrictions; the same command passed in the normal execution environment.
- `scripts/verify_twinpulse.ps1 -SkipIsaac`: PASS at `artifacts/runs/20260925-164423`; Core 30, Provider 27, R1 9, R3 9, R4 6, R5/S2/S3c 34, R6 11, React 10 and production build.
- An actual Isaac Build/Run of the earlier live draft had already passed before the new rack-overlap guard. The guard itself is pure validation and has not had a post-change actual-Isaac regression in this audit.

## Open acceptance boundaries

- A clean clone on this development PC and the company PC have not yet been installed and executed from this commit. Do not label the installer universally verified until one of those independent checks passes.
- The live image has not been regenerated under the new overlap guard. No paid re-request was made by this audit. The physical scene still requires photo-fidelity review and appropriate dimensional evidence.
- No physical TurtleBot/AGV, ROS2, cloud endpoint, or paid inference was run for this audit.
