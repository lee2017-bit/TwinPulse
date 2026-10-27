// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {ApiError,TwinPulseApi} from './api';
import {EnvironmentImport} from './EnvironmentImport';
import type {EnvironmentAction,EnvironmentPhotoCandidate,EnvironmentState} from './environment-types';
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
const photoCandidate=(c:Partial<EnvironmentPhotoCandidate>):EnvironmentPhotoCandidate=>({id:'Candidate_1',kind:'basket',label:'Basket candidate',confidence:.8,bbox:[.1,.2,.4,.7],
  description:'Check the photo.',dimensions_m:[.35,.3,.4],dimensions_basis:'catalog_estimate',overlay_kind:'basket',addable:true,possible_duplicates:[],duplicate_check_required:true,...c});
const withPhoto=(...candidates:EnvironmentPhotoCandidate[])=>{const state=snapshot('imported');
  state.objects.push({id:'Added_lidar',category:'unknown',label:'LiDAR unknown #1',position_m:[2,1,.2],dimensions_m:[.3,.3,.4],added:true,
    uncertainty_m:.1,risk:'unknown',evidence:{basis:'lidar_estimate',source_name:'route.json',sha256:'c'.repeat(64),alignment_verified:false}});
  state.photo_proposal={status:'ready',error:null,job_id:'photo-job',model_id:'fake-observer',explanation:'Review estimates.',candidates};return state;};
const sofa=photoCandidate({kind:'sofa',label:'Sofa',dimensions_m:[1.6,.8,.85],overlay_kind:'unknown',possible_duplicates:['Sofa0']});
function editTransaction(state='COMMITTED',frame=true):SceneEditTransaction{return {operation_id:'move',state,engine_acknowledged:true,durable_committed:state==='COMMITTED',current_frame:frame,result_revision:'scene-b',command_id:'command',error:null};}
afterEach(()=>{vi.useRealTimers();vi.unstubAllGlobals();});

