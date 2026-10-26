// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Jaewon Lee
import {describe,expect,it} from 'vitest';
import {lidarDiagnosticLabel} from './robot-operation-diagnostics';
import type {RobotFleetRobot} from './robot-fleet-types';

const base={robot_id:'a',label:'Burger',kind:'physical',connection_state:'CONNECTED',connection_epoch:'e1',motion_epoch:'m1',control_state:'UNPREPARED',
  lidar_state:'STREAMING',recording_state:'RECORDING',operation_id:null,reason:null,battery:{voltage_v:12.3,percent:null,source:'measured',age_ms:100},
  pose:null,telemetry_age_ms:200,capabilities:{prepare:true,drive:false,qualify:false,profile:true},live_heartbeat:true} as unknown as RobotFleetRobot;

describe('LiDAR diagnostic label (PHYS09)',()=>{
  it('reports the live state while the heartbeat is fresh',()=>{expect(lidarDiagnosticLabel(base)).toBe('STREAMING');});
  it('says the sensor state is unknown after a remote exit without cleanup instead of echoing the last robot value as a fault',()=>{
    const exited={...base,connection_state:'DISCONNECTED',live_heartbeat:false,telemetry_age_ms:null,lidar_state:'FAULT',cleanup_confirmed:false,last_reported_lidar_state:'FAULT'} as RobotFleetRobot;
    expect(lidarDiagnosticLabel(exited)).toBe('unknown · runtime exited without cleanup (last robot value FAULT) · check whether the LDS is spinning');
  });
  it('keeps the plain stale wording when cleanup was confirmed',()=>{
    const clean={...base,connection_state:'DISCONNECTED',live_heartbeat:false,telemetry_age_ms:null,lidar_state:'OFF',cleanup_confirmed:true} as RobotFleetRobot;
    expect(lidarDiagnosticLabel(clean)).toBe('No current stream · last reported OFF');
  });
});
