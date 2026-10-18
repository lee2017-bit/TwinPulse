// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { fireEvent, render, screen, waitFor, cleanup } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ExecutionDiagnostics } from './ExecutionDiagnostics';
import type { TwinPulseApi } from './api';

afterEach(cleanup);
const health = {diagnostics_degraded:false,storage_errors:0,dropped_events:0};
function harness() {
  const execution = {execution_id:'a'.repeat(32),at:'2026-10-07',stage:'scene_generation',status:'failed',duration_s:1.25,
    metadata:{mode:'explicit_fixture'},first_error:{error_type:'ProviderTimeoutError'}};
  return {executionList:vi.fn().mockResolvedValue({executions:[execution],health}),
    executionDiagnostics:vi.fn().mockResolvedValue({manifest:{...execution,project_id:'default'},status:'failed',duration_s:1.25,
      first_error:execution.first_error,spans:[{span_id:'root',parent_span_id:null,stage:'planner',status:'failed',duration_s:1.2,metadata:{attempt_id:'b'.repeat(32)}}],
      events:[],health,raw_included:false,physical_authority:false}),
    exportExecutionDiagnostics:vi.fn(),conversationAction:vi.fn(),manualAction:vi.fn(),simulationRun:vi.fn()};
}
function linkedGraph() {
  return {schema_version:'1.0',project_id:'default',execution_id:'a'.repeat(32),scope:'recorded_one_hop_references',
    partial:false,checked_count:3,reverse_scanned_count:3,unavailable_count:0,
    limits:{nodes:32,edges:128,reverse_records:100,directory_entries:4096,total_read_bytes:8388608,record_read_bytes:1048576},
    nodes:[{execution_id:'a'.repeat(32),available:true,stage:'generation',status:'succeeded'},
      {execution_id:'c'.repeat(32),available:true,stage:'engine_command_build_site_scene',status:'failed'},
      {execution_id:'d'.repeat(32),available:false,stage:null,status:'unknown'}],
    edges:[{source:'c'.repeat(32),target:'a'.repeat(32),relation:'evidence_id'},
      {source:'a'.repeat(32),target:'d'.repeat(32),relation:'launch_execution_id'}],raw_included:false,physical_authority:false};
}
describe('read-only execution diagnostics', () => {
  it('shows the observed build metadata without invoking generation or motion',async()=>{
    const api={...harness(),runtimeDiagnostics:vi.fn().mockResolvedValue({
      release:{product_version:'0.1.0a1',build_id:'20261014T120000Z-reviewed',simulation_only:true}})};
    render(<ExecutionDiagnostics api={api as unknown as TwinPulseApi} close={()=>{}}/>);
    expect(await screen.findByText(/App version: 0.1.0a1.*20261014T120000Z-reviewed.*SIM-only alpha/)).toBeTruthy();
    expect(api.conversationAction).not.toHaveBeenCalled();expect(api.simulationRun).not.toHaveBeenCalled();
  });
  it('retains historical and invalid values without presenting them as calibrated bottlenecks', async () => {
    const api = harness(); const detail = await api.executionDiagnostics();
    api.executionDiagnostics.mockResolvedValue({...detail, events:[
      {span_id:'old',type:'profile_row',at:'now',metadata:{source_file:'copy.py',function:'deepcopy',timer_basis:'thread_cpu',calls:495,self_s:.359375,cumulative_s:0}},
      {span_id:'new',type:'profile_row',at:'now',metadata:{source_file:'compile.py',function:'compile',timer_basis:'thread_cpu',calls:1,self_s:.01,cumulative_s:.02,profile_valid:true,profile_id:'new',profiler_kind:'thread_filtered_cprofile'}},
      {span_id:'legacy',type:'profile_row',at:'now',metadata:{source_file:'legacy.py',function:'unverified',timer_basis:'thread_cpu',calls:1,self_s:.01,cumulative_s:.02}},
    ]} as never);
    render(<ExecutionDiagnostics api={api as unknown as TwinPulseApi} initialExecution={'a'.repeat(32)} close={()=>{}}/>);
    await screen.findByRole('table',{name:'Function profile measurements'});
    expect(screen.getByText('0.359 s')).toBeTruthy();
    expect(screen.getByText('Invalid measurement · not rankable')).toBeTruthy();
    expect(screen.getByText('Uncalibrated history · not rankable')).toBeTruthy();
    expect(screen.getByText('Validated owner-thread profile')).toBeTruthy();
    expect(screen.getByText(/Unrankable measurements retained/)).toBeTruthy();
    expect(api.conversationAction).not.toHaveBeenCalled();expect(api.manualAction).not.toHaveBeenCalled();
  });
  it('does not approve a plausible sibling row from an invalid or truncated profile', async () => {
    const api = harness(); const detail = await api.executionDiagnostics();
    api.executionDiagnostics.mockResolvedValue({...detail,events_truncated:true,events:[
      {span_id:'same',type:'profile_row',at:'now',metadata:{source_file:'bad.py',function:'bad',self_s:-1,cumulative_s:0,profile_valid:false}},
      {span_id:'same',type:'profile_row',at:'now',metadata:{source_file:'good.py',function:'good',self_s:.01,cumulative_s:.02,profile_valid:true,profile_id:'same',profiler_kind:'thread_filtered_cprofile'}},
      {span_id:'other',type:'profile_row',at:'now',metadata:{source_file:'other.py',function:'other',self_s:.01,cumulative_s:.02,profile_valid:true,profile_id:'other',profiler_kind:'thread_filtered_cprofile'}},
    ]} as never);
    render(<ExecutionDiagnostics api={api as unknown as TwinPulseApi} initialExecution={'a'.repeat(32)} close={()=>{}}/>);
    await screen.findByRole('table',{name:'Function profile measurements'});
    expect(screen.getAllByText('Invalid measurement · not rankable')).toHaveLength(2);
    expect(screen.getByText('Incomplete evidence · not rankable')).toBeTruthy();
    expect(screen.queryByText('Validated owner-thread profile')).toBeNull();
  });
  it('shows mission commit and unknown ACK separately without authorizing or replaying control',async()=>{
    const api={...harness(),executionDiagnostics:vi.fn().mockResolvedValue({
      manifest:{execution_id:'a'.repeat(32),project_id:'default',stage:'observed_mission',at:'2026-10-08',metadata:{}},
      status:'cancelled',duration_s:1,first_error:null,
      spans:[{span_id:'commit',parent_span_id:'root',stage:'mission_correction_commit',status:'succeeded',duration_s:.02,
        metadata:{measurement_source:'pc_observation',correction_revision:'b'.repeat(64)}},
        {span_id:'ack',parent_span_id:'root',stage:'mission_correction_ack',status:'unknown',duration_s:.1,
          metadata:{measurement_source:'pc_observation',remote_outcome:'unknown'}}],
      events:[],health,raw_included:false,physical_authority:false})};
    render(<ExecutionDiagnostics api={api as unknown as TwinPulseApi} initialExecution={'a'.repeat(32)} close={()=>{}}/>);
    await screen.findByText('mission_correction_commit');expect(screen.getByText('mission_correction_ack')).toBeTruthy();
    expect(screen.getByText(/Phase durations are PC-observed windows/)).toBeTruthy();
    expect(screen.getByText('b'.repeat(64))).toBeTruthy();expect(screen.getByText('remote outcome')).toBeTruthy();
    expect(api.conversationAction).not.toHaveBeenCalled();expect(api.manualAction).not.toHaveBeenCalled();expect(api.simulationRun).not.toHaveBeenCalled();
  });
  it('loads the graph only on request and shows incoming records and unavailable outgoing evidence',async()=>{
    const api={...harness(),executionGraph:vi.fn().mockResolvedValue({...linkedGraph(),partial:true})};
    render(<ExecutionDiagnostics api={api as unknown as TwinPulseApi} initialExecution={'a'.repeat(32)} close={()=>{}}/>);
    await screen.findByText('Show linked execution graph');expect(api.executionGraph).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('Show linked execution graph'));
    expect(await screen.findByText('Incoming · evidence id')).toBeTruthy();
    expect(screen.getByText(/Partial graph/)).toBeTruthy();
    expect(screen.getByText('d'.repeat(32)).hasAttribute('disabled')).toBe(true);
    fireEvent.click(screen.getByText('c'.repeat(32)));
    await waitFor(()=>expect(api.executionDiagnostics).toHaveBeenLastCalledWith('c'.repeat(32)));
    expect(screen.queryByRole('region',{name:'Linked execution graph'})).toBeNull();
    expect(api.conversationAction).not.toHaveBeenCalled();expect(api.manualAction).not.toHaveBeenCalled();expect(api.simulationRun).not.toHaveBeenCalled();
  });
  it('keeps the valid detail when graph lookup fails or returns a foreign project',async()=>{
    const api={...harness(),executionGraph:vi.fn().mockRejectedValue(new Error('Graph unavailable.'))};
    render(<ExecutionDiagnostics api={api as unknown as TwinPulseApi} initialExecution={'a'.repeat(32)} close={()=>{}}/>);
    fireEvent.click(await screen.findByText('Show linked execution graph'));
    await screen.findByText('Graph unavailable.');expect(screen.getByText('Stage timeline')).toBeTruthy();
    api.executionGraph.mockResolvedValue({...linkedGraph(),project_id:'other'});
    fireEvent.click(screen.getByText('Show linked execution graph'));
    await screen.findByText('Linked execution records do not match the selected project.');
    expect(screen.queryByText('c'.repeat(32))).toBeNull();expect(screen.getByText('Stage timeline')).toBeTruthy();
  });
  it('ignores a late graph result after leaving the selected execution',async()=>{
    let resolve!:(value:unknown)=>void;
    const api={...harness(),executionGraph:vi.fn().mockImplementation(()=>new Promise(value=>{resolve=value;}))};
    render(<ExecutionDiagnostics api={api as unknown as TwinPulseApi} initialExecution={'a'.repeat(32)} close={()=>{}}/>);
    fireEvent.click(await screen.findByText('Show linked execution graph'));
    await screen.findByText('Reading bounded linked execution records…');
    fireEvent.click(screen.getByText('All executions'));await screen.findByText('Search executions');
    resolve(linkedGraph());await waitFor(()=>expect(screen.queryByRole('region',{name:'Linked execution graph'})).toBeNull());
    expect(screen.queryByText('c'.repeat(32))).toBeNull();
  });
  it('distinguishes runtime observation elapsed from mission duration and confirmed cleanup',async()=>{
    const api=harness();const detail=await api.executionDiagnostics();
    api.executionDiagnostics.mockResolvedValue({...detail,manifest:{...detail.manifest,stage:'engine_runtime_observation'}});
    render(<ExecutionDiagnostics api={api as unknown as TwinPulseApi} initialExecution={'a'.repeat(32)} close={()=>{}}/>);
    expect(await screen.findByText(/not the full mission duration/)).toBeTruthy();
    expect(screen.getByText(/cleanup failure is not a confirmed stop/)).toBeTruthy();
  });
  it('searches server metadata and resets paging when filters change', async () => {
    const api=harness();const execution=(await api.executionList()).executions[0];api.executionList.mockClear();
    api.executionList.mockResolvedValue({executions:[execution],health,next_cursor:'saved-cursor',has_more:true,scanned_count:1});
    render(<ExecutionDiagnostics api={api as unknown as TwinPulseApi} close={()=>{}}/>);
    await waitFor(()=>expect(screen.getByText('ProviderTimeoutError')).toBeTruthy());
    fireEvent.change(screen.getByLabelText('Search saved metadata'),{target:{value:'mission-1'}});
    fireEvent.click(screen.getByText('Search executions'));
    await waitFor(()=>expect(api.executionList).toHaveBeenLastCalledWith({query:'mission-1',status:'',cursor:null}));
    await waitFor(()=>expect(screen.getByText('Older executions').hasAttribute('disabled')).toBe(false));
    fireEvent.click(screen.getByText('Older executions'));
    await waitFor(()=>expect(api.executionList).toHaveBeenLastCalledWith({query:'mission-1',status:'',cursor:'saved-cursor'}));
    await waitFor(()=>expect(screen.getByText(/Page 2/)).toBeTruthy());
    fireEvent.change(screen.getByLabelText('Status'),{target:{value:'failed'}});
    await waitFor(()=>expect(api.executionList).toHaveBeenLastCalledWith({query:'mission-1',status:'failed',cursor:null}));
    expect(screen.getByText(/Page 1/)).toBeTruthy();
    expect(api.conversationAction).not.toHaveBeenCalled();expect(api.manualAction).not.toHaveBeenCalled();
  });
  it('can read older empty search pages and refreshes from the beginning', async () => {
    const api=harness();api.executionList.mockResolvedValue({executions:[],health,next_cursor:'cursor-1',has_more:true,scanned_count:100});
    render(<ExecutionDiagnostics api={api as unknown as TwinPulseApi} close={()=>{}}/>);
    await waitFor(()=>expect(screen.getByText(/No matches in this scanned page/)).toBeTruthy());
    fireEvent.click(screen.getByText('Older executions'));
    await waitFor(()=>expect(api.executionList).toHaveBeenLastCalledWith({query:'',status:'',cursor:'cursor-1'}));
    await waitFor(()=>expect(screen.getByText('Refresh diagnostics').hasAttribute('disabled')).toBe(false));
    fireEvent.click(screen.getByText('Refresh diagnostics'));
    await waitFor(()=>expect(api.executionList).toHaveBeenLastCalledWith({query:'',status:'',cursor:null}));
  });
  it('opens only typed related execution IDs and preserves a back link', async () => {
    const api=harness();const detail=await api.executionDiagnostics();
    const related='c'.repeat(32);
    api.executionDiagnostics.mockImplementation(async(id:string)=>({...detail,manifest:{...detail.manifest,execution_id:id,
      metadata:{command_execution_id:related,evidence_id:'d'.repeat(32),evidence_kind:'private_raw',scene_edit_execution_id:'../../secret'}}}));
    render(<ExecutionDiagnostics api={api as unknown as TwinPulseApi} initialExecution={'a'.repeat(32)} close={()=>{}}/>);
    await waitFor(()=>expect(screen.getByText(related)).toBeTruthy());
    expect(screen.queryByText('d'.repeat(32))).toBeNull();expect(screen.queryByText('../../secret')).toBeNull();
    fireEvent.click(screen.getByText(related));
    await waitFor(()=>expect(api.executionDiagnostics).toHaveBeenLastCalledWith(related));
    await waitFor(()=>expect(screen.getByText('Back to previous execution').hasAttribute('disabled')).toBe(false));
    fireEvent.click(screen.getByText('Back to previous execution'));
    await waitFor(()=>expect(api.executionDiagnostics).toHaveBeenLastCalledWith('a'.repeat(32)));
    expect(api.executionList).not.toHaveBeenCalled();expect(api.manualAction).not.toHaveBeenCalled();
  });
  it('clears older results when searching fails and reports unavailable records', async () => {
    const api=harness();api.executionList.mockResolvedValue({executions:[],health:{...health,diagnostics_degraded:true,unavailable_executions:2}});
    render(<ExecutionDiagnostics api={api as unknown as TwinPulseApi} close={()=>{}}/>);
    await waitFor(()=>expect(screen.getByRole('alert').textContent).toContain('2 unavailable executions'));
    api.executionList.mockRejectedValueOnce(new Error('Search unavailable'));
    fireEvent.change(screen.getByLabelText('Search saved metadata'),{target:{value:'failed'}});
    fireEvent.click(screen.getByText('Search executions'));
    await waitFor(()=>expect(screen.getByRole('alert').textContent).toContain('Search unavailable'));
    expect(screen.queryByText(/No saved executions match/)).toBeNull();
  });
  it('shows measured frame waiting separately from creating its failure record',async()=>{
    const api=harness();const detail=await api.executionDiagnostics();
    api.executionDiagnostics.mockResolvedValue({...detail,manifest:{...detail.manifest,stage:'engine_view_observation'},
      duration_s:0,spans:[{span_id:'wait',parent_span_id:null,stage:'first_current_frame_deadline',status:'failed',
        duration_s:0,metadata:{measurement_source:'backend_local_elapsed',elapsed_s:15.078}}]} as never);
    render(<ExecutionDiagnostics api={api as unknown as TwinPulseApi} initialExecution={'a'.repeat(32)} close={()=>{}}/>);
    expect(await screen.findByText(/15.078 s · measured backend-local waiting/)).toBeTruthy();
    expect(screen.getByText(/Record creation: 0.000 s/)).toBeTruthy();
    expect(screen.getByText(/does not identify a GPU, capture, or network cause/)).toBeTruthy();
    expect(api.simulationRun).not.toHaveBeenCalled();
  });
  it('clears earlier details when refreshing the same execution fails', async () => {
    const api=harness();render(<ExecutionDiagnostics api={api as unknown as TwinPulseApi} initialExecution={'a'.repeat(32)} close={()=>{}}/>);
    await waitFor(()=>expect(screen.getByText('planner')).toBeTruthy());
    api.executionDiagnostics.mockRejectedValueOnce(new Error('Refresh unavailable'));
    fireEvent.click(screen.getByText('Refresh diagnostics'));
    await waitFor(()=>expect(screen.getByRole('alert').textContent).toContain('Refresh unavailable'));
    expect(screen.queryByText('planner')).toBeNull();
  });
  it('labels a bounded timeline and export as incomplete', async () => {
    const api=harness();
    const detail=await api.executionDiagnostics();
    api.executionDiagnostics.mockResolvedValue({...detail,event_count:9000,events_truncated:true});
    render(<ExecutionDiagnostics api={api as unknown as TwinPulseApi} initialExecution={'a'.repeat(32)} close={()=>{}}/>);
    await waitFor(()=>expect(screen.getByRole('alert').textContent).toContain('9000 total'));
    expect(screen.getByRole('alert').textContent).toContain('not a complete execution history');
  });
  it('opens the exact failed execution directly from an error link', async () => {
    const api=harness();render(<ExecutionDiagnostics api={api as unknown as TwinPulseApi} initialExecution={'a'.repeat(32)} close={()=>{}}/>);
    await waitFor(()=>expect(screen.getByText('planner')).toBeTruthy());
    expect(api.executionDiagnostics).toHaveBeenCalledWith('a'.repeat(32));
    expect(api.executionList).not.toHaveBeenCalled();
  });
  it('lists failures, opens stage details and never executes a product action', async () => {
    const api=harness();render(<ExecutionDiagnostics api={api as unknown as TwinPulseApi} close={()=>{}}/>);
    await waitFor(()=>expect(screen.getByText('ProviderTimeoutError')).toBeTruthy());
    fireEvent.click(screen.getByText('a'.repeat(32)));
    await waitFor(()=>expect(screen.getByText('planner')).toBeTruthy());
    expect(screen.getByText('attempt id')).toBeTruthy();
    expect(screen.getByText('b'.repeat(32))).toBeTruthy();
    expect(api.conversationAction).not.toHaveBeenCalled();expect(api.manualAction).not.toHaveBeenCalled();expect(api.simulationRun).not.toHaveBeenCalled();
  });
  it('shows storage degradation without silently reporting success', async () => {
    const api=harness();api.executionList.mockResolvedValue({executions:[],health:{...health,diagnostics_degraded:true,dropped_events:3}});
    render(<ExecutionDiagnostics api={api as unknown as TwinPulseApi} close={()=>{}}/>);
    await waitFor(()=>expect(screen.getByRole('alert').textContent).toContain('3 dropped events'));
  });
  it('does not show stale details when a newer read fails', async () => {
    const api=harness();api.executionDiagnostics.mockRejectedValue(new Error('Execution unavailable'));
    render(<ExecutionDiagnostics api={api as unknown as TwinPulseApi} close={()=>{}}/>);
    await waitFor(()=>expect(screen.getByText('a'.repeat(32))).toBeTruthy());
    fireEvent.click(screen.getByText('a'.repeat(32)));
    await waitFor(()=>expect(screen.getByRole('alert').textContent).toContain('Execution unavailable'));
    expect(screen.queryByText('planner')).toBeNull();
  });
});
