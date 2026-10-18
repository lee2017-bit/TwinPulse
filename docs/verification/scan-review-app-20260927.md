# D5 third slice — isolated App scan review

2026-09-27 05:19 KST. **ISOLATED OFFLINE APP REVIEW TESTED SCOPE PASS**.
Not an actual robot/Isaac demo or active-project scene correction. No SSH, serial,
robot power/sensor/motor commands, deployment, paid API, installs, commit or push.
Original physical settling122ms<200ms FAIL and real LiDAR/TF gates remain unchanged.

## Connected path

ApplicationService owns a new `ScanReview` session-local scratch workspace. Its
state never changes `SiteDraftRecord`, the project store, broker artifacts, leases
or engine commands. This preserves deterministic tool-plan/site identity in the
existing project path. The product-facing adapter exposes the workspace through
authenticated `/v1/product/scan-review` GET and import/propose/apply/undo POST routes.
All mutations retain existing CSRF checks; exact bodies reject arbitrary paths,
commands and caller-supplied receipts. Unsupported actions are rejected.

- Import accepts JSON **text** preserving strict duplicate/nonfinite checks. Inner
  bundle≤5MiB, HTTP import body≤8MiB, exact `offline-scan-bundle-1.0` shape contains
  matching `site_plan` and `recording`. Other mutation bodies remain≤256KiB.
- Existing site/scan contracts revalidate identities, data sizes, time/frame/units.
  Imported approvals are not adopted; scratch review_required=true. Invalid imports
  leave the previous scratch workspace unchanged. Successful import replaces it.
- Server owns pending proposal and applied receipt; clients submit revision IDs,
  not edit receipts. A lock and fresh workspace revision prevent stale/multi-tab
  proposal/apply/undo from overwriting later work. Repeated apply is rejected.
- Apply/undo use the tested core and clear scratch map/mission/review. New scene
  identity no longer matches the old recording: another proposal needs a newly
  matching bundle. Undo does not restore previous approvals or old scene identity.
- GET export produces `scan-review-export-1.0` for inspection only: execution
  authority=false, restore_supported=false. Restart discards workspace/history.
  This is **not persistent derived-project support**, nor a supported import format.

## UI

Collapsed **Scan review · Offline scratch draft** panel makes no request on mount.
Manual local bundle import/refresh shows explicit provenance, invalid-ray count and
bounded SVG top-view overlay: imported boxes dashed, current scratch boxes blue,
saved returns orange. XY and rotation are shown; no height reconstruction. Cylinder
geometry is explicitly not drawn/corrected in this view.

Advanced explicit landmark-pair JSON supports the existing2..16 correspondence
contract. Preview shows proposed delta/residual. A review checkbox is required to
apply or undo, reset after actions/field changes. Changed pair input hides stale
proposals; refresh replaces pair controls with the returned proposal's exact pairs.
Only scratch state changes. No Run/Deploy/Connect control exists in this panel.

The browser download exports the review record, not a runnable project. No arbitrary
filesystem path is sent to the backend. Native file picker language follows the OS;
product labels are English. Desktop and390px mobile have no horizontal overflow.

## Rehearsal files and reproduction

`scripts/prepare_scan_review_rehearsal.py` is a **developer verification helper**
using the known synthetic regression fixture, not a real recording exporter. It
creates only a new output directory and produces a matching bundle, pairs and actual
pure-service snapshots for UI tests. It does not connect to any device/provider.

Prepared files:

- [Import bundle](../../artifacts/scan-review-rehearsal-20260927/bundle.json)
- [Matching explicit pairs](../../artifacts/scan-review-rehearsal-20260927/pairs.json)
- [Service snapshots](../../artifacts/scan-review-rehearsal-20260927/states.json)
- [Desktop after apply](../../artifacts/scan-review-rehearsal-20260927/scan-review-desktop.png)
- [Mobile after undo](../../artifacts/scan-review-rehearsal-20260927/scan-review-mobile.png)

With an already running built App, open the panel, import bundle.json, paste the
pairs.json array, Preview XY correction, inspect(+0.2m,+0.1m), check review, Apply to
scratch draft only; check review again and Undo. No robot is needed. For another
fresh fixture directory, run from repo root:

```powershell
.\.venv\Scripts\python.exe scripts/prepare_scan_review_rehearsal.py artifacts/my-new-scan-rehearsal
```

This helper depends on checked-in test fixtures and is not part of the user runtime.

## Evidence and limits

- New service9 tests cover import/propose/apply/undo/export, reset, stale versions,
  preserved state on rejection, receipt ownership, bounded strict JSON and no aliases.
- Real local HTTP tests cover401/403, matching review IDs, no lease/operation/project
  changes, stale apply, export, undo, unknown commands/paths/forged receipt rejection.
- New React6 tests cover no autoload, provenance/overlay, exact reviewed apply,
  field-change invalidation, malformed pair JSON and oversized upload rejection.
- Full `scripts/verify_twinpulse.ps1 -SkipIsaac`: **Python223 / Web29 / build PASS**.
  Python: core90 + offline CLI/report/review24 + provider33 + R1=9 + R3=9 + R4=6 +
  R5/S2/S3=41 + process-manager11.
  [Manifest](../../artifacts/runs/20260927-051728/manifest.json),
  [full output](../../artifacts/scan-review-app-regression-20260927.log).
- `node e2e/scan-review-browser.mjs` from apps/twinpulse-web: desktop/mobile PASS,
  import→preview→checkbox→apply→checkbox→undo, correct exact IDs and no page errors.
  **Browser HTTP was mocked with actual pure-service synthetic snapshots.** Real
  HTTP correctness was tested separately; browser→real backend E2E is not yet run.
  Mobile screenshot visually inspected. Actual robot/Isaac NOT_RUN.

Next: D6 same-condition geometric route comparison and clearly labelled offline
rehearsal; real-backend browser integration if feasible. Active Twin promotion still
needs an explicit derived-draft persistence/artifact contract plus actual Isaac
validation. Do not mark the isolated scratch review as completed scan→Twin product
integration or physical navigation.
