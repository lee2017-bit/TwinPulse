// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {TwinPulseApi} from './api';
import {EnvironmentImport} from './EnvironmentImport';
import type {EnvironmentAction,EnvironmentState} from './environment-types';
import type {SceneEditPreview,SceneEditTransaction,WorkflowState} from './types';

const snapshot=(status:EnvironmentState['status']='empty'):EnvironmentState=>({project_id:'room',status,job_id:status==='empty'?null:'inspection',error:null,
  source_name:status==='empty'?null:'room.usdc',source_sha256:status==='empty'?null:'a'.repeat(64),units_basis:status==='empty'?null:'selected_for_sim',
  objects:status==='empty'?[]:[{id:'chair_1',category:'Chair',label:'Chair',position_m:[1,2,0]}],scene_revision:status==='imported'?'scene-a':null});
const workflow={phase:'draft_ready',site_draft:{revision:'scene-a'}} as WorkflowState;
function localFile(name='room.usdc'){
  const file=new File(['room geometry'],name,{type:'application/octet-stream'});
  Object.defineProperty(file,'arrayBuffer',{value:async()=>new TextEncoder().encode('room geometry').buffer});return file;
}
function harness(initial=snapshot()){
  const api={context:'context-a',environment:vi.fn(async()=>initial),environmentAction:vi.fn(async(_body:EnvironmentAction)=>initial),workflow:vi.fn(async()=>workflow),
    applyEnvironmentEdit:vi.fn(async(_operation:Record<string,unknown>,_digest:string)=>editTransaction('DISPATCHED',false)),sceneEditTransaction:vi.fn(async()=>editTransaction())};
  return {api,typed:api as unknown as TwinPulseApi};
}
function editTransaction(state='COMMITTED',frame=true):SceneEditTransaction{return {operation_id:'move',state,engine_acknowledged:true,durable_committed:state==='COMMITTED',current_frame:frame,result_revision:'scene-b',command_id:'command',error:null};}
afterEach(()=>{vi.useRealTimers();vi.unstubAllGlobals();});

