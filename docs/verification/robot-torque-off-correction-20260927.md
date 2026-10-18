# OFF-only preparation corrected — 2026-09-27 11:52–11:56 KST

## Decision and authorization

User requested that the unresolved torque issue actually be fixed instead of
keeping a charged robot waiting for manual steps. Earlier explicit flat/clear-floor
confirmation remains the current physical setup; no new movement was approved.

The first OFF helper incorrectly used exact encoder equality as permission to
remove motor torque. This conflated **OFF-only maintenance on a supported flat
floor** with **physical stopping qualification before driving**. Corrected only
that maintenance condition: encoder differences are recorded, not interpreted as
motion qualification and not a reason to leave torque enabled. Identity, exclusive
ownership, no debug/host connection, released buttons, voltage, motor connection,
zero commanded/sampled speed, single OFF write and independent read remain.
The previous physical settling122ms<200ms FAIL and all driving thresholds are
unchanged. The first failed attempt/log/consumed marker remain untouched.

## Actual OFF result

- Separate new run: `artifacts/torque-off-20260927-correction/`.
  Remote: `/home/twinpulse/.local/share/twinpulse/robot/torque-off-20260927-correction/`.
- Source archive SHA256 `436cfadf556f1e7f77e59b47654f4993e926ab646e1a810e0a111f527141b7e2`.
  ARM64 helper SHA256 `ce746d1b3d3e4e8e084f24cb7180ab3b21e9622dbaa2fd750cf4dfa7d35f118c`.
- Existing g++17/O2/Wall/Wextra/Werror/pedantic build PASS,88 device-free core cases
  PASS, including encoder-change annotation, OFF failure, ignored OFF and nonzero
  speed after OFF. The fake test is not the physical result below.
- User-approved wrapper ran once. Preflight left2321→2320, right1626, speed0,
  commands0, voltage11.89V. Exactly one `write1ByteTxRx(ID200,149,0)` ACK succeeded.
  Three subsequent snapshots show torque00, speed/commands0. Right encoder
  briefly1627 then1626; recorded `encoder_changed=1 motion_qualified=0`.
- Separate immutable READ helper then returned torque00, speed0/0, commands0,
  encoder2320/1626,11.89V. Both helpers restored serial settings. No heartbeat,
  torque-enable, velocity, LiDAR, base startup, firmware or power action.

Manufacturer [motor driver source](https://raw.githubusercontent.com/ROBOTIS-GIT/OpenCR/master/arduino/opencr_arduino/opencr/libraries/turtlebot3_ros2/src/turtlebot3/turtlebot3_motor_driver.cpp)
shows `set_torque(false)` sends torque0 to both motor IDs and startup calls
`set_torque(true)`. Its reported torque flag is aggregate: `get_torque()` is true
only if both motor reads return true. Thus ACK/board flag0 corroborate the OFF
path, not independent electrical proof of each motor's current or a certified
emergency stop. Installed binary/source reproducibility remains unproven.

## Permanent preparation integration

Added reviewed helper build to `runtime.prepare`, manifest-verified `disarm_board`,
fixed `owned_exec` torque-off role with parent-death binding,8s timeout and existing
lease, plus explicit paired flags on both client/runtime. Plain prepare/check/
offline/stationary never implicitly write torque. Invalid/missing combinations
reject before connection. Independent READ runs after an OFF failure; control
action is not retried. OFF-helper completion cannot grant motion permission.

For an approved supported-floor setup, the operator/assistant can now use one
preparation command instead of staging/compiling/manual register steps:

```powershell
.\.venv\Scripts\python.exe -B scripts/prepare_robot.py --mode prepare --disable-torque --operator-confirmed-flat-clear-floor
```

These flags represent real authorization/known setup, not a substitute for it.
No automatic-on-boot service, OS change or general motion runner was installed.

- New permanent release `1f444e2e03e4d16c7e4a62eaaa62bd11df000a6ca46c11f54b32fae6b227d603`.
  ManifestSHA `0b15bb43d1aca753721b418ed4fcbd7a895b797d5859f6d1623863e76c4784f3`.
  Original release retained; guarded base binary unchanged.
- First plain prepare (no additional OFF):
  `artifacts/robot-preparation/20260927T025439Z-c67117e8/`.
  Actual Pi CTest4/4 PASS(runtime8, stationary17 fake, commandguard1314, OFF88),
  battery615 PASS; ARM64 READ/OFF helper builds PASS. Local client5 tests PASS.
  Result **SOFTWARE_PREPARED_IDLE**,11:54:55KST11.87V/76.1% voltage estimate,
  torque0, speed/commands0, encoder2320/1626,manifestVERIFIED.
- Same-source cached prepare with explicit OFF flags:
  `artifacts/robot-preparation/20260927T025601Z-8dc8205f/`.
  Integrated actual parent-death/helper/report path PASS,11:56:06KST
  SOFTWARE_PREPARED_IDLE,11.87V,torque0,speed/commands0,encoder2321/1626.
  Already OFF so helper sent no further torque write. See retained
  `remote-operation.log`; no `TORQUE_OFF addr=` write line.
- Existing retained CTest relocation-path defect remains; these tests ran during
  staging before rename. Do not claim the post-rename CTest directory is portable.

## Readiness and working agreement

Basic OFF/idle preparation now works. This is NOT a completed physical demo:
actual stationary lifecycle, LiDAR receive/stop/TF, settling qualification,
D2 physical runner and scan→Twin/mission integration remain.
Prepare software, bounded observation and cleanup before asking the user to wait
with power on. Batch no-motion diagnostics and use one current setup confirmation
within the same session; do not repeatedly ask about an unchanged setup.
After a power/setup change, or before actual motion, required confirmation is fresh.

User requests sensor-based local judgment as a product requirement. Future robot
preflight must report current scan freshness/coverage/frame and footprint clearance,
and distinguish CLEAR/BLOCKED/UNKNOWN rather than treating no scan as clear.
Current LiDAR stop/scan/TF are unverified, so no live obstacle judgment was fabricated.
No human presence/ground-support guarantee can be inferred from an unqualified scan.
Do not promise “power on and full demo works” while these gates are incomplete.
