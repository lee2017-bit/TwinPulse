# Bedroom photo → existing Burger visual composition (N1 increment)

## Result / scope

Actual isolated Isaac 6.0.1 run `artifacts/bedroom-twin-20260928-r2/verification.json`:
**ROOM_BURGER_VISUAL_PASS**, six checks, 4 imported visual meshes.
This is the user's actual photo interpreted as an **approximate blockout**, not
photogrammetry, surveyed geometry, a calibrated robot pose or a driven robot.
App selection/Build wiring for this combined preview remains pending.
No robot connection, sensor, motor, deployment, provider call or simulation Run.

- Product `SiteDraftRecord` and allowlisted `SiteToolPlan` reused; 12 scene objects.
- Floor/walls, bed, wardrobe/open door, desk, chair, fan/boxes, bag and left luggage.
- `SceneCompiler.compile_site_scene` builds the room; imported official Burger
  appears at `/World/TwinPulse/Presentation/BurgerPhotoPreview`, not the controlled
  `/World/TwinPulse/Robot`. No warehouse AGV profile substitution.
- Visual `Physics=none` plus preview-layer deletion of base collision API schemas.
  Original 9 asset dependency files remain byte-identical. A future simulation
  adapter must explicitly reintroduce/qualify dynamics; this view does not do so.
- Y toward window is a draft convention. Robot yaw90deg/position are illustrative.
  Top-view photo direction binds to the preserved source, not a verified TF.
- Saved native scan is not placed into world coordinates or used to clear floor.
- Idempotence, external prim preservation, forged placement rejection before
  mutation, source preservation, three actual viewport captures and USD reopen PASS.
- Right wall is visually hidden for cutaway inspection, not deleted from geometry.
  Near room extent is estimated; an unseen wall/door is not invented.

## Evidence / identities

- Photo `a183bf7e30cb6d1ddc712aa25f484f8763bca6ccbc75d4c8977aa99cbb6f6ea0`.
- Scene `c18410caf2fd41628b7487de1dabb0ee84b3161ac0a4ac0870f7a7cddf61b8b8`.
- Manifest `176e0bdc569aeff37b5173a77afbc48f185678efd306dd0ac12e7a6d7a8fefe1`.
- Export `bedroom-burger-preview.usda` SHA256
  `1b52829a744c6344d159fdf480f4934f7a64528b8ea1e12feca79cf4a93c2955`.
- Overview `room-perspective.png` SHA256
  `f3a2a27646d4aeb66b2f43006030f4460d839afe2e0b15e4bf4c49875a6a0c89`.
- Also `room-photo-view.png`, `burger-detail.png`; overview/detail visually inspected.
  Furniture is box-envelope geometry, not a detailed visual replica.

Verified code SHA256:

| File | SHA256 |
| --- | --- |
| packages/twinpulse_app/src/twinpulse_app/bedroom_twin.py | 8112afc54bb5d2a72a58492298a0d34d99b63ba8fb6e1d5e740ed584541b7226 |
| extensions/twinpulse.extension/twinpulse/extension/bedroom_preview.py | cc3164ccffcc5b2a7c7c6d0b383f0b90fee33c39ab40fd746870cae771198527 |
| scripts/prepare_bedroom_twin.py | 8e2936e51240c30a410b9ea0886b58f402f090cc68fb936c95e1430a62ecffaf |
| scripts/verify_bedroom_twin.py | c2607defc509a31d191438594155a32cc989aebb01e12537a4c05c6ac9c3d32b |

## Regression and failed attempts

- New bedroom tests7 PASS. Related photo/derived record/product selection tests:
  **27 combined PASS**, including those7, not an additional27.
- Pure core138 PASS, also included again in full regression.
- `artifacts/bedroom-regression-20260928-r1/manifest.json`: full existing offline
  suite + new bedroom7, React82, production build PASS. Isaac is NOT_RUN in that
  regression manifest; actual Isaac evidence is the separate r2 run above.
- Initial focused test import missed provider package path, corrected.
- Initial 27-test attempt had11 Windows sandbox temporary-directory access errors.
  Same bounded command rerun with reviewed extra permission passed; not hidden.
- Actual Isaac r1 rejected collision schemas retained in importer base layer even
  with Physics=none. Preview now removes only these APIs in its stronger layer;
  source files unchanged. r1 FAIL is preserved. No physical stop policy changed.
- Isaac r2 emitted OptiX cache readonly and OmniCache/derived-cache warnings.
  No cache deletion/system change. Rendering completed (~265s), captures verified.

## Reproduction / next

Existing tools only, always choose a new output directory:

```powershell
C:\isaacsim\python.bat scripts\verify_bedroom_twin.py artifacts\new-bedroom-preview
.venv\Scripts\python.exe -m unittest -v tests.integration.test_bedroom_twin
powershell.exe -NoProfile -File scripts\verify_twinpulse.ps1 -SkipIsaac -ArtifactDirectory artifacts\new-bedroom-regression
```

N1 next: expose source-bound local room draft/visual preview through the actual
App and typed engine boundary, preserving ordinary scene review gates. Do not
silently seed/overwrite the user's active project or register this as a qualified
Burger motion profile. Then N2/N3 integrated preparation/session logs and N4/N5
autonomous mission/replay/comparison. Use the approved overnight plan; no physical
testing until the user returns and separately approves the mission scope.
