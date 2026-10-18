# Private preservation snapshot — 2026-10-18

This is an archival **pre-release**, not a public release or a claim that all robot functions work. The existing `lee2017-bit/TwinPulse` repository remains private.

## Frozen package with actual SIM evidence

- Build: `20261018T044930Z-d0d4e62d6701` (Windows x64).
- Frozen source-manifest SHA256: `d0d4e62d67010295e5b30e6350a352fbe0dd6344b4ad964e7919997c11a33a93`.
- ZIP SHA256: `b40e498fc19eda8b045152c92cddc91def3b90f824e047146a47f01bc1f1dd8f`.
- ZIP bytes: `188900955`.
- Actual installed Electron Test/Isaac SIM fresh27steps, cold12steps, lineage8steps, lineage-cold3steps were separate completed journeys. They are not one uninterrupted50-step run. Ordinary start/repeated start and shutdown observations were separately recorded.
- Photo-relative layout remains uncertain/PARTIAL. Native full interaction/Explorer/OS clipboard/clean-PC acceptance and physical driving are not certified by these results.

The ZIP is preserved without editing or relabelling its original manifest. It is a frozen local-development package with `dirty:true`; its original `git_revision` alone did not identify all local source changes. Its exact shipped runtime sources, compiled web files, original dependency notices and `source-manifest.json` are in `TwinPulse/_internal/resources/`. The Git preservation commit also contains subsequent battery-display/startup fixes from build08 and supporting tests; **do not claim that rebuilding this newer checkout reproduces frozen06 bytes**. Use the ZIP's bound resources and manifests to inspect the exact archived runtime.

## Latest development checkpoint is separate

Current installed development package: `20261018T060740Z-eb840a4afcaa`, source-manifest SHA256 `eb840a4afcaaca7f30a4f986b53d186ec8f569714899d1aff49303e10f54386d`. It fixed a real missing-percent UI crash and adds startup diagnostics. Real Connect and LiDAR receipt were observed, but stationary trial `4bf36ea0ee0045c99ff89762eaf88f2b` was INCONCLUSIVE; ROS freshness blocked Prepare/driving. Operation `f28b9e909309481084c8679301e832cd` sent no wheel command. Recording ended incomplete after ENOSPC. These failures remain unresolved and are not SIM or hardware PASS.

## Use and maintenance

Extract the entire frozen package, verify SHA256 and read its README. Isaac Sim remains a separately installed prerequisite. Use your own provider credentials; personal credentials, photos, user projects and raw robot captures are not release assets. The frozen package contains development robot features and a known physical Connect UI defect: use it as a **SIM rollback**, not for physical driving.

Keep current08, last SIM rollback06 and boot-timeout reproduction build01 locally. Do not delete projects, settings, raw logs, source manifests or pinned original assets to reclaim space. Obsolete installer copies and reproducible intermediate build trees can be removed only after source push and remote ZIP download/hash verification. No force push, history rewrite, repository visibility change or system pagefile/Docker/Isaac cleanup is part of this request.
