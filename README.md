# TwinPulse

TwinPulse is a 3D Isaac Sim Playground/Copilot Extension for turning constrained warehouse images and optional natural-language constraints into a runnable simulation. The multimodal LLM produces a high-level allowlisted plan; deterministic local code owns robot profiles, USD/PhysX compilation, runtime control, and acceptance measurement.

## Current scope

- M2-B local integration: persistent provider Settings, secure Windows credential storage, one-image picker/preview, an image-first strict scene-tool plan, reload-safe generated-draft persistence, and generated-scene application.
- `agv_compact_2wd_caster_v2` is a vetted differential-drive profile with two driven wheels and two passive ball casters. Legacy `agv_compact_diff_v1` plans resolve to it without letting the LLM author physical parameters.
- Runtime safety stops now cover route deviation and excessive roll/pitch. Headless acceptance records pose, attitude, goal error, vertical motion, geometric collider overlap, and support-wheel structure.
- Default provider settings target `gpt-5.6-luna` through the modern Responses API; no key is bundled.
- A user-run Luna request produced a validated image-first 14-call/59-object plan and a 134-prim scene. No paid request is sent by automated verification.
- No ROS2, Isaac Lab, cloud deployment, or physical robot control has been run yet.
- The Extension owns only `/World/TwinPulse` in the USD stage.

## Core tests

```powershell
C:\isaacsim\python.bat -m unittest discover -s packages\twinpulse_core\tests -v
```

## Runtime verification

```powershell
.\scripts\verify_twinpulse.ps1 -IsaacRoot "C:\isaacsim"
```

Each run writes a machine-readable manifest, Isaac result JSON, and a console transcript below `artifacts/runs/<run-id>`. Use `-SkipIsaac` for pure contract/provider checks.

## Provider tests

```powershell
C:\isaacsim\python.bat -m unittest discover -s packages\twinpulse_provider\tests -v
```

## Open in Isaac Sim

Use the provided launcher or add `extensions` as a local Extension search path, enable `twinpulse.extension`, and use the **TwinPulse Copilot** window.

- Company PC installation and transfer: [`docs/COMPANY_PC_INSTALL.md`](docs/COMPANY_PC_INSTALL.md)
- Extension controls and provider behavior: [`docs/extension-usage.md`](docs/extension-usage.md)
- Verified status and open limitations: [`docs/progress.md`](docs/progress.md)
