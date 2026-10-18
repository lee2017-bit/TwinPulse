# Guarded command-expiry physical test — 2026-09-26

## Authorization and bounds

User approved the proposed short real-motion automatic-stop test and requested
remaining battery information. Current operator-reported power is battery.
Operator was told to clear the robot surroundings and keep its power switch accessible.
The scope is one straight-line test, not turns, navigation, LiDAR or repeated trials.

Fixed test: +0.03m/s, zero angular velocity, publish fresh stamped messages for
600ms at approximately20Hz, then keep the publisher alive but send no messages.
The existing staged guard should latch `command_timeout` after its400ms lifetime.
No explicit zero is sent during the timeout observation, to distinguish the guard
from tester cleanup. After observation, explicit stop and motor-off are required.
700ms after the last send without timeout is a test abort, not an allowed stop bound.
The test also checks sensor freshness, button release, battery>=11.4V, bounded
encoder travel/asymmetry and stable encoder feedback after stopping.
These are conservative experimental bounds, not a safety certification.

## Preserved production and test paths

The production guard remains unchanged from the previous no-motion verification.
Executable: `/home/twinpulse/guard-validation.RIUO8r/base-build/turtlebot3_ros`.
Original Pi workspace/install/default launch and firmware remain untouched.

Reviewed bounded C++ test source is at
`C:/Users/jaewo/Documents/Codex/2026-09-12/dl/guard_stop_probe/probe.cpp`, with CMake
in the same directory; Pi copy is `guard-validation.RIUO8r/guard_stop_probe` and
build is `guard-validation.RIUO8r/probe-build`. No generated Python control script.
Final source SHA256: `603709214667d842c67a39c7d80dc25510dc691a90121f7d3b481d23a02e8629`.
Real run requires `--run-once`; `--check` performs no service writes or movement.
An atomic marker `stop-probe-run-consumed` in the staging root prevents rerunning
the physical trial automatically. Signal/error handling attempts stop and motor-off.
The already-tested guard and lower-level heartbeat fallback are independent of
this finite input source, but all failure combinations remain unqualified.

## Initial battery / state

At23:24:23 KST the independent read-only helper reported battery11.56V,
wheel feedback0/0, encoder930/4648, torque0 and all command bytes0.
An initial SensorState lookup in the overlay failed because the message package
is installed under `/opt/ros/humble`; the correct definition was then read.
No device operation failed in that lookup.

