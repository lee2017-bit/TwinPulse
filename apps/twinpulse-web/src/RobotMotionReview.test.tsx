// SPDX-License-Identifier: Apache-2.0
// Supplementary fixtures only; no physical outcome is asserted.
import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {describe,expect,it,vi} from 'vitest';
import {RobotMotionReview,type MotionReviewState} from './RobotMotionReview';
import type {TwinPulseApi} from './api';
const empty:MotionReviewState={job:null,review:null,scope:'historical',authority_restored:false};
function setup(){
  const get=vi.fn().mockResolvedValue(empty),action=vi.fn().mockResolvedValue(empty);
  const api={context:'project-context',robotMotionReview:get,robotMotionReviewAction:action} as unknown as TwinPulseApi;
  const view=render(<RobotMotionReview api={api} operation={'1'.repeat(32)} physical/>);
  return {get,action,api,...view};
}
function open(){const d=screen.getByLabelText('Saved motion review') as HTMLDetailsElement;d.open=true;fireEvent(d,new Event('toggle'));}
describe('saved physical motion review',()=>{
  it('does not start analysis when opening history; requires an explicit action',async()=>{
    const {get,action}=setup();expect(get).not.toHaveBeenCalled();expect(action).not.toHaveBeenCalled();
    open();await waitFor(()=>expect(get).toHaveBeenCalledTimes(1));expect(action).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button',{name:'Analyze recording'}));
    await waitFor(()=>expect(action).toHaveBeenCalledTimes(1));
    expect(action.mock.calls[0][0]).toBe('1'.repeat(32));expect(action.mock.calls[0][1].action).toBe('start');
  });
  it('shows wheel, independent scan and noise without a body PASS',async()=>{
    const {get}=setup();get.mockResolvedValue({...empty,review:{schema:'physical-motion-review-1.0',status:'COMPLETED_WITH_LIMITS',operation_id:'1'.repeat(32),
      original_complete:false,input_receipt_sha256:'a'.repeat(64),windows:[{direction:'forward',request_id:'original-request',linkage:'LEGACY_RECONSTRUCTED',command_end_reason:'INPUT_DEADLINE_EXPIRED',
        wheel:{centre_m:.01,yaw_rad:0,wheel_data_quality:'LEGACY_INTERVAL_GAP_UNQUALIFIED'},lidar:{status:'ESTIMATED_UNQUALIFIED',translation_m:.006,yaw_rad:0,pairs:2,max_residual_m:.003},
        stationary_baseline:{windows:6},comparison:'CHANGE_OVERLAPS_OBSERVED_BASELINE'}]}});
    open();await waitFor(()=>expect(screen.getByRole('table',{name:'Command sensor comparison'}).textContent).toContain('10.00 mm'));
    expect(screen.getByText(/Body unqualified \/ unknown/)).toBeTruthy();expect(screen.getAllByText(/INPUT_DEADLINE_EXPIRED/).length).toBeGreaterThan(0);
    expect(screen.getByText(/observed noise is not a statistical error bound/)).toBeTruthy();
  });
  it('discards late results after operation or context changes',async()=>{
    const {get,api,rerender}=setup();let resolve!:(v:MotionReviewState)=>void;get.mockReturnValue(new Promise<MotionReviewState>(r=>{resolve=r;}));
    open();await waitFor(()=>expect(get).toHaveBeenCalled());
    rerender(<RobotMotionReview api={api} operation={'2'.repeat(32)} physical/>);
    await act(async()=>resolve({...empty,review:{status:'old-marker'}}));expect(screen.queryByText(/old-marker/)).toBeNull();
  });
});
