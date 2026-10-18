# Saved native scan → 3D evidence and correspondence review

## Scope and result (2026-09-27, 14:08 KST)

User approved a four-hour offline preparation window, 13:46–17:45 KST.
Robot power is OFF by user report; this work did not connect to the robot,
read current battery, use serial/sensors/motors, deploy software, install tools,
call a paid provider, or change a user's Isaac stage. No physical readiness claim.

**Limited PASS:** saved native scan App export → exact USDA bytes → actual local
Isaac import and viewport capture for first/middle/last frames. Separately,
explicit coordinate correspondence proposal math/API/UI passed using synthetic
metric references. No actual room coordinate calibration or active Twin update.

## Implementation

- `native_scan_3d.py` exports all usable points in one selected frame, retaining
  original sample IDs, angles/ranges/quality/byte cursors and excluded IDs. USD
  units are metres; Z-up and z=0 describe the sensor drawing plane, **not floor
  height**. Sensor-native axes remain unverified. Export ignores display mirrors.
- Five authored prims only: World, TwinPulse, NativeEvidence, Returns, NativeAxes.
  No colliders, physics, robot, active mission, external asset references/payloads
  or time samples. Metadata binds the bundle and source claims, not verified TF.
- Authenticated/CSRF-protected `/v1/product/native-scan/3d-export` checks exact
  request fields and workspace revision. Browser verifies UTF-8 SHA256 before
  downloading `native-frame-NNN.usda`; no arbitrary server path writes.
- `native_registration.py` accepts 3–16 explicit original sample IDs and paired
  independent metric XY references. It evaluates each native Y convention
  separately and fits proper 2D rotation plus translation, never a scaled TF.
  No automatic correspondence, outlier deletion or automatic application.
- Proposal API `/v1/product/native-scan/registration` binds bundle/frame/scene
  revision/reference hash; rejects stale revisions, duplicates/nonfinite data,
  photo guesses and degenerate points. Source hashes are claims, not signatures.
- App shows both residuals and candidates, with synthetic/operator-unverified
  labels. `world_alignment_verified`, `sensor_to_base_verified` and
  `motion_authorized` remain false. Reimport clears a proposal. This temporary
  proposal is not a persistent calibration, TF, active Twin or robot command.

Reference JSON contract (`native-registration-request-1.0`): exact fields
`schema_version`, `bundle_digest`, `frame_index`, `target_frame` (fixed
`site_review_xy_m`), `scene_revision` (64 lowercase hex), `reference_kind`
(`synthetic_test_fixture` or `operator_supplied_metric_reference`),
`reference_sha256`, `pairs` of `{node_index, target_xy_m:[x,y]}`.
Maximum file 64 KiB, coordinates finite within ±100 m, triangle area at least
0.01 m², draft fit threshold 0.05 m. These are review/conditioning limits,
**not physical safety tolerances**. No actual room reference was fabricated.

## Verification evidence

| Scope | Result and explicit artifact |
|---|---|
| Python / Web / TypeScript / product build | 317 Python tests, 46 Web tests, TS/build PASS: `artifacts/native-registration-regression-20260927-r1/` |
| Real React → local backend; actual saved sensor recording | 9 stages PASS: `artifacts/native-3d-browser-20260927-r3/result.json` and `browser-result.json` |
| Synthetic correspondence through real App/backend | 4 stages PASS: `artifacts/native-registration-browser-20260927-r2/result.json` and `browser-result.json` |
| Actual local Isaac saved-data import | 3 frames PASS: `artifacts/native-3d-isaac-20260927-r3/result.json`; process exit 0 |

Actual Isaac frames 0/37/73 contain 346/386/389 usable points. Original IDs and
double angle/range/quality/cursor attributes match; point3f XYZ differs by less
than 1e-5 m from the input calculation. Original exported USD hashes remain
unchanged. The App download exactly equals the final-frame exporter output:
`bcc02e330123283e398bb3276e82219bdb2b0c7431de84a7998b26d5482b56a1`.
Bundle digest `d7e9e5056d4bdd742b3aef5dcc29237eb8f53fae5b47cc7be3f4c0632ca46463`.

Actual USD source validates before opening in Kit. Kit-created render settings
and its four standard viewport cameras are separately whitelisted and recorded;
they are not authored scan data. A preview camera/light exists only in the new
isolated stage, beneath TwinPulse. Timeline never plays. No existing stage saved.
Runtime emits existing Kit/Fabric VtValue warnings; this is not warning-free.
Viewport PNG and all tested attributes still passed. No dynamics or free space.

Both App runs store source/build hashes before/after and preserve the original
active project; external requests, engine commands, page errors and robot calls
are zero. Screenshots include desktop/mobile; synthetic mobile and native Isaac
last-frame captures were visually inspected. Native point density is deliberately
not replaced by invented surfaces or extruded room geometry.

### Reproduction with existing local tools

Use a new output directory per run, never overwrite prior evidence:

```powershell
.venv\Scripts\python.exe scripts\rehearse_offline_app.py --help
.venv\Scripts\python.exe scripts\rehearse_offline_app.py artifacts\new-registration-run --registration-fixture
C:\isaacsim\python.bat scripts\verify_native_scan_3d.py --bundle artifacts\photo-scan-review-20260927\native-scan-bundle.json --app-usda artifacts\native-3d-browser-20260927-r3\exported-native-frame-073.usda --output artifacts\new-native-isaac-run
```

Existing approved local execution permissions may be required. The Isaac command
opens only its own standalone new stage and does not start a physical robot.

### Failed attempts preserved

- Initial exporter tests lacked test import-path setup; corrected before passing.
- `native-3d-regression-20260927-r1`: sandbox temp-directory access failed;
  approved local execution rerun r2 passed 310 Python/45 Web before registration.
- `native-3d-isaac-20260927-r1`: checker incorrectly included Kit-added blank-type
  render scope in authored USD types. Separated pristine USD validation and
  explicit engine-added prim whitelist; r2/r3 passed. Authored types unchanged.
- Historical native-hour handoff expects its original eight-stage contract;
  do not feed the new nine-stage result into it or overwrite its evidence.

## Remaining gates / next increment

1. Derived review persistence with validated provenance and the existing typed
   scene-build boundary; active Twin still does not consume this native evidence.
2. Independently established sensor/native↔base/world axes and actual metric
   references. Optional review UI does not mean manual measuring is always needed;
   trustworthy device geometry or validated existing evidence may supply them.
3. Original physical stopping qualification remains FAIL (122 ms stable window
   versus required 200 ms). No criteria relaxed, no offline test can clear it.
4. Physical D2 runner/session integration and complete real-room demo remain open.

Continue offline during the approved window; physical tests require the user's
return and fresh approval. Current battery is not inferred from historical data.
