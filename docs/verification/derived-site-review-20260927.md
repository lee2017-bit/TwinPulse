# Derived site review record and actual Isaac boundary

2026-09-27 14:44 KST · approved offline window · robot OFF by user report.

## Implemented, with limits

`DerivedSiteReview` is a separate persisted review, not a replacement
`SiteDraftRecord`. It retains the full original input/tool-plan draft. Creation
and every load revalidate that deterministic expansion, require the archive's
entire base plan to match it exactly, and recompute the archive operation chain.
The final derived geometry and identity must equal the recomputed result.
Empty edit history, changed original geometry, inconsistent revision/derived
geometry and claimed execution/source authority are rejected.

`DerivedReviewStore` uses an explicitly supplied sidecar path, a uniquely named
temporary file, flush/fsync and atomic replace. A save failure retains the previous
record and cleans only that save's own temporary file; unrelated partial files and
the active project are untouched. Input is bounded to20MiB; duplicate keys,
nonfinite values, excessive nesting and tampered records fail closed. The original
draft and source provenance remain intact. Review/build/motion authority stays
false. Hashes establish internal consistency, not real-world calibration.

**This increment is the record/storage and typed adapter foundation only.**
There is no production API/UI promotion button or active ProjectStore integration
yet. A persisted record alone cannot register a build, grant a lease, acknowledge
a scene, run a mission or connect to a physical robot. The existing live project
was not selected, replaced or upgraded by this new store.

## Verified

- `artifacts/derived-review-regression-20260927-r3/manifest.json` and sibling
  `.log`: full offline **331 Python /48 Web /TypeScript /build PASS**.
  Python groups138+79+33+9+9+6+46+11. New five tests cover source/geometry binding,
  roundtrip, forged direct records, atomic save failure and strict parsing.
- `artifacts/derived-review-isaac-20260927-r2/result.json`: actual isolated Isaac
  **five checks PASS**, process exit0. Inputs are explicitly **synthetic**.
  Source draft → disk-reloaded derived draft goes through the existing typed
  `build_site_scene` adapter/compiler. All authored object positions match the
  relevant scene; synthetic wall moves(1,1,.5)→(1.1,1.1,.5), preserving height.
  `/ExternalKeep` remains unchanged, no Robot/Task prims, no Run permission,
  no timeline playback. A stale build identity fails without replacing the derived
  geometry; identical derived build retains its fingerprint.
- Final Isaac verifier imports classes without starting Extension UI, reading
  user settings/credentials or restoring a user project. Inherited managed bridge
  configuration is removed without reading/printing values; fallback state is
  isolated under the newly created output directory.
- Last existing App browser runs and their source/build remain unchanged by this
  new standalone module. No browser promotion flow is claimed as tested here.

Reproduction with existing local tools, new output path only:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests/integration -p test_derived_site_review.py -v
C:\isaacsim\python.bat scripts\verify_derived_site_review.py --output artifacts\new-derived-isaac-run
```

### Failed attempts / remaining test reliability issue

Initial sandbox temporary-directory access failed, then approved local execution
was used. Test fixture mistakes (`args` instead of `arguments`, tuple mutation
before JSON roundtrip) were corrected; unit r1/r2 failed logs are retained.

Isaac r1 passed the geometry tests but enabled the Extension's full startup,
which can load existing settings. The final r2 verifier avoids that startup and
asserts no Extension UI instance exists. Only r2 is the final isolation evidence.

Full regression r1 and r2 each hit an existing HTTP rejection-path
`ConnectionAbortedError`/WinError10053 (R5 unauthenticated3D export, then R4
foreign-Origin bootstrap). No assertion was weakened and no retry added to the
product. After Isaac stopped, isolated R4/R5 **25 tests PASS** in
`artifacts/derived-review-http-isolated-20260927.log`, followed by full sequential
r3 PASS. **Root cause remains unproven; a passing rerun does not resolve the
intermittent connection issue.** Preserve failures for focused investigation.

## Next bounded increment

Wire this record through `ApplicationService`/`ProductWorkflow`, not directly from
scratch into the broker. Use the current original site draft and input identity,
save the derived sidecar separately, invalidate prior acknowledgements and expose
the new derived identity for explicit review. Input/generation/provider changes,
restore, stale workspace and persistence failures must fail safely. Existing
`assert_site_build_allowed` must still guard typed Build, and Run stays unavailable.
Add actual local UI→API and actual Isaac verification before claiming active Twin
integration. Do not replace the original deterministic `SiteDraftRecord.site`.

No robot/SSH/serial/sensor/motor/deployment/current-battery reads, installation,
paid APIs or physical tests. Actual native/base/world axes remain unqualified,
original stopping qualification remains FAIL, D2 physical mission integration and
the complete real-room demo remain incomplete. Continue offline until17:45KST.
