# OpenCR stationary precheck — 2026-09-26

## Latest: command-loss stop-path source review

Scope: user approved checking the stopping path, not implementing changes or enabling motion. Read-only SSH source inspection and existing read-only register helper only. No ROS process, heartbeat, motor-power service, movement publisher, firmware upload or LiDAR command started this turn.

Pi source checkout `/home/twinpulse/turtlebot3_ws/src/turtlebot3` is clean at `90a68bd2e3c61c12966779da89d8eeaec82730e9`.

- `turtlebot3_node/src/turtlebot3.cpp` lines221–269: run installs independent50ms sensor and100ms heartbeat timers. Heartbeat increments regardless of cmd_vel freshness.
- Same file lines331–406: both Twist and TwistStamped callbacks convert velocity and write it to OpenCR. No last-received timestamp, command timeout, or stale-stamp rejection. Header stamps are not checked by the stamped callback.
- `include/turtlebot3_node/twist_subscriber.hpp` only selects the subscription type and forwards callbacks; it does not add a timeout despite explanatory comments about stamped messages.
- `include/turtlebot3_node/turtlebot3.hpp` has an empty destructor; inspected main shutdown and SDK destructor do not establish an explicit zero-velocity-on-shutdown path. MotorPower is a separately invoked service, not publisher-loss monitoring.

Manufacturer OpenCR public source reviewed at https://raw.githubusercontent.com/ROBOTIS-GIT/OpenCR/master/arduino/opencr_arduino/opencr/libraries/turtlebot3_ros2/src/turtlebot3/turtlebot3.cpp : heartbeat timeout500ms, update_connection_state_with_ros2_node, and run clear the ROS-derived goal when connection is false. Debug mode overrides heartbeat expiry; button/RC100 contributions are separate. This public source is supporting design evidence, **not a reproducible-build match to the installed V230127R1 binary**. Earlier stationary connection-expiry check corroborates only the tested no-motion behavior. No500ms physical stopping-distance/time guarantee is claimed.

Conclusion: losing only the velocity publisher (including PC Wi-Fi loss with robot-local base still running) is distinct from losing base→OpenCR heartbeat. For the first case no command-age zeroing path was found; last movement can persist if motors are enabled. Therefore general ROS motion/turning remains gated on a reviewed command-expiry stop mechanism and nonmoving verification. Stopping a publisher is not an emergency stop. A future supervisor must also account for its own failure, not just periodically publish zero while alive. Earlier direct-SDK3cm test explicitly sent zero and torqueoff; its success is not invalidated, but did not exercise this scenario.

Current independent read: no visible turtlebot3_ros/serial owner; PING and all READ comm0/error0, identity BurgerFW5, voltage `A0040000`=11.84V, wheel feedback `0000000000000000A203000028120000` (zero speeds, same930/4648 encoders), torque00,24 zero command bytes. Port settings restored by helper. No source/configuration/firmware fix or physical fault injection performed. The defect finding is static; runtime command-loss behavior with nonzero command is not experimentally reproduced.

## Latest: stationary base ROS telemetry, 22:46–22:49 KST

User approved stationary ROS checks after asking what additional tests were needed. No wheel movement or LiDAR activation authorized/executed in this check. Installed official source inspection covered node initialization, SDK, motor-power service, sensor references, odometry and Burger params/launch. Startup performs IMU recalibration (5s) and heartbeat but does not invoke the torque-enable service. Preflight read-only helper confirmed firmware5, supply11.91V (`A7040000`), wheel velocities0, positions930/4648, torque0 and24 zero command bytes. No serial owner was visible.

Only `turtlebot3_ros` was run, not the full robot launch. Process-local ROS_DOMAIN_ID86 / ROS_LOCALHOST_ONLY1; `/tp_stationary_check` namespace; `cmd_vel` remapped to `disabled_cmd_vel`; official Humble burger.yaml. No persistent environment or service configuration changed. Initially empty domain. Runtime graph showed only turtlebot3_node and diff_drive_controller, and disabled_cmd_vel had **0 publishers / 1 subscriber**. No service calls or velocity publication occurred.

