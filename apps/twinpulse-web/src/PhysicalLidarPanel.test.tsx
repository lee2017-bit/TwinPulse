// SPDX-License-Identifier: Apache-2.0
import {act,render,screen} from '@testing-library/react';
import {afterEach,describe,it,expect,vi} from 'vitest';
import {PhysicalLidarPanel} from './PhysicalLidarPanel';
import type {RobotFleetRobot} from './robot-fleet-types';

function robot():RobotFleetRobot{return {
  robot_id:'physical-a',label:'Burger',kind:'physical',connection_state:'CONNECTED',connection_epoch:'connection-a',
  motion_epoch:'motion-a',operation_id:'operation-a',control_state:'PAUSED',lidar_state:'STREAMING',recording_state:'RECORDING',reason:null,
  live_heartbeat:true,telemetry_age_ms:10,telemetry_sequence:4,pose:null,
  battery:{voltage_v:12,percent:null,source:'measured',age_ms:10},capabilities:{drive:false,lidar:true},
  scan:{points:[[1,0],[0,2]],frame_sequence:8,raw_sha256:'a'.repeat(64),source:'physical_native_sensor_unaligned'},
  scan_receipt:{age_ms:50,age_basis:'pc_scan_receipt',frame_id:'native_sensor',aligned:false}};}
afterEach(()=>vi.useRealTimers());
describe('always-visible physical sensor panel',()=>{
  it('shows original physical points without inventing a world pose or requiring a placed marker',()=>{
    render(<PhysicalLidarPanel robot={robot()} rendered={false} currentRevision="revision"/>);
    const svg=screen.getByRole('img',{name:'LiDAR scan · physical_native_sensor_unaligned'});
    expect(svg.querySelectorAll('circle')).toHaveLength(3);
    expect(screen.getByText(/Receiving · 2 hits/)).toBeTruthy();
    expect(screen.getByText('Robot not placed in this Twin')).toBeTruthy();
    expect(screen.getByText('Sensor-local view · not projected into the room.')).toBeTruthy();
    expect(screen.getByText(/Turning alone does not establish room alignment/)).toBeTruthy();
  });
  it('clears points immediately on OFF or disconnect, even if a raw scan remains in the row',()=>{
    const r=robot(),component=render(<PhysicalLidarPanel robot={r} rendered={false}/>);
    component.rerender(<PhysicalLidarPanel robot={{...r,lidar_state:'OFF'}} rendered={false}/>);
    expect(screen.queryByRole('img')).toBeNull();expect(screen.getByText('Sensor OFF')).toBeTruthy();
    component.rerender(<PhysicalLidarPanel robot={{...r,connection_state:'DISCONNECTED',live_heartbeat:false}} rendered={false}/>);
    expect(screen.queryByRole('img')).toBeNull();expect(screen.getByText('Disconnected · no live scan')).toBeTruthy();
  });
  it('expires an unchanged original scan without refreshing its age on repeated snapshots',()=>{
    vi.useFakeTimers();vi.setSystemTime(10000);const r=robot();
    const component=render(<PhysicalLidarPanel robot={r} rendered={false}/>);
    act(()=>vi.advanceTimersByTime(750));
    component.rerender(<PhysicalLidarPanel robot={{...r,scan:{...r.scan!},scan_receipt:{...r.scan_receipt!,age_ms:0}}} rendered={false}/>);
    act(()=>vi.advanceTimersByTime(250));
    expect(screen.queryByRole('img')).toBeNull();expect(screen.getByText('Scan unavailable / stale')).toBeTruthy();
    component.rerender(<PhysicalLidarPanel robot={{...r,scan:{...r.scan!,frame_sequence:9,raw_sha256:'b'.repeat(64)}}} rendered={false}/>);
    expect(screen.getByRole('img')).toBeTruthy();
  });
  it('does not fabricate receipt freshness and distinguishes an estimate from a rendered model',()=>{
    const r={...robot(),scan_receipt:null,display_pose:{position_m:[1,2,0] as [number,number,number],source:'operator_estimate_not_localized' as const,scene_revision:'revision',frame_id:'isaac_world' as const,aligned:false as const}};
    const component=render(<PhysicalLidarPanel robot={r} rendered={false} currentRevision="revision"/>);
    expect(screen.queryByRole('img')).toBeNull();expect(screen.getByText('Estimate saved · model outside view / awaiting render')).toBeTruthy();
    component.rerender(<PhysicalLidarPanel robot={r} rendered currentRevision="revision"/>);
    expect(screen.getByText('Robot model visible · estimated')).toBeTruthy();
    component.rerender(<PhysicalLidarPanel robot={r} rendered currentRevision="different-revision"/>);
    expect(screen.queryByText('Robot model visible · estimated')).toBeNull();
    expect(screen.getByText('Robot not placed in this Twin')).toBeTruthy();
  });
  it('keeps a marker placed after a Twin edit of the same import, such as an auto-applied LiDAR box, but not across imports',()=>{
    const pose={position_m:[1,2,0] as [number,number,number],source:'operator_estimate_not_localized' as const,scene_revision:'before-box',frame_id:'isaac_world' as const,aligned:false as const};
    const component=render(<PhysicalLidarPanel robot={{...robot(),display_pose:pose,display_pose_current:true}} rendered currentRevision="after-box"/>);
    expect(screen.getByText('Robot model visible · estimated')).toBeTruthy();
    component.rerender(<PhysicalLidarPanel robot={{...robot(),display_pose:pose,display_pose_current:false}} rendered currentRevision="new-import"/>);
    expect(screen.getByText('Robot not placed in this Twin')).toBeTruthy();
    component.rerender(<PhysicalLidarPanel robot={{...robot(),display_pose:pose,display_pose_current:true}} rendered/>);
    expect(screen.getByText('Robot not placed in this Twin')).toBeTruthy();
  });
  it('clears an otherwise fresh row when App/fleet reception is unavailable',()=>{
    const r=robot(),component=render(<PhysicalLidarPanel robot={r} rendered={false}/>);
    expect(screen.getByRole('img')).toBeTruthy();
    component.rerender(<PhysicalLidarPanel robot={r} available={false} rendered={false}/>);
    expect(screen.queryByRole('img')).toBeNull();expect(screen.queryByText(/Receiving/)).toBeNull();
  });
  it('does not adopt the previous connection scan as a new receipt',()=>{
    const r=robot(),component=render(<PhysicalLidarPanel robot={r} rendered={false}/>);
    component.rerender(<PhysicalLidarPanel robot={{...r,connection_epoch:'new-connection'}} rendered={false}/>);
    expect(screen.queryByRole('img')).toBeNull();
    component.rerender(<PhysicalLidarPanel robot={{...r,connection_epoch:'new-connection',scan:{...r.scan!,frame_sequence:9}}} rendered={false}/>);
    expect(screen.getByRole('img')).toBeTruthy();
  });
});
