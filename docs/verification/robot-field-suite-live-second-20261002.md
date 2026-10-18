# Second supervised combined field attempt — 2026-10-02 KST

User confirmed the prior rotor stopped, direct observation and clear floor, then authorized one new fixed trial. The field suite report is `artifacts/robot-field-suite/20261002T142841Z-52dd91ee/report.json`. PC contracts, read-only initial/pre-motion/final board checks, source/idle and stationary collection passed. This was **one** newly authorized physical attempt, with no autonomous mission.

## Original result, not a PASS

The pinned isolated ROS driver started and exited 0 on owned SIGINT. `artifacts/manual-control/a2bd64c4bf0b43718372dd88e9380e39/robot-evidence/ros-messages.raw` has 124587 bytes: scan6, odom67, `/tf`67 and `/tf_static`0, plus command/guard records. The robot report is `FAILED` with `INPUT_DEADLINE_EXPIRED`; `moving_command_ns=[]` and `MOTION_COMMAND_WINDOW_MISSING_OR_INVALID`. The robot accepted the first `qualify` input; the PC journal shows later `watch` packets written to the pipe, but the robot session has **no accepted watch**. This matches the 250ms active input lease expiring while the driver warms up. No fixed wheel command or measured movement can be claimed.

Owned cleanup recorded driver exit0, independent sensor STOP complete, one-second data quiet, port restoration and final board observation. The user confirmed the physical rotor stopped, with no unexpected wheel movement/collision. Do not generalize that observation to future automatic rotor-stop verification.

## Offline correction and boundary

The robot now emits a distinct `PREPARING` state before sensor startup. During that wheels-disabled interval the initial `qualify` input lease and old challenges are invalidated, while PC `watch` updates its local watchdog without forwarding stale packets. After the driver and passive scan/odom are ready, a **new accepted watch challenge** is required before consuming the one-shot movement marker or enabling torque. The original 250ms moving-input limit and stop criteria were not widened. Tests cover no-watch rejection, fresh-watch path and PC PREPARING heartbeat. Robot-OFF focused106/106 and full single-entry preflight134/134 passed; the saved physical original bytes were revalidated by `artifacts/robot-field-suite/20261002T143935Z-96f227f7/report.json`.

**The corrected path has not yet run on hardware.** Same-window *moving* scan/odom/TF, a passing stop qualification, static TF/sensor-to-base and room-to-odom calibration, live collision avoidance and autonomous demo remain unverified/locked. Another physical trial requires fresh direct-observation, rotor-stop and clear-floor confirmation plus a new one-time scope approval.