describe('local space import',()=>{
  it('requires explicit photo consent and submits exactly one analysis without Apply',async()=>{
    const h=harness(snapshot('imported'));render(<EnvironmentImport api={h.typed} close={vi.fn()} onReady={vi.fn()}/>);
    await screen.findByText('Added obstacles · 0');fireEvent.click(screen.getByText('Added obstacles · 0'));
    expect(h.api.environmentAction).not.toHaveBeenCalled();
    const photo=new File(['photo'],'room.jpg',{type:'image/jpeg'});
    fireEvent.change(screen.getByLabelText('Obstacle reference photo'),{target:{files:[photo]}});
    expect(screen.getByRole('button',{name:'Analyze photo'})).toHaveProperty('disabled',true);
    fireEvent.click(screen.getByLabelText('Allow photo analysis'));fireEvent.click(screen.getByRole('button',{name:'Analyze photo'}));
    await waitFor(()=>expect(h.api.environmentAction).toHaveBeenCalledWith(expect.objectContaining({action:'photo_analyze',consent:true,
      photo:{name:'room.jpg',bytes_base64:'cGhvdG8='},expected_scene_revision:'scene-a'})));
    expect(h.api.environmentAction).toHaveBeenCalledTimes(1);expect(h.api.applyEnvironmentEdit).not.toHaveBeenCalled();
    expect(screen.getByLabelText('Allow photo analysis')).toHaveProperty('checked',false);
  });
  it('restores photo candidates read-only and requires coordinates plus duplicate review',async()=>{
    const state=snapshot('imported');state.photo_proposal={status:'ready',error:null,job_id:'photo-job',model_id:'fake-observer',explanation:'Review estimates.',
      candidates:[{id:'Candidate_1',kind:'basket',label:'Basket candidate',confidence:.8,bbox:[.1,.2,.4,.7],description:'Check the photo.',
        dimensions_m:[.35,.3,.4],dimensions_basis:'catalog_estimate',duplicate_check_required:true}]};
    const h=harness(state);render(<EnvironmentImport api={h.typed} close={vi.fn()} onReady={vi.fn()}/>);
    await screen.findByText('Added obstacles · 0');fireEvent.click(screen.getByText('Added obstacles · 0'));
    expect(h.api.environmentAction).not.toHaveBeenCalled();fireEvent.click(screen.getByRole('button',{name:'Review Candidate_1'}));
    expect(screen.getByLabelText('Obstacle X')).toHaveProperty('value','');expect(screen.getByRole('button',{name:'Preview obstacle'})).toHaveProperty('disabled',true);
    fireEvent.change(screen.getByLabelText('Obstacle X'),{target:{value:'1.3'}});fireEvent.change(screen.getByLabelText('Obstacle Y'),{target:{value:'1.4'}});
    expect(screen.getByRole('button',{name:'Preview obstacle'})).toHaveProperty('disabled',true);
    fireEvent.click(screen.getByLabelText('Candidate duplicate reviewed'));fireEvent.click(screen.getByRole('button',{name:'Preview obstacle'}));
    await waitFor(()=>expect(h.api.environmentAction).toHaveBeenCalledWith(expect.objectContaining({action:'photo_candidate_preview',duplicate_reviewed:true,
      candidate_ref:{job_id:'photo-job',candidate_id:'Candidate_1'},obstacle:expect.objectContaining({position_xy_m:[1.3,1.4]})})));
    expect(h.api.environmentAction).toHaveBeenCalledTimes(1);expect(h.api.applyEnvironmentEdit).not.toHaveBeenCalled();
  });
  it('previews an estimated catalog obstacle separately without applying or calling a model',async()=>{
    const h=harness(snapshot('imported'));render(<EnvironmentImport api={h.typed} close={vi.fn()} onReady={vi.fn()}/>);
    await screen.findByText('Added obstacles · 0');
    fireEvent.click(screen.getByText('Added obstacles · 0'));
    fireEvent.change(screen.getByLabelText('Obstacle X'),{target:{value:'1.3'}});
    fireEvent.change(screen.getByLabelText('Obstacle Y'),{target:{value:'1.4'}});
    fireEvent.click(screen.getByRole('button',{name:'Preview obstacle'}));
    await waitFor(()=>expect(h.api.environmentAction).toHaveBeenCalledWith(expect.objectContaining({action:'add_overlay_preview',
      expected_scene_revision:'scene-a',photo:null,obstacle:{kind:'basket',label:'Basket',position_xy_m:[1.3,1.4],dimensions_m:[.35,.3,.4],yaw_deg:0,uncertainty_m:.2}})));
    expect(h.api.applyEnvironmentEdit).not.toHaveBeenCalled();
    expect(screen.getByText(/not automatic photo-to-room alignment/)).toBeTruthy();
  });
  it('does not submit invalid uncertainty, floor dimensions or blank coordinates',async()=>{
    const h=harness(snapshot('imported'));render(<EnvironmentImport api={h.typed} close={vi.fn()} onReady={vi.fn()}/>);
    await screen.findByText('Added obstacles · 0');fireEvent.click(screen.getByText('Added obstacles · 0'));
    fireEvent.change(screen.getByLabelText('Obstacle uncertainty'),{target:{value:'0'}});
    expect(screen.getByRole('button',{name:'Preview obstacle'})).toHaveProperty('disabled',true);
    fireEvent.change(screen.getByLabelText('Obstacle uncertainty'),{target:{value:'.2'}});
    fireEvent.change(screen.getByLabelText('Obstacle X'),{target:{value:''}});
    expect(screen.getByRole('button',{name:'Preview obstacle'})).toHaveProperty('disabled',true);
    expect(h.api.environmentAction).not.toHaveBeenCalled();
  });
  it('shows saved photo provenance and removes only an added obstacle through preview',async()=>{
    const state=snapshot('imported');state.objects.push({id:'Added_abc',category:'basket',label:'Basket',position_m:[1,1,.2],added:true,
      uncertainty_m:.2,risk:'collision',evidence:{basis:'photo_estimate',source_name:'room.jpg',sha256:'b'.repeat(64),alignment_verified:false}});
    const h=harness(state);render(<EnvironmentImport api={h.typed} close={vi.fn()} onReady={vi.fn()}/>);
    await screen.findByText('Added obstacles · 1');fireEvent.click(screen.getByText('Added obstacles · 1'));
    expect(screen.getByText(/photo estimate · not aligned/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'Remove Basket · preview'}));
    await waitFor(()=>expect(h.api.environmentAction).toHaveBeenCalledWith(expect.objectContaining({action:'remove_overlay_preview',object_id:'Added_abc',expected_scene_revision:'scene-a'})));
    expect(h.api.applyEnvironmentEdit).not.toHaveBeenCalled();
  });
  it('shows geometry bounds without claiming measured dimensions or photo fusion',async()=>{
    const state=snapshot('imported');state.objects[0].dimensions_m=[1.23456,.4,.9];const h=harness(state);
    render(<EnvironmentImport api={h.typed} close={vi.fn()} onReady={vi.fn()}/>);
    await screen.findByText('Objects and size');
    expect(screen.getByText(/1.235 × 0.400 × 0.900 m/)).toBeTruthy();
    expect(screen.getByText(/not measured object dimensions/)).toBeTruthy();
    expect(screen.getByText(/Photos are not automatically merged/)).toBeTruthy();
    expect(h.api.environmentAction).not.toHaveBeenCalled();
  });
  it('keeps selection local with no implicit unit choice or inspection',async()=>{
    const h=harness();render(<EnvironmentImport api={h.typed} initialFile={localFile()} close={vi.fn()} onReady={vi.fn()}/>);
    await screen.findByText('Import status: empty');
    expect(screen.getByLabelText('Space source units')).toHaveProperty('value','');
    expect(screen.getByText(/room.usdc · selected locally/)).toBeTruthy();
    expect(h.api.environmentAction).not.toHaveBeenCalled();
    expect(screen.queryByRole('button',{name:'Import space'})).toBeNull();
  });

  it('retains missing-unit rejection until an explicit SIM unit choice and new Inspect',async()=>{
    const h=harness();h.api.environmentAction.mockImplementation(async body=>body.action==='inspect'&&body.units===null?
      {...snapshot('failed'),error:'USD source units are missing. Choose units explicitly.'}:snapshot('ready'));
    render(<EnvironmentImport api={h.typed} initialFile={localFile()} close={vi.fn()} onReady={vi.fn()}/>);
    await screen.findByText('Import status: empty');fireEvent.click(screen.getByRole('button',{name:'Inspect space'}));
    expect(await screen.findByRole('alert')).toHaveProperty('textContent','USD source units are missing. Choose units explicitly.');
    expect(h.api.environmentAction).toHaveBeenCalledWith(expect.objectContaining({action:'inspect',units:null}));
    expect(screen.queryByRole('button',{name:'Import space'})).toBeNull();
    fireEvent.change(screen.getByLabelText('Space source units'),{target:{value:'m'}});
    expect(screen.getByText(/User-selected units are uncalibrated SIM scale/)).toBeTruthy();
    expect(h.api.environmentAction).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button',{name:'Inspect space'}));
    await screen.findByRole('button',{name:'Import space'});
    expect(h.api.environmentAction).toHaveBeenLastCalledWith(expect.objectContaining({action:'inspect',units:'m'}));
  });

  it('requires separate Inspect, Import and Show Twin clicks',async()=>{
    const h=harness(),ready=vi.fn();h.api.environmentAction.mockImplementation(async body=>body.action==='inspect'?snapshot('ready'):
      body.action==='adopt'?{...snapshot('imported'),workflow}:{...snapshot('imported'),workflow});
    render(<EnvironmentImport api={h.typed} initialFile={localFile()} close={vi.fn()} onReady={ready}/>);
    await screen.findByText('Import status: empty');fireEvent.change(screen.getByLabelText('Space source units'),{target:{value:'m'}});
    fireEvent.click(screen.getByRole('button',{name:'Inspect space'}));
    fireEvent.click(await screen.findByRole('button',{name:'Import space'}));
    await screen.findByRole('button',{name:'Show Twin'});
    expect(h.api.environmentAction.mock.calls.map(([body])=>body.action)).toEqual(['inspect','adopt']);
    expect(ready).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button',{name:'Show Twin'}));
    await waitFor(()=>expect(h.api.environmentAction.mock.calls.map(([body])=>body.action)).toEqual(['inspect','adopt','build']));
    expect(ready).toHaveBeenCalledTimes(2);
  });

  it('polls an asynchronous inspection with GET only and stops when ready',async()=>{
    vi.useFakeTimers();const h=harness();h.api.environmentAction.mockResolvedValue(snapshot('inspecting'));
    render(<EnvironmentImport api={h.typed} initialFile={localFile()} close={vi.fn()} onReady={vi.fn()}/>);
    await act(async()=>{await Promise.resolve();});
    fireEvent.click(screen.getByRole('button',{name:'Inspect space'}));
    await act(async()=>{await Promise.resolve();});
    h.api.environment.mockResolvedValue(snapshot('ready'));
    await act(async()=>{await vi.advanceTimersByTimeAsync(1000);});
    expect(screen.getByRole('button',{name:'Import space'})).toBeTruthy();
    const count=h.api.environment.mock.calls.length;
    await act(async()=>{await vi.advanceTimersByTimeAsync(4000);});
    expect(h.api.environment).toHaveBeenCalledTimes(count);expect(h.api.environmentAction).toHaveBeenCalledTimes(1);
  });

  it('discards a late old-context import response and never calls its workflow callback',async()=>{
    const h=harness(snapshot('ready')),ready=vi.fn();let complete!:(value:EnvironmentState)=>void;
    h.api.environmentAction.mockImplementation(()=>new Promise(resolve=>{complete=resolve;}));
    const view=render(<EnvironmentImport api={h.typed} close={vi.fn()} onReady={ready}/>);
    fireEvent.click(await screen.findByRole('button',{name:'Import space'}));
    h.api.context='context-b';h.api.environment.mockResolvedValue({...snapshot(),project_id:'other'});
    view.rerender(<EnvironmentImport api={h.typed} close={vi.fn()} onReady={ready}/>);
    await screen.findByText('Import status: empty');
    await act(async()=>{complete({...snapshot('imported'),workflow});});
    expect(ready).not.toHaveBeenCalled();expect(screen.queryByRole('button',{name:'Show Twin'})).toBeNull();
    expect(screen.getByText('Import status: empty')).toBeTruthy();
  });

  it('rejects an unsupported environment file without submitting it',async()=>{
    const h=harness();render(<EnvironmentImport api={h.typed} close={vi.fn()} onReady={vi.fn()}/>);
    await screen.findByText('Import status: empty');
    fireEvent.change(screen.getByLabelText('Space USD file'),{target:{files:[localFile('asset.obj')]}});
    expect(screen.getByRole('alert').textContent).toMatch(/Choose one self-contained USD/);
    expect(screen.getByRole('button',{name:'Inspect space'})).toHaveProperty('disabled',true);
    expect(h.api.environmentAction).not.toHaveBeenCalled();
  });

  it('rejects a space file over the 10 MiB backend limit before reading its bytes',async()=>{
    const h=harness(),file=localFile();Object.defineProperty(file,'size',{value:10*1024*1024+1});
    render(<EnvironmentImport api={h.typed} close={vi.fn()} onReady={vi.fn()}/>);
    await screen.findByText('Import status: empty');
    fireEvent.change(screen.getByLabelText('Space USD file'),{target:{files:[file]}});
    expect(screen.getByRole('alert').textContent).toMatch(/up to 10 MiB/);
    expect(screen.getByRole('button',{name:'Inspect space'})).toHaveProperty('disabled',true);
    expect(h.api.environmentAction).not.toHaveBeenCalled();
  });

  it('restores a saved imported space with an explicit Show Twin action only',async()=>{
    const h=harness(snapshot('imported'));render(<EnvironmentImport api={h.typed} close={vi.fn()} onReady={vi.fn()}/>);
    await screen.findByRole('button',{name:'Show Twin'});
    expect(screen.getByText(/Space imported · saved environment/)).toBeTruthy();
    expect(h.api.environmentAction).not.toHaveBeenCalled();
  });

  it('keeps an object edit pending until matching ACK, durable revision and current frame',async()=>{
    vi.useFakeTimers();const h=harness(snapshot('imported')),ready=vi.fn();
    const preview:SceneEditPreview={operation:{operation_id:'move'},preview_digest:'digest',source_revision:'scene-a',parent_revision:'scene-a',result_revision:'scene-b',
      affected_before:{chair_1:{position_m:[1,2,0],dimensions_m:[1,1,1],kind:'chair'}},affected_after:{chair_1:{position_m:[2,2,0],dimensions_m:[1,1,1],kind:'chair'}},preserved_object_count:3,review_required:true,physical_validation:'NOT_RUN'};
    h.api.environmentAction.mockResolvedValue({...snapshot('imported'),preview});h.api.sceneEditTransaction.mockResolvedValue(editTransaction('COMMITTED',false));
    h.api.workflow.mockResolvedValue({...workflow,site_draft:{...workflow.site_draft!,revision:'scene-b'}});
    render(<EnvironmentImport api={h.typed} close={vi.fn()} onReady={ready}/>);
    await act(async()=>{await Promise.resolve();});
    fireEvent.change(screen.getByLabelText('Imported object'),{target:{value:'chair_1'}});
    fireEvent.change(screen.getByLabelText('Space object move X'),{target:{value:'1'}});
    fireEvent.click(screen.getByRole('button',{name:'Preview object move'}));
    await act(async()=>{await Promise.resolve();});
    expect(h.api.environmentAction).toHaveBeenCalledWith(expect.objectContaining({action:'move_preview',object_id:'chair_1',translation_m:[1,0,0],expected_scene_revision:'scene-a'}));
    fireEvent.click(screen.getByRole('button',{name:'Apply space edit'}));
    await act(async()=>{await Promise.resolve();});
    expect(ready).not.toHaveBeenCalled();expect(screen.getByText(/Edit COMMITTED.*Current frame pending/)).toBeTruthy();
    let releaseSnapshot!:(value:EnvironmentState)=>void;
    const nextSnapshot=new Promise<EnvironmentState>(resolve=>{releaseSnapshot=resolve;});
    h.api.sceneEditTransaction.mockResolvedValue(editTransaction());h.api.environment.mockReturnValue(nextSnapshot);
    await act(async()=>{await vi.advanceTimersByTimeAsync(1000);});
    expect(ready).toHaveBeenCalledTimes(1);expect(h.api.applyEnvironmentEdit).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button',{name:'Undo last edit · preview'}).closest('fieldset')).toHaveProperty('disabled',true);
    await act(async()=>{releaseSnapshot({...snapshot('imported'),scene_revision:'scene-b'});await Promise.resolve();});
    expect(screen.queryByRole('button',{name:'Apply space edit'})).toBeNull();
  });
});

