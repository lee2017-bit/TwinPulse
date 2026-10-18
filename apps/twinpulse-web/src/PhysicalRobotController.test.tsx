// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { TwinPulseApi } from './api';
import { PhysicalRobotController, type PhysicalState } from './PhysicalRobotController';
import type { RobotDiagnosticsState } from './RobotDiagnostics';

const observedRobot:NonNullable<RobotDiagnosticsState['record']>={
  boot_id:'boot-a',release_id:'release-a',report_sha256:'test',observed_at_utc:'2026-10-03T00:00:00Z',
  age_seconds:0,board_status:'OBSERVED',idle_at_observation:true,battery:null,
};

function mock(){
  let current:PhysicalState={state:'NOT_STARTED',busy:false};
  return {
    physicalStart:vi.fn().mockImplementation(async(mode:string,id:string)=>{
      current={state:'READY',busy:true,owned:true,job_id:id,mode,sequence:0};return current;
    }),
    physicalState:vi.fn().mockImplementation(async()=>current),
    physicalInput:vi.fn().mockImplementation(async(_job:string,sequence:number,action:string)=>{
      current={...current,sequence,...(action==='close'?{state:'FINISHED',busy:false,cleanup_confirmed:true}:{})};return current;
    }),
  };
}
function continuousMock(){
  const api=mock();let current:PhysicalState={state:'NOT_STARTED',busy:false};
  api.physicalStart.mockImplementation(async(mode:string,id:string)=>current={state:'READY',mode,job_id:id,busy:true,owned:true,sequence:0,
    motion_generation:0,pause_reason:null,motion_lease_policy:'fresh-intent-1.0',session_policy:'until-stop-1.0'});
  api.physicalState.mockImplementation(async()=>current);
  api.physicalInput.mockImplementation(async(_id:string,sequence:number,action:string)=>current={...current,sequence,
    ...(action==='close'?{state:'FINISHED',busy:false,cleanup_confirmed:true}:{})});
  return {api,get:()=>current,set:(value:PhysicalState)=>{current=value;}};
}
async function connectContinuous(h:ReturnType<typeof continuousMock>){
  const view=render(<PhysicalRobotController api={h.api as unknown as TwinPulseApi}/>);
  fireEvent.click(screen.getByRole('checkbox'));fireEvent.click(screen.getByText('3. Connect manual control'));
  await waitFor(()=>expect((screen.getByText('↑ Forward') as HTMLButtonElement).disabled).toBe(false));
  return {view,panel:screen.getByRole('region',{name:'Physical controller'})};
}
afterEach(()=>{vi.useRealTimers();vi.unstubAllGlobals();});
describe('physical manual controls',()=>{
  it('keeps an advertised until-stop session ready beyond the legacy timer and displays actual worker speeds',async()=>{
    const timer=vi.spyOn(performance,'now').mockReturnValue(0);
    try{
      const api=mock();let current:PhysicalState={state:'FINISHED',busy:false,last_trial:{historical:true,
        job_id:'trial',boot_id:'boot-a',release_id:'release-a',status:'QUALIFIED',cleanup_confirmed:true,
        stop_assessment:{policy_id:'supervised-stop-2.1',status:'PASS',reason:'',checks:{},metrics:{},
          limits:{deceleration_budget_s:.5,verification_s:.3,wheel_travel_limit_mm:10,residual_rate_limit_mm_s:1}}}};
      api.physicalState.mockImplementation(async()=>current);
      api.physicalStart.mockImplementation(async(mode:string,id:string)=>current={...current,state:'READY',mode,
        job_id:id,busy:true,owned:true,sequence:0,motion_lease_policy:'fresh-intent-1.0',
        session_policy:'until-stop-1.0',manual_speed:{linear_m_s:.05,angular_rad_s:.3}});
      api.physicalInput.mockImplementation(async(_id:string,sequence:number)=>current={...current,sequence});
      render(<PhysicalRobotController api={api as unknown as TwinPulseApi} compact observedRobot={observedRobot} localReleaseId="release-a"/>);
      await waitFor(()=>expect((screen.getByRole('button',{name:'Connect drive + LiDAR'}) as HTMLButtonElement).disabled).toBe(false));
      fireEvent.click(screen.getByRole('button',{name:'Connect drive + LiDAR'}));
      await screen.findByText(/READY TO DRIVE · Until Stop/);
      timer.mockReturnValue(180000);
      await screen.findByText(/Speed: 0.05 m\/s · turn: 0.30 rad\/s/);
      expect(screen.queryByText(/Session expires in about/)).toBeNull();
      expect((screen.getByRole('button',{name:'Drive joystick'}) as HTMLButtonElement).disabled).toBe(false);
      expect(api.physicalStart).toHaveBeenCalledTimes(1);
      expect(api.physicalInput.mock.calls.some(c=>['close','force_stop','finish_stop'].includes(c[2]))).toBe(false);
      current={...current,state:'STOPPING'};
      await screen.findByText('Stopping robot and LiDAR — waiting for cleanup confirmation.');
      current={...current,state:'FINISHED',session_policy:undefined,busy:true};
      await screen.findByText('Robot operation ended — saving results. No movement or automatic reconnect.');
      expect(screen.queryByText(/Session expires in about/)).toBeNull();
      expect(screen.queryByText(/Preparing control scan/)).toBeNull();
    }finally{timer.mockRestore();}
  });
  it('shows approximate countdown and expiry at the joystick without inventing a release fault',async()=>{
    const timer=vi.spyOn(performance,'now').mockReturnValue(0);
    try{
      const api=mock();let current:PhysicalState={state:'FINISHED',busy:false,last_trial:{historical:true,
        job_id:'trial',boot_id:'boot-a',release_id:'release-a',status:'QUALIFIED',cleanup_confirmed:true,
        stop_assessment:{policy_id:'supervised-stop-2.0',status:'PASS',reason:'',checks:{},metrics:{},
          limits:{deceleration_budget_s:.5,verification_s:.3,wheel_travel_limit_mm:10,residual_rate_limit_mm_s:1}}}};
      api.physicalState.mockImplementation(async()=>current);
      api.physicalStart.mockImplementation(async(mode:string,id:string)=>current={...current,state:'READY',mode,
        job_id:id,busy:true,owned:true,sequence:0,motion_lease_policy:'fresh-intent-1.0'});
      api.physicalInput.mockImplementation(async(_id:string,sequence:number)=>current={...current,sequence});
      render(<PhysicalRobotController api={api as unknown as TwinPulseApi} compact observedRobot={observedRobot} localReleaseId="release-a"/>);
      await waitFor(()=>expect((screen.getByRole('button',{name:'Connect drive + LiDAR'}) as HTMLButtonElement).disabled).toBe(false));
      fireEvent.click(screen.getByRole('button',{name:'Connect drive + LiDAR'}));
      await screen.findByText(/READY TO DRIVE · about 60s remaining/);
      timer.mockReturnValue(52000);
      await screen.findByText(/Session expires in about 8s/);
      current={...current,state:'RELEASING'};
      await screen.findByText('Stopping wheels · connection remains open');
      current={...current,state:'FINISHED',busy:false,reason:'SESSION_EXPIRED',result:'FAILED',cleanup_confirmed:true};
      await screen.findByText(/Session ended — the 60-second connection limit was reached, not a joystick-release fault/);
      expect((screen.getByRole('button',{name:'Connect drive + LiDAR'}) as HTMLButtonElement).disabled).toBe(false);
      expect(api.physicalStart).toHaveBeenCalledTimes(1);
    }finally{timer.mockRestore();}
  });
  it('allows scan-only without a motion receipt, never unlocks the joystick and closes the sensor session',async()=>{
    const api=mock();
    render(<PhysicalRobotController api={api as unknown as TwinPulseApi} compact observedRobot={observedRobot} localReleaseId="release-a"/>);
    fireEvent.click(screen.getByRole('button',{name:'Start LiDAR scan'}));
    await waitFor(()=>expect(api.physicalStart).toHaveBeenCalledTimes(1));
    expect(api.physicalStart.mock.calls[0][0]).toBe('scan');
    expect((screen.getByRole('button',{name:'Drive joystick'}) as HTMLButtonElement).disabled).toBe(true);
    await waitFor(()=>expect((screen.getByRole('button',{name:'Stop LiDAR scan'}) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole('button',{name:'Stop LiDAR scan'}));
    await waitFor(()=>expect(api.physicalInput.mock.calls.some(c=>c[2]==='close')).toBe(true));
    expect(api.physicalInput.mock.calls.some(c=>['forward','backward','left','right'].includes(c[2]))).toBe(false);
  });
  it('refuses scan display on an older robot source even when the operator confirms',async()=>{
    const api=mock();
    render(<PhysicalRobotController api={api as unknown as TwinPulseApi} compact observedRobot={observedRobot} localReleaseId="new-release"/>);
    expect((screen.getByRole('button',{name:'Start LiDAR scan'}) as HTMLButtonElement).disabled).toBe(true);
    expect(api.physicalStart).not.toHaveBeenCalled();
  });
  it('shows LiDAR stop progress next to its button and distinguishes data quiet from rotor measurement',async()=>{
    const api=mock();
    api.physicalStart.mockImplementation(async(mode:string,id:string)=>({state:'LIDAR_RUNNING',mode,
      job_id:id,owned:true,busy:true,sequence:0}));
    api.physicalInput.mockImplementation(async(job_id:string,sequence:number,action:string)=>({state:'STOPPING',
      mode:'lidar',job_id,owned:true,busy:true,sequence,stop_request:'close',stop_delivery:'PIPE_WRITTEN'}));
    render(<PhysicalRobotController api={api as unknown as TwinPulseApi}/>);
    fireEvent.click(screen.getByRole('checkbox'));fireEvent.click(screen.getByText('Start lidar · up to 8 seconds'));
    await screen.findByText(/LiDAR running ·/);
    const stop=screen.getByRole('button',{name:'Stop lidar'});
    fireEvent.click(stop);
    await screen.findByText(/Stop request transmitted — waiting for sensor data/);
    expect((stop as HTMLButtonElement).disabled).toBe(true);
    const id=api.physicalInput.mock.calls[0][0];
    api.physicalState.mockResolvedValue({state:'FINISHED',mode:'lidar',job_id:id,owned:true,busy:false,
      sequence:100,cleanup_confirmed:true,lidar_result:{operator_cancelled:true,data_quiet_after_stop:true,
        port_restored:true,stop_write_complete:true,physical_rotor_stopped:false}});
    await screen.findByText(/LiDAR STOP write confirmed · data quiet · port restored/);
    expect(screen.getByText(/Physical rotor stop is not measured/)).toBeTruthy();
  });
  it('uses the current boot and release stop receipt to show only Connect in the quick console',async()=>{
    const api=mock();api.physicalState.mockResolvedValue({state:'FINISHED',mode:'control',busy:false,
      result:'FAILED',reason:'HOLD_LIMIT_EXCEEDED',last_trial:{historical:true,job_id:'trial',
        boot_id:'boot-a',release_id:'release-a',status:'QUALIFIED',cleanup_confirmed:true,
        stop_assessment:{policy_id:'supervised-stop-2.0',status:'PASS',reason:'',checks:{},metrics:{},
          limits:{deceleration_budget_s:.5,verification_s:.3,wheel_travel_limit_mm:10,residual_rate_limit_mm_s:1}}}});
    render(<PhysicalRobotController api={api as unknown as TwinPulseApi} compact observedRobot={observedRobot} localReleaseId="release-a"/>);
    await waitFor(()=>expect(screen.getByText(/This boot and package release have a passing stop record/)).toBeTruthy());
    expect(screen.queryByText('Prepare package · deploy / Motor OFF')).toBeNull();
    expect(screen.queryByText('Prepare required stop test')).toBeNull();
    const connect=screen.getByRole('button',{name:'Connect drive + LiDAR'}) as HTMLButtonElement;
    expect(screen.queryByRole('checkbox')).toBeNull();
    expect(connect.disabled).toBe(false);
    expect(api.physicalStart).not.toHaveBeenCalled();
  });
  it('starts scan and manual drive as one owned mode, not a second LiDAR operation',async()=>{
    const api=mock();api.physicalState.mockResolvedValue({state:'FINISHED',busy:false,
      last_trial:{historical:true,job_id:'trial',boot_id:'boot-a',release_id:'release-a',
        status:'QUALIFIED',cleanup_confirmed:true,stop_assessment:{
          policy_id:'supervised-stop-2.0',status:'PASS',reason:'',checks:{},metrics:{},
          limits:{deceleration_budget_s:.5,verification_s:.3,wheel_travel_limit_mm:10,residual_rate_limit_mm_s:1}}}});
    render(<PhysicalRobotController api={api as unknown as TwinPulseApi} compact observedRobot={observedRobot} localReleaseId="release-a"/>);
    await waitFor(()=>expect((screen.getByRole('button',{name:'Connect drive + LiDAR'}) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole('button',{name:'Connect drive + LiDAR'}));
    await waitFor(()=>expect(api.physicalStart).toHaveBeenCalledTimes(1));
    expect(api.physicalStart.mock.calls[0][0]).toBe('control_scan');
    await waitFor(()=>expect((screen.getByRole('button',{name:'↑ Forward'}) as HTMLButtonElement).disabled).toBe(false));
    expect((screen.getByRole('button',{name:'Start lidar · up to 8 seconds'}) as HTMLButtonElement).disabled).toBe(true);
  });
  it('does not offer control from a stale or failed qualification',async()=>{
    const api=mock();api.physicalState.mockResolvedValue({state:'FINISHED',busy:false,
      last_trial:{historical:true,job_id:'old',boot_id:'boot-a',release_id:'release-b',
        status:'QUALIFIED',cleanup_confirmed:true,stop_assessment:{
          policy_id:'supervised-stop-2.0',status:'PASS',reason:'',checks:{},metrics:{},
          limits:{deceleration_budget_s:.5,verification_s:.3,wheel_travel_limit_mm:10,residual_rate_limit_mm_s:1}}}});
    render(<PhysicalRobotController api={api as unknown as TwinPulseApi} compact observedRobot={observedRobot}/>);
    await waitFor(()=>expect(screen.getByText(/Saved stop test does not match this status snapshot/)).toBeTruthy());
    expect((screen.getByRole('button',{name:'Connect drive + LiDAR'}) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole('button',{name:'Prepare required stop test'}) as HTMLButtonElement).disabled).toBe(true);
    expect(api.physicalStart).not.toHaveBeenCalled();
  });
  it('keeps combined LiDAR + drive locked on an older qualified robot release and offers explicit upgrade',async()=>{
    const api=mock();api.physicalState.mockResolvedValue({state:'FINISHED',busy:false,
      last_trial:{historical:true,job_id:'trial',boot_id:'boot-a',release_id:'release-a',
        status:'QUALIFIED',cleanup_confirmed:true,stop_assessment:{
          policy_id:'supervised-stop-2.0',status:'PASS',reason:'',checks:{},metrics:{},
          limits:{deceleration_budget_s:.5,verification_s:.3,wheel_travel_limit_mm:10,residual_rate_limit_mm_s:1}}}});
    render(<PhysicalRobotController api={api as unknown as TwinPulseApi} compact observedRobot={observedRobot} localReleaseId="new-release"/>);
    await waitFor(()=>expect(screen.getByText(/LiDAR \+ driving needs this App’s newer robot package/)).toBeTruthy());
    expect((screen.getByRole('button',{name:'Connect drive + LiDAR'}) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByRole('combobox',{name:'Driving mode'}),{target:{value:'control'}});
    expect((screen.getByRole('button',{name:'Connect drive only'}) as HTMLButtonElement).disabled).toBe(false);
    expect((screen.getByRole('button',{name:'Prepare package · deploy / Motor OFF'}) as HTMLButtonElement).disabled).toBe(false);
  });
  it('opens Connect after this page completes an owned physical stop test without redeploying',async()=>{
    const api=mock();let current:PhysicalState={state:'FINISHED',busy:false,result:'PREPARED'};
    api.physicalState.mockImplementation(async()=>current);
    api.physicalStart.mockImplementation(async(mode:string,id:string)=>{
      current={state:'READY',mode,busy:true,owned:true,job_id:id,sequence:0};return current;
    });
    api.physicalInput.mockImplementation(async(_job:string,sequence:number,action:string)=>{
      if(action==='qualify')current={state:'FINISHED',mode:'qualify',busy:false,owned:true,
        job_id:current.job_id,sequence,result:'QUALIFIED',cleanup_confirmed:true,physical_verified:true,
        last_trial:{historical:true,job_id:current.job_id!,boot_id:'boot-a',release_id:'release-b',
          status:'QUALIFIED',cleanup_confirmed:true}};
      else current={...current,sequence};
      return current;
    });
    render(<PhysicalRobotController api={api as unknown as TwinPulseApi} compact observedRobot={observedRobot} localReleaseId="release-b"/>);
    await waitFor(()=>expect((screen.getByRole('button',{name:'Prepare required stop test'}) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole('button',{name:'Prepare required stop test'}));
    await waitFor(()=>expect((screen.getByRole('button',{name:/Execute stop test/}) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole('button',{name:/Execute stop test/}));
    await waitFor(()=>expect(screen.queryByText('Prepare package · deploy / Motor OFF')).toBeNull());
    expect((screen.getByRole('button',{name:'Connect drive + LiDAR'}) as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(screen.getByRole('button',{name:'Connect drive + LiDAR'}));
    await screen.findByText(/CONNECTED · Drive \+ LiDAR · joystick READY · about \d+s remaining/);
    expect(screen.queryByText('Prepare required stop test')).toBeNull();
    expect((screen.getByRole('button',{name:'Drive joystick'}) as HTMLButtonElement).disabled).toBe(false);
  });
  it('releases before two seconds and waits for robot READY before continuing a held direction',async()=>{
    const api=mock();let current:PhysicalState={state:'NOT_STARTED',busy:false};
    api.physicalStart.mockImplementation(async(mode:string,id:string)=>{
      current={state:'READY',mode,job_id:id,busy:true,owned:true,sequence:0};return current;
    });
    api.physicalState.mockImplementation(async()=>current);
    api.physicalInput.mockImplementation(async(_job:string,sequence:number,action:string)=>{
      current={...current,sequence,...(action==='stop'?{state:'RELEASING'}:{})};
      if(action==='stop')setTimeout(()=>{current={...current,state:'READY'};},80);
      return current;
    });
    render(<PhysicalRobotController api={api as unknown as TwinPulseApi}/>);
    fireEvent.click(screen.getByRole('checkbox'));fireEvent.click(screen.getByText('3. Connect manual control'));
    await waitFor(()=>expect((screen.getByText('↑ Forward') as HTMLButtonElement).disabled).toBe(false));
    const panel=screen.getByRole('region',{name:'Physical controller'});
    fireEvent.keyDown(panel,{key:'w',code:'KeyW'});
    await waitFor(()=>expect(api.physicalInput.mock.calls.filter(c=>c[2]==='stop')).toHaveLength(1),{timeout:2400});
    await waitFor(()=>expect(api.physicalInput.mock.calls.filter(c=>c[2]==='forward').length).toBeGreaterThan(1));
    fireEvent.keyUp(panel,{key:'w',code:'KeyW'});
    expect(api.physicalInput.mock.calls.some(c=>c[2]==='close')).toBe(false);
    await waitFor(()=>expect((screen.getByText('↑ Forward') as HTMLButtonElement).disabled).toBe(false));
  });
  it('keeps fresh-policy WASD held across three seconds and releases without closing',async()=>{
    const api=mock();let current:PhysicalState={state:'FINISHED',busy:false,last_trial:{historical:true,
      job_id:'trial',boot_id:'boot-a',release_id:'release-a',status:'QUALIFIED',cleanup_confirmed:true,
      stop_assessment:{policy_id:'supervised-stop-2.0',status:'PASS',reason:'',checks:{},metrics:{},
        limits:{deceleration_budget_s:.5,verification_s:.3,wheel_travel_limit_mm:10,residual_rate_limit_mm_s:1}}}};
    api.physicalState.mockImplementation(async()=>current);
    api.physicalStart.mockImplementation(async(mode:string,id:string)=>{
      current={...current,state:'READY',mode,job_id:id,busy:true,owned:true,sequence:0,motion_lease_policy:'fresh-intent-1.0'};
      return current;
    });
    api.physicalInput.mockImplementation(async(_job:string,sequence:number)=>current={...current,sequence});
    render(<PhysicalRobotController api={api as unknown as TwinPulseApi} compact observedRobot={observedRobot} localReleaseId="release-a"/>);
    await waitFor(()=>expect((screen.getByRole('button',{name:'Connect drive + LiDAR'}) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole('button',{name:'Connect drive + LiDAR'}));
    await screen.findByText(/CONNECTED · Drive \+ LiDAR · joystick READY · about \d+s remaining/);
    const panel=screen.getByRole('region',{name:'Physical controller'});
    fireEvent.keyDown(panel,{key:'w',code:'KeyW'});
    await act(async()=>{await new Promise(r=>setTimeout(r,3100));});
    expect(api.physicalInput.mock.calls.filter(c=>c[2]==='forward').length).toBeGreaterThan(15);
    expect(api.physicalInput.mock.calls.some(c=>c[2]==='stop'||c[2]==='close')).toBe(false);
    fireEvent.keyUp(panel,{key:'w',code:'KeyW'});
    await waitFor(()=>expect(api.physicalInput.mock.calls.filter(c=>c[2]==='stop')).toHaveLength(1));
    expect((screen.getByRole('button',{name:'Drive joystick'}) as HTMLButtonElement).disabled).toBe(false);
    expect(api.physicalInput.mock.calls.some(c=>c[2]==='close')).toBe(false);
  });
  it('finishes only the current slice, locks new input and permits force escalation',async()=>{
    const api=mock();render(<PhysicalRobotController api={api as unknown as TwinPulseApi}/>);
    fireEvent.click(screen.getByRole('checkbox'));fireEvent.click(screen.getByText('3. Connect manual control'));
    await waitFor(()=>expect((screen.getByText('↑ Forward') as HTMLButtonElement).disabled).toBe(false));
    const panel=screen.getByRole('region',{name:'Physical controller'});
    fireEvent.keyDown(panel,{key:'w',code:'KeyW'});
    fireEvent.click(screen.getByRole('button',{name:'Stop after current command'}));
    await waitFor(()=>expect(api.physicalInput.mock.calls.some(c=>c[2]==='finish_stop')).toBe(true));
    expect((screen.getByText('↑ Forward') as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole('button',{name:'Force STOP · Esc'}) as HTMLButtonElement).disabled).toBe(false);
    const count=api.physicalInput.mock.calls.length;
    fireEvent.keyDown(panel,{key:'a',code:'KeyA'});
    await act(async()=>{await new Promise(r=>setTimeout(r,220));});
    expect(api.physicalInput.mock.calls).toHaveLength(count);
    fireEvent.click(screen.getByRole('button',{name:'Force STOP · Esc'}));
    await waitFor(()=>expect(api.physicalInput.mock.calls.at(-1)?.[2]).toBe('force_stop'));
    expect(api.physicalStart).toHaveBeenCalledTimes(1);
  });
  it('Escape requests force stop without requiring renewed operator confirmation',async()=>{
    const api=mock();render(<PhysicalRobotController api={api as unknown as TwinPulseApi}/>);
    fireEvent.click(screen.getByRole('checkbox'));fireEvent.click(screen.getByText('3. Connect manual control'));
    await waitFor(()=>expect((screen.getByText('↑ Forward') as HTMLButtonElement).disabled).toBe(false));
    fireEvent.keyDown(screen.getByRole('region',{name:'Physical controller'}),{key:'Escape'});
    await waitFor(()=>expect(api.physicalInput.mock.calls.some(c=>c[2]==='force_stop')).toBe(true));
    expect((screen.getByRole('checkbox') as HTMLInputElement).checked).toBe(false);
    expect((screen.getByText('↑ Forward') as HTMLButtonElement).disabled).toBe(true);
  });
  it('locks live mission with actionable implementation reason and no connection',async()=>{
    const api=mock();render(<PhysicalRobotController api={api as unknown as TwinPulseApi}/>);
    expect(screen.getByText(/reviewed physical deployment and coordinate calibration are missing/)).toBeTruthy();
    fireEvent.click(screen.getByRole('checkbox'));
    expect((screen.getByText('Start approved mission') as HTMLButtonElement).disabled).toBe(true);
    expect(api.physicalStart).not.toHaveBeenCalled();
  });
  it('freezes one approved scope and sends only heartbeat until explicit mission cancellation',async()=>{
    const api={...mock(),physicalMission:vi.fn()};
    api.physicalState.mockResolvedValue({state:'NOT_STARTED',busy:false,
      mission_readiness:{start_available:true,basis:'TEST_TRANSPORT_ONLY',physical_ready:false}});
    api.physicalMission.mockImplementation(async(scope,id)=>({state:'READY',busy:true,owned:true,job_id:id,mode:'mission',
      sequence:0,mission_scope:scope,mission_readiness:{start_available:true,basis:'TEST_TRANSPORT_ONLY',physical_ready:false}}));
    render(<PhysicalRobotController api={api as unknown as TwinPulseApi}/>);
    await waitFor(()=>expect((screen.getByLabelText('Mission waypoints XY') as HTMLTextAreaElement).disabled).toBe(false));
    fireEvent.change(screen.getByLabelText('Mission waypoints XY'),{target:{value:'[[0.04,0]]'}});
    fireEvent.click(screen.getByRole('checkbox'));fireEvent.click(screen.getByText('Start approved mission'));
    await waitFor(()=>expect(api.physicalMission).toHaveBeenCalledTimes(1));
    expect(api.physicalMission.mock.calls[0][0]).toEqual({frame_id:'odom',waypoints:[[.04,0]],duration_s:15});
    expect((screen.getByLabelText('Mission waypoints XY') as HTMLTextAreaElement).disabled).toBe(true);
    expect((screen.getByText('↑ Forward') as HTMLButtonElement).disabled).toBe(true);
    await waitFor(()=>expect(api.physicalInput.mock.calls.some(c=>c[2]==='watch')).toBe(true));
    fireEvent.click(screen.getByText('Cancel mission'));
    await waitFor(()=>expect(api.physicalInput.mock.calls.some(c=>c[2]==='close')).toBe(true));
    expect(api.physicalInput.mock.calls.every(c=>['watch','close'].includes(c[2]))).toBe(true);
    expect(api.physicalStart).not.toHaveBeenCalled();
  });
  it.each(['blur','escape','backend','unmount'])('revokes a late mission start after %s',async(reason)=>{
    const api={...mock(),physicalMission:vi.fn()};let resolve!:(s:PhysicalState)=>void;
    api.physicalState.mockResolvedValue({state:'NOT_STARTED',busy:false,
      mission_readiness:{start_available:true,basis:'TEST_TRANSPORT_ONLY',physical_ready:false}});
    api.physicalMission.mockImplementation(()=>new Promise<PhysicalState>(r=>{resolve=r;}));
    const view=render(<PhysicalRobotController api={api as unknown as TwinPulseApi}/>);
    await waitFor(()=>expect((screen.getByLabelText('Mission waypoints XY') as HTMLTextAreaElement).disabled).toBe(false));
    fireEvent.change(screen.getByLabelText('Mission waypoints XY'),{target:{value:'[[0.04,0]]'}});
    fireEvent.click(screen.getByRole('checkbox'));fireEvent.click(screen.getByText('Start approved mission'));
    const id=api.physicalMission.mock.calls[0][1];
    if(reason==='blur')fireEvent(window,new Event('blur'));
    if(reason==='escape')fireEvent.keyDown(screen.getByRole('region',{name:'Physical controller'}),{key:'Escape'});
    if(reason==='backend')view.rerender(<PhysicalRobotController api={api as unknown as TwinPulseApi} backendReady={false}/>);
    if(reason==='unmount')view.unmount();
    await act(async()=>resolve({state:'READY',mode:'mission',busy:true,owned:true,job_id:id,sequence:0}));
    await waitFor(()=>expect(api.physicalInput.mock.calls.some(c=>c[0]===id&&c[2]==='close')).toBe(true));
    expect(api.physicalInput.mock.calls.every(c=>c[2]==='close')).toBe(true);
    expect(api.physicalMission).toHaveBeenCalledTimes(1);
  });
  it.each(['blur','escape','backend','unmount'])('requires fresh manual intent after a delayed start and %s',async(reason)=>{
    const api=mock();let resolve!:(s:PhysicalState)=>void;
    api.physicalStart.mockImplementation(()=>new Promise<PhysicalState>(r=>{resolve=r;}));
    const view=render(<PhysicalRobotController api={api as unknown as TwinPulseApi}/>);
    fireEvent.click(screen.getByRole('checkbox'));fireEvent.click(screen.getByText('3. Connect manual control'));
    const id=api.physicalStart.mock.calls[0][1];
    if(reason==='blur')fireEvent(window,new Event('blur'));
    if(reason==='escape')fireEvent.keyDown(screen.getByRole('region',{name:'Physical controller'}),{key:'Escape'});
    if(reason==='backend')view.rerender(<PhysicalRobotController api={api as unknown as TwinPulseApi} backendReady={false}/>);
    if(reason==='unmount')view.unmount();
    const late:PhysicalState={state:'READY',mode:'control',busy:true,owned:true,job_id:id,sequence:0};
    await act(async()=>resolve(late));
    const expected=reason==='escape'?'close':'stop';
    await waitFor(()=>expect(api.physicalInput.mock.calls.some(c=>c[0]===id&&c[2]===expected)).toBe(true));
    if(reason!=='unmount'){
      expect((screen.getByText('↑ Forward') as HTMLButtonElement).disabled).toBe(reason!=='blur');
      api.physicalState.mockResolvedValue(late);
      if(reason==='backend')view.rerender(<PhysicalRobotController api={api as unknown as TwinPulseApi} backendReady/>);
      fireEvent.click(screen.getByText('Refresh results · read-only'));
      await act(async()=>{await new Promise(r=>setTimeout(r,220));});
      expect((screen.getByText('↑ Forward') as HTMLButtonElement).disabled).toBe(reason!=='blur');
    }
    expect(api.physicalInput.mock.calls.every(c=>[expected,'watch'].includes(c[2]))).toBe(true);
    expect(api.physicalStart).toHaveBeenCalledTimes(1);
  });
  it('cannot approve or start while backend is unavailable',()=>{
    const api=mock();render(<PhysicalRobotController api={api as unknown as TwinPulseApi} backendReady={false}/>);
    expect((screen.getByRole('checkbox') as HTMLInputElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole('checkbox'));fireEvent.click(screen.getByText('3. Connect manual control'));
    expect(api.physicalStart).not.toHaveBeenCalled();
  });
  it('shows saved prefix and command/observation boundaries without authorizing motion',async()=>{
    const api=mock();api.physicalState.mockResolvedValue({state:'FAILED',busy:false,real_transport:false,
      session_log_complete:false,session_storage:{accepted:15,saved:12,error:'JOURNAL_WRITE_FAILED'},
      session_evidence:{pc_received:5,pipe_written:4,robot_accepted:3,robot_published:1,observations:2,
        last_observation:{t:1,encoders:[10,11],torque:false,source_age_s:.02},floor_pose_measured:false,physical_success:null}});
    render(<PhysicalRobotController api={api as unknown as TwinPulseApi}/>);
    await waitFor(()=>expect(screen.getByText(/12 \/ 15 saved/)).toBeTruthy());
    expect(screen.getByText(/Input received 5 · transmitted 4 · robot accepted 3 · ROS published 1 · observed 2/)).toBeTruthy();
    expect(screen.getByText(/encoder 10 \/ 11/)).toBeTruthy();
    expect(screen.getByRole('alert').textContent).toContain('JOURNAL_WRITE_FAILED');
    expect((screen.getByText('↑ Forward') as HTMLButtonElement).disabled).toBe(true);
    expect(api.physicalStart).not.toHaveBeenCalled();expect(api.physicalInput).not.toHaveBeenCalled();
  });
  it('focuses the ready pad and accepts Korean-layout physical keys without reconnecting',async()=>{
    const api=mock();render(<PhysicalRobotController api={api as unknown as TwinPulseApi}/>);
    fireEvent.click(screen.getByRole('checkbox'));fireEvent.click(screen.getByText('3. Connect manual control'));
    const panel=screen.getByRole('region',{name:'Physical controller'});
    await waitFor(()=>expect(document.activeElement).toBe(panel));
    fireEvent.keyDown(panel,{key:'ㅈ',code:'KeyW'});fireEvent.keyUp(panel,{key:'ㅈ',code:'KeyW'});
    fireEvent.keyDown(panel,{key:'ㅁ',code:'KeyA'});fireEvent.keyUp(panel,{key:'ㅁ',code:'KeyA'});
    await waitFor(()=>expect(api.physicalInput.mock.calls.map(c=>c[2])).toContain('left'));
    expect(api.physicalInput.mock.calls.map(c=>c[2])).toContain('forward');
    expect(api.physicalInput.mock.calls.map(c=>c[2]).filter(a=>a==='stop')).toHaveLength(2);
    expect(api.physicalStart).toHaveBeenCalledTimes(1);
  });
  it('reads saved state only after backend authentication without starting transport',async()=>{
    const api=mock();
    const view=render(<PhysicalRobotController api={api as unknown as TwinPulseApi} backendReady={false}/>);
    expect(api.physicalState).not.toHaveBeenCalled();
    view.rerender(<PhysicalRobotController api={api as unknown as TwinPulseApi} backendReady/>);
    await waitFor(()=>expect(api.physicalState).toHaveBeenCalledTimes(1));
    expect(api.physicalStart).not.toHaveBeenCalled();expect(api.physicalInput).not.toHaveBeenCalled();
  });
  it('keeps historical PASS distinct from failed cleanup and never unlocks',async()=>{
    const api=mock();api.physicalState.mockResolvedValue({state:'FINISHED',mode:'control',busy:false,
      result:'FAILED',reason:'PHYSICAL_STOP_NOT_QUALIFIED_FOR_THIS_BOOT_RELEASE',cleanup_confirmed:true,
      last_trial:{historical:true,job_id:'prior',status:'FINAL_IDLE_UNCONFIRMED',cleanup_confirmed:false,
        cleanup_stage:'independent_torque_off',cleanup_error:'helper exit=3',stop_assessment:{
          policy_id:'supervised-stop-2.0',status:'PASS',reason:'',checks:{},metrics:{wheel_travel_mm:[3.19,3.29]},
          limits:{deceleration_budget_s:.5,verification_s:.3,wheel_travel_limit_mm:10,residual_rate_limit_mm_s:1}}}});
    render(<PhysicalRobotController api={api as unknown as TwinPulseApi}/>);
    fireEvent.click(screen.getByText('Refresh results · read-only'));
    await waitFor(()=>expect(screen.getByText(/Stop metrics PASS \/ cleanup confirmation failed/)).toBeTruthy());
    expect(screen.getByText(/This is a recently saved stop test/)).toBeTruthy();
    expect(screen.getByText(/helper exit=3/)).toBeTruthy();
    expect((screen.getByText('↑ Forward') as HTMLButtonElement).disabled).toBe(true);
    expect(api.physicalStart).not.toHaveBeenCalled();expect(api.physicalInput).not.toHaveBeenCalled();
  });
  it('shows new physical-unit metrics without treating replay as permission',async()=>{
    const api=mock();api.physicalState.mockResolvedValue({state:'FINISHED',mode:'qualify',busy:false,
      result:'STOP_POLICY_FAIL',cleanup_confirmed:true,stop_assessment:{policy_id:'supervised-stop-2.0',
        status:'INCOMPLETE',reason:'OBSERVATION_WINDOW_INCOMPLETE',checks:{},
        metrics:{guard_observation_ms:410},limits:{deceleration_budget_s:.5,verification_s:.3,
          wheel_travel_limit_mm:10,residual_rate_limit_mm_s:1}}});
    render(<PhysicalRobotController api={api as unknown as TwinPulseApi}/>);
    fireEvent.click(screen.getByText('Refresh results · read-only'));
    await waitFor(()=>expect(screen.getByLabelText('Separated stop assessment')).toBeTruthy());
    expect(screen.getByText(/Command-blocking observation: 410ms/)).toBeTruthy();
    expect(screen.getByText(/actual body stopping are not measured/)).toBeTruthy();
    expect((screen.getByText('↑ Forward') as HTMLButtonElement).disabled).toBe(true);
    expect(api.physicalInput).not.toHaveBeenCalled();
  });
  it('explains measured failure separately from final OFF without enabling motion',async()=>{
    const api=mock();api.physicalState.mockResolvedValue({state:'FINISHED',mode:'qualify',busy:false,
      result:'SETTLING_FAIL',cleanup_confirmed:true,stop_diagnostics:{stable_ms:90.767942,
        required_stable_ms:200,window_ms:500,reason:'ENCODER_SETTLING_SHORT'}});
    render(<PhysicalRobotController api={api as unknown as TwinPulseApi}/>);
    fireEvent.click(screen.getByText('Refresh results · read-only'));
    await waitFor(()=>expect(screen.getByText(/stable duration 90.8ms/)).toBeTruthy());
    expect(screen.getByRole('alert').textContent).toContain('Do not repeat the same test');
    expect(screen.getByText('Independent Motor OFF and idle observation after completion: confirmed')).toBeTruthy();
    expect((screen.getByText('↑ Forward') as HTMLButtonElement).disabled).toBe(true);
    expect(api.physicalStart).not.toHaveBeenCalled();
  });
  it('never connects on mount and requires operation confirmation',()=>{
    const api=mock();render(<PhysicalRobotController api={api as unknown as TwinPulseApi}/>);
    expect(api.physicalStart).not.toHaveBeenCalled();
    expect((screen.getByText('3. Connect manual control') as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByText('↑ Forward') as HTMLButtonElement).disabled).toBe(true);
  });
  it('uses the adapter contract and release/blur stop motion while retaining manual connection',async()=>{
    const api=mock();render(<PhysicalRobotController api={api as unknown as TwinPulseApi}/>);
    fireEvent.click(screen.getByRole('checkbox'));fireEvent.click(screen.getByText('3. Connect manual control'));
    await waitFor(()=>expect((screen.getByText('↑ Forward') as HTMLButtonElement).disabled).toBe(false));
    const panel=screen.getByRole('region',{name:'Physical controller'});
    fireEvent.keyDown(panel,{key:'w'});fireEvent.keyUp(panel,{key:'w'});
    await waitFor(()=>expect(api.physicalInput.mock.calls.map(c=>c[2])).toContain('forward'));
    expect(api.physicalInput.mock.calls.map(c=>c[2])).toContain('stop');
    fireEvent(window,new Event('blur'));
    await waitFor(()=>expect(api.physicalInput.mock.calls.filter(c=>c[2]==='stop').length).toBeGreaterThanOrEqual(2));
    expect(api.physicalInput.mock.calls.map(c=>c[2])).not.toContain('close');
  });
  it('result refresh cannot arm or renew an existing session',async()=>{
    const api=mock();api.physicalState.mockResolvedValue({state:'READY',mode:'control',busy:true,owned:true,job_id:'old'});
    render(<PhysicalRobotController api={api as unknown as TwinPulseApi}/>);
    fireEvent.click(screen.getByText('Refresh results · read-only'));
    await waitFor(()=>expect(screen.getByText('Robot-side preparation complete')).toBeTruthy());
    expect((screen.getByText('↑ Forward') as HTMLButtonElement).disabled).toBe(true);
    await new Promise(resolve=>setTimeout(resolve,230));
    expect(api.physicalInput).not.toHaveBeenCalled();
  });
  it.each(['window blur','panel blur','visibility','pointer cancel','unmount'])('pauses manual movement on %s and retains connection',async(reason)=>{
    const h=continuousMock(),{view,panel}=await connectContinuous(h);
    fireEvent.keyDown(panel,{key:'w',code:'KeyW'});
    if(reason==='window blur')fireEvent.blur(window);
    if(reason==='panel blur')fireEvent.blur(panel,{relatedTarget:document.body});
    if(reason==='visibility'){vi.spyOn(document,'visibilityState','get').mockReturnValue('hidden');fireEvent(document,new Event('visibilitychange'));}
    if(reason==='pointer cancel')fireEvent.pointerCancel(screen.getByText('↑ Forward'));
    if(reason==='unmount')view.unmount();
    await waitFor(()=>expect(h.api.physicalInput.mock.calls.some(call=>call[2]==='stop')).toBe(true));
    expect(h.api.physicalInput.mock.calls.some(call=>call[2]==='close')).toBe(false);
    const directions=h.api.physicalInput.mock.calls.filter(call=>call[2]==='forward').length;
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve,240));});
    expect(h.api.physicalInput.mock.calls.filter(call=>call[2]==='forward')).toHaveLength(directions);
    expect(h.api.physicalStart).toHaveBeenCalledTimes(1);
  });
  it('still closes manual control after explicit Disconnect',async()=>{
    const h=continuousMock();await connectContinuous(h);
    fireEvent.click(screen.getByRole('button',{name:'Disconnect manual control'}));
    await waitFor(()=>expect(h.api.physicalInput.mock.calls.some(call=>call[2]==='close')).toBe(true));
  });
  it('does not serialize 100ms held input behind pending HTTP and discards late replies after release',async()=>{
    const h=continuousMock();const replies:((state:PhysicalState)=>void)[]=[];
    h.api.physicalInput.mockImplementation(async(_id:string,sequence:number,action:string)=>{
      if(action==='forward')return new Promise<PhysicalState>(resolve=>replies.push(resolve));
      const next={...h.get(),sequence};h.set(next);return next;
    });
    const {panel}=await connectContinuous(h);fireEvent.keyDown(panel,{key:'w',code:'KeyW'});
    await waitFor(()=>expect(h.api.physicalInput.mock.calls.filter(call=>call[2]==='forward').length).toBeGreaterThanOrEqual(3));
    fireEvent.keyUp(window,{key:'w',code:'KeyW'});
    await waitFor(()=>expect(h.api.physicalInput.mock.calls.some(call=>call[2]==='stop')).toBe(true));
    const count=h.api.physicalInput.mock.calls.filter(call=>call[2]==='forward').length;
    await act(async()=>{for(const reply of replies)reply({...h.get(),sequence:1000,pause_reason:'OLD_REPLY'});});
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve,250));});
    expect(h.api.physicalInput.mock.calls.filter(call=>call[2]==='forward')).toHaveLength(count);
    expect(screen.queryByText(/OLD_REPLY/)).toBeNull();
    expect(h.api.physicalInput.mock.calls.some(call=>call[2]==='close')).toBe(false);
  });
  it('a status read failure stops movement, keeps the session, and recovery requires a fresh press',async()=>{
    const h=continuousMock();let failing=false;
    h.api.physicalState.mockImplementation(async()=>{if(failing)throw new Error('read delayed');return h.get();});
    const {panel}=await connectContinuous(h);fireEvent.keyDown(panel,{key:'w',code:'KeyW'});failing=true;
    await screen.findByText(/Robot status query delayed — movement paused; connection retained/);
    const count=h.api.physicalInput.mock.calls.filter(call=>call[2]==='forward').length;
    expect(h.api.physicalInput.mock.calls.some(call=>call[2]==='stop')).toBe(true);
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve,250));});
    failing=false;await waitFor(()=>expect((screen.getByText('↑ Forward') as HTMLButtonElement).disabled).toBe(false));
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve,220));});
    expect(h.api.physicalInput.mock.calls.filter(call=>call[2]==='forward')).toHaveLength(count);
    expect(h.api.physicalInput.mock.calls.some(call=>call[2]==='close')).toBe(false);
    fireEvent.keyDown(panel,{key:'w',code:'KeyW'});
    await waitFor(()=>expect(h.api.physicalInput.mock.calls.filter(call=>call[2]==='forward').length).toBeGreaterThan(count));
  });
  it.each(['INPUT_DEADLINE_EXPIRED','ARMING'])('discards held direction when a new worker generation reports %s',async(pause)=>{
    const h=continuousMock(),{panel}=await connectContinuous(h);
    fireEvent.keyDown(panel,{key:'w',code:'KeyW'});
    h.set({...h.get(),motion_generation:1,pause_reason:pause});
    await screen.findByText(new RegExp(`Movement paused · ${pause}`));
    const count=h.api.physicalInput.mock.calls.filter(call=>call[2]==='forward').length;
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve,250));});
    expect(h.api.physicalInput.mock.calls.filter(call=>call[2]==='forward')).toHaveLength(count);
    h.set({...h.get(),pause_reason:null});
    fireEvent.keyDown(panel,{key:'w',code:'KeyW'});
    await waitFor(()=>expect(h.api.physicalInput.mock.calls.filter(call=>call[2]==='forward').length).toBeGreaterThan(count));
    expect(h.api.physicalStart).toHaveBeenCalledTimes(1);
    expect(h.api.physicalInput.mock.calls.some(call=>call[2]==='close')).toBe(false);
  });
  it('pauses after uncertain manual input delivery without terminating the session',async()=>{
    const h=continuousMock();let rejectOnce=true;
    h.api.physicalInput.mockImplementation(async(_id:string,sequence:number,action:string)=>{
      if(action==='forward'&&rejectOnce){rejectOnce=false;throw new Error('unknown input delivery');}
      const next={...h.get(),sequence};h.set(next);return next;
    });
    const {panel}=await connectContinuous(h);fireEvent.keyDown(panel,{key:'w',code:'KeyW'});
    await screen.findByText(/Input delivery unverified — movement paused; connection retained/);
    await waitFor(()=>expect(h.api.physicalInput.mock.calls.some(call=>call[2]==='stop')).toBe(true));
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve,250));});
    expect(h.api.physicalInput.mock.calls.filter(call=>call[2]==='forward')).toHaveLength(1);
    expect(h.api.physicalInput.mock.calls.some(call=>call[2]==='close')).toBe(false);
  });
  it('bounds direction HTTP delivery to 250ms without blocking Stop or retrying the old input',async()=>{
    vi.useFakeTimers();const response=(body:object)=>({ok:true,status:200,json:async()=>body,headers:new Headers({'X-TwinPulse-Context':'physical-test'})}) as Response;
    const request=vi.fn(async(path:string,init?:RequestInit)=>{
      if(path==='/v1/product/session')return response({csrf_token:'csrf',context_id:'physical-test',project_id:'default',project_switch:null});
      if(JSON.parse(String(init?.body)).action==='forward')return new Promise<Response>(()=>{});
      return response({state:'READY',mode:'control',busy:true,owned:true,job_id:'job',sequence:2});
    });vi.stubGlobal('fetch',request);const api=new TwinPulseApi();await api.bootstrap();
    const pending=api.physicalInput('job',1,'forward').catch(error=>error);
    await api.physicalInput('job',2,'stop');await vi.advanceTimersByTimeAsync(250);
    expect(await pending).toMatchObject({code:'physical_delivery_unknown'});
    const inputs=request.mock.calls.filter(([path])=>path==='/v1/product/robot/physical/input');
    expect(inputs).toHaveLength(2);expect(inputs[0][1]?.signal?.aborted).toBe(true);
  });
});
