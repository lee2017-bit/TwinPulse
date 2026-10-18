# Connect your TurtleBot3 Burger — first read-only check

## Manual check window (2026-09-27 19:20)

Double-click `Open-Robot-Console.cmd` for the lightweight App without Isaac.
Use **1. PC 사전준비** while charging; once the robot is ready, repeat PC preparation,
confirm the read-only check and click **2. 로봇 연결·묶음 점검**. No automatic deployment,
driver start or movement. The new UI is verified with synthetic transport, not yet
against the physical robot. [Complete scope and evidence](verification/robot-console-20260927.md).
The voltages below are historical observations, not today's charging status.

## Consolidated health check for the configured TwinPulse Burger

**Latest12:14KST:** bounded sensor-only8s recording completed, one STOP followed by
serial silence, restored settings and released ports. 74 complete actual scans are
saved for PC-only review. No wheel commands; torque0/encoders unchanged,11.69V
(voltage-estimated66.1%). Physical rotor stop still awaits operator observation.
ROS scan/TF/axis alignment and the integrated demo remain unverified.
[Evidence](verification/robot-lidar-recording-20260927.md).

**Latest12:02KST:** approved actual stationary lifecycle PASS:20s/318 status
samples, disarmed guard, normal exit0 and independent torque0/speed0/commands0.
11.82V/voltage-estimated73.3%. No lidar or movement was run.
[Evidence](verification/robot-stationary-live-20260927.md).

**Latest 11:56 KST:** torque-OFF correction and permanent preparation integration
completed. Explicit approved OFF command plus independent read confirmed torque0,
speed/commands0; SOFTWARE_PREPARED_IDLE,11.87V/voltage-estimated76.1%.
For an actually confirmed supported floor, `Prepare-Robot.cmd --disable-torque
--operator-confirmed-flat-clear-floor` packages/caches, performs OFF-only maintenance
and records a final independent read. Plain prepare stays read-only after build.
No driver/drive is started, and this is not full demo or stopping qualification.
[Latest evidence](verification/robot-torque-off-correction-20260927.md).

**Earlier 11:38 KST:** an explicitly approved one-shot torque-OFF attempt aborted
before writing because a preflight encoder changed by one tick. Torque remains ON,
sampled speed/commands zero,12.15V. Do not automatically retry or start stationary
mode. [Current evidence and limits](verification/robot-torque-off-20260927.md).

**D1 first deployment and ARM64 READ-helper build completed at 11:20 KST on
September 27. Readings showed 12.35V, estimated100%, zero speed/commands, but the
board torque flag was true. PREPARED_NEEDS_ATTENTION remains; no drivers or motors
were started by this operation.** [Latest evidence](verification/robot-first-deployment-20260927.md).
`Prepare-Robot.cmd` implements one-command permanent deployment plus an idle
snapshot; first deployment succeeded but disabled-idle qualification did not. It installs no system component,
starts no driver and allows no motion. See [D1 status](verification/robot-package-d1-20260927.md).

Explicit `Check-Robot-Stationary.cmd` now implements disarmed base observation
and final idle confirmation. The ordinary lifecycle passed once on the actual Pi;
failure-injection/reboot qualification remains incomplete. Prepare never starts it automatically.
`Prepare-Robot.cmd --mode offline` creates the bundle/report without SSH.
See [charging-time preparation](verification/robot-charging-offline-prep-20260927.md).

After that deployment is verified, check with one command from the repository root:

```powershell
.\.venv\Scripts\python.exe scripts/check_robot_connection.py --profile twinpulse-burger --ros-distro humble --identity-file C:\Users\jaewo\.ssh\twinpulse-burger\id_ed25519_automation --batch --board-snapshot
```

This profile defaults to the last verified host192.168.35.139/user twinpulse/domain86;
use `--host` if DHCP changes. SSH reads the existing key; the report contains no key
material. The generic checker below remains available for other robots.

The report combines system/boot/USB/process/guard artifact checks and optional
board voltage, estimated charge, torque, velocity and command state. It also
observes sensor streams and guard status when their drivers are already running.
It does not start drivers or move the robot. A stopped driver can produce
`NO_SENSOR_DATA` while the board's idle snapshot is good; both are shown separately.

The new checker requires the permanent release manifest; it does not fall back
to the earlier temporary helper. Missing/changed releases show UNKNOWN; an
occupied managed-operation lease or serial port shows BUSY. A past battery value
is never substituted. Managed READ ownership is implemented and tested without
devices; base lifecycle ownership now has code and fake-process tests, while live
deployment/qualification remain pending. Full TF, physical stop qualification, LiDAR rotation-stop and navigation
remain unfinished.

Latest [review and integration plan](planning/TWINPULSE_ROBOT_REVIEW_2026-09-27.md)
and [current state](planning/TWINPULSE_ROBOT_CURRENT_STATE.md) supersede the initial
setup assumptions below. Reports are in `artifacts/robot-checks/`.

