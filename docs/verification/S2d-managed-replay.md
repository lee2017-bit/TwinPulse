# S2d stored M2-C managed replay verification

- Date: 2026-09-24 KST
- Result: **PASS**
- Source: three stored M2-C provider results
- Paid/live provider requests: **0**
- Physical robot commands: **0**

## Implemented boundary

- Added a strict replay loader that accepts only a prior PASS report, checks fixture/image/plan/bundle hashes, parses the allowlisted `SceneToolPlan`, re-executes it locally, and rejects count or digest changes before broker registration.
- Added an explicit `replay` workflow mode. It loads a prevalidated draft into `ApplicationService`, registers only that artifact with the command broker, marks provenance as `source=replay`, and rejects the Generate endpoint with `replay_generation_forbidden`.
- Added manager/backend replay arguments without reading or using provider credentials. `ReplayOnlyGateway` fails if any generation call is attempted.
- Added an actual-Isaac verifier that creates a new owned backend/Isaac process tree per fixture and performs Build, Run, Pause, mid-run Reset, completion Run, and post-completion Reset.
- The verifier records a per-fixture result even on failure, preserving engine/capture diagnostics instead of losing the successful control portion.

## Actual-Isaac evidence

Passing run: `artifacts/runs/20260924-185750-s2d-replay/result.json`

| Stored fixture | Scene | Tools / objects | Prims | Pause drift | Mid / completion Reset error | Goal error | Capture |
|---|---|---:|---:|---:|---:|---:|---|
| `warehouse_narrow_pallet_racks` | `warehouse_narrow_rack_aisle_01` | 10 / 58 | 136 | 0 m | 0 / 0 m | 0.243935 m | PASS |
| `warehouse_asymmetric_parts_storage` | `parts_storage_aisle_scene` | 9 / 58 | 136 | 0 m | 0 / 0 m | 0.244431 m | PASS |
| `warehouse_open_pallet_staging` | `wide_pallet_staging_warehouse` | 18 / 46 | 112 | 0 m | 0 / 0 m | 0.213635 m | PASS |

The run preserved three distinct scene IDs, three distinct plan hashes, and three distinct tool/object-count pairs. Every fixture moved more than 0.22 m before the mid-run Reset, reached `completed`, returned exactly to its built start pose after both Reset operations, and produced an official Isaac viewport capture. The result records `provider_requests: 0`.

An earlier diagnostic run, `artifacts/runs/20260924-144451-s2d-replay`, retained a **FAIL** because headless Isaac reported `viewport_missing`. Its first fixture nevertheless completed the managed physics/control sequence. The final run used visible Isaac solely to satisfy the official viewport-capture contract; no user interaction or provider call was required.

## Regression evidence

- `tests/integration/test_s2d_managed_replay.py`: 3/3 PASS, covering provenance/revalidation, tamper rejection, and replay registration without generation.
- Final official non-Isaac run `artifacts/runs/20260924-190555`: PASS.
  - Core 24/24
  - Provider 13/13
  - R1 9/9
  - R3 9/9
  - R4 6/6
  - R5 + S2a + S2b + S2c + S2d 30/30
  - R6 process manager 11/11
  - React 10/10 and production build PASS

The immediately preceding default-venv attempt stopped before tests because that environment did not contain Pillow. The same official runner passed with the existing Isaac Python, which already satisfies the pinned Pillow requirement; no dependency was installed and this was not a product failure.

A final OS-process audit found four orphaned `kit.exe` processes whose complete command lines were the earlier S2c/S2d `-m unittest` invocations (three S2c, one S2d). Their exact PIDs and executable path were verified before terminating only those four; the remaining matching test-process count was zero. The managed actual-Isaac launch records independently reported `status=stopped`. Future pure-Python verification should prefer the repository `.venv` after its pinned dependencies are installed, avoiding use of the Isaac `python.bat` wrapper for unit suites.

## Remaining boundary

- S2d proves deterministic replay through the owned App → service → broker → manager → actual-Isaac path. It does not prove current Nebius/NVIDIA model availability or live multimodal behavior.
- Fresh-clone/company-PC reproduction and a separately approved live-provider App smoke remain open R6 gates.
- S3a begins only after the user supplies the intended model list, Base URL, and API key. The first live call remains a separate, explicit gate.
