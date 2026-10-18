# 20% policy trial preparation — 2026-09-27

## Scope / outcome

User requested preparation only after the earlier immediate-motion request could
not proceed because the updated trial was not deployed. Preparation is complete:
ARM64 build, battery policy checks and ROS fake-SDK regression PASS. Physical
command-expiry stopping remains PENDING. No real base/probe execution, motor
enable, serial-device access, LiDAR, firmware, charging or shutdown this turn.

## Exact artifacts

New isolated Pi directory:
`/home/twinpulse/guard-validation.RIUO8r/policy20-prep.zr1ee6`.
Source copied from local `guard_stop_probe`: probe.cpp, CMakeLists.txt,
battery_policy.hpp and battery_policy_test.cpp. No old source/build overwritten.

- New actual trial: `build/stop_probe`, SHA256
  `7bfe7dbce4a5760a767ea01aebd744bb5a546aaf80b418a318a555394694a000`.
- Fake-only trial: `build/stop_probe_fake`, SHA256
  `04d131b2ab2bf60c05e86dc5575b19d22258b83882bafba750842a6b4d0fb933`.
- probe.cpp SHA256 `d5b4698e4dc6db901b776771d1e84fffa584a03b9f901ea42f36ef550045dbc6`.
- battery_policy.hpp SHA256 `fd6248339fc4538ba92b17b8249782ce99992a635357a299394977e48cb1f319`.
- Existing guarded base remains `../base-build/turtlebot3_ros`, unchanged SHA256
  `403b148b2bdbf0e4c6fc0540888768f9a5eddd38649b1d20883e61fb7fcdc042`.

New trial uses the fixed atomic one-shot marker
`/home/twinpulse/guard-validation.RIUO8r/stop-probe-20260927-policy20-consumed`.
It is created only by a future explicitly authorized physical run after preflight,
before any enable request. It does NOT exist as of final preparation inspection.
Old `stop-probe-run-consumed` remains untouched. No automatic retry/removal.

## Verification

Pi GCC11.4/C++17 Debug/Wall/Wextra/Werror/pedantic built all three targets, exit0.
Direct battery test:615 checks PASS; CTest1/1 PASS. New real executable ldd found
no missing shared libraries with /opt/ros/humble/setup.bash sourced.

Actual ROS API with compile-time fake SDK only, localhost domain87 and namespace
`/tp_guard_probe_fake`: normal fake voltage changed to11.40V to regress the earlier
boundary failure; low fake voltage changed to exactly10.86V (estimated20%).

Normal fake one-shot: preflight11.4V/50%,12 messages at+0.03m/s over600ms,
command_timeout observed416ms after last send, stopped encoder band stable,
cleanup stop_ack=1/torque_off_ack=1/stable_off_readback=1, result0.
Low fake: rejected by battery gate before any enable request, result0.
Both fake cases executed under20s timeout and returned normally.
Fake SDK has no serial/device implementation. These timings are NOT physical
stopping measurements or a safety certification.

At00:07:59 KST: no exact-name turtlebot3_ros/stop_probe/stop_probe_fake process,
no ttyACM0 owner; old marker preserved and new marker absent. No fresh battery
voltage or torque measurement was performed in this preparation turn.

## Next action, not performed

Lengthy compilation is complete. Obtain fresh operator confirmation that they
are watching, area is clear and power cutoff accessible, then do immediate
stationary hardware/battery preflight using the previously validated guarded base.
If any check fails or preparation is delayed, do NOT move; report and reconfirm.
Proposed bounded trial remains+0.03m/s/600ms input, zero angular velocity,
observe400ms command expiry, then explicit stop/motor-off and independent readback.
Expected travel is about3cm, not guaranteed. Use the new trial path above; never
the historical11.4V binary or the unguarded original default launch.

User charging policy remains estimated<=20%, with independent board protection
taking priority. No new battery monitoring service or production/default launch
change is implied. See [policy](robot-battery-policy-20260926.md) and
[earlier physical result](robot-command-expiry-motion-20260926.md).
