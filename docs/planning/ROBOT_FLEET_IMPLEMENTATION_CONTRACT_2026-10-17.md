# Robot fleet implementation contract 1.0

Approved implementation: multi-robot/continuous-control plan plus chat control. Physical robot is powered off; hardware acceptance is NOT_RUN. Additional Nebius test allowance is USD50 beyond the existing USD20 campaign, separately accounted with prior usage and uncertainty preserved.

## Ownership

Main: Python application/robot contracts, API routing, conversation routing, Isaac fleet runtime and viewport transport, integration tests/build/actual App+Isaac acceptance, evidence and budget.

UI helper: new robot-fleet-types.ts / RobotFleet.tsx / RobotFleet.test.tsx, TwinViewport.tsx and viewport-types.ts, ChatWorkspace.tsx, api.ts fleet methods, styles.css fleet styles. Ownership was explicitly extended to PhysicalRobotController.tsx/tests for its input lifecycle, then to bounded logs, badge collision layout and stop confirmation display. No Python, Isaac, launch or paid calls by the helper; only supplementary UI tests. Astra owned new physical_fleet_adapter.py/tests, independent saved decoder candidate/harness, then manual_motion_guard.py/tests only. Main integrated shared API/workspace and owns all actual runtime/installation/paid acceptance.

Final scoped transfers: Astra additionally owned teleop_worker.py + test_continuous_worker_recovery.py for the enabled-but-inactive late pre-arm nonce fix, then physical_fleet_adapter.py/tests for authenticated cold history and explicit reconnect. Those files were frozen and returned before build05. Main alone changed RobotFleet/FleetRecorder/PhysicalController integration. The UI helper performed a read-only concurrency review, no overlapping edits. No helper launched Isaac, installed a package, called a paid provider, or contacted hardware.

## Product API

GET `/v1/product/robot-fleet`: `RobotFleetState`.

POST same URL: exact envelope `{action,request_id,robot_id,connection_epoch,motion_epoch,payload}`. UUID request_id; nullable robot_id/epochs when creating/selecting. Mutations are idempotent per request and reject different content reused with same ID.

Actions:
- `register_sim`: payload `{label,position_m:[x,y,yaw]}`. Real Isaac kinematic SIM robot, explicitly simulated telemetry; no physical transport.
- `focus`: robot_id, payload `{}`. Stops previous manual intent but retains connections.
- `connect`, `disconnect`, `prepare`: robot_id, payload `{}`. Fresh engine/sensor status is required for SIM green; physical follows declared capabilities.
- `drive`: robot_id+current connection_epoch/motion_epoch, payload `{direction:'forward'|'backward'|'left'|'right',sequence:int,expires_at_ms:number}`. Hold messages sent every100ms; expires250ms initially. No queued old commands. Stop supersedes held/late requests.
- `stop`: robot_id; payload `{}`. Does not require current motion_epoch (stopping is always accepted for owned session), rotates motion_epoch.
- `stop_all`: robot_id null, payload `{}`.
- `lidar`: robot_id+connection_epoch, payload `{enabled:boolean}`. Off stops movement, keeps connection.
- `command`: robot_id nullable, payload `{text:string}`. Bounded distance/angle/turn-and-scan actions, same control/recording path. No indefinite motion from chat. Stop lexical fast-path.

State:
```
{schema_version:'robot-fleet-1.0',revision:number,focused_robot_id:string|null,
 robots:RobotFleetRobot[],last_command:{request_id,operation_id,robot_id,status,message}|null,
 capabilities:{sim:boolean,physical:boolean}, policy:{linear_m_s:number,angular_rad_s:number,input_expiry_ms:number}}
```
Robot:
```
{robot_id,label,kind:'sim'|'physical',connection_state:'DISCONNECTED'|'CONNECTING'|'CONNECTED'|'DEGRADED',
 connection_epoch:string|null,motion_epoch:string|null,
 control_state:'UNPREPARED'|'ARMING'|'READY'|'DRIVING'|'PAUSED'|'FAULT',
 lidar_state:'OFF'|'STARTING'|'STREAMING'|'STOPPING'|'FAULT',
 recording_state:string,operation_id:string|null,reason:string|null,
 battery:{voltage_v:number|null,percent:number|null,source:'simulated'|'measured'|'unknown',age_ms:number|null},
 pose:{position_m:[x,y,yaw],frame_id:string,source:string,aligned:boolean}|null,
 telemetry_age_ms:number|null,telemetry_sequence:number,
 capabilities:{drive:boolean,lidar:boolean},scan:{points:[number,number][],source:string}|null}
```
Backward-compatible optional fields: `last_operation_id` is historical evidence only; `applied_motion_epoch` is the engine-observed epoch. `motion_epoch` is desired control generation. PAUSED at request acceptance does not prove engine stop: confirmation requires a fresh report with matching applied/desired epochs. UI shows the distinction; no arbitrary settling sleep is treated as an ACK.

Never use last historical battery/connection as current. Kind/source remain visible. SIM is kinematic Isaac validation, not a PhysX differential-drive qualification. Unsupported/disabled physical actions return precise unavailability; never substitute SIM for physical.

GET `/v1/product/robot-fleet/operations/<operation_id>` returns `{schema_version:'robot-operation-1.0',operation_id,robot_id,project_id,events:[...],manifest:{...}}`, original command/engine measurements, source pins and completeness. UI can show JSON/details/download in the drawer.

## Twin view integration

`ViewportFrame.robot_anchors?: {robot_id,screen_anchor_uv:[number,number],screen_bounds_uv:[number,number,number,number],visible:boolean}[]`.
Anchors are captured on Isaac update alongside frame metadata. The containing frame binds engine_session_id, stage_epoch, revision, frame_id and camera_sequence. No stale preview click claims current geometry. Fixed robot list remains available if pose/anchor unaligned/missing.

TwinViewport optional props `robotFleet?:RobotFleetState`, `onRobotSelect?:(id:string)=>void`. Anchor badge below model displays green only fresh CONNECTED heartbeat, label/battery source. DOM overlay reuses rendered image fit/letterboxing. RobotFleet mounts in Twin pane and has an always-visible compact fleet list, register-SIM form, selected drawer, joystick/keyboard hold, Stop, LiDAR, text command, operation log. ChatWorkspace also supplies anchors/select handler and routes ordinary conversation commands through backend ConversationService.

## Isaac exchange

Authenticated POST `/v1/engine/robots` uses same engine identity and project broker epoch:
`{engine_session_id,stage_epoch,report:{applied_revision,robots:[...]}}` -> `{fleet:{project_id,applied_revision,robots:[desired...]}}`.
No arbitrary source execution. Main runtime only owns `/World/TwinPulse/Fleet`. Per-robot finite input deadline and motion_epoch preserved. Pose/near-obstacle simulated measurements come from actual USD state; no fixed successful response. Stage/revision change pauses and invalidates movement. Local update and data exchange remain distinct from display frame freshness.

On a new engine/stage/revision binding or explicit reconnect, rotate connection epoch, discard old task/input, reset telemetry sequence and require a fresh matching engine report. The old operation's delayed finalizer captures its immutable operation ID/recorder and cannot finalize a new connection. Stop and engine exchange do not hold the fleet lock while another physical service closes or an atomic snapshot is written/serialized. Append-only journal admission and close receipts share a recorder lock; join occurs outside it. Historical physical operation references restore no connection/drive authority; the reader checks the current authenticated project session and registered immutable binding before bounded JSONL/footer verification.
