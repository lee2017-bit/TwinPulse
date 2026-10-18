// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
export type FleetDirection = 'forward' | 'backward' | 'left' | 'right';
export type RobotTwinContext = {
  schema:'robot-twin-context-1.0';context_id:string;project_id:string;conversation_session_id:string|null;
  scene_revision:string|null;engine_session_id:string|null;stage_epoch:string|null;
  association:'TWIN_REFERENCE'|'NO_CURRENT_TWIN';
  alignment:{frame_id:string;status:'SIM_WORLD'|'UNALIGNED'|'OPERATOR_ESTIMATE_NOT_LOCALIZED';aligned:boolean;anchor:Record<string,unknown>|null};
};
export type FieldTestCase = 'stationary'|'bootstrap_stop'|'forward'|'backward'|'left'|'right'|'full_turn'|'proximity'|'stall'|'presence_gap'|'soak';
export type FieldObservation = 'stopped'|'not_stopped'|'moved'|'not_moved'|'inconclusive';
export type FieldSetupConfig = {
  schema:'supervised-field-test-1.0';robot_id:string;binding_sha256:string;
  footprint_radius_m:number;sensor_x_m:number;sensor_y_m:number;sensor_yaw_rad:number;angle_sign:-1|1;
  wheel_metres_per_tick:number;wheel_separation_m:number;
  provenance:'reference'|'operator_reviewed'|'operator_measured';axes_reviewed:true;
};
export type FieldTrial = {
  trial_id:string;case:FieldTestCase;status:'RUNNING'|'PASS'|'FAIL'|'INCONCLUSIVE'|'CANCELLED';
  reason:string|null;started_s:number;ended_s?:number;result?:Record<string,unknown>|null;
};
export type RobotFieldState = {
  config:FieldSetupConfig|null;config_sha256:string|null;mode:'SUPERVISED_FIELD_TEST';armed:boolean;remaining_s:number;
  blockers:string[];stop_receipt:Record<string,unknown>|null;
  tracking:{status:string;epoch:string|null;pose:unknown;reason:string|null;raw_sha256:string|null;independent:true;accuracy:'UNQUALIFIED'}|null;
  active_trial:FieldTrial|null;trials:FieldTrial[];
};
export type RobotFleetRobot = {
  robot_id:string; label:string; kind:'sim'|'physical';
  connection_state:'DISCONNECTED'|'CONNECTING'|'CONNECTED'|'DEGRADED';
  connection_epoch:string|null; motion_epoch:string|null;
  applied_motion_epoch?:string|null;
  control_state:'UNPREPARED'|'ARMING'|'READY'|'DRIVING'|'PAUSED'|'FAULT';
  lidar_state:'OFF'|'STARTING'|'STREAMING'|'STOPPING'|'FAULT';
  recording_state:string; operation_id:string|null; reason:string|null;
  last_operation_id?:string|null;
  source_twin_context?:RobotTwinContext|null;current_twin_context?:RobotTwinContext;
  twin_context_relation?:string;
  battery:{voltage_v:number|null;percent:number|null;source:'simulated'|'measured'|'unknown';age_ms:number|null};
  pose:{position_m:[number,number,number];frame_id:string;source:string;aligned:boolean}|null;
  display_pose?:{position_m:[number,number,number];source:'operator_estimate_not_localized';scene_revision:string;frame_id:'isaac_world';aligned:false}|null;
  telemetry_age_ms:number|null; telemetry_sequence:number;
  live_heartbeat?:boolean;
  controller_state?:string|null;
  cleanup_confirmed?:boolean|null;
  sensor_frame?:Record<string,unknown>|null;
  setup?:{runtime_state:string;blockers:string[];profile:Record<string,unknown>|null;qualification:Record<string,unknown>|null;binding_sha256?:string};
  field?:RobotFieldState;
  capabilities:{drive:boolean;lidar:boolean;read_only_connection?:boolean;prepare?:boolean;qualify?:boolean;profile?:boolean};
  scan:{points:[number,number][];source:string}|null;
};
export type RobotFleetState = {
  schema_version:'robot-fleet-1.0';revision:number;focused_robot_id:string|null;robots:RobotFleetRobot[];
  last_command:{request_id:string;operation_id:string|null;robot_id:string|null;status:string;message:string}|null;
  capabilities:{sim:boolean;physical:boolean};policy:{linear_m_s:number;angular_rad_s:number;input_expiry_ms:number};
};
type FleetPayloads = {
  register_sim:{label:string;position_m:[number,number,number]};focus:Record<string,never>;
  connect:Record<string,never>;disconnect:Record<string,never>;prepare:Record<string,never>|{confirmed:true};
  qualify:{confirmed:true};profile:{profile:Record<string,unknown>};
  set_twin_pose:{position_m:[number,number,number]};
  field_setup:{config:FieldSetupConfig};field_arm:{confirmed:true};
  field_test:{case:FieldTestCase;confirmed:true};
  field_review:{trial_id:string;observed:FieldObservation;clearance_m?:number};
  drive:{direction:FleetDirection;sequence:number;expires_at_ms:number};stop:Record<string,never>;stop_all:Record<string,never>;
  lidar:{enabled:boolean};command:{text:string};
};
export type RobotFleetAction = {[K in keyof FleetPayloads]:{
  action:K;request_id:string;robot_id:string|null;connection_epoch:string|null;motion_epoch:string|null;payload:FleetPayloads[K]
}}[keyof FleetPayloads];
export type RobotFleetOperation = {
  schema_version:'robot-operation-1.0';operation_id:string;robot_id:string;project_id:string;
  events:Record<string,unknown>[];manifest:Record<string,unknown>;
};
// A connected label alone never certifies a current heartbeat or battery.
export function fleetRobotFresh(robot:RobotFleetRobot){
  // A successful one-shot physical read is not a persistent heartbeat.
  if(robot.kind==='physical'&&robot.live_heartbeat!==true)return false;
  return robot.connection_state==='CONNECTED'&&robot.telemetry_age_ms!==null&&robot.telemetry_age_ms>=0&&robot.telemetry_age_ms<(robot.kind==='physical'?2500:1000);
}
export function fleetBatteryLabel(robot:RobotFleetRobot){
  const battery=robot.battery;
  const stale=typeof battery.age_ms!=='number'||!Number.isFinite(battery.age_ms)||battery.age_ms<0||battery.age_ms>=1000||!fleetRobotFresh(robot);
  const value=battery.source==='unknown'?'unavailable':[
    typeof battery.percent==='number'&&Number.isFinite(battery.percent)?`${battery.percent.toFixed(0)}%`:null,
    typeof battery.voltage_v==='number'&&Number.isFinite(battery.voltage_v)?`${battery.voltage_v.toFixed(2)} V`:null,
  ].filter(Boolean).join(' · ')||'unavailable';
  return `${value} · ${battery.source}${stale?' · stale':''}`;
}
