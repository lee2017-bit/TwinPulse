# Torque-on investigation and one-shot OFF attempt — 2026-09-27 11:35–11:40 KST

User approved checking the reason and a no-motion torque-off step, then explicitly
confirmed a flat floor with clear wheel surroundings. No movement, torque-enable,
heartbeat, base/ROS driver, LiDAR, firmware, reboot or system install was performed.

## Reason supported by source, not exact-binary provenance

Manufacturer public [OpenCR ROS2 core](https://raw.githubusercontent.com/ROBOTIS-GIT/OpenCR/master/arduino/opencr_arduino/opencr/libraries/turtlebot3_ros2/src/turtlebot3/turtlebot3.cpp)
`begin()` lines524–528 enables wheel torque after motor connectivity succeeds.
Address149 is the torque item; its write callback passes the boolean to the motor
driver. The periodic status update copies `get_torque()` into this item. This is
consistent with today's torque=true and prior reboot/FW-upload observations.
Public master is NOT proven a reproducible match to installed V230127R1/FW5.
Therefore startup enable is the supported explanation, not a definitive diagnosis
of every actual motor state or malfunction.

## Current read and attempted operation

- Before: `artifacts/robot-checks/20260927T023515Z-43e581/report.json`:
  11:35:03KST, 12.17V, voltage estimate92.8%, torque=true, speed0/0, commands0,
  encoder2320/1626, same boot, release VERIFIED, monitored processes empty.
- Separate maintenance source in `packages/twinpulse_robot_safety/`:
  `src/opencr_torque_off.cpp`, `include/twinpulse_robot_safety/torque_off.hpp`,
  `tests/torque_off_test.cpp`, `torque_off_once.py`. Not wired into automatic
  prepare/startup/check commands; existing permanent release/current unchanged.
- Fixed by-id/ttyACM0/ID200/BurgerFW5; identity, disconnected/debug/status,
  voltage, motor connection, released buttons, zero commands/speed and exact
  encoder stability before OFF. The only write API is fixed address149/value0.
  No retries/re-enable rollback. Wrapper verifies current release, takes existing
  managed lease, refuses existing serial owner, consumes exclusive one-shot marker,
  bounds child lifetime and independently READs afterward even on failure.
- Local evidence: `artifacts/torque-off-20260927-1138/`.
  Remote staging: `/home/twinpulse/.local/share/twinpulse/robot/torque-off-20260927-1138/`.
  Archive SHA256 `2e727928932694dc7f43969103ddbf8ca0fe62f3f5684bc820b5bc5927c780dd`.
  ARM64 binary SHA256 `db145277f39d8ba58bcac038f7b34b5ebe446632d1c852288ecb9c07035f190c`.
- Executed wrapper once. **ABORT BEFORE WRITE**: two preflight samples ~200ms
  apart showed left encoder2321→2320, right1626 unchanged, speed0/0 and commands0.
  There is no `TORQUE_OFF` write in `operation.log`. Child exit3, restore verified1.
  `consumed` remains and must not be removed/reused for an automatic retry.
- `independent-board.log`: supply `BF040000` =12.15V, torque01, speed0/0,
  encoder2320/1626, commands allzero; port restoration succeeds. OFF did not happen.
  A single tick difference does not distinguish physical micro-motion from feedback
  quantization/noise; it is not a newly proven actuator fault or a PASS.

## Verification and retained failures

- Existing ARM64 g++17 O2/Wall/Wextra/Werror/pedantic: helper and pure core test
  compile PASS. **87 device-free cases PASS** (identity/gates/read failures,
  all command bytes, drift, ignored/failed OFF, already-off, success).
  This does not qualify the unexecuted physical write/readback path.
- Existing Pi device-free tests run directly: runtime6, stationary fake17,
  command guard1314 checks PASS (`direct-regression.log`). No real base launched.
- Windows first regression attempt: temporary-file sandbox WinError5; approved
  retry reached symlink creation but failed WinError1314. Not a Windows PASS.
- Re-running retained Pi CTest build directory failed because generated paths
  still name the pre-rename `.staging-*` directory. Failure retained in
  `existing-regression.log`; direct current-path execution above passed. Initial
  pre-rename build/test PASS remains valid; relocation-safe CTest is a follow-up
  tooling defect, not silently fixed or a device failure.

## Outcome / next boundary

Torque remains ON with zero sampled speed and zero commands. No automatic retry,
threshold relaxation, driver startup or additional movement. The exact-stability
gate refused this attempt; resolve the one-tick observation and review the bounded
OFF procedure before a newly approved attempt. Existing settling122ms<200ms FAIL,
D2 physical adapter, actual stationary ROS lifecycle, LiDAR/TF and integrated demo
gates remain. Battery percentages remain voltage estimates, not capacity metering.
