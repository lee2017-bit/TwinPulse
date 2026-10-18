# Physical robot first boot and ROS installation — 2026-09-26

## Scope and verified state

**Subsequent operator clarification / offline review:** The user later said the scanner stopped; do not infer shutdown or adapter removal. Current power state is unconfirmed and no power change is needed for PC tests. A PC-only parser patch and 222738-assertion synthetic ASan/UBSan regression passed; [details and limits](coin-d4-offline-parser-review-20260926.md). No patch was deployed to the Pi, no further device access occurred, and software-controlled physical stop remains unresolved. The pending observations below describe earlier checkpoints.

**Operator correction after the 19:54 probe: scanner STILL ROTATING.** The user directly reports continuing rotation. The prior 0.5s zero-byte result is only a short communication observation, not proof of physical stop. The official driver's deactivation path was reread: it sends the same `end_lidar` byte sequence already tried. No new device command was sent on this follow-up; do not guess alternate byte sequences or modem-line states. The test is halted and the user was instructed to run `sudo poweroff` in their authenticated SSH terminal, wait 30s after disconnect, then switch off robot power/disconnect the wall adapter without connecting the battery. Shutdown/power removal and physical stop remain unconfirmed. Resolve the stop behavior before another sensor runtime. No wheel/OpenCR/firmware operation occurred.

**Latest result (19:54 KST): COIN-D4 / LDS-03 family identified; bounded raw protocol check PASS.** User explicitly approved top-sensor-only start testing while tethered to the wall supply. The installed official source at commit `8277b288902f28b37948b42e1bb80ba59afbba60` selects 230400 baud for version 4/M1CT_TOF, clears DTR, and defines start `AA 55 F0 0F` and stop `AA 55 F5 0A`. This differs from the 115200 setting used in the earlier passive attempt. No claim is made that baud alone explains the earlier silence, because both initialization and start signaling also changed.

A bounded diagnostic helper, `C:\Users\jaewo\Documents\Codex\2026-09-12\dl\lidar_bounded_probe.py`, was piped over authenticated SSH to Python's standard-library serial APIs. It fixes the device to the observed CP2102 by-id path and aborts on a different target; uses exclusive access, a 10s receive limit and outer timeout; and sends stop/restores termios and modem lines in cleanup. It does not import or execute the upstream packet parser, ROS, or access OpenCR. One active attempt received 130371 bytes in 10.0s, retaining the first 8192 for bounded host-side examination. The response contains ASCII `COIN-D4`. Applying the pinned protocol's 10-byte header, sample count, three-byte intensity/distance samples and XOR checksum to that sample found 103 valid complete packets and zero invalid candidate checksums. This establishes model/protocol evidence, not calibrated distance accuracy, ROS scan publication or whole-robot acceptance.

Initial stop write succeeded, but 6266 bytes still arrived during the immediate 0.5s check. A **stop-only** retry (no second start) waited 2s, flushed receive buffering, then observed zero bytes over 0.5s. Both runs reported control-line and termios restoration; independent final stty matched the saved initial value and fuser found no port owner. Data silence is not direct visual evidence of physical rotation stop; operator observation was requested. [Structured result](robot-lidar-probe-20260926.json). The LDS-03 compiler warning remains unresolved; no upstream driver/node, OpenCR command, firmware, wheel command, navigation or automatic startup was run. Historical checkpoints follow.

**Latest sensor check (19:45 KST): INCONCLUSIVE.** The user approved a short sensor-only read and stated that the robot remains attached to the wall adapter; no travel or battery switch is needed. USB by-id confirmed CP2102 maps to `/dev/ttyUSB0`; OpenCR `/dev/ttyACM0` was not opened. Two attempts were bounded to 10 seconds and at most 4096 bytes at 115200/8N1 raw, with no application data written to the device. The first used `timeout`/`dd`; the retry held a read-only descriptor open and used `timeout`/`head` to avoid discarding a partial full-block read. Both produced no hex data. Therefore neither packet family nor exact model was identified. Serial opening/configuration may affect modem-control lines; this is not a claim of electrically inert observation.

`stty` reported `unable to perform all requested operations` on restoration. The retry's saved BEFORE and read-back AFTER values matched exactly, including original 9600/canonical settings, and a later independent read-back matched again. Final `fuser` showed no owner; no head/dd/turtlebot3_ros/ld08_driver processes remained. No ROS driver was run, no wheel command sent and no firmware changed. Cause of no data remains unknown (physical rotation, sensor power/wiring and model still need confirmation); do not label the hardware defective or select a model from this negative test. Next ask for a non-contact observation of the top scanner's rotation. A later driver/bringup or movement step needs its own scope approval.

