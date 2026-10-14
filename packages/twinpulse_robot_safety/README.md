# TwinPulse robot command guard (first bounded implementation)

This package is the robot-local **final velocity output gate**, not the full mission
adapter, navigation stack, obstacle monitor, or certified emergency stop. It is
separate from the App, AI provider, and Isaac simulator. An approved local mission
controller can later feed this gate without keeping a chat or cloud request alive.

## Implemented contract

- Startup is disarmed. `motion_guard/arm` is an explicit Trigger service; it writes
  zero first and never enables motor torque. One DDS command publisher must exist.
- Only `guarded_cmd_vel` (`geometry_msgs/msg/TwistStamped`) is subscribed. Body
  frame is exactly `base_link`; unsupported axes must be zero. Legacy raw
  `cmd_vel` is deliberately NOT connected in the patched base executable.
- Maximum |linear.x|=0.05m/s and |angular.z|=0.30rad/s. Excess, nonfinite values,
  wrong frames, stale/future/duplicate stamps, or publisher replacement cause a
  latched stop, not silent clipping. These are initial experimental limits, not
  measured safe operating limits.
- Source timestamp must be after arm and strictly increasing. Its age reduces the
  remaining 400ms command lifetime. Expiration is enforced with a steady clock,
  checked by a 20ms wall timer. Real scheduling/serial delay is additional; this
  is NOT a guaranteed400ms physical stopping time. Physical use_sim_time is rejected.
- Timeout, no/multiple publishers or explicit stop cannot be cleared by another
  movement message. Reconnection does not re-arm. An explicit new arm plus a new
  post-arm command is required. Already-armed arm requests cannot extend a deadline.
- The same output path writes velocity and only then renews the board heartbeat
  at100ms intervals. Write/heartbeat failure latches an I/O fault and suppresses
  ALL subsequent heartbeats until process restart, with best-effort zero writes.
- Process startup and orderly exit explicitly write zero. A crashed or stalled
  process cannot keep an independent heartbeat timer alive. Firmware heartbeat
  expiry remains the lower-layer fallback and requires separate physical validation.
- `motion_guard/stop` sends zero and disarms; `motion_guard/status` reports reason.
  Neither replaces a physically accessible power cutoff. No torque-enable logic
  is added. The upstream motor_power service is separate and must not be invoked
  without current operator approval.

## Integration and preservation

`turtlebot3-90a68bd.patch` targets ONLY official TurtleBot3 commit
`90a68bd2e3c61c12966779da89d8eeaec82730e9`. Use `git apply --check` before application.
Copy `include/twinpulse_robot_safety` into that source's `turtlebot3_node/include`.
The patch instantiates RosGuard in the official node, disconnects the legacy
velocity subscription and independent heartbeat, and adds orderly shutdown zero.
Upstream helper definitions remain uncalled to keep the vendor diff small.
Retain upstream license headers. Do not automatically apply to another release.

The initial validation uses a separate source/build folder. The original Pi
workspace, its default launch, firmware and automatic-start configuration remain
unchanged. **Running the old default launch still runs the old unguarded path.**
Future robot experiments must explicitly select the guarded executable; making
it the default product deployment is a separate, recorded integration step.

## D1 package preparation (2026-09-27: deployed; idle snapshot confirmed)

The next source-only release adds a pre-build, device-free Humble argument probe and pins the reviewed Burger parameter YAML hash. ROS topic namespace remains `/tp_guard_stationary`, while the vendor `namespace` parameter is explicitly empty to avoid a leading slash in odom/TF frame IDs. The stationary observer now records bounded `/tf_static`, endpoint/missing-message reasons and redacted failure-log clues. These changes have not been deployed or physically verified. The COIN-D4 ROS driver remains separate and is not automatically started. See [collector preparation](../../docs/verification/robot-collector-preflight-20260930.md).

`Prepare-Robot.cmd` in the repository root packages this source, verifies the
qualified existing guard binary, builds the READ-only helper with the existing
Humble SDK, runs device-free checks and records an idle snapshot. No driver or
motion trial is started. Source-addressed releases and reports go under
`~/.local/share/twinpulse/robot/`; existing installations and one-shot markers stay.

