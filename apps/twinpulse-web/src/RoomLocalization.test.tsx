// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {describe,it,expect,vi} from 'vitest';
import {RoomLocalization,type LocalizationResult} from './RoomLocalization';
import type {TwinPulseApi} from './api';
import type {BedroomReviewState} from './BedroomTwin';

const review={revision:'room',scene_revision:'scene'} as BedroomReviewState;
function fixture(status='GEOMETRIC_CANDIDATE'):LocalizationResult{return {
  revision:'result',epoch:2,job_id:'a'.repeat(32),frame:0,frame_count:10,elapsed_s:0,duration_s:1,stamp_ns:123,source_revision:'raw',
  goal_candidate_available:status==='GEOMETRIC_CANDIDATE',match:{status,mean_error_m:.05},
  robot_pose_room_candidate:[0,0,0],scan_points_room_candidate:[[1,0]],trajectory_candidate:[{stamp_ns:123,pose:[0,0,0]}],
  outline:{bounds_m:[-1,1,-1,1],segments:[[[0,0],[1,0]]]},timing:{paired_frames:9,rejected_frames:1,failures:[{frame:9,reason:'ODOM_TIME_UNBRACKETED'}]},
  diagnostics:{decoded_counts:{scan:10,odom:20},tf_static_count:0,sensor_extrinsic:'NOMINAL_MODEL_NOT_AS_BUILT'},alignment_verified:false,motion_authorized:false,physical_demo_ready:false};}
function mock(){return {physicalSessions:vi.fn().mockResolvedValue({sessions:[{job_id:'a'.repeat(32)}]}),roomLocalization:vi.fn().mockResolvedValue(fixture()),
  localizedRoomGoal:vi.fn().mockResolvedValue({odom_goal_candidate_m:[.5,.7],mission_request:null}),invalidateRoomLocalization:vi.fn().mockResolvedValue({})};}
async function run(api:ReturnType<typeof mock>){
  render(<RoomLocalization api={api as unknown as TwinPulseApi} review={review} backendReady/>);
  expect(api.roomLocalization).not.toHaveBeenCalled();fireEvent.click(screen.getByText('Load saved sessions'));
  await waitFor(()=>expect((screen.getByLabelText('Localization saved session') as HTMLSelectElement).value).toBe('a'.repeat(32)));
  fireEvent.click(screen.getByText('Find position from scan'));await screen.findByText(/GEOMETRIC CANDIDATE|AMBIGUOUS/);
}
describe('saved scan localization',()=>{
  it('shows source/timing/candidate and converts without authorizing motion',async()=>{
    const api=mock();await run(api);expect(screen.getByText(/Declared-time paired frames/).textContent).toContain('rejected: 1');
    fireEvent.click(screen.getByText('Convert goal · review only'));await screen.findByText(/Odom goal candidate: 0.500/);
    expect(api.localizedRoomGoal).toHaveBeenCalledWith('room','result',2,[0,0]);
    fireEvent.click(screen.getByText('Robot moved by hand · invalidate position'));
    await screen.findByText(/Previous position invalidated/);expect(screen.queryByText(/Odom goal candidate/)).toBeNull();
  });
  it('rejects ambiguous position and clears a prior result when frame changes',async()=>{
    const api=mock();api.roomLocalization.mockResolvedValue(fixture('AMBIGUOUS'));await run(api);
    expect((screen.getByText('Convert goal · review only') as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText('Localization scan frame'),{target:{value:'3'}});
    expect(screen.queryByText(/Robot position candidate/)).toBeNull();
  });
  it('shows exact backend reason rather than leaving a silent locked panel',async()=>{
    const api=mock();api.roomLocalization.mockRejectedValue(new Error('SCAN_SOURCE_CLOCK_RESET_OR_DUPLICATE'));
    render(<RoomLocalization api={api as unknown as TwinPulseApi} review={review} backendReady/>);
    fireEvent.click(screen.getByText('Load saved sessions'));await waitFor(()=>expect((screen.getByLabelText('Localization saved session') as HTMLSelectElement).value).toBe('a'.repeat(32)));
    fireEvent.click(screen.getByText('Find position from scan'));await screen.findByRole('alert');
    expect(screen.getByRole('alert').textContent).toContain('SCAN_SOURCE_CLOCK_RESET_OR_DUPLICATE');
  });
  it('drops a pending result after the room identity changes',async()=>{
    const api=mock();let complete!:(value:LocalizationResult)=>void;
    api.roomLocalization.mockImplementation(()=>new Promise(resolve=>{complete=resolve;}));
    const view=render(<RoomLocalization api={api as unknown as TwinPulseApi} review={review} backendReady/>);
    fireEvent.click(screen.getByText('Load saved sessions'));
    await waitFor(()=>expect((screen.getByLabelText('Localization saved session') as HTMLSelectElement).value).toBe('a'.repeat(32)));
    fireEvent.click(screen.getByText('Find position from scan'));
    view.rerender(<RoomLocalization api={api as unknown as TwinPulseApi} review={{...review,revision:'changed'}} backendReady/>);
    complete(fixture());await waitFor(()=>expect(screen.queryByText(/Robot position candidate/)).toBeNull());
    expect(api.localizedRoomGoal).not.toHaveBeenCalled();
  });
});
