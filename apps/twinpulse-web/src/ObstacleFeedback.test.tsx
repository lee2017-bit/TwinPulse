// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {Activity,Suspense,startTransition,useState} from 'react';
import {describe,expect,it,vi} from 'vitest';
import {ApiError,type TwinPulseApi} from './api';
import {ObstacleFeedback} from './ObstacleFeedback';
import type {ObstacleCorrectionPreview,ObstacleFeedbackState,ObstacleObservation} from './obstacle-types';
import type {SceneEditPreview,SceneEditTransaction} from './types';

const revision='a'.repeat(64),sha='b'.repeat(64);
const observation:ObstacleObservation={id:'scan-1',sha256:'c'.repeat(64),provenance:'IMPORTED_SENSOR',received_at_utc:'2026-10-17T09:00:00Z',execution_id:'e'.repeat(32),
  scan_count:2,scan_height_m:.2,sensor_pose_m:[0,0,0],points:[[1,0],[1,.1]],cells:[[1,0,'occupied'],[0,0,'free'],[2,0,'unknown']],
  occupied_count:1,free_count:1,unknown_count:1,association:'unassigned'};
const feedback:ObstacleFeedbackState={schema_version:'obstacle-feedback-1.0',context:{project_id:'room-a',current_scene_revision:revision,current_state_sha256:sha},
  observations:[observation],targets:[{id:'desk-a',label:'Desk',center_m:[1,0,.4]},{id:'chair-a',label:'Chair',center_m:[0,1,.2]}],physical_authority:false};
const proposal:ObstacleCorrectionPreview={status:'preview',reason:'TRANSLATION_CANDIDATE',execution_id:'d'.repeat(32),observation_id:observation.id,
  observation_sha256:observation.sha256,translation_xy_m:[.1,0],fit:{status:'candidate',score:.8},operation:{operation_id:'obstacle-operation'},
  preview_digest:'f'.repeat(64),sensor_binding:{observation_id:observation.id},apply_version:'scene-edit-apply-2.0'};
const committed:SceneEditTransaction={operation_id:'obstacle-operation',state:'COMMITTED',engine_acknowledged:true,durable_committed:true,current_frame:false,
  error:null,command_id:'build-command',execution_id:'1'.repeat(32),result_revision:'2'.repeat(64)};
// SceneChangeHistory._dependency_preview response: no apply_version field.
const undoPreview:SceneEditPreview={parent_revision:revision,parent_state_sha256:sha,result_state_sha256:'7'.repeat(64),
  operation:{operation_id:'undo-operation',mode:'undo',parent_revision:revision,target_call_id:null,tool_call:null,
    expected_non_target_digests:{},result_revision:'6'.repeat(64),parent_state_sha256:sha,result_state_sha256:'7'.repeat(64)},
  preview_digest:'5'.repeat(64),source_revision:revision,result_revision:'6'.repeat(64),
  affected_before:{},affected_after:{},preserved_object_count:1,inventory_changes:[],review_required:true,physical_validation:'NOT_RUN'};
function harness(value=feedback){return {context:'context-a',obstacleFeedbackState:vi.fn().mockResolvedValue(value),
  importObstacleObservation:vi.fn().mockResolvedValue(value),previewObstacleCorrection:vi.fn().mockResolvedValue(proposal),
  applyObstacleCorrection:vi.fn().mockResolvedValue(committed),sceneEditTransaction:vi.fn().mockResolvedValue(null),
  previewSceneEdit:vi.fn(),startSceneEditTransaction:vi.fn(),simulationRun:vi.fn(),conversationAction:vi.fn()};}
function show(api:ReturnType<typeof harness>,props:{revision?:string;stateSha?:string|null;enabled?:boolean}={}){
  return render(<ObstacleFeedback api={api as unknown as TwinPulseApi} revision={props.revision??revision} stateSha={props.stateSha===undefined?sha:props.stateSha} enabled={props.enabled??true}/>);
}
async function choose(){await screen.findByRole('option',{name:'Desk · desk-a'});fireEvent.change(screen.getByRole('combobox',{name:'Correction target'}),{target:{value:'desk-a'}});}
async function prepare(){await choose();fireEvent.click(screen.getByRole('button',{name:'Preview obstacle correction'}));await screen.findByRole('region',{name:'Obstacle correction proposal'});}
function jsonFile(value:unknown){const text=typeof value==='string'?value:JSON.stringify(value);const file=new File([text],'scan.json',{type:'application/json'});
  Object.defineProperty(file,'text',{configurable:true,value:async()=>text});return file;}
function importInputs(file:File){fireEvent.change(screen.getByLabelText('Sensor observation JSON'),{target:{files:[file]}});
  for(const [label,value] of [['X','0'],['Y','1'],['yaw','.5']])fireEvent.change(screen.getByLabelText(`Estimated sensor ${label}`),{target:{value}});
  fireEvent.change(screen.getByLabelText('Estimated scan height'),{target:{value:'.2'}});}