The migrated trial in `trial/` is not enabled by default. Explicit
`runtime.py stationary` / `Check-Robot-Stationary.cmd` implements a bounded
disarmed lifecycle with a passive20-second observer and final independent READ.
Children inherit the lease FD and bind to parent death. Legacy/direct SDK users
do not honor it. This is not a robot-wide enforcement boundary or clean-OS installer.
Live ARM64/ROS qualification remains pending. Preparation never invokes stationary.
`trial_session.py` is a dry-run approval/expiry/binding contract only, always
returning `motion_authorized:false`; the physical adapter remains disconnected.
See [lifecycle preparation](../../docs/verification/robot-charging-offline-prep-20260927.md).

An explicitly approved supported-floor preparation can add `--disable-torque`
and `--operator-confirmed-flat-clear-floor` to Prepare-Robot. It builds/caches a
fixed OFF-only helper, takes the same lease, checks identity/zero commands/speed,
sends at most one torque-OFF write and independently READs afterward. Encoder
changes are retained as observations, never promoted to motion qualification.
Plain prepare/read/offline/stationary do not imply torque control. Startup torque
enable was observed; the OFF path and permanent integration now passed in their
limited scopes. No auto-boot control service was added, and actual stationary
ROS lifecycle/physical stopping/LiDAR/full demo qualification remain incomplete.
[OFF result and preparation evidence](../../docs/verification/robot-torque-off-correction-20260927.md).

## No-device tests

```text
cmake -S packages/twinpulse_robot_safety -B <new-build-directory>
cmake --build <new-build-directory>
ctest --test-dir <new-build-directory> --output-on-failure
```

On a ROS Humble host, source its setup and add `-DBUILD_ROS_TESTS=ON`.
`ros_guard_test` shadows the SDK header at compile time with a recorder containing
no serial/device implementation. It forces localhost domain87 and the dedicated
`/twinpulse_guard_fake_only` namespace. Nonzero commands in that executable reach
only fake memory. Never substitute the real SDK into this test.

Core tests use fake clocks and writers. ROS tests exercise actual subscriptions,
services, timers, source count, lost input, stale input, explicit stop, I/O failure,
and component restart, but do NOT test physical deceleration or firmware behavior.

## Remaining demo work / limitations

### Explicit manual console path (implemented offline; not physically qualified)

`teleop.sh` exposes only fixed `off`, `lidar`, `qualify`, and `control` roles.
The PC console invokes them only on current explicit operator confirmation; there
is no boot service or auto-connect. The existing `motion_enabled:false` remains
the legacy trial/mission gate. The separate `manual_control_policy` requires a
robot-local successful fixed stop test tied to the current boot and full release
before manual wheel commands. Preparation/idle READ and stored PC reports cannot
grant this permission. Qualification preserves the original200ms/2-tick/500ms
criteria and consumes a new one-shot marker immediately before torque enable.

The robot challenges the sender for fresh inputs; queued inputs preserve age.
Each held gesture is bounded to2s and a session to60s. Release requests guard
stop/torque OFF. EOF/errors clean up the owned base before independent OFF/READ.
LiDAR is a separate bounded8s job with cancel and STOP cleanup, not rotor feedback.
This source has no new physical deployment/ROS/ARM64 acceptance yet. Tests with
fake devices are not physical qualification or a certified emergency stop.
See [manual console scope](../../docs/verification/physical-controller-20260927.md).

- The arm service is not an authenticated mission approval or multi-source lease
  manager. The future mission adapter must enforce operator approval, candidate/
  map/profile binding, source selection and session ownership before arming.
  DDS publisher count/GID is accidental-source protection, not a security boundary.
- Sensor/TF freshness, obstacle/area checks and actual stop distance remain future
  layers. Pi and sender clocks must be synchronized and their offset measured;
  default scope is a robot-local controller, not an arbitrary WAN velocity stream.
- Do not wrap old Twist messages with a fresh timestamp merely to pass the guard.
  That hides upstream age. A future Nav2/teleop adapter needs an honest freshness
  contract and verified failure behavior.
- The existing OpenCR button/RC100 inputs are separate from ROS velocity. Do not
  press drive-test buttons or enable another control path during a run.
- No guarantee covers a failed MCU/motor bus, loss of power, hung kernel, all
  hardware faults, or another process writing directly to USB. Single serial
  ownership and lower-layer protection must be checked before physical tests.

See `docs/verification/robot-command-guard-20260926.md` for observed results and
the exact staged executable. No full B3/H6 completion is implied.
