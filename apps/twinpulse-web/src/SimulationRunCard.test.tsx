// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {Activity,createRef} from 'react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {ApiError,type TwinPulseApi} from './api';
import {SimulationRunCard,type SimulationPlan} from './SimulationRunCard';
import type {ProductState} from './types';
import type {Operation,SimulationSnapshot} from './engine-contracts';
import type {SimulationReview} from './conversation-types';

function harness(){
  const snapshot:SimulationSnapshot={schema_version:'1.1',engine_session_id:'engine',stage_epoch:'epoch',project_id:'room',
    applied_revision:null,run_id:null,sequence:1,runtime_state:'idle',safety_state:null,safety_reason:null,
    permitted_commands:['build_site_scene'],capabilities:['site_scene_build_v2','site_simulation_v1','site_simulation_preview_v1'],sim_time_s:0,sampled_at_utc:null,frame_id:'world',
    position_m:null,yaw_rad:null,roll_rad:null,pitch_rad:null,linear_speed_mps:null,distance_to_goal_m:null,cross_track_error_m:null,telemetry_available:false};
  const state:ProductState={project_id:'room',engine_connected:true,engine_session_id:'engine',stage_epoch:'epoch',lease_owned:true,
    control_lease_id:'lease',snapshot,engine_readiness:{site_scene_build_v2:{feature:'site_scene_build_v2',ready:true,code:'ready'}},operations:[],artifacts:[]};
  const operation=(kind:Operation['command_type']):Operation=>({command_id:kind,command_type:kind,project_id:'room',engine_session_id:'engine',
    stage_epoch:'epoch',expected_applied_revision:'current',status:'succeeded',receipt:null});
  const plan:SimulationPlan={plan_id:'plan',scene_revision:'current',mode:'SIM',asset_id:'burger',start:[0,0],goal:[0,.5],route:[[0,.5]],
    yaw_rad:0,max_linear_mps:.15,max_angular_rps:.6,physical_authority:false};
  const api={simulationPlan:vi.fn().mockResolvedValue(plan),acquireLease:vi.fn().mockResolvedValue({control_lease_id:'lease'}),
    renewLease:vi.fn().mockResolvedValue({}),acknowledge:vi.fn().mockResolvedValue({}),productState:vi.fn(async()=>state),
    command:vi.fn(async(kind:Operation['command_type'])=>{const op=operation(kind);state.operations.push(op);return op;}),
    simulationRun:vi.fn(async(_plan:string,_revision:string,_request:string)=>{const op=operation('run');state.operations.push(op);return op;}),
    simulationOutcome:vi.fn().mockResolvedValue(operation('run'))};
  const report=vi.fn();
  const component=()=> <SimulationRunCard api={api as unknown as TwinPulseApi} revision="current" artifactId="artifact" product={state} report={report}/>;
  return {api,state,snapshot,plan,operation,report,component};
}
async function preview(){fireEvent.click(screen.getByRole('button',{name:'Preview SIM route'}));await waitFor(()=>expect(screen.getByRole('button',{name:'Run simulation'})).toHaveProperty('disabled',false));}

function resetHarness(){
  const h=harness();
  h.snapshot.applied_revision='current';h.snapshot.runtime_state='paused';h.snapshot.run_id='old-plan';
  h.snapshot.permitted_commands=['reset','run'];
  const resetOperation:Operation={...h.operation('reset'),receipt:{schema_version:'1.1',command_id:'reset',command_type:'reset',
    project_id:'room',engine_session_id:'engine',stage_epoch:'epoch',status:'succeeded',message:'Simulation reset',
    error_code:null,applied_revision:'current',build_fingerprint:null}};
  h.api.command.mockImplementation(async()=>{
    h.state.operations.push(resetOperation);h.snapshot.runtime_state='built';h.snapshot.run_id=null;h.snapshot.sequence++;
    return resetOperation;
  });
  return {...h,resetOperation};
}