First attempt failed with `UninitializedStaticallyTypedParameterException: namespace` before SDK initialization/port open. Supplying `-p namespace:=tp_stationary_check`, as the official launch normally does, fixed the invocation without source edits. The second invocation was bounded by `timeout --signal=INT --kill-after=5s 150s`. Log time1790430364.510799→1790430514.428227 (~149.92s), including initial5s calibration; final SIGINT/SIGTERM handler line present, no communication errors in the retained base log. Tool wrapper reported exit1 at timeout, so this is not described as a natural exit0. Independent process/port checks afterward were empty.

Observed results:

- Odom25s CLI sample: final reported average20.008Hz, min interval0.037s/max0.063s, stddev0.00649s, window433.
- IMU25s CLI sample: final20.009Hz, min0.039s/max0.061s, stddev0.00506s, window449.
- Sensor states at1790430407 and1790430503: torquefalse, encoders930/4648, buttons0. JointState sample positions0/0 relative to node startup, velocities0/0.
- Battery early11.87V, late11.85V. `percentage` output76.1100006 then75.0; do not treat this unvalidated field as accurate remaining capacity or directly map it to UI. Charge/current/capacity fields are zero, not measured proof of zero current or empty capacity.
- IMU sample quaternion(-0.0026513,-0.0006275,0.0070591,0.9999671), angular velocity0/0/0, accelerationZ10.2244m/s². Reception/finite values only, not calibrated accuracy acceptance.
- Odom sample position approximately0, linear velocity0, small angular estimate7.65e-5rad/s. Late TF at1790430500: `tp_stationary_check/odom`→`tp_stationary_check/base_footprint`, translation approximately0, quaternionZ3.025e-5/W0.9999999995. Only this TF edge checked; robot_state_publisher/full URDF/LiDAR TF not started.
- One extra late CLI read occurred after the timed node had already exited and reported unavailable topics. This is logged as a post-shutdown query, not evidence of an in-run disconnection.

Postcheck22:49:28: read-only helper PING and all READ comm0/error0; supply `A1040000`=11.85V; wheel feedback `0000000000000000A203000028120000` (velocities0/0, same930/4648); torque00;24 command bytes zero. Helper restored the port state it found. Official ROS node left serial baud1000000; full pre-ROS termios restoration was not claimed. No running turtlebot3_ros, no visible serial owner, empty isolated ROS graph. Robot remains powered, stationary and torqueoff; no shutdown or battery change performed.

Robot logs retained under `/tmp/twinpulse-stationary-ros.HyS2Kj/`: `base.log` (first failed invocation), `base-second.log`, `odom-hz.log`, `imu-hz.log`, `tf.log`, `sensor-state.log`, `battery.log`, `postcheck.log`. Late-query files may be empty; original early echo samples were returned in tool output. Temporary logs may disappear on reboot.

**Limited stationary base ROS reception PASS; full B2 remains PARTIAL.** This was not a continuous recorded120s all-topic/stamp quality audit, a moving ROS test, stopping-distance/connection-loss test, sensor accuracy calibration or LiDAR acceptance. Before later ROS motion, review command freshness/stop behavior: inspected base callback writes received velocity while a separate timer maintains heartbeat; do not assume publisher disappearance alone stops motion. No driver patch, firmware change, install, torque-enable, wheel movement or LiDAR command this turn.

## Latest operator clarification: normal forward direction

User clarified actual travel was away from bed and opposite the ball-caster support. They called this backward only because they believed the caster side was front. Official Humble Burger URDF defines `caster_back_joint`/`caster_back_link` at x=-0.081 relative to base_link, i.e. rear: https://github.com/ROBOTIS-GIT/turtlebot3/blob/humble/turtlebot3_description/urdf/turtlebot3_burger.urdf . This supports normal positive-forward travel in the one-shot test. Limited physical movement/stop plus direction confirmed from encoder evidence and operator observation, not a measured full trajectory or comprehensive robot acceptance. No velocity-sign inversion, motor configuration change, further robot access or movement. Last confirmed torque0. Prior direction-uncertain record below is historical.

## Operator follow-up: movement observed, direction unresolved

