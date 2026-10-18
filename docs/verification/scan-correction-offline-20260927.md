# D5 second slice — manually reviewed XY draft correction and undo

2026-09-27 04:14 KST. **PURE OFFLINE CORE TESTED SCOPE PASS**.
No App/API/Isaac correction integration yet. No robot access, deployment, serial,
sensor/motor commands, actual Isaac, paid requests, install, commit or push.
D3/D5 and final demo remain PARTIAL; physical settling122ms<200ms FAIL is unchanged.

## Implementation and boundary

`packages/twinpulse_core/src/twinpulse_core/scan_correction.py` adds:

1. `LandmarkPair`: an explicit original frame/beam index plus a selected box's local
   perimeter XY point. No nearest-object or automatic correspondence guess.
2. `propose_xy_correction`: binds the complete parent SitePlan, scene, robot-profile
   and recording digests; fits only a translation to2..16 distinct correspondences
   from one claimed-stationary snapshot. Source geometry must survive existing
   SitePlan persistence/digest validation before proposal.
3. `apply_xy_correction`: requires the exact reviewed proposal digest, re-computes
   it from the current recording and rejects changed/stale inputs. A pure function
   returns an immutable before/after receipt; it does not mutate an active project.
4. `undo_xy_correction`: accepts only the exact current after-plan and reviewed edit
   digest; restores geometry as a NEW child revision, not the old authority/identity.

Both apply and undo clear navigation_map and mission, set review_required=true and
create a new scene digest. Previous Build identity cannot match the changed scene;
this is a contract invariant, **not tested live broker/Isaac revocation**. Robot
instance, Z, dimensions, rotation, flags, stable object IDs, observation bindings,
unselected/occluded objects and all geometry outside the selected object's XY are
preserved. No new obstacle or deletion. Floors, dynamic/non-collidable objects,
cylinders and tilted objects are excluded. Scene source is `manual`, source_ref
links the proposal/undo receipt; it does not pretend synthetic data is verified scan.

`ScanFrame.world_point()` now projects an original full-resolution beam for both
bounded replay and correspondence fitting. Missing rays cannot be used as evidence.

## Deliberately limited policy

Fixed `offline_manual_xy_translation_v1`: maximum translation0.5m, maximum per-pair
translation residual0.03m, minimum landmark span0.05m, negligible<1e-6m changes
rejected. These are bounded **offline draft review limits**, not measured sensor
uncertainty or physical acceptance criteria. The implementation does not fit or
verify extrinsics, yaw, scale, SLAM, ICP, automatic associations or symmetric-site
ambiguity. It cannot establish that selected returns belong to a stationary wall
instead of a moving object. It relies on explicit reviewer associations and keeps
source_verified/alignment_verified/motion_authorized/demo_ready=false and physical
validation NOT_RUN in previews. Map/mission must be rebuilt and reviewed later.

The digest expresses the exact proposal selected for review; it is not a signature,
user authentication or proof that a person reviewed it. A future App service must
own receipts server-side, authenticate requests, lock current revisions, invalidate
acknowledgements/artifacts and prevent any live execution without its separate gates.
Do not accept caller-supplied `AppliedCorrection` objects as trusted history.

## Verification

- New correction22 tests PASS, stored-scan15 tests PASS; complete core90 PASS.
- Known synthetic(+0.2m,+0.1m) correction recovered; rotated-box local coordinates,
  height/shape/rotation/unseen preservation, map/mission invalidation, exact review,
  stale apply/undo, changed recording/mission/robot/review, modified proposals,
  bad/missing/duplicate/outlier/insufficient-span correspondences and provenance
  limits covered. Apply→undo restores geometry but neither original revision nor
  old map/mission/approval. No actual sensor sample substituted for the fixture.
- Initial roundtrip test exposed integer-vs-float geometry digest instability in
  a typed test fixture. Fixture now uses canonical float geometry and proposal entry
  rejects non-persistable parent plans; global digest rules were not weakened.
- First complete regression failed at a pre-existing saved-report HTTP test with
  WinError10053(local connection aborted). [FAIL manifest](../../artifacts/runs/20260927-041128/manifest.json)
  retained. The isolated test and next full run passed; root cause of the transient
  connection abort is **not established**, and no auth/CSRF checks were weakened.
- Final full `scripts/verify_twinpulse.ps1 -SkipIsaac`: **Python212, Web23 + build PASS**.
  Python: core90, CLI/report15, provider33, R1=9, R3=9, R4=6, R5/S2/S3=39, R6=11.
  [PASS manifest](../../artifacts/runs/20260927-041255/manifest.json),
  [captured full output](../../artifacts/scan-correction-full-regression-20260927.log).
  Actual Isaac NOT_RUN; real robot NOT_RUN.

Reproduce core only:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s packages/twinpulse_core/tests -p 'test_scan*.py' -v
```

## Next dependency

Integrate saved scan review/explicit correspondence selection and isolated draft
apply/undo in ApplicationService/API/React, then decide the versioned promotion
contract to the actual scene. Existing `SiteDraftRecord` verifies deterministic
tool-plan expansion; do NOT overwrite its `site` with corrected geometry while
leaving the old tool plan/hash. Introduce an explicit derived-draft/edit record or
keep the offline review isolated until that persistence boundary is implemented.
After that, prepare D6 same-condition comparison and a clearly labelled synthetic
rehearsal. Actual scan/TF and physical stopping gates still wait for the operator.
