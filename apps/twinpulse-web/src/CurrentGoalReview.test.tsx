// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {render,screen,act} from '@testing-library/react';
import {describe,it,expect,vi} from 'vitest';
import {CurrentGoalReview} from './CurrentGoalReview';
import type {CurrentGoalState} from './conversation-types';

describe('current goal review',()=>{
  const state:CurrentGoalState={review:{scene_revision:'scene',target:null,choices:[],drawing:{bounds:[-2,2,-2,2],boxes:[],discs:[]},
    plan:{schema:'current-goal-preview-1.0',mode:'REAL_CANDIDATE',plan_id:'plan',start:[0,0],goal:[.2,0],route:[[.2,0]],yaw_rad:0,physical_authority:false}},
    error:null,current_pose_available:false,motion_authorized:false,physical_demo_ready:false,job:null};
  it('shows active repeat leg, dated battery, unsupported load and separate faults',()=>{
    render(<CurrentGoalReview state={{...state,task_loop:{task_id:'task',state:'FAILED',leg:3,destination:'A',completed_legs:2,
      a:[0,0],b:[.2,0],worker_active:false,error:'TASK_BATTERY_STALE',error_stage:'PREPARE_LEG',cleanup_error:'CLEANUP_PENDING',
      resources:{voltage_v:12,estimated_percent:83.3,capacity_measured:false,historical:true},motion_authorized:false,physical_demo_ready:false}}}/>);
    expect(screen.getByText(/Leg 3 → A/)).toBeTruthy();
    expect(screen.getByText(/historical, not measured capacity/)).toBeTruthy();
    expect(screen.getByText(/Motor load measurement is unsupported/)).toBeTruthy();
    expect(screen.getAllByRole('alert').map(x=>x.textContent)).toEqual(['PREPARE_LEG: TASK_BATTERY_STALE','Cleanup: CLEANUP_PENDING']);
    expect(screen.queryByRole('progressbar')).toBeNull();
  });
  it.each(['DRIVING','STOPPING','MISSION_ARRIVED'])('labels current telemetry separately from history in %s',phase=>{
    render(<CurrentGoalReview state={{...state,job:{job_id:'j',state:phase,elapsed_s:1,worker_active:true,
      telemetry_age_s:.05,telemetry_status:'RECENT_WORKER_RECEIPT',telemetry:{
        battery:{voltage_v:12,estimated_percent:83.3,measured_capacity:false},
        next_waypoint:{index:0,count:2,xy_room:[.1,.2]},motor_load:'UNSUPPORTED'}}}}/>);
    if(phase==='DRIVING'){
      expect(screen.getByText(/Latest worker battery: 12.00 V/)).toBeTruthy();
      expect(screen.getByText(/Next waypoint 1\/2/)).toBeTruthy();
    }else{
      expect(screen.queryByText(/Latest worker battery:/)).toBeNull();
      expect(screen.getByText(/Current battery unavailable/)).toBeTruthy();
    }
  });
  it('never labels stale receipts current',()=>{
    render(<CurrentGoalReview state={{...state,job:{job_id:'j',state:'DRIVING',elapsed_s:1,worker_active:true,
      telemetry_age_s:1.1,telemetry_status:'RECENT_WORKER_RECEIPT',telemetry:{
        battery:{voltage_v:12,estimated_percent:83.3,measured_capacity:false},next_waypoint:null,motor_load:'UNSUPPORTED'}}}}/>);
    expect(screen.queryByText(/Latest worker battery:/)).toBeNull();
    expect(screen.getByText(/Current battery unavailable/)).toBeTruthy();
  });
  it('expires a cached receipt without any subsequent network response',()=>{
    vi.useFakeTimers();
    try{
      render(<CurrentGoalReview state={{...state,job:{job_id:'j',state:'DRIVING',elapsed_s:1,worker_active:true,
        telemetry_age_s:.05,telemetry_status:'RECENT_WORKER_RECEIPT',telemetry:{
          battery:{voltage_v:12,estimated_percent:83.3,measured_capacity:false},next_waypoint:null,motor_load:'UNSUPPORTED'}}}}/>);
      expect(screen.getByText(/Latest worker battery:/)).toBeTruthy();
      act(()=>vi.advanceTimersByTime(951));
      expect(screen.queryByText(/Latest worker battery:/)).toBeNull();
      expect(screen.getByText(/Current battery unavailable/)).toBeTruthy();
    }finally{vi.useRealTimers();}
  });
  it('shows a reviewed historical start, not live pose or completed 3D',()=>{
    render(<CurrentGoalReview state={state}/>);
    expect(screen.getByRole('img',{name:'Candidate route from the reviewed sensor position'})).toBeTruthy();
    expect(screen.getByText(/not a continuously observed current position/)).toBeTruthy();
    expect(screen.queryByRole('button')).toBeNull();
  });
  it('shows exact backend blocker instead of silently substituting SIM',()=>{
    render(<CurrentGoalReview state={{...state,review:null,error:'current_goal_preview_unavailable'}}/>);
    expect(screen.getByRole('alert').textContent).toContain('current_goal_preview_unavailable');
    expect(screen.queryByRole('img')).toBeNull();
  });
  it('keeps first, cleanup and report failures separate',()=>{
    render(<CurrentGoalReview state={{...state,review:null,job:{job_id:'job',state:'FAILED',elapsed_s:2,
      error:'SCAN_STALE',cleanup_error:'MOTOR_STOP_UNKNOWN',report_error:'DISK_FULL'}}}/>);
    expect(screen.getAllByRole('alert').map(x=>x.textContent)).toEqual(['SCAN_STALE','Cleanup: MOTOR_STOP_UNKNOWN','Report: DISK_FULL']);
  });
  it('shows bounded native cleanup diagnoses even when adapter cleanup is different',()=>{
    render(<CurrentGoalReview state={{...state,review:null,job:{job_id:'job',state:'FAILED',elapsed_s:2,
      error:'INPUT_DEADLINE_EXPIRED',native_cleanup_errors:[{stage:'mission_halt',code:'STOP_READBACK_UNCONFIRMED',error_type:'ValueError'}],
      cleanup_error:'OWNED_SENSOR_STOP_UNCONFIRMED',report_error:'MISSION_REPORT_STORAGE_FULL'}}}/>);
    expect(screen.getAllByRole('alert').map(x=>x.textContent)).toEqual(['INPUT_DEADLINE_EXPIRED',
      'Native cleanup · mission_halt: STOP_READBACK_UNCONFIRMED (ValueError)',
      'Cleanup: OWNED_SENSOR_STOP_UNCONFIRMED','Report: MISSION_REPORT_STORAGE_FULL']);
  });
  it('does not render arbitrary native exception text or oversized lists',()=>{
    const bad={stage:'mission_halt',code:'SECRET=untrusted',error_type:'ValueError'};
    const view=render(<CurrentGoalReview state={{...state,job:{job_id:'j',state:'FAILED',elapsed_s:1,native_cleanup_errors:[bad]}}}/>);
    expect(screen.queryByText(/SECRET/)).toBeNull();
    view.rerender(<CurrentGoalReview state={{...state,job:{job_id:'j',state:'FAILED',elapsed_s:1,
      native_cleanup_errors:Array(9).fill({...bad,code:'STOP_READBACK_UNCONFIRMED'})}}}/>);
    expect(screen.queryByText(/Native cleanup/)).toBeNull();
  });
  it('shows loading and exact preview stage without authorizing real motion',()=>{
    render(<CurrentGoalReview state={{...state,demonstration:{state:'RUNNING',stage:'RUN',elapsed_s:2,error:null,
      cleanup_error:null,review_id:'plan',simulation_id:'sim',receipt_current:false,handoff_ready:false,physical_authority:false}}}/>);
    expect(screen.getByRole('progressbar')).toBeTruthy();
    expect(screen.getByText(/Isaac 3D route demonstration/).textContent).toContain('RUNNING');
  });
  it('distinguishes completed SIM, missing handoff and cleanup error',()=>{
    render(<CurrentGoalReview state={{...state,demonstration:{state:'COMPLETED',stage:'ARRIVAL',elapsed_s:3,error:null,
      cleanup_error:'PAUSE_FAILED',review_id:'plan',simulation_id:'sim',receipt_current:true,handoff_ready:false,physical_authority:false}}}/>);
    expect(screen.getByText(/Exact route completed in Isaac PhysX/).textContent).toContain('not physical validation');
    expect(screen.getByRole('alert').textContent).toContain('PAUSE_FAILED');
    expect(screen.queryByRole('progressbar')).toBeNull();
  });
  it('shows parked review without claiming a live pose or automatic start',()=>{
    render(<CurrentGoalReview state={{...state,review:{...state.review!,plan:{...state.review!.plan!,schema:'current-goal-preview-2.0'}},
      demonstration:{state:'COMPLETED',stage:'ARRIVAL',elapsed_s:3,error:null,cleanup_error:null,
        review_id:'plan',simulation_id:'sim',receipt_current:true,handoff_ready:true,robot_review_parked:true,physical_authority:false}}}/>);
    expect(screen.getByText(/Robot idle during review/).textContent).toContain('Confirm collects a fresh position');
    expect(screen.getByText(/not a continuously observed current position/)).toBeTruthy();
    expect(screen.queryByRole('button')).toBeNull();
  });
});