In response to “눈으로도 조금 전진했다가 멈춘 게 보였나요?”, user replied “응 뒤로 3cm 정도 갔어”. This corroborates the short movement/stop while explicitly reporting backward motion in their frame. Do not accept forward-direction alignment or silently invert velocity signs. Establish which physical side the user calls front, compare manufacturer frame/assembly, and diagnose configuration only if needed. No additional robot access, motion or configuration change made for this observation. Last measured torque0. Prior visual-confirmation-pending text below describes the earlier state.

## Latest: explicit one-shot movement approval and execution, 22:30 KST

User described battery setup and sent cleared-floor photo. Previous motion dispatch was rejected by approval review because photo alone did not explicitly approve physical movement; no movement executed then. Assistant asked exact permission for 0.03m/s for approximately1s, one time, explicit zero and motor de-energization; user replied “응 진행해”. This grants this one test only, not broader navigation or future motion.

Reviewed helper `C:\Users\jaewo\Documents\Codex\2026-09-12\dl\opencr_short_motion.cpp`, SHA256 `e6956b34954ac7d4e1bd76fd0cf2612564aa50d600cfc7f7d53dd7633c9af561`. Existing SDK, fixed OpenCR by-id/ID200, Burger model/FW5 gates. No arbitrary speed/duration/port parameters. --check tests heartbeat connect/expiry while commands and wheel feedback remain zero; this passed before motion. --run repeats gates then one +3 raw (0.03m/s) command, approximately1s deadline and bounded feedback checks. Only register writes: heartbeat19, velocity150={0,3}, angular170=0, torque149=0. No torque-enable/calibration/firmware/LiDAR writes. Exception/signal path attempts stop; independent board heartbeat expiry provides source-reviewed fallback, but moving loss-of-link behavior was not physically tested. Scheduler/serial latency means nominal 1s is not a hard real-time guarantee. Photos do not establish a measured1m clearance; operator was told to keep clear and cut power if unexpected movement.

Temporary binary `/tmp/twinpulse-short-motion.yFtK6V/check`; actual first run log `/tmp/twinpulse-short-motion.yFtK6V/run-first.log`. Compiled with C++14/O2/Wall/Wextra/Werror. Final no-owner/no-other-target-ROS-process check preceded run. --run executed once, exit0:

```text
PREFLIGHT voltage=12.17 positions=347,4076
STATIONARY_WATCHDOG_PASS (not a moving stop test)
MOVE_START linear=0.03m/s angular=0 duration_limit=1000ms
SAMPLE ms=16 velocity=0,0 delta=0,0
SAMPLE ms=142 velocity=9,6 delta=10,6
SAMPLE ms=336 velocity=38,35 delta=107,94
SAMPLE ms=659 velocity=37,36 delta=301,293
SAMPLE ms=982 velocity=36,38 delta=490,490
STOP linear_zero=1 angular_zero=1 torque_off=1
FINAL_STOP_PASS delta_ticks=583,572 torque=0 connection=0
RESTORE verified=1
```

Manufacturer nominal wheel radius0.033m/4096 ticks yields ~2.95/2.90cm wheel travel, not independent ground displacement or slip measurement. User actual movement/stop observation requested and pending. No automatic second run. Torque is now OFF; same helper's initial gate rejects another run without a separately considered torque-enable step.

Independent existing read-only helper afterward: all PING/READ comm0/error0; voltage `BF040000`=12.15V; velocities0/0; positions `A203000028120000`=930/4648; torque00; 24 command bytes all zero; termios/modem restore success. fuser no owner. (Positions match initial347/4076 plus583/572.) No ROS nodes or LiDAR runtime executed. Narrow result: command/encoder/stop feedback confirmed; full physical safety, ROS odometry, mapping, autonomous driving and battery capacity remain unvalidated.

## Latest: battery reboot follow-up, 22:22–22:23 KST

User reports switching from adapter to battery, powering on, and a short ascending melody only at startup. No recording independently verified; vendor source includes an initialization melody, not proof that Pi has booted. Earlier SSH attempts were refused; this attempt connected at same IP192.168.35.139 with uptime2min. Both known USB by-id entries persisted. No visible ttyACM0 owner.