describe('supplementary obstacle observation feedback',()=>{
  it('retains a sealed proposal as a locked view through stale transport and requires an explicit Apply after recovery',async()=>{
    const api=harness(),view=show(api);await prepare();
    const proposalPanel=screen.getByRole('region',{name:'Obstacle correction proposal'});
    view.rerender(<ObstacleFeedback api={api as unknown as TwinPulseApi} revision={revision} stateSha={sha} enabled fresh={false}/>);
    expect(screen.getByRole('region',{name:'Obstacle correction proposal'})).toBe(proposalPanel);
    const apply=screen.getByRole('button',{name:'Apply reviewed obstacle correction'});expect(apply).toHaveProperty('disabled',true);fireEvent.click(apply);
    expect(screen.getByRole('button',{name:'Preview Undo last scene edit'})).toHaveProperty('disabled',true);
    expect(screen.getByRole('button',{name:'Import obstacle observation · local only'}).closest('fieldset')).toHaveProperty('disabled',true);
    view.rerender(<ObstacleFeedback api={api as unknown as TwinPulseApi} revision={revision} stateSha={sha} enabled fresh/>);
    expect(apply).toHaveProperty('disabled',false);expect(api.obstacleFeedbackState).toHaveBeenCalledOnce();expect(api.previewObstacleCorrection).toHaveBeenCalledOnce();
    expect(api.applyObstacleCorrection).not.toHaveBeenCalled();fireEvent.click(apply);await screen.findByText('Engine ACK received · disk COMMITTED');
    expect(api.applyObstacleCorrection).toHaveBeenCalledExactlyOnceWith(proposal);view.unmount();
  });
  it.each(['correction','Undo'])('keeps an in-flight %s preview response as a locked view when transport becomes stale',async kind=>{
    const api=harness();let finish!:(value:never)=>void;
    (kind==='correction'?api.previewObstacleCorrection:api.previewSceneEdit).mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
    const view=show(api);await choose();fireEvent.click(screen.getByRole('button',{name:kind==='correction'?'Preview obstacle correction':'Preview Undo last scene edit'}));
    view.rerender(<ObstacleFeedback api={api as unknown as TwinPulseApi} revision={revision} stateSha={sha} enabled fresh={false}/>);
    await act(async()=>finish((kind==='correction'?proposal:undoPreview) as never));
    const apply=screen.getByRole('button',{name:kind==='correction'?'Apply reviewed obstacle correction':'Apply reviewed Undo'});expect(apply).toHaveProperty('disabled',true);
    view.rerender(<ObstacleFeedback api={api as unknown as TwinPulseApi} revision={revision} stateSha={sha} enabled fresh/>);
    expect(apply).toHaveProperty('disabled',false);expect(api.applyObstacleCorrection).not.toHaveBeenCalled();expect(api.startSceneEditTransaction).not.toHaveBeenCalled();
    expect(api.obstacleFeedbackState).toHaveBeenCalledOnce();
  });
  it('rechecks current admission after an asynchronous file read before sending its import POST',async()=>{
    const api=harness(),view=show(api);await choose();const file=jsonFile('{}');let finish!:(text:string)=>void;
    Object.defineProperty(file,'text',{configurable:true,value:()=>new Promise<string>(resolve=>{finish=resolve;})});
    importInputs(file);fireEvent.click(screen.getByRole('button',{name:'Import obstacle observation · local only'}));
    view.rerender(<ObstacleFeedback api={api as unknown as TwinPulseApi} revision={revision} stateSha={sha} enabled fresh={false}/>);
    await act(async()=>finish('{}'));expect(api.importObstacleObservation).not.toHaveBeenCalled();await screen.findByText(/No import request was sent; wait for a fresh workflow/);
    view.rerender(<ObstacleFeedback api={api as unknown as TwinPulseApi} revision={revision} stateSha={sha} enabled fresh/>);
    expect(api.importObstacleObservation).not.toHaveBeenCalled();
  });
  it('does not clear or resubmit an unknown Apply when transport becomes stale and recovers',async()=>{
    const api=harness();api.applyObstacleCorrection.mockRejectedValue(new ApiError('delivery_unknown','Unconfirmed'));
    const view=show(api);await prepare();fireEvent.click(screen.getByRole('button',{name:'Apply reviewed obstacle correction'}));await screen.findByText(/Correction outcome is unconfirmed/);
    view.rerender(<ObstacleFeedback api={api as unknown as TwinPulseApi} revision={revision} stateSha={sha} enabled fresh={false}/>);
    view.rerender(<ObstacleFeedback api={api as unknown as TwinPulseApi} revision={revision} stateSha={sha} enabled fresh/>);
    expect(screen.getByRole('button',{name:'Preview obstacle correction'}).closest('fieldset')).toHaveProperty('disabled',true);
    expect(api.applyObstacleCorrection).toHaveBeenCalledOnce();expect(api.obstacleFeedbackState).toHaveBeenCalledOnce();
    expect(screen.getByRole('button',{name:'Check saved correction result · read only'})).toHaveProperty('disabled',false);
  });
  it('observes a pending Apply result across stale transport without clearing or resubmitting its operation',async()=>{
    const api=harness();let finish!:(value:SceneEditTransaction)=>void;api.applyObstacleCorrection.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}));
    const view=show(api);await prepare();fireEvent.click(screen.getByRole('button',{name:'Apply reviewed obstacle correction'}));
    view.rerender(<ObstacleFeedback api={api as unknown as TwinPulseApi} revision={revision} stateSha={sha} enabled fresh={false}/>);
    expect(api.applyObstacleCorrection).toHaveBeenCalledOnce();
    await act(async()=>finish({...committed,current_frame:true}));await screen.findByText('Engine ACK received · disk COMMITTED');
    expect(screen.getByRole('button',{name:'Preview Undo last scene edit'})).toHaveProperty('disabled',true);
    view.rerender(<ObstacleFeedback api={api as unknown as TwinPulseApi} revision={revision} stateSha={sha} enabled fresh/>);
    expect(api.applyObstacleCorrection).toHaveBeenCalledOnce();expect(api.obstacleFeedbackState).toHaveBeenCalledOnce();
    expect(screen.getByText('Current frame confirmed for this transaction.')).toBeTruthy();
  });
  it.each(['context','revision','state SHA'])('discards a locked stale proposal when the actual %s identity changes',async changed=>{
    const api=harness(),view=show(api);await prepare();
    view.rerender(<ObstacleFeedback api={api as unknown as TwinPulseApi} revision={revision} stateSha={sha} enabled fresh={false}/>);
    expect(screen.getByRole('status',{name:'Obstacle feedback availability'})).toHaveProperty('textContent',expect.stringContaining('locked views only'));
    if(changed==='context')api.context='context-b';
    view.rerender(<ObstacleFeedback api={api as unknown as TwinPulseApi} revision={changed==='revision'?'8'.repeat(64):revision} stateSha={changed==='state SHA'?'9'.repeat(64):sha} enabled fresh={false}/>);
    expect(screen.queryByRole('region',{name:'Obstacle correction proposal'})).toBeNull();expect(api.applyObstacleCorrection).not.toHaveBeenCalled();
  });
  it('restores read-only Refresh after Activity hides and shows the same panel',async()=>{
    const api=harness();const component=(hidden:boolean)=><Activity mode={hidden?'hidden':'visible'}>
      <ObstacleFeedback api={api as unknown as TwinPulseApi} revision={revision} stateSha={sha} enabled/></Activity>;
    const view=render(component(false));await choose();view.rerender(component(true));view.rerender(component(false));
    await waitFor(()=>expect(api.obstacleFeedbackState).toHaveBeenCalledTimes(2));
    const refresh=screen.getByRole('button',{name:'Refresh obstacle feedback · read only'});await waitFor(()=>expect(refresh).toHaveProperty('disabled',false));
    fireEvent.click(refresh);await waitFor(()=>expect(api.obstacleFeedbackState).toHaveBeenCalledTimes(3));
    expect(api.importObstacleObservation).not.toHaveBeenCalled();expect(api.applyObstacleCorrection).not.toHaveBeenCalled();
  });
  it('keeps the committed read-only Refresh handler usable when a different scene render suspends before commit',async()=>{
    const api=harness();let change!:()=>void,attempted=false;
    const blocked=new Promise<never>(()=>{});
    function Gate({hold}:{hold:boolean}){if(hold){attempted=true;throw blocked;}return null;}
    function ConcurrentScene(){const [next,setNext]=useState(false);change=()=>startTransition(()=>setNext(true));
      return <Suspense fallback={<p>Uncommitted scene loading</p>}><ObstacleFeedback api={api as unknown as TwinPulseApi}
        revision={next?'8'.repeat(64):revision} stateSha={sha} enabled/><Gate hold={next}/></Suspense>;}
    render(<ConcurrentScene/>);await choose();expect(api.obstacleFeedbackState).toHaveBeenCalledOnce();
    await act(async()=>change());expect(attempted).toBe(true);
    expect(screen.queryByText('Uncommitted scene loading')).toBeNull();
    const refresh=screen.getByRole('button',{name:'Refresh obstacle feedback · read only'});expect(refresh).toHaveProperty('disabled',false);
    fireEvent.click(refresh);await waitFor(()=>expect(api.obstacleFeedbackState).toHaveBeenCalledTimes(2));
    expect(api.importObstacleObservation).not.toHaveBeenCalled();expect(api.applyObstacleCorrection).not.toHaveBeenCalled();
  });
  it('loads only saved state and shows empty guidance without requiring a robot or scan',async()=>{
    const api=harness({...feedback,observations:[]});show(api);
    expect(await screen.findByText(/No saved obstacle observation/)).toBeTruthy();
    expect(screen.getByRole('button',{name:'Import obstacle observation · local only'})).toHaveProperty('disabled',true);
    expect(screen.getByText(/A scan is not required to create a draft/)).toBeTruthy();
    expect(api.importObstacleObservation).not.toHaveBeenCalled();expect(api.previewObstacleCorrection).not.toHaveBeenCalled();
    expect(api.simulationRun).not.toHaveBeenCalled();expect(api.conversationAction).not.toHaveBeenCalled();
  });
  it('plots cell centres in the supplied room metres without applying cell size twice',async()=>{
    const api=harness({...feedback,observations:[{...observation,points:[[1,0]],cells:[[1,0,'occupied']],cell_size_m:.1,cell_coordinates:'room_metres_cell_centres'}]});show(api);
    const plot=await screen.findByRole('img',{name:'Imported XY points and occupied free unknown markers'});
    const point=plot.querySelector('circle')!,cell=plot.querySelectorAll('rect')[1];
    expect(Number(point.getAttribute('cx'))).toBeCloseTo(Number(cell.getAttribute('x'))+2);
    expect(Number(point.getAttribute('cy'))).toBeCloseTo(Number(cell.getAttribute('y'))+2);
    expect(screen.getByText(/Supplied grid cell size: 0.1 m/)).toBeTruthy();expect(screen.getByText(/unobserved space remains unknown/)).toBeTruthy();
  });
  it('imports a local wrapped record only after explicit estimated coordinates, preserving all original snapshots',async()=>{
    const api=harness();show(api);await screen.findByRole('option',{name:'Desk · desk-a'});
    const scan={stamp_ns:1,frame_id:'laser',angle_min_rad:0,angle_increment_rad:.1,range_min_m:.05,range_max_m:4,ranges_m:[1,null,2]};
    const wrapped={job_id:'connection-job',obstacle_observation:{schema_version:'obstacle-observation-1.0',provenance:'ROBOT_READ_ONLY',scans:[scan,{...scan,stamp_ns:2}]}};
    fireEvent.change(screen.getByLabelText('Sensor observation JSON'),{target:{files:[jsonFile(wrapped)]}});
    expect(screen.getByRole('button',{name:'Import obstacle observation · local only'})).toHaveProperty('disabled',true);
    importInputs(jsonFile(wrapped));fireEvent.click(screen.getByRole('button',{name:'Import obstacle observation · local only'}));
    await waitFor(()=>expect(api.importObstacleObservation).toHaveBeenCalledExactlyOnceWith({json_text:JSON.stringify(wrapped)},revision,sha,[0,1,.5],.2));
    expect(await screen.findByText(/Observation imported locally/)).toBeTruthy();expect(api.applyObstacleCorrection).not.toHaveBeenCalled();
    expect(screen.getByRole('img',{name:'Imported XY points and occupied free unknown markers'})).toBeTruthy();
    expect(screen.getByText(/Occupied 1 · free 1 · unknown 1/)).toBeTruthy();
  });
  it('transports the UTF-8 source text without changing numeric spellings or a robot export wrapper',async()=>{
    const api=harness();show(api);await choose();
    const text='{\n "job_id":"로봇-관측", "source_sha256":"declared-source-hash",\n "obstacle_observation":{"schema_version":"obstacle-observation-1.0","provenance":"ROBOT_READ_ONLY","scans":[{"stamp_ns":1,"frame_id":"laser","angle_min_rad":-0.0,"angle_increment_rad":0.1,"range_min_m":0.0,"range_max_m":4.0,"ranges_m":[1.0,null,2.0]}]}\n}';
    const file=jsonFile(text);expect(file.size).toBe(new TextEncoder().encode(text).length);
    importInputs(file);fireEvent.click(screen.getByRole('button',{name:'Import obstacle observation · local only'}));
    await waitFor(()=>expect(api.importObstacleObservation).toHaveBeenCalledExactlyOnceWith({json_text:text},revision,sha,[0,1,.5],.2));
    const sent=api.importObstacleObservation.mock.calls[0][0] as {json_text:string};
    expect(JSON.parse(sent.json_text)).toEqual(JSON.parse(text));expect(sent.json_text).not.toBe(JSON.stringify(JSON.parse(text)));
  });
  it.each(['invalid','oversized','array','null'])('rejects %s local JSON without an import request',async kind=>{
    const api=harness();show(api);await choose();const file=jsonFile(kind==='invalid'?'{bad':kind==='array'?[]:kind==='null'?null:{});
    if(kind==='oversized')Object.defineProperty(file,'size',{value:2*1024*1024+1});
    importInputs(file);fireEvent.click(screen.getByRole('button',{name:'Import obstacle observation · local only'}));
    await screen.findByRole('alert');expect(api.importObstacleObservation).not.toHaveBeenCalled();
  });
  it('requires bounded estimated pose and height and rejects a late file read before sending an import',async()=>{
    const api=harness();const view=show(api);await choose();const file=jsonFile({schema_version:'obstacle-observation-1.0'});
    let finish!:(text:string)=>void;Object.defineProperty(file,'text',{configurable:true,value:()=>new Promise<string>(resolve=>{finish=resolve;})});
    importInputs(file);fireEvent.change(screen.getByLabelText('Estimated scan height'),{target:{value:'0'}});
    expect(screen.getByRole('button',{name:'Import obstacle observation · local only'})).toHaveProperty('disabled',true);
    fireEvent.change(screen.getByLabelText('Estimated scan height'),{target:{value:'.2'}});
    fireEvent.click(screen.getByRole('button',{name:'Import obstacle observation · local only'}));api.context='context-b';
    view.rerender(<ObstacleFeedback api={api as unknown as TwinPulseApi} revision={revision} stateSha={sha} enabled/>);
    await act(async()=>finish('{}'));expect(api.importObstacleObservation).not.toHaveBeenCalled();
  });
  it('sends null for automatic fit and requires a separate reviewed Apply',async()=>{
    const api=harness();show(api);await prepare();
    expect(api.previewObstacleCorrection).toHaveBeenCalledExactlyOnceWith(observation.id,observation.sha256,revision,sha,'desk-a',null);
    expect(api.applyObstacleCorrection).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button',{name:'Apply reviewed obstacle correction'}));
    await waitFor(()=>expect(api.applyObstacleCorrection).toHaveBeenCalledExactlyOnceWith(proposal));
    expect(await screen.findByText('Engine ACK received · disk COMMITTED')).toBeTruthy();
    expect(screen.getByText(/Current frame not confirmed here/)).toBeTruthy();expect(api.simulationRun).not.toHaveBeenCalled();
  });
  it('keeps uncertain fits held and never offers an applicable correction',async()=>{
    const api=harness();api.previewObstacleCorrection.mockResolvedValue({...proposal,status:'HELD',reason:'INSUFFICIENT_SENSOR_EVIDENCE',operation:undefined});show(api);await prepare();
    expect(screen.getByText('Correction held · not applied')).toBeTruthy();expect(screen.getByText('INSUFFICIENT_SENSOR_EVIDENCE')).toBeTruthy();
    const apply=screen.getByRole('button',{name:'Apply reviewed obstacle correction'});expect(apply).toHaveProperty('disabled',true);fireEvent.click(apply);
    expect(api.applyObstacleCorrection).not.toHaveBeenCalled();
  });
  it('labels manual finite XY as an estimate and invalidates the prior preview when inputs or target change',async()=>{
    const api=harness();show(api);await prepare();
    fireEvent.click(screen.getByRole('checkbox',{name:'Specify an estimated XY translation instead of automatic fit'}));
    expect(screen.queryByRole('region',{name:'Obstacle correction proposal'})).toBeNull();
    expect(screen.getByRole('button',{name:'Preview obstacle correction'})).toHaveProperty('disabled',true);
    fireEvent.change(screen.getByLabelText('Estimated delta X'),{target:{value:'.25'}});fireEvent.change(screen.getByLabelText('Estimated delta Y'),{target:{value:'-.1'}});
    fireEvent.click(screen.getByRole('button',{name:'Preview obstacle correction'}));await screen.findByRole('region',{name:'Obstacle correction proposal'});
    expect(api.previewObstacleCorrection).toHaveBeenLastCalledWith(observation.id,observation.sha256,revision,sha,'desk-a',[.25,-.1]);
    fireEvent.change(screen.getByLabelText('Correction target'),{target:{value:'chair-a'}});
    expect(screen.queryByRole('region',{name:'Obstacle correction proposal'})).toBeNull();expect(api.applyObstacleCorrection).not.toHaveBeenCalled();
  });
  it.each(['revision','state','context','disabled'])('rejects a late preview across a %s change',async change=>{
    const api=harness();let finish!:(value:ObstacleCorrectionPreview)=>void;api.previewObstacleCorrection.mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
    const view=show(api);await choose();fireEvent.click(screen.getByRole('button',{name:'Preview obstacle correction'}));
    const nextRevision=change==='revision'?'3'.repeat(64):revision,nextSha=change==='state'?'4'.repeat(64):sha;
    if(change==='context')api.context='context-b';
    api.obstacleFeedbackState.mockResolvedValue({...feedback,context:{...feedback.context,current_scene_revision:nextRevision,current_state_sha256:nextSha}});
    view.rerender(<ObstacleFeedback api={api as unknown as TwinPulseApi} revision={nextRevision} stateSha={nextSha} enabled={change!=='disabled'}/>);
    await act(async()=>finish(proposal));
    expect(screen.queryByRole('region',{name:'Obstacle correction proposal'})).toBeNull();expect(api.applyObstacleCorrection).not.toHaveBeenCalled();
  });
  it('does not fetch a disabled panel or accept a late read after unmount',async()=>{
    const api=harness();const view=show(api,{enabled:false});expect(api.obstacleFeedbackState).not.toHaveBeenCalled();expect(api.sceneEditTransaction).not.toHaveBeenCalled();
    let finish!:(value:ObstacleFeedbackState)=>void;api.obstacleFeedbackState.mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
    view.rerender(<ObstacleFeedback api={api as unknown as TwinPulseApi} revision={revision} stateSha={sha} enabled/>);
    view.unmount();await act(async()=>finish(feedback));expect(api.applyObstacleCorrection).not.toHaveBeenCalled();
  });
  it('does not read or enable correction with an unknown current-state SHA',()=>{
    const api=harness();show(api,{stateSha:null});expect(api.obstacleFeedbackState).not.toHaveBeenCalled();
    expect(screen.getByRole('button',{name:'Preview obstacle correction'}).closest('fieldset')).toHaveProperty('disabled',true);
  });
  it('checks ACK/disk/current frame independently using read-only polls',async()=>{
    const api=harness();api.applyObstacleCorrection.mockResolvedValue({...committed,state:'BUILDING',engine_acknowledged:false,durable_committed:false});
    api.sceneEditTransaction.mockResolvedValueOnce(null).mockResolvedValue(committed);const view=show(api);await prepare();
    fireEvent.click(screen.getByRole('button',{name:'Apply reviewed obstacle correction'}));
    expect(await screen.findByText(/Scene transaction: BUILDING/)).toBeTruthy();
    await screen.findByText('Engine ACK received · disk COMMITTED',{}, {timeout:2000});
    expect(screen.getByText(/Current frame not confirmed here/)).toBeTruthy();
    api.sceneEditTransaction.mockResolvedValue({...committed,current_frame:true});
    await screen.findByText('Current frame confirmed for this transaction.',{}, {timeout:2000});
    expect(api.applyObstacleCorrection).toHaveBeenCalledOnce();view.unmount();
  });
  it('does not let an older frame-check response overwrite a newly submitted correction',async()=>{
    const api=harness();let finish!:(value:SceneEditTransaction)=>void;
    const prior={...committed,operation_id:'previous-correction'};
    api.sceneEditTransaction.mockResolvedValueOnce(prior).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}));
    api.applyObstacleCorrection.mockResolvedValue({...committed,state:'BUILDING',engine_acknowledged:false,durable_committed:false});
    const view=show(api);await screen.findByText('Engine ACK received · disk COMMITTED');
    await waitFor(()=>expect(api.sceneEditTransaction).toHaveBeenCalledTimes(2),{timeout:2000});await prepare();
    fireEvent.click(screen.getByRole('button',{name:'Apply reviewed obstacle correction'}));await screen.findByText(/Scene transaction: BUILDING/);
    await act(async()=>finish({...prior,current_frame:true}));
    expect(screen.getByText(/Scene transaction: BUILDING/)).toBeTruthy();expect(screen.queryByText('Engine ACK received · disk COMMITTED')).toBeNull();
    view.unmount();
  });
  it('never resubmits an unconfirmed Apply and recovers only by reading the exact operation',async()=>{
    const api=harness();api.applyObstacleCorrection.mockRejectedValue(new ApiError('delivery_unknown','Lost response'));const view=show(api);await prepare();
    fireEvent.click(screen.getByRole('button',{name:'Apply reviewed obstacle correction'}));
    await screen.findByText(/Correction outcome is unconfirmed/);
    expect(screen.getByRole('button',{name:'Preview obstacle correction'}).closest('fieldset')).toHaveProperty('disabled',true);
    api.sceneEditTransaction.mockResolvedValue(committed);fireEvent.click(screen.getByRole('button',{name:'Check saved correction result · read only'}));
    await screen.findByText('Engine ACK received · disk COMMITTED');expect(api.applyObstacleCorrection).toHaveBeenCalledOnce();view.unmount();
  });
  it.each(['scene_edit_invalid','scene_edit_engine_not_ready','scene_sensor_apply_rejected'])('unlocks known pre-dispatch %s only for a fresh explicit review',async code=>{
    const api=harness();api.applyObstacleCorrection.mockRejectedValueOnce(new ApiError(code,'Admission rejected'));
    const view=show(api);await prepare();fireEvent.click(screen.getByRole('button',{name:'Apply reviewed obstacle correction'}));
    await screen.findByText(/Preview was rejected before dispatch/);
    if(code==='scene_edit_engine_not_ready')expect(screen.getByText(/use "View current Twin".*saved scene in Isaac.*ready and idle/)).toBeTruthy();
    expect(screen.queryByText(/Correction outcome is unconfirmed/)).toBeNull();
    expect(screen.queryByRole('button',{name:'Apply reviewed obstacle correction'})).toBeNull();
    expect(screen.getByRole('button',{name:'Preview obstacle correction'}).closest('fieldset')).toHaveProperty('disabled',false);
    expect(api.applyObstacleCorrection).toHaveBeenCalledOnce();
    expect(api.obstacleFeedbackState).toHaveBeenCalledOnce();expect(api.simulationRun).not.toHaveBeenCalled();expect(api.conversationAction).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button',{name:'Refresh obstacle feedback · read only'}));
    await waitFor(()=>expect(api.obstacleFeedbackState).toHaveBeenCalledTimes(2));
    fireEvent.click(screen.getByRole('button',{name:'Preview obstacle correction'}));await screen.findByRole('region',{name:'Obstacle correction proposal'});
    expect(api.applyObstacleCorrection).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole('button',{name:'Apply reviewed obstacle correction'}));
    await screen.findByText('Engine ACK received · disk COMMITTED');expect(api.applyObstacleCorrection).toHaveBeenCalledTimes(2);view.unmount();
  });
  it.each(['context_changed','engine_state_unknown','scene_edit_busy'])('keeps other Apply %s unconfirmed and does not automatically resubmit',async code=>{
    const api=harness();api.applyObstacleCorrection.mockRejectedValue(new ApiError(code,'Unconfirmed result'));show(api);await prepare();
    fireEvent.click(screen.getByRole('button',{name:'Apply reviewed obstacle correction'}));await screen.findByText(/Correction outcome is unconfirmed/);
    expect(screen.getByRole('button',{name:'Preview obstacle correction'}).closest('fieldset')).toHaveProperty('disabled',true);
    expect(screen.queryByText(/Preview was rejected before dispatch/)).toBeNull();expect(api.applyObstacleCorrection).toHaveBeenCalledOnce();
  });
  it('keeps an acknowledged transaction with an unknown outcome locked despite an admission-like error message',async()=>{
    const api=harness();api.applyObstacleCorrection.mockResolvedValue({...committed,state:'ENGINE_STATE_UNKNOWN',durable_committed:false,
      error:'scene_edit_engine_not_ready'});show(api);await prepare();
    fireEvent.click(screen.getByRole('button',{name:'Apply reviewed obstacle correction'}));await screen.findByText(/Scene transaction: ENGINE_STATE_UNKNOWN/);
    expect(screen.getByRole('button',{name:'Preview obstacle correction'}).closest('fieldset')).toHaveProperty('disabled',true);
    expect(screen.queryByText(/Preview was rejected before dispatch/)).toBeNull();expect(api.applyObstacleCorrection).toHaveBeenCalledOnce();
    expect(screen.queryByText('Engine ACK received · disk COMMITTED')).toBeNull();
  });
  it('reopens a rejected preview with saved selection but without replaying Apply or persisting its UI lock',async()=>{
    const api=harness();api.applyObstacleCorrection.mockRejectedValue(new ApiError('scene_edit_engine_not_ready','Admission rejected'));
    const first=show(api);await prepare();fireEvent.click(screen.getByRole('button',{name:'Apply reviewed obstacle correction'}));
    await screen.findByText(/use "View current Twin"/);first.unmount();
    const view=show(api);await waitFor(()=>expect(screen.getByLabelText('Correction target')).toHaveProperty('value','desk-a'));
    expect(screen.getByRole('button',{name:'Preview obstacle correction'}).closest('fieldset')).toHaveProperty('disabled',false);
    expect(screen.queryByRole('region',{name:'Obstacle correction proposal'})).toBeNull();
    expect(api.applyObstacleCorrection).toHaveBeenCalledOnce();expect(api.previewObstacleCorrection).toHaveBeenCalledOnce();view.unmount();
  });
  it('does not reinterpret a restored unknown transaction as a safe rejection from its error text',async()=>{
    const api=harness();api.sceneEditTransaction.mockResolvedValue({...committed,state:'ENGINE_STATE_UNKNOWN',durable_committed:false,
      error:'scene_edit_engine_not_ready'});show(api);await screen.findByText(/Scene transaction: ENGINE_STATE_UNKNOWN/);
    expect(screen.getByRole('button',{name:'Preview obstacle correction'}).closest('fieldset')).toHaveProperty('disabled',true);
    expect(screen.queryByText(/Preview was rejected before dispatch/)).toBeNull();
    expect(api.applyObstacleCorrection).not.toHaveBeenCalled();expect(api.previewObstacleCorrection).not.toHaveBeenCalled();
  });
  it('does not call a different operation a committed correction',async()=>{
    const api=harness();api.applyObstacleCorrection.mockResolvedValue({...committed,operation_id:'different-operation'});show(api);await prepare();
    fireEvent.click(screen.getByRole('button',{name:'Apply reviewed obstacle correction'}));await screen.findByRole('alert');
    expect(screen.queryByText('Engine ACK received · disk COMMITTED')).toBeNull();expect(api.applyObstacleCorrection).toHaveBeenCalledOnce();
  });
  it('previews and explicitly applies the common Undo without deleting observations',async()=>{
    const api=harness();const undo=undoPreview;expect(undo).not.toHaveProperty('apply_version');
    api.previewSceneEdit.mockResolvedValue(undo);api.startSceneEditTransaction.mockResolvedValue({...committed,operation_id:'undo-operation'});
    const view=show(api);await choose();fireEvent.click(screen.getByRole('button',{name:'Preview Undo last scene edit'}));
    await screen.findByRole('region',{name:'Obstacle feedback Undo review'});
    expect(api.previewSceneEdit).toHaveBeenCalledExactlyOnceWith(expect.stringMatching(/^obstacle_undo_/),'undo',null,null);
    expect(api.startSceneEditTransaction).not.toHaveBeenCalled();expect(screen.getByRole('button',{name:'Apply reviewed Undo'})).toHaveProperty('disabled',false);
    fireEvent.click(screen.getByRole('button',{name:'Apply reviewed Undo'}));
    await waitFor(()=>expect(api.startSceneEditTransaction).toHaveBeenCalledExactlyOnceWith(undo));
    expect(screen.getByRole('option',{name:new RegExp(observation.id)})).toBeTruthy();expect(api.importObstacleObservation).not.toHaveBeenCalled();view.unmount();
  });
  it.each(['mode','parent revision','parent SHA','operation revision','operation SHA','operation id','digest'])('rejects Undo with an invalid %s without submitting a transaction',async field=>{
    const api=harness();const undo={...undoPreview,operation:{...undoPreview.operation}};
    if(field==='mode')undo.operation.mode='change';
    if(field==='parent revision')undo.parent_revision='8'.repeat(64);
    if(field==='parent SHA')undo.parent_state_sha256='8'.repeat(64);
    if(field==='operation revision')undo.operation.parent_revision='8'.repeat(64);
    if(field==='operation SHA')undo.operation.parent_state_sha256='8'.repeat(64);
    if(field==='operation id')undo.operation.operation_id='';
    if(field==='digest')undo.preview_digest='';
    api.previewSceneEdit.mockResolvedValue(undo);show(api);await choose();fireEvent.click(screen.getByRole('button',{name:'Preview Undo last scene edit'}));
    await screen.findByRole('region',{name:'Obstacle feedback Undo review'});
    const apply=screen.getByRole('button',{name:'Apply reviewed Undo'});expect(apply).toHaveProperty('disabled',true);fireEvent.click(apply);
    expect(api.startSceneEditTransaction).not.toHaveBeenCalled();
  });
  it('reopens saved observations, selected IDs and historical transaction without replaying Apply',async()=>{
    const api=harness();const first=show(api);await choose();first.unmount();
    api.sceneEditTransaction.mockResolvedValue({...committed,historical:true,current_frame:false});const view=show(api);
    await waitFor(()=>expect(screen.getByLabelText('Correction target')).toHaveProperty('value','desk-a'));
    expect(screen.getByLabelText('Obstacle observation')).toHaveProperty('value',observation.id);
    expect(await screen.findByText('Engine ACK received · disk COMMITTED')).toBeTruthy();
    expect(screen.getByText(/Current frame not confirmed here/)).toBeTruthy();expect(api.applyObstacleCorrection).not.toHaveBeenCalled();view.unmount();
  });
  it('treats malformed optional stored selections as no selection, not as correction authority',async()=>{
    sessionStorage.setItem('twinpulse.obstacle.selection.room-a','null');const api=harness();show(api);
    await screen.findByRole('option',{name:'Desk · desk-a'});expect(screen.getByLabelText('Correction target')).toHaveProperty('value','');
    expect(api.applyObstacleCorrection).not.toHaveBeenCalled();
  });
});
