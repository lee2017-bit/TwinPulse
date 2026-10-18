# Saved manual driving and scan review

The saved October 3 sessions contain timed scans, wheel odometry and dynamic TF. They are reusable observations, not a prescribed future route or a calibrated room map. This update reviews the originals offline, fixes a topic lookup error and separates manual control from blocking SSH telemetry writes. No robot connection, deployment or movement was performed.

## Original evidence

The source actually used on the robot was `582714f7984692f4d7bc769352d3d27e57de2f46dace3752fd3869ad46be0bd2`. Its earlier NOT_DEPLOYED note describes the preceding development turn, not the current saved sessions.

Session `4493be87ef7643ababb661b4a12f0180` lasted 262.67 seconds including preparation and cleanup. It contains 2,318 raw scan messages over 231.373 seconds, 4,678 odom and 4,678 dynamic TF messages. The maximum scan receipt gap is 109.410 ms. Exact raw/footer and export bindings pass offline reinspection, and the PC mirror equals the full robot journal. Robot acceptance of close sequence 2426 precedes idle confirmation; no later wheel command was published.

In the latest session `b6cf346718da44b99e7bffe6f7919bbf`, the final robot-accepted control input is `finish_stop` sequence 1323, followed by its idle confirmation and `COMMAND_SEGMENT_STOPPED`. PC close sequence 1324 arrived after the FINISHED event and was not written to the robot pipe. There are zero published wheel commands after the accepted terminal stop. This distinguishes the final PC request from the final executed robot input.

Failed session `1a7f033af112437699ca67aef3438ecb` retains `INPUT_DEADLINE_EXPIRED`. PC inputs continued around 100 ms apart, while robot observation delivery showed an interval excess of 1.431 seconds; raw odom and sensor receipt gaps also reached about 1.48 seconds. The observer event was timestamped before a synchronous journal flush and stdout mirror, and arrived at the PC much later. This identifies a blocking control path that can cause failure, but the old logs cannot isolate Wi-Fi, SSH backpressure, local journal I/O or scheduling as the unique cause. Interval excess is not measured one-way network latency.

Offline reports are `artifacts/saved-lap-4493-review-20261003.json`, `artifacts/saved-lap-b6cf-review-20261003.json` and `artifacts/saved-lap-failure-review-20261003.json`. The originals were not changed. `scripts/review_manual_scan_session.py` accepts any copied manual session and verifies original hashes, clocks, sequence binding and the PC mirror before reviewing the timeline. It does not fully deserialize ROS CDR, interpolate odom or produce a mapped room.

## Corrections and protections

`RosLink` subscribed to absolute `/scan`, but passive navigation called `count_publishers('scan')` in `/tp_guard_stationary`. The count now uses the subscription's absolute topic. The earlier user-facing description of `ENDPOINT_COUNT` as a scan-format error was incorrect: it is a publisher-count check. [ROS node source](https://github.com/ros2/rclpy/blob/humble/rclpy/rclpy/node.py) documents relative-topic namespace expansion. Strict range, timing, missing-ray and calibration checks remain unchanged; correcting the address does not guarantee the real driver satisfies those subsequent checks.

Manual protocol messages now enter a bounded FIFO sender rather than blocking the wheel loop on stdout. Messages retain their original timestamps and challenges; there is no restamping, silent dropping or automatic resume. Delivery stalls at 200 ms, queue/byte overflow and write failures have distinct errors. The loop still requires fresh movement input within 250 ms and retains the 400 ms C++ output guard, idle presence, ownership, battery, scan and cleanup checks. The local exact journal remains authoritative; journal flush duration is measured separately and a 200 ms stall is an explicit failure. The report's protocol counters are a pre-FINISHED enqueue snapshot, not proof of final wire delivery. A peer that stops reading can still cause protective termination; it cannot block local cleanup.

The PC keeps advertised session policy when the operation finishes. The UI distinguishes stopping and saving results from preparation and suppresses obsolete expiry warnings while cleanup/export is running. Recording checks accept the existing 64 MiB manual journal budget without changing other evidence limits.

## Variable start and route requirements

The room model is persistent; localization is session-local. Every start and unobserved manual reposition requires a new sensor-to-room position estimate. Never assign an old final odom pose to the next physical start. Wheel odometry alone cannot detect carrying the robot without turning its wheels. Ambiguous or inconsistent scan matching must invalidate alignment rather than guess a start pose.

Command publications, encoders, odom and scans can support a response model with uncertainty. They do not prove actual floor displacement or imply that replaying identical inputs at another start reproduces the route. Future navigation must use current localization, current scans and the selected goal, not hardcoded turns from this lap. [LaserScan definition](https://github.com/ros2/common_interfaces/blob/humble/sensor_msgs/msg/LaserScan.msg) distinguishes first-ray acquisition time and per-ray time increments; these timing fields remain in the exact saved messages, not merely the final display image.

Remaining mapping gates are full raw-message decoding and time pairing, sensor-to-base extrinsics, per-session odom-to-room localization and scan-registration acceptance. `/tf_static` was not received. No measured 3D geometry, floor pose, calibrated room alignment, collision avoidance or autonomous demo acceptance is claimed. Requested manual 0.08 m/s remains unapplied because the pinned imported guard caps 0.05; rotation remains 0.30 rad/s. A reviewed executable update and stopping qualification are still required for that speed.

## Verification and application

Focused Python regression passes 148 tests and 115 subtests; report `artifacts/saved-lap-control-review-20261003-tests-r4.xml`. It includes blocked/failing protocol writers, FIFO identity, explicit budgets, root-topic lookup, existing stop/ownership/controller/raw export boundaries and offline terminal correlation. Web regression passes 199 tests, including stopping/export feedback; TypeScript and Vite build pass. The initial restricted-shell run failed on Windows temporary-directory access and is retained; the approved local rerun did not relax code requirements.

New source is `f6e0087568294946a6f4b2ad53dbea46b4560da99c092ca22788bfa0cddd4696`, NOT_DEPLOYED. Actual interruption repair and corrected live observations are NOT_RUN. Applying this robot-source change requires the explicit reviewed prepare and current-release qualification flow; an old receipt cannot authorize a new release. No robot reboot is inherently required, and no automatic deployment was added.
