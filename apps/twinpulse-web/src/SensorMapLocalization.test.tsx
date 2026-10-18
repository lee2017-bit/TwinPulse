// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {describe,it,expect,vi} from 'vitest';
import {SensorMapLocalization,type SensorMapResult} from './SensorMapLocalization';
import type {TwinPulseApi} from './api';

function result(status='SENSOR_MAP_GEOMETRIC_CANDIDATE'):SensorMapResult{return {
  revision:'result',status,job_id:'ref',query_job_id:'query',frame:8,query_frames:[7,8,9],
  reference_endpoint_cells:[[1,0,2,0,4]],bounds_m:[-1,2,-1,2],reference_retained_scan_count:100,
  holdout:{excluded_reference_frames:[3,4,5],direct_query_scan_reuse:false},alternative_margin_m:.04,
  best_diagnostic_hypothesis:{sensor_pose_reference_candidate:[.2,.3,.4],weighted_capped_mean_error_m:.01,supported_query_frames:3},
  overlays:[{frame:8,points:[[1,0]],sensor_pose_reference_candidate:[.2,.3,.4]}],
  photo_geometry_used:false,room_transform_created:false,motion_authorized:false,physical_demo_ready:false};}

describe('held-out sensor-map location review',()=>{
  it('runs only explicitly, displays original sources and clears results on query changes',async()=>{
    const locate=vi.fn().mockResolvedValue(result()),begin=vi.fn(),end=vi.fn();
    render(<SensorMapLocalization api={{locateSensorMap:locate} as unknown as TwinPulseApi} referenceJob="ref" observationRevision="map" jobs={['query']} disabled={false} onBegin={begin} onEnd={end}/>);
    expect(locate).not.toHaveBeenCalled();fireEvent.change(screen.getByLabelText('Sensor map test session'),{target:{value:'query'}});
    fireEvent.change(screen.getByLabelText('Sensor map test frame'),{target:{value:'8'}});
    fireEvent.click(screen.getByText('Locate recorded scans · sensor map'));
    await screen.findByText(/SENSOR MAP GEOMETRIC CANDIDATE/);
    expect(locate).toHaveBeenCalledWith('ref','map','query',8);expect(begin).toHaveBeenCalledTimes(1);expect(end).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/Excluded 3 reference scans/)).toBeTruthy();expect(screen.getByText(/not physical position accuracy/)).toBeTruthy();
    expect(screen.getByRole('img',{name:'Held-out sensor map and recorded scan position candidate'})).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Sensor map test frame'),{target:{value:'9'}});
    expect(screen.queryByText(/Historical sensor position candidate/)).toBeNull();expect(locate).toHaveBeenCalledTimes(1);
  });
  it('discards a late response after reference map changes and shows exact errors without retry',async()=>{
    let done!:(value:SensorMapResult)=>void;const locate=vi.fn().mockImplementationOnce(()=>new Promise(resolve=>{done=resolve;})).mockRejectedValue(new Error('QUERY_ODOM_TIME_UNBRACKETED'));
    const api={locateSensorMap:locate} as unknown as TwinPulseApi,begin=vi.fn(),end=vi.fn();
    const view=render(<SensorMapLocalization api={api} referenceJob="old" observationRevision="map1" jobs={[]} disabled={false} onBegin={begin} onEnd={end}/>);
    fireEvent.click(screen.getByText('Locate recorded scans · sensor map'));
    view.rerender(<SensorMapLocalization api={api} referenceJob="new" observationRevision="map2" jobs={[]} disabled={false} onBegin={begin} onEnd={end}/>);
    done(result());await waitFor(()=>expect(screen.queryByText(/Historical sensor position candidate/)).toBeNull());
    fireEvent.click(screen.getByText('Locate recorded scans · sensor map'));await screen.findByRole('alert');
    expect(screen.getByRole('alert').textContent).toContain('QUERY_ODOM_TIME_UNBRACKETED');expect(locate).toHaveBeenCalledTimes(2);
    expect((screen.getByText('Locate recorded scans · sensor map') as HTMLButtonElement).disabled).toBe(false);
  });
  it('does not cancel its own request when the parent locks other work and displays ambiguity',async()=>{
    let done!:(value:SensorMapResult)=>void;const locate=vi.fn().mockImplementation(()=>new Promise(resolve=>{done=resolve;}));
    const api={locateSensorMap:locate} as unknown as TwinPulseApi;
    const view=render(<SensorMapLocalization api={api} referenceJob="ref" observationRevision="map" jobs={[]} disabled={false} onBegin={()=>{}} onEnd={()=>{}}/>);
    fireEvent.click(screen.getByText('Locate recorded scans · sensor map'));
    view.rerender(<SensorMapLocalization api={api} referenceJob="ref" observationRevision="map" jobs={[]} disabled={true} onBegin={()=>{}} onEnd={()=>{}}/>);
    done(result('AMBIGUOUS'));await screen.findByText(/AMBIGUOUS · 3\/3/);
    expect(screen.getByText(/ambiguous candidates remain unaccepted/)).toBeTruthy();
  });
});
