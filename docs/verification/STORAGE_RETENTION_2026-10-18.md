# GitHub preservation and reviewed storage cleanup — 2026-10-18

## Verified sequence

1. Existing repository `lee2017-bit/TwinPulse` was confirmed **private** and kept private.
2. Source checkpoint `90a7b82679f9e848fa13c4cb4589cb0498595ca2` was pushed to main and compared with `git ls-remote`. Runtime outputs/binaries/private images were excluded. Known key-shape scan findings0 over1571candidate source files/21,463,120bytes is a bounded check, not proof that all possible sensitive information is absent.
3. [Frozen SIM archive](https://github.com/lee2017-bit/TwinPulse/releases/tag/sim-alpha-2026-10-18-archive) ZIP188,900,955bytes and SHA256SUMS were uploaded using existing Git authentication kept only in memory. Both assets were actually downloaded and SHA-checked. ZIP SHA256: `b40e498fc19eda8b045152c92cddc91def3b90f824e047146a47f01bc1f1dd8f`.
4. Only then was the absolute-path dry-run reviewed and deletion applied under the existing maintenance kernel lock. Protected/running/reparse/out-of-scope checks were enforced. No app, robot or provider was started.

## Result

| Class | Removed targets |
|---|---:|
| Obsolete installed releases |139|
| Old distribution ZIPs |167|
| Reproducible intermediate dist/work/staging/desktop-build folders |514|
| Total / failures |820 /0|

Logical target bytes120,034,262,581 are not physical disk allocation. Observed C: free bytes3,522,523,136→71,882,428,416; increase68,359,905,280bytes (**63.66GiB**), ending around66.95GiB. Other simultaneous system activity can also affect the exact free-space measurement.

Installed releases142→3, and their corresponding local build folders/ZIPs were retained:

- Current08: `20261018T060740Z-eb840a4afcaa`.
- Last full SIM acceptance rollback06: `20261018T044930Z-d0d4e62d6701`.
- Startup-timeout reproduction01: `20261018T054101Z-10f256a1732a`.

All six retained package directories passed1609-file hash verification each, and all three ZIPs matched their original hashes. Active pointer remained08. Protected user runtime projects/devices/provider-evidence/harness/library/inputs/source-blobs and original ITM input: **14049files/2,033,906,967bytes, SHA comparison UNCHANGED**, no added/changed/missing files. Old small build/source manifests are retained separately. Photos, raw sensor/failure logs, projects, settings, source checkout, original assets, Docker/WSL, Isaac installations, system pagefile and Git history were not deleted.

Deleted historical binaries are not all backed up as remote assets. The protected06 archive can be restored from GitHub with its original SHA, and the three retained versions remain local. Arbitrary deleted old build bytes are not promised recoverable or reproducible exactly.

## Supplementary checks and limitations

- Existing build venv device-free tests:19physical-session protocol/storage +32process-manager cases PASS; these are not new App/Isaac/hardware acceptance. System Python attempts first failed because pytest/Pillow were absent; no dependencies were installed to hide that failure.
- Frozen06 package integrity and remote ZIP download passed. New source contains later08 fixes; no claim that rebuilding the Git tag recreates06 byte-for-byte.
- Original license/patch whitespace was left unchanged rather than reformatting upstream material to satisfy whitespace diagnostics. Git fsck had no integrity errors; dangling historical objects were not deleted.
- Scripts `prune_preserved_builds.ps1` and `retention_data_sentinel.py` record the reviewed maintenance. The prune script has date-specific pins/proof and refuses unreviewed active releases or changed remote preservation. Refresh these only after actual review, not by removing its guards.
- **Automatic release retention in the installed EXE was not implemented by this cleanup.** Before another large build/install, follow AGENTS retention rules and assess product-level GC/pins. Do not resume indefinite accumulation or ask the user to clear unrelated files first.
- Physical Connect/scan/Prepare trials remain partial/NOT_READY due native/ROS freshness and incomplete recording. Recovering disk space does not prove those causes fixed. No physical driving or new full UI acceptance occurred here.

## Local evidence (not uploaded)

`outputs/github-preservation-20261018/report.html` is the one local maintenance report. It links `remote-verification.json`, the exact dry-run/applied plan, per-target removal receipts, protected-data before/after SHA manifests and retained-package verification. These intentionally remain local, along with private captures and projects. New model/API calls0, additional provider costUSD0, new installs0, paid Cloud0, GitHub Actions0. Git commit/push and private prerelease assets were explicitly requested; no visibility change or force push occurred.
