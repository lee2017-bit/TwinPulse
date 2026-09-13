# M2-C three-image multimodal E2E

- Date: 2026-09-14 KST
- Host: Windows 10, Isaac Sim 6.0.1-rc.7, RTX 2070 Max-Q 8 GB
- Provider: OpenAI Responses, `gpt-5.6-luna`, reasoning `low`
- Result: **PASS (3/3 provider plans and 3/3 Isaac physics episodes)**

## What was tested

Three visually different, attributed Wikimedia Commons warehouse photographs were downloaded from the exact URLs in `fixtures/m2c/warehouse_images.json` and checked against fixed SHA-256 values. The binary images are not committed. Each image was sent once with a short constraint prompt to the saved Windows Credential Manager key. Automatic paid retries remained disabled.

The provider returned a strict allowlisted scene-tool plan for every fixture. Local validation expanded each plan into a `SpecBundle`. A separate headless Isaac 6.0.1 process then replaced `/World/TwinPulse` with each generated bundle, executed Run, sampled the real articulation pose, waited for completion, tested Pause drift, and tested Reset recovery.

## Inputs and generation diversity

| Fixture | Source/license | Provider interpretation | Calls / objects |
|---|---|---|---:|
| `warehouse_narrow_pallet_racks` | Wikimedia Commons, public domain, Jandrinov | long narrow aisle with continuous tall racks on both sides; no visible AGV added | 10 / 58 |
| `warehouse_asymmetric_parts_storage` | Wikimedia Commons, CC BY-SA 4.0, Aspasturias | asymmetric dense parts shelving and broad center-right aisle; visible industrial vehicle omitted as unsupported/ambiguous | 9 / 58 |
| `warehouse_open_pallet_staging` | Wikimedia Commons, public domain FEMA, Jacinta Quesada/FEMA | wide aisle with pallet stacks on both sides; visible person omitted | 18 / 46 |

The resulting scene IDs were `warehouse_narrow_rack_aisle_01`, `parts_storage_aisle_scene`, and `wide_pallet_staging_warehouse`. This shows that the provider did not replay one fixed mock fixture: observations, call sequences, expanded object counts, floor sizes, and route lengths differed by image.

## Isaac physics results

| Fixture | Prims | Sim time | Travel | Goal error | Max cross-track | Max roll / pitch | Collision samples | Pause drift | Reset error |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| narrow pallet racks | 136 | 23.467 s | 5.754 m | 0.2464 m | 0.00515 m | 0.1029° / 0.0471° | 0 | 0 m | 0 m |
| asymmetric parts storage | 136 | 23.483 s | 5.757 m | 0.2444 m | 0.00438 m | 0.0951° / 0.0607° | 0 | 0 m | 0 m |
| open pallet staging | 112 | 31.617 s | 7.786 m | 0.2153 m | 0.00390 m | 0.1010° / 0.0667° | 0 | 0 m | 0 m |

All episodes ended in `completed`, stayed within each generated task's 0.25 m goal tolerance, retained both passive support wheels, and recorded no geometric collider overlap. The test did not teleport the robot or bypass colliders.

## Measurement and failure-path checks

The post-change pure verification passed 24 core and 8 provider tests. These include:

- normal stable episode acceptance;
- an intentional collider overlap that must produce exactly one collision sample and fail the episode;
- blocked-route rejection before build;
- off-route zero-velocity safety stop;
- invalid provider structure, timeout with no retry, rate-limit typing, unsupported image capability, and cancelled late-response rejection.

The approximation warning and generated/sample source separation remain covered by the existing Isaac Extension regression. No physical robot, ROS2, Isaac Lab, or cloud GPU was used.

## Reproduction

```powershell
C:\isaacsim\python.bat scripts\fetch_m2c_fixtures.py --output-dir C:\temp\twinpulse-m2c-images

C:\isaacsim\python.bat scripts\run_m2c_provider_fixtures.py `
  --image-dir C:\temp\twinpulse-m2c-images `
  --output C:\temp\twinpulse-m2c-provider.json

C:\isaacsim\python.bat scripts\run_m2c_isaac_fixtures.py `
  --provider-report C:\temp\twinpulse-m2c-provider.json `
  --output C:\temp\twinpulse-m2c-isaac.json
```

The provider command performs one paid request per fixture. It reads the existing `TwinPulse/OpenAIResponsesAPI` Windows credential without printing or serializing it. Local run evidence is preserved under `artifacts/runs/20260914-0616-m2c/` and intentionally excluded from Git.

## Remaining limits

- Photo-derived dimensions and occluded geometry remain approximate.
- The local controller is still a validated positive-X straight-route controller, not general navigation or obstacle avoidance.
- These three passing scenes do not prove that every future model output will be physically valid; schema, route, and episode gates must remain mandatory.
- MinimalRendering produced machine-readable evidence but no presentation screenshot. Interactive Full-app visual review is optional evidence, not required to reproduce these headless results.
