// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {describe,it,expect,vi} from 'vitest';
import {AutomaticDemo,type AutomaticState} from './AutomaticDemo';
import type {TwinPulseApi} from './api';

function state(status='COMPLETED',epoch=1):AutomaticState{return {job:{job_id:'c'.repeat(32),source_job_id:'a'.repeat(32),state:status,
  epoch,elapsed_s:1,progress_sequence:8,map_id:status==='COMPLETED'?'c'.repeat(32):null,error:null,
  result:status==='PAUSED'?null:{state:'AMBIGUOUS',pose_candidate:null,counts:{scans_paired:3,derived_skipped:1},reasons:{},
    reference_eligible:false,corrected_cells:[[0,0,'occupied',100,1,0,'raw']],loop_status:'NOT_ESTABLISHED',timing_basis:'UNVERIFIED',trajectory:[]}}};}
function apiMock(){return {physicalSessions:vi.fn().mockResolvedValue({sessions:[{job_id:'a'.repeat(32)}]}),
  automaticMaps:vi.fn().mockResolvedValue({maps:[]}),automaticStart:vi.fn().mockResolvedValue(state()),
  automaticState:vi.fn().mockResolvedValue(state()),automaticControl:vi.fn().mockResolvedValue(state('PAUSED',2)),
  automaticReopen:vi.fn().mockResolvedValue({map:{reference_eligible:false,cells:[[0,0,'occupied',100,1,0,'raw']]}})};}