**Latest result (19:24 KST):** The user's reboot completed; SSH returned at 19:13 KST, both USB serial devices remained and `/var/run/reboot-required` cleared. ROS base plus five official-source packages built successfully. Overlay package/executable discovery, Burger launch/config presence, node shared-library resolution (no missing libraries) and clean `dpkg --audit` verified without executing robot nodes. Root free: 9.7GB; sampled post-build temperature 54.5 C. This is installation/static-check acceptance, not sensor/motion acceptance. Earlier checkpoints below are historical.

The apt TurtleBot bringup/node/description packages remain uninstalled because this setup uses the official source overlay below. Installed hls covers LDS-01; staged ld08 and coin_d4 cover LDS-02/03 respectively, but do not establish which physical sensor is present. Select only the confirmed model before authorized bringup. No OpenCR firmware, robot node, motion or automatic boot service was run/added.

## Post-reboot source build

New workspace: `/home/twinpulse/turtlebot3_ws` (did not exist before this step). Official build files were inspected; upstream source was not patched.

| Repository | Branch | Pinned commit |
| --- | --- | --- |
| ROBOTIS-GIT/turtlebot3 | humble | `90a68bd2e3c61c12966779da89d8eeaec82730e9` |
| ROBOTIS-GIT/ld08_driver | humble | `4c528699904cc5e3bd4a6b82963595c7365d7243` |
| ROBOTIS-GIT/coin_d4_driver | main | `8277b288902f28b37948b42e1bb80ba59afbba60` |

After sourcing `/opt/ros/humble/setup.sh`, the completed command was:

```bash
cd /home/twinpulse/turtlebot3_ws
env CMAKE_BUILD_PARALLEL_LEVEL=1 MAKEFLAGS=-j1 \
  colcon build --symlink-install --executor sequential \
  --packages-select turtlebot3_description turtlebot3_node turtlebot3_bringup ld08_driver coin_d4_driver \
  --cmake-args -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF
```

Result: `5 packages finished [8min 28s]`, exit 0; one package (`coin_d4_driver`) emitted stderr. Unit tests were disabled, not passed. Build logs are under `~/turtlebot3_ws/log/latest_build/`. Post-build checks sourced `~/turtlebot3_ws/install/setup.sh` only in the check session. All five package prefixes were found; node/driver executables were enumerated, not executed. No `.bashrc`, `LDS_MODEL`, ROS domain, udev rules or automatic startup changes. Optional navigation/cartographer/example/teleop packages were not built; RViz-dependent desktop launch paths are not claimed ready.

**Pre-runtime gate:** `coin_d4_driver/src/lidar_sdk/lidar_data_processor.cpp:371` produced GCC `-Wstringop-overflow` for `package_buffer[recv_pos++]`. The pointer is derived from the two-byte `package_Head` member of a larger packed packet structure. Compilation success does not prove runtime safety; neither a confirmed exploitable overflow nor a harmless false positive is established. Review the packet bounds before running LDS-03 code. Actual LiDAR model, OpenCR firmware compatibility, scan/odom reception, motor safety and Isaac integration remain unverified. User was asked for the visible LDS model label without disassembly.

The user approved Ubuntu SD provisioning, dedicated SSH authentication and ROS 2 Humble/TurtleBot software installation. No OpenCR firmware flashing, bringup or motor motion is authorized by this installation step.

- User assembled the Burger and wrote Ubuntu 22.04.5 Server arm64 with Raspberry Pi Imager. First verification failed; a reseat/retry reported success. No further card flashing is needed.
- Actual SSH: `twinpulse@twinpulse-burger`, DHCP address `192.168.35.139` at verification. Ubuntu Jammy arm64; cloud-init done; root approximately 11 GB free; Pi temperature approximately 43–49 C in sampled checks.
- `/dev/ttyACM0`: ROBOTIS / OpenCR Virtual ComPort, USB 0483:5740.
- `/dev/ttyUSB0`: Silicon Labs CP2102, USB 10c4:ea60. Exact LiDAR revision and live data remain unverified.
- Windows key path: `C:\Users\jaewo\.ssh\twinpulse-burger\id_ed25519_automation`. Private material remains outside the repository. Use explicit `-i`, `IdentitiesOnly=yes`, `BatchMode=yes`, `StrictHostKeyChecking=yes`; do not disable host checking. The older encrypted key remains unchanged.
- The user switched to the photographed 12V 5A center-positive adapter. SSH initially refused during startup, then succeeded at about three minutes uptime; `ssh` service active. No repeated power cycle is required based on the initial refusal alone.
- Passwordless sudo is not enabled. The user enters passwords only in their own SSH terminal. An independent assistant session cannot inherit that terminal's sudo authentication.