Reboot removed previous /tmp helper. Read full unchanged `opencr_readonly_check.cpp`, rebuilt with existing g++/Dynamixel SDK (C++14/O2/Wall/Wextra/Werror) into fresh `/tmp/twinpulse-battery-readonly.T8yJn7/check`, then ran once. PING comm0/error0/model20480; all six reads comm0/error0. Identity `00500100000005C800` (Burger/FW5); status `00`; voltage `C3040000` =1219/100=12.19V; wheel feedback `00000000000000005B010000EC0F0000` (velocities0/0, positions347/4076); torque `01`; 24-byte command region all zero. Restore termios0/modem0, final baud9600 matches initial, fuser showed no owner. No ROS/heartbeat/velocity/torque/firmware/LiDAR command sent. Snapshot only: not a physical stopping or battery-capacity/load acceptance. No further fixed three-minute wait is required now SSH works.

## Latest: approved official upload and protocol verification PASS

2026-09-26 22:10–22:12 KST. User completed libc6:armhf install in their authenticated SSH session (2.35-0ubuntu3.15). dpkg audit returned no issues; no apt-get/dpkg process visible. ARM loader dependencies resolved. Firmware/loader SHA256 unchanged from preparation below; exact OpenCR by-id still resolved to ttyACM0, no visible fuser owner.

Executed vendor `./update.sh /dev/ttyACM0 burger.opencr` once in the recorded staging directory, with pipefail and tee log. No retry/recovery button procedure was needed. Existing application overwritten; no original application backup exists.

```text
fw_name: burger
fw_ver: V230127R1
Board Name: OpenCR R1.0
Board Ver: 0x17020800
[OK] flash_erase: 0.91s
[OK] flash_write: 1.34s
[OK] CRC Check: D92222 D92222
[OK] Download
[OK] jump_to_fw
```

SSH command exit0. Same USB by-id returned. Independent bounded identity READ (not just uploader success) returned:

```text
IDENTITY_READ id=200 address=0 length=9 timeout_ms=1000 comm=0 error=0 bytes=00500100000005C800
model=20480 model_info=1 firmware=5 id=200
RESTORE termios=0 modem=0 readback_match=1
```

Follow-up existing read-only status helper:

```text
PING id=200 comm=0 error=0 model=20480
READ identification addr=0 len=9 comm=0 error=0 bytes=00500100000005C800
READ expected_device_status addr=18 len=1 comm=0 error=0 bytes=00
READ expected_supply_voltage addr=42 len=4 comm=0 error=0 bytes=BB040000
READ expected_wheel_feedback addr=128 len=16 comm=0 error=0 bytes=00000000000000005E010000EC0F0000
READ expected_torque_state addr=149 len=1 comm=0 error=0 bytes=01
READ expected_command_state addr=150 len=24 comm=0 error=0 bytes=000000000000000000000000000000000000000000000000
RESTORE termios=0 modem=0 modem_saved=1
```

Supply raw1211; left/right velocity feedback0; positions350/4076 raw counts. These are a snapshot, not physical stop-performance or motor-connectivity acceptance. Torque flag1 is reported by the new firmware: absence of host torque commands does NOT mean motors are de-energized. No host velocity/torque-enable/heartbeat/calibration write, ROS node or LiDAR runtime executed. Vendor uploader performed firmware reset/jump as part of approved update. Final fuser and targeted ROS-process query showed no owner/runtime. No battery swap or Pi reboot performed this turn.

Remote logs retained under `/home/twinpulse/firmware-staging/opencr-official.fzGgP5/`: `upload-first.log`, `identity-after-upload.log`, `status-after-upload.log`. Outcome: expected board protocol communication is now established; previous program identity remains unknown. Full bringup, controlled wheel motion/stop, odometry and LiDAR physical-stop behavior remain unverified. Prior sections below are historical preparation and diagnosis.

## Latest: official firmware preparation, upload NOT_RUN

User explicitly approved overwriting the existing application with official ROS2 Burger firmware after the risk/overwrite explanation. Wheel motion, LiDAR runtime and full bringup remain out of scope. Adapter/USB stay connected; no battery swap requested.

