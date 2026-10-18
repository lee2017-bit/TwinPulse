# Robot field candidate preparation

October 6, 2026 / Baseline 1.0.311. The existing single field entry now consumes an immutable, locally checked source archive. Preparation is complete for a **bounded legacy-driver collection trial**, not corrected-driver deployment or an autonomous demo. Robot contact, deployment and physical tests in this increment: zero.

## Prepared source and execution path

Use the existing `scripts/run_robot_field_suite.py --prepare-field-candidate` while the robot is OFF. It checks PC SSH/SCP and existing identity/host-record presence without reading credential contents, runs collection/field regressions, compiles Python source and imports the actual bundled modules outside the checkout without ROS/serial startup. The default locked profile is unchanged.

Final [report](../../artifacts/robot-field-candidates/2d6196d9ec2145f782a55f518e244a4e/report.json) and [manifest](../../artifacts/robot-field-candidates/2d6196d9ec2145f782a55f518e244a4e/manifest.json):

- Source identity: `170a6466ee2f767ab54bd0e6074101e1cb0dcd185bf9ae068b644ca9587f76fe`, 89 source members.
- Robot archive SHA256: `40f25638e88ccb19e0594ad48557fe95e725cd9c771acb8e78f7a770ffdb061a`.
- Corrected-driver source archive SHA256: `3a2ff56fdb27ab15f8c77b6433167afd8094b027fc1355cf9d40389918c29344`, 35 members. This separate archive is **not automatically transferred or activated** by the field trial.
- PC presence checks all true. Target architecture is ARM64 / ROS Humble; current remote prerequisites remain unverified.

The report supplies the exact later field command with `--field-run --candidate <manifest> --operator-watching --clear-floor --allow-torque-off --allow-fixed-motion-and-scan`. Those flags require a new on-site approval; preparing or opening the report does not grant it. The same manifest flows through field suite → readiness → preparation. The client transfers the exact checked archive, and remote SHA256 is checked before extraction. A successful preparation/stationary result with a different release is rejected. A failed target preparation retains its original reason instead of being mislabeled as release mismatch.

Before SSH, candidate validation checks source/archive/member bytes, runner and collection fingerprints, preserved sensor-source bytes and PC-test age. Contract receipts expire after the existing 12-hour cache period; refresh the candidate on the PC while the robot is OFF if expired or source changed. Exact target/boot/battery/freshness/stop checks still run in the robot session. No stale stop qualification is reused for a new boot or release.

The existing field sequence remains board/battery → source prepare and stationary raw → fresh same-boot/release → one fixed stop trial with scan/odom/TF → safe independent diagnostics → cleanup/export. Earlier motion failures still permit independent observations only when existing safety/cleanup gates allow them. No autonomous go-to or loop is added to this collection scope.

## Corrected LiDAR source preparation defect

The preserved October 4 candidate reported patch application but lacked `include/coin_d4_driver/scan_clock_contract.hpp`; its `getTime()` still contained the old realtime compilation branch. `git -C <candidate> rev-parse --show-toplevel` resolved to the ancestor TwinPulse checkout. Thus the prior successful apply command was not proof that the nested candidate files changed.

`prepare_coin_time_candidate.py` now prevents ancestor discovery with a Git ceiling, rejects a discovered repository, verifies every patch target actually changed, and runs an immediate reverse-apply check. It reads the pinned local vendor Git object without resetting/editing that clone or creating a repository. A fresh [candidate receipt](../../artifacts/coin-d4-ad1-time-candidate-20261006-r1/twinpulse-candidate.json) binds all prepared source bytes. The header and monotonic implementation are present; all four existing reviewed patches applied and reversed-check successfully. Original candidate and patch bytes remain preserved. CRLF trailing-whitespace warnings remain visible; patch contents were not silently rewritten.

The field candidate separately hashes this source snapshot, checks included bytes against its post-application receipt and preserves the build requirements/command arrays. The source preparation helper is also bound by runner fingerprint. Source preparation is **not a C++ compilation or ARM64 ROS build PASS**.

## Validation

- Focused integration regressions: **68 tests PASS**, 3.678 seconds, including actual nested Git patch application, inert real-source import, frozen propagation, changed/expired/duplicate/archive rejection, no-contact failures and original target-error preservation.
- Final preparation: collection groups **79 tests (3 skipped) + 11 tests**, plus **190 focused field tests / 23.709 seconds**, PASS. Counts overlap with the focused integration run and are not a count of unique tests. [Final preflight receipt](../../artifacts/robot-field-candidates/2d6196d9ec2145f782a55f518e244a4e/preflight.json).
- Final `checked()` reinspection of source, both archives, sensor receipt, runners and fingerprints: PASS. `git diff --check` for the changed existing scripts: PASS.
- Locked profile hash remains `3ede976616d841d42dbbdcd276a78936bc7f623afdc7723ce00fd136a64469f3`. Motion/scan freshness, stop policy, autonomous speeds and physical admission are unchanged.

The first sandbox test attempt failed temporary-folder ACL access; scoped no-device test execution then passed. An intermediate 67-test run failed because the missing real LiDAR header was detected, not because a synthetic fixture was accepted. The older candidate without the source-snapshot schema and intervening source fingerprints is not the final field manifest. These failures are not relabeled as PASS.

No new Web/Isaac runtime claim is made: this increment changes field/source preparation, not the previously verified UI. C3/C4/C5/C6 and whole-demo readiness remain partial/false; the previous UI/package/resource limitations remain.

## Target and physical prerequisites

1. **Corrected ARM64 driver compilation is still blocked on this PC.** Read-only PATH inventory exposes no native C++/CMake compiler route; existing WSL service denial was not bypassed or retried. The prepared source has device-free clock-test and ROS build command arrays, but no target binary was built. The earlier robot inspection found its existing ROS/compiler tools; availability and exact binary/library hashes must be checked after a separately approved connection. No new installation is part of this preparation.
2. The runtime still pins the earlier owned-driver binary. Switching to a successfully built corrected binary requires reviewed hashes and changed-release qualification; source preparation alone does not switch that path.
3. Timing remains `HOST_SYNC_APPROXIMATE_NOT_HARDWARE_FIRST_RAY`, not verified acquisition. Actual mounted sensor extrinsics and chassis footprint must have physical evidence. Saved TF/nominal Burger data/photo estimates alone do not supply that claim.
4. `navigation-calibration.json`, `adaptive-qualification.json`, `adaptive-sensor-evidence.json` and reviewed room/source registration remain absent. They are intentionally not synthesized. Review real target/sensor evidence, bind its bytes and only then opt into the autonomous profile. Same-boot stop and new current localization are still required.

The next useful robot session starts with a **no-motion target/build inspection**, not a promise of immediate autonomous driving. When target build/review is available, collect and qualify the relevant real source in one bounded session, then attempt fit/short goal/Stop only if admission genuinely passes. Unrelated C6 packaging and long-duration UI checks need not delay that target inspection.