describe('explicit current-scene SIM reset',()=>{
  it('leases and acknowledges Reset, retains the scene and invalidates the old review without motion',async()=>{
    const h=resetHarness();
    const review:SimulationReview={request_id:'old-review',text:'Go to bed',scene_revision:'current',start_source:'saved_sim_placement',
      plan:h.plan,target:null,choices:[],drawing:{bounds:[-2,2,-2,2],boxes:[],discs:[]}};
    const component=(value:SimulationReview)=><SimulationRunCard api={h.api as unknown as TwinPulseApi} revision="current" artifactId="artifact" product={h.state} report={h.report} review={value}/>;
    const view=render(component(review));
    expect(h.api.command).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button',{name:'Reset simulation'}));
    expect(await screen.findByText(/Simulation reset confirmed.*saved scene is retained; no motion restarted/)).toBeTruthy();
    expect(h.api.command).toHaveBeenCalledExactlyOnceWith('reset','current');
    expect(h.api.acquireLease.mock.invocationCallOrder[0]).toBeLessThan(h.api.acknowledge.mock.invocationCallOrder[0]);
    expect(h.api.acknowledge.mock.invocationCallOrder[0]).toBeLessThan(h.api.command.mock.invocationCallOrder[0]);
    expect(h.api.simulationRun).not.toHaveBeenCalled();expect(h.api.simulationPlan).not.toHaveBeenCalled();
    view.rerender(component({...review}));
    expect(screen.getByRole('region',{name:'Simulation route'}).getAttribute('data-plan-id')).toBe('');
    expect(screen.getByRole('region',{name:'Simulation route'}).getAttribute('data-review-request-id')).toBe('');
    expect(screen.queryByRole('img',{name:'SIM planned route and observed trajectory'})).toBeNull();
    expect(screen.getByRole('button',{name:'Run simulation'})).toHaveProperty('disabled',true);
    view.rerender(component({...review,request_id:'fresh-review'}));
    await waitFor(()=>expect(screen.getByRole('button',{name:'Run simulation'})).toHaveProperty('disabled',false));
  });
  it.each(['moving','other-revision','other-engine','other-epoch','other-project','no-permission','no-lease','busy','unknown'])(
    'does not submit Reset when %s',reason=>{
      const h=resetHarness();
      if(reason==='moving')h.snapshot.runtime_state='running';
      if(reason==='other-revision')h.snapshot.applied_revision='other';
      if(reason==='other-engine')h.snapshot.engine_session_id='other';
      if(reason==='other-epoch')h.snapshot.stage_epoch='other';
      if(reason==='other-project')h.snapshot.project_id='other';
      if(reason==='no-permission')h.snapshot.permitted_commands=[];
      if(reason==='no-lease')h.state.lease_owned=false;
      if(reason==='busy'||reason==='unknown')h.state.operations.push({...h.operation('run'),status:reason==='busy'?'accepted':'unknown'});
      render(h.component());expect(screen.getByRole('button',{name:'Reset simulation'})).toHaveProperty('disabled',true);
      fireEvent.click(screen.getByRole('button',{name:'Reset simulation'}));
      expect(h.api.command).not.toHaveBeenCalled();expect(h.api.acquireLease).not.toHaveBeenCalled();
    });
  it('rechecks permission after ACK and never submits to a changed revision',async()=>{
    const h=resetHarness();h.api.acknowledge.mockImplementation(async()=>{h.snapshot.applied_revision='other';return {};});
    render(h.component());fireEvent.click(screen.getByRole('button',{name:'Reset simulation'}));
    await waitFor(()=>expect(h.report).toHaveBeenCalledWith(expect.stringContaining('No Reset was sent')));
    expect(h.api.command).not.toHaveBeenCalled();
  });
  it('requires a newer idle observation as well as the exact successful receipt',async()=>{
    const h=resetHarness();h.api.command.mockImplementation(async()=>{h.state.operations.push(h.resetOperation);return h.resetOperation;});
    render(h.component());fireEvent.click(screen.getByRole('button',{name:'Reset simulation'}));
    await screen.findByText(/Reset submitted/);
    expect(screen.queryByText(/Simulation reset confirmed/)).toBeNull();
    expect(screen.getByRole('button',{name:'Reset simulation'})).toHaveProperty('disabled',true);
    h.snapshot.runtime_state='built';h.snapshot.run_id=null;h.snapshot.sequence++;
    expect(await screen.findByText(/Simulation reset confirmed/)).toBeTruthy();
    expect(h.api.command).toHaveBeenCalledTimes(1);
  });
  it('does not accept a succeeded operation without its receipt or automatically retry',async()=>{
    const h=resetHarness();h.resetOperation.receipt=null;
    render(h.component());fireEvent.click(screen.getByRole('button',{name:'Reset simulation'}));
    await waitFor(()=>expect(h.report).toHaveBeenCalledWith(expect.stringContaining('Reset receipt identity was not confirmed')));
    expect(screen.queryByText(/Simulation reset confirmed/)).toBeNull();
    expect(screen.getByRole('button',{name:'Reset simulation'})).toHaveProperty('disabled',true);
    expect(screen.getByRole('button',{name:'Preview SIM route'})).toHaveProperty('disabled',true);
    expect(h.api.command).toHaveBeenCalledTimes(1);expect(h.api.simulationRun).not.toHaveBeenCalled();
  });
  it('does not reuse the pre-Reset endpoint while parent observation is still stale',async()=>{
    const h=resetHarness();h.snapshot.runtime_state='completed';h.snapshot.telemetry_available=true;
    h.snapshot.position_m=[0,.5,0];h.snapshot.distance_to_goal_m=0;
    const staleProduct={...h.state,snapshot:{...h.snapshot}};
    render(<SimulationRunCard api={h.api as unknown as TwinPulseApi} revision="current" artifactId="artifact" product={staleProduct} report={h.report}/>);
    expect(screen.getByText(/Destination reached/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'Reset simulation'}));
    expect(await screen.findByText(/Simulation reset confirmed/)).toBeTruthy();
    // The fresh Reset read is built/run_id=null/sequence+1; rendered props
    // deliberately remain the old completed observation at the same goal.
    expect(staleProduct.snapshot.runtime_state).toBe('completed');
    expect(screen.queryByText(/Destination reached/)).toBeNull();
    expect(screen.getByRole('textbox',{name:'SIM start'})).toHaveProperty('disabled',false);
    fireEvent.click(screen.getByRole('button',{name:'Preview SIM route'}));
    await waitFor(()=>expect(h.api.simulationPlan).toHaveBeenCalledExactlyOnceWith('current',[0,0],[0,.5],0));
    expect(screen.queryByText(/Already at this goal/)).toBeNull();
    expect(h.api.simulationRun).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button',{name:'Run simulation'}));
    await waitFor(()=>expect(h.api.simulationRun).toHaveBeenCalledTimes(1));
    expect(h.report).not.toHaveBeenCalled();
  });
  it('keeps an unknown Reset locked and never resends or starts motion',async()=>{
    const h=resetHarness();h.api.command.mockRejectedValue(new ApiError('delivery_unknown','Reset response timed out'));
    render(h.component());fireEvent.click(screen.getByRole('button',{name:'Reset simulation'}));
    await waitFor(()=>expect(h.report).toHaveBeenCalledWith('Reset response timed out'));
    expect(screen.getByText(/Reset outcome is not yet confirmed/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'Reset simulation'}));
    fireEvent.click(screen.getByRole('button',{name:'Preview SIM route'}));
    expect(h.api.command).toHaveBeenCalledTimes(1);expect(h.api.simulationPlan).not.toHaveBeenCalled();expect(h.api.simulationRun).not.toHaveBeenCalled();
  });
  it('blocks Reset while a Run delivery remains unknown even if the observed runtime is paused',async()=>{
    const h=resetHarness();h.api.simulationRun.mockRejectedValue(new ApiError('delivery_unknown','Run response timed out'));
    h.api.simulationOutcome.mockRejectedValue(new ApiError('command_unknown','No receipt yet'));
    render(h.component());await preview();fireEvent.click(screen.getByRole('button',{name:'Run simulation'}));
    await waitFor(()=>expect(h.report).toHaveBeenCalledWith('Run response timed out'));
    expect(screen.getByRole('button',{name:'Reset simulation'})).toHaveProperty('disabled',true);
    fireEvent.click(screen.getByRole('button',{name:'Reset simulation'}));expect(h.api.command).not.toHaveBeenCalled();
  });
});

