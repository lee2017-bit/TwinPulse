// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {fireEvent,render,screen} from '@testing-library/react';
import {describe,expect,it,vi} from 'vitest';
import type {TwinPulseApi} from './api';
import {RobotFleet} from './RobotFleet';
import type {RobotFleetRobot,RobotFleetState} from './robot-fleet-types';

const live=(over:Partial<RobotFleetRobot>={}):RobotFleetRobot=>({robot_id:'a',label:'Burger',kind:'physical',connection_state:'CONNECTED',
  connection_epoch:'connection-a',motion_epoch:'motion-1',control_state:'PAUSED',lidar_state:'STREAMING',recording_state:'RECORDING',
  operation_id:'operation-a',reason:null,battery:{voltage_v:11.8,percent:null,source:'measured',age_ms:50},pose:null,telemetry_age_ms:50,
  telemetry_sequence:1,live_heartbeat:true,capabilities:{drive:true,lidar:true,read_only_connection:true,prepare:true,qualify:true,profile:true},scan:null,
  setup:{runtime_state:'CONNECTED',binding_sha256:'b',blockers:[],profile:null,qualification:null},
  field:{mode:'SUPERVISED_FIELD_TEST',armed:true,remaining_s:100,config:null,config_sha256:'cfg',blockers:[],stop_receipt:null,tracking:null,active_trial:null,trials:[]},
  ...over} as unknown as RobotFleetRobot);
const ended=(over:Partial<RobotFleetRobot>={})=>live({connection_state:'DISCONNECTED',connection_epoch:null,motion_epoch:null,live_heartbeat:false,operation_id:null,...over});
const state=(robots:RobotFleetRobot[]):RobotFleetState=>({schema_version:'robot-fleet-1.0',revision:2,focused_robot_id:'a',robots,last_command:null,
  capabilities:{sim:true,physical:true},policy:{linear_m_s:.05,angular_rad_s:.3,input_expiry_ms:250}} as RobotFleetState);
const notice=()=>screen.queryByText('Confirmations reset: new connection epoch');
const present=()=>screen.getByLabelText('I am present and confirm zero-command controller preparation.') as HTMLInputElement;
const supervise=()=>screen.getByLabelText(/I am supervising, charging is unplugged/) as HTMLInputElement;
function mount(first:RobotFleetRobot){
  const api={context:'c',robotFleetAction:vi.fn()} as unknown as TwinPulseApi;
  const props={api,selectedId:'a',onChange:vi.fn(),onSelect:vi.fn(),available:true};
  const view=render(<RobotFleet {...props} state={state([first])}/>);
  return {...view,show:(row:RobotFleetRobot|null)=>view.rerender(<RobotFleet {...props} state={row?state([row]):null}/>)};
}

describe('connection epoch notice (2026-10-27 build 59: stale, misattributed reset notice)',()=>{
  it('a reconnect resets every tick and is announced only until the next motion generation',()=>{
    const {show}=mount(live());
    fireEvent.click(present());fireEvent.click(supervise());
    show(ended());expect(present().checked).toBe(false);expect(notice()).toBeNull(); // link alert, not "new connection"
    show(live({connection_epoch:'connection-b',motion_epoch:'motion-b'}));
    expect(present().checked).toBe(false);expect(supervise().checked).toBe(false);expect(notice()).not.toBeNull();
    for(let i=2;i<35;i++)show(live({connection_epoch:'connection-b',motion_epoch:'motion-'+i}));
    expect(notice()).toBeNull();
    fireEvent.click(supervise());show(live({connection_epoch:'connection-b',motion_epoch:'motion-99'}));
    expect(supervise().checked).toBe(false); // FieldSessionGate motion reset unchanged
    fireEvent.click(supervise());show(live({connection_epoch:'connection-b',motion_epoch:'motion-99',field:{...live().field!,armed:false,remaining_s:0}}));
    expect(supervise().checked).toBe(false); // FieldSessionGate armed reset unchanged
    expect(notice()).toBeNull();
  });
  it('a direct X -> Y replacement right after mount is announced; a projection without the row is not',()=>{
    const {show}=mount(live());
    show(live({connection_epoch:'connection-b',motion_epoch:'motion-b'}));expect(notice()).not.toBeNull();
    show(live({connection_epoch:'connection-b',motion_epoch:'motion-c'}));expect(notice()).toBeNull();
    show(null);show(live({connection_epoch:'connection-b',motion_epoch:'motion-c'}));expect(notice()).toBeNull();
  });
});
