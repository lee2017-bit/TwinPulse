# Passive odom rejection diagnostics — 2026-09-30

Scope: offline follow-up after the supervised Burger session in [robot-live-session-20260930.md](robot-live-session-20260930.md). The robot was reported powered OFF before this work. No SSH, ROS runtime, motor, LiDAR, deployment, Isaac, or autonomous mission was run.

## New evidence and implementation

- The operator supplied a photo and said it shows the room used in the preceding test. Its SHA-256 is `456c9f3e8d87fda9adb4de47bbf7ac61d048b72f105dd525c9c5c7659eb161a0`. The robot is on visible floor between the bed and the opposite furniture; bags and a floor cable are also visible. This is a scene-context photo, **not** a metric map, current obstacle-clearance reading, pose, TF, or evidence that the room stayed unchanged during all commands. The earlier operator's local 30 cm clearance report remains a separate time-specific observation.
- The saved live navigation snapshots say `odom: INVALID_MESSAGE`, but the original raw Odometry message was not captured. They cannot reveal which field failed. Existing command/encoder and final idle evidence remain valid only within their recorded scope; no robot-frame trajectory is inferred.
- `RosObservations.receive` now emits bounded cause codes for rejected fields: `STAMP_FORMAT`, `FRAME_ID`, `ODOM_POSITION`, `ODOM_ORIENTATION`, `SCAN_GEOMETRY`, `SCAN_RANGES`, or `MESSAGE_SHAPE`. Endpoint, source-time, clock and stale faults retain their existing codes. No raw invalid field value, pose, credential, or new authority is added to the strict `passive-ros-observation-1.0` snapshot shape. Invalid observations are still cleared and cannot become navigation input. Existing journal bytes and their hashes are not rewritten; prior `INVALID_MESSAGE` stays as recorded.
- A fake rejected odom snapshot passed through the existing strict robot event/session review path with its fault code preserved, `odom=null`, `floor_pose_measured=false`, and `motion_authorized=false`.

## Offline checks

- `.venv\Scripts\python.exe -m unittest discover -s packages/twinpulse_core/tests -q`: **180 PASS**.
- `.venv\Scripts\python.exe -m unittest packages.twinpulse_core.tests.test_ros_observations tests.integration.test_physical_controller -q`: **68 PASS**. This includes the added strict journal round-trip case.
- An initial system-Python integration attempt lacked Pillow. Two subsequent sandboxed Windows integration attempts failed because test-created temporary directories were not writable. The same local tests passed using the existing project venv with approved execution permissions; no dependency was installed and the failures are not counted as product regressions.

## Still required

On a separately approved future, supervised, non-autonomous session, collect a new passive snapshot with this version and check the actual fault code. If needed, capture a bounded raw Odometry message in the same boot/namespace without enabling movement. Only then fix or document the specific producer/contract mismatch and re-run the strict tests. A reason code is diagnostic, not a valid pose or an authorization to drive. Room-to-odom registration, live obstacle clearance, chassis stop distance, and the physical TwinPulse demo remain unverified/locked.
