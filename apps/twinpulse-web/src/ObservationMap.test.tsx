// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {describe,it,expect,vi} from 'vitest';
import {ObservationMap,type ObservationMapResult} from './ObservationMap';
import type {TwinPulseApi} from './api';
import type {ModelComparisonResult} from './ModelComparison';

function comparison():ModelComparisonResult{return {revision:'cmp',status:'MODEL_OR_ODOM_INCONSISTENT',evaluated_keyframes:2,
  scan_height_m_nominal:.18,outline:{segments:[[[-1,-1],[1,-1]]]},
  best_diagnostic_hypothesis:{weighted_capped_mean_error_m:.2,supported_frames:0,evaluated_frames:2,frames:[]},
  sensor_sections:[{object_id:'chair',intersects_nominal_scan_plane:true,review_priority:'FURNITURE_LOWER_SECTION_UNKNOWN'}],
  overlays:[{frame:0,points:[[1,0]],sensor_pose:[0,0,0]}],nearest_surface_diagnostics:[{object_id:'chair',nearest_returns:2,beyond_15cm_returns:1}],
  geometry_changed:false,alignment_verified:false,motion_authorized:false,physical_demo_ready:false};}

function fixture():ObservationMapResult{return {
  revision:'map',job_id:'a'.repeat(32),source_revision:'raw',status:'DIAGNOSTIC_ODOM_PROJECTION',frame_count:12,
  coordinate_frame:'SESSION_START_ODOM_LOCAL_NOT_ROOM_OR_MAP',paired_frames:11,rejected_frames:1,sampled_hits:42,
  endpoint_cells:[[1,0,3,0,10]],bounds_m:[-1,2,-1,2],
  keyframes:[{frame:0,elapsed_s:0,sensor_pose:[0,0,0],points:[[1,0]]},
             {frame:10,elapsed_s:1,sensor_pose:[.5,0,0],points:[[1,.5]]}],
  trajectory:[{stamp_ns:0,pose:[0,0,0]}],
  timing:{header_basis:'DECLARED_HEADER',beam_order:'ORDER_UNVERIFIED',acquisition_timing_verified:false},
  failures:[{frame:11,reason:'ODOM_TIME_UNBRACKETED'}],photo_geometry_used:false,motion_authorized:false,physical_demo_ready:false};}

describe('independent observation map',()=>{
  it('compares only the current map explicitly, displays disagreement and invalidates on room change',async()=>{
    const compare=vi.fn().mockResolvedValue(comparison()),clear=vi.fn();
    const api={sessionObservationMap:vi.fn().mockResolvedValue(fixture()),compareObservationModel:compare} as unknown as TwinPulseApi;
    const view=render(<ObservationMap api={api} job={'a'.repeat(32)} disabled={false} roomRevision="room1" onDiagnostic={clear}/>);
    expect(compare).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('Build observation map · entire session'));await screen.findByText(/Diagnostic map/);
    fireEvent.click(screen.getByText('Compare with photo 3D · multiple frames'));
    await screen.findByRole('region',{name:'Photo model comparison'});
    expect(compare).toHaveBeenCalledWith('a'.repeat(32),'room1','map');expect(clear).toHaveBeenCalledTimes(2);
    expect(screen.getByText(/0\/2 frames support/)).toBeTruthy();expect(screen.getByText(/not position accuracy/)).toBeTruthy();
    expect(screen.getByText(/chair: intersects/)).toBeTruthy();
    view.rerender(<ObservationMap api={api} job={'a'.repeat(32)} disabled={false} roomRevision="room2"/>);
    expect(screen.queryByRole('region',{name:'Photo model comparison'})).toBeNull();expect(compare).toHaveBeenCalledTimes(1);
  });
  it('discards a late comparison after job change and shows rejection without losing the observation map',async()=>{
    let done!:(v:ModelComparisonResult)=>void;
    const compare=vi.fn().mockRejectedValueOnce(new Error('SAVED_RAW_SOURCE_CHANGED')).mockImplementation(()=>new Promise(resolve=>{done=resolve;}));
    const api={sessionObservationMap:vi.fn().mockResolvedValue(fixture()),compareObservationModel:compare} as unknown as TwinPulseApi;
    const view=render(<ObservationMap api={api} job="old" disabled={false} roomRevision="room"/>);
    fireEvent.click(screen.getByText('Build observation map · entire session'));await screen.findByText(/Diagnostic map/);
    fireEvent.click(screen.getByText('Compare with photo 3D · multiple frames'));await screen.findByText('SAVED_RAW_SOURCE_CHANGED');
    expect(screen.getByText(/Diagnostic map/)).toBeTruthy();
    fireEvent.click(screen.getByText('Compare with photo 3D · multiple frames'));
    view.rerender(<ObservationMap api={api} job="new" disabled={false} roomRevision="room"/>);done(comparison());
    await waitFor(()=>expect(screen.queryByRole('region',{name:'Photo model comparison'})).toBeNull());
  });
  it('is explicit, replays original keyframes and reports unverified timing',async()=>{
    const fn=vi.fn().mockResolvedValue(fixture());const api={sessionObservationMap:fn} as unknown as TwinPulseApi;
    render(<ObservationMap api={api} job={'a'.repeat(32)} disabled={false}/>);
    expect(fn).not.toHaveBeenCalled();fireEvent.click(screen.getByText('Build observation map · entire session'));
    await screen.findByText(/Diagnostic map/);expect(fn).toHaveBeenCalledWith('a'.repeat(32));
    expect(screen.getByText(/Timing unverified/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Observation scan time'),{target:{value:'1'}});
    expect(screen.getByText(/Original frame 11\/12/)).toBeTruthy();
    expect(screen.getByText(/No scan-to-room transform/)).toBeTruthy();
    expect(screen.getByText(/ODOM_TIME_UNBRACKETED/)).toBeTruthy();
  });
  it('clears old and late maps after session changes and does not auto retry',async()=>{
    let complete!:(v:ObservationMapResult)=>void;const fn=vi.fn().mockImplementation(()=>new Promise(resolve=>{complete=resolve;}));
    const api={sessionObservationMap:fn} as unknown as TwinPulseApi;
    const view=render(<ObservationMap api={api} job="old" disabled={false}/>);
    fireEvent.click(screen.getByText('Build observation map · entire session'));
    view.rerender(<ObservationMap api={api} job="new" disabled={false}/>);complete(fixture());
    await waitFor(()=>expect(screen.queryByText(/Diagnostic map/)).toBeNull());expect(fn).toHaveBeenCalledTimes(1);
  });
  it('shows the exact rejection and remains usable for an explicit retry',async()=>{
    const fn=vi.fn().mockRejectedValue(new Error('OBSERVATION_NO_PAIRED_RETURNS'));
    render(<ObservationMap api={{sessionObservationMap:fn} as unknown as TwinPulseApi} job="a" disabled={false}/>);
    fireEvent.click(screen.getByText('Build observation map · entire session'));await screen.findByRole('alert');
    expect(screen.getByRole('alert').textContent).toContain('OBSERVATION_NO_PAIRED_RETURNS');
    expect((screen.getByText('Build observation map · entire session') as HTMLButtonElement).disabled).toBe(false);
  });
});