describe('local space import',()=>{
  it('offers the chat Undo only with the panel edit controls free and never sends a panel action for it',async()=>{
    const h=harness(withPhoto(sofa)),undo=vi.fn();
    const view=render(<EnvironmentImport api={h.typed} close={vi.fn()} onReady={vi.fn()} undoLastEdit={undo} enabled={false}/>);
    const button=await screen.findByRole('button',{name:'Undo last edit in chat · closes this panel'});expect(button).toHaveProperty('disabled',true);  // e.g. a goal or repeat task owns the scene
    view.rerender(<EnvironmentImport api={h.typed} close={vi.fn()} onReady={vi.fn()} undoLastEdit={undo}/>);
    expect(button).toHaveProperty('disabled',false);fireEvent.click(button);expect(undo).toHaveBeenCalledOnce();expect(h.api.environmentAction).not.toHaveBeenCalled();
    view.rerender(<EnvironmentImport api={h.typed} close={vi.fn()} onReady={vi.fn()}/>);
    expect(screen.queryByRole('button',{name:'Undo last edit in chat · closes this panel'})).toBeNull();  // no committed edit, no Undo
  });
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
        dimensions_m:[.35,.3,.4],dimensions_basis:'catalog_estimate',overlay_kind:'basket',addable:true,possible_duplicates:[],duplicate_check_required:true}]};
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
  it('reviews a furniture candidate as a labelled unknown box with a duplicate hint and no Replace',async()=>{
    const h=harness(withPhoto(sofa));
    h.api.environmentAction.mockRejectedValueOnce(new ApiError('invalid_request','ENVIRONMENT_OVERLAY_OUTSIDE_FLOOR'));
    render(<EnvironmentImport api={h.typed} close={vi.fn()} onReady={vi.fn()}/>);
    await screen.findByText('Added obstacles · 1');fireEvent.click(screen.getByText('Added obstacles · 1'));
    expect(screen.getByText(/Possible duplicate of: Sofa0/)).toBeTruthy();expect(screen.getByText(/Added as a labelled box \(unknown kind, catalog size\)/)).toBeTruthy();
    expect(screen.getByText(/Against a wall: keep the center at least half the depth \+ 0\.15 m away/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'Review Candidate_1'}));
    expect(screen.getByLabelText('Obstacle type')).toHaveProperty('value','unknown');expect(screen.getByLabelText('Obstacle name')).toHaveProperty('value','Sofa');
    expect(screen.getByLabelText('Obstacle width')).toHaveProperty('value','1.6');expect(screen.getByLabelText('Obstacle uncertainty')).toHaveProperty('value','.05');
    expect(screen.queryByLabelText('Replace LiDAR unknown box')).toBeNull();
    const button=()=>screen.getByRole('button',{name:'Preview obstacle'});expect(button()).toHaveProperty('disabled',true);
    fireEvent.change(screen.getByLabelText('Obstacle X'),{target:{value:'1.3'}});expect(button()).toHaveProperty('disabled',true);
    fireEvent.change(screen.getByLabelText('Obstacle Y'),{target:{value:'.4'}});expect(button()).toHaveProperty('disabled',true);
    fireEvent.click(screen.getByLabelText('Candidate duplicate reviewed'));expect(button()).toHaveProperty('disabled',false);
    fireEvent.click(button());
    expect(await screen.findByText('Outside the scanned floor. Against a wall: keep the center at least half the depth + 0.15 m away.')).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Obstacle Y'),{target:{value:'1'}});fireEvent.click(button());
    await waitFor(()=>expect(h.api.environmentAction).toHaveBeenCalledTimes(2));
    expect(h.api.environmentAction).toHaveBeenLastCalledWith(expect.objectContaining({action:'photo_candidate_preview',duplicate_reviewed:true,
      candidate_ref:{job_id:'photo-job',candidate_id:'Candidate_1'},obstacle:{kind:'unknown',label:'Sofa',position_xy_m:[1.3,1],dimensions_m:[1.6,.8,.85],yaw_deg:0,uncertainty_m:.05}}));
    expect(h.api.environmentAction.mock.calls[1][0]).not.toHaveProperty('replace_object_id');expect(h.api.applyEnvironmentEdit).not.toHaveBeenCalled();
  });
  it('keeps Replace for a same-kind candidate and disables Review for a recognised-only object',async()=>{
    const blind=photoCandidate({id:'Candidate_2',kind:'window_blind',label:'Blind',dimensions_m:[.8,.08,.8],overlay_kind:null,addable:false});
    const h=harness(withPhoto(photoCandidate({}),blind));render(<EnvironmentImport api={h.typed} close={vi.fn()} onReady={vi.fn()}/>);
    await screen.findByText('Added obstacles · 1');fireEvent.click(screen.getByText('Added obstacles · 1'));
    expect(screen.getByRole('button',{name:'Review Candidate_2'})).toHaveProperty('disabled',true);expect(screen.getByText(/Recognised only/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'Review Candidate_1'}));
    expect(screen.getByLabelText('Obstacle type')).toHaveProperty('value','basket');expect(screen.getByLabelText('Obstacle uncertainty')).toHaveProperty('value','.2');
    expect(screen.getByLabelText('Replace LiDAR unknown box')).toBeTruthy();expect(h.api.environmentAction).not.toHaveBeenCalled();
  });
  it('restores the default uncertainty after a furniture review unless the user typed one',async()=>{
    const h=harness(withPhoto(sofa,photoCandidate({id:'Candidate_2'})));render(<EnvironmentImport api={h.typed} close={vi.fn()} onReady={vi.fn()}/>);
    await screen.findByText('Added obstacles · 1');fireEvent.click(screen.getByText('Added obstacles · 1'));
    const margin=()=>screen.getByLabelText('Obstacle uncertainty'),review=(id:string)=>fireEvent.click(screen.getByRole('button',{name:'Review '+id})),
      manual=()=>fireEvent.click(screen.getByRole('button',{name:'Use manual entry'}));
    review('Candidate_1');expect(margin()).toHaveProperty('value','.05');manual();expect(margin()).toHaveProperty('value','.2');
    review('Candidate_1');fireEvent.change(screen.getByLabelText('Obstacle type'),{target:{value:'bag'}});expect(margin()).toHaveProperty('value','.2');
    review('Candidate_1');review('Candidate_2');expect(margin()).toHaveProperty('value','.2');
    review('Candidate_1');fireEvent.change(margin(),{target:{value:'.1'}});manual();expect(margin()).toHaveProperty('value','.1');
    review('Candidate_2');expect(margin()).toHaveProperty('value','.1');
    // Sofa from the photo, then a manual basket: the basket keeps the default margin.
    review('Candidate_1');manual();fireEvent.change(screen.getByLabelText('Obstacle type'),{target:{value:'basket'}});
    fireEvent.change(screen.getByLabelText('Obstacle X'),{target:{value:'1.3'}});fireEvent.change(screen.getByLabelText('Obstacle Y'),{target:{value:'1'}});
    fireEvent.click(screen.getByRole('button',{name:'Preview obstacle'}));
    await waitFor(()=>expect(h.api.environmentAction).toHaveBeenCalledTimes(1));
    expect(h.api.environmentAction).toHaveBeenCalledWith(expect.objectContaining({action:'add_overlay_preview',obstacle:expect.objectContaining({kind:'basket',uncertainty_m:.2})}));
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
    expect(screen.getByText(/User-selected units are uncalibrated\. Measured scale is not verified/)).toBeTruthy();
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

describe('Twin-edit auto-apply',()=>{
  it('applies a previewed obstacle through the normal Apply path once, and never without the setting',async()=>{
    const preview={operation:{operation_id:'op-1'},preview_digest:'d',result_revision:'scene-b',affected_before:{},affected_after:{Added_x:{position_m:[1,1,.15]}},preserved_object_count:1} as unknown as SceneEditPreview;
    const state={...snapshot('imported'),objects:[]};
    for(const auto of [false,true]){
      const h=harness(state);h.api.environmentAction=vi.fn(async(_body:EnvironmentAction)=>({...state,preview}));
      const view=render(<EnvironmentImport api={h.typed} close={vi.fn()} onReady={vi.fn()} autoApply={auto}/>);
      await screen.findByRole('button',{name:'Preview obstacle'});
      fireEvent.change(screen.getByLabelText('Obstacle X'),{target:{value:'1'}});fireEvent.change(screen.getByLabelText('Obstacle Y'),{target:{value:'1'}});
      fireEvent.click(screen.getByRole('button',{name:'Preview obstacle'}));
      await screen.findByRole('button',{name:'Apply space edit'});
      if(auto){await waitFor(()=>expect(h.api.applyEnvironmentEdit).toHaveBeenCalledTimes(1));await act(async()=>{});expect(h.api.applyEnvironmentEdit).toHaveBeenCalledTimes(1);}  // once, not on every render
      else{await act(async()=>{});expect(h.api.applyEnvironmentEdit).not.toHaveBeenCalled();}
      view.unmount();
    }
  });
  it('applies a reviewed furniture photo preview once, only after Review, placement, duplicate check and Preview',async()=>{
    const preview={operation:{operation_id:'op-photo'},preview_digest:'d',result_revision:'scene-b',affected_before:{},affected_after:{Added_x:{position_m:[1.3,1,.425]}},preserved_object_count:1} as unknown as SceneEditPreview;
    const state=withPhoto(sofa),h=harness(state);h.api.environmentAction=vi.fn(async(_body:EnvironmentAction)=>({...state,preview}));
    render(<EnvironmentImport api={h.typed} close={vi.fn()} onReady={vi.fn()} autoApply/>);
    await screen.findByText('Added obstacles · 1');fireEvent.click(screen.getByText('Added obstacles · 1'));
    fireEvent.click(screen.getByRole('button',{name:'Review Candidate_1'}));
    fireEvent.change(screen.getByLabelText('Obstacle X'),{target:{value:'1.3'}});fireEvent.change(screen.getByLabelText('Obstacle Y'),{target:{value:'1'}});
    fireEvent.click(screen.getByLabelText('Candidate duplicate reviewed'));await act(async()=>{});
    expect(h.api.environmentAction).not.toHaveBeenCalled();expect(h.api.applyEnvironmentEdit).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button',{name:'Preview obstacle'}));
    await waitFor(()=>expect(h.api.applyEnvironmentEdit).toHaveBeenCalledTimes(1));await act(async()=>{});
    expect(h.api.applyEnvironmentEdit).toHaveBeenCalledTimes(1);expect(h.api.applyEnvironmentEdit).toHaveBeenCalledWith(preview.operation,'d');
    expect(h.api.environmentAction).toHaveBeenCalledTimes(1);
  });
});

describe('photo candidates placed beside their named neighbour',()=>{
  const placement=(x:number,y:number,anchor='Sofa0',yaw=30,margin=.3)=>({position_m:[x,y,.2] as [number,number,number],yaw_deg:yaw,dimensions_m:[.35,.3,.4] as [number,number,number],uncertainty_m:margin,
    anchor,gap_m:.05,side:'+x',at_end:true,basis:'photo_near_anchor' as const,alignment_verified:false as const,envelope_xy:[[x-.475,y-.45],[x+.475,y-.45],[x+.475,y+.45],[x-.475,y+.45]] as [number,number][]});
  const basket=(id:string,x:number,y:number,more:Partial<EnvironmentPhotoCandidate>={})=>photoCandidate({id,label:'Basket '+id.slice(-1),near:'Sofa0',suggested:placement(x,y),suggestion_reason:null,batch_addable:true,...more});
  const rows=()=>[basket('Candidate_1',1.8,1.8),basket('Candidate_2',2.7,1.8),
    photoCandidate({id:'Candidate_3',kind:'office_chair',label:'Desk chair',overlay_kind:'unknown',dimensions_m:[.6,.6,.9],possible_duplicates:['Chair0'],near:'Chair0',suggested:null,suggestion_reason:'POSSIBLE_DUPLICATE',batch_addable:false}),
    photoCandidate({id:'Candidate_4',label:'Loose basket',near:null,suggested:null,suggestion_reason:'NO_ANCHOR',batch_addable:false})];
  const withRows=(candidates:EnvironmentPhotoCandidate[])=>{const state=withPhoto(...candidates);state.floor_triangles_xy=[[[0,0],[4,0],[4,3]],[[0,0],[4,3],[0,3]]];return state;};
  const open=async()=>{await screen.findByText('Added obstacles · 1');fireEvent.click(screen.getByText('Added obstacles · 1'));};
  const previews=(h:ReturnType<typeof harness>)=>h.api.environmentAction.mock.calls.map(([body])=>body).flatMap(body=>body.action==='photo_candidate_preview'?
    [[body.candidate_ref.candidate_id,body.obstacle.position_xy_m,body.obstacle.yaw_deg,body.expected_scene_revision,body.duplicate_reviewed]]:[]);
  const disabled=(name:string)=>screen.getByRole('button',{name}).matches(':disabled');
  // A scene whose revision advances on each committed edit, through the same preview/Apply/transaction API as one Review.
  // later(n) gives the candidates the server recomputes after n commits; refuse/rollback name the n-th preview.
  function scene({refuse,rollback,later=rows}:{refuse?:number;rollback?:number;later?:(committed:number)=>EnvironmentPhotoCandidate[]}={}){
    const h=harness(withRows(rows()));let revision='scene-a',n=0,committed=0,applied:SceneEditPreview|null=null;
    const now=():EnvironmentState=>({...withRows(later(committed)),scene_revision:revision});
    h.api.environment.mockImplementation(async()=>now());h.api.workflow.mockImplementation(async()=>({...workflow,site_draft:{revision}}) as WorkflowState);
    h.api.environmentAction.mockImplementation(async body=>{if(body.action!=='photo_candidate_preview')return now();n++;
      if(n===refuse)throw new ApiError('invalid_request','PHOTO_CANDIDATE_ALREADY_REPRESENTED');
      const preview={operation:{operation_id:'op-'+n},preview_digest:'d'+n,source_revision:revision,parent_revision:revision,result_revision:'scene-'+n,
        affected_before:{},affected_after:{['Added_'+n]:{position_m:[...body.obstacle.position_xy_m,.2],dimensions_m:body.obstacle.dimensions_m,kind:'basket'}},
        preserved_object_count:2,review_required:true,physical_validation:'NOT_RUN'} as SceneEditPreview;applied=preview;return {...now(),preview};});
    h.api.applyEnvironmentEdit.mockImplementation(async operation=>({...editTransaction('DISPATCHED',false),operation_id:String(operation.operation_id)}));
    h.api.sceneEditTransaction.mockImplementation(async()=>{if(!applied)return null as unknown as SceneEditTransaction;const id=String(applied.operation.operation_id);
      if(id==='op-'+rollback)return {...editTransaction('ROLLED_BACK'),operation_id:id,engine_acknowledged:false,result_revision:null,error:'Engine NACK'} as unknown as SceneEditTransaction;
      if(revision!==applied.result_revision){revision=applied.result_revision;committed++;}
      return {...editTransaction(),operation_id:id,result_revision:applied.result_revision};});
    return h;
  }
  it('pre-fills the suggested center, yaw and uncertainty on Review, draws it, and still needs the duplicate check',async()=>{
    const h=harness(withRows(rows()));render(<EnvironmentImport api={h.typed} close={vi.fn()} onReady={vi.fn()}/>);await open();
    expect(screen.getAllByText(/Suggested: next to Sofa0 · at its end · 0\.05 m gap · estimate \(the side is a guess\)/)).toHaveLength(2);
    expect([...document.querySelectorAll('svg polygon[stroke-dasharray] title')].map(t=>t.textContent)).toEqual(['Candidate_1 · suggested next to Sofa0 · estimate','Candidate_2 · suggested next to Sofa0 · estimate']);
    fireEvent.click(screen.getByRole('button',{name:'Review Candidate_1'}));
    expect(screen.getByLabelText('Obstacle X')).toHaveProperty('value','1.8');expect(screen.getByLabelText('Obstacle Y')).toHaveProperty('value','1.8');
    expect(screen.getByLabelText('Obstacle yaw')).toHaveProperty('value','30');expect(screen.getByLabelText('Obstacle uncertainty')).toHaveProperty('value','0.3');
    expect(screen.getByText(/Placed next to Sofa0 from the photo \(estimate; the side is a guess\) · click the map or edit X\/Y to adjust; the robot LiDAR corrects offsets up to 0\.6 m, not a wrong side\./)).toBeTruthy();
    expect(disabled('Preview obstacle')).toBe(true);
    fireEvent.click(screen.getByLabelText('Candidate duplicate reviewed'));fireEvent.click(screen.getByRole('button',{name:'Preview obstacle'}));
    await waitFor(()=>expect(h.api.environmentAction).toHaveBeenCalledWith(expect.objectContaining({action:'photo_candidate_preview',candidate_ref:{job_id:'photo-job',candidate_id:'Candidate_1'},
      obstacle:{kind:'basket',label:'Basket 1',position_xy_m:[1.8,1.8],dimensions_m:[.35,.3,.4],yaw_deg:30,uncertainty_m:.3}})));
    expect(h.api.applyEnvironmentEdit).not.toHaveBeenCalled();
  });
  it('keeps manual entry with the reason when a candidate has no suggestion',async()=>{
    const h=harness(withRows(rows()));render(<EnvironmentImport api={h.typed} close={vi.fn()} onReady={vi.fn()}/>);await open();
    expect(screen.getByText(/No suggested spot: the photo model named no neighbouring scanned or added object\. Place the center on the map\./)).toBeTruthy();
    expect(screen.getByText(/No suggested spot: it may already be one of the possible duplicates above/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'Review Candidate_4'}));
    expect(screen.getByLabelText('Obstacle X')).toHaveProperty('value','');expect(screen.getByText(/Reviewing Candidate_4 · set the center on the map\./)).toBeTruthy();
    expect(disabled('Preview obstacle')).toBe(true);
  });
  it('adds the batch-safe suggestions one at a time and waits for each Apply when auto-apply is off',async()=>{
    const h=scene(),ready=vi.fn();render(<EnvironmentImport api={h.typed} close={vi.fn()} onReady={ready}/>);await open();
    expect(disabled('Add 2 suggested objects')).toBe(true);  // Desk chair may be Chair0; Candidate_4 has no spot
    expect(screen.getByText(/Each one opens its own preview in order; check it and Apply space edit to continue/)).toBeTruthy();
    fireEvent.click(screen.getByLabelText('Suggested objects duplicate reviewed'));fireEvent.click(screen.getByRole('button',{name:'Add 2 suggested objects'}));
    await screen.findByText('Candidate_1: 1 of 2 · check the preview, then Apply space edit to continue or Cancel to stop.');
    await act(async()=>{});expect(h.api.applyEnvironmentEdit).not.toHaveBeenCalled();
    // Nothing else can start an edit while the batch runs.
    for(const name of ['Review Candidate_2','Preview obstacle','Preview object move','Undo last edit · preview'])expect(disabled(name)).toBe(true);
    fireEvent.click(screen.getByRole('button',{name:'Apply space edit'}));
    await screen.findByText('Candidate_2: 2 of 2 · check the preview, then Apply space edit to continue or Cancel to stop.');
    expect(h.api.applyEnvironmentEdit).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button',{name:'Apply space edit'}));
    await screen.findByText('Added 2 suggested objects. Positions are estimates; the robot LiDAR corrects small offsets.');
    expect(previews(h)).toEqual([['Candidate_1',[1.8,1.8],30,'scene-a',true],['Candidate_2',[2.7,1.8],30,'scene-1',true]]);
    expect(h.api.applyEnvironmentEdit.mock.calls.map(([operation,digest])=>[operation.operation_id,digest])).toEqual([['op-1','d1'],['op-2','d2']]);
    expect(ready).toHaveBeenCalledTimes(2);
  });
  it('cancelling a batch preview stops the batch without applying it',async()=>{
    const h=scene();render(<EnvironmentImport api={h.typed} close={vi.fn()} onReady={vi.fn()}/>);await open();
    fireEvent.click(screen.getByLabelText('Suggested objects duplicate reviewed'));fireEvent.click(screen.getByRole('button',{name:'Add 2 suggested objects'}));
    await screen.findByRole('button',{name:'Apply space edit'});fireEvent.click(screen.getByRole('button',{name:'Cancel space edit'}));
    await screen.findByText('Stopped at Candidate_1 after 0 added: not applied (preview cancelled)');
    expect(previews(h)).toHaveLength(1);expect(h.api.applyEnvironmentEdit).not.toHaveBeenCalled();
  });
  it('with auto-apply on, stops at the first refused candidate and never previews the rest',async()=>{
    const h=scene({refuse:2,later:()=>[...rows().slice(0,2),basket('Candidate_3',3.4,1.8)]});
    render(<EnvironmentImport api={h.typed} close={vi.fn()} onReady={vi.fn()} autoApply/>);await open();
    fireEvent.click(screen.getByLabelText('Suggested objects duplicate reviewed'));fireEvent.click(screen.getByRole('button',{name:'Add 3 suggested objects'}));
    await screen.findByText('Stopped at Candidate_2 after 1 added: PHOTO_CANDIDATE_ALREADY_REPRESENTED');
    await act(async()=>{});
    expect(previews(h).map(row=>row[0])).toEqual(['Candidate_1','Candidate_2']);expect(h.api.applyEnvironmentEdit).toHaveBeenCalledTimes(1);
  });
  it('stops when an applied edit rolls back instead of counting it',async()=>{
    const h=scene({rollback:1}),ready=vi.fn();render(<EnvironmentImport api={h.typed} close={vi.fn()} onReady={ready} autoApply/>);await open();
    fireEvent.click(screen.getByLabelText('Suggested objects duplicate reviewed'));fireEvent.click(screen.getByRole('button',{name:'Add 2 suggested objects'}));
    await screen.findByText('Stopped at Candidate_1 after 0 added: Engine NACK',{},{timeout:3000});
    expect(previews(h)).toHaveLength(1);expect(h.api.applyEnvironmentEdit).toHaveBeenCalledTimes(1);expect(ready).not.toHaveBeenCalled();
  });
  it('keeps the chat Undo locked during an "Add N suggested objects" batch and while a photo analysis runs',async()=>{
    // The panel's own edit locks also hold the chat Undo it offers after a committed edit (2026-10-27 review).
    const h=scene(),undo=vi.fn(),view=render(<EnvironmentImport api={h.typed} close={vi.fn()} onReady={vi.fn()} undoLastEdit={undo}/>);await open();
    expect(disabled('Undo last edit in chat · closes this panel')).toBe(false);
    fireEvent.click(screen.getByLabelText('Suggested objects duplicate reviewed'));fireEvent.click(screen.getByRole('button',{name:'Add 2 suggested objects'}));
    await screen.findByText('Candidate_1: 1 of 2 · check the preview, then Apply space edit to continue or Cancel to stop.');
    expect(disabled('Undo last edit in chat · closes this panel')).toBe(true);view.unmount();
    const analyzing=withRows([]);analyzing.photo_proposal={status:'running',error:null,job_id:'photo-job',model_id:'fake-observer',explanation:null,candidates:[]};
    render(<EnvironmentImport api={harness(analyzing).typed} close={vi.fn()} onReady={vi.fn()} undoLastEdit={undo}/>);
    await screen.findByText('Space imported · saved environment.');expect(disabled('Undo last edit in chat · closes this panel')).toBe(true);
    expect(undo).not.toHaveBeenCalled();
  });
  it('uses the suggestion the server recomputes after each commit, and stops when it is no longer batch-safe',async()=>{
    const moved=scene({later:committed=>committed?[rows()[0],basket('Candidate_2',3.1,1.7)]:rows()});
    const view=render(<EnvironmentImport api={moved.typed} close={vi.fn()} onReady={vi.fn()} autoApply/>);await open();
    fireEvent.click(screen.getByLabelText('Suggested objects duplicate reviewed'));fireEvent.click(screen.getByRole('button',{name:'Add 2 suggested objects'}));
    await screen.findByText(/^Added 2 suggested objects/);
    expect(previews(moved).map(row=>row.slice(0,2))).toEqual([['Candidate_1',[1.8,1.8]],['Candidate_2',[3.1,1.7]]]);
    view.unmount();
    const unsafe=scene({later:committed=>committed?[rows()[0],basket('Candidate_2',2.7,1.8,{suggestion_reason:'POSSIBLE_DUPLICATE',batch_addable:false,possible_duplicates:['Other basket']})]:rows()});
    render(<EnvironmentImport api={unsafe.typed} close={vi.fn()} onReady={vi.fn()} autoApply/>);await open();
    fireEvent.click(screen.getByLabelText('Suggested objects duplicate reviewed'));fireEvent.click(screen.getByRole('button',{name:'Add 2 suggested objects'}));
    await screen.findByText('Stopped at Candidate_2 after 1 added: POSSIBLE_DUPLICATE');
    expect(previews(unsafe).map(row=>row[0])).toEqual(['Candidate_1']);expect(unsafe.api.applyEnvironmentEdit).toHaveBeenCalledTimes(1);
  });
});
