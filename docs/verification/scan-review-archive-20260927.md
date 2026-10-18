# Offline review archive — 2026-09-27 14:30 KST

## Completed scope

The scratch scan review can now explicitly save and restore a bounded replay
archive. This addresses loss of reviewed geometry on App restart; it does not
promote that geometry into the active project or authorize execution.

- New `scan-review-archive-1.0` retains the canonical base plan and recording,
  up to16 applied correction / conservative-map-overlay / undo operations,
  exact proposal/edit/result revision bindings and a final plan digest.
- Import verifies/recomputes the chain in a private workspace, then atomically
  replaces only the offline scratch workspace if its revision is still current.
  Failures and concurrent changes never partially overwrite the previous state.
- Pending proposals, route comparisons and transient review checkboxes are not
  restored. A new workspace ID is issued; source and alignment stay unverified,
  motion authorization false, physical validation NOT_RUN, review_required true.
- Restore trusts no serialized derived geometry or imported receipt as authority:
  supported bounded operations run through the same existing pure validators.
  Hashes provide consistency, not authentic sensor provenance or human approval.
- `Save replay archive` downloads exact server-created UTF-8 text with client
  SHA256 verification. `Restore offline archive (JSON)` imports explicitly only.
  Existing `Export review record` remains inspection-only and unchanged in schema.
  The UI now distinguishes these two file formats.
- API POST `archive-export` and `archive-import` under `/v1/product/scan-review/`
  require authentication, CSRF and exact field shapes; no filesystem paths,
  active project changes, broker commands or execution leases are accepted.
- Maximum archive10MiB,16 operations; inner original bundle5MiB. Duplicate keys,
  nonfinite values, deep JSON, stale revisions and wrong history hashes rejected.

Persistence currently means a user-selected saved file that can be imported into
a fresh backend. Automatic project persistence and active Twin promotion remain
the next separate integration; no existing SiteDraftRecord is silently modified.
The archive contains the synthetic world-aligned scratch contract, not the actual
nonuniform native recording converted into an invented world-aligned scan.

## Evidence

Full offline regression **326 Python /48 Web /TypeScript /build PASS**:

- `artifacts/scan-archive-regression-20260927-final/manifest.json`
- `artifacts/scan-archive-regression-20260927-final.log` preserves all output
  (Python groups138+74+33+9+9+6+46+11=326).
- Subsequent copy-only UI clarification passed the same48 Web tests and build;
  final browser runs below bind the resulting current source/build hashes.

Actual React → real isolated local HTTP backend:

| Input scope | Exact final run | Stages |
|---|---|---|
| Synthetic scratch correction/map/archive/undo/mobile | `artifacts/scan-archive-browser-20260927-final/` |12 PASS|
| Actual saved native scan + original photos + USD export | `artifacts/native-3d-browser-20260927-final/` |9 PASS|
| Explicitly synthetic coordinate reference fit | `artifacts/native-registration-browser-20260927-final/` |4 PASS|

Each contains `result.json`, `browser-result.json`, screenshots and applicable
downloaded artifacts. Active project bytes remain unchanged, external requests /
engine commands / page errors zero. Source/build hashes match before and after.
`browser-archive.json` is SYNTHETIC and must not be passed off as real room data.
`corrupt-archive.json` is an intentional rejected fixture, not a recommended file.

Last-frame USDA from the final saved-native run exactly matches the previously
tested Isaac r3 export SHA256:
`bcc02e330123283e398bb3276e82219bdb2b0c7431de84a7998b26d5482b56a1`.
Isaac was not rerun solely because the isolated scratch UI changed. Its prior
three-frame result retains its original scope; no new physics or motion.

The archive-restored screenshot and prior static3D handoff mobile page were
visually inspected; the prior page also passed all image decoding/local links and
desktop/mobile width checks. [Prior 3D result page](../../artifacts/native-3d-handoff-20260927/index.html)
is a preserved14:08 intermediate report, not this later regression count.

### Failures found and fixed

- Browser archive r1/r2 read an in-progress UI state: checking a disabled Undo
  button alone also matched the busy state. The test now waits for the third
  completed operation, enabled import input and completed HTTP restore response.
- r3/r4 exposed a real transport defect: JSON.parse/stringify in the browser
  converted integer-valued float representations (e.g.0.0→0), invalidating core
  digest bindings. Do **not** relax the original digest or coerce global schemas.
  Export now wraps exact archive text with its byte hash. r5 and final pass.
- First full archive regression missed newly separated archive unit tests in an
  explicitly enumerated suite. Added them to `verify_twinpulse.ps1`; final includes
  all8 archive tests plus new API test. Earlier results are preserved separately.
- PowerShell transcript omitted external-program test output on this host, so
  the final run also preserves stdout/stderr in the sibling `.log` file.

### Repeat only when relevant code changes

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests/integration -p test_scan_archive.py -v
.venv\Scripts\python.exe scripts/rehearse_offline_app.py artifacts/new-archive-run --archive-fixture
```

Use a new output directory; never overwrite previous evidence. Existing local
tools only, approved execution permissions as required. No new installations.

## Next work and unchanged blockers

Continue the approved offline window until17:45KST. The next useful increment is
a separately validated derived-review record and typed scene-build connection:
`SiteDraftRecord.from_dict` currently requires the original deterministic tool
expansion, and `ProductWorkflow.assert_site_build_allowed` requires the active
input/draft acknowledgement. Do not bypass either with scratch broker registration
or overwrite the generated draft's `site`. Preserve original draft/provenance,
make explicit derived identity, invalidate old review/build/run identities, then
validate local Isaac geometry separately before any runtime milestone claim.

Robot OFF is user-reported. No robot access/SSH/serial/sensor/motor/battery read,
deployment, physical test, paid API or installation was performed. Original
physical stopping qualification FAIL remains. Actual native/base/world alignment,
D2 physical execution adapter and complete real-room demo are still incomplete.