- Source: ROBOTIS-GIT/OpenCR-Binaries commit `57ac5807d07000b30bca0476b2ffefaca172e3d5`, `turtlebot3/ROS2/latest/opencr_update.tar.bz2`.
- Pi staging: `/home/twinpulse/firmware-staging/opencr-official.fzGgP5/opencr_update`.
- Archive SHA256: `df13eba4e915c6ab4ed225329c8a02ebd69cd5655675e9d60f72214c4d029518`.
- burger.opencr SHA256: `6b445fde733740e9aa35b00ec41843305a609ec3bd9ef602e7bcde415168b1be`.
- opencr_ld_shell_arm SHA256: `9ca99f1189532cc141e90a11d818404010268861fec67b68c76e07e38e81e6b6`.
- Despite filename extension, archive is gzip. Initial bzip2 listing failed; `file` and automatic tar listing confirmed format. Entries were inspected before extraction into fresh staging, with no-same-owner/no-same-permissions. No existing project files overwritten.
- Reviewed full vendor update.sh/README. Script selects ARM uploader for aarch64, passes port, 115200, firmware and mode 1. Loader ELF is ARM32 EABI5, dynamically requires libc.so.6 and `/lib/ld-linux-armhf.so.3`.
- Pi aarch64, no foreign architectures, libc6:armhf absent. `sudo -n true` returned password required. No password requested through chat, no installation or uploader execution performed.

Next: user runs official prerequisite commands in their own authenticated robot SSH terminal: `sudo dpkg --add-architecture armhf`, `sudo apt-get update`, `sudo apt-get install libc6:armhf`. Verify install, then recheck OpenCR target/ownership and execute approved vendor update for Burger only. Retain upload log and verify actual board identity afterward; do not infer upload success from download or script exit alone. Firmware original application/version is unknown and has not been backed up. No zero-risk or guaranteed repair claim.

Official instructions: https://emanual.robotis.com/docs/en/platform/turtlebot3/opencr_setup/ (Humble OpenCR Setup). Earlier sections below reflect pre-approval observations.

## Follow-up: firmware identification (latest)

User authorized identifying current firmware, not uploading/resetting it. USB properties still show generic ROBOTIS OpenCR CDC, revision `0200`. Manufacturer core source hardcodes that USB descriptor value; it is not proof of ROS2 or an application firmware version. ModemManager is inactive; targeted kernel log query returned no entries (not proof of no historical USB faults).

Manufacturer ROS2 source defines protocol 2.0 / ID 200 / model 0x5000, with model information at address 2 and firmware version at address 6. Debug version text is routed to SerialBT2, not necessarily USB. USB core uses DTR as the opened flag; 1200-baud and a special boot message are reset mechanisms. Neither reset mechanism was used.

A separate helper with installed SDK performs a direct READ of addresses 0..8 after asserting normal DTR (without cycling it), 500ms settling, and a 1000ms receive timeout. One bounded execution returned:

```text
CONNECT dtr_set=0 saved_modem=38
IDENTITY_READ id=200 address=0 length=9 timeout_ms=1000 comm=-3002 error=0 message=[TxRxResult] Incorrect status packet! bytes=
RESTORE termios=0 modem=0 readback_match=1
```

Because data format was unexpected, one further **passive** observation (no application packet transmission, maximum 3s/256 bytes) returned:

```text
CONNECT dtr_set=0 saved_modem=38
PASSIVE bytes=16 hex=31300D0A31300D0A31300D0A31300D0A
RESTORE termios=0 modem=0 readback_match=1
```

This is ASCII `10\r\n` repeated four times. It proves USB reception in this check, but does not identify the installed sketch/version or establish what "10" means. No valid expected ROS2 identification reply or rosserial frame was observed. Do not label this conclusively ROS1, factory firmware, or hardware failure. A different/test application is a hypothesis, not a verified identity. Host adapter power does not need changing for these checks.

Final fuser showed no visible owner; both USB by-id paths persisted. Terminal flags/control characters/baud/modem flags were reread and matched the saved state. No motor, heartbeat, calibration, firmware-upload or reset command was sent. Existing ROS and LiDAR sources unchanged.

Follow-up helper: `C:\Users\jaewo\Documents\Codex\2026-09-12\dl\opencr_firmware_identify.cpp`; final SHA-256 `fff82183363e70167f3bd768b9984525a5c06525516c1ee649f75cb55e8010a5`. Temporary executable `/tmp/twinpulse-opencr-readonly.s1xmQj/identify`, not installed. The passive mode was added after the direct identity read; each mode ran once, without repeated flashing or motion tests.

