# Short live-window preparation correction — 2026-09-30

The operator provided a short supervised robot window. It was my responsibility to have the capture path ready before using that window. The 2026-09-30 session established a qualified bounded stop, supervised forward/stop, direction commands with encoder deltas, an eight-second raw LiDAR capture with physical rotor-stop confirmation, and a 316-sample disarmed final observation. It did **not** establish odometry pose, TF alignment, ROS LaserScan, chassis stopping distance, collision avoidance, or the physical TwinPulse demo. The separate `ros2 topic echo` attempt failed to capture Odometry; the original manual-session logger reduced the fault to `INVALID_MESSAGE`. This was a preparation gap, not an operator failure or evidence that another repeated drive trial is inherently required.

## Implemented offline now

- The existing fixed 20-second disarmed stationary observer subscribes passively to its own namespaced `odom` and `scan`, and absolute `/tf` when the message type is available. It does not start a LiDAR driver or publish/call any ROS command. Missing optional diagnostic message types do not alter the pre-existing stationary safety verdict.
- The resulting `telemetry.json` adds `passive_ros`: bounded counts, accepted/rejected reason counts, first three and latest odom/scan metadata, one example per fault type, and up to eight distinct `/tf` frame pairs with stamps/transforms. Nonfinite numeric values and non-allowlisted frame strings are sanitized for strict JSON; scan ranges are never dumped. Accepted odom remains explicitly unaligned; received TF remains unvalidated. The 20-second safety check, torque/OFF criteria, and independent final idle read are unchanged.
- The deterministic reviewed release bundle already includes `stationary_observer.py` and the common `ros_observations.py`; a new bundle membership assertion protects this. Source changes are **not deployed** to the powered-off robot, and the old release will not magically produce the new fields.

## Offline verification and limitations

- Final same-source `stationary_test` + robot preparation + core observations + physical controller/session history: **93 tests, 90 pass / 3 Linux-only skips**. Fake ROS messages cover a rejected quaternion, later faults after initially valid samples, bounded TF, sanitization, strict JSON, and no publisher/client calls. The offline preparation/bundle suite also passes standalone: **5/5**.
- The broader Windows runtime/preparation run was **not** a pass. It exposed a real offline packaging test issue: `bundle()` used the patched output `ROOT` for common source files. The source lookup now stays relative to `PACKAGE`, while output can be isolated; offline-mode and archive tests pass. Two remaining Linux-runtime cases fail on Windows because of Unix symlink privilege and missing `signal.SIGHUP`; they are not reported as product acceptance or silently skipped. The subprocess test now prints stderr when it fails.
- There is no offline substitute for the missing 2026-09-30 raw Odometry. The newly added fields can only diagnose a **future** observed message after an explicitly approved release deployment and passive stationary session. ROS `scan` remains `NOT_RECEIVED` if its separate driver is off; no raw LiDAR packet is promoted to a LaserScan or collision-clearance claim.

## Next physical window, only if separately authorized

1. Before powering on, finish offline fake/manifest verification and prepare the exact release/check instructions. No further motion is needed to investigate the current odom error.
2. After operator power-on and approval, verify boot/release and disarmed state, deploy the reviewed source if needed, then run **one** bounded stationary check. Read the saved `passive_ros` receipt and independent final OFF result. If `odom` is rejected, use its reason and sanitized example to fix the producer/contract offline. If no odom/TF is received, record that absence rather than driving to create data.
3. Only after odom/TF and a separately started, time-bounded ROS scan path have real evidence should room alignment and local obstacle logic be examined. Require fresh room↔robot measurements and an explicit separate movement scope before any autonomous trial. The existing stop qualification does not grant that authority.

This is a repair to **test preparation**, not completion of the autonomous demo or a request for the operator to turn the robot back on now.