const modelPreview:SceneEditPreview={operation:{operation_id:'move'},preview_digest:'model-digest',source_revision:'scene-a',parent_revision:'scene-a',result_revision:'scene-b',
  affected_before:{chair_1:{position_m:[1,2,0],dimensions_m:[1,1,1],kind:'chair'}},affected_after:{chair_1:{position_m:[1.1,2,0],dimensions_m:[1,1,1],kind:'chair'}},preserved_object_count:3,review_required:true,physical_validation:'NOT_RUN'};
describe('model space move suggestions (supplementary UI tests)',()=>{
  const selectRequest=()=>{fireEvent.change(screen.getByLabelText('Imported object'),{target:{value:'chair_1'}});
    fireEvent.change(screen.getByLabelText('Object move request'),{target:{value:'Move 10 cm along X'}});fireEvent.click(screen.getByRole('button',{name:'Suggest move'}));};
  const answer=(request_id:string,status:'running'|'ready'|'failed'='running'):EnvironmentState=>({...snapshot('imported'),proposal:{job_id:'model-job',request_id,status,source_revision:'scene-a',model_id:'nemotron',error:status==='failed'?'Model unavailable':null,...(status==='ready'?{suggestion:{translation_m:[.1,0,0] as [number,number,0],explanation:'Relative move along X'}}:{})}});
  const reviewed=(request:string):EnvironmentState=>{const next=answer(request,'ready');next.preview=modelPreview;next.proposal!.preview=modelPreview;return next;};

  it('polls only GET, sends no geometry and requires a separate Apply with the original ACK/frame gate',async()=>{
    vi.useFakeTimers();const h=harness(snapshot('imported')),ready=vi.fn();let request='';
    h.api.environmentAction.mockImplementation(async body=>{if(body.action==='model_review')return reviewed(request);request=body.request_id;return answer(request);});
    h.api.sceneEditTransaction.mockResolvedValue(editTransaction('COMMITTED',false));
    render(<EnvironmentImport api={h.typed} close={vi.fn()} onReady={ready}/>);await act(async()=>{});selectRequest();await act(async()=>{});
    expect(h.api.environmentAction.mock.calls[0][0]).toEqual({action:'model_move_preview',request_id:expect.any(String),object_id:'chair_1',text:'Move 10 cm along X',expected_scene_revision:'scene-a'});
    expect(screen.getByRole('button',{name:'Suggest move'}).closest('fieldset')).toHaveProperty('disabled',true);
    h.api.environment.mockResolvedValue(answer(request,'ready'));await act(async()=>{await vi.advanceTimersByTimeAsync(1000);});
    expect(screen.getByText(/Move suggestion: ready/)).toBeTruthy();expect(h.api.applyEnvironmentEdit).not.toHaveBeenCalled();
    expect(h.api.environmentAction).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('button',{name:'Apply space edit'})).toBeNull();
    fireEvent.click(screen.getByRole('button',{name:'Review suggestion'}));await act(async()=>{});
    expect(h.api.environmentAction).toHaveBeenLastCalledWith({action:'model_review',request_id:expect.any(String),job_id:'model-job',expected_scene_revision:'scene-a'});
    expect(h.api.applyEnvironmentEdit).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button',{name:'Apply space edit'}));await act(async()=>{});
    expect(h.api.applyEnvironmentEdit).toHaveBeenCalledExactlyOnceWith(modelPreview.operation,'model-digest');
    expect(ready).not.toHaveBeenCalled();expect(screen.getByText(/Current frame pending/)).toBeTruthy();
  });

  it('cancels the owned job and discards an already pending ready response',async()=>{
    vi.useFakeTimers();const h=harness(snapshot('imported'));let request='',finish!:(next:EnvironmentState)=>void;
    h.api.environmentAction.mockImplementation(async body=>{if(body.action==='model_move_preview'){request=body.request_id;return answer(request);}return snapshot('imported');});
    render(<EnvironmentImport api={h.typed} close={vi.fn()} onReady={vi.fn()}/>);await act(async()=>{});selectRequest();await act(async()=>{});
    h.api.environment.mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
    await act(async()=>{await vi.advanceTimersByTimeAsync(1000);});
    fireEvent.click(screen.getByRole('button',{name:'Cancel suggestion'}));await act(async()=>{});
    expect(h.api.environmentAction).toHaveBeenLastCalledWith({action:'model_cancel',request_id:expect.any(String),job_id:'model-job'});
    await act(async()=>{finish(reviewed(request));});
    expect(screen.queryByRole('button',{name:'Apply space edit'})).toBeNull();expect(h.api.applyEnvironmentEdit).not.toHaveBeenCalled();
    await act(async()=>{await vi.advanceTimersByTimeAsync(4000);});expect(h.api.environmentAction).toHaveBeenCalledTimes(2);
  });

  it.each(['scene','source','job','request'] as const)('rejects a ready result with a different %s identity',async changed=>{
    vi.useFakeTimers();const h=harness(snapshot('imported'));let request='';
    h.api.environmentAction.mockImplementation(async body=>{request=body.request_id;return answer(request);});
    render(<EnvironmentImport api={h.typed} close={vi.fn()} onReady={vi.fn()}/>);await act(async()=>{});selectRequest();await act(async()=>{});
    const stale=answer(request,'ready');if(changed==='scene')stale.scene_revision='scene-new';
    else if(changed==='source')stale.proposal!.source_revision='scene-old';else if(changed==='job')stale.proposal!.job_id='other-job';else stale.proposal!.request_id='other-request';
    h.api.environment.mockResolvedValue(stale);await act(async()=>{await vi.advanceTimersByTimeAsync(1000);});
    expect(screen.queryByRole('button',{name:'Apply space edit'})).toBeNull();expect(h.api.applyEnvironmentEdit).not.toHaveBeenCalled();expect(h.api.environmentAction).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('button',{name:'Review suggestion'})).toBeNull();
  });

  it('never repeats a rejected review or requests the model automatically',async()=>{
    const h=harness(snapshot('imported'));let request='';
    h.api.environmentAction.mockImplementation(async body=>{if(body.action==='model_review')throw new Error('Review unavailable');request=body.request_id;return answer(request,'ready');});
    render(<EnvironmentImport api={h.typed} close={vi.fn()} onReady={vi.fn()}/>);await screen.findByRole('button',{name:'Suggest move'});selectRequest();
    fireEvent.click(await screen.findByRole('button',{name:'Review suggestion'}));await screen.findByText('Review unavailable');
    expect(screen.getByRole('button',{name:'Review suggestion'})).toHaveProperty('disabled',true);
    fireEvent.click(screen.getByRole('button',{name:'Review suggestion'}));expect(h.api.environmentAction).toHaveBeenCalledTimes(2);expect(h.api.applyEnvironmentEdit).not.toHaveBeenCalled();
  });

  it('does not retry a failed model request or recover a cancelled preview from saved GET',async()=>{
    vi.useFakeTimers();const h=harness(snapshot('imported'));let request='';
    h.api.environmentAction.mockImplementation(async body=>{request=body.request_id;return answer(request,'failed');});
    render(<EnvironmentImport api={h.typed} close={vi.fn()} onReady={vi.fn()}/>);await act(async()=>{});selectRequest();await act(async()=>{});
    expect(screen.getByRole('alert').textContent).toBe('Model unavailable');
    await act(async()=>{await vi.advanceTimersByTimeAsync(5000);});expect(h.api.environmentAction).toHaveBeenCalledTimes(1);
    fireEvent.change(screen.getByLabelText('Object move request'),{target:{value:'Move 20 cm along X'}});
    h.api.environment.mockResolvedValue(answer(request,'ready'));fireEvent.click(screen.getByRole('button',{name:'Check saved import'}));await act(async()=>{});
    expect(screen.queryByRole('button',{name:'Apply space edit'})).toBeNull();
  });

  it('invalidates a reviewed suggestion when selection changes and preserves manual editing and Undo',async()=>{
    const h=harness(snapshot('imported'));let request='';
    h.api.environmentAction.mockImplementation(async body=>{if(body.action==='model_review')return reviewed(request);request=body.request_id;return answer(request,'ready');});
    render(<EnvironmentImport api={h.typed} close={vi.fn()} onReady={vi.fn()}/>);await screen.findByRole('button',{name:'Suggest move'});
    selectRequest();fireEvent.click(await screen.findByRole('button',{name:'Review suggestion'}));await screen.findByRole('button',{name:'Apply space edit'});
    fireEvent.change(screen.getByLabelText('Imported object'),{target:{value:''}});
    expect(screen.queryByRole('button',{name:'Apply space edit'})).toBeNull();
    h.api.environment.mockResolvedValue(answer(request,'ready'));fireEvent.click(screen.getByRole('button',{name:'Check saved import'}));await act(async()=>{});
    expect(screen.queryByRole('button',{name:'Apply space edit'})).toBeNull();
    expect(screen.getByRole('button',{name:'Undo last edit · preview'})).toHaveProperty('disabled',false);
    expect(screen.getByLabelText('Space object move X')).toHaveProperty('value','0');expect(h.api.applyEnvironmentEdit).not.toHaveBeenCalled();
  });

  it('discards an old project response and does not adopt proposals on cold reopen',async()=>{
    const h=harness(snapshot('imported'));let finish!:(next:EnvironmentState)=>void,request='';
    h.api.environmentAction.mockImplementation(body=>{request=body.request_id;return new Promise(resolve=>{finish=resolve;});});
    const view=render(<EnvironmentImport api={h.typed} close={vi.fn()} onReady={vi.fn()}/>);
    await screen.findByRole('button',{name:'Suggest move'});selectRequest();
    h.api.context='context-b';h.api.environment.mockResolvedValue({...snapshot('imported'),project_id:'other'});
    view.rerender(<EnvironmentImport api={h.typed} close={vi.fn()} onReady={vi.fn()}/>);
    await act(async()=>{finish(answer(request,'ready'));});expect(screen.queryByRole('button',{name:'Apply space edit'})).toBeNull();
    view.unmount();h.api.environment.mockResolvedValue(answer(request,'ready'));
    render(<EnvironmentImport api={h.typed} close={vi.fn()} onReady={vi.fn()}/>);await screen.findByRole('button',{name:'Suggest move'});
    expect(screen.queryByRole('button',{name:'Apply space edit'})).toBeNull();expect(h.api.applyEnvironmentEdit).not.toHaveBeenCalled();
  });
});