## In-progress installation (not a completion receipt)

Official ROS repository configuration package downloaded to `/home/twinpulse/ros-setup.F6IlgF/ros2-apt-source.deb`:

- Upstream: https://github.com/ros-infrastructure/ros-apt-source/releases/download/1.3.0/ros2-apt-source_1.3.0.jammy_all.deb
- SHA-256: `110b9a462d55252decb8b7c816f61c2ba0d9890ce5fb93ac504e97cae5860d76`, matched official GitHub release metadata and the robot-side file.
- Package inspected as `ros2-apt-source`, version `1.3.0~jammy`, architecture `all`.
- Ubuntu Universe is already enabled. `dpkg --audit` was empty before installation.

The user started this sequence in their existing SSH terminal:

```bash
sudo dpkg -i /home/twinpulse/ros-setup.F6IlgF/ros2-apt-source.deb &&
sudo apt-get update &&
sudo apt-get install -y --no-remove --only-upgrade systemd udev &&
sudo apt-get install -y --no-remove \
  ros-humble-ros-base ros-humble-turtlebot3-msgs \
  ros-humble-dynamixel-sdk ros-humble-hls-lfcd-lds-driver \
  ros-humble-xacro python3-argcomplete python3-colcon-common-extensions \
  libboost-system-dev libudev-dev build-essential git
```

At the current checkpoint, repository package installation succeeded, systemd/udev 249.11-0ubuntu3.22 were configured and initramfs/Ubuntu Pi boot-file triggers finished. These OS package triggers are not OpenCR firmware flashing. `needrestart` is waiting in a `whiptail` dialog titled `Daemons using outdated libraries` / `Which services should be restarted?`. Its observed defaults include `netplan-wpa-wlan0.service` and `ssh.service` selected. The operator was advised to deselect these two to avoid interrupting Wi-Fi/SSH during the remaining install, leave other defaults unchanged and confirm. Their deferred restarts need an orderly reboot after installation finishes, not during apt. ROS package completion has not yet been verified.

## Resume and acceptance

### 19:02 KST checkpoint

The first dialog was cleared by the user. The five requested ROS packages now show `ii` (installed/configured): ros-base 0.10.0, turtlebot3-msgs 2.4.0, dynamixel-sdk 4.0.3, hls-lfcd-lds-driver 2.1.1 and xacro 2.1.1. `dpkg --audit` is clean; `ros2 --help`, rclpy/turtlebot3_msgs prefix discovery and driver executable enumeration passed. No driver/node was executed. Root free space: 9.7 GB. The hls driver is for LDS-01; its presence does not identify the actual kit LiDAR.

**apt has not exited:** a second needrestart dialog is awaiting input. Its observed defaults additionally select `systemd-networkd.service` and `systemd-resolved.service`. Deselect those two plus `netplan-wpa-wlan0.service` and `ssh.service` to defer network/SSH restarts during installation; keep other defaults and confirm. Full TurtleBot setup, apt exit and post-install reboot remain pending.

1. Read process state and `/var/log/dpkg.log` / `/var/log/apt/term.log`; do not run a second package manager, kill locks, reboot during installation or assume an idle-looking terminal means failure.
2. If a dialog requires input, inspect the actual user screenshot; do not guess selections.
3. After apt exits, check `dpkg --audit`, exact package status, source `/opt/ros/humble/setup.bash`, and test imports/CLI without starting robot nodes.
4. TurtleBot workspace/bringup packages and the physical LiDAR driver may need additional reviewed installation. This package list alone is not the complete robot setup.
5. No full robot acceptance, sensor PASS, motor safety, Isaac integration or motion claim follows from successful ROS installation. Stop before firmware/bringup/motion without corresponding authorization.

Sources: [ROS Humble Debian installation](https://docs.ros.org/en/humble/Installation/Ubuntu-Install-Debs.html), [ROBOTIS SBC setup](https://emanual.robotis.com/docs/en/platform/turtlebot3/sbc_setup/), [OpenCR specifications](https://emanual.robotis.com/docs/en/parts/controller/opencr10/).