Next decision: manufacturer/supplier identification of existing board program, or explicit approval to replace it with official ROS2 Burger firmware. Upload is a distinct destructive-to-existing-program operation, not authorized by this inspection. No claim that an update is guaranteed to resolve every hardware issue.

Public manufacturer source reviewed:
- https://github.com/ROBOTIS-GIT/OpenCR/blob/master/arduino/opencr_arduino/opencr/libraries/turtlebot3_ros2/src/turtlebot3/turtlebot3.cpp
- https://github.com/ROBOTIS-GIT/OpenCR/blob/master/arduino/opencr_arduino/opencr/libraries/turtlebot3_ros2/include/turtlebot3/turtlebot3.h
- https://github.com/ROBOTIS-GIT/OpenCR/blob/master/arduino/opencr_arduino/opencr/variants/OpenCR/hw/usb_cdc/usbd_cdc_interface.c
- https://github.com/ROBOTIS-GIT/OpenCR/blob/master/arduino/opencr_arduino/opencr/variants/OpenCR/hw/usb_cdc/usbd_desc.c

## Earlier ping-only checkpoint

**USB/access PASS; expected ROS 2 board response NOT CONFIRMED. Motion NOT TESTED.**

User authorized stationary readiness checks and confirmed wall-adapter power. No battery swap, power cycle, firmware upload, LiDAR/ROS node, calibration, heartbeat, torque-enable or velocity command was performed.

## Evidence

- SSH succeeds. Humble and the five built package folders/executables remain. Installed original COIN-D4 checkout is clean at `8277b288902f28b37948b42e1bb80ba59afbba60`; the PC patch is not deployed. Driver download is not the current blocker.
- User belongs to `dialout`; `/dev/ttyACM0` has group read/write permission. Fixed ROBOTIS OpenCR by-id path resolves there. CP2102 on `/dev/ttyUSB0` was not opened.
- User-level `fuser` showed no visible owner before/after; visibility of privileged processes is not guaranteed.
- Installed node source writes IMU calibration during initialization and heartbeat later, so that node was not run. Base and LiDAR are separate processes, although default launch starts both.
- Bounded C++ helper uses installed manufacturer SDK 4.0.3 with configured protocol 2.0 / ID 200 / 1000000 baud. Fixed target, cooperative lock, saved terminal/modem settings, only PING/READ calls, no register-write/reboot commands. Existing ARM64 g++ optimized warning-as-error compile passed; `ldd` resolves all libraries.
- One execution with 10-second outer timeout returned promptly:

```text
PING id=200 comm=-3001 error=0 model=0 message=[TxRxResult] There is no status packet!
RESTORE termios=0 modem=0 modem_saved=1
```

Conditional register reads were NOT EXECUTED after failed ping. Model zero is an initialized fallback, not a detected model. Firmware/voltage/torque/wheel state UNKNOWN. Restore syscalls succeeded; no independent byte-for-byte terminal comparison. Final USB paths persisted and process query matched only its own inspection shell, not a target driver.

Source: `C:\Users\jaewo\Documents\Codex\2026-09-12\dl\opencr_readonly_check.cpp`.
SHA-256: `cd387ceaa7c1fc8e1913bfcc007ab9d1b3e5dbca833c54c3db5b86d7983a5100`.
Robot temporary executable: `/tmp/twinpulse-opencr-readonly.s1xmQj/check`; retained, not a service/driver, no automatic rerun.

## Limits / next step

No reply does not establish hardware damage, insufficient adapter power, incorrect firmware or a LiDAR-caused wheel failure. One ping is not exhaustive diagnosis. Identify supplied OpenCR firmware/runtime state before deciding on updates; firmware upload and physical motion need separate approval.

Official model-specific ROS 2 firmware guidance: https://emanual.robotis.com/docs/en/platform/turtlebot3/opencr_setup/ . Its push-button tests cause motion and are not part of this check. Do not ask the tethered user to press them. Keep adapter power for stationary investigation; no battery swap needed. Wheel rotation/stop, odometry, ROS scan, teleoperation and navigation remain unverified.
