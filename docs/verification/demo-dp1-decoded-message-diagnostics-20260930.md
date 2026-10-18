# DP1 decoded-message diagnostics — 2026-09-30

Scope: robot OFF, no SSH, serial, sensor, motor, deployment or physical test. Existing local ROS 2 decoder packages are absent; actual CDR replay was not run.

The saved-bundle inspector's optional decoded-message path now emits bounded `message_diagnostics` by raw sequence and topic. It checks the project-facing structural fields of Odometry, LaserScan and TF/TFStatic separately: timestamp and frame shape, odom position/quaternion, scan angular/range shape, and TF edge/translation/rotation. It counts all decoded messages, including unreviewed topics, but stores at most 12 problem examples with only sequence/topic/reason. Nonfinite or out-of-range scan readings are diagnosed without rewriting the original ranges. Static TF zero timestamps are allowed as a shape diagnostic. `SHAPE_OK` explicitly means neither verified robot pose nor room alignment.

The diagnostic is deliberately separate from raw capture integrity: a decoded but rejected message remains in the original raw bundle. `COMPLETE` still means a complete copied-byte bundle under the existing contract, not that observations are valid or motion is safe. The existing CLI decoder-unavailable/failed-decode result remains incomplete when `--decode-ros` is requested.

Offline fixtures: focused decoded-message tests 3/3 PASS, plus raw export/preparation/recovery/recording, passive ROS contract and DP0 audit tests, 48/48 PASS total in the existing `.venv`. The default sandboxed run could not write nested temporary fixtures; the same tests passed under explicitly approved local filesystem access. No new package was installed. Read-only probe reported `ROS_DECODER_AVAILABLE=False`; no real raw bundle was found in the known manual-control and robot-preparation artifact directories. This does not prove that no bundle exists elsewhere.

Remaining: actual current robot CDR capture/export and decode; ROS time, publisher count, QoS and source freshness; full odom/scan/TF validation, body/sensor geometry and room↔odom calibration; throughput and field safety. DP1 acceptance, PC readiness and live mission remain blocked.
