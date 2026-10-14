// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {describe,it,expect,vi} from 'vitest';
import {SensorPhotoLink,type PhotoLinkContext,type PhotoLinkResult} from './SensorPhotoLink';
import type {SensorMapResult} from './SensorMapLocalization';
import type {TwinPulseApi} from './api';

const sensor={revision:'sensor',reference_endpoint_cells:[[0,0],[1,0],[0,1],[1,1]],bounds_m:[-2,2,-2,2]} as SensorMapResult;
const context:PhotoLinkContext={revision:'context',anchors:[0,1,2,3].map(i=>({id:`wall:${i}`,object_id:'wall',corner:i,xy_m:[i%2,Math.floor(i/2)]})),outline:{bounds_m:[-2,2,-2,2],segments:[]}};
const result:PhotoLinkResult={revision:'link',status:'APPROXIMATE_VISUAL_LINK_CANDIDATE',fit_rms_m:0,fit_max_residual_m:0,validation_max_residual_m:.01,
  sensor_pose_room_candidate:[.2,.3,0],diagnostic_sensor_pose_room:[.2,.3,0],outline:context.outline,overlays:[{points:[[4,4]]}],pairs:[],
  alignment_verified:false,motion_authorized:false,physical_demo_ready:false};
function api(){return {photoLinkContext:vi.fn().mockResolvedValue(context),linkSensorPhoto:vi.fn().mockResolvedValue(result),photoLinkGoal:vi.fn().mockResolvedValue({query_odom_goal_candidate_m:[.1,.2]})};}
async function pairs(){
  fireEvent.click(screen.getByText('Load photo wall anchors'));await screen.findByLabelText('Photo link endpoint index');
  expect((screen.getByText('Check coordinate link · no movement') as HTMLButtonElement).disabled).toBe(true);
  for(let i=0;i<4;i++){
    fireEvent.change(screen.getByLabelText('Photo link endpoint index'),{target:{value:String(i)}});
    fireEvent.change(screen.getByLabelText('Photo link wall anchor'),{target:{value:`wall:${i}`}});
    if(i===3)fireEvent.change(screen.getByLabelText('Photo link pair role'),{target:{value:'validation'}});
    fireEvent.click(screen.getByText('Add correspondence'));
  }
}
describe('sensor map to approximate photo coordinates',()=>{
  it('requires explicit separate checks, sends identities and previews a historical goal only',async()=>{
    const mock=api();render(<SensorPhotoLink api={mock as unknown as TwinPulseApi} sensor={sensor} roomRevision="room" disabled={false} onBegin={()=>{}} onEnd={()=>{}}/>);
    expect(mock.photoLinkContext).not.toHaveBeenCalled();await pairs();
    expect(screen.getByLabelText('Select photo wall corner').getAttribute('viewBox')).toBe('-208 -208 416 416');
    expect(screen.getByText(/3 fit points · 1 held-out/)).toBeTruthy();
    fireEvent.click(screen.getByText('Check coordinate link · no movement'));await screen.findByText(/APPROXIMATE VISUAL LINK/);
    expect(mock.linkSensorPhoto.mock.calls[0].slice(0,3)).toEqual(['room','sensor','context']);
    expect(screen.getByText(/Physical pose uncertainty remains unknown/)).toBeTruthy();
    fireEvent.click(screen.getByText('Preview linked goal coordinates'));await screen.findByText(/Historical query odom goal/);
    expect(mock.photoLinkGoal).toHaveBeenCalledWith('room','link',[0,0]);
    fireEvent.click(screen.getByText('Remove pair 4'));expect(screen.queryByText(/Historical query odom goal/)).toBeNull();
    expect(screen.queryByText(/APPROXIMATE VISUAL LINK/)).toBeNull();
  });
  it('keeps mismatch explicit with no usable pose or goal',async()=>{
    const mock=api();mock.linkSensorPhoto.mockResolvedValue({...result,status:'ANCHOR_MISMATCH',sensor_pose_room_candidate:null,validation_max_residual_m:.4});
    render(<SensorPhotoLink api={mock as unknown as TwinPulseApi} sensor={sensor} roomRevision="room" disabled={false} onBegin={()=>{}} onEnd={()=>{}}/>);
    await pairs();fireEvent.click(screen.getByText('Check coordinate link · no movement'));await screen.findByText(/ANCHOR MISMATCH/);
    expect(screen.queryByText('Preview linked goal coordinates')).toBeNull();expect(mock.photoLinkGoal).not.toHaveBeenCalled();
    expect(screen.getByText(/outside-room returns are retained/)).toBeTruthy();
  });
  it('drops late context after room changes and reports exact failures without retry',async()=>{
    const mock=api();let done!:(value:PhotoLinkContext)=>void;
    mock.photoLinkContext.mockImplementationOnce(()=>new Promise(resolve=>{done=resolve;})).mockRejectedValue(new Error('SAVED_RAW_SOURCE_CHANGED'));
    const props={api:mock as unknown as TwinPulseApi,sensor,disabled:false,onBegin:()=>{},onEnd:()=>{}};
    const view=render(<SensorPhotoLink {...props} roomRevision="old"/>);fireEvent.click(screen.getByText('Load photo wall anchors'));
    view.rerender(<SensorPhotoLink {...props} roomRevision="new"/>);done(context);
    await waitFor(()=>expect(screen.queryByLabelText('Photo link endpoint index')).toBeNull());
    fireEvent.click(screen.getByText('Load photo wall anchors'));await screen.findByRole('alert');
    expect(screen.getByRole('alert').textContent).toContain('SAVED_RAW_SOURCE_CHANGED');expect(mock.photoLinkContext).toHaveBeenCalledTimes(2);
  });
});