No site photo or room measurement is required for this check. Finish assembly first. Do not power a partly wired robot just to satisfy a software test.

## What is ready

- Windows entry point: **Check-Robot-Connection.cmd** at the repository root.
- It connects only to the host you enter, over SSH. No ROS installation is required on the Windows PC for this diagnostic.
- It reports the Pi's OS, installed ROS directories, serial-device count, and (when ROS is usable and drivers are already running) a short `/scan` and `/odom` observation. Topic discovery can find a single namespaced sensor; ambiguous multiple sensors are not silently selected.
- It never installs software, flashes the SD card/OpenCR, starts robot bringup, sends a motor command, or changes the firewall. No application publisher or ROS service client exists in the probe.
- Reports are saved under `artifacts/robot-checks/<run-id>/report.json` and `report.html`. A sensor-message result is not proof of real hardware, correct time/TF, safe stopping, or permission to move.

## After assembly

1. Follow the manufacturer's power/wiring checks. Keep physical power-off accessible and do not run teleop or navigation yet.
2. Boot the supplied microSD **without overwriting it**. We do not know whether it contains an OS, ROS, or network settings. If there is no usable boot/login/network, stop here and inspect the card with a display or an approved setup path; flashing requires an explicit backup/installation decision.
3. Connect the Pi and PC to an approved local network. Find the Pi's IP from its console or the router's device list. The diagnostic does not scan the network.
4. Double-click **Check-Robot-Connection.cmd**. Enter that IP and the Linux username you configured/found on the Pi. Do not assume a factory username/password. SSH handles any password prompt; never paste a password into chat or save it in project files.
5. On first connection verify the host fingerprint against the Pi before accepting it. Changed host keys are not automatically bypassed. The report opens after the bounded check.

For an already approved SSH key connection, the assistant can run:

```powershell
.\.venv\Scripts\python.exe scripts\check_robot_connection.py --host <robot-ip> --user <linux-user> --batch --open-report
```

The ROS diagnostic defaults to domain **30**, the ROBOTIS example. It is **not auto-detected**. If bringup uses another domain, pass `--domain-id N`. `--ros-distro humble` or `--ros-distro jazzy` selects a known `/opt/ros/.../setup.bash`; automatic mode sources only when exactly one of those two exists. Custom workspace-only ROS installations need explicit follow-up setup and are not silently sourced.

| Result | Meaning / next action |
| --- | --- |
| SSH_OR_REMOTE_SETUP_FAILED | Check power, IP, SSH service/login, host fingerprint, Python and shell. This is not a robot motion failure. |
| ROS_PYTHON_UNAVAILABLE | Inventory succeeded but rclpy/sensor packages are unavailable in the selected environment. Inspect OS and choose matching ROS installation before changing anything. |
| NO_SENSOR_DATA | No samples observed. Check whether bringup is running, domain/RMW, sensor devices and topic namespace; do not start motors to test connectivity. |
| PARTIAL_SENSOR_DATA | Only some requested sensor streams arrived. Inspect the missing stream. |
| SENSOR_MESSAGES_RECEIVED | Both scan and odometry messages arrived. Still check physical source, valid ranges, timestamp ages, TF and command publishers. Not a safety PASS. |
| CONNECTION_CHECK_TIMEOUT / CHECK_FAILED | Bounded failure; no retry or fallback to motor actions. |

Starting bringup, verifying sensor-frame correctness, manual-motion/stop tests and scan-to-Twin alignment follow the real device inventory and field approval. They are not automated by this checker.

## Model preparation — independent of physical assembly

An official nominal Burger model is staged from ROBOTIS commit `90a68bd2e3c61c12966779da89d8eeaec82730e9` (description package 2.3.7, Apache-2.0). This does not choose the Pi's ROS version. The installed LiDAR/board revision still needs matching against the physical kit.

```powershell
.\.venv\Scripts\python.exe scripts\prepare_turtlebot_model.py --fetch
C:\isaacsim\python.bat scripts\verify_turtlebot_import.py
```

The preparer preserves the official source and license, pins its commit and hashes meshes, and only resolves the audited empty namespace. The second command starts a **separate headless Isaac process**, imports the model, checks wheel joints/meshes and captures it. It does not open or replace the user's current stage. Generated outputs are under `artifacts/robot-models/`; check `burger-isaac/verification.json`, not just the process exit code. Artifacts are local/ignored by Git; another machine must run the preparer or receive a reviewed asset bundle. This is not yet integrated into the one-click offline release or validated as a physical RobotProfile.

## Sources

- [ROBOTIS SBC setup](https://emanual.robotis.com/docs/en/platform/turtlebot3/sbc_setup/)
- [ROBOTIS bringup and ROS domain](https://emanual.robotis.com/docs/en/platform/turtlebot3/bringup/)
- [NVIDIA TurtleBot URDF import](https://docs.isaacsim.omniverse.nvidia.com/6.0.0/ros2_tutorials/tutorial_ros2_turtlebot.html)
