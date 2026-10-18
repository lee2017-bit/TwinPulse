# Battery charging threshold and operator readiness — 2026-09-26

## User decision

User selected charging at approximately20% remaining. Interpret this as a
**voltage-derived estimate**, not calibrated measured capacity or remaining minutes.
Public ROBOTIS ROS2 firmware maps10.5V→0%,12.3V→100%:
`(V - 10.5) / 1.8 * 100`. This puts20% at10.86V,11.4V at50%, and the last
measured11.45V at approximately52.8%. Those percentages are calculated from the
public source, not a fresh measurement of the installed board's percentage register.

Source: https://github.com/ROBOTIS-GIT/OpenCR/blob/master/arduino/opencr_arduino/opencr/libraries/turtlebot3_ros2/src/turtlebot3/turtlebot3.cpp

## Independent hardware protection takes priority

Public firmware diagnosis code sets a low-battery LED below11.1V and uses an
approximately11.0V averaged-voltage state machine for warning/motor-power protection.
11.0V corresponds to approximately27.8% under the same display formula, so hardware
protection may intervene BEFORE the user's20% charging threshold. Do not promise
the robot can physically operate down to20%, or disable/alter firmware protection.
Exact installed-binary/source reproducibility and actual cutoff behavior remain
unverified. Battery damage, temperature, cell imbalance or unstable supply also
take priority over a percentage estimate. No such new condition was measured here.

Source: https://github.com/ROBOTIS-GIT/OpenCR/blob/master/arduino/opencr_arduino/opencr/libraries/turtlebot3_ros2/src/turtlebot3/turtlebot3_diagnosis.cpp

## Implementation / verified scope

Local bounded trial source in
`C:/Users/jaewo/Documents/Codex/2026-09-12/dl/guard_stop_probe` now includes
`battery_policy.hpp`: charging gate at<=20% (<=1086 centivolts), finite/range checks,
rounded centivolt comparison to avoid the earlier float-vs-double boundary error,
and clamped0–100% estimated display. The trial logs estimated percent in preflight.
This changes the optional trial client only, not the production command guard.
The firmware's independent protection is untouched; no new automatic battery alarm
monitoring service has been installed.

PC WSL GCC compilation with C++17/Wall/Wextra/Werror/pedantic and615 pure policy
checks PASS (10.85/10.86/10.87 boundary,11.4V accepted by charging policy,11.45V
estimate, nonfinite/range failures,301 centivolt values). Initial sandbox WSL
access denied; approved local execution then succeeded. No ROS/device access.
Full ROS probe rebuild/integration NOT_RUN for this revision.

**Not deployed to Pi.** Existing remote trial binary still has the historical11.4V
test threshold and its consumed one-shot marker remains in place. Never run that
old binary expecting this new policy. Before the next authorized trial, deploy
the reviewed source, rebuild/fake-test and separately establish a new one-shot
execution record. Do not erase the earlier marker or rerun automatically.

## Execution readiness correction

User reported they were not watching during the earlier brief movement because
preparation took approximately20 minutes. Therefore there is NO user visual
confirmation of that motion; only recorded telemetry/encoder evidence exists.
The assistant acknowledges it should have reconfirmed readiness just before motion.

For future physical trials: complete all lengthy preparation first; then state
fixed distance/speed/duration and request a fresh operator response confirming
they are watching and the area is clear. Execute promptly only after that response.
If delayed or preparation resumes, ask again. Earlier general approval is not a
standing authorization for unexpectedly delayed movement. Preparation should use
wall power where feasible; a physical power change remains an operator action.

This turn changes local source and records only. No robot SSH, motor/LiDAR action,
firmware update, threshold deployment, charging, shutdown or movement was performed.
The earlier instruction that charging is mandatory solely at11.4V is superseded;
physical command-expiry validation remains pending.