describe('SIM route execution ordering and boundaries',()=>{
  it('allows the initial lease-free View when capability and idle identity match, then acknowledges before acquiring permission',async()=>{
    const h=harness();h.state.lease_owned=false;h.state.control_lease_id=null;h.state.engine_readiness!.site_scene_build_v2.ready=false;
    h.snapshot.permitted_commands=['get_state','focus_scene'];let finish!:()=>void;
    h.api.acknowledge.mockImplementationOnce(()=>new Promise<void>(resolve=>{finish=resolve;}));
    h.api.acquireLease.mockImplementation(async()=>{h.state.lease_owned=true;h.state.control_lease_id='lease';h.snapshot.permitted_commands=['build_site_scene'];h.state.engine_readiness!.site_scene_build_v2.ready=true;return {control_lease_id:'lease'};});
    h.api.command.mockImplementation(async kind=>{h.snapshot.applied_revision='current';h.snapshot.runtime_state='built';const op=h.operation(kind);h.state.operations.push(op);return op;});
    render(h.component());const view=screen.getByRole('button',{name:'View current Twin'});expect(view).toHaveProperty('disabled',false);fireEvent.click(view);
    expect(h.api.acknowledge).toHaveBeenCalledOnce();expect(h.api.acquireLease).not.toHaveBeenCalled();expect(h.api.command).not.toHaveBeenCalled();
    await act(async()=>finish());await screen.findByText(/Draft apply confirmed/);
    expect(h.api.acknowledge.mock.invocationCallOrder[0]).toBeLessThan(h.api.acquireLease.mock.invocationCallOrder[0]);
    expect(h.api.acquireLease.mock.invocationCallOrder[0]).toBeLessThan(h.api.command.mock.invocationCallOrder[0]);
    expect(h.api.command).toHaveBeenCalledExactlyOnceWith('build_site_scene','current','artifact',undefined);expect(h.api.simulationRun).not.toHaveBeenCalled();
  });
  it('does not offer View from engine-connected alone when explicit site Build capability is absent',()=>{
    const h=harness();h.snapshot.capabilities=['site_simulation_v1'];render(h.component());
    const view=screen.getByRole('button',{name:'View current Twin'});expect(view).toHaveProperty('disabled',true);fireEvent.click(view);
    expect(screen.getByRole('status',{name:'Isaac Build readiness'})).toBeTruthy();
    expect(h.api.acknowledge).not.toHaveBeenCalled();expect(h.api.acquireLease).not.toHaveBeenCalled();expect(h.api.command).not.toHaveBeenCalled();
  });
  it.each(['engine','epoch'])('does not acquire a lease or Build if %s changes in the same context while ACK is pending',async changed=>{
    const h=harness();let finish!:()=>void;h.api.acknowledge.mockImplementationOnce(()=>new Promise<void>(resolve=>{finish=resolve;}));
    const view=render(h.component());fireEvent.click(screen.getByRole('button',{name:'View current Twin'}));expect(h.api.acknowledge).toHaveBeenCalledOnce();
    if(changed==='engine'){h.state.engine_session_id='replacement';h.snapshot.engine_session_id='replacement';}else{h.state.stage_epoch='replacement';h.snapshot.stage_epoch='replacement';}
    view.rerender(h.component());await act(async()=>finish());
    expect(h.report).toHaveBeenCalledWith(expect.stringContaining('Isaac engine identity changed'));
    expect(h.api.acquireLease).not.toHaveBeenCalled();expect(h.api.command).not.toHaveBeenCalled();expect(h.api.simulationRun).not.toHaveBeenCalled();
  });
  it.each(['engine','epoch'])('sends no Build if the post-lease state reports a different %s before parent polling observes it',async changed=>{
    const h=harness();const next={...h.state,snapshot:{...h.snapshot}};
    if(changed==='engine'){next.engine_session_id='replacement';next.snapshot.engine_session_id='replacement';}else{next.stage_epoch='replacement';next.snapshot.stage_epoch='replacement';}
    h.api.productState.mockResolvedValue(next);render(h.component());fireEvent.click(screen.getByRole('button',{name:'View current Twin'}));
    await waitFor(()=>expect(h.report).toHaveBeenCalledWith(expect.stringContaining('Isaac engine identity changed')));
    expect(h.api.acquireLease).toHaveBeenCalledOnce();expect(h.api.command).not.toHaveBeenCalled();expect(h.api.simulationRun).not.toHaveBeenCalled();
  });
  it.each(['capability','permission','identity'])('retains the bounded readiness wait but sends no Build when fresh post-lease %s is missing',async missing=>{
    vi.useFakeTimers();const h=harness();const snapshot={...h.snapshot,capabilities:[...h.snapshot.capabilities],permitted_commands:[...h.snapshot.permitted_commands]};
    if(missing==='capability')snapshot.capabilities=[];if(missing==='permission')snapshot.permitted_commands=['get_state','focus_scene'];if(missing==='identity')snapshot.stage_epoch='another-stage';
    h.api.productState.mockResolvedValue({...h.state,snapshot});const view=render(h.component());
    await act(async()=>fireEvent.click(screen.getByRole('button',{name:'View current Twin'})));await act(async()=>vi.advanceTimersByTimeAsync(6500));
    expect(h.report).toHaveBeenCalledWith(expect.stringContaining('No Build was sent'));expect(h.api.command).not.toHaveBeenCalled();
    expect(h.api.acquireLease).toHaveBeenCalledOnce();expect(h.api.simulationRun).not.toHaveBeenCalled();view.unmount();vi.useRealTimers();
  });
  it('rejects a mismatched fresh lease before dispatch and never resends a broker-rejected Build',async()=>{
    const h=harness();h.state.control_lease_id='different-lease';render(h.component());fireEvent.click(screen.getByRole('button',{name:'View current Twin'}));
    await waitFor(()=>expect(h.report).toHaveBeenCalledWith(expect.stringContaining('Current Build lease ownership is not confirmed')));
    expect(h.api.command).not.toHaveBeenCalled();h.state.control_lease_id='lease';h.report.mockClear();
    h.api.command.mockRejectedValueOnce(new ApiError('site_scene_capability_missing','Current engine cannot build site scenes'));
    fireEvent.click(screen.getByRole('button',{name:'View current Twin'}));await waitFor(()=>expect(h.report).toHaveBeenCalledExactlyOnceWith('Current engine cannot build site scenes'));
    expect(h.api.command).toHaveBeenCalledOnce();expect(h.api.simulationRun).not.toHaveBeenCalled();
  });
  it.each(['unmount','context','revision','project'])('does not publish a late preparation failure after its %s owner is retired',async changed=>{
    const h=harness(),api=Object.assign(h.api,{context:'context-a'});let reject!:(reason:Error)=>void;
    h.api.command.mockImplementationOnce(()=>new Promise<Operation>((_resolve,fail)=>{reject=fail;}));
    const component=(revision='current')=><SimulationRunCard api={api as unknown as TwinPulseApi} revision={revision} artifactId="artifact" product={h.state} report={h.report}/>;
    const view=render(component());fireEvent.click(screen.getByRole('button',{name:'View current Twin'}));await waitFor(()=>expect(h.api.command).toHaveBeenCalledOnce());
    if(changed==='unmount')view.unmount();else{
      if(changed==='context')api.context='context-b';if(changed==='project')h.state.project_id='other-project';
      view.rerender(component(changed==='revision'?'other-revision':'current'));
    }
    await act(async()=>reject(new Error('Old view failed after ownership changed')));
    expect(h.report).not.toHaveBeenCalled();expect(h.api.simulationRun).not.toHaveBeenCalled();
  });
  it('does not let an old preparation finally unlock a newer owner action',async()=>{
    const h=harness(),api=Object.assign(h.api,{context:'context-a'});let rejectOld!:(error:Error)=>void,rejectNew!:(error:Error)=>void;
    h.api.command.mockImplementationOnce(()=>new Promise<Operation>((_resolve,reject)=>{rejectOld=reject;}))
      .mockImplementationOnce(()=>new Promise<Operation>((_resolve,reject)=>{rejectNew=reject;}));
    const component=()=><SimulationRunCard api={api as unknown as TwinPulseApi} revision="current" artifactId="artifact" product={h.state} report={h.report}/>;
    const view=render(component());fireEvent.click(screen.getByRole('button',{name:'View current Twin'}));await waitFor(()=>expect(h.api.command).toHaveBeenCalledTimes(1));
    api.context='context-b';view.rerender(component());fireEvent.click(screen.getByRole('button',{name:'View current Twin'}));await waitFor(()=>expect(h.api.command).toHaveBeenCalledTimes(2));
    await act(async()=>rejectOld(new Error('Old error')));expect(h.report).not.toHaveBeenCalled();expect(screen.getByRole('button',{name:'View current Twin'})).toHaveProperty('disabled',true);
    await act(async()=>rejectNew(new Error('Current explicit failure')));expect(h.report).toHaveBeenCalledExactlyOnceWith('Current explicit failure');
  });
  it('does not turn transport recovery into automatic generation-preview Build or lease acquisition',async()=>{
    const h=harness();const review:SimulationReview={request_id:'stale-review',text:'Generated SIM preview',scene_revision:'current',start_source:'planned_sim_spawn',
      plan:h.plan,target:null,choices:[],drawing:{bounds:[-2,2,-2,2],boxes:[],discs:[]}};
    const component=(fresh:boolean)=><SimulationRunCard api={h.api as unknown as TwinPulseApi} revision="current" artifactId="artifact" product={h.state} report={h.report} review={review} fresh={fresh}/>;
    const view=render(component(false));expect(screen.getByRole('button',{name:'View current Twin'})).toHaveProperty('disabled',true);
    view.rerender(component(true));await act(async()=>{});expect(h.api.acquireLease).not.toHaveBeenCalled();expect(h.api.command).not.toHaveBeenCalled();
    expect(h.api.simulationRun).not.toHaveBeenCalled();
  });
  it('rechecks freshness after lease acquisition before Build and acknowledges before acquiring the lease',async()=>{
    const h=harness();let finish!:(value:{control_lease_id:string})=>void;h.api.acquireLease.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}));
    const component=(fresh:boolean)=><SimulationRunCard api={h.api as unknown as TwinPulseApi} revision="current" artifactId="artifact" product={h.state} report={h.report} fresh={fresh}/>;
    const view=render(component(true));fireEvent.click(screen.getByRole('button',{name:'View current Twin'}));await waitFor(()=>expect(h.api.acquireLease).toHaveBeenCalledOnce());view.rerender(component(false));
    await act(async()=>finish({control_lease_id:'lease'}));expect(h.api.acknowledge).toHaveBeenCalledOnce();expect(h.api.acknowledge.mock.invocationCallOrder[0]).toBeLessThan(h.api.acquireLease.mock.invocationCallOrder[0]);
    expect(h.api.command).not.toHaveBeenCalled();expect(h.api.simulationRun).not.toHaveBeenCalled();
  });
  it('does not let an old context lease reply replace the newer owner lease or its renewal',async()=>{
    vi.useFakeTimers();const h=harness(),api=Object.assign(h.api,{context:'context-a'});let finish!:(value:{control_lease_id:string})=>void;
    h.snapshot.applied_revision='current';h.snapshot.runtime_state='built';
    h.state.control_lease_id='new-lease';
    h.api.acquireLease.mockResolvedValue({control_lease_id:'new-lease'}).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}));
    const component=()=><SimulationRunCard api={api as unknown as TwinPulseApi} revision="current" artifactId="artifact" product={h.state} report={h.report}/>;
    const view=render(component());await act(async()=>fireEvent.click(screen.getByRole('button',{name:'View current Twin'})));
    api.context='context-b';view.rerender(component());await act(async()=>fireEvent.click(screen.getByRole('button',{name:'View current Twin'})));
    expect(h.api.acquireLease).toHaveBeenCalledTimes(2);expect(h.api.command).toHaveBeenCalledOnce();
    await act(async()=>finish({control_lease_id:'old-lease'}));await act(async()=>vi.advanceTimersByTimeAsync(750));
    expect(h.api.renewLease).toHaveBeenCalledExactlyOnceWith('new-lease');expect(h.report).not.toHaveBeenCalled();view.unmount();vi.useRealTimers();
  });
  it('keeps observed moving Stop available while fresh scene actions are locked',async()=>{
    const h=harness();h.snapshot.applied_revision='current';h.snapshot.runtime_state='running';h.snapshot.telemetry_available=true;h.snapshot.run_id='run';
    render(<SimulationRunCard api={h.api as unknown as TwinPulseApi} revision="current" artifactId="artifact" product={h.state} report={h.report} fresh={false}/>);
    const stop=screen.getByRole('button',{name:'Stop simulation'});expect(stop).toHaveProperty('disabled',false);fireEvent.click(stop);
    await waitFor(()=>expect(h.api.command).toHaveBeenCalledExactlyOnceWith('pause','current'));expect(h.api.simulationRun).not.toHaveBeenCalled();
  });
  it('explains arrival and does not submit an identical too-close preview or Run',async()=>{
    const h=harness();h.snapshot.applied_revision='current';h.snapshot.run_id='plan';
    h.snapshot.runtime_state='completed';h.snapshot.telemetry_available=true;
    h.snapshot.position_m=[0,.46,0];h.snapshot.distance_to_goal_m=.04;
    render(h.component());
    expect(screen.getByText(/Destination reached/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'Preview SIM route'}));
    expect(await screen.findByText(/Already at this goal/)).toBeTruthy();
    expect(h.api.simulationPlan).not.toHaveBeenCalled();expect(h.api.simulationRun).not.toHaveBeenCalled();
    expect(h.report).not.toHaveBeenCalled();
  });
  afterEach(()=>vi.useRealTimers());
  it('Activity suspension stops the lease timer and does not publish an in-flight old-owner renewal failure on restore',async()=>{
    const h=resetHarness();let rejectRenew!:(error:Error)=>void;
    h.api.renewLease.mockImplementation(()=>new Promise((_resolve,reject)=>{rejectRenew=reject;}));
    const component=(hidden:boolean)=><Activity mode={hidden?'hidden':'visible'}>{h.component()}</Activity>;
    vi.useFakeTimers();const view=render(component(false));
    await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'Reset simulation'}));});
    expect(screen.getByText(/Simulation reset confirmed/)).toBeTruthy();
    await act(async()=>{await vi.advanceTimersByTimeAsync(750);});expect(h.api.renewLease).toHaveBeenCalledOnce();
    view.rerender(component(true));
    await act(async()=>{rejectRenew(new ApiError('delivery_unknown','Old lease delivery unknown'));await vi.advanceTimersByTimeAsync(3000);});
    expect(h.api.renewLease).toHaveBeenCalledOnce();expect(h.report).not.toHaveBeenCalled();
    view.rerender(component(false));await act(async()=>{await vi.advanceTimersByTimeAsync(1500);});
    expect(h.api.renewLease).toHaveBeenCalledOnce();expect(h.api.acquireLease).toHaveBeenCalledOnce();
    expect(screen.queryByText(/Control lease lost/)).toBeNull();expect(h.api.simulationRun).not.toHaveBeenCalled();view.unmount();
  });
  it('explicitly displays an all-resolved saved Twin on a fresh engine without automatic Run',async()=>{
    const h=harness();h.snapshot.capabilities=['site_scene_build_v2'];
    h.api.command.mockImplementation(async(kind:Operation['command_type'])=>{
      const op=h.operation(kind);h.state.operations.push(op);h.snapshot.applied_revision='current';h.snapshot.runtime_state='built';return op;
    });
    render(h.component());
    expect(h.api.command).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button',{name:'View current Twin'}));
    expect(await screen.findByText(/Draft apply confirmed/)).toBeTruthy();
    expect(h.api.command).toHaveBeenCalledWith('build_site_scene','current','artifact',undefined);
    expect(h.api.simulationPlan).not.toHaveBeenCalled();expect(h.api.simulationRun).not.toHaveBeenCalled();
  });
  it('can build a pending draft without requiring simulation motion capabilities',async()=>{
    const h=harness();h.snapshot.applied_revision='current';h.snapshot.runtime_state='built';h.snapshot.capabilities=['site_scene_build_v2'];
    render(<SimulationRunCard api={h.api as unknown as TwinPulseApi} revision="current" artifactId="artifact" product={h.state} report={h.report} taskBlocked/>);
    fireEvent.click(screen.getByRole('button',{name:'View draft in Isaac'}));
    expect(await screen.findByText(/Draft apply confirmed.*No motion is authorized/)).toBeTruthy();
    expect(h.api.command).toHaveBeenCalledWith('build_site_scene','current','artifact',undefined);
    expect(h.api.simulationPlan).not.toHaveBeenCalled();expect(h.api.simulationRun).not.toHaveBeenCalled();
    expect(h.report).not.toHaveBeenCalled();
  });
  it('pending objects allow only draft viewing and never hide observed moving Stop',async()=>{
    const h=harness();h.snapshot.applied_revision='current';h.snapshot.runtime_state='built';
    const component=()=> <SimulationRunCard api={h.api as unknown as TwinPulseApi} revision="current" artifactId="artifact" product={h.state} report={h.report} taskBlocked/>;
    const rendered=render(component());
    expect(screen.getByRole('button',{name:'View draft in Isaac'})).toBeTruthy();
    expect(screen.queryByRole('button',{name:'Preview SIM route'})).toBeNull();
    expect(screen.queryByRole('button',{name:'Run simulation'})).toBeNull();
    expect(h.api.simulationPlan).not.toHaveBeenCalled();expect(h.api.simulationRun).not.toHaveBeenCalled();
    h.snapshot.runtime_state='running';h.snapshot.run_id='plan';h.snapshot.telemetry_available=true;
    rendered.rerender(component());
    expect(screen.getByRole('button',{name:'Stop simulation'})).toHaveProperty('disabled',false);
  });
  it('never restores an old chat route into a pending draft',async()=>{
    const h=harness();h.snapshot.applied_revision='current';h.snapshot.runtime_state='built';
    const review:SimulationReview={request_id:'old-review',text:'Go to bed',scene_revision:'current',start_source:'saved_sim_placement',plan:h.plan,target:null,choices:[],drawing:{bounds:[-2,2,-2,2],boxes:[],discs:[]}};
    render(<SimulationRunCard api={h.api as unknown as TwinPulseApi} revision="current" artifactId="artifact" product={h.state} report={h.report} review={review} taskBlocked/>);
    expect(screen.getByRole('region',{name:'Simulation route'}).getAttribute('data-plan-id')).toBe('');
    expect(screen.queryByRole('img',{name:'SIM planned route and observed trajectory'})).toBeNull();
    expect(screen.queryByRole('textbox',{name:'SIM goal'})).toBeNull();
    expect(screen.queryByText(/Chat goal reviewed.*Select Run simulation/)).toBeNull();
    expect(h.api.simulationRun).not.toHaveBeenCalled();
  });
  it('a pending chat request locks the old plan while keeping observed moving Stop available',async()=>{
    const h=harness();h.snapshot.applied_revision='current';h.snapshot.runtime_state='built';
    const review:SimulationReview={request_id:'review',text:'Go to bed',scene_revision:'current',start_source:'saved_sim_placement',plan:h.plan,target:null,choices:[],drawing:{bounds:[-2,2,-2,2],boxes:[],discs:[]}};
    const component=(chatPending:boolean)=><SimulationRunCard api={h.api as unknown as TwinPulseApi} revision="current" artifactId="artifact" product={h.state} report={h.report} review={review} chatPending={chatPending}/>;
    const rendered=render(component(true));
    expect(screen.getByRole('button',{name:'Run simulation'})).toHaveProperty('disabled',true);
    expect(screen.getByRole('region',{name:'Simulation route'}).getAttribute('data-plan-id')).toBe('plan');
    expect(screen.getByText(/Preparing the current chat request/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'Run simulation'}));expect(h.api.simulationRun).not.toHaveBeenCalled();
    h.snapshot.runtime_state='running';h.snapshot.run_id='plan';h.snapshot.telemetry_available=true;
    rendered.rerender(component(true));expect(screen.getByRole('button',{name:'Stop simulation'})).toHaveProperty('disabled',false);
  });
  it('a browser-only display failure blocks Run but never disables Stop for an observed moving SIM',async()=>{
    const h=harness();h.snapshot.applied_revision='current';h.snapshot.runtime_state='built';
    const review:SimulationReview={request_id:'review',text:'Go to bed',scene_revision:'current',start_source:'saved_sim_placement',plan:h.plan,target:null,choices:[],drawing:{bounds:[-2,2,-2,2],boxes:[],discs:[]}};
    const component=(blocked:boolean)=><SimulationRunCard api={h.api as unknown as TwinPulseApi} revision="current" artifactId="artifact" product={h.state} report={h.report} review={review} browserBlocked={blocked}/>;
    const rendered=render(component(true));
    expect(screen.getByRole('button',{name:'Run simulation'})).toHaveProperty('disabled',true);
    fireEvent.click(screen.getByRole('button',{name:'Run simulation'}));expect(h.api.simulationRun).not.toHaveBeenCalled();
    rendered.rerender(component(false));await waitFor(()=>expect(screen.getByRole('button',{name:'Run simulation'})).toHaveProperty('disabled',false));
    h.snapshot.runtime_state='running';h.snapshot.run_id='run';h.snapshot.telemetry_available=true;
    rendered.rerender(component(true));expect(screen.getByRole('button',{name:'Stop simulation'})).toHaveProperty('disabled',false);
    fireEvent.click(screen.getByRole('button',{name:'Stop simulation'}));
    await waitFor(()=>expect(h.api.command).toHaveBeenCalledWith('pause','current'));
    expect(h.api.simulationRun).not.toHaveBeenCalled();
  });
  it.each(['waiting','failed','unknown'] as const)('blocks Run while the same applied scene display is %s',async status=>{
    const h=harness();h.state.build_view={command_id:'build',engine_session_id:'engine',stage_epoch:'epoch',
      applied_revision:'current',status,error_code:status==='waiting'?null:'first_current_frame_timeout',execution_id:null};
    render(h.component());fireEvent.click(screen.getByRole('button',{name:'Preview SIM route'}));
    await waitFor(()=>expect(h.api.simulationPlan).toHaveBeenCalledTimes(1));
    expect(screen.getByRole('button',{name:'Run simulation'})).toHaveProperty('disabled',true);
    expect(h.api.simulationRun).not.toHaveBeenCalled();
  });
  it('prepares a fresh generated room once but never starts motion automatically',async()=>{
    const h=harness();
    const previous=h.api.command.getMockImplementation()!;
    h.api.command.mockImplementation(async(kind)=>{const op=await previous(kind);h.snapshot.applied_revision='current';h.snapshot.runtime_state='built';return op;});
    const review:SimulationReview={request_id:'generate-choice',text:'Generated SIM preview',scene_revision:'current',start_source:'planned_sim_spawn',
      plan:h.plan,target:null,choices:[],drawing:{bounds:[-2,2,-2,2],boxes:[],discs:[]}};
    const props={api:h.api as unknown as TwinPulseApi,revision:'current',artifactId:'artifact',product:h.state,report:h.report,review};
    const rendered=render(<SimulationRunCard {...props}/>);
    await waitFor(()=>expect(screen.getByText(/Scene applied in Isaac\. Check the current 3D display/)).toBeTruthy());
    expect(h.api.command).toHaveBeenCalledTimes(1);
    expect(h.api.command).toHaveBeenCalledWith('build_site_scene','current','artifact','plan');
    expect(h.api.simulationRun).not.toHaveBeenCalled();
    rendered.rerender(<SimulationRunCard {...props} review={{...review}}/>);
    expect(h.api.command).toHaveBeenCalledTimes(1);
  });
  it('chat Stop control is explicit, uses pause and is never invoked on mount',async()=>{
    const h=harness();h.snapshot.applied_revision='current';h.snapshot.runtime_state='running';h.snapshot.run_id='run';h.snapshot.telemetry_available=true;h.snapshot.position_m=[0,0,.02];
    const control=createRef<{stop:()=>void}>();
    render(<SimulationRunCard api={h.api as unknown as TwinPulseApi} revision="current" artifactId="artifact" product={h.state} report={h.report} stopHandle={control}/>);
    expect(h.api.command).not.toHaveBeenCalled();
    await act(async()=>control.current!.stop());
    await waitFor(()=>expect(h.api.command).toHaveBeenCalledWith('pause','current'));
    expect(h.api.simulationRun).not.toHaveBeenCalled();
  });
  it('an old engine cannot prepare or rearm a generated preview after failure',async()=>{
    const h=harness();h.snapshot.applied_revision='current';h.snapshot.runtime_state='built';
    h.snapshot.capabilities=['site_scene_build_v2','site_simulation_v1'];
    const review:SimulationReview={request_id:'generate-choice',text:'Generated SIM preview',scene_revision:'current',start_source:'planned_sim_spawn',
      plan:h.plan,target:null,choices:[],drawing:{bounds:[-2,2,-2,2],boxes:[],discs:[]}};
    render(<SimulationRunCard api={h.api as unknown as TwinPulseApi} revision="current" artifactId="artifact" product={h.state} report={h.report} review={review}/>);
    await waitFor(()=>expect(h.report).toHaveBeenCalledWith(expect.stringContaining('Updated Isaac adapter')));
    expect(h.api.command).not.toHaveBeenCalled();expect(h.api.simulationRun).not.toHaveBeenCalled();
    expect(screen.getByRole('button',{name:'Run simulation'})).toHaveProperty('disabled',true);
  });
  it('loads an acknowledged chat preview without auto Run and never rearms from polling',async()=>{
    const h=harness();h.snapshot.applied_revision='current';h.snapshot.runtime_state='built';
    const review:SimulationReview={request_id:'goal-1',text:'Go to bed',scene_revision:'current',start_source:'saved_sim_placement',plan:h.plan,target:null,choices:[],drawing:{bounds:[-2,2,-2,2],boxes:[],discs:[]}};
    const component=(value:SimulationReview|null)=><SimulationRunCard api={h.api as unknown as TwinPulseApi} revision="current" artifactId="artifact" product={h.state} report={h.report} review={value}/>;
    const view=render(component(review));
    await waitFor(()=>expect(screen.getByRole('button',{name:'Run simulation'})).toHaveProperty('disabled',false));
    expect(h.api.simulationRun).not.toHaveBeenCalled();expect(screen.getByRole('img',{name:'SIM planned route and observed trajectory'})).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'Run simulation'}));await waitFor(()=>expect(h.api.simulationRun).toHaveBeenCalledTimes(1));
    await waitFor(()=>expect(screen.getByRole('button',{name:'Run simulation'})).toHaveProperty('disabled',true));
    view.rerender(component({...review}));expect(screen.getByRole('button',{name:'Run simulation'})).toHaveProperty('disabled',true);
    view.rerender(component({...review,request_id:'goal-2'}));await waitFor(()=>expect(screen.getByRole('button',{name:'Run simulation'})).toHaveProperty('disabled',false));
    view.rerender(component(null));await waitFor(()=>expect(screen.getByRole('button',{name:'Run simulation'})).toHaveProperty('disabled',true));
  });
  it('does not auto-plan, lease, Build or Run when opened',()=>{
    const h=harness();render(h.component());expect(h.api.simulationPlan).not.toHaveBeenCalled();expect(h.api.acquireLease).not.toHaveBeenCalled();
    expect(h.api.command).not.toHaveBeenCalled();expect(h.api.simulationRun).not.toHaveBeenCalled();
  });
  it('does not send Run after a Build receipt until the current applied snapshot is idle',async()=>{
    const h=harness();render(h.component());await preview();fireEvent.click(screen.getByRole('button',{name:'Run simulation'}));
    await waitFor(()=>expect(h.api.command).toHaveBeenCalledWith('build_site_scene','current','artifact','plan'));
    await waitFor(()=>expect(h.api.productState.mock.calls.length).toBeGreaterThanOrEqual(3));
    expect(h.api.simulationRun).not.toHaveBeenCalled();
    h.snapshot.applied_revision='current';h.snapshot.runtime_state='running';
    await new Promise(resolve=>setTimeout(resolve,220));expect(h.api.simulationRun).not.toHaveBeenCalled();
    h.snapshot.runtime_state='built';await waitFor(()=>expect(h.api.simulationRun).toHaveBeenCalledTimes(1));
    expect(h.report).not.toHaveBeenCalled();
  });
  it('blocks unsafe review and requires an explicit fresh route after recovery without redundant Build',async()=>{
    const h=harness();h.snapshot.applied_revision='current';h.snapshot.runtime_state='paused';h.snapshot.safety_state='lease_lost';
    const view=render(h.component());
    expect(screen.getByRole('button',{name:'Preview SIM route'})).toHaveProperty('disabled',true);
    expect(h.api.command).not.toHaveBeenCalled();expect(h.api.simulationRun).not.toHaveBeenCalled();
    h.snapshot.safety_state=null;view.rerender(h.component());await preview();fireEvent.click(screen.getByRole('button',{name:'Run simulation'}));
    await waitFor(()=>expect(h.api.simulationRun).toHaveBeenCalledTimes(1));expect(h.api.command).not.toHaveBeenCalled();
  });
  it('surfaces a failed Build and never sends Run',async()=>{
    const h=harness();h.api.command.mockImplementation(async kind=>{const op={...h.operation(kind),status:'failed' as const};h.state.operations.push(op);return op;});
    render(h.component());await preview();fireEvent.click(screen.getByRole('button',{name:'Run simulation'}));
    await waitFor(()=>expect(h.report).toHaveBeenCalledWith('failed'));expect(h.api.simulationRun).not.toHaveBeenCalled();
  });
  it('checks a lost Run response without repeating it',async()=>{
    const h=harness();h.snapshot.applied_revision='current';h.snapshot.runtime_state='built';
    h.api.simulationRun.mockRejectedValue(new TypeError('Network lost'));
    render(h.component());await preview();fireEvent.click(screen.getByRole('button',{name:'Run simulation'}));
    await waitFor(()=>expect(h.api.simulationOutcome).toHaveBeenCalled());expect(h.api.simulationRun).toHaveBeenCalledTimes(1);
    const request=h.api.simulationRun.mock.calls[0];expect(h.api.simulationOutcome).toHaveBeenCalledWith(request[2]);
  });
  it('waits for POST acceptance before looking up the saved Run request',async()=>{
    const h=harness();h.snapshot.applied_revision='current';h.snapshot.runtime_state='built';
    let accept!:(op:Operation)=>void;
    h.api.simulationRun.mockImplementation(()=>new Promise(resolve=>{accept=resolve;}));
    h.api.simulationOutcome.mockResolvedValue({...h.operation('run'),status:'accepted'});
    render(h.component());await preview();vi.useFakeTimers();
    await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'Run simulation'}));});
    expect(h.api.simulationRun).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/Waiting for Run acceptance/)).toBeTruthy();
    await act(async()=>{await vi.advanceTimersByTimeAsync(3000);});
    expect(h.api.simulationOutcome).not.toHaveBeenCalled();
    expect(screen.getByRole('button',{name:'Run simulation'})).toHaveProperty('disabled',true);
    await act(async()=>{accept({...h.operation('run'),status:'accepted'});});
    const requestId=h.api.simulationRun.mock.calls[0][2];
    expect(h.api.simulationOutcome).toHaveBeenCalledExactlyOnceWith(requestId);
    expect(screen.getByText(/Checking the accepted Run receipt/)).toBeTruthy();
    expect(h.api.simulationRun).toHaveBeenCalledTimes(1);
  });
  it('uses the terminal POST Operation directly without a redundant result lookup',async()=>{
    const h=harness();h.snapshot.applied_revision='current';h.snapshot.runtime_state='built';
    render(h.component());await preview();fireEvent.click(screen.getByRole('button',{name:'Run simulation'}));
    expect(await screen.findByText(/Run acknowledged/)).toBeTruthy();
    expect(h.api.simulationOutcome).not.toHaveBeenCalled();
    expect(h.api.simulationRun).toHaveBeenCalledTimes(1);
  });
  it('surfaces an accepted request lookup failure without treating it as success or resending Run',async()=>{
    const h=harness();h.snapshot.applied_revision='current';h.snapshot.runtime_state='built';
    h.api.simulationRun.mockResolvedValue({...h.operation('run'),status:'accepted'});
    h.api.simulationOutcome.mockRejectedValue(new ApiError('command_unknown','Saved Run request was not found'));
    render(h.component());await preview();fireEvent.click(screen.getByRole('button',{name:'Run simulation'}));
    await waitFor(()=>expect(h.report).toHaveBeenCalledWith(expect.stringContaining('command_unknown')));
    expect(screen.getByText(/Run result lookup failed: Saved Run request was not found/)).toBeTruthy();
    expect(screen.queryByText(/Run acknowledged/)).toBeNull();
    expect(screen.getByRole('button',{name:'Run simulation'})).toHaveProperty('disabled',true);
    expect(h.api.simulationRun).toHaveBeenCalledTimes(1);
  });
  it.each(['revision','project','context'] as const)('discards a late POST acceptance after the %s changes',async changed=>{
    const h=harness();h.snapshot.applied_revision='current';h.snapshot.runtime_state='built';
    const apiWithContext=Object.assign(h.api,{context:'context-a'});
    let accept!:(op:Operation)=>void;
    h.api.simulationRun.mockImplementation(()=>new Promise(resolve=>{accept=resolve;}));
    const component=(revision='current')=><SimulationRunCard api={apiWithContext as unknown as TwinPulseApi} revision={revision} artifactId="artifact" product={h.state} report={h.report}/>;
    const view=render(component());await preview();fireEvent.click(screen.getByRole('button',{name:'Run simulation'}));
    await waitFor(()=>expect(h.api.simulationRun).toHaveBeenCalledTimes(1));
    if(changed==='project')h.state.project_id='new-project';
    if(changed==='context')apiWithContext.context='context-b';
    view.rerender(component(changed==='revision'?'new-revision':'current'));
    await act(async()=>{accept({...h.operation('run'),status:'accepted'});});
    expect(h.api.simulationOutcome).not.toHaveBeenCalled();
    expect(screen.queryByText(/Checking the accepted Run receipt/)).toBeNull();
    expect(screen.queryByText(/Run acknowledged/)).toBeNull();
    expect(h.report).not.toHaveBeenCalled();
  });
  it('does not submit Run after its room preparation belongs to an old revision',async()=>{
    const h=harness();
    const component=(revision:string)=><SimulationRunCard api={h.api as unknown as TwinPulseApi} revision={revision} artifactId="artifact" product={h.state} report={h.report}/>;
    const view=render(component('current'));await preview();fireEvent.click(screen.getByRole('button',{name:'Run simulation'}));
    await waitFor(()=>expect(h.api.command).toHaveBeenCalledWith('build_site_scene','current','artifact','plan'));
    view.rerender(component('new-revision'));
    h.snapshot.applied_revision='current';h.snapshot.runtime_state='built';
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve,220));});
    expect(h.api.simulationRun).not.toHaveBeenCalled();
  });
  it('a definite rejection clears the preview and requires a new review',async()=>{
    const h=harness();h.snapshot.applied_revision='current';h.snapshot.runtime_state='built';
    h.api.simulationRun.mockRejectedValue(new ApiError('simulation_not_ready','Scene changed'));
    render(h.component());await preview();fireEvent.click(screen.getByRole('button',{name:'Run simulation'}));
    await waitFor(()=>expect(h.report).toHaveBeenCalledWith('Scene changed'));
    expect(screen.getByRole('button',{name:'Run simulation'})).toHaveProperty('disabled',true);
    expect(h.api.simulationOutcome).not.toHaveBeenCalled();
  });
  it('a transport timeout is an unknown delivery, not permission to send another Run',async()=>{
    const h=harness();h.snapshot.applied_revision='current';h.snapshot.runtime_state='built';
    h.api.simulationRun.mockRejectedValue(new ApiError('delivery_unknown','Run response timed out'));
    h.api.simulationOutcome.mockRejectedValue(new ApiError('command_unknown','No receipt yet'));
    render(h.component());await preview();fireEvent.click(screen.getByRole('button',{name:'Run simulation'}));
    await waitFor(()=>expect(h.report).toHaveBeenCalledWith('Run response timed out'));
    expect(screen.getByRole('button',{name:'Run simulation'})).toHaveProperty('disabled',true);
    expect(h.api.simulationRun).toHaveBeenCalledTimes(1);
  });
  it('bounds receipt polling and offers read-only recovery without re-execution',async()=>{
    const h=harness();h.snapshot.applied_revision='current';h.snapshot.runtime_state='built';
    h.api.simulationRun.mockRejectedValue(new TypeError('Network lost'));
    h.api.simulationOutcome.mockRejectedValue(new ApiError('command_unknown','No receipt yet'));
    render(h.component());await preview();vi.useFakeTimers();
    await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'Run simulation'}));});
    await act(async()=>{await vi.advanceTimersByTimeAsync(46000);});
    const count=h.api.simulationOutcome.mock.calls.length;
    expect(screen.getByRole('button',{name:'Check Run result · read only'})).toBeTruthy();
    await act(async()=>{await vi.advanceTimersByTimeAsync(10000);});
    expect(h.api.simulationOutcome).toHaveBeenCalledTimes(count);expect(h.api.simulationRun).toHaveBeenCalledTimes(1);
    h.api.simulationOutcome.mockResolvedValue(h.operation('run'));
    await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'Check Run result · read only'}));});
    expect(h.api.simulationRun).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('button',{name:'Check Run result · read only'})).toBeNull();
  });
  it('Stop remains independent while Run receipt is pending',async()=>{
    const h=harness();h.snapshot.applied_revision='current';h.snapshot.runtime_state='built';
    h.api.simulationRun.mockImplementation(()=>new Promise(()=>{}));h.api.simulationOutcome.mockImplementation(()=>new Promise(()=>{}));
    const view=render(h.component());await preview();fireEvent.click(screen.getByRole('button',{name:'Run simulation'}));
    await waitFor(()=>expect(h.api.simulationRun).toHaveBeenCalled());
    expect(h.api.simulationOutcome).not.toHaveBeenCalled();
    h.snapshot.runtime_state='running';h.snapshot.telemetry_available=true;h.snapshot.run_id='plan';h.snapshot.position_m=[0,0,0];view.rerender(h.component());
    fireEvent.click(screen.getByRole('button',{name:'Stop simulation'}));await waitFor(()=>expect(h.api.command).toHaveBeenCalledWith('pause','current'));
  });
  it('closing preparation never sends a subsequent Run',async()=>{
    const h=harness();const view=render(h.component());await preview();fireEvent.click(screen.getByRole('button',{name:'Run simulation'}));
    await waitFor(()=>expect(h.api.command).toHaveBeenCalled());view.unmount();h.snapshot.applied_revision='current';h.snapshot.runtime_state='built';
    await new Promise(resolve=>setTimeout(resolve,220));expect(h.api.simulationRun).not.toHaveBeenCalled();
  });
  it('discards a reviewed route after a disconnect or a new engine identity',async()=>{
    const h=harness();const view=render(h.component());await preview();
    h.state.engine_connected=false;view.rerender(h.component());
    await waitFor(()=>expect(screen.getByRole('button',{name:'Run simulation'})).toHaveProperty('disabled',true));
    h.state.engine_connected=true;h.snapshot.engine_session_id='replacement';view.rerender(h.component());
    expect(screen.getByRole('button',{name:'Run simulation'})).toHaveProperty('disabled',true);
    expect(h.api.simulationRun).not.toHaveBeenCalled();
  });
  it('discards an old review on a current runtime fault without replaying it after recovery',async()=>{
    const h=harness();const view=render(h.component());await preview();
    h.snapshot.runtime_state='error';h.snapshot.safety_state='simulation_error';view.rerender(h.component());
    await waitFor(()=>expect(screen.getByRole('button',{name:'Run simulation'})).toHaveProperty('disabled',true));
    h.snapshot.runtime_state='built';h.snapshot.safety_state=null;view.rerender(h.component());
    expect(screen.getByRole('button',{name:'Run simulation'})).toHaveProperty('disabled',true);
    expect(h.api.simulationRun).not.toHaveBeenCalled();
  });
});