Pack voltage is measured, but capacity percentage and remaining minutes are NOT
established. Manufacturer nominal battery specification is11.1V/1800mAh:
[ROBOTIS features](https://emanual.robotis.com/docs/en/platform/turtlebot3/features/).
This nominal value alone is not a voltage-to-state-of-charge calibration.
Existing ROS percentage output is not used as a validated charge estimate.

## Test preparation observations

First fake-SDK trial detected a test-client race: successful arm-service response
can precede the next20ms status publication. The trial aborted before any nonzero
fake command, and explicit stop/motor-off/readback all succeeded. The client now
waits at most100ms for armed status before issuing motion. Production guard unchanged.
This preparation run used fake hardware only, localhost domain87, not the robot.

The revised fake trial passed: timeout observed416ms after the last send,
stable simulated encoders, stop/off acknowledgements and off readback. The separate
10V fake-battery case was rejected before any enable. These are fake results only.

First actual `--check` reported `encoders not stationary` and issued no service
writes or velocity messages. Two independent ROS samples afterward showed
torque=false, encoders930/4648 unchanged, battery11.49V. The initial hypothesis was
that queued discovery messages could complete the count without a200ms wall-clock
observation interval. Added250ms explicit observation before checking unchanged
encoder age. The90s bounded base process expired normally
via its configured SIGINT before an explicit cleanup signal reached the old PID.
No physical run marker was consumed and no motion was attempted in this precheck.

The additional interval did not resolve the second preflight: `--run-once` at
23:37:20 again aborted BEFORE the physical-run marker and ANY enable/arm/write.
A6s ROS subscription captured79 samples: left encoder930 in all, right4648 in74
and4649 in5; torque=false in all, voltage11.45–11.47V. Observed one-tick idle
quantization/jitter, not established macroscopic movement, explains the rejection.
Two isolated samples had missed it.

The test-client stationary check now uses a fixed two-tick anchor band (nominal
~0.10mm wheel travel with4096ticks/rev and radius0.033m). Crossing that band resets
the200ms stable interval; it is NOT a per-sample drift allowance. The pre-arm check
uses the same band. The fake sensor now injects alternating one-tick idle jitter.
Production guard, timeout, battery threshold and travel bounds are unchanged.
Final independent zero-velocity/torque readback is still required. Both preliminary
base runs auto-ended by their90s timeout; subsequent signals found no old process.

## Final fake regression

Final source built with GCC11.4, C++17, Debug, Wall/Wextra/Werror/pedantic.
Normal fake run including one-tick idle jitter PASS: timeout observed416ms after
last input, stable encoder band, stop/off acknowledgements and off readback.
The10V fake case PASS: rejected before any motor-enable request. No fake SDK
contains a serial implementation. Real-SDK driver was not modified or rebuilt.

## Actual one-shot execution: interrupted by battery gate

At23:41:20 KST independent preflight reported11.43V, torque0/velocity0/commands0,
encoders930/4648. Final base launch was bounded to60s, domain86/localhost-only.
At **23:42:13 KST**, the final test invocation passed preflight at11.43V and
consumed the atomic run marker once. It successfully enabled motors, armed the
guard, and sent12 fresh messages at+0.03m/s over approximately0.6s.

```text
MOVE fixed_v=0.03 fixed_w=0 publish_window_ms=600 no_repeat
INPUT_SILENT t=568 sent=12
SENSOR t=660 left=1218 right=4949 torque=1 V=11.4
ABORT battery below conservative 11.4V test threshold or invalid
STATUS explicit_stop
CLEANUP stop_ack=1 torque_off_ack=1 stable_off_readback=1
RESULT 1 run
```

The sensor's float value displayed as11.40V hit the test comparator `<11.4`:
binary float representation at that boundary is slightly below double11.4.
Do not describe this as a calibrated cell-undervoltage alarm or proof of an empty
battery. It is a conservative TEST threshold with a numeric-boundary limitation.
No voltage threshold was lowered and no second movement was attempted.

The battery gate aborted approximately92ms after the last input, BEFORE the
400ms command-expiry timeout. Thus **physical command-timeout stopping is NOT
verified by this run**. Explicit test-client stop and torque-off operated instead.
Encoder values settled near1261/4994 (one-tick jitter remains); nominal wheel
travel was approximately1.7cm. No independent floor-distance measurement or
operator visual confirmation has yet been collected. This is a limited forward
motion / abort-cleanup observation, not full driving or safety acceptance.

The driver ended through its configured60s SIGINT timeout (wrapper exit1);
subsequent PID cleanup found it had already exited. No LiDAR, turn, firmware,
default launch replacement, OS shutdown or charging action was performed.

## Independent final readback

At **23:43:24 KST**, no turtlebot3_ros process or ttyACM0 owner was found.
The independent PING/READ helper returned comm0/error0 throughout:

```text
identity: 00500100000005C800
supply: 79040000 (11.45V)
wheel feedback: 0000000000000000EE04000082130000
torque: 00
commands: 000000000000000000000000000000000000000000000000
termios/modem restoration: success
```

Wheel velocities0/0, final encoders1262/4994 (delta332/346), torque disabled,
commands all zero. Nominal radius0.033m/4096ticks gives1.68/1.75cm wheel travel;
not a calibrated ground-displacement measurement. Supply recovered to11.45V
after the short load; percent remaining or minutes remaining are unknown.

Remote artifacts under `/home/twinpulse/guard-validation.RIUO8r/`:
`expiry-motion-base-executed.log`, `expiry-motion-trial-executed.log`,
`expiry-preflight-sensor-stream.log`, `stop-probe-run-consumed`.
The last two sensor/trial logs are also preserved beside the local C++ test source.

**Outcome: ONE_SHOT_ABORT_CLEANUP_CONFIRMED / PHYSICAL_COMMAND_EXPIRY_PENDING.**
Next requires battery charging and fresh operator approval/readiness before a
new bounded trial. Do not clear the one-shot marker or automatically retry. The
existing staged driver remains unchanged; old default launch remains unguarded.
