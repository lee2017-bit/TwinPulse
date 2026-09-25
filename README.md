# TwinPulse

TwinPulse is a 3D Isaac Sim Playground/Copilot Extension for turning constrained warehouse images and optional natural-language constraints into a runnable simulation. The multimodal LLM produces a high-level allowlisted plan; deterministic local code owns robot profiles, USD/PhysX compilation, runtime control, and acceptance measurement.

The approved product architecture is a **local React web App plus a separate Isaac 3D window**. This GitHub-connected clone is the canonical development root; the current Extension and its legacy UI remain available as the engine adapter. R0 through the R5 React-to-actual-Isaac vertical slice are complete for their tested local scopes. R6 has a passing local deterministic managed-launcher E2E, and S1d/S2a/S2b/S2c/S2d now harden process ownership, immutable inputs, single-owner generation, provider/credential binding, and zero-provider stored-result replay through actual Isaac. One local Nebius Gemma→Nemotron image draft built into Isaac and completed the simulated AGV route, but the rack layout did not pass photo-fidelity review; fresh-clone/company-PC reproduction remains pending. See [`docs/planning/TWINPULSE_R0_HANDOFF.md`](docs/planning/TWINPULSE_R0_HANDOFF.md), the [R6 evidence](docs/verification/R6-automatic-app-e2e.md), and the [stepwise migration plan](docs/planning/TWINPULSE_APP_MIGRATION_PLAYBOOK.md).

## Install and run on another Windows PC

Prerequisites: Isaac Sim 6.0.1 standalone, CPython 3.12, Node.js 20.19+ or 22.12+, Git, and network access for the first dependency install. After cloning, double-click **`Install-TwinPulse.cmd`**. It locates or asks for the Isaac root, creates a repository-local `.venv`, installs the hash-locked Python dependency and frozen web lockfile, builds the UI, and launches TwinPulse. It does not install Isaac/Node/Python, copy API keys, or send a paid model request. Run it again to repair/update dependencies after pulling changes. The script keeps the launcher open until you close it.

For an explicit Isaac location or install without launching:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install_twinpulse.ps1 -IsaacRoot "D:\isaacsim\isaac-sim-standalone-6.0.1-windows-x86_64"
```

Add `-Launch` to start the App after installation. See [company-PC instructions](docs/COMPANY_PC_INSTALL.md) for verification, secret setup, and limitations. One-click installation passed on the development PC; a fresh clone and company PC are not yet verified.

## Current scope

- M2-C local integration: persistent provider Settings, secure Windows credential storage, one-image picker/preview, an image-first strict scene-tool plan, reload-safe generated-draft persistence, generated-scene application, and a reproducible three-image provider/Isaac harness.
- `agv_compact_2wd_caster_v2` is a vetted differential-drive profile with two driven wheels and two passive ball casters. Legacy `agv_compact_diff_v1` plans resolve to it without letting the LLM author physical parameters.
- Runtime safety stops now cover route deviation and excessive roll/pitch. Headless acceptance records pose, attitude, goal error, vertical motion, geometric collider overlap, and support-wheel structure.
- Generated floor boxes are compiled as actual-size closed USD meshes, avoiding the asymmetric PhysX contact observed with large non-uniformly scaled cube colliders. The saved one-image 8 m plan now completes the tested route.
- Default provider settings target `gpt-5.6-luna` through the modern Responses API; no key is bundled.
- Three distinct attributed warehouse images produced different validated Luna plans (10/9/18 calls; 58/58/46 expanded objects) and all three generated Isaac scenes completed their routes with zero collision samples. Routine verification still sends no paid request; the explicit M2-C provider runner does.
- A deterministic dimensioned 2D floor-plan fixture, exact-coordinate scorer, trusted measurement sidecar, and local reference-to-Isaac harness are available for plan-to-3D evaluation. One real provider plan built and ran in Isaac but scored 27/29 after reading both 3.0 m rack heights as 2.0 m. The M2-D code has been preserved as a **partial checkpoint**, not validated as a complete workflow: the sidecar generator/plan fields and stale-draft binding need R1 repair. No fresh paid 29/29 attempt has run.
- No ROS2, Isaac Lab, cloud deployment, or physical robot control has been run yet.
- The Extension owns only `/World/TwinPulse` in the USD stage.
- R1 binds every generated draft to immutable input/measurement/settings revisions and revalidates persisted receipts before Build.
- R2 binds applied content to a canonical fingerprint and success-only receipt, repairs stale/damaged owned content, preserves foreign stage content through rollback, and requires Reset after off-route/unstable safety stops.
- R3 centralizes generation, project persistence and Build eligibility in a UI-independent application service, defines strict versioned engine command/receipt/snapshot contracts, and keeps Isaac imports behind the Extension boundary.
- R4 adds an authenticated loopback command broker and managed Extension bridge. Network I/O remains off the Kit thread; actual Build/Run/Pause/Reset/GetState/Focus, disconnect watchdog behavior, and three reconnect cycles passed in Isaac.
- R5 adds a same-origin React/TypeScript product UI for strict image/optional measurement upload, asynchronous deterministic draft generation, review acknowledgement, revision-gated 3D Build, and actual Isaac Run/Pause/Reset/Focus. The automated browser-to-Isaac acceptance passed at desktop, mobile, and 125% zoom; no new paid provider request was made.
- R6 adds an owned-process manager, one-command launcher, authenticated readiness checks, finite failure handling, browser screenshots, official Isaac viewport capture, and a secret-safe provider settings UI. S1d assigns backend/Isaac trees to Windows Job Objects, isolates each run below `runtime/launches/<launch-id>`, and reports stale heartbeat as `engine_unresponsive` while blocking Run. The API key persists in Windows Credential Manager across restarts; it is never returned to the browser.
- S2a replaces header sniffing with bounded Pillow verify+full decode for PNG/JPEG/VP8/VP8L and binds sidecar 1.1 to the immutable input. S2b routes the product API through `ApplicationService`, makes fixture mode explicit, rejects late/cancelled results, registers only validated dynamic artifacts, and binds Build acknowledgement to input+draft revisions. S2c adds provider profile/capability/credential identity, explicit endpoint-key reapproval, atomic settings writes with rollback, corrupt-state preservation, and separate saved/capability/key/live-success states. S2d strictly revalidates and replays the three stored M2-C outputs through the owned manager and actual Isaac with zero provider calls; all three Build/Run/Pause/mid-Reset/completion/post-Reset sequences and official viewport captures passed.
- S3b validates a strict two-stage Nebius Chat Completions pipeline with fake transport: Gemma produces bounded visual observations, NVIDIA Nemotron owns the full allowlisted scene/tool plan, and local validation remains authoritative. S3c now wires the exact reviewed preset into schema-3.0 product Settings, the backend composition root, and the React UI without issuing a provider request. The finite paid/live gate remains separately approved.

## Python App dependency

The local product App uses a repository virtual environment. The lock is CPython 3.12 / Windows x86-64 specific:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r config\python-runtime-requirements.lock
```

