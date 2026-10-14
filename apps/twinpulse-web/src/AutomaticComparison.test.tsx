// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {describe,it,expect,vi} from 'vitest';
import {AutomaticComparison} from './AutomaticComparison';
import type {TwinPulseApi} from './api';
describe('executed automatic comparison',()=>{
  it('never runs on open; one request starts the pair and shows synthetic failures without improvement',async()=>{
    const arm={state:'FAILED',error:'SCAN_COVERAGE_UNKNOWN',distance_m:.4,source_elapsed_s:3,pc_runtime_s:4,
      collision_episodes:0,collision_penalty_points:0,score:0,geometry_corrected:false,trajectory:[[20,0,0,0],[21,.1,0,0]]};
    const api={automaticComparisonState:vi.fn().mockResolvedValue({job:null}),
      automaticComparisonStart:vi.fn().mockResolvedValue({job:{job_id:'a'.repeat(32),state:'COMPLETED',arm:'corrected',
        report_revision:'b'.repeat(64),result:{arms:{baseline:arm,corrected:arm},comparable_arrivals:false}}}),automaticComparisonStop:vi.fn()};
    render(<AutomaticComparison api={api as unknown as TwinPulseApi} available projectId="room"/>);
    await waitFor(()=>expect(api.automaticComparisonState).toHaveBeenCalledTimes(1));
    expect(api.automaticComparisonStart).not.toHaveBeenCalled();fireEvent.click(screen.getByText('Start offline comparison'));
    await screen.findByText(/Arrival comparison unavailable/);
    expect(api.automaticComparisonStart).toHaveBeenCalledWith([0,-.6,0],[.15,-.6]);
    expect(screen.getByRole('img',{name:'Comparison executed trajectories'})).toBeTruthy();
  });
  it('reports request failure as a dialog and allows refresh, not automatic retry',async()=>{
    const api={automaticComparisonState:vi.fn().mockResolvedValue({job:null}),
      automaticComparisonStart:vi.fn().mockRejectedValue(Error('COMPARISON_SOURCE_CHANGED'))};
    render(<AutomaticComparison api={api as unknown as TwinPulseApi} available projectId="room"/>);
    fireEvent.click(screen.getByText('Start offline comparison'));await screen.findByRole('alertdialog');
    expect(screen.getByText('COMPARISON_SOURCE_CHANGED')).toBeTruthy();expect(api.automaticComparisonStart).toHaveBeenCalledTimes(1);
  });
  it('keeps polling after execution until the final report is saved',async()=>{
    const completed={job_id:'a'.repeat(32),state:'COMPLETED',arm:'corrected',result:null};
    const api={automaticComparisonState:vi.fn().mockResolvedValueOnce({job:null})
      .mockResolvedValue({job:{...completed,report_revision:'b'.repeat(64)}}),
      automaticComparisonStart:vi.fn().mockResolvedValue({job:completed})};
    render(<AutomaticComparison api={api as unknown as TwinPulseApi} available projectId="room"/>);
    await waitFor(()=>expect(api.automaticComparisonState).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByText('Start offline comparison'));
    await screen.findByText(/Comparison report saved/);
    expect(api.automaticComparisonState).toHaveBeenCalledTimes(2);
    expect(api.automaticComparisonStart).toHaveBeenCalledTimes(1);
  });
});
