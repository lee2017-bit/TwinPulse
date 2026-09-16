# TwinPulse

TwinPulse is a 3D Isaac Sim Playground/Copilot Extension for turning constrained warehouse images and optional natural-language constraints into a runnable simulation. The multimodal LLM produces a high-level allowlisted plan; deterministic local code owns robot profiles, USD/PhysX compilation, runtime control, and acceptance measurement.

The approved next product architecture is a **local React web App plus a separate Isaac 3D window**. This GitHub-connected clone is the canonical development root; the current Extension and its legacy UI are retained as the engine adapter until the replacement is validated. R0 source handoff, R1 input/draft integrity and R2 actual-Isaac stage identity/runtime safety are complete. R3 application-service extraction and the web UI/backend have not started. See [`docs/planning/TWINPULSE_R0_HANDOFF.md`](docs/planning/TWINPULSE_R0_HANDOFF.md), the [R2 evidence](docs/verification/R2-stage-identity-safety.md), and the [stepwise migration plan](docs/planning/TWINPULSE_APP_MIGRATION_PLAYBOOK.md).

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
- Generated-floor root cause and evidence: [`docs/verification/M2-generated-floor-stability.md`](docs/verification/M2-generated-floor-stability.md)
- Three-image multimodal/physics evidence: [`docs/verification/M2-C-three-image-e2e.md`](docs/verification/M2-C-three-image-e2e.md)
- Dimensioned-plan partial evidence: [`docs/verification/M2-D-dimensioned-floorplan-e2e.md`](docs/verification/M2-D-dimensioned-floorplan-e2e.md)
- R1 input/draft integrity evidence: [`docs/verification/R1-input-draft-integrity.md`](docs/verification/R1-input-draft-integrity.md)
- R2 stage identity/safety evidence: [`docs/verification/R2-stage-identity-safety.md`](docs/verification/R2-stage-identity-safety.md)
