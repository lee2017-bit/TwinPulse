# Single-entry robot field suite — offline verification, 2026-10-01 KST

## Why

The earlier `run_robot_readiness.py` only sequenced source/idle and stationary collection. The isolated ROS scan and fixed moving-stop qualification were separate ad-hoc invocations. A failure could end one path without reporting which independent checks remained safe. This was a preparation defect, not an operator task.

## Implemented boundary

- `scripts/run_robot_field_suite.py` is a **single PC entry point**. Its default mode is robot-OFF: local collection contracts plus explicitly named saved raw bundles; no SSH, deployment, sensor start or motor command. A field run needs current operator/floor confirmation. Torque OFF and the one fixed qualification plus one isolated ROS scan each require explicit scope flags. No autonomous mission or automatic retry is available.
- The field plan calls existing read-only health, reviewed source preparation/stationary collection, existing fixed 0.6-second qualification, and `scripts/run_ros_scan_client.py` for a 12-second isolated ROS scan. It records each result separately in one incrementally saved report. A failed prerequisite skips dependent physical work while saved-file analysis, safe health checks and cleanup evidence continue where possible. A remote-unknown or unconfirmed qualification cleanup blocks subsequent sensor startup. Voltage at/below the existing 11.1 V guard blocks preparation; a 11.4 V *field-session margin*, not a manufacturer capacity claim, blocks the fixed movement. A battery/source-age failure blocks the remaining powered trial.
- Scan transport copies the script under a content-addressed name, checks its remote SHA-256 before launch, accepts only a fixed reports-directory ID, downloads an allowlist of originals, validates ROS raw frame sequence/footer/hash and same boot/release, and retains transfer errors. It does not install the driver or promote serial-data quiet to physical rotor stop.
- Every report keeps `demo_ready=false` and names the remaining gates: concurrent moving scan/odom/TF capture, physical LiDAR stop, sensor-to-base and room-to-odom calibration, and live collision guard/autonomous mission. The field suite is not the DP3 App button or DP6/DP7 acceptance.

## Verification actually run

- New no-device branch tests: 17/17 PASS. Cases include offline default/no SSH, failed PC preflight/no SSH, invalid saved raw, malformed board response/no retry, torque ON with explicitly scoped OFF, qualification failure with confirmed cleanup continuing safe scan, battery failure stopping powered scan, uncertain cleanup/remote state blocking scan, boot/release mismatch, remote script hash/path rejection, and a complete fake transport using the saved actual 105-scan raw bundle.
- Related local regression: 114/114 PASS for readiness, connection, physical controller and the new tests. No hardware contact.
- One final saved-data offline invocation of the new entry point: local collection contracts `PASS`; stored 105-message ROS scan raw and moving-qualification raw footer/sequence verified; live stages all `SKIPPED` in robot-OFF mode. Report: `artifacts/robot-field-suite/20260930T154427Z-e8218655/report.json`. It is an original-byte check, not a physical PASS.
- Python syntax check of the two new scripts passed. The initial sandbox-only unit test attempt could not create a temporary output folder; the same tests passed with permitted local execution. No code or hardware failure was inferred from that sandbox error.

## Remaining before saying “one command finishes demo preparation”

This entry point consolidates **currently executable** checks but does not invent missing measurements. In particular its scan and moving-odom trials are different time windows, so the combined scan/odom/TF evidence needed for moving mapping is still missing. The field path itself has not been run on hardware, and the isolated candidate driver has not been generally installed. Its first live use requires a new supervised field scope and should be treated as a limited acquisition trial, not automatic demo authorization. If the field path exposes an issue, the report names the stage and preserves originals; a code correction still has to be verified offline before any new physical run.
