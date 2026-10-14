// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {fireEvent,render,screen,waitFor,cleanup} from '@testing-library/react';
import {afterEach,describe,it,expect,vi} from 'vitest';
import {AutomaticMission} from './AutomaticMission';
import type {TwinPulseApi} from './api';
afterEach(cleanup);
function mock(adapter=true){return {automaticMissionReadiness:vi.fn().mockResolvedValue({room_revision:'b'.repeat(64),photo_status:'ALIGNMENT_CANDIDATE',adapter_available:adapter,next_action:'Fresh sensor matching required'}),
  automaticMissionStart:vi.fn().mockResolvedValue({adapter_available:true,job:{job_id:'c'.repeat(32),state:'LOCALIZING',elapsed_s:0}}),
  automaticMissionState:vi.fn().mockResolvedValue({adapter_available:true,job:{job_id:'c'.repeat(32),state:'DRIVING',elapsed_s:1}}),
  automaticMissionStop:vi.fn().mockResolvedValue({adapter_available:true,job:{job_id:'c'.repeat(32),state:'STOPPING',elapsed_s:1}}),automaticMissionPreview:vi.fn()};}
describe('current observed mission',()=>{
  it('shows a typed geometry failure once and does not reopen a dismissed dialog on duplicate polls',async()=>{
    const api=mock();api.automaticMissionState.mockResolvedValue({adapter_available:true,job:{job_id:'c'.repeat(32),
      state:'DRIVING',elapsed_s:1,photo_correction:{status:'APPLIED',goal_revalidation:'VALIDATED',
        isaac_geometry_status:'ACTIVE_GEOMETRY_RENDER_FAILED',error_code:'ACTIVE_GEOMETRY_PERMIT_EXPIRED',error_type:'ValueError'}}} as never);
    render(<AutomaticMission api={api as unknown as TwinPulseApi} mapId={null} available/>);
    await waitFor(()=>expect((screen.getByText('Start observed mission · maximum 45 s') as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByText('Start observed mission · maximum 45 s'));
    expect((await screen.findByRole('alertdialog')).textContent).toContain('ACTIVE_GEOMETRY_PERMIT_EXPIRED (ValueError)');
    fireEvent.click(screen.getByText('Dismiss'));
    await waitFor(()=>expect(api.automaticMissionState.mock.calls.length).toBeGreaterThanOrEqual(3));
    expect(screen.queryByRole('alertdialog')).toBeNull();expect(api.automaticMissionStart).toHaveBeenCalledTimes(1);
  });
  it('rechecks the effective room revision on each explicit Start without automatically starting',async()=>{
    const api=mock();api.automaticMissionReadiness.mockResolvedValueOnce({room_revision:'b'.repeat(64),photo_status:'ALIGNMENT_CANDIDATE',
      adapter_available:true,next_action:'Fresh sensor matching required'}).mockResolvedValue({room_revision:'e'.repeat(64),photo_status:'ALIGNMENT_CANDIDATE',
      adapter_available:true,next_action:'Fresh sensor matching required'});
    render(<AutomaticMission api={api as unknown as TwinPulseApi} mapId={null} available/>);
    await waitFor(()=>expect((screen.getByText('Start observed mission · maximum 45 s') as HTMLButtonElement).disabled).toBe(false));
    expect(api.automaticMissionStart).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('Start observed mission · maximum 45 s'));
    await waitFor(()=>expect(api.automaticMissionStart).toHaveBeenCalledWith(null,{mode:'SURVEY_THEN_NAVIGATE',xy:[0,0],
      room_revision:'e'.repeat(64),duration_s:45}));
    expect(api.automaticMissionStart).toHaveBeenCalledTimes(1);
  });
  it('submits explicit correction only for an available cold-start adapter',async()=>{
    const api=mock();api.automaticMissionReadiness.mockResolvedValue({room_revision:'b'.repeat(64),photo_status:'NOT_AVAILABLE',
      adapter_available:true,next_action:'Fresh sensor matching required',photo_correction_available:true} as never);
    render(<AutomaticMission api={api as unknown as TwinPulseApi} mapId={null} available/>);
    await waitFor(()=>expect((screen.getByText('Start observed mission · maximum 45 s') as HTMLButtonElement).disabled).toBe(false));
    fireEvent.change(screen.getByLabelText('Photo correction'),{target:{value:'correct_walls'}});
    fireEvent.click(screen.getByText('Start observed mission · maximum 45 s'));
    await waitFor(()=>expect(api.automaticMissionStart).toHaveBeenCalledWith(null,{mode:'SURVEY_THEN_NAVIGATE',xy:[0,0],
      room_revision:'b'.repeat(64),duration_s:45},'correct_walls'));
  });
  it('does not offer correction when the remote acknowledgement is unavailable',async()=>{
    const api=mock();render(<AutomaticMission api={api as unknown as TwinPulseApi} mapId={null} available/>);
    await waitFor(()=>expect((screen.getByText('Start observed mission · maximum 45 s') as HTMLButtonElement).disabled).toBe(false));
    expect((screen.getByText('Correct validated walls · derived revision') as HTMLOptionElement).disabled).toBe(true);
  });
  it('shows both original and cleanup failures even in an immediate terminal response',async()=>{
    const api=mock();api.automaticMissionStart.mockResolvedValue({adapter_available:true,job:{job_id:'c'.repeat(32),
      state:'FAILED',elapsed_s:1,error:'INPUT_DEADLINE_EXPIRED',error_stage:'RUN_CURRENT_MISSION',
      cleanup_error:'OWNED_SENSOR_STOP_UNCONFIRMED',report_status:'SAVED',
      cold_start:{reason:'PHOTO_SOURCE_REVISION_CHANGED',error_stage:'PHOTO_ALIGNMENT',error_type:'ValueError'}}} as never);
    render(<AutomaticMission api={api as unknown as TwinPulseApi} mapId={null} available/>);
    await waitFor(()=>expect((screen.getByText('Start observed mission · maximum 45 s') as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByText('Start observed mission · maximum 45 s'));
    const alert=await screen.findByRole('alertdialog',{name:'Observed mission error'});
    expect(alert.textContent).toContain('RUN_CURRENT_MISSION: INPUT_DEADLINE_EXPIRED');
    expect(alert.textContent).toContain('Cleanup: OWNED_SENSOR_STOP_UNCONFIRMED');
    expect(alert.textContent).toContain('PHOTO_ALIGNMENT: PHOTO_SOURCE_REVISION_CHANGED (ValueError)');
    expect(api.automaticMissionStart).toHaveBeenCalledTimes(1);expect(api.automaticMissionState).not.toHaveBeenCalled();
  });
  it('shows cleanup-only failures from polling and marks unavailable position explicitly',async()=>{
    const api=mock();api.automaticMissionState.mockResolvedValue({adapter_available:true,job:{job_id:'c'.repeat(32),
      state:'FAILED',elapsed_s:1,cleanup_error:'MISSION_ADAPTER_CLEANUP_FAILED',report_status:'SAVED',
      visual:{pose_room:null,goal_room:[0,0],route_room:[],scan_room:[],trajectory_room:[[0,0,0]],revision:'f'.repeat(64)}}} as never);
    render(<AutomaticMission api={api as unknown as TwinPulseApi} mapId={null} available/>);
    await waitFor(()=>expect((screen.getByText('Start observed mission · maximum 45 s') as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByText('Start observed mission · maximum 45 s'));
    expect((await screen.findByRole('alertdialog')).textContent).toContain('Cleanup: MISSION_ADAPTER_CLEANUP_FAILED');
    expect(screen.getByText(/Current room position unavailable/)).toBeTruthy();
    expect(api.automaticMissionStart).toHaveBeenCalledTimes(1);
  });
  it('keeps polling after arrival until the immutable report is saved',async()=>{
    const api=mock();const job={job_id:'c'.repeat(32),state:'MISSION_ARRIVED',elapsed_s:1,report_status:'PENDING',
      visual:{pose_room:[0,0,0],goal_room:[0,0],route_room:[],scan_room:[],trajectory_room:[],revision:'f'.repeat(64)}};
    api.automaticMissionStart.mockResolvedValue({adapter_available:true,job});
    api.automaticMissionState.mockResolvedValue({adapter_available:true,job:{...job,report_status:'SAVED',report_revision:'f'.repeat(64)}});
    render(<AutomaticMission api={api as unknown as TwinPulseApi} mapId={null} available/>);
    await waitFor(()=>expect((screen.getByText('Start observed mission · maximum 45 s') as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByText('Start observed mission · maximum 45 s'));
    await screen.findByText('Motion ended · saving the immutable result…');
    expect((screen.getByText('Show saved mission in Isaac 3D') as HTMLButtonElement).disabled).toBe(true);
    await waitFor(()=>expect((screen.getByText('Show saved mission in Isaac 3D') as HTMLButtonElement).disabled).toBe(false));
    expect(api.automaticMissionState).toHaveBeenCalled();expect(api.automaticMissionStart).toHaveBeenCalledTimes(1);
  });
  it('separates a report storage failure from the primary motion error without retrying motion',async()=>{
    const api=mock();api.automaticMissionState.mockResolvedValue({adapter_available:true,job:{job_id:'c'.repeat(32),
      state:'FAILED',elapsed_s:1,error:'BATTERY_BUTTON_OR_SOURCE_AGE',error_stage:'RUN_CURRENT_MISSION',
      report_status:'FAILED',report_error:'MISSION_REPORT_STORAGE_FULL',report_stage:'REPORT_SAVE',
      report_error_type:'OSError',report_errno:28,visual:{pose_room:null,goal_room:[0,0],route_room:[],
        scan_room:[],trajectory_room:[[0,0,0]],revision:'f'.repeat(64)}}} as never);
    render(<AutomaticMission api={api as unknown as TwinPulseApi} mapId={null} available/>);
    await waitFor(()=>expect((screen.getByText('Start observed mission · maximum 45 s') as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByText('Start observed mission · maximum 45 s'));
    const alert=await screen.findByRole('alertdialog',{name:'Observed mission error'});
    expect(alert.textContent).toContain('RUN_CURRENT_MISSION: BATTERY_BUTTON_OR_SOURCE_AGE');
    expect(alert.textContent).toContain('REPORT_SAVE: MISSION_REPORT_STORAGE_FULL (OSError, errno 28)');
    expect(screen.getByText(/Current room position unavailable/)).toBeTruthy();
    expect((screen.getByText('Show saved mission in Isaac 3D') as HTMLButtonElement).disabled).toBe(true);
    expect(api.automaticMissionStart).toHaveBeenCalledTimes(1);
  });
  it('reports late storage failure after arrival rather than displaying an unsaved success',async()=>{
    const api=mock();api.automaticMissionStart.mockResolvedValue({adapter_available:true,job:{job_id:'c'.repeat(32),
      state:'MISSION_ARRIVED',elapsed_s:1,report_status:'PENDING'}} as never);
    api.automaticMissionState.mockResolvedValue({adapter_available:true,job:{job_id:'c'.repeat(32),state:'FAILED',elapsed_s:1,
      error:'MISSION_REPORT_PERMISSION_DENIED',error_stage:'REPORT_SAVE',report_status:'FAILED',
      report_error:'MISSION_REPORT_PERMISSION_DENIED',report_stage:'REPORT_SAVE',report_error_type:'PermissionError',report_errno:13}} as never);
    render(<AutomaticMission api={api as unknown as TwinPulseApi} mapId={null} available/>);
    await waitFor(()=>expect((screen.getByText('Start observed mission · maximum 45 s') as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByText('Start observed mission · maximum 45 s'));
    const alert=await screen.findByRole('alertdialog');
    expect(alert.textContent).toContain('MISSION_REPORT_PERMISSION_DENIED (PermissionError, errno 13)');
    expect(alert.textContent?.match(/MISSION_REPORT_PERMISSION_DENIED/g)).toHaveLength(1);
    expect((screen.getByText('Show saved mission in Isaac 3D') as HTMLButtonElement).disabled).toBe(true);
    expect(api.automaticMissionStart).toHaveBeenCalledTimes(1);
  });
  it('cold-start survey and photo alignment starts without a saved map, not a restored room pose',async()=>{
    const api=mock();render(<AutomaticMission api={api as unknown as TwinPulseApi} mapId={null} available/>);
    await waitFor(()=>expect((screen.getByText('Start observed mission · maximum 45 s') as HTMLButtonElement).disabled).toBe(false));
    expect(api.automaticMissionReadiness).toHaveBeenCalledWith(null);
    expect((screen.getByLabelText('Mission mode') as HTMLSelectElement).value).toBe('SURVEY_THEN_NAVIGATE');
    fireEvent.click(screen.getByText('Start observed mission · maximum 45 s'));
    await screen.findByText('LOCALIZING · PC runtime 0.0 s');
    expect(api.automaticMissionStart).toHaveBeenCalledWith(null,{mode:'SURVEY_THEN_NAVIGATE',xy:[0,0],room_revision:'b'.repeat(64),duration_s:45});
  });
  it('waits for the actual Isaac lease snapshot before a single visual submission',async()=>{
    const api={...mock(),acquireLease:vi.fn().mockResolvedValue({}),productState:vi.fn()
      .mockResolvedValueOnce({operations:[],engine_readiness:{automatic_mission_visual_v1:{ready:false,code:'runtime_command_unavailable'}}})
      .mockResolvedValue({operations:[],engine_readiness:{automatic_mission_visual_v1:{ready:true,code:'ready'}}})};
    api.automaticMissionStart.mockResolvedValue({adapter_available:true,job:{job_id:'c'.repeat(32),state:'MISSION_ARRIVED',elapsed_s:1,report_revision:'f'.repeat(64),visual:{pose_room:[0,0,0],goal_room:[0,0],route_room:[],scan_room:[],trajectory_room:[],revision:'f'.repeat(64)}}});
    api.automaticMissionPreview.mockResolvedValue({command_id:'visual',status:'succeeded'});
    render(<AutomaticMission api={api as unknown as TwinPulseApi} mapId={'a'.repeat(32)} available/>);
    await waitFor(()=>expect((screen.getByText('Start observed mission · maximum 45 s') as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByText('Start observed mission · maximum 45 s'));await screen.findByText('MISSION_ARRIVED · PC runtime 1.0 s');
    expect(screen.getByText(/PC runtime is wall time, not the adapter-clock mission budget/)).toBeTruthy();
    fireEvent.click(screen.getByText('Show saved mission in Isaac 3D'));
    await screen.findByText('Isaac saved visual is ready. This is not physical execution.');
    expect(api.productState).toHaveBeenCalledTimes(2);expect(api.automaticMissionPreview).toHaveBeenCalledTimes(1);
  });
  it.each(['succeeded','failed'])('polls an accepted visual operation to its actual %s receipt without resubmitting',async outcome=>{
    const api={...mock(),acquireLease:vi.fn().mockResolvedValue({}),productState:vi.fn()
      .mockResolvedValueOnce({operations:[],engine_readiness:{automatic_mission_visual_v1:{ready:true,code:'ready'}}})
      .mockResolvedValueOnce({operations:[{command_id:'other',status:'succeeded'},{command_id:'visual',status:'claimed'}]})
      .mockResolvedValueOnce({operations:[{command_id:'visual',status:'running'}]})
      .mockResolvedValue({operations:[{command_id:'visual',status:outcome}]})};
    api.automaticMissionStart.mockResolvedValue({adapter_available:true,job:{job_id:'c'.repeat(32),state:'MISSION_ARRIVED',elapsed_s:1,
      report_revision:'f'.repeat(64),visual:{pose_room:[0,0,0],goal_room:[0,0],route_room:[],scan_room:[],trajectory_room:[],revision:'f'.repeat(64)}}});
    api.automaticMissionPreview.mockResolvedValue({command_id:'visual',status:'accepted'});
    render(<AutomaticMission api={api as unknown as TwinPulseApi} mapId={null} available/>);
    await waitFor(()=>expect((screen.getByText('Start observed mission · maximum 45 s') as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByText('Start observed mission · maximum 45 s'));await screen.findByText('MISSION_ARRIVED · PC runtime 1.0 s');
    fireEvent.click(screen.getByText('Show saved mission in Isaac 3D'));
    await screen.findByText('Isaac visual operation: accepted…');
    expect(screen.queryByRole('alertdialog')).toBeNull();
    expect((screen.getByText('Show saved mission in Isaac 3D') as HTMLButtonElement).disabled).toBe(true);
    if(outcome==='succeeded')await screen.findByText('Isaac saved visual is ready. This is not physical execution.',{}, {timeout:4000});
    else expect((await screen.findByRole('alertdialog',{}, {timeout:4000})).textContent).toContain('Isaac visual operation failed.');
    expect(api.automaticMissionPreview).toHaveBeenCalledTimes(1);expect(api.productState).toHaveBeenCalledTimes(4);
    expect(api.automaticMissionStart).toHaveBeenCalledTimes(1);
  });
  it('evidence selection change force-stops an active owner without carrying over a pose',async()=>{
    const api=mock();const props={api:api as unknown as TwinPulseApi,available:true};
    const {rerender}=render(<AutomaticMission {...props} mapId={'a'.repeat(32)}/>);
    await waitFor(()=>expect((screen.getByText('Start observed mission · maximum 45 s') as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByText('Start observed mission · maximum 45 s'));await screen.findByText('LOCALIZING · PC runtime 0.0 s');
    rerender(<AutomaticMission {...props} mapId={'d'.repeat(32)}/>);
    await waitFor(()=>expect(api.automaticMissionStop).toHaveBeenCalledWith('c'.repeat(32),true));
    expect(api.automaticMissionStart).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('LOCALIZING · PC runtime 0.0 s')).toBeNull();
  });
  it('late start after evidence change is stopped rather than silently abandoned',async()=>{
    const api=mock();let resolve:(v:unknown)=>void=()=>{};
    api.automaticMissionStart.mockImplementation(()=>new Promise(r=>{resolve=r;}));
    const props={api:api as unknown as TwinPulseApi,available:true};
    const {rerender}=render(<AutomaticMission {...props} mapId={'a'.repeat(32)}/>);
    await waitFor(()=>expect((screen.getByText('Start observed mission · maximum 45 s') as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByText('Start observed mission · maximum 45 s'));
    await waitFor(()=>expect(api.automaticMissionStart).toHaveBeenCalledTimes(1));
    rerender(<AutomaticMission {...props} mapId={'d'.repeat(32)}/>);
    resolve({adapter_available:true,job:{job_id:'c'.repeat(32),state:'LOCALIZING',elapsed_s:0}});
    await waitFor(()=>expect(api.automaticMissionStop).toHaveBeenCalledWith('c'.repeat(32),true));
    expect(screen.queryByText('LOCALIZING · PC runtime 0.0 s')).toBeNull();
  });
  it('late readiness after evidence change never submits a mission',async()=>{
    const api=mock();let resolve:(v:unknown)=>void=()=>{};
    const props={api:api as unknown as TwinPulseApi,available:true};
    const {rerender}=render(<AutomaticMission {...props} mapId={'a'.repeat(32)}/>);
    await waitFor(()=>expect((screen.getByText('Start observed mission · maximum 45 s') as HTMLButtonElement).disabled).toBe(false));
    api.automaticMissionReadiness.mockImplementationOnce(()=>new Promise(r=>{resolve=r;}) as never);
    fireEvent.click(screen.getByText('Start observed mission · maximum 45 s'));
    rerender(<AutomaticMission {...props} mapId={'d'.repeat(32)}/>);
    resolve({room_revision:'e'.repeat(64),photo_status:'ALIGNMENT_CANDIDATE',adapter_available:true,next_action:'Fresh sensor matching required'});
    await waitFor(()=>expect((screen.getByText('Start observed mission · maximum 45 s') as HTMLButtonElement).disabled).toBe(false));
    expect(api.automaticMissionStart).not.toHaveBeenCalled();expect(api.automaticMissionStop).not.toHaveBeenCalled();
  });
  it('no configured adapter never enables movement from a saved PASS',async()=>{
    const api=mock(false);render(<AutomaticMission api={api as unknown as TwinPulseApi} mapId={'a'.repeat(32)} available/>);
    await screen.findByText(/No qualified live adapter configured/);
    expect((screen.getByText('Start observed mission · maximum 45 s') as HTMLButtonElement).disabled).toBe(true);
    expect(api.automaticMissionStart).not.toHaveBeenCalled();
  });
  it('one goal start, ordinary Stop and independent Force STOP while stopping',async()=>{
    const api=mock();render(<AutomaticMission api={api as unknown as TwinPulseApi} mapId={'a'.repeat(32)} available/>);
    await waitFor(()=>expect((screen.getByText('Start observed mission · maximum 45 s') as HTMLButtonElement).disabled).toBe(false));
    fireEvent.change(screen.getByLabelText('Goal X (m)'),{target:{value:'.3'}});
    fireEvent.click(screen.getByText('Start observed mission · maximum 45 s'));
    await screen.findByText('LOCALIZING · PC runtime 0.0 s');
    expect(api.automaticMissionStart).toHaveBeenCalledWith('a'.repeat(32),{mode:'NAVIGATE_TWIN_GOAL',xy:[.3,0],room_revision:'b'.repeat(64),duration_s:45});
    fireEvent.click(screen.getByText('Stop after current command'));await screen.findByText('STOPPING · PC runtime 1.0 s');
    fireEvent.click(screen.getByText('Force STOP'));await waitFor(()=>expect(api.automaticMissionStop).toHaveBeenCalledWith('c'.repeat(32),true));
    expect(api.automaticMissionStart).toHaveBeenCalledTimes(1);
  });
  it('explicit error dialog and Escape stop, not automatic resume',async()=>{
    const api=mock();render(<AutomaticMission api={api as unknown as TwinPulseApi} mapId={'a'.repeat(32)} available/>);
    await waitFor(()=>expect((screen.getByText('Start observed mission · maximum 45 s') as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByText('Start observed mission · maximum 45 s'));await screen.findByText('LOCALIZING · PC runtime 0.0 s');
    api.automaticMissionStop.mockRejectedValueOnce(Error('INPUT_DEADLINE_EXPIRED'));
    fireEvent.click(screen.getByText('Force STOP'));await screen.findByRole('alertdialog',{name:'Observed mission error'});
    fireEvent.keyDown(window,{key:'Escape'});await waitFor(()=>expect(api.automaticMissionStop).toHaveBeenCalledTimes(2));
    expect(api.automaticMissionStart).toHaveBeenCalledTimes(1);
  });
});
