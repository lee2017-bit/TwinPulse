# Physical fleet integration contract 2.0 — implementation in progress

This supplements, not replaces, the 2026-10-17 fleet contract. The robot is OFF/charging. No hardware connection, deployment, motor/sensor activation or new dependencies are authorized by this implementation test. Hardware acceptance remains NOT_RUN until an actual supervised session. Software stubs are not hardware NOT_RUN.

## Ownership

- Main: physical_live_session.py, PhysicalFleetAdapter, RobotFleet, PhysicalController lifecycle, API/workspace/conversation Stop admission, packaging/source bundle, integration/installed acceptance/report.
- Astra ultra review/implementation: robot-local fleet_worker.py/native_stream.py, teleop_ros.py/teleop_worker.py, pure manual guard and their supplementary tests. It first audited read-only; its UI/packaging audit helper returns before a replacement UI helper starts. Maximum two helpers active, no shared file edits.
- UI helper (after audit helper returns): RobotFleet/types/tests and new preparation/profile UI only, no Python/robot/build/paid calls.

## Lifetimes and authority

Explicit Connect starts one authenticated, binding/operation/project/connection-epoch-pinned persistent SSH session. It starts no motors or sensor. Heartbeat freshness, measured battery freshness, native sensor freshness, control readiness and recording completeness are independent. SSH reconnect never replays movement or restores authority. No green from saved one-shot diagnostics. Snapshot never starts transport.

LiDAR On/Off uses the native serial stream; nonuniform native angles remain native. No fabricated uniform LaserScan, TF, room pose, battery percentage, beam acquisition timestamps or measured profile. Off/Stop invalidates movement but retains the authenticated session. Input expiry/gesture release pauses movement; explicit Disconnect ends the session. Storage/protocol saturation must stop movement and surface incomplete evidence, not silently discard it.

Prepare/qualification are explicit app actions, not URL flags. Existing same-boot/release stop qualification and robot-local watchdog/ownership remain authoritative. Protective drive requires verified local geometry/timing/stopping profile references. Missing measurements are specific setup blockers with a UI import/review path, not a generic unimplemented adapter. Body motion independent of wheels is UNKNOWN when no independent source exists; wheel odometry is never relabelled body proof. Real measurements cannot be invented while the robot is OFF.

## Reviewed session protocol

PC launches only a fixed reviewed bootstrap through strict host-key SSH. Sources are selected from shipped robot/core files, SHA-bound, bounded, cached in a versioned user directory; the selected robot/current release is not overwritten. No third-party install, model code or arbitrary user shell. The robot verifies the existing release before any board action.

PC command: `{schema:'physical-live-command-1.0',operation_id,robot_id,project_id,connection_epoch,motion_epoch,request_id,sequence,action,payload}`. Actions: lidar/prepare/qualify/drive/task/stop/close/profile. Original UI input expiry is not renewed by transport. All commands include immutable operation/robot/project IDs. Stop bypasses pending project edits/shutdown and cannot target a SIM instead of a live physical operation.

Robot event: `{schema:'physical-live-event-1.0',operation_id,robot_id,project_id,connection_epoch,sequence,kind,robot_monotonic_s,data}`. Kinds heartbeat/scan/raw/raw_source/command/cleanup/fault. Strict increasing sequence and matching identity required before publishing telemetry. Command ACK is not completed motion; cleanup ACK is not inferred from process exit. Full raw native bytes/chunk timing and command lineage must be exportable under the operation ID, with bounded segmented recordings and explicit missing receipts. Old results cannot replace a new session. `raw_source` exports only fixed helper/qualification members in 16KiB chunks, 256KiB/member, 1MiB/session; exact offsets and hashes distinguish full bytes from truncated tails. Truncation or read failure makes recording incomplete.

Optional public robot fields: `setup:{runtime_state,blockers,profile,qualification}`, `live_heartbeat`, `telemetry_age_ms`, `battery.age_ms`, `control_state`, `controller_state`, `cleanup_confirmed`, `sensor_frame`, `capabilities:{read_only_connection,prepare,qualify,profile,drive,lidar}`. Existing SIM schema and API envelope remain valid. `prepare`, `qualify`, `profile` accept explicit payloads only; physical drive receives direction/extent/sequence/expiry/epochs/request ID rather than dropping them.

## Acceptance separation

1. Offline real saved native data + protocol/expiry/fault/cleanup tests: supplementary, never hardware PASS.
2. Same installed Electron Test BrowserWindow: visible New chat, existing real generated scene/Isaac, SIM regression, physical drawer/setup/missing-prerequisite/status/history; no direct product mutation replacing clicks.
3. Ordinary installed Start debug-off and normal shutdown/restart, native input limitations separately NOT_RUN.
4. Robot OFF: actual SSH authentication, new boot qualification, measured profile, sensor On/Off, wheels/obstacle stop/continuous 360 and long-session resource behavior are NOT_RUN. A complete software path is not a guarantee of those outcomes.

No paid model call is needed merely to test deterministic connection, native sensor and Stop wiring. Prior costs/unknowns stay unchanged unless an actual paid call occurs.

## Reviewed supervised scope

A profile must explicitly choose `independent_required` or `explicitly_unverified_supervised`. The latter permits measured wheel-stall monitoring plus native clearance protection while reporting independent chassis progress UNKNOWN; it is not slip/body-progress qualification. No choice or measured values are generated by the App. Native timing uses a measured conservative pipeline bound and a receipt interval, never an exact beam clock invented from host receipt. `watch` carries only presence/challenge/generation, never refreshes a held manual direction. Finite task authority remains bounded and is discarded on a presence gap; Stop accepts sequence gaps caused by discarded queued movement. Metadata/archives redact challenges while preserving native bytes, per-chunk timing, commands, source hashes and receipts.
