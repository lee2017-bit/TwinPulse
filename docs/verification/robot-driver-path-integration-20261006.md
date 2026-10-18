# Reviewed COIN driver integration — 2026-10-06

The user's request was to connect the already built corrected driver to TwinPulse. This increment updates the existing manual/scan execution paths and deploys reviewed project sources. It does not launch the driver, rotate LiDAR, change motor torque, drive, qualify a stop, or authorize an autonomous mission.

## Implemented product paths

- `coin_driver_identity.py` is the single inert identity source for the reviewed ARM64 binary, private library and source hashes. `isolated_ros_scan.py` consumes it for manual Drive + LiDAR, qualification, localization and mission modes already using the owned adapter.
- The standalone `robot_ros_scan_trial.py` and PC `run_ros_scan_client.py` consume the same identity. The trial now uses the pinned library environment; receipts reject an old/different driver identity while still exporting its historical raw bytes. Historical scan data was not relabeled as corrected-driver evidence.
- Before launching the driver, the adapter checks binary/library presence, symlinks, exact hashes, AArch64 ELF, loader dependencies and exact private-library resolution, then existing device identity/ownership. It returns distinct missing/hash/architecture/library/port errors. Child environments exclude `LD_PRELOAD` and `LD_AUDIT`; system settings are unchanged.
- Runtime preparation performs a no-sensor artifact preflight before selecting `current`, including on cached releases. A failed dependency preflight preserves the previous selected release. Existing speed, timing, stop, lease, raw-data and profile gates remain unchanged.

## Local verification

Final focused driver/transport/same-window/manual regressions: **57 tests PASS / 3.608 seconds**. Frozen-candidate collection groups: **79 tests (3 skipped) and 11 tests PASS**; field contracts: **212 tests PASS / 23.707 seconds**, with overlapping counts. Syntax, isolated imports and unchanged-input checks passed. The valid [manifest](../../artifacts/robot-field-candidates/165250259c6b44f0a5d998b86ed7468e/manifest.json) froze **91 source members**, source ID `1cede5493f5a4ade3c46c49049dc9752a8fef3476b76f5a0cc214e16e9ade1ba`, archive SHA `ec9665d40faab1d113f666672f8a8f30f457943b2c45b4b51f22ba2c544523f1`.

The first field-contract run failed because a regression expected the previous generic identity-error text. Its [failed preflight](../../artifacts/robot-field-candidates/fc498536cdcf4280952ca4a27fb35c14/preflight.json) is retained; the test now explicitly supplies a missing binary and expects the precise error. A broad Windows invocation of Linux runtime tests also failed on Windows symlink privilege and missing `SIGHUP`; no system configuration was changed. The actual Linux target later passed that runtime group, including new pre-selection and cached dependency-failure checks. Original patch CRLF warnings remain visible.

## Actual robot deployment and independent verification

The exact frozen candidate was deployed with existing `prepare_robot.py --mode prepare --candidate ...`, **without torque flags**. Runtime source/guard/parameter validation, source SHA, compiler checks, **9/9 device-free CTest groups / 7.69 seconds**, and **615 battery-policy checks** passed. The [original operation log](../../artifacts/robot-preparation/20261006T131754Z-3bb6b2f6/operation.log) was copied to PC. `current` now resolves to the exact source ID above; the previous release was not overwritten.

An independent SSH invocation of `current/isolated_ros_scan.py --artifact-preflight` returned **`PASS_NO_SENSOR_ACCESS`**, with exact reviewed hashes:

- Binary: `candidates/coin-time-build-20261006T125707Z-30d7bdc2/build/single_coin_d4_node`; SHA `d2e06c51786963ec828993faea2a91048dcac0e826145af0d738cf847f65b9c9`.
- Library: same candidate's `build/libcoin_d4_driver_lib.so`; SHA `4c3ac61f023eb90f8bce4376dcce8cc22339e791a44a7e573f048d2980452d6b`.
- Corrected driver source SHA: `0ac6ccd380d8d146828cf28334bb17e20d58aa2c3c046aa27f6a1e83c3f30e16`.
- Boot: `ebc097db-36fb-4ccc-a09f-64fc6da30a2f`.

The target prepared-status was **`PREPARED_NEEDS_ATTENTION`**, not an integration failure. The [saved board/health report](../../artifacts/robot-preparation/20261006T131754Z-3bb6b2f6/result/report.json), observed at **2026-10-06T13:18:19Z**, shows torque enabled, wheel raw velocities `[0,0]`, zero command bytes, restored port, 11.28 V and voltage-based estimate 43.3%. We neither enabled nor disabled torque. This snapshot is not physical stop certification and is not continuous status. Reported deployment verification succeeded.

## Scope boundary and next field action

**Driver-path integration and target artifact/dependency verification are complete. Physical corrected-driver scan/lifecycle is NOT_RUN.** The passive build receipt still describes build evidence only, not sensor activation authority. Timing remains `HOST_SYNC_APPROXIMATE_NOT_HARDWARE_FIRST_RAY`; physical verification remains false. Profile SHA `3ede976616d841d42dbbdcd276a78936bc7f623afdc7723ce00fd136a64469f3`, qualified guard and earlier raw/failures are preserved. C3–C6 remain partial; whole readiness remains false. No Web/Isaac acceptance is claimed for this increment.

After reopening/restarting the existing TwinPulse App if it holds old imports, an explicitly approved field operation can use the new driver through the existing controls. Scan-only does not provide a moving odom/TF qualification. Drive + LiDAR requires the existing current-boot/current-release stop gate; an older release's stop receipt must not unlock the new release. Next field acceptance is motor-disabled initial state under approved preparation, new-release short stop qualification, fresh scan/odom/TF and driver cleanup, followed by measured sensor/footprint/timing and room registration before an autonomous goal. Those actions were not performed here.
