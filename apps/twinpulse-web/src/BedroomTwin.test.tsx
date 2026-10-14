// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { BedroomTwin } from './BedroomTwin';
import type { TwinPulseApi } from './api';
import type { ProductState } from './types';
const review = { revision: 'manifest', scene_revision: 'scene', summary: 'room', objects: [], limits: [] };
const product = { engine_connected: true, operations: [], snapshot: { capabilities: ['bedroom_visual_v1','bedroom_replay_v1'], permitted_commands: ['build_site_scene'] } } as unknown as ProductState;
function setup(state = product, failure = false) {
  const api = { prepareBedroom: vi.fn().mockResolvedValue(review), acquireLease: vi.fn().mockResolvedValue({}),
    compareBedroom:vi.fn(),
    offlineBedroomAcceptance:vi.fn(),exportBedroomOfflineAcceptance:vi.fn(),importBedroomOfflineAcceptance:vi.fn(),
    exportBedroomComparison:vi.fn(),
    exportBedroomRehearsal:vi.fn(),
    replayBedroom:vi.fn().mockResolvedValue({command_id:'replay',status:'accepted'}),
    rehearseBedroom:vi.fn().mockResolvedValue({status:'ARRIVED',scenario:'route',revision:'result',scene_revision:'scene',
      physical_validation:'NOT_RUN',motion_authorized:false,duration_s:10,distance_m:.3,command_count:10,waypoints:[[0,0]],events:[]}),
    productState: vi.fn().mockResolvedValue({ ...state, lease_owned: true }),
    buildBedroom: failure ? vi.fn().mockRejectedValue(new Error('stale source')) : vi.fn().mockResolvedValue({ command_id: 'build', status: 'accepted' }) };
  const view = render(<BedroomTwin api={api as unknown as TwinPulseApi} product={state} refresh={vi.fn()} backendReady />);
  return { api, ...view };
}
async function prepare() {
  fireEvent.click(screen.getByText('Load saved room and model'));
  await screen.findByText('room');
}
describe('bedroom explicit local preview', () => {
  it('runs one synthetic suite and reviews its records without engine or robot commands',async()=>{
    const {api}=setup({...product,engine_connected:false});await prepare();
    const record=await api.rehearseBedroom();api.rehearseBedroom.mockClear();
    api.offlineBedroomAcceptance.mockResolvedValue({schema:'bedroom-offline-acceptance-1.0',revision:'bundle',
      scene_revision:'scene',source_revision:'manifest',provenance:'SYNTHETIC_PHOTO_APPROXIMATION',
      physical_validation:'NOT_RUN',motion_authorized:false,robot_connection:false,isaac_run:false,
      status:'SYNTHETIC_PASS',checks:{route_arrived:true,no_path_stopped:true},
      records:{route:record,detour_no_path:{...record,scenario:'detour_no_path',status:'NO_PATH'}},
      comparison:{revision:'comparison',conditions_revision:'conditions',eligible_for_efficiency_comparison:false,
        b_minus_a:null,candidates:[]},evaluation:{physical_validation:'NOT_RUN',overall_score:null}});
    fireEvent.click(screen.getByText('Run complete PC synthetic suite'));
    await screen.findByLabelText('PC synthetic suite result');
    expect(screen.getByText('SYNTHETIC_PASS · robot and Isaac not run')).toBeTruthy();
    fireEvent.click(screen.getByText('Review detour no path record'));
    await screen.findByText('NO_PATH · not physical validation');
    expect(api.offlineBedroomAcceptance).toHaveBeenCalledExactlyOnceWith('manifest');
    expect(api.rehearseBedroom).not.toHaveBeenCalled();expect(api.acquireLease).not.toHaveBeenCalled();
    expect(api.buildBedroom).not.toHaveBeenCalled();
  });
  it('reopens a server-verified saved suite without sending control commands',async()=>{
    const {api}=setup({...product,engine_connected:false});await prepare();
    const record=await api.rehearseBedroom();api.rehearseBedroom.mockClear();
    api.importBedroomOfflineAcceptance.mockResolvedValue({revision:'reopened',status:'SYNTHETIC_PASS',
      checks:{no_path_stopped:true},records:{route:record},comparison:{revision:'comparison',
        conditions_revision:'conditions',eligible_for_efficiency_comparison:false,b_minus_a:null,candidates:[]}});
    const file=new File(['{"revision":"reopened"}'],'saved.json',{type:'application/json'});
    Object.defineProperty(file,'text',{value:vi.fn().mockResolvedValue('{"revision":"reopened"}')});
    fireEvent.change(screen.getByLabelText(/Reopen saved PC synthetic suite/),{target:{files:[file]}});
    await screen.findByLabelText('PC synthetic suite result');
    expect(api.importBedroomOfflineAcceptance).toHaveBeenCalledExactlyOnceWith('manifest','{"revision":"reopened"}');
    expect(api.acquireLease).not.toHaveBeenCalled();expect(api.buildBedroom).not.toHaveBeenCalled();
  });
  it('plays and seeks the saved synthetic path locally without sending Isaac or robot commands',async()=>{
    const {api}=setup({...product,engine_connected:false});await prepare();
    const base=await api.rehearseBedroom();
    api.rehearseBedroom.mockResolvedValue({...base,events:[
      {t:.1,pose_after:[.01,0,0],proposed:[.03,0],decision:{allowed:true,reason:'CLEAR'}},
      {t:.2,pose_after:[.02,0,0],proposed:[0,0],decision:{allowed:true,reason:'STOP'}}]});
    fireEvent.click(screen.getByText('Run synthetic mission'));
    await screen.findByLabelText('Synthetic timeline controls');
    fireEvent.click(screen.getByText('Play replay'));
    await waitFor(()=>expect(screen.getByText(/Synthetic record frame 2 \/ 2/)).toBeTruthy());
    expect(api.replayBedroom).not.toHaveBeenCalled();expect(api.acquireLease).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('Restart replay'));
    expect(screen.getByText(/Synthetic record frame 0 \/ 2/)).toBeTruthy();
  });
  it('compares explicitly, selects stored candidate without new requests and clears stale result',async()=>{
    const {api}=setup({...product,engine_connected:false});await prepare();
    const record={status:'ARRIVED',scenario:'direct',revision:'direct-hash',duration_s:14,distance_m:.3,command_count:1,waypoints:[[0,0]],events:[]};
    api.compareBedroom.mockResolvedValue({revision:'compare',conditions_revision:'conditions',eligible_for_efficiency_comparison:true,
      b_minus_a:{duration_s:-7.8,distance_m:-.1},candidates:[{label:'B · 목표 직행 경로',record,metrics:{...record,goal_error_m:.014,
      min_guard_margin_m:.15,near_guard_samples:0,guard_samples:10,guard_denials:0,collision_count:null}}]});
    expect(api.compareBedroom).not.toHaveBeenCalled();fireEvent.click(screen.getByText('Compare two routes under identical conditions'));
    await screen.findByLabelText('Same-condition synthetic comparison');
    expect(api.compareBedroom).toHaveBeenCalledExactlyOnceWith('manifest');
    fireEvent.click(screen.getByText('A review record'));await screen.findByLabelText('Synthetic mission result');
    expect(api.rehearseBedroom).not.toHaveBeenCalled();expect(api.acquireLease).not.toHaveBeenCalled();
    await prepare();expect(screen.queryByLabelText('Same-condition synthetic comparison')).toBeNull();
  });
  it('clears comparison after failure and never retries automatically',async()=>{
    const {api}=setup();await prepare();api.compareBedroom.mockRejectedValue(new Error('comparison stale'));
    fireEvent.click(screen.getByText('Compare two routes under identical conditions'));await screen.findByText('comparison stale');
    expect(api.compareBedroom).toHaveBeenCalledTimes(1);expect(screen.queryByLabelText('Same-condition synthetic comparison')).toBeNull();
  });
  it('exports only the same server-produced comparison bytes and rejects a stale export',async()=>{
    const {api}=setup();await prepare();
    api.compareBedroom.mockResolvedValue({revision:'compare',conditions_revision:'conditions',eligible_for_efficiency_comparison:false,
      b_minus_a:null,candidates:[]});
    fireEvent.click(screen.getByText('Compare two routes under identical conditions'));
    await screen.findByLabelText('Same-condition synthetic comparison');
    api.exportBedroomComparison.mockResolvedValue({comparison_revision:'old',json_text:'{"revision":"old"}',sha256:'00'.repeat(32)});
    vi.stubGlobal('crypto',{subtle:{digest:vi.fn().mockResolvedValue(new Uint8Array(32).buffer)}});
    fireEvent.click(screen.getByText('Save comparison and both records as JSON'));
    await screen.findByText('The comparison record changed or saved file verification failed.');
    expect(api.exportBedroomComparison).toHaveBeenCalledExactlyOnceWith('manifest','compare');
    vi.unstubAllGlobals();
  });
  it('does not seek with an old engine that only supports static bedroom build',async()=>{
    const state={...product,snapshot:{...product.snapshot,capabilities:['bedroom_visual_v1']}} as ProductState;
    const {api}=setup(state);await prepare();fireEvent.click(screen.getByText('Run synthetic mission'));
    await screen.findByText('ARRIVED · not physical validation');fireEvent.click(screen.getByRole('checkbox'));
    expect((screen.getByText('Display selected record in Isaac') as HTMLButtonElement).disabled).toBe(true);
    expect(api.replayBedroom).not.toHaveBeenCalled();
  });
  it('seeks only on explicit action with reviewed scene and synthetic revision',async()=>{
    const {api}=setup();await prepare();fireEvent.click(screen.getByText('Run synthetic mission'));
    await screen.findByText('ARRIVED · not physical validation');
    const button=screen.getByText('Display selected record in Isaac') as HTMLButtonElement;
    expect(button.disabled).toBe(true);expect(api.replayBedroom).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('checkbox'));fireEvent.click(button);
    await waitFor(()=>expect(api.replayBedroom).toHaveBeenCalledExactlyOnceWith('manifest',
      {scenario:'route',revision:'result',frame:0},expect.any(String)));
    expect(api.buildBedroom).not.toHaveBeenCalled();
  });
  it('runs a synthetic mission once without engine lease or physical approval',async()=>{
    const {api}=setup({...product,engine_connected:false});
    expect(api.rehearseBedroom).not.toHaveBeenCalled();await prepare();
    fireEvent.click(screen.getByText('Run synthetic mission'));
    await screen.findByText('ARRIVED · not physical validation');
    expect(api.rehearseBedroom).toHaveBeenCalledExactlyOnceWith('manifest','route');
    expect(api.acquireLease).not.toHaveBeenCalled();expect(api.buildBedroom).not.toHaveBeenCalled();
    expect(screen.getByRole('img',{name:'Synthetic XY path · not Isaac playback'})).toBeTruthy();
    await prepare();expect(screen.queryByLabelText('Synthetic mission result')).toBeNull();
  });
  it('shows synthetic detour and no-path as distinct nonphysical outcomes',async()=>{
    const {api}=setup({...product,engine_connected:false});await prepare();
    const base=await api.rehearseBedroom();
    api.rehearseBedroom.mockResolvedValueOnce({...base,scenario:'detour',replan_events:[
      {t:.4,status:'NEW_SYNTHETIC_PATH',reason:'SYNTHETIC_OBSTACLE_EVENT',output_zero:true,waypoints:[[.1,.2]]}]});
    fireEvent.click(screen.getByText('Test synthetic stop and detour'));
    await screen.findByText(/NEW_SYNTHETIC_PATH/);
    expect(api.rehearseBedroom).toHaveBeenLastCalledWith('manifest','detour');
    api.rehearseBedroom.mockResolvedValueOnce({...base,scenario:'detour_no_path',status:'NO_PATH',replan_events:[
      {t:.4,status:'NO_PATH',reason:'START_OR_GOAL_BLOCKED',output_zero:true}]});
    fireEvent.click(screen.getByText('Test no-path stop'));
    await screen.findByText('NO_PATH · not physical validation');
    expect(api.rehearseBedroom).toHaveBeenLastCalledWith('manifest','detour_no_path');
    expect(api.acquireLease).not.toHaveBeenCalled();
    expect(api.buildBedroom).not.toHaveBeenCalled();
  });
  it('does not retry a failed rehearsal or display old success',async()=>{
    const {api}=setup();await prepare();api.rehearseBedroom.mockRejectedValue(new Error('source changed'));
    fireEvent.click(screen.getByText('Rehearse stale-sensor stop'));await screen.findByText('source changed');
    expect(api.rehearseBedroom).toHaveBeenCalledTimes(1);expect(screen.queryByLabelText('Synthetic mission result')).toBeNull();
  });
  it('refuses a stale synthetic record download without creating a blob',async()=>{
    const {api}=setup();await prepare();fireEvent.click(screen.getByText('Run synthetic mission'));
    await screen.findByText('ARRIVED · not physical validation');
    api.exportBedroomRehearsal.mockResolvedValue({record_revision:'old',json_text:'{"revision":"old"}',sha256:'00'.repeat(32)});
    vi.stubGlobal('crypto',{subtle:{digest:vi.fn().mockResolvedValue(new Uint8Array(32).buffer)}});
    fireEvent.click(screen.getByText('Save synthetic commands and observations as JSON'));
    await screen.findByText('The synthetic record changed or saved file verification failed.');
    expect(api.exportBedroomRehearsal).toHaveBeenCalledExactlyOnceWith('manifest','route','result');
    vi.unstubAllGlobals();
  });
  it('requires prepare, acknowledgement and then only queues a visual build', async () => {
    const { api } = setup();
    expect(api.prepareBedroom).not.toHaveBeenCalled();
    await prepare();
    const build = screen.getByText('Display room + Burger in Isaac') as HTMLButtonElement;
    expect(build.disabled).toBe(true);
    fireEvent.click(screen.getByRole('checkbox')); fireEvent.click(build);
    await waitFor(() => expect(api.buildBedroom).toHaveBeenCalledWith('manifest', true, expect.any(String)));
    await waitFor(() => expect(build.disabled).toBe(true));
    expect(api.acquireLease).toHaveBeenCalledTimes(1);
  });
  it('does not build without current engine capability', async () => {
    const { api } = setup({ ...product, engine_connected: false }); await prepare();
    fireEvent.click(screen.getByRole('checkbox'));
    expect((screen.getByText('Display room + Burger in Isaac') as HTMLButtonElement).disabled).toBe(true);
    expect(api.buildBedroom).not.toHaveBeenCalled();
  });
  it('does not trust cached readiness after the product state transport fails', async () => {
    const disconnected = { ...product, engine_connected: false, snapshot: null, engine_readiness: {
      bedroom_visual_v1: { feature: 'bedroom_visual_v1', ready: true, code: 'ready' },
    } } as ProductState;
    const { api } = setup(disconnected); await prepare(); fireEvent.click(screen.getByRole('checkbox'));
    expect((screen.getByText('Display room + Burger in Isaac') as HTMLButtonElement).disabled).toBe(true);
    expect(api.buildBedroom).not.toHaveBeenCalled();
  });
  it('uses backend readiness to reject a stale stage even if old snapshot flags look capable', async () => {
    const stale = { ...product, engine_readiness: {
      bedroom_visual_v1: { feature: 'bedroom_visual_v1', ready: false, code: 'runtime_identity_stale' },
    } } as ProductState;
    const { api } = setup(stale); await prepare(); fireEvent.click(screen.getByRole('checkbox'));
    expect((screen.getByText('Display room + Burger in Isaac') as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText('Isaac session or scene information is stale.')).toBeTruthy();
    expect(api.buildBedroom).not.toHaveBeenCalled();
  });
  it('can request a lease when the feature exists but Build is not yet permitted', async () => {
    const waiting = { ...product, engine_readiness: {
      bedroom_visual_v1: { feature: 'bedroom_visual_v1', ready: false, code: 'runtime_command_unavailable' },
    } } as ProductState;
    const { api } = setup(waiting); await prepare(); fireEvent.click(screen.getByRole('checkbox'));
    api.productState.mockResolvedValue({ ...waiting, lease_owned: true, engine_readiness: {
      bedroom_visual_v1: { feature: 'bedroom_visual_v1', ready: true, code: 'ready' },
    } });
    expect((screen.getByText('Display room + Burger in Isaac') as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(screen.getByText('Display room + Burger in Isaac'));
    await waitFor(() => expect(api.buildBedroom).toHaveBeenCalledTimes(1));
    expect(api.acquireLease).toHaveBeenCalledTimes(1);
  });
  it('clears acknowledgement after rejected build', async () => {
    setup(product, true); await prepare();
    fireEvent.click(screen.getByRole('checkbox')); fireEvent.click(screen.getByText('Display room + Burger in Isaac'));
    await screen.findByText('stale source');
    expect((screen.getByRole('checkbox') as HTMLInputElement).checked).toBe(false);
  });
  it('waits for the production bridge to observe the lease, then submits exactly once', async () => {
    const { api } = setup();
    api.productState.mockResolvedValueOnce({ ...product, lease_owned: false });
    await prepare(); fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByText('Display room + Burger in Isaac'));
    await waitFor(() => expect(api.productState).toHaveBeenCalledTimes(1));
    expect(api.buildBedroom).not.toHaveBeenCalled();
    await waitFor(() => expect(api.buildBedroom).toHaveBeenCalledTimes(1));
  });
  it('loss during preparation never sends a build', async () => {
    const { api } = setup();
    api.productState.mockResolvedValue({ ...product, engine_connected: false, lease_owned: true });
    await prepare(); fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByText('Display room + Burger in Isaac'));
    await screen.findByRole('alert'); expect(api.buildBedroom).not.toHaveBeenCalled();
  });
});
