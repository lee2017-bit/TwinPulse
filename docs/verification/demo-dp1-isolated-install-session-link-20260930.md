# DP1 installed-PC smoke and collection-context link — 2026-09-30

## Scope

Robot OFF throughout: no SSH, serial, physical sensors/motors, source transfer, real ROS capture, drive, or paid call. This is a dirty-tree **local development release**, not a frozen clean release or company-PC acceptance.

## Installed-PC path

- Added an offline builder input for an existing Windows Pillow wheel. The filename and SHA-256 must match the pinned lock; the web dependency resolution runs with `pnpm --offline --frozen-lockfile`. Normal build behavior remains available when this input is absent.
- A source-and-web release built without network (`tp-local-dp1-session-r2-20260930`, 295 manifest files, `dirty=true`). Installer `-CheckOnly -AllowDevelopment` verified every listed hash and required file.
- The first isolated install correctly stopped at the pre-existing global launcher lock. Its recorded PID 5036 had no running process. The lock was **not removed**. The installer now has an explicit `-IsolatedTest` path that permits a non-default install root only when the lock can be parsed and its owner PID is absent; default install and any active/unknown lock remain blocked. With that switch, the release installed entirely beneath `artifacts/offline-install-dp1-session` using `pip --no-index --require-hashes` and the bundled wheel. No existing installation was replaced.
- The installed release's own Python ran `--collection-only`: `COLLECTION_CONTRACTS_PASS_DEMO_LOCKED`, robot contact `NOT_RUN`. The installed launcher then ran with an isolated state directory, `--offline --headless --no-browser`, reached `TWINPULSE_APP_READY`, and its local UI returned HTTP 200. The launcher was interrupted after the smoke test; its owned backend/engine PIDs 18244/7984 and isolated lock were absent afterward. The PTY reported exit code 1 on Ctrl-C, so this is a startup/cleanup smoke, not a graceful exit-code assertion.

## One collection record and App reference

The authenticated no-motion start now snapshots the active App scene revision and robot profile, or records `UNAVAILABLE`. The default-project identity and collection request/job ID persist with the saved readiness result and survive App service reopening. The UI shows that reference beside the captured robot boot/release (when present) and odom/scan/TF gaps. A malformed context is rejected before a collector starts. This is **not** a room-to-odom transform or a joined physical drive mission. Legacy saved readiness states without a scene reference remain explicitly unknown rather than being assigned one retroactively.

## Regression and limits

- Source fake/controller/API regression: 122/122 PASS. Packaged App readiness tests: 10/10 PASS. Web: 178/178 PASS and TypeScript/Vite build PASS. `git diff --check` exit 0 (existing CRLF warnings).
- No new real collection was triggered by opening the App or the installed launcher. The explicit collection button may still deploy source when separately approved; this smoke never clicked it.
- Remaining: full clean committed release and company-PC acceptance; actual same-boot odom/scan/TF original bytes, ROS LiDAR driver lifecycle, measured sensor/body/room alignment, physical stop/collision evidence, and autonomous mission/Twin comparison. `pc_demo_ready=false`, `manifest_mapped=false`, physical motion locked.

## Fresh installed-PC recheck — 2026-09-30

- Rechecked all 295 release-manifest hashes: `TWINPULSE_RELEASE_VERIFY=PASS`. All 294 non-wheel manifest files still match both the current source and the isolated installed copy (missing/changed: 0/0 on each side). The pinned wheel also matches the installed copy.
- The installed Python's `--collection-only` run initially returned `COLLECTION_REVIEW_REQUIRED` in the restricted test shell: Windows `tempfile` cleanup raised `PermissionError [WinError 5]`. Redirecting TEMP/TMP to a project-local folder still hit the same shell restriction. The failure was kept as a failure, not reclassified as a passing test.
- Re-ran the identical installed command with the approved unrestricted local shell: `COLLECTION_CONTRACTS_PASS_DEMO_LOCKED`. Group 1: 68 tests, 3 platform skips; group 2: 11 tests, 0 skips. The installed cache then read back as `MATCHED`; `robot_contact=NOT_RUN`, `demo_ready=false`.
- A normal clean build without `-AllowDirty` stopped at the intended dirty-tree gate before creating `tp-clean-gate-check-20260930`. No commit, push, clean release, company-PC execution, robot contact, source transfer, or physical test was performed. Current verified artifact remains a dirty development release, not a releasable clean build.
