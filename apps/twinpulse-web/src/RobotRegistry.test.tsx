// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {act,cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {RobotRegistry,type RobotRegistryState} from './RobotRegistry';
import type {TwinPulseApi} from './api';
afterEach(()=>{cleanup();vi.useRealTimers();});
const state:RobotRegistryState={schema_version:'robot-registry-1.0',revision:3,active_id:null,robots:[],
  adapters:[{id:'unreviewed',label:'Unreviewed hardware',supported:false},{id:'turtlebot3_burger_v1',label:'TurtleBot3 Burger',supported:true}],
  discovery:{state:'completed',freshness:'recent',remaining_seconds:30,candidates:[]}};
const rawExport=(job_id:string,json_text:string)=>({schema_version:'robot-observation-export-1.0',job_id,json_text,
  file_sha256:'a'.repeat(64),export_sha256:'b'.repeat(64)});
function setup(value=state){const api={robotRegistry:vi.fn().mockResolvedValue(value),updateRobotRegistry:vi.fn().mockResolvedValue(value)};
  const result=render(<RobotRegistry runtimeReady={true} api={api as unknown as TwinPulseApi} close={vi.fn()}/>);return {api,...result};}
describe('robot registry supplementary UI contracts',()=>{
  it('gates startup mutations on launcher readiness without replay while retaining saved reads',async()=>{
    const value={...state,active_id:'r',robots:[{id:'r',label:'Burger',adapter_id:'turtlebot3_burger_v1',endpoint:{host:'robot.local',user:'tp',port:22,ros_domain_id:86},connection_state:'unverified' as const,motion_authorized:false as const}]};
    const api={robotRegistry:vi.fn().mockResolvedValue(value),updateRobotRegistry:vi.fn().mockResolvedValue(value)};
    const panel=render(<RobotRegistry api={api as unknown as TwinPulseApi} close={vi.fn()} runtimeReady={false}/>);
    const prepare=await screen.findByRole('button',{name:'Check PC preparation'});
    expect(prepare).toHaveProperty('disabled',true);expect(screen.getByRole('button',{name:'Check connection (read-only)'})).toHaveProperty('disabled',true);
    expect(screen.getByRole('button',{name:'Search for robots'})).toHaveProperty('disabled',true);expect(screen.getByText(/Waiting for launcher readiness/)).toBeTruthy();
    fireEvent.click(prepare);expect(api.updateRobotRegistry).not.toHaveBeenCalled();
    panel.rerender(<RobotRegistry api={api as unknown as TwinPulseApi} close={vi.fn()} runtimeReady={true}/>);
    expect(prepare).toHaveProperty('disabled',false);expect(api.updateRobotRegistry).not.toHaveBeenCalled();
    fireEvent.click(prepare);await waitFor(()=>expect(api.updateRobotRegistry).toHaveBeenCalledExactlyOnceWith({action:'prepare',expected_revision:3}));
    panel.rerender(<RobotRegistry api={api as unknown as TwinPulseApi} close={vi.fn()} runtimeReady={false}/>);
    expect(prepare).toHaveProperty('disabled',true);expect(api.updateRobotRegistry).toHaveBeenCalledTimes(1);
  });
  it.each([false,undefined])('does not read an unsaved running connection log when logs_saved is %s',async logs_saved=>{
    const api={robotRegistry:vi.fn().mockResolvedValue({...state,connection:{state:'running',job_id:'collecting-job',logs_saved}}),
      updateRobotRegistry:vi.fn(),robotObservation:vi.fn()};
    render(<RobotRegistry runtimeReady={true} api={api as unknown as TwinPulseApi} close={vi.fn()}/>);
    const button=await screen.findByRole('button',{name:'View connection log'});expect(button).toHaveProperty('disabled',true);fireEvent.click(button);
    expect(screen.getByText(/Waiting for local observation log storage confirmation/)).toBeTruthy();
    expect(api.robotObservation).not.toHaveBeenCalled();expect(api.updateRobotRegistry).not.toHaveBeenCalled();
  });
  it('enables explicit log viewing after storage is confirmed even when the connection check failed',async()=>{
    const value={...state,connection:{state:'running',job_id:'collecting-job',logs_saved:false}};
    const api={robotRegistry:vi.fn().mockResolvedValue(value),updateRobotRegistry:vi.fn(),robotObservation:vi.fn().mockResolvedValue({job_id:'collecting-job',result_code:'SSH_AUTH_FAILED'})};
    render(<RobotRegistry runtimeReady={true} api={api as unknown as TwinPulseApi} close={vi.fn()}/>);
    const button=await screen.findByRole('button',{name:'View connection log'});expect(button).toHaveProperty('disabled',true);
    api.robotRegistry.mockResolvedValue({...value,connection:{state:'failed',job_id:'collecting-job',logs_saved:true}});
    await waitFor(()=>expect(button).toHaveProperty('disabled',false),{timeout:2500});
    expect(api.robotObservation).not.toHaveBeenCalled();expect(screen.queryByText(/Waiting for local observation log storage confirmation/)).toBeNull();
    fireEvent.click(button);await screen.findByRole('button',{name:'Download observation JSON'});
    expect(api.robotObservation).toHaveBeenCalledExactlyOnceWith('collecting-job');expect(api.updateRobotRegistry).not.toHaveBeenCalled();
    expect(screen.getByText(/Connection check: failed/)).toBeTruthy();
  });
  it('reads and downloads saved observations after reopening without a current connection job',async()=>{
    const history={job_id:'saved-job',execution_id:'saved-execution',result_code:'ROBOT_OBSERVATION_COMPLETE',finished_at_utc:'2026-10-17T01:00:00Z',scan_count:3};
    const record={job_id:history.job_id,execution_id:history.execution_id,obstacle_observation:{schema_version:'obstacle-observation-1.0',scans:[]}};
    const value:RobotRegistryState={...state,active_id:'r1',observation_history:[history]};
    const original=JSON.stringify(record,null,2).replace('"scans": []','"scans": [], "exact_number": 0.0').replace(/\n/g,'\r\n');
    const api={robotRegistry:vi.fn().mockResolvedValue(value),updateRobotRegistry:vi.fn(),robotObservation:vi.fn().mockResolvedValue(record),
      robotObservationExport:vi.fn().mockResolvedValue(rawExport(history.job_id,original))};
    render(<RobotRegistry runtimeReady={true} api={api as unknown as TwinPulseApi} close={vi.fn()}/>);
    fireEvent.click(await screen.findByText('Saved connection observations'));
    const saved=screen.getByRole('article',{name:'Saved observation saved-job'});
    expect(within(saved).getByText('Execution: saved-execution')).toBeTruthy();
    expect(within(saved).getByText(/ROBOT_OBSERVATION_COMPLETE · 3 scan snapshots/)).toBeTruthy();
    expect(screen.queryByRole('button',{name:'View connection log'})).toBeNull();expect(api.robotObservation).not.toHaveBeenCalled();
    fireEvent.click(within(saved).getByRole('button',{name:'View saved observation log'}));
    await screen.findByRole('button',{name:'Download observation JSON'});
    expect(api.robotObservation).toHaveBeenCalledExactlyOnceWith('saved-job');
    expect(screen.getByText(/Historical local records.*not a current connection/)).toBeTruthy();
    expect(screen.getByText('Saved observation: saved-job · Not a current connection guarantee.')).toBeTruthy();
    const click=vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{});
    const create=vi.spyOn(URL,'createObjectURL');fireEvent.click(screen.getByRole('button',{name:'Download observation JSON'}));
    await waitFor(()=>expect(click).toHaveBeenCalledOnce());
    const exported=await new Promise<string>((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result));reader.onerror=reject;reader.readAsText(create.mock.calls.at(-1)![0] as Blob);});
    expect(exported).toBe(original);expect(exported).toContain('0.0');expect(api.robotObservationExport).toHaveBeenCalledExactlyOnceWith('saved-job');
    expect(api.updateRobotRegistry).not.toHaveBeenCalled();
  });
  it('keeps a selected historical log separate when the current connection job changes',async()=>{
    const history={job_id:'saved-job',execution_id:'saved-execution',result_code:'FAILED',finished_at_utc:'2026-10-17T01:00:00Z',scan_count:0};
    const value={...state,connection:{job_id:'current-job'},observation_history:[history]};
    const api={robotRegistry:vi.fn().mockResolvedValue(value),updateRobotRegistry:vi.fn(),robotObservation:vi.fn().mockResolvedValue({job_id:'saved-job',snapshot:'historical'})};
    render(<RobotRegistry runtimeReady={true} api={api as unknown as TwinPulseApi} close={vi.fn()}/>);
    fireEvent.click(await screen.findByText('Saved connection observations'));
    fireEvent.click(screen.getByRole('button',{name:'View saved observation log'}));await screen.findByRole('button',{name:'Download observation JSON'});
    api.robotRegistry.mockResolvedValue({...value,connection:{job_id:'next-current-job'}});
    await screen.findByText('Observation next-current-job',{}, {timeout:2500});
    expect(screen.getByRole('button',{name:'Download observation JSON'})).toBeTruthy();
    expect(screen.getByText('Saved observation: saved-job · Not a current connection guarantee.')).toBeTruthy();
    expect(api.robotObservation).toHaveBeenCalledExactlyOnceWith('saved-job');expect(api.updateRobotRegistry).not.toHaveBeenCalled();
  });
  it('discards a pending saved observation after the selected robot changes',async()=>{
    let finish!:(value:Record<string,unknown>)=>void;
    const history={job_id:'saved-job',execution_id:'saved-execution',result_code:'COMPLETE',finished_at_utc:'2026-10-17T01:00:00Z',scan_count:1};
    const value={...state,active_id:'r1',observation_history:[history]};
    const api={robotRegistry:vi.fn().mockResolvedValue(value),updateRobotRegistry:vi.fn(),robotObservation:vi.fn(()=>new Promise<Record<string,unknown>>(resolve=>{finish=resolve;}))};
    render(<RobotRegistry runtimeReady={true} api={api as unknown as TwinPulseApi} close={vi.fn()}/>);
    fireEvent.click(await screen.findByText('Saved connection observations'));fireEvent.click(screen.getByRole('button',{name:'View saved observation log'}));
    api.robotRegistry.mockResolvedValue({...value,active_id:'r2',observation_history:[]});
    await screen.findByText('No saved connection observations listed for this robot.',{}, {timeout:2500});
    await act(async()=>finish({job_id:'saved-job',snapshot:'previous-robot-log'}));
    expect(screen.queryByText(/previous-robot-log/)).toBeNull();expect(screen.queryByRole('button',{name:'Download observation JSON'})).toBeNull();
    expect(api.updateRobotRegistry).not.toHaveBeenCalled();
  });
  it('reads a connection log only on click and downloads the returned sensor wrapper without reconnecting',async()=>{
    const record={job_id:'job-1',execution_id:'e'.repeat(32),obstacle_observation:{schema_version:'obstacle-observation-1.0',provenance:'ROBOT_READ_ONLY',scans:[]}};
    const value:RobotRegistryState={...state,connection:{state:'completed',job_id:'job-1',execution_id:'e'.repeat(32),logs_saved:true,scan_count:2,artifact_id:'observation-1'}};
    const api={context:'registry-a',robotRegistry:vi.fn().mockResolvedValue(value),updateRobotRegistry:vi.fn(),robotObservation:vi.fn().mockResolvedValue(record),
      robotObservationExport:vi.fn().mockResolvedValue(rawExport('job-1',JSON.stringify(record,null,2)))};
    render(<RobotRegistry runtimeReady={true} api={api as unknown as TwinPulseApi} close={vi.fn()}/>);
    const button=await screen.findByRole('button',{name:'View connection log'});expect(api.robotObservation).not.toHaveBeenCalled();
    fireEvent.click(button);expect(await screen.findByText(/Connection observation log · historical/)).toBeTruthy();
    expect(api.robotObservation).toHaveBeenCalledExactlyOnceWith('job-1');expect(screen.getByText(/2 scan snapshots/)).toBeTruthy();
    const click=vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{});
    const create=vi.spyOn(URL,'createObjectURL');fireEvent.click(screen.getByRole('button',{name:'Download observation JSON'}));
    await waitFor(()=>expect(create).toHaveBeenCalledWith(expect.any(Blob)));expect(click).toHaveBeenCalledOnce();
    const exported=await new Promise<string>((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result));reader.onerror=reject;reader.readAsText(create.mock.calls.at(-1)![0] as Blob);});
    expect(JSON.parse(exported)).toEqual(record);
    expect(api.updateRobotRegistry).not.toHaveBeenCalled();expect(screen.getByText(/can be created without a scan/)).toBeTruthy();
  });
  it('does not display a late connection log after owner context changes or panel unmounts',async()=>{
    let finish!:(value:Record<string,unknown>)=>void;
    const api={context:'registry-a',robotRegistry:vi.fn().mockResolvedValue({...state,connection:{state:'completed',job_id:'job-1',logs_saved:true}}),updateRobotRegistry:vi.fn(),
      robotObservation:vi.fn(()=>new Promise<Record<string,unknown>>(resolve=>{finish=resolve;}))};
    const panel=render(<RobotRegistry runtimeReady={true} api={api as unknown as TwinPulseApi} close={vi.fn()}/>);
    fireEvent.click(await screen.findByRole('button',{name:'View connection log'}));api.context='registry-b';
    panel.rerender(<RobotRegistry runtimeReady={true} api={api as unknown as TwinPulseApi} close={vi.fn()}/>);
    await act(async()=>finish({job_id:'job-1',old_owner_evidence:'must not show'}));
    expect(screen.queryByText(/must not show/)).toBeNull();expect(screen.queryByRole('button',{name:'Download observation JSON'})).toBeNull();
    fireEvent.click(screen.getByRole('button',{name:'View connection log'}));panel.unmount();await act(async()=>finish({job_id:'job-1'}));
    expect(api.updateRobotRegistry).not.toHaveBeenCalled();
  });
  it('does not download an original export arriving after owner context changes',async()=>{
    let finish!:(value:ReturnType<typeof rawExport>)=>void;
    const value={...state,connection:{state:'completed',job_id:'job-1',logs_saved:true}};
    const api={context:'registry-a',robotRegistry:vi.fn().mockResolvedValue(value),updateRobotRegistry:vi.fn(),
      robotObservation:vi.fn().mockResolvedValue({job_id:'job-1'}),
      robotObservationExport:vi.fn(()=>new Promise<ReturnType<typeof rawExport>>(resolve=>{finish=resolve;}))};
    const panel=render(<RobotRegistry runtimeReady={true} api={api as unknown as TwinPulseApi} close={vi.fn()}/>);
    fireEvent.click(await screen.findByRole('button',{name:'View connection log'}));
    const button=await screen.findByRole('button',{name:'Download observation JSON'});
    const create=vi.spyOn(URL,'createObjectURL');create.mockClear();fireEvent.click(button);
    expect(api.robotObservationExport).toHaveBeenCalledExactlyOnceWith('job-1');
    api.context='registry-b';panel.rerender(<RobotRegistry runtimeReady={true} api={api as unknown as TwinPulseApi} close={vi.fn()}/>);
    await act(async()=>finish(rawExport('job-1','{"job_id":"job-1","angle":0.0}')));
    expect(create).not.toHaveBeenCalled();expect(api.updateRobotRegistry).not.toHaveBeenCalled();
  });
  it('invalidates an open log when polling reports a different connection job',async()=>{
    const api={context:'registry-a',robotRegistry:vi.fn().mockResolvedValue({...state,connection:{state:'completed',job_id:'job-1',logs_saved:true}}),updateRobotRegistry:vi.fn(),
      robotObservation:vi.fn().mockResolvedValue({job_id:'job-1',snapshot:'prior-job'})};
    render(<RobotRegistry runtimeReady={true} api={api as unknown as TwinPulseApi} close={vi.fn()}/>);
    fireEvent.click(await screen.findByRole('button',{name:'View connection log'}));await screen.findByRole('button',{name:'Download observation JSON'});
    api.robotRegistry.mockResolvedValue({...state,connection:{job_id:'job-2'}});
    await screen.findByText('Observation job-2',{}, {timeout:2500});
    expect(screen.queryByRole('button',{name:'Download observation JSON'})).toBeNull();expect(api.robotObservation).toHaveBeenCalledTimes(1);
  });
  it('reports a read failure without starting another hardware connection check',async()=>{
    const api={robotRegistry:vi.fn().mockResolvedValue({...state,connection:{state:'completed',job_id:'job-1',logs_saved:true}}),updateRobotRegistry:vi.fn(),
      robotObservation:vi.fn().mockRejectedValue(new Error('Log unavailable'))};
    render(<RobotRegistry runtimeReady={true} api={api as unknown as TwinPulseApi} close={vi.fn()}/>);
    fireEvent.click(await screen.findByRole('button',{name:'View connection log'}));
    expect(await screen.findByRole('alert')).toHaveProperty('textContent',expect.stringContaining('No connection check was repeated'));
    expect(api.updateRobotRegistry).not.toHaveBeenCalled();expect(api.robotObservation).toHaveBeenCalledTimes(1);
  });
  it('rejects a different job log instead of labeling it as the selected connection result',async()=>{
    const api={robotRegistry:vi.fn().mockResolvedValue({...state,connection:{state:'completed',job_id:'job-1',logs_saved:true}}),updateRobotRegistry:vi.fn(),
      robotObservation:vi.fn().mockResolvedValue({job_id:'job-2',snapshot:'wrong job'})};
    render(<RobotRegistry runtimeReady={true} api={api as unknown as TwinPulseApi} close={vi.fn()}/>);
    fireEvent.click(await screen.findByRole('button',{name:'View connection log'}));await screen.findByRole('alert');
    expect(screen.queryByRole('button',{name:'Download observation JSON'})).toBeNull();expect(screen.queryByText(/wrong job/)).toBeNull();
    expect(api.updateRobotRegistry).not.toHaveBeenCalled();
  });
  it('shows local preparation and disables unavailable live diagnostics in the SIM package',async()=>{
    const value:RobotRegistryState={...state,active_id:'r1',robots:[{id:'r1',label:'Burger',adapter_id:'turtlebot3_burger_v1',endpoint:{host:'robot.local',user:'twinpulse',port:22,ros_domain_id:86},connection_state:'unverified',motion_authorized:false}],
      capabilities:{registration:true,discovery:true,local_preparation:true,read_only_connection:false,physical_control:false,unavailable_reason:'SIM_ONLY_RELEASE'},
      preparation:{schema_version:'robot-local-preparation-1.0',state:'not_checked',pc_ready:false,connection_verified:false,motion_authorized:false,checks:[]}};
    const {api}=setup(value);await screen.findByText('Not checked for this robot');
    expect(screen.getByRole('button',{name:'Check connection (read-only)'})).toHaveProperty('disabled',true);
    fireEvent.click(screen.getByRole('button',{name:'Check PC preparation'}));
    await waitFor(()=>expect(api.updateRobotRegistry).toHaveBeenCalledWith({action:'prepare',expected_revision:3}));
    expect(screen.getByText(/This SIM alpha supports registration/)).toBeTruthy();
  });
  it('does not infer connection from empty discovery or register without explicit input',async()=>{
    const {api}=setup();await screen.findByText(/No network advertisements observed/);
    expect(screen.getByText(/No robots registered/)).toBeTruthy();expect(api.updateRobotRegistry).not.toHaveBeenCalled();
    expect(screen.queryByRole('button',{name:'Check connection (read-only)'})).toBeNull();
  });
  it('copies Bluetooth candidates without guessing SSH or motor protocol and registers a reviewed address once',async()=>{
    const candidate={candidate_id:'bt-1',transport:'bluetooth' as const,address:'00:11:22:33:44:55',label:'Unknown device',identity_verified:false as const};
    const {api}=setup({...state,discovery:{state:'completed',candidates:[],known_devices:[candidate]}});
    await screen.findByRole('button',{name:'Use in manual registration'});fireEvent.click(screen.getByRole('button',{name:'Use in manual registration'}));
    expect(screen.getByLabelText('Robot host')).toHaveProperty('value','');expect(api.updateRobotRegistry).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('Robot host'),{target:{value:'robot.local'}});fireEvent.change(screen.getByLabelText('Robot adapter'),{target:{value:'turtlebot3_burger_v1'}});
    let resolve!:(next:RobotRegistryState)=>void;api.updateRobotRegistry.mockImplementation(()=>new Promise(done=>{resolve=done;}));
    fireEvent.click(screen.getByRole('button',{name:'Register robot'}));fireEvent.click(screen.getByRole('button',{name:'Register robot'}));
    expect(api.updateRobotRegistry).toHaveBeenCalledOnce();expect(api.updateRobotRegistry).toHaveBeenCalledWith({action:'register',label:'Unknown device',adapter_id:'turtlebot3_burger_v1',endpoint:{host:'robot.local',user:'twinpulse',port:22,ros_domain_id:86},expected_revision:3});
    await act(async()=>resolve(state));expect(screen.queryByText(/live connection guarantee/)).toBeNull();
  });
  it('polls only while mounted and sends the selected revision for an explicit connection check',async()=>{
    const value:RobotRegistryState={...state,active_id:'r1',robots:[{id:'r1',label:'Burger',adapter_id:'turtlebot3_burger_v1',endpoint:{host:'robot.local',user:'ubuntu',port:22,ros_domain_id:0},connection_state:'unverified',motion_authorized:false}]};
    const {api,unmount}=setup(value);await screen.findByText(/Connection unverified/);
    fireEvent.click(screen.getByRole('button',{name:'Check connection (read-only)'}));
    await waitFor(()=>expect(api.updateRobotRegistry).toHaveBeenCalledWith({action:'connect',expected_revision:3}));
    vi.useFakeTimers();unmount();await act(async()=>{await vi.advanceTimersByTimeAsync(4000);});expect(api.robotRegistry).toHaveBeenCalledOnce();
  });
  it('separates cached devices from search results without implying power or connection',async()=>{
    setup({...state,discovery:{...state.discovery,known_devices:[{candidate_id:'cached',transport:'bluetooth',address:'00:11:22:33:44:55',label:'AirPods memory',identity_verified:false}]}});
    const discovery=await screen.findByRole('region',{name:'Robot discovery'});
    expect(within(discovery).queryByText('AirPods memory')).toBeNull();
    expect(screen.getByText('AirPods memory')).toBeTruthy();expect(screen.getByText(/Current presence unknown/)).toBeTruthy();
    expect(screen.queryByRole('button',{name:'Review and register'})).toBeNull();
  });
  it('shows the saved name for address matches but never authenticates or chooses automatically',async()=>{
    const {api}=setup({...state,discovery:{...state.discovery,candidates:[{candidate_id:'net',transport:'network',address:'192.168.1.20',label:'TurtleBot3',identity_verified:false,
      remaining_seconds:30,registered_matches:[{id:'saved1',label:'My Burger'},{id:'saved2',label:'Shared endpoint'}]}]}});
    await screen.findByText('My Burger / Shared endpoint');expect(screen.getByText(/address and port only/)).toBeTruthy();
    expect(screen.queryByRole('button',{name:'Select saved robot'})).toBeNull();expect(api.updateRobotRegistry).not.toHaveBeenCalled();
  });
  it('expires a response even when refreshing fails and does not offer stale registration',async()=>{
    vi.useFakeTimers({toFake:['setTimeout','clearTimeout','setInterval','clearInterval','performance']});
    const value:RobotRegistryState={...state,discovery:{...state.discovery,candidates:[{candidate_id:'net',transport:'network',address:'robot.local',label:'TurtleBot3',identity_verified:false,remaining_seconds:1}]}};
    const {api}=setup(value);await act(async()=>{});expect(screen.getByRole('button',{name:'Review and register'})).toBeTruthy();
    api.robotRegistry.mockRejectedValue(new Error('supplementary refresh fault'));
    await act(async()=>{await vi.advanceTimersByTimeAsync(2000);});
    expect(screen.queryByRole('button',{name:'Review and register'})).toBeNull();expect(api.updateRobotRegistry).not.toHaveBeenCalled();
  });
  it('guards a click after suspension before an expiry render occurs',async()=>{
    const {api}=setup({...state,discovery:{...state.discovery,candidates:[{candidate_id:'net',transport:'network',address:'robot.local',label:'TurtleBot3',identity_verified:false,remaining_seconds:1}]}});
    const button=await screen.findByRole('button',{name:'Review and register'});
    const clock=vi.spyOn(performance,'now').mockReturnValue(performance.now()+2000);
    fireEvent.click(button);expect(screen.getByText(/Search result expired or could not be refreshed/)).toBeTruthy();
    expect(screen.getByLabelText('Robot label')).toHaveProperty('value','');expect(api.updateRobotRegistry).not.toHaveBeenCalled();clock.mockRestore();
  });
  it('does not revive a response which expired in transit before the GET resolved',async()=>{
    let resolve!:(value:RobotRegistryState)=>void;
    const clock=vi.spyOn(performance,'now').mockReturnValue(1000);
    const api={robotRegistry:vi.fn(()=>new Promise<RobotRegistryState>(done=>{resolve=done;})),updateRobotRegistry:vi.fn()};
    render(<RobotRegistry runtimeReady={true} api={api as unknown as TwinPulseApi} close={vi.fn()}/>);
    clock.mockReturnValue(3000);
    await act(async()=>resolve({...state,discovery:{...state.discovery,candidates:[{candidate_id:'delayed',transport:'network',address:'robot.local',label:'Delayed robot',identity_verified:false,remaining_seconds:1}]}}));
    expect(screen.queryByRole('button',{name:'Review and register'})).toBeNull();
    expect(screen.getByText(/Search results expired or unavailable/)).toBeTruthy();clock.mockRestore();
  });
});
