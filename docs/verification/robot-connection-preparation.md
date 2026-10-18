# Robot connection preparation — 2026-09-26

## User scope

The user is assembling the supplied TurtleBot3 Burger RPi4 kit and does not know its OS/ROS state. Prepare the software so the next physical session can start with a robot connection check. Do not wait for a site photo, request room measurements as a prerequisite, or claim an assembled/running robot.

## Verified locally

- Existing PC environment: Ubuntu-22.04 WSL2, Ubuntu 22.04.5; no `/opt/ros` installation or ROS command found. Started that existing distro for read-only inventory only; no OS/ROS/WSL/firewall installation or configuration change.
- Official ROBOTIS source downloaded at commit `90a68bd2e3c61c12966779da89d8eeaec82730e9`. Description 2.3.7 / Apache-2.0; source/license retained under ignored `artifacts/robot-models/`. Asset preparer records source URDF and mesh SHA-256, rejects a different revision or edited checkout. It resolves only the known empty-namespace xacro declarations, not arbitrary xacro code.
- Actual isolated Isaac 6.0.1 import: **IMPORT_STRUCTURE_PASS**, four visual meshes and both wheel revolute joints. Actual viewport image captured. First harness run missed instance-proxy meshes and reported FAIL; second used USD instance traversal and passed. The importer warned about missing actuator gain values; no motion tuning or physics Run was claimed.
- Connection diagnostic tests: **9/9 PASS** (host/argument validation, bounded timeout, authentication failure, report safety, no publisher/service client, namespace ambiguity and secret-limited inventory).
- Core: **53/53 PASS**, including photo review without manual measurements. Legacy `ready_for_alignment_review` remains a compatibility alias for the optional manual-evidence route, not a blocker for initial photo creation, connection, or sensor collection.
- Ran the actual probe in local WSL: correctly reported `ROS_PYTHON_UNAVAILABLE`, Ubuntu 22.04.5/x86_64 and no serial devices. This is a **local negative check**, not a Pi/SSH/physical sensor PASS.
- Also ran the exact generated LF shell payload via Windows binary stdin into WSL bash, parsed its real output and generated `artifacts/robot-checks/local-wsl-37cfc9df/report.html`. This covers shell transport/JSON/report rendering without claiming an SSH connection. PowerShell launcher parsed without errors; Windows OpenSSH executable is present.

## What is usable next

`Check-Robot-Connection.cmd` invokes the repository Python diagnostic, asks for the Pi's host and username, leaves SSH authentication to OpenSSH, and writes a per-run HTML/JSON report. The payload performs only inventory and bounded sensor subscriptions; never bringup, motor publish, installation or firmware actions. On an approved key connection, the assistant can run the same tool in batch mode. No manual screenshot relay is needed for its reports.

## Remaining blockers and limits

- Physical assembly, bootable microSD, OS/ROS state, actual LiDAR revision, IP/login and hardware safety are unknown. No robot host was guessed or contacted.
- Windows local SSH→Pi path has not been tested end-to-end; tests use a fake transport. An actual SSH session needs the assembled powered robot, network and approved credentials/trusted host identity.
- Default ROS domain 30 must match the device; not auto-detected. ROS environment in a custom workspace requires follow-up. Received messages alone do not establish freshness, correct TF or physical origin.
- Burger source is a nominal model, not a validated TwinPulse robot profile. No simulated wheel motion, sensor emulation, real motion, scan alignment, navigation or route comparison was performed. H3c/B0-B2 overall remain PARTIAL.
- No photo, paid LLM call, real robot action, commit or push. Runtime generated assets are not included in offline release yet.

See [operator instructions](../ROBOT_CONNECTION.md). The next physical session starts with **boot/network/inventory**, not a photo/measurement gate.