describe('automatic causal session',()=>{
  it('explicitly requests historical 1x receipt replay, never a live command',async()=>{
    const api=apiMock();render(<AutomaticDemo api={api as unknown as TwinPulseApi} available projectId="default"/>);
    await waitFor(()=>expect((screen.getByText('Start automatic replay') as HTMLButtonElement).disabled).toBe(false));
    fireEvent.change(screen.getByLabelText('Automatic replay speed'),{target:{value:'recorded_1x'}});
    fireEvent.click(screen.getByText('Start automatic replay'));
    await waitFor(()=>expect(api.automaticStart).toHaveBeenCalledWith('a'.repeat(32),null,'correct_walls','recorded_1x'));
    expect(api.automaticStart).toHaveBeenCalledTimes(1);
  });
  it('selects an automatic policy before Start and shows rejection without any manual points',async()=>{
    const api=apiMock(),ended=state();ended.job!.result!.photo_alignment={status:'MODEL_MISMATCH',reason:'STRUCTURAL_POSE_FIT_REJECTED',
      policy:'align_only',room_from_map:null,goal_revalidation_required:false,validation_basis:'SHARED_ODOM',fit_sequences:[1,3],validation_sequences:[8,10]};
    ended.job!.result!.photo_alignment.residual_diagnosis={fit:[{structure_index:0,nearest_wall_hypothesis:'wall_west',
      mean_uncapped_residual_m:.812,support_sequences:[1,3]}],held_out:[],unresolved_causes:['APPROXIMATE_PHOTO_WALL_GEOMETRY']};
    api.automaticStart.mockResolvedValue(ended);
    render(<AutomaticDemo api={api as unknown as TwinPulseApi} available projectId="default"/>);
    await waitFor(()=>expect((screen.getByText('Start automatic replay') as HTMLButtonElement).disabled).toBe(false));
    fireEvent.change(screen.getByLabelText('Automatic photo policy'),{target:{value:'align_only'}});
    fireEvent.click(screen.getByText('Start automatic replay'));
    await screen.findByText('Photo Twin alignment · MODEL_MISMATCH');
    expect(screen.getByText('Why structures disagree')).toBeTruthy();
    expect(screen.getByText('0.812 m')).toBeTruthy();
    expect(screen.getByText('wall_west')).toBeTruthy();
    expect(api.automaticStart).toHaveBeenCalledWith('a'.repeat(32),null,'align_only');
    expect(screen.queryByText('Roll back automatic wall correction')).toBeNull();
  });
  it('offers rollback only for an applied revision and shows failures as a dialog',async()=>{
    const api={...apiMock(),automaticRollbackPhoto:vi.fn().mockRejectedValue(Error('PHOTO_LEDGER_HEAD_CHANGED'))},ended=state();
    ended.job!.result!.photo_alignment={status:'ALIGNMENT_CANDIDATE',policy:'correct_walls',room_from_map:[0,0,0],
      applied_revision:'e'.repeat(64),goal_revalidation_required:true,validation_basis:'SHARED_ODOM'};
    api.automaticStart.mockResolvedValue(ended);
    render(<AutomaticDemo api={api as unknown as TwinPulseApi} available projectId="default"/>);
    await waitFor(()=>expect((screen.getByText('Start automatic replay') as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByText('Start automatic replay'));fireEvent.click(await screen.findByText('Roll back automatic wall correction'));
    expect((await screen.findByRole('alertdialog')).textContent).toContain('PHOTO_LEDGER_HEAD_CHANGED');
    expect(api.automaticRollbackPhoto).toHaveBeenCalledWith('c'.repeat(32),'e'.repeat(64));
  });
  it('reopens a stored photo report as historical evidence without an Apply button',async()=>{
    const api=apiMock();api.automaticReopen.mockResolvedValue({map:{reference_eligible:false,cells:[]},photo_alignment:{
      status:'AMBIGUOUS',policy:'correct_walls',room_from_map:null,goal_revalidation_required:false,validation_basis:'SHARED_ODOM'}} as never);
    render(<AutomaticDemo api={api as unknown as TwinPulseApi} available projectId="default"/>);
    await waitFor(()=>expect((screen.getByText('Start automatic replay') as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByText('Start automatic replay'));fireEvent.click(await screen.findByText('Reopen saved map · no retained pose'));
    await screen.findByText(/Historical evidence only/);expect(screen.queryByText('Roll back automatic wall correction')).toBeNull();
  });
  it('retains usable inputs when a corrupt map catalog fails',async()=>{
    const api=apiMock();api.automaticMaps.mockRejectedValue(Error('AUTOMATIC_MAP_HASH_MISMATCH'));
    render(<AutomaticDemo api={api as unknown as TwinPulseApi} available projectId="default"/>);
    expect((await screen.findByRole('alertdialog')).textContent).toContain('AUTOMATIC_MAP_HASH_MISMATCH');
    expect((screen.getByText('Start automatic replay') as HTMLButtonElement).disabled).toBe(false);
  });
  it('refreshes the map catalog after completion without restarting the session',async()=>{
    const api=apiMock();render(<AutomaticDemo api={api as unknown as TwinPulseApi} available projectId="default"/>);
    await waitFor(()=>expect((screen.getByText('Start automatic replay') as HTMLButtonElement).disabled).toBe(false));
    api.automaticMaps.mockResolvedValue({maps:[{map_id:'c'.repeat(32),reference_eligible:true}]} as never);
    fireEvent.click(screen.getByText('Start automatic replay'));await screen.findByText(/Revisit cccccccccccc/);
    expect(api.automaticStart).toHaveBeenCalledTimes(1);
  });
  it('shows an asynchronous processing failure in the error dialog',async()=>{
    const api=apiMock();api.automaticStart.mockResolvedValue(state('PREPARING'));
    const failed=state('FAILED');failed.job!.error='ODOM_DYNAMIC_TF_CONFLICT';failed.job!.result=null;
    api.automaticState.mockResolvedValue(failed);
    render(<AutomaticDemo api={api as unknown as TwinPulseApi} available projectId="default"/>);
    await waitFor(()=>expect((screen.getByText('Start automatic replay') as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByText('Start automatic replay'));
    expect((await screen.findByRole('alertdialog')).textContent).toContain('ODOM_DYNAMIC_TF_CONFLICT');
    expect(api.automaticStart).toHaveBeenCalledTimes(1);
  });
  it('starts without a frame selection or robot operation and reopens with no retained pose',async()=>{
    const api=apiMock();render(<AutomaticDemo api={api as unknown as TwinPulseApi} available projectId="default"/>);
    expect(api.automaticStart).not.toHaveBeenCalled();
    await waitFor(()=>expect((screen.getByText('Start automatic replay') as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByText('Start automatic replay'));await screen.findByText(/COMPLETED ·/);
    expect(api.automaticStart).toHaveBeenCalledWith('a'.repeat(32),null,'correct_walls');expect(screen.getByText(/Localization: AMBIGUOUS/)).toBeTruthy();
    fireEvent.click(screen.getByText('Reopen saved map · no retained pose'));await screen.findByRole('img');
    expect(api.automaticReopen).toHaveBeenCalledWith('c'.repeat(32));
  });
  it('invalidates the displayed result immediately on pause and uses the owned job',async()=>{
    const api=apiMock();api.automaticStart.mockResolvedValue(state('TRACKING_CANDIDATE'));
    render(<AutomaticDemo api={api as unknown as TwinPulseApi} available projectId="default"/>);
    await waitFor(()=>expect((screen.getByText('Start automatic replay') as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByText('Start automatic replay'));await screen.findByText('Pause · invalidate current pose');
    fireEvent.click(screen.getByText('Pause · invalidate current pose'));await screen.findByText(/PAUSED ·/);
    expect(screen.queryByRole('img')).toBeNull();expect(api.automaticControl).toHaveBeenCalledWith('c'.repeat(32),'pause',null);
    expect((screen.getByText('Resume causal replay') as HTMLButtonElement).disabled).toBe(false);
  });
  it('shows an error dialog and never automatically retries a rejected start',async()=>{
    const api=apiMock();api.automaticStart.mockRejectedValue(Error('MAP_QUERY_SOURCE_REUSE'));
    render(<AutomaticDemo api={api as unknown as TwinPulseApi} available projectId="default"/>);
    await waitFor(()=>expect((screen.getByText('Start automatic replay') as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByText('Start automatic replay'));expect((await screen.findByRole('alertdialog')).textContent).toContain('MAP_QUERY_SOURCE_REUSE');
    expect(api.automaticStart).toHaveBeenCalledTimes(1);
  });
  it('discards late source-list and operation results after a project change',async()=>{
    const api=apiMock();let finish!:(value:AutomaticState)=>void;
    api.automaticStart.mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
    const view=render(<AutomaticDemo api={api as unknown as TwinPulseApi} available projectId="default"/>);
    await waitFor(()=>expect((screen.getByText('Start automatic replay') as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByText('Start automatic replay'));view.rerender(<AutomaticDemo api={api as unknown as TwinPulseApi} available projectId="other"/>);
    finish(state());await waitFor(()=>expect(screen.queryByText(/COMPLETED ·/)).toBeNull());
  });
});
