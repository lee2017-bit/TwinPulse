# Guarded one-shot trial — 2026-09-27 00:11 KST

## Scope and authorization

After preparation was complete, user explicitly said they were watching and to
start. One fixed straight trial only: +0.03m/s stamped inputs for600ms, angular0,
then no further input to observe400ms expiry. No repeat, turn or LiDAR.
Artifacts are exactly those in [preparation](robot-policy20-preparation-20260927.md).
No source, firmware, parameters or stop criteria modified in this turn.

## Preflight and execution

Independent read before starting:11.27V (voltage-estimated42.8%), velocities0/0,
torque0, commands0, encoders1261/4994. No existing base or serial-port owner.
Confirmed actual base main takes `-i` and required namespace parameter.
Initial source lookup used nonexistent turtlebot3_ros.cpp; corrected to node_main.cpp
before launch. No movement during lookup.

Base launched with domain86/localhost-only, `/tp_guard_stationary` namespace,
vendor Humble burger.yaml, `namespace:=/tp_guard_stationary`, stable OpenCR by-id
port.45s SIGINT timeout with3s kill fallback. Gyro initialization took5s.
Actual new trial `policy20-prep.zr1ee6/build/stop_probe --run-once` used20s timeout.

At00:11:48.623501604 KST the new atomic marker was consumed once, after successful
preflight and before motor enable. Old marker remains preserved.

Key actual output (not fake):

```text
PREFLIGHT V=11.27 estimated_percent=42.7778 left=1261 right=4994
MOVE fixed_v=0.03 fixed_w=0 publish_window_ms=600 no_repeat
INPUT_SILENT t=562 sent=12
SENSOR t=970 left=1729 right=5457 torque=1 V=11.25
STATUS command_timeout
TIMEOUT_OBSERVED after_last_send_ms=421
SENSOR t=1011 left=1755 right=5480 torque=1 V=11.25
SENSOR t=1120 left=1793 right=5517 torque=1 V=11.25
SENSOR t=1211 left=1799 right=5522 torque=1 V=11.23
SENSOR t=1269 left=1800 right=5525 torque=1 V=11.25
SENSOR t=1361 left=1800 right=5528 torque=1 V=11.25
SENSOR t=1414 left=1800 right=5530 torque=1 V=11.25
SENSOR t=1461 left=1800 right=5530 torque=1 V=11.25
ABORT encoders still changing after timeout
STATUS explicit_stop
CLEANUP stop_ack=1 torque_off_ack=1 stable_off_readback=1
RESULT 1 run
```

The actual software expiry latch was observed421ms after last input, unlike the
earlier battery-aborted trial. Battery11.23–11.27V did not trip the20% gate.
However the200ms stable fixed-two-tick encoder band was NOT achieved within the
500ms observation after timeout. Right encoder continued small changes late in
that window. Do not call the full physical stop acceptance PASS, and do not
automatically relax the criterion. Mechanical settling, creep and measurement
effects are not distinguished by this trial. Explicit abort cleanup then stopped
and disabled motors, with stable-off telemetry confirmed.

Encoder delta539/536 ticks gives nominal wheel travel2.73/2.71cm using radius0.033m
and4096ticks/revolution. This is not an independent floor-distance measurement.
User subsequently confirmed: “응 전진후 정지 봤어” (observed forward movement
then stop). This confirms visible motion/stop, not exact distance or timing and
does not override the encoder settling acceptance failure. No second motion attempted.

## Final independent readback

Base ended at its45s timeout through SIGINT; wrapper exit1 is recorded, not a
spontaneous success exit. At00:12:44 KST no base/port owner; independent read:

```text
identification 00500100000005C800
supply 65040000
wheel feedback 0000000000000000080700009A150000
torque 00
commands 000000000000000000000000000000000000000000000000
RESTORE termios=0 modem=0 modem_saved=1
```

Thus11.25V (~41.7% voltage estimate), velocity0/0, encoder1800/5530, torque0,
commands0; serial settings restored. No charging, shutdown or automatic startup.

**Outcome: ACTUAL_COMMAND_TIMEOUT_OBSERVED / SETTLING_ACCEPTANCE_FAIL /
ABORT_CLEANUP_AND_INDEPENDENT_ZERO_CONFIRMED.** Full driving safety, hardware stop
distance qualification and final demo remain incomplete. User visual forward/stop
confirmation is now recorded. Next: diagnosis of settling criterion/data, not
another unapproved movement. This observation update involved no robot connection.
