# Saved native scan → TwinPulse App — 2026-09-27

## Final offline handoff (13:35 KST)

Open `artifacts/native-scan-hour-handoff-20260927-final/index.html` without powering
the robot or starting the App. It links completed work, remaining gates, screenshots
and source identities. This is an offline evidence PASS, not a physical demo PASS.

- Final full regression: **305 Python / 44 web / TypeScript / production build PASS**
  (`129+64+33+9+9+6+44+11` Python), plus existing real-local synthetic9-stage browser
  rehearsal. Run: `artifacts/offline-rehearsal-20260927-133229-310a0d94/`.
- Actual stored-native-data real-local browser **8 stages PASS**:
  `artifacts/native-scan-hour-browser-20260927-r4/`. Curated source/build hashes
  were captured before and after execution, checked unchanged and rechecked by
  the handoff verifier. The raw capture and decoded nodes hashes were also
  independently compared with the saved bundle during handoff generation.
- New pure-core descriptive quality audit across74frames:29,538 samples,
  1,025 excluded (3.4701%),342–402 usable returns/frame; widest gap between usable
  directions2.89°. All72five-degree groups have at least one recorded return in
  the entire capture. None of these statistics proves free space, stationarity,
  sensor accuracy or current robot state; clearance stays UNKNOWN.
- `native-quality.json` is recomputed exactly during handoff verification.
  Native nonuniform beams remain unchanged: five-degree groups are statistics,
  not a resampled LaserScan, occupancy map or TF.
- Pure quality4 tests and handoff7 tests are included in the final305. Handoff
  cases reject changed photos/raw bytes/source bindings, missing export/stages,
  invented quality, path escape and oversized input; both UTF-8 and Windows
  PowerShell5 UTF-16 logs are supported.
- Final static handoff browser QA: local images decode, all links resolve,
  desktop/mobile no horizontal overflow, zero external requests/page errors.
  Initial mobile PASS-column wrapping was fixed without modifying evidence.

The synthetic rehearsal initially failed at its last screenshot because the new
native panel shared `.scan-review`; the old test's selector matched two panels.
Scoped that screenshot to the existing scratch panel (no acceptance weakened),
retained FAIL in `offline-rehearsal-20260927-132046-15d3b4a3`, then reran all tests.
The first handoff generation rejected a UTF-16 regression log instead of silently
miscounting it; added explicit BOM decoding and a regression before final output.

Next physical session is prepared in
`docs/planning/TWINPULSE_NEXT_PHYSICAL_SESSION_2026-09-27.md`: single read-only
inventory/board report after fresh authorization, then only unresolved axis/stop
checks under separate scope. No physical check was executed in this work hour.

The earlier milestone below remains historical and is superseded by these final
counts and r4/source-bound results.

## Verified milestone (13:14 KST)

The production React App now has **Native scan · Saved photo review**. It imports
the strict additive `native-scan-bundle-1.0` contract through the authenticated
local API, preserving nonuniform native angles and original sample identities.
It does not reinterpret this as `scan-recording-1.0` or invent a robot/world TF.

Actual input: `artifacts/photo-scan-review-20260927/native-scan-bundle.json`.
Canonical bundle digest:
`d7e9e5056d4bdd742b3aef5dcc29237eb8f53fae5b47cc7be3f4c0632ca46463`.
The 74 complete frames contain 29,538 original samples; partial start/end scans
remain in the source recording but are not included as complete frames. Every
included angle/range/quality/source-byte cursor was compared with `nodes.ndjson`.
Last frame: 403 samples, 389 usable, 14 excluded by the existing zero/short-low-quality rule.

## Capabilities and boundaries

- Import / previous-next-select frame / presentation-only orientation / exact
  native-bundle export. No interpolation or fabricated ranges.
- Original room and top-view JPEGs are selected locally; SHA-256 mismatch is
  rejected, matching photos stay in the browser and are not uploaded to a provider.
- Photo-up = window is shown as a user statement, not robot-forward. Native zero,
  handedness, world alignment, heights and full furniture dimensions remain unknown.
- Reflection candidates are explicitly not rigid TF. Default view is unmodified
  native angles, not the earlier qualitative mirror1 candidate.
- The export builder checks existing raw receipt, packet/sample inventory, pinned
  photo/raw association and decoded-nodes/photo hashes. The App only validates
  imported metadata and selected photo bytes; it does not independently verify
  raw acquisition, authorship, geometry or live state.
- Session-local inspection only: no active project writes, command broker lease,
  engine command, live connection, physical validation, free-space or demo approval.
- Bounds: 8 MiB bundle, 100 frames, 50,000 samples, 4,096 samples/frame, two JPEG
  bindings and eight presentation hypotheses. Exact fields, finite values,
  original index ordering and stale workspace revisions are checked.

## Validation evidence

- Full existing offline verification: **283 Python tests, 43 web tests, TypeScript
  and production build PASS**. `artifacts/native-scan-hour-regression-20260927/`.
  (`125+46+33+9+9+6+44+11` Python; new native tests are included.)
- Focused native tests: core8 + workspace/actual-data3 + actual HTTP1 PASS.
- Real browser → production React → real local HTTP API, saved actual input:
  `artifacts/native-scan-hour-browser-20260927-r2/result.json` and
  `browser-result.json`: **7 stages PASS**, no external requests/page errors/engine
  commands, active project bytes unchanged. Tests cover wrong-photo rejection,
  both original JPEGs, first/middle/last frame counts, exact export roundtrip,
  invalid authority-field rejection and mobile no-horizontal-overflow.
- Desktop/mobile screenshots manually inspected: points, legends and both source
  photos visible; mobile stacks sections. Mobile screenshot retains the deliberate
  invalid-import error from the negative test; old valid evidence stays unchanged.
- Initial core test exposed negative first source cursor acceptance; fixed and
  rerun. Initial sandbox build/temp-folder restrictions were not bypassed: normal
  approval preceded successful local-only runs. First browser run failed because
  its exact accessible-label selector did not match the nested select label;
  corrected the test locator, retained original FAIL, fresh r2 PASS.

## Reproduce without the robot

Use existing dependencies; do not install or launch a robot/engine:

```powershell
.\.venv\Scripts\python.exe scripts/export_native_scan_bundle.py --output <new-file.json>
.\.venv\Scripts\python.exe scripts/rehearse_offline_app.py <new-results-directory> --native-bundle artifacts/photo-scan-review-20260927/native-scan-bundle.json --photo-dir artifacts/photo-scan-review-20260927
```

The exporter and rehearsal refuse to overwrite an existing output file/directory.
For interactive App use, import the bundle in the Native scan panel and attach
`room.jpg` and `top-view-window-up.jpg` when requested. No extra robot capture is
needed to reproduce the present review. Separate existing scratch review still
uses synthetic/world-bound contracts and is not implicitly linked to this panel.

## Physical status remains separate

User reports robot powered OFF for this work hour. No robot access or new battery
reading occurred. Last measured 12:14 KST state and previous physical stop FAIL
remain historical evidence. Software completion here does not resolve native/base
alignment, physical stopping qualification, live active-Twin updates, automatic
route optimization or integrated physical demonstration.
