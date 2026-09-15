# M2-D dimensioned floor-plan E2E

- Date: 2026-09-14 KST
- Host: Windows 10, Isaac Sim 6.0.1-rc.7, RTX 2070 Max-Q 8 GB
- Provider target: OpenAI Responses, `gpt-5.6-luna`, reasoning `low`
- Result: **PARTIAL — real provider/3D/physics path works; exact drawing acceptance is 27/29**

## Authoritative input

`scripts/create_m2d_floorplan_fixture.py` creates a deterministic 12 x 8 m top-down PNG and a sibling `*.measurements.json` file. The sidecar contains eight independently supplied constraints covering floor size, rack length/depth/height/bays, wall height, AGV start, and navigation goal. Its values are trusted test data, not values copied from the LLM response.

The PNG SHA-256 is `600235a5050dfda789edc3eb1abc199533fd14ba1d720dc2bd0254601e3ba59f`. Image and sidecar are generated artifacts rather than committed binaries.

## Real provider and Isaac result

One saved-key Luna request completed without retry and produced `dimensioned_warehouse_floor_plan`, 10 tool calls, and 32 expanded objects. The plan correctly reproduced the 12 x 8 m floor, 2.5 m walls, rack length/depth/bay count, center aisle, AGV start, and goal. It read both 3.0 m rack heights as 2.0 m, so the exact scorer returned **27/29 FAIL**.

The same historical plan was built before the new guard existed. Actual Isaac execution produced 84 prims and completed the route:

| Metric | Result |
|---|---:|
| simulated time | 32.583 s |
| traveled distance | 7.903 m |
| final goal error | 0.09887 m |
| maximum cross-track error | 0.00390 m |
| maximum roll / pitch | 0.10101° / 0.06674° |
| geometric collision samples | 0 |
| Pause drift / Reset error | 0 m / 0 m |

The exported provider stage is `dimensioned_warehouse_floorplan_v1.usda` (33,823 bytes, SHA-256 `1EA2E44C5D1732A2CE35D8A71E5BE7322BB7FA3E51D97F498A1404B5B81DDC0A`). Physics PASS does not override the incorrect rack dimensions.

## Post-failure guard

The provider boundary and Extension now apply two controls before local tool execution:

1. Dimensioned-plan cues select OpenAI image detail `high`; ordinary warehouse photos retain `low` by default.
2. If an attached image has a sibling `<stem>.measurements.json`, the Extension loads it, binds it to the exact image file name, and validates every matching tool argument before registry execution. A mismatch rejects the provider response, leaves Build unavailable, and does not silently substitute a sample scene.

The existing 27/29 plan was replayed through this guard without another paid request. It was rejected at `rack_height` (`expected 3 +/- 0.25, got 2`) and `build_allowed` was false. Provider tests are 13/13, core tests are 24/24, compileall passes, and the deterministic generator emits a valid eight-constraint sidecar. A clean Isaac restart then loaded `twinpulse.extension-0.1.0` and reached `Isaac Sim Full App is loaded` / `app ready` with the new provider exports.

When no sidecar exists, image generation remains available but the UI explicitly reports `exact dimensions unverified`. This is intentional: the LLM can propose semantic geometry, but exact drawing dimensions require an independent measurement source.

## Reproduction

```powershell
C:\isaacsim\python.bat scripts\create_m2d_floorplan_fixture.py `
  --output C:\temp\twinpulse-m2d\warehouse-floorplan.png

C:\isaacsim\python.bat scripts\run_m2c_provider_fixtures.py `
  --manifest fixtures\m2d\dimensioned_floorplan.json `
  --image-dir C:\temp\twinpulse-m2d `
  --output C:\temp\twinpulse-m2d-provider.json

C:\isaacsim\python.bat scripts\evaluate_m2d_floorplan_result.py `
  --manifest fixtures\m2d\dimensioned_floorplan.json `
  --provider-report C:\temp\twinpulse-m2d-provider.json `
  --output C:\temp\twinpulse-m2d-score.json
```

The provider command performs one paid request and no automatic retry. A second paid request has not been made after the guard change; M2-D remains PARTIAL until a fresh result passes 29/29 and the measurement gate.
