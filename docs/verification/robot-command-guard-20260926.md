# Robot command guard — 2026-09-26

## Scope and architecture

User approved implementing automatic stop consistent with the final TwinPulse demo.
This step is software implementation and no-motion verification, not approval to
enable torque or drive. New package: `packages/twinpulse_robot_safety`.

The pure C++ CommandGuard owns command expiry and a latched output state. RosGuard
adapts it to the existing single-threaded TurtleBot base process, immediately
upstream of the existing SDK writes. The same path renews heartbeat only after a
successful velocity write. Thus stopping/stalling this guard cannot leave the old
independent base heartbeat running. No firmware changes are required for this
host-side change. The board's existing heartbeat fallback remains a separately
qualified lower-layer dependency, not a physical stop-time guarantee.

This is the final-output safety slice of the demo architecture. Full operator
approval/mission binding, source leases, sensor freshness/TF, obstacle limits,
physical emergency handling, App UI and Nav2 adapter are NOT completed here.

## Behavioral contract

- Starts disarmed; explicit arm service with one command publisher, acknowledged
  zero write, no torque activation. Stop/timeout does not automatically re-arm.
- Stamped body-frame input only, queue1, volatile. Linear limit0.05m/s, angular
  limit0.30rad/s, source/receipt lifetime400ms, output wall timer20ms.
- Nonfinite/excess values, wrong axes/frame, invalid/stale/replayed/future stamps,
  no/multiple publishers and GID replacement cause a latched stop.
- New arm invalidates pre-arm stamps. A already-armed arm call cannot refresh the
  deadline. Clock skew is fail-closed; robot-local controller is the initial target.
- Output/heartbeat I/O failure is latched until process restart; no renewed
  heartbeat, best-effort zero writes. Restart itself remains disarmed.
- Process orderly exit writes zero. Constructor/exit never enable motor torque.
- 400ms is a software command deadline, not a certified physical stop bound;
  serial blocking, executor latency, firmware/motor behavior and braking add delay.

## Source preservation / staged integration

Official source pinned at `90a68bd2e3c61c12966779da89d8eeaec82730e9`.
The original `/home/twinpulse/turtlebot3_ws` source/install are not modified.
Fresh staging root `/home/twinpulse/guard-validation.RIUO8r` contains:

- `twinpulse_robot_safety`: copied package/test source.
- `vendor`: official git archive plus checked `turtlebot3-90a68bd.patch` and headers.
- `test-build`: pure core + actual ROS API integration with compile-time FAKE SDK.
- `base-build`: real-SDK official base build with the guard connected.
- `guard-sanitized`: pure core ASan/UBSan test executable.

Patch application first failed due to excess blank-line context; corrected patch
then passed normal `git apply --check` and application. Existing upstream raw
callback/heartbeat helper definitions are retained but no longer registered in
the patched run path. Only guarded_cmd_vel is intended to be subscribed.

**The old default launch remains unguarded.** Do not use it for future driving.
Only an explicitly selected, validated guarded executable has this behavior.
No automatic startup, shell profile, ROS system installation, LiDAR source or
firmware changed. No commit/push performed.

## Final observed tests

- ARM64 GCC11.4 / C++17 / Wall/Wextra/Werror/pedantic: pure core **1314 checks PASS**.
- Pure core AddressSanitizer + UndefinedBehaviorSanitizer: **1314 checks PASS**.
- ROS Humble fake-SDK integration final expanded run: **62 checks PASS**,
  including post-shutdown input/arm rejection. Uses actual rclcpp subscriptions/services/timers,
  but test SDK contains NO serial/device implementation. Nonzero test values go
  only to fake memory in localhost domain87, `/twinpulse_guard_fake_only`.
- Real-SDK official base with the vendor patch: **ARM64 Release build PASS**.

The deterministic400-case age sweep includes the initial-arm timeout boundary.
Other cases cover start disarmed, explicit arm/stop, sustained refresh, exact
expiry, delayed/repeated input, source loss/conflict, speed bounds, NaN/infinity,
I/O failure, heartbeat ordering/suppression, and restart remaining disarmed.

No moving disconnection/stopping-distance test is part of this verification.

## Actual board: bounded stationary verification

The staged real executable ran for approximately75 seconds, with ROS_DOMAIN_ID86,
ROS_LOCALHOST_ONLY1 and namespace `/tp_guard_stationary`. Firmware was unchanged.
No arm service, motor-enable service, nonzero hardware command or LiDAR operation
was invoked. The node began disarmed and remained `explicit_stop` in observed
status samples. Sensor samples reported torque=false and unchanged encoders930/4648;
odom linear velocity was0 and battery voltage approximately11.60V.

`ros2 node info` confirmed the base's only velocity subscription was the stamped
`guarded_cmd_vel`, with no original raw cmd_vel subscription. An earlier topic-info
query briefly reported unknown topic during discovery; subsequent node introspection
and topic samples succeeded. The test ended through the intentional75s timeout's
SIGINT; the wrapper returned1, not a spontaneous successful exit0.

At **2026-09-26 23:20:48 KST**, independent post-run read-only inspection found no
turtlebot3_ros process or ttyACM0 owner. Board response:

```text
identity: 00500100000005C800
supply: 86040000 (11.58V)
wheel feedback: 0000000000000000A203000028120000
torque: 00
commands: 000000000000000000000000000000000000000000000000
termios/modem restoration: success
```

Thus wheel feedback=0/0, encoders=930/4648 unchanged, torque disabled and all
command bytes zero. This verifies disarmed hardware integration only; software
timeout cases with nonzero values were exercised exclusively against the fake SDK.

Executable: `/home/twinpulse/guard-validation.RIUO8r/base-build/turtlebot3_ros`.
Runtime log: `/home/twinpulse/guard-validation.RIUO8r/stationary.log`.
SHA256 records:

| Artifact | SHA256 |
| --- | --- |
| Real ARM64 executable | `403b148b2bdbf0e4c6fc0540888768f9a5eddd38649b1d20883e61fb7fcdc042` |
| Vendor patch | `fa8fa60231daf3d90f691c1e4fc88016657e56b635cddf347d6d03fe1d5446c2` |
| command_guard.hpp | `ae30643662413c1a24289fb89126899dfb9194e84af905947a3eddee8d23d4a1a` |
| ros_guard.hpp | `7a99606207be9657bcb6b9671a881fd92262cf18ae361319558b731596c18262` |

**Outcome: software/fake-transport and stationary real-board tested scope PASS;
physical expiry-stop, process-loss stop, full B3/H6 and final demo remain PARTIAL.**
Next is a separately authorized, bounded physical stop test with operator present,
preflight checks, accessible power cutoff, explicit guarded executable selection,
and a finite command source. Do not resume broad motion using the old default launch.