describe('space edit transaction transport',()=>{
  it.each([
    ['move preview',(api:TwinPulseApi)=>api.environmentAction({action:'move_preview',request_id:'move',object_id:'chair',translation_m:[.1,0,0],expected_scene_revision:'scene-a'})],
    ['model move suggestion',(api:TwinPulseApi)=>api.environmentAction({action:'model_move_preview',request_id:'model',object_id:'chair',text:'Move 10 cm along X',expected_scene_revision:'scene-a'})],
    ['model cancellation',(api:TwinPulseApi)=>api.environmentAction({action:'model_cancel',request_id:'cancel',job_id:'model-job'})],
    ['model review',(api:TwinPulseApi)=>api.environmentAction({action:'model_review',request_id:'review',job_id:'model-job',expected_scene_revision:'scene-a'})],
    ['Undo preview',(api:TwinPulseApi)=>api.environmentAction({action:'undo_preview',request_id:'undo',expected_scene_revision:'scene-a'})],
    ['Build dispatch',(api:TwinPulseApi)=>api.environmentAction({action:'build',request_id:'build'})],
    ['edit Apply dispatch',(api:TwinPulseApi)=>api.applyEnvironmentEdit({operation_id:'move'},'digest')],
  ] as const)('drains observations for %s and releases them at the initial response',async(_name,submit)=>{
    const response=(body:object)=>({ok:true,status:200,headers:new Headers({'X-TwinPulse-Context':'space-context'}),json:async()=>body}) as Response;
    let finishRead!:(value:Response)=>void,finishMutation!:(value:Response)=>void;
    const request=vi.fn((path:string):Promise<Response>=>{
      if(path==='/v1/product/session')return Promise.resolve(response({csrf_token:'space-csrf',context_id:'space-context',project_id:'room'}));
      if(path==='/v1/product/workflow')return new Promise(resolve=>{finishRead=resolve;});
      if(path.endsWith('/action')||path.endsWith('/apply'))return new Promise(resolve=>{finishMutation=resolve;});
      return Promise.resolve(response({}));
    });
    vi.stubGlobal('fetch',request);const api=new TwinPulseApi();await api.bootstrap();
    const prior=api.workflow(),change=submit(api),next=api.productState();
    await Promise.resolve();expect(finishMutation).toBeUndefined();
    finishRead(response({phase:'draft_ready'}));await prior;
    await waitFor(()=>expect(finishMutation).toBeTypeOf('function'));
    expect(request.mock.calls.some(([path])=>path==='/v1/product/state')).toBe(false);
    finishMutation(response({state:'STAGED'}));await change;await next;
    expect(request.mock.calls.filter(([path])=>path.endsWith('/action')||path.endsWith('/apply'))).toHaveLength(1);
  });

  it('drains prior observations and defers new polls during explicit adoption without replay',async()=>{
    const response=(body:object)=>({ok:true,status:200,headers:new Headers({'X-TwinPulse-Context':'space-context'}),json:async()=>body}) as Response;
    let finishRead!:(value:Response)=>void,finishAdopt!:(value:Response)=>void;
    const request=vi.fn((path:string):Promise<Response>=>{
      if(path==='/v1/product/session')return Promise.resolve(response({csrf_token:'space-csrf',context_id:'space-context',project_id:'room'}));
      if(path==='/v1/product/workflow')return new Promise(resolve=>{finishRead=resolve;});
      if(path==='/v1/product/environment/action')return new Promise(resolve=>{finishAdopt=resolve;});
      return Promise.resolve(response({}));
    });
    vi.stubGlobal('fetch',request);const api=new TwinPulseApi();await api.bootstrap();
    const prior=api.workflow();const adopt=api.environmentAction({action:'adopt',request_id:'adopt-test',job_id:'inspection'});
    const next=api.productState();
    await Promise.resolve();expect(request.mock.calls.some(([path])=>path==='/v1/product/environment/action')).toBe(false);
    finishRead(response({phase:'editing_input'}));await prior;
    await waitFor(()=>expect(request.mock.calls.some(([path])=>path==='/v1/product/environment/action')).toBe(true));
    expect(request.mock.calls.some(([path])=>path==='/v1/product/state')).toBe(false);
    await expect(api.switchProject('other')).rejects.toThrow('already being observed');
    await expect(api.environmentAction({action:'adopt',request_id:'duplicate',job_id:'inspection'})).rejects.toThrow('already being observed');
    finishAdopt(response(snapshot('imported')));await adopt;await next;
    expect(request.mock.calls.filter(([path])=>path==='/v1/product/environment/action')).toHaveLength(1);
    expect(request.mock.calls.some(([path])=>path==='/v1/product/state')).toBe(true);
  });

  it('admits all four image reads after adoption before starting their unchanged delivery timers',async()=>{
    vi.useFakeTimers();
    const response=(body:object)=>({ok:true,status:200,headers:new Headers({'X-TwinPulse-Context':'space-context'}),json:async()=>body}) as Response;
    let finishAdopt!:(value:Response)=>void;
    const request=vi.fn((path:string):Promise<Response>=>{
      if(path==='/v1/product/session')return Promise.resolve(response({csrf_token:'space-csrf',context_id:'space-context',project_id:'room'}));
      if(path==='/v1/product/environment/action')return new Promise(resolve=>{finishAdopt=resolve;});
      const current=path==='/v1/product/viewport/current';
      const headers=new Headers({'X-TwinPulse-Context':'space-context','Content-Type':path.includes('conversation')?'image/png':'image/jpeg'});
      if(current)headers.set('X-TwinPulse-Viewport',JSON.stringify({state:'waiting',physical_authority:false,fps:0,camera_pending:false,camera_result:null,frame:null}));
      return Promise.resolve({ok:true,status:current?204:200,headers,arrayBuffer:async()=>new Uint8Array(current?[]:[1,2,3]).buffer} as Response);
    });
    vi.stubGlobal('fetch',request);const api=new TwinPulseApi();await api.bootstrap();
    const adopt=api.environmentAction({action:'adopt',request_id:'adopt-test',job_id:'inspection'});
    const images=[api.conversationImage('/v1/product/conversation/image/source'),api.viewportPreviewImage('a'.repeat(64)),api.viewportImage(1),api.viewportImageFrame()];
    await vi.advanceTimersByTimeAsync(2500);
    expect(request.mock.calls.filter(([path])=>path.includes('viewport')||path.includes('conversation/image'))).toHaveLength(0);
    finishAdopt(response(snapshot('imported')));await adopt;await Promise.all(images);
    expect(request.mock.calls.filter(([path])=>path.includes('viewport')||path.includes('conversation/image'))).toHaveLength(4);
  });

  it('releases deferred observations after rejected adoption and never retries the mutation',async()=>{
    const response=(body:object,status=200)=>({ok:status===200,status,headers:new Headers({'X-TwinPulse-Context':'space-context'}),json:async()=>body}) as Response;
    const request=vi.fn(async(path:string)=>path==='/v1/product/session'?response({csrf_token:'space-csrf',context_id:'space-context',project_id:'room'}):
      path==='/v1/product/environment/action'?response({error:{code:'review_changed',message:'review changed'}},409):response({phase:'editing_input'}));
    vi.stubGlobal('fetch',request);const api=new TwinPulseApi();await api.bootstrap();
    await expect(api.environmentAction({action:'adopt',request_id:'adopt-test',job_id:'inspection'})).rejects.toThrow('review changed');
    await expect(api.workflow()).resolves.toMatchObject({phase:'editing_input'});
    expect(request.mock.calls.filter(([path])=>path==='/v1/product/environment/action')).toHaveLength(1);
  });

  it('sends the async transaction schema and pinned preview identity, never mesh JSON',async()=>{
    const response=(body:object,status=200)=>({ok:true,status,headers:new Headers({'X-TwinPulse-Context':'space-context'}),json:async()=>body}) as Response;
    const request=vi.fn(async(path:string)=>path==='/v1/product/session'?response({csrf_token:'space-csrf',context_id:'space-context',project_id:'room',project_switch:null}):response({operation_id:'move',state:'PREPARED'},202));
    vi.stubGlobal('fetch',request);const api=new TwinPulseApi();await api.bootstrap();
    const operation={operation_id:'move',parent_revision:'scene-a'};
    await expect(api.applyEnvironmentEdit(operation,'digest')).resolves.toMatchObject({operation_id:'move',state:'PREPARED'});
    expect(request).toHaveBeenCalledWith('/v1/product/scene-edit/apply',expect.objectContaining({method:'POST',body:JSON.stringify({schema_version:'scene-edit-apply-2.0',environment_preview_id:'move',preview_digest:'digest'})}));
    expect(request.mock.calls.filter(([path])=>path==='/v1/product/scene-edit/apply')).toHaveLength(1);
  });
});
