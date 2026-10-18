# Derived review: product selection and actual Isaac boundary

2026-09-27 15:22 KST · approved offline window · robot OFF by user report.

## Implemented

ApplicationService now owns an explicit, session-local derived selection plus a
separate `*.derived-review.json` sidecar adjacent to its project file. Adoption
requires the current input digest, original scene revision and displayed scratch
workspace revision. The complete original SiteDraftRecord and archive edit chain
are revalidated before storage. Original project bytes remain unchanged by adoption.

ProductWorkflow registers the new geometry under a derived identity, clears the
old acknowledgement, and requires a new scene acknowledgement before the existing
typed Build gate. Connected engine capabilities and a current lease are still
required; selection itself issues no commands. UI/API show original scene identity
and `offline_review_unverified` geometry provenance. Original tool-plan provenance
is retained, not relabelled as a generation of the corrected geometry.

The Scan review panel has explicit **Select scratch edits as scene draft** and
**Restore saved derived scene for review** controls. Both require a checkbox and
switch to the scene review card; neither builds automatically. Restore does not
restore acknowledgement. Startup does not load/select the sidecar automatically.
The stored file is evidence only. New input (even identical reselection), provider
change, cancellation and generation clear eligibility. Stale workspace/input or
persistence failure cannot leave an acknowledged derived artifact available.
A concurrent change may leave a valid review file on disk but never gives it
selection authority. Once adopted, geometry is a frozen review; later scratch
edits require another explicit adoption rather than silently altering the scene.

POST `/v1/product/derived-review/adopt` accepts exactly input_revision,
source_revision, workspace_revision; `/restore` accepts only the first two.
Both use existing product authentication and CSRF checks. Site-plan Run is now
blocked during input/generation transitions as well as during draft review.

## Verification

- Full regression `artifacts/derived-selection-regression-20260927-r2/manifest.json`
  plus sibling log: **343 Python /52 Web /TypeScript /production build PASS**.
  Python groups138+87+33+9+9+10+46+11. Eight selection tests include actual HTTP,
  source preservation, restore, old acknowledgement, engine absence, stale input,
  source/workspace, same-input/save race, workspace/save race, disk failure and
  corrupt sidecar. Four React tests cover explicit controls and error refresh.
- `artifacts/derived-selection-browser-20260927-final/result.json`: **five actual
  local React→authenticated API stages PASS**, synthetic source/scan only.
  No engine connection, lease, command or external request. Original initialized
  project bytes unchanged; derived sidecar saved. Desktop scene card and mobile
  selection panel screenshots inspected; no horizontal overflow.
- `artifacts/derived-selection-isaac-20260927-r1/result.json`: **six checks PASS**,
  actual isolated Isaac process exit0. Application selection→new acknowledgement→
  CommandBroker→actual adapter/compiler→receipt/snapshot, source then derived wall
  at(1,1,.5)→(1.1,1.1,.5). Correct scene identities/fingerprints, stale denial,
  idempotence, unrelated prim preservation, no robot/task/Run/timeline play.
  No Extension UI startup or user project/settings restore.
  **Browser/API and workflow→Isaac are separately tested boundaries, not yet a
  single combined browser→Isaac E2E run.** Geometry fixture remains synthetic.
- Existing archive browser12 stages and saved-native browser9 stages PASS with
  final code: `derived-selection-archive-browser-20260927-final` and
  `derived-selection-native-browser-20260927-final`. Source/build pre/post hashes
  match; real saved 74 frames and original photo hashes preserved. Native USD SHA
  bcc02e330123283e398bb3276e82219bdb2b0c7431de84a7998b26d5482b56a1 remains identical
  to prior actual native Isaac import evidence. Native recording is NOT used as
  invented world-aligned synthetic review data.

Reproduce using existing tools and new output directories only:

```powershell
.venv\Scripts\python.exe scripts/rehearse_derived_review.py artifacts/new-derived-app-run
C:\isaacsim\python.bat scripts\verify_derived_site_review.py --workflow --output artifacts\new-derived-workflow-isaac
```

## HTTP rejection delivery correction and failed attempts

The first full regression failed in an existing missing-CSRF request with Windows
10053, preserved in `derived-selection-regression-20260927-r1.log`. A standalone
60-request loopback reproducer then failed the same way before the correction:
`http-rejection-before-20260927-r2.log`. Its first attempt used the wrong expected
error-code name; that fixture error is separately retained in the preceding log.

Early authentication/Host/Origin/CSRF rejection previously closed a connection
without consuming its body. `_discard_unread_body` now discards, never parses,
only unambiguous bodies up to512KiB with a **total100ms deadline** and16KiB chunks,
then sends the original rejection. Already consumed bodies are not read twice;
oversized/ambiguous framing is skipped. The old oversized-body drain, which had
no time bound, now uses the same bounded path. No credential, CSRF, origin,
payload acceptance rule or response assertion was weakened.

After correction the identical60-request test, incomplete-body deadline,
byte/duplicate-drain bounds and ambiguous-framing tests pass, as does the full
regression. This demonstrates correction of the reproduced rejection-body case,
not a claim that every possible Windows network interruption has been eliminated.
`http-rejection-after-20260927-r1.log` contains the initial10 passing focused checks;
the final full regression includes all four HTTP-delivery tests.

Initial sandbox temp-directory writes failed; approved local execution was used.
The first React run found an extra inapplicable checkbox in the legacy v1 flow;
derived controls now render only for a v2 site draft. All52 final tests pass.
Browser r1 stopped at checkbox post-click checking; explicit click followed by
exact server acknowledgement assertion passes in r2 and final. Original failed
artifacts remain. No timeout assertion, stop criterion or content rule was relaxed.

## Remaining / next

Run a combined browser→API→broker→actual Isaac rehearsal if the existing local
runtime permits isolation, then consolidate the final handoff. Production
selection/build plumbing is now available, but the real room has no qualified
native/base/world transform or independently measured correspondences. Do not
promote photo-up/window or reflected display hypotheses to TF or map geometry.
Original physical stop qualification remains FAIL; D2 physical mission adapter,
real-room alignment and the complete physical demo remain incomplete. No robot
access, live battery read, deployment, install or paid API occurred. Continue
offline only until17:45KST, then pause the existing heartbeat.
