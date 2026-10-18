# Combined robot collection path — robot-OFF verification, 2026-10-01 KST

## What changed

The existing single PC entry point, `scripts/run_robot_field_suite.py`, now routes its fixed, one-shot qualification through a robot-owned `qualify_scan` worker. That worker starts the pinned isolated COIN D4 ROS driver for `/scan`, samples `/scan`, odom and TF in the **same owned session**, and records exact CDR bytes and movement-command monotonic times. The scan subscription uses the observed absolute `/scan` topic. Sensor freshness/publisher loss fails the fixed trial closed; no adaptive movement or automatic retry was added. Driver cleanup is ordered before final base/board cleanup: terminate owned driver, independent serial STOP, receive-quiet/port restoration check, then final board read. An uncertain cleanup cannot be called a stop PASS.

The original-byte export includes the driver's log. `scripts/inspect_same_window_ros.py` checks raw/footer/report count binding and command-window overlap for scan, odom and dynamic TF, and reports static TF separately. Missing static TF or other required evidence stays INCOMPLETE. Even a complete raw window is only `COMMAND_WINDOW_RAW_CAPTURED_UNALIGNED`: it is not physical floor displacement, calibrated sensor-to-base/room transform, or a verified rotor stop.

The field suite performs the expanded local no-device checks **before** any field SSH. It keeps independent safe stages and bounded transport errors in one report. When combined qualification was attempted, it does not start a redundant second isolated scan. If the motion voltage margin blocks the combined attempt, the independent sensor-only scan can still be considered under its own guards. Prior one-shot/boot and stop-failure rules are unchanged.

## Verification actually performed

- Existing local `.venv` no-device focused regression: **128/128 PASS**. Coverage includes same-window analysis, combined-worker cleanup ordering, field-suite branching, and previous controller paths. Bundle presence for the new worker/driver files passed. This is local mock/contract verification, not ARM64/runtime validation.
- Robot-OFF single-entry run: `artifacts/robot-field-suite/20260930T205118Z-315ed689/report.json`. `offline_contracts=PASS` (70 tests with 3 platform skips + 11 lifecycle/record tests, plus focused128/128); `saved_evidence=VERIFIED`; **all live stages SKIPPED** with `ROBOT_OFF_OFFLINE_MODE`; `demo_ready=false` and `autonomous_motion_authorized=false`.
- Saved **real** raw files were reread without contacting the robot: prior ROS scan raw 105 frames (scan105, odom0, TF0), prior moving-qualification raw 152 frames (odom27, scan0, dynamic TF27, static TF0). Exact bytes/footer verify, but these are separate time windows and do not prove concurrent collection. Previous moving stop qualification remained **FAILED** after voltage 11.099999 V crossed its >11.1 V guard; no historical result was rewritten.
- No SSH, serial, LiDAR start, motor command, deployment, or physical test was run in this increment. The local report and prior raw files are preserved.

## Remaining acceptance boundary

The next supervised physical session must first satisfy current board/voltage/boot/release and fixed-scope safety guards, then exercise this newly wired single-entry path once. A resulting report must be inspected for same-window scan/odom/TF originals, driver exit/STOP/quiet/port restore and final board state. Absence of `/tf_static` or a measured sensor-to-base transform remains a separate calibration blocker; a photo cannot supply it. Operator-visible physical rotor stop, room-to-odom registration, live collision guard and autonomous mission acceptance are also outstanding. Charging or one successful raw capture alone does not unlock the demo.