The launcher and verifier automatically select `.venv\Scripts\python.exe` when present. They do not silently install or update packages.

## Core tests

```powershell
C:\isaacsim\python.bat -m unittest discover -s packages\twinpulse_core\tests -v
```

## Runtime verification

```powershell
.\scripts\verify_twinpulse.ps1 -IsaacRoot "C:\isaacsim"
```

Each run writes a machine-readable manifest, Isaac result JSON, and a console transcript below `artifacts/runs/<run-id>`. Use `-SkipIsaac` for pure contract/provider checks.

Use `-RunR6` to include the managed-launcher browser/actual-Isaac suite:

```powershell
.\scripts\verify_twinpulse.ps1 -IsaacRoot "C:\isaacsim" -RunR6
```

## Launch the product App

```powershell
.\scripts\launch_twinpulse_app.ps1 -IsaacRoot "C:\isaacsim"
```

The launcher builds the React app, starts the local backend and its owned Isaac process, then opens the browser. Closing the launcher stops only those owned processes. Provider non-secret settings are stored under `%LOCALAPPDATA%\TwinPulse\runtime`; the API key remains in Windows Credential Manager.

## Provider tests

```powershell
C:\isaacsim\python.bat -m unittest discover -s packages\twinpulse_provider\tests -v
```

## Open in Isaac Sim

Use the provided launcher or add `extensions` as a local Extension search path, enable `twinpulse.extension`, and use the **TwinPulse Copilot** window.

- Company PC installation and transfer: [`docs/COMPANY_PC_INSTALL.md`](docs/COMPANY_PC_INSTALL.md)
- Extension controls and provider behavior: [`docs/extension-usage.md`](docs/extension-usage.md)
- Verified status and open limitations: [`docs/progress.md`](docs/progress.md)
- Generated-floor root cause and evidence: [`docs/verification/M2-generated-floor-stability.md`](docs/verification/M2-generated-floor-stability.md)
- Three-image multimodal/physics evidence: [`docs/verification/M2-C-three-image-e2e.md`](docs/verification/M2-C-three-image-e2e.md)
- Dimensioned-plan partial evidence: [`docs/verification/M2-D-dimensioned-floorplan-e2e.md`](docs/verification/M2-D-dimensioned-floorplan-e2e.md)
- R1 input/draft integrity evidence: [`docs/verification/R1-input-draft-integrity.md`](docs/verification/R1-input-draft-integrity.md)
- R2 stage identity/safety evidence: [`docs/verification/R2-stage-identity-safety.md`](docs/verification/R2-stage-identity-safety.md)
- R3 application-service/contract evidence: [`docs/verification/R3-application-service-contracts.md`](docs/verification/R3-application-service-contracts.md)
- R4 loopback/actual-Isaac bridge evidence: [`docs/verification/R4-loopback-isaac-bridge.md`](docs/verification/R4-loopback-isaac-bridge.md)
- R5 React product UI evidence: [`docs/verification/R5-react-product-ui.md`](docs/verification/R5-react-product-ui.md)
- R6 automatic App/Isaac evidence: [`docs/verification/R6-automatic-app-e2e.md`](docs/verification/R6-automatic-app-e2e.md)
- S1d process-tree/state-isolation evidence: [`docs/verification/S1d-process-boundary-state-isolation.md`](docs/verification/S1d-process-boundary-state-isolation.md)
- S2a input-integrity evidence: [`docs/verification/S2a-input-integrity.md`](docs/verification/S2a-input-integrity.md)
- S2b generation-ownership evidence: [`docs/verification/S2b-generation-ownership.md`](docs/verification/S2b-generation-ownership.md)
- S2c provider-settings evidence: [`docs/verification/S2c-provider-settings-hardening.md`](docs/verification/S2c-provider-settings-hardening.md)
- S2d managed-replay evidence: [`docs/verification/S2d-managed-replay.md`](docs/verification/S2d-managed-replay.md)
- S3b fake-transport evidence: [`docs/verification/S3b-nebius-fake-transport.md`](docs/verification/S3b-nebius-fake-transport.md)
- S3c no-call product-wiring evidence: [`docs/verification/S3c-product-wiring.md`](docs/verification/S3c-product-wiring.md)
