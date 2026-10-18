// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {act,fireEvent,render,screen} from '@testing-library/react';
import {Activity} from 'react';
import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {ApiError,type TwinPulseApi} from './api';
import {SimulationRunCard,type SimulationPlan} from './SimulationRunCard';
import type {ProductState} from './types';
import type {Operation,SimulationSnapshot} from './engine-contracts';

// Mock-only lease lifecycle coverage. No backend, Isaac or browser connection.
function harness(){
  const snapshot:SimulationSnapshot={schema_version:'1.1',engine_session_id:'engine',stage_epoch:'epoch',project_id:'room',
    applied_revision:'current',run_id:null,sequence:1,runtime_state:'built',safety_state:null,safety_reason:null,
    permitted_commands:['build_site_scene','run','reset'],capabilities:['site_scene_build_v2','site_simulation_v1','site_simulation_preview_v1'],
    sim_time_s:0,sampled_at_utc:null,frame_id:'world',position_m:null,yaw_rad:null,roll_rad:null,pitch_rad:null,
    linear_speed_mps:null,distance_to_goal_m:null,cross_track_error_m:null,telemetry_available:false};
  const state:ProductState={project_id:'room',engine_connected:true,engine_session_id:'engine',stage_epoch:'epoch',lease_owned:true,
    control_lease_id:'lease-1',snapshot,operations:[],artifacts:[],
    engine_readiness:{site_scene_build_v2:{feature:'site_scene_build_v2',ready:true,code:'ready'}}};
  const plan:SimulationPlan={plan_id:'route',scene_revision:'current',mode:'SIM',asset_id:'burger',start:[0,0],goal:[0,.5],
    route:[[0,.5]],yaw_rad:0,max_linear_mps:.15,max_angular_rps:.6,physical_authority:false};
  let acquired=0,command=0;
  const operation=(kind:Operation['command_type']):Operation=>({command_id:`command-${++command}`,command_type:kind,
    project_id:state.project_id,engine_session_id:'engine',stage_epoch:'epoch',expected_applied_revision:snapshot.applied_revision,
    status:'succeeded',receipt:null});
  const api={context:'context-a',acquireLease:vi.fn(async()=>{state.control_lease_id=`lease-${++acquired}`;return {control_lease_id:state.control_lease_id,ttl_s:3};}),
    renewLease:vi.fn(async(_lease:string)=>({control_lease_id:'renewed',ttl_s:3})),acknowledge:vi.fn(async()=>({})),
    productState:vi.fn(async()=>state),simulationPlan:vi.fn(async()=>plan),
    command:vi.fn(async(kind:Operation['command_type'])=>{const op=operation(kind);state.operations.push(op);return op;}),
    simulationRun:vi.fn(async()=>operation('run')),simulationOutcome:vi.fn(async()=>operation('run'))};
  const report=vi.fn();
  const component=(writer=false,revision='current',product:ProductState|null=state)=><SimulationRunCard api={api as unknown as TwinPulseApi}
    revision={revision} artifactId="artifact" product={product} report={report} sceneWriterActive={writer}/>;
  return {api,state,snapshot,report,component,operation};
}
async function click(name:string){await act(async()=>{fireEvent.click(screen.getByRole('button',{name}));});}
async function tick(ms=750){await act(async()=>{await vi.advanceTimersByTimeAsync(ms);});}
function delayedRenew(h:ReturnType<typeof harness>){
  let reject!:(reason:Error)=>void;
  h.api.renewLease.mockImplementationOnce(()=>new Promise((_resolve,fail)=>{reject=fail;}));
  return ()=>reject(new ApiError('control_lease_invalid','Control lease is invalid or expired'));
}

