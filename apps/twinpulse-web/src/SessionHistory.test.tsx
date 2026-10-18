// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { TwinPulseApi } from './api';
import { SessionHistory } from './SessionHistory';

function fixture(){return {
  physicalSessions:vi.fn().mockResolvedValue({sessions:[{job_id:'a'.repeat(32),modified_s:1}],historical:true,motion_authorized:false}),
  physicalSession:vi.fn().mockResolvedValue({job_id:'a'.repeat(32),provenance:'SYNTHETIC_TRANSPORT',record_status:'INCOMPLETE_RECORD',
    partial_tail_excluded:true,pc_received:4,pipe_written:3,robot_accepted:2,published_count:1,observation_count:0,commands_omitted:0,
    commands:[{sequence:3,action:'forward',robot_t:10,linear_m_s:.03,angular_rad_s:0,source_age_s:.01,next_observation:null}]}),
  physicalStart:vi.fn(),physicalInput:vi.fn(),physicalResumeEvidence:vi.fn(),physicalReviewEvidence:vi.fn(),physicalState:vi.fn(),
};}
describe('saved session history',()=>{
  it('replays a saved timeline and compares counts without claiming matched conditions or motion authority',async()=>{
    const api=fixture(),first='a'.repeat(32),second='b'.repeat(32);
    const base=await api.physicalSession();
    api.physicalSessions.mockResolvedValue({sessions:[{job_id:first,modified_s:2},{job_id:second,modified_s:1}],historical:true,motion_authorized:false});
    api.physicalSession.mockImplementation(async(job:string)=>({...base,job_id:job,project_id:'default',attribution:'BOUND',
      published_count:job===first?1:2,
      comparison_evidence:{app_context_capture:'CAPTURED',app_scene_revision:job===first?'a'.repeat(64):'b'.repeat(64),
        app_robot_profile_id:'turtlebot3_burger',mission_scope_sha256:null,
        robot_boot_id:'boot-a',robot_release_id:null,room_odom_alignment:'UNVERIFIED'},
      timeline:[{event_index:1,pc_t:100,robot_t:10,clock_domain:'pc_monotonic',kind:'published',sequence:1,
        action:'forward',linear_m_s:.03,angular_rad_s:0,encoders:null,odom_xy_m:null,observation_gap:true},
        {event_index:2,pc_t:101,robot_t:11,clock_domain:'pc_monotonic',kind:'robot_finished',sequence:null,
        action:null,linear_m_s:null,angular_rad_s:null,encoders:null,odom_xy_m:null,observation_gap:false}]}));
    render(<SessionHistory api={api as unknown as TwinPulseApi} disabled={false}/>);
    fireEvent.click(screen.getByText('Load saved history'));
    fireEvent.click(await screen.findByRole('button',{name:'Record '+first}));
    await screen.findByLabelText('Saved session replay');
    expect(screen.getByText(/no following encoder observation within 0.5 s/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Replay position'),{target:{value:'1'}});
    await waitFor(()=>expect(screen.getByText(/event 2 \/ 2: robot_finished/)).toBeTruthy());
    fireEvent.change(screen.getByLabelText('Second saved session'),{target:{value:second}});
    await screen.findByText(/Outcome ranking is disabled/);
    expect(screen.getByRole('table',{name:'Recorded comparison conditions'}).textContent).toContain('Recorded mismatch');
    expect(screen.getByRole('table',{name:'Recorded comparison conditions'}).textContent).toContain('Recorded match');
    expect(screen.getByRole('table',{name:'Recorded comparison conditions'}).textContent).toContain('Not recorded for both');
    expect(api.physicalStart).not.toHaveBeenCalled();expect(api.physicalInput).not.toHaveBeenCalled();
  });
  it('discards a pending comparison when control disables history',async()=>{
    const api=fixture(),first='a'.repeat(32),second='b'.repeat(32);
    const record=await api.physicalSession();
    let resolveSecond!:(value:unknown)=>void;
    api.physicalSessions.mockResolvedValue({sessions:[{job_id:first,modified_s:2},{job_id:second,modified_s:1}],historical:true,motion_authorized:false});
    api.physicalSession.mockImplementation((job:string)=>job===second?
      new Promise(resolve=>{resolveSecond=resolve}):Promise.resolve({...record,job_id:first}));
    const {rerender}=render(<SessionHistory api={api as unknown as TwinPulseApi} disabled={false}/>);
    fireEvent.click(screen.getByText('Load saved history'));
    fireEvent.click(await screen.findByRole('button',{name:'Record '+first}));
    await screen.findByLabelText('Saved session details');
    fireEvent.change(screen.getByLabelText('Second saved session'),{target:{value:second}});
    rerender(<SessionHistory api={api as unknown as TwinPulseApi} disabled/>);
    resolveSecond({job_id:second,provenance:'SYNTHETIC_TRANSPORT',published_count:2,
      observation_count:0,recorded_end:null,comparison_evidence:{}});
    await waitFor(()=>expect(screen.queryByLabelText('Saved session details')).toBeNull());
    expect(screen.queryByText(/Outcome ranking is disabled/)).toBeNull();
  });
  it('shows recorded autonomous decisions without starting or authorizing a mission',async()=>{
    const api=fixture();const record=await api.physicalSession();
    api.physicalSession.mockResolvedValue({...record,mission_events:[{kind:'mission_decision',t:10,
      data:{mission_id:'a'.repeat(32),tick:7,status:'RUNNING',decision:{reason:'CLEAR_IN_SCAN_ENVELOPE',
        linear_m_s:.03,angular_rad_s:0,navigation:{pose_xy_yaw:[.1,.2,0]}}}}],mission_events_omitted:0});
    render(<SessionHistory api={api as unknown as TwinPulseApi} disabled={false}/>);
    fireEvent.click(screen.getByText('Load saved history'));
    fireEvent.click(await screen.findByRole('button',{name:'Record '+'a'.repeat(32)}));
    await screen.findByLabelText('Saved autonomous decisions');
    expect(screen.getByText('CLEAR_IN_SCAN_ENVELOPE / RUNNING')).toBeTruthy();
    expect(screen.getByText('0.100 / 0.200 / 0.000')).toBeTruthy();
    expect(screen.getByText(/Not current execution status or proof of physical success/)).toBeTruthy();
    expect(api.physicalStart).not.toHaveBeenCalled();expect(api.physicalInput).not.toHaveBeenCalled();
  });
  it('loads explicitly and keeps missing observations/incomplete evidence separate from control',async()=>{
    const api=fixture();render(<SessionHistory api={api as unknown as TwinPulseApi} disabled={false}/>);
    expect(api.physicalSessions).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('Load saved history'));
    fireEvent.click(await screen.findByRole('button',{name:'Record '+'a'.repeat(32)}));
    await screen.findByText(/Synthetic transport record · Incomplete record/);
    expect(screen.getByText('Recorded ending: No ending observed')).toBeTruthy();
    expect(screen.getByText('Pose/scan records 0 · pose received 0 · scan received 0')).toBeTruthy();
    expect(screen.getByText('No observation')).toBeTruthy();expect(screen.getByText(/An incomplete final row was excluded/)).toBeTruthy();
    expect(api.physicalStart).not.toHaveBeenCalled();expect(api.physicalInput).not.toHaveBeenCalled();
  });
  it('clears old detail on failed re-read and does not retry',async()=>{
    const api=fixture();render(<SessionHistory api={api as unknown as TwinPulseApi} disabled={false}/>);
    fireEvent.click(screen.getByText('Load saved history'));
    const item=await screen.findByRole('button',{name:'Record '+'a'.repeat(32)});fireEvent.click(item);
    await screen.findByText('No observation');api.physicalSession.mockRejectedValueOnce(new Error('invalid'));
    fireEvent.click(item);await screen.findByRole('alert');
    expect(screen.queryByLabelText('Saved session details')).toBeNull();expect(api.physicalSession).toHaveBeenCalledTimes(2);
  });
  it('does not read while operation is busy or backend not ready',async()=>{
    const api=fixture();render(<SessionHistory api={api as unknown as TwinPulseApi} disabled/>);
    expect((screen.getByText('Load saved history') as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByText('Load saved history'));
    await waitFor(()=>expect(api.physicalSessions).not.toHaveBeenCalled());
  });
  it('counts available passive observations without claiming alignment',async()=>{
    const api=fixture();const record=await api.physicalSession();
    api.physicalSession.mockResolvedValue({...record,navigation_observations:[{t:1,odom:{frame_id:'odom'},scan:null,faults:{odom:'NONE',scan:'NOT_RECEIVED'}}]});
    render(<SessionHistory api={api as unknown as TwinPulseApi} disabled={false}/>);
    fireEvent.click(screen.getByText('Load saved history'));
    fireEvent.click(await screen.findByRole('button',{name:'Record '+'a'.repeat(32)}));
    await screen.findByText('Pose/scan records 1 · pose received 1 · scan received 0');
    expect(screen.getByText(/These records do not certify coordinate alignment, collision avoidance, or measured floor position/)).toBeTruthy();
    expect(api.physicalStart).not.toHaveBeenCalled();
  });
  it('requires an explicit click for real saved evidence transfer and never retries a robot action',async()=>{
    const api=fixture(),job='a'.repeat(32),record=await api.physicalSession();
    api.physicalSession.mockResolvedValue({...record,provenance:'RECORDED_REAL_TRANSPORT',
      recorded_end:{status:'FAILED',reason:'TRANSFER_FAILED',cleanup_confirmed:false}});
    api.physicalResumeEvidence.mockResolvedValue({status:'COMPLETE',job_id:job,transfer_only:true});
    render(<SessionHistory api={api as unknown as TwinPulseApi} disabled={false}/>);
    fireEvent.click(screen.getByText('Load saved history'));
    fireEvent.click(await screen.findByRole('button',{name:'Record '+job}));
    await screen.findByLabelText('Saved evidence recovery');
    expect(api.physicalResumeEvidence).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('Retry saved evidence transfer only'));
    await screen.findByText('Transfer: COMPLETE');
    expect(api.physicalResumeEvidence).toHaveBeenCalledTimes(1);
    expect(api.physicalResumeEvidence.mock.calls[0][0]).toBe(job);
    expect(api.physicalStart).not.toHaveBeenCalled();
    expect(api.physicalInput).not.toHaveBeenCalled();
  });
  it('reviews saved PC evidence only on click and separates file integrity from ROS and physical validation',async()=>{
    const api=fixture(),job='a'.repeat(32);
    api.physicalReviewEvidence.mockResolvedValue({schema_version:'robot-evidence-offline-review-1',job_id:job,
      status:'COMPLETE',files:{'report.json':'VERIFIED'},raw_ros:{status:'NOT_CAPTURED',message_decode:'NOT_RUN'},
      contract_errors:[],physical_validation:'NOT_RUN_BY_THIS_TOOL',transfer_only:true});
    render(<SessionHistory api={api as unknown as TwinPulseApi} disabled={false}/>);
    fireEvent.click(screen.getByText('Load saved history'));
    fireEvent.click(await screen.findByRole('button',{name:'Record '+job}));
    await screen.findByLabelText('Saved evidence offline review');
    expect(api.physicalReviewEvidence).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('Review saved evidence locally'));
    await screen.findByText('Saved file integrity: COMPLETE');
    expect(screen.getByText(/ROS raw: NOT_CAPTURED .* physical validation: NOT RUN/)).toBeTruthy();
    expect(screen.getByText('report.json: VERIFIED')).toBeTruthy();
    expect(api.physicalReviewEvidence).toHaveBeenCalledWith(job);
    expect(api.physicalResumeEvidence).not.toHaveBeenCalled();
    expect(api.physicalStart).not.toHaveBeenCalled();
    expect(api.physicalInput).not.toHaveBeenCalled();
  });
  it('drops an in-flight saved evidence review when control disables history',async()=>{
    const api=fixture(),job='a'.repeat(32);
    let resolveReview!:(value:unknown)=>void;
    api.physicalReviewEvidence.mockImplementation(()=>new Promise(resolve=>{resolveReview=resolve;}));
    const {rerender}=render(<SessionHistory api={api as unknown as TwinPulseApi} disabled={false}/>);
    fireEvent.click(screen.getByText('Load saved history'));
    fireEvent.click(await screen.findByRole('button',{name:'Record '+job}));
    await screen.findByLabelText('Saved evidence offline review');
    fireEvent.click(screen.getByText('Review saved evidence locally'));
    rerender(<SessionHistory api={api as unknown as TwinPulseApi} disabled/>);
    resolveReview({job_id:job,status:'COMPLETE',raw_ros:{status:'VERIFIED',message_decode:'NOT_RUN'}});
    await waitFor(()=>expect(screen.queryByLabelText('Saved session details')).toBeNull());
    expect(screen.queryByText('Saved file integrity: COMPLETE')).toBeNull();
  });
  it('shows incomplete raw and file causes without automatic retry or transfer',async()=>{
    const api=fixture(),job='a'.repeat(32);
    api.physicalReviewEvidence.mockResolvedValue({schema_version:'robot-evidence-offline-review-1',job_id:job,
      status:'INCOMPLETE',files:{'ros-messages.raw':'HASH_OR_SIZE_MISMATCH'},
      raw_ros:{status:'REJECTED',message_decode:'NOT_RUN',reason:'RAW_FILES_NOT_VERIFIED'},
      contract_errors:['RAW_RECORDING_INCOMPLETE'],physical_validation:'NOT_RUN_BY_THIS_TOOL',transfer_only:true});
    render(<SessionHistory api={api as unknown as TwinPulseApi} disabled={false}/>);
    fireEvent.click(screen.getByText('Load saved history'));
    fireEvent.click(await screen.findByRole('button',{name:'Record '+job}));
    fireEvent.click(await screen.findByText('Review saved evidence locally'));
    await screen.findByText('Saved file integrity: INCOMPLETE');
    expect(screen.getByText(/RAW_FILES_NOT_VERIFIED.*physical validation: NOT RUN/)).toBeTruthy();
    expect(screen.getByText('Contract errors: RAW_RECORDING_INCOMPLETE')).toBeTruthy();
    expect(screen.getByText('ros-messages.raw: HASH_OR_SIZE_MISMATCH')).toBeTruthy();
    expect(api.physicalReviewEvidence).toHaveBeenCalledTimes(1);
    expect(api.physicalResumeEvidence).not.toHaveBeenCalled();
  });
});
