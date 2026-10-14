// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {describe,it,expect,vi} from 'vitest';
import {BedroomGoalReview} from './BedroomGoalReview';
import type {TwinPulseApi} from './api';
import type {BedroomReviewState} from './BedroomTwin';
const review={revision:'room',scene_revision:'scene',objects:[]} as unknown as BedroomReviewState;
const evidence={revision:'evidence',model_commit:'pinned',base_link_to_scan_xyz_m:[-.032,0,.172],
  wheel_separation_m:.16,wheel_radius_m:.033,collision_aabb_base_link_m:[[-.102,.038],[-.089,.089]],
  retained_guard_radius_m:.18,saved_scan:{frames:74,boot_id:'old-boot'},missing:['SAME_TIME_ODOM_AND_TF']};
function setup(){
  const api={geometryEvidence:vi.fn().mockResolvedValue(evidence),bedroomGoal:vi.fn().mockResolvedValue({
    status:'MISSING_METRIC_REFERENCE',twin_goal_xy_m:[0,0],odom_goal_candidate_m:null,motion_authorized:false,alignment_verified:false})};
  render(<BedroomGoalReview api={api as unknown as TwinPulseApi} review={review} backendReady/>);return api;
}
describe('Twin goal evidence',()=>{
  it('does not inspect automatically or invent odom from a photograph',async()=>{
    const api=setup();expect(api.geometryEvidence).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('Inspect sensor pose and robot footprint evidence'));
    await screen.findByText(/Wheel separation 160/);
    fireEvent.click(screen.getByText('Review goal coordinate mapping · no movement'));
    await screen.findByText(/no measured correspondence evidence/);
    expect(api.bedroomGoal).toHaveBeenCalledExactlyOnceWith('room','evidence',[0,0],null);
  });
  it('invalidates an old candidate when goal or reference changes',async()=>{
    const api=setup();fireEvent.click(screen.getByText('Inspect sensor pose and robot footprint evidence'));await screen.findByText(/Wheel separation 160/);
    api.bedroomGoal.mockResolvedValue({status:'CANDIDATE_ONLY_NOT_CALIBRATED',odom_goal_candidate_m:[.7,2.2],max_residual_m:0});
    fireEvent.change(screen.getByLabelText('Twin odom correspondence evidence JSON'),{target:{value:'{"basis":"synthetic_test_fixture"}'}});
    fireEvent.click(screen.getByText('Review goal coordinate mapping · no movement'));await screen.findByText(/Odom candidate:/);
    fireEvent.change(screen.getByLabelText('Twin goal X'),{target:{value:'.2'}});
    expect(screen.queryByText(/Odom candidate:/)).toBeNull();
    api.bedroomGoal.mockRejectedValue(new Error('changed'));
    fireEvent.click(screen.getByText('Review goal coordinate mapping · no movement'));
    await screen.findByRole('alert');expect(screen.queryByText(/Odom candidate:/)).toBeNull();
  });
  it('rejects malformed JSON without a network request',async()=>{
    const api=setup();fireEvent.click(screen.getByText('Inspect sensor pose and robot footprint evidence'));await screen.findByText(/Wheel separation 160/);
    fireEvent.change(screen.getByLabelText('Twin odom correspondence evidence JSON'),{target:{value:'{broken'}});
    fireEvent.click(screen.getByText('Review goal coordinate mapping · no movement'));
    await waitFor(()=>expect(screen.getByRole('alert')).toBeTruthy());expect(api.bedroomGoal).not.toHaveBeenCalled();
  });
});