describe('SIM lease writer handoff and response ownership',()=>{
  beforeEach(()=>vi.useFakeTimers());
  afterEach(()=>vi.useRealTimers());

  it('retains an unknown Run request and its lease across missing product observations for the same context',async()=>{
    const h=harness();h.api.simulationRun.mockRejectedValueOnce(new ApiError('delivery_unknown','Run delivery unknown'));
    h.api.simulationOutcome.mockImplementation(()=>new Promise<Operation>(()=>{}));
    const view=render(h.component());await click('View current Twin');await click('Preview SIM route');await click('Run simulation');
    const request=h.api.simulationOutcome.mock.calls[0];expect(request).toBeTruthy();
    view.rerender(h.component(false,'current',null));
    expect(screen.getByText(/Run delivery is unconfirmed\. Checking the same request only/)).toBeTruthy();
    expect(screen.getByRole('button',{name:'Run simulation'})).toHaveProperty('disabled',true);expect(screen.getByRole('button',{name:'Reset simulation'})).toHaveProperty('disabled',true);
    await tick();expect(h.api.renewLease).toHaveBeenLastCalledWith('lease-2');
    view.rerender(h.component());
    expect(screen.getByText(/Run delivery is unconfirmed\. Checking the same request only/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'Run simulation'}));fireEvent.click(screen.getByRole('button',{name:'Reset simulation'}));await tick();
    expect(h.api.simulationRun).toHaveBeenCalledOnce();expect(h.api.simulationOutcome).toHaveBeenCalledTimes(1);
    expect(h.api.simulationOutcome.mock.calls[0]).toEqual(request);expect(h.api.acquireLease).toHaveBeenCalledTimes(2);
    expect(h.api.command.mock.calls.filter(([kind])=>kind==='reset')).toHaveLength(0);view.unmount();
  });
  it('retains an unconfirmed Reset and its lease across missing product observations and same-project recovery',async()=>{
    const h=harness(),view=render(h.component());await click('View current Twin');
    h.api.command.mockRejectedValueOnce(new ApiError('delivery_unknown','Reset outcome unknown'));await click('Reset simulation');
    expect(screen.getByText(/Reset outcome is not yet confirmed/)).toBeTruthy();
    view.rerender(h.component(false,'current',null));expect(screen.getByText(/Reset outcome is not yet confirmed/)).toBeTruthy();await tick();
    expect(h.api.renewLease).toHaveBeenLastCalledWith('lease-2');
    view.rerender(h.component());expect(screen.getByText(/Reset outcome is not yet confirmed/)).toBeTruthy();
    expect(screen.getByRole('button',{name:'Reset simulation'})).toHaveProperty('disabled',true);expect(screen.getByRole('button',{name:'Run simulation'})).toHaveProperty('disabled',true);
    fireEvent.click(screen.getByRole('button',{name:'Reset simulation'}));fireEvent.click(screen.getByRole('button',{name:'Run simulation'}));await tick();
    expect(h.api.command.mock.calls.filter(([kind])=>kind==='reset')).toHaveLength(1);expect(h.api.acquireLease).toHaveBeenCalledTimes(2);
    expect(h.api.simulationRun).not.toHaveBeenCalled();view.unmount();
  });
  it.each(['context','project'])('still invalidates an old Reset latch on a confirmed %s change after a missing observation',async changed=>{
    const h=harness(),view=render(h.component());await click('View current Twin');
    h.api.command.mockRejectedValueOnce(new ApiError('delivery_unknown','Reset outcome unknown'));await click('Reset simulation');
    view.rerender(h.component(false,'current',null));expect(screen.getByText(/Reset outcome is not yet confirmed/)).toBeTruthy();
    if(changed==='context'){h.api.context='context-b';view.rerender(h.component(false,'current',null));}
    else{h.state.project_id='other-room';h.snapshot.project_id='other-room';view.rerender(h.component());}
    expect(screen.queryByText(/Reset outcome is not yet confirmed/)).toBeNull();
    expect(h.api.command.mock.calls.filter(([kind])=>kind==='reset')).toHaveLength(1);expect(h.api.simulationRun).not.toHaveBeenCalled();view.unmount();
  });

  it('retires idle lease and route for the scene writer, then requires an explicit fresh route and acquisition',async()=>{
    const h=harness(),view=render(h.component());
    await click('View current Twin');await click('Preview SIM route');
    expect(screen.getByRole('region',{name:'Simulation route'}).getAttribute('data-plan-id')).toBe('route');
    await tick();expect(h.api.renewLease).toHaveBeenCalledExactlyOnceWith('lease-1');
    view.rerender(h.component(true));
    expect(screen.getByRole('region',{name:'Simulation route'}).getAttribute('data-plan-id')).toBe('');
    expect(screen.getByRole('button',{name:'Run simulation'})).toHaveProperty('disabled',true);
    expect(screen.getByText(/Scene tools are active.*fresh SIM route/)).toBeTruthy();
    await tick(3000);expect(h.api.renewLease).toHaveBeenCalledTimes(1);
    expect(h.api.acquireLease).toHaveBeenCalledTimes(1);expect(h.api.simulationRun).not.toHaveBeenCalled();
    view.rerender(h.component(false));await click('Run simulation');
    expect(h.api.simulationRun).not.toHaveBeenCalled();
    await click('Preview SIM route');await click('Run simulation');
    expect(h.api.acquireLease).toHaveBeenCalledTimes(2);expect(h.api.simulationRun).toHaveBeenCalledTimes(1);
    expect(h.report).not.toHaveBeenCalled();view.unmount();
  });

  it('does not let an old renewal rejection clear the newly acquired lease',async()=>{
    const h=harness(),reject=delayedRenew(h),view=render(h.component());
    await click('View current Twin');await tick();
    await click('View current Twin');expect(h.api.acquireLease).toHaveBeenCalledTimes(2);
    await act(async()=>reject());expect(h.report).not.toHaveBeenCalled();
    await tick();expect(h.api.renewLease).toHaveBeenLastCalledWith('lease-2');
    expect(h.report).not.toHaveBeenCalled();view.unmount();
  });

  it('fences an in-flight rejection after Activity hides and restores the same mounted card',async()=>{
    const h=harness(),reject=delayedRenew(h);
    const component=(hidden:boolean)=><Activity mode={hidden?'hidden':'visible'}>{h.component()}</Activity>;
    const view=render(component(false));await click('View current Twin');await tick();
    view.rerender(component(true));await tick(1500);expect(h.api.renewLease).toHaveBeenCalledTimes(1);
    view.rerender(component(false));await click('View current Twin');
    await act(async()=>reject());expect(h.report).not.toHaveBeenCalled();
    await tick();expect(h.api.renewLease).toHaveBeenLastCalledWith('lease-2');
    expect(screen.queryByText(/Control lease lost/)).toBeNull();view.unmount();
  });

  it.each(['raw-running','unknown-operation','accepted-operation','running-operation','unknown-engine'])(
    'keeps current renewal rejection visible during writer activity with %s',async reason=>{
      const h=harness(),view=render(h.component());await click('View current Twin');
      if(reason==='raw-running'){
        // No run_id/telemetry: the derived `moving` flag is false, but raw running must still prevent idle handoff.
        h.snapshot.runtime_state='running';h.snapshot.run_id=null;
      }else if(reason==='unknown-engine')h.state.engine_connected=false;
      else h.state.operations.push({...h.operation('run'),status:reason.replace('-operation','') as Operation['status']});
      h.api.renewLease.mockRejectedValueOnce(new ApiError('control_lease_invalid','Control lease is invalid or expired'));
      view.rerender(h.component(true));await tick();
      expect(h.api.renewLease).toHaveBeenCalledExactlyOnceWith('lease-1');
      expect(h.report).toHaveBeenCalledWith(expect.stringContaining('Control lease is invalid or expired'));
      expect(screen.getByText(/Control lease lost/)).toBeTruthy();expect(h.api.acquireLease).toHaveBeenCalledTimes(1);
      expect(h.api.simulationRun).not.toHaveBeenCalled();view.unmount();
    });

  it('does not retire the lease for an unknown Run delivery even when the raw engine looks idle',async()=>{
    const h=harness();h.api.simulationRun.mockRejectedValueOnce(new ApiError('delivery_unknown','Run delivery unknown'));
    h.api.simulationOutcome.mockImplementation(()=>new Promise<Operation>(()=>{}));
    const view=render(h.component());await click('View current Twin');await click('Preview SIM route');await click('Run simulation');
    expect(screen.getByRole('status').textContent).toContain('Run delivery is unconfirmed');h.report.mockClear();
    h.api.renewLease.mockRejectedValueOnce(new ApiError('control_lease_invalid','Current uncertain lease rejected'));
    view.rerender(h.component(true));await tick();
    expect(h.api.renewLease).toHaveBeenCalledWith('lease-2');
    expect(h.report).toHaveBeenCalledWith(expect.stringContaining('Current uncertain lease rejected'));
    expect(h.api.simulationRun).toHaveBeenCalledTimes(1);expect(h.api.acquireLease).toHaveBeenCalledTimes(2);
    expect(screen.getByRole('button',{name:'Run simulation'})).toHaveProperty('disabled',true);view.unmount();
  });

  it('keeps a renewal rejection visible while Reset delivery is unknown on an apparently idle engine',async()=>{
    const h=harness(),view=render(h.component());await click('View current Twin');
    h.api.command.mockRejectedValueOnce(new ApiError('delivery_unknown','Reset outcome unknown'));
    await click('Reset simulation');expect(screen.getByText(/Reset outcome is not yet confirmed/)).toBeTruthy();h.report.mockClear();
    h.api.renewLease.mockRejectedValueOnce(new ApiError('control_lease_invalid','Unconfirmed Reset lease rejected'));
    view.rerender(h.component(true));await tick();
    expect(h.api.renewLease).toHaveBeenCalledWith('lease-2');
    expect(h.report).toHaveBeenCalledWith(expect.stringContaining('Unconfirmed Reset lease rejected'));
    expect(h.api.acquireLease).toHaveBeenCalledTimes(2);expect(h.api.simulationRun).not.toHaveBeenCalled();view.unmount();
  });

  it('does not hand off control while its local Build POST is still pending despite an older idle snapshot',async()=>{
    const h=harness(),view=render(h.component());await click('View current Twin');
    let rejectBuild!:(reason:Error)=>void;
    h.api.command.mockImplementationOnce(()=>new Promise((_resolve,reject)=>{rejectBuild=reject;}));
    await click('View current Twin');view.rerender(h.component(true));
    h.api.renewLease.mockRejectedValueOnce(new ApiError('control_lease_invalid','Pending Build lease rejected'));
    await tick();expect(h.api.renewLease).toHaveBeenCalledWith('lease-2');
    expect(h.report).toHaveBeenCalledWith(expect.stringContaining('Pending Build lease rejected'));
    await act(async()=>rejectBuild(new ApiError('delivery_unknown','Build response unknown')));
    expect(h.api.acquireLease).toHaveBeenCalledTimes(2);expect(h.api.simulationRun).not.toHaveBeenCalled();view.unmount();
  });

  it('does not hand off an unconfirmed Stop merely because the next snapshot already looks built',async()=>{
    const h=harness(),view=render(h.component());await click('View current Twin');
    h.snapshot.runtime_state='running';h.snapshot.run_id='run';h.snapshot.telemetry_available=true;h.snapshot.position_m=[0,0,0];
    view.rerender(h.component());let resolveStop!:(op:Operation)=>void;
    h.api.command.mockImplementationOnce(()=>new Promise(resolve=>{resolveStop=resolve;}));
    await click('Stop simulation');h.snapshot.runtime_state='built';view.rerender(h.component(true));
    h.api.renewLease.mockRejectedValueOnce(new ApiError('control_lease_invalid','Pending Stop lease rejected'));
    await tick();expect(h.api.renewLease).toHaveBeenCalledWith('lease-1');
    expect(h.report).toHaveBeenCalledWith(expect.stringContaining('Pending Stop lease rejected'));
    const op=h.operation('pause');h.state.operations.push(op);await act(async()=>resolveStop(op));
    expect(h.api.acquireLease).toHaveBeenCalledTimes(1);expect(h.api.simulationRun).not.toHaveBeenCalled();view.unmount();
  });

  it.each(['engine','epoch','project','revision'])('does not treat a mismatched idle snapshot %s as permission to silence renewal rejection',async mismatch=>{
    const h=harness(),view=render(h.component());await click('View current Twin');
    if(mismatch==='engine')h.snapshot.engine_session_id='other-engine';
    if(mismatch==='epoch')h.snapshot.stage_epoch='other-epoch';
    if(mismatch==='project')h.snapshot.project_id='other-room';
    if(mismatch==='revision')h.snapshot.applied_revision='other-revision';
    h.api.renewLease.mockRejectedValueOnce(new ApiError('control_lease_invalid','Unconfirmed binding lease rejected'));
    view.rerender(h.component(true));await tick();
    expect(h.api.renewLease).toHaveBeenCalledWith('lease-1');
    expect(h.report).toHaveBeenCalledWith(expect.stringContaining('Unconfirmed binding lease rejected'));
    expect(h.api.acquireLease).toHaveBeenCalledTimes(1);view.unmount();
  });

  it.each(['revision','context','project'])('retires the old renewal across %s change and never sends its old lease again',async reason=>{
    const h=harness(),reject=delayedRenew(h),view=render(h.component());
    await click('View current Twin');await tick();
    let revision='current';
    if(reason==='revision'){revision='next';h.snapshot.applied_revision=revision;}
    if(reason==='context')h.api.context='context-b';
    if(reason==='project'){h.state.project_id='other';h.snapshot.project_id='other';}
    view.rerender(h.component(false,revision));
    await act(async()=>reject());await tick(1500);
    expect(h.api.renewLease).toHaveBeenCalledTimes(1);expect(h.report).not.toHaveBeenCalled();
    expect(screen.getByRole('button',{name:'Run simulation'})).toHaveProperty('disabled',true);
    await click('View current Twin');await tick();
    expect(h.api.renewLease).toHaveBeenLastCalledWith('lease-2');expect(h.api.acquireLease).toHaveBeenCalledTimes(2);
    expect(h.report).not.toHaveBeenCalled();view.unmount();
  });
});
