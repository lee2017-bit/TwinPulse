// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {ApiError,type TwinPulseApi} from './api';
import {LibraryWorkspace,toolInputs} from './LibraryWorkspace';
import type {LibraryJob,LibraryPlacementPreview,LibraryWorkspaceAction,LibraryWorkspaceState} from './library-workspace-types';
import type {SceneEditTransaction,WorkflowState} from './types';

const empty=():LibraryWorkspaceState=>({schema_version:'library-workspace-1.0',project_id:'room',current_scene_revision:'scene-a',assets:[],jobs:[],extensions:[]});
const job=(status:LibraryJob['status']='ready'):LibraryJob=>({job_id:'job',project_id:'room',request_id:'request',purpose:'asset_create',status,phase:'validation',message:'Recipe geometry checked',tool_id:'recipe',execution_id:'execution',input_sha256:'a'.repeat(64),created_at:'now',can_cancel:status==='running',can_register:status==='ready',error:null});
const savedAsset={asset_id:'chair',version:'a'.repeat(64),title:'Saved chair',kind:'recipe' as const,source_name:'recipe.json',source_sha256:'b'.repeat(64),dimensions_m:[.5,.5,.9] as [number,number,number],units:'m' as const,up_axis:'Z' as const,origin:'self-created',license:'User original',visual_status:'checked',physics_status:'geometry only',reusable:true};
const placement:LibraryPlacementPreview={preview_id:'saved-preview',operation:{operation_id:'placement',asset_version:savedAsset.version,position_m:[1,0,0]},preview_digest:'digest',source_revision:'scene-a',parent_revision:'scene-a',result_revision:'scene-b',affected_before:{},affected_after:{chair_1:{position_m:[0,0,0],dimensions_m:[.5,.5,.9],kind:'chair'}},preserved_object_count:3,review_required:true,physical_validation:'NOT_RUN'};
const placementTransaction=(state='COMMITTED',frame=true):SceneEditTransaction=>({operation_id:'placement',state,engine_acknowledged:true,durable_committed:state==='COMMITTED',current_frame:frame,error:null,command_id:'command',before_revision:'scene-a',result_revision:'scene-b'});
function localFile(name:string,type:string,text='file bytes'){
  const file=new File([text],name,{type});Object.defineProperty(file,'arrayBuffer',{value:async()=>new TextEncoder().encode(text).buffer,configurable:true});return file;
}
function harness(state=empty()){
  const api={context:'context-a',libraryWorkspace:vi.fn(async()=>state),libraryWorkspaceAction:vi.fn(async(_body:LibraryWorkspaceAction)=>state),applySceneEdit:vi.fn(async()=>({phase:'draft_ready'})),
    applyLibraryPlacement:vi.fn(async(_id:string,_digest:string)=>placementTransaction('DISPATCHED',false)),sceneEditTransaction:vi.fn<()=>Promise<SceneEditTransaction|null>>(async()=>placementTransaction()),workflow:vi.fn(async()=>({phase:'draft_ready',site_draft:{revision:'scene-b'}} as WorkflowState))};
  return {state,api,typed:api as unknown as TwinPulseApi};
}
async function placementView(h:ReturnType<typeof harness>,applied=vi.fn()){
  h.api.libraryWorkspaceAction.mockResolvedValue({...h.state,placement_preview:placement});
  const view=render(<LibraryWorkspace api={h.typed} tab="assets" sceneRevision="scene-a" onSceneApplied={applied}/>);
  fireEvent.click(await screen.findByRole('button',{name:/Saved chair/}));
  fireEvent.click(screen.getByRole('button',{name:'Preview asset placement'}));
  await screen.findByRole('button',{name:'Apply asset placement'});return {view,applied};
}
describe('purpose-bound Library workspace',()=>{
  afterEach(()=>vi.useRealTimers());
  it.each(['timeout','transport'])('rechecks one transient initial %s read after 400ms without claiming an empty Library',async kind=>{
    vi.useFakeTimers();const h=harness({...empty(),assets:[savedAsset]});
    h.api.libraryWorkspace.mockRejectedValueOnce(kind==='timeout'?new ApiError('state_read_timeout','Local state read exceeded 3 seconds.'):new TypeError('Failed to fetch'));
    const view=render(<LibraryWorkspace api={h.typed} tab="assets"/>);
    await act(async()=>{await Promise.resolve();});
    expect(screen.getByText(/Rechecking saved Library assets · read only/)).toBeTruthy();
    expect(screen.queryByText(/No registered assets yet/)).toBeNull();
    await act(async()=>{await vi.advanceTimersByTimeAsync(399);});expect(h.api.libraryWorkspace).toHaveBeenCalledTimes(1);
    await act(async()=>{await vi.advanceTimersByTimeAsync(1);});expect(h.api.libraryWorkspace).toHaveBeenCalledTimes(2);
    expect(screen.getByRole('button',{name:/Saved chair/})).toBeTruthy();expect(screen.queryByRole('alert')).toBeNull();
    await act(async()=>{await vi.advanceTimersByTimeAsync(5000);});expect(h.api.libraryWorkspace).toHaveBeenCalledTimes(2);
    expect(h.api.libraryWorkspaceAction).not.toHaveBeenCalled();expect(h.api.applyLibraryPlacement).not.toHaveBeenCalled();view.unmount();
  });
  it('stops after one failed cold-read retry and retains explicit read-only recovery',async()=>{
    vi.useFakeTimers();const h=harness({...empty(),assets:[savedAsset]});
    h.api.libraryWorkspace.mockRejectedValue(new ApiError('state_read_timeout','Read timed out'));
    const view=render(<LibraryWorkspace api={h.typed} tab="assets"/>);
    await act(async()=>{await vi.advanceTimersByTimeAsync(400);});
    expect(h.api.libraryWorkspace).toHaveBeenCalledTimes(2);expect(screen.getByRole('alert').textContent).toBe('Read timed out');
    expect(screen.getByText(/Library assets could not be read/)).toBeTruthy();expect(screen.queryByText(/No registered assets yet/)).toBeNull();
    await act(async()=>{await vi.advanceTimersByTimeAsync(5000);});expect(h.api.libraryWorkspace).toHaveBeenCalledTimes(2);
    h.api.libraryWorkspace.mockResolvedValue(h.state);
    await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'Check saved Library results · read only'}));});
    expect(screen.getByRole('button',{name:/Saved chair/})).toBeTruthy();expect(screen.queryByRole('alert')).toBeNull();
    expect(h.api.libraryWorkspace).toHaveBeenCalledTimes(3);expect(h.api.libraryWorkspaceAction).not.toHaveBeenCalled();view.unmount();
  });
  it.each([
    new ApiError('csrf_rejected','Forbidden'),new ApiError('host_forbidden','Forbidden'),
    new ApiError('session_reopen_required','Reopen session'),new ApiError('context_changed','Context changed'),
    new ApiError('project_context_changed','Project context changed'),new ApiError('request_failed','Unknown HTTP failure'),
    new SyntaxError('Invalid JSON protocol response'),new TypeError('Cannot read properties of undefined'),
  ])('never retries a non-transient initial read error %s',async error=>{
    vi.useFakeTimers();const h=harness();h.api.libraryWorkspace.mockRejectedValue(error);
    const view=render(<LibraryWorkspace api={h.typed} tab="assets"/>);
    await act(async()=>{await vi.advanceTimersByTimeAsync(5000);});
    expect(h.api.libraryWorkspace).toHaveBeenCalledTimes(1);expect(screen.getByRole('alert').textContent).toBe(error.message);
    expect(screen.queryByText(/No registered assets yet/)).toBeNull();
    expect(screen.getByRole('button',{name:'Check saved Library results · read only'})).toHaveProperty('disabled',false);
    expect(h.api.libraryWorkspaceAction).not.toHaveBeenCalled();view.unmount();
  });
  it.each(['close','context'])('cancels the scheduled cold-read retry on %s',async reason=>{
    vi.useFakeTimers();const h=harness({...empty(),assets:[savedAsset]});
    h.api.libraryWorkspace.mockRejectedValueOnce(new ApiError('state_read_timeout','Read timed out'));
    const view=render(<LibraryWorkspace api={h.typed} tab="assets"/>);
    await act(async()=>{await Promise.resolve();});expect(screen.getByText(/Rechecking saved Library assets/)).toBeTruthy();
    if(reason==='close')view.unmount();
    else{h.api.context='context-b';view.rerender(<LibraryWorkspace api={h.typed} tab="assets"/>);}
    await act(async()=>{await vi.advanceTimersByTimeAsync(1000);});
    expect(h.api.libraryWorkspace).toHaveBeenCalledTimes(reason==='close'?1:2);
    expect(h.api.libraryWorkspaceAction).not.toHaveBeenCalled();view.unmount();
  });
  it('does not send the scheduled automatic GET after an explicit read recovers during its delay',async()=>{
    vi.useFakeTimers();const h=harness({...empty(),assets:[savedAsset]});
    h.api.libraryWorkspace.mockRejectedValueOnce(new ApiError('state_read_timeout','Initial read timed out'));
    const view=render(<LibraryWorkspace api={h.typed} tab="assets"/>);
    await act(async()=>{await Promise.resolve();});expect(screen.getByText(/Rechecking saved Library assets/)).toBeTruthy();
    await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'Check saved Library results · read only'}));});
    await act(async()=>{await vi.advanceTimersByTimeAsync(1000);});
    expect(screen.getByRole('button',{name:/Saved chair/})).toBeTruthy();expect(h.api.libraryWorkspace).toHaveBeenCalledTimes(2);
    expect(h.api.libraryWorkspaceAction).not.toHaveBeenCalled();view.unmount();
  });
  it.each(['resolve','reject'])('discards an initial read %s after context A → B → A',async outcome=>{
    vi.useFakeTimers();const h=harness({...empty(),assets:[savedAsset]});
    let resolve!:(value:LibraryWorkspaceState)=>void,reject!:(error:Error)=>void;
    h.api.libraryWorkspace.mockImplementationOnce(()=>new Promise((done,fail)=>{resolve=done;reject=fail;}));
    const view=render(<LibraryWorkspace api={h.typed} tab="assets"/>);
    h.api.context='context-b';view.rerender(<LibraryWorkspace api={h.typed} tab="assets"/>);
    await act(async()=>{await Promise.resolve();});
    h.api.context='context-a';view.rerender(<LibraryWorkspace api={h.typed} tab="assets"/>);
    await act(async()=>{await Promise.resolve();});
    await act(async()=>{if(outcome==='resolve')resolve(empty());else reject(new ApiError('state_read_timeout','Old context timeout'));await vi.advanceTimersByTimeAsync(1000);});
    expect(screen.getByRole('button',{name:/Saved chair/})).toBeTruthy();expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.queryByText(/No registered assets yet/)).toBeNull();expect(h.api.libraryWorkspace).toHaveBeenCalledTimes(3);view.unmount();
  });
  it.each(['resolve','reject'])('ignores an older initial read %s after a newer explicit read succeeds',async outcome=>{
    vi.useFakeTimers();const h=harness({...empty(),assets:[savedAsset]});
    let resolve!:(value:LibraryWorkspaceState)=>void,reject!:(error:Error)=>void;
    h.api.libraryWorkspace.mockImplementationOnce(()=>new Promise((done,fail)=>{resolve=done;reject=fail;}));
    const view=render(<LibraryWorkspace api={h.typed} tab="assets"/>);
    await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'Check saved Library results · read only'}));});
    await act(async()=>{if(outcome==='resolve')resolve(empty());else reject(new ApiError('state_read_timeout','Old read timeout'));await vi.advanceTimersByTimeAsync(1000);});
    expect(screen.getByRole('button',{name:/Saved chair/})).toBeTruthy();expect(screen.queryByRole('alert')).toBeNull();
    expect(h.api.libraryWorkspace).toHaveBeenCalledTimes(2);expect(h.api.libraryWorkspaceAction).not.toHaveBeenCalled();view.unmount();
  });
  it('shows the empty-assets guidance only after a successful empty read',async()=>{
    const h=harness();render(<LibraryWorkspace api={h.typed} tab="assets"/>);
    expect(screen.queryByText(/No registered assets yet/)).toBeNull();
    expect(await screen.findByText(/No registered assets yet/)).toBeTruthy();expect(h.api.libraryWorkspace).toHaveBeenCalledOnce();
  });
  it('selects an asset reference locally and starts one recipe job only on explicit Create',async()=>{
    const h=harness();h.api.libraryWorkspaceAction.mockImplementation(async body=>({...h.state,jobs:[{...job(),request_id:'request_id'in body?body.request_id:''}]}));
    render(<LibraryWorkspace api={h.typed} tab="create"/>);await screen.findByRole('button',{name:'Create asset'});
    fireEvent.change(screen.getByRole('textbox',{name:'Describe Library asset'}),{target:{value:'A wooden chair'}});
    fireEvent.change(screen.getByLabelText('Asset reference image'),{target:{files:[localFile('chair.jpg','image/jpeg')]}});
    expect(h.api.libraryWorkspaceAction).not.toHaveBeenCalled();expect(h.api.applySceneEdit).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button',{name:'Create asset'}));
    await screen.findByText(/Recipe geometry checked/);
    expect(h.api.libraryWorkspaceAction).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({action:'create_recipe',prompt:'A wooden chair',reference:expect.objectContaining({name:'chair.jpg',role:'asset_reference',bytes_base64:btoa('file bytes')})}));
    expect(h.api.applySceneEdit).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button',{name:'Register asset'}));
    await waitFor(()=>expect(h.api.libraryWorkspaceAction).toHaveBeenCalledWith(expect.objectContaining({action:'register_job',job_id:'job'})));
    expect(h.api.applySceneEdit).not.toHaveBeenCalled();
  });
  it('keeps CAD bytes and provenance local until explicit Import, with no scene API call',async()=>{
    const h=harness();const file=localFile('machine.step','application/step');const accepted=vi.fn();
    render(<LibraryWorkspace api={h.typed} tab="import" initialImport={file} onImportSubmitted={accepted}/>);
    await screen.findByText(/machine.step · Library asset source/);
    expect(h.api.libraryWorkspaceAction).not.toHaveBeenCalled();
    fireEvent.change(screen.getByRole('textbox',{name:'Asset license'}),{target:{value:'CC0'}});
    fireEvent.click(screen.getByRole('button',{name:'Import asset'}));
    await waitFor(()=>expect(h.api.libraryWorkspaceAction).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({action:'import_asset',license:'CC0',attachment:{name:'machine.step',media_type:'application/step',bytes_base64:btoa('file bytes'),role:'asset_source'}})));
    await waitFor(()=>expect(accepted).toHaveBeenCalledOnce());expect(h.api.applySceneEdit).not.toHaveBeenCalled();
  });
  it('rejects a CAD file mislabeled as an asset reference before posting',async()=>{
    const h=harness();render(<LibraryWorkspace api={h.typed} tab="create" initialPrompt="chair" initialReference={localFile('part.step','application/step')}/>);
    await waitFor(()=>expect(screen.getByRole('button',{name:'Create asset'})).toHaveProperty('disabled',false));
    fireEvent.click(screen.getByRole('button',{name:'Create asset'}));expect(await screen.findByRole('alert')).toHaveProperty('textContent',expect.stringContaining('PNG, JPEG or WebP'));
    expect(h.api.libraryWorkspaceAction).not.toHaveBeenCalled();
  });
  it('exposes missing optional programs while built-in recipe creation remains available',async()=>{
    const h=harness({...empty(),extensions:[{extension_id:'cad',title:'CAD converter',transport:'cli',available:false,enabled:false,reason:'Program not installed',version:null,executable_configurable:true,tools:[]}]});
    const view=render(<LibraryWorkspace api={h.typed} tab="connections" initialPrompt="A chair"/>);
    expect(await screen.findByText('Program not installed')).toBeTruthy();expect(h.api.libraryWorkspaceAction).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button',{name:'Check CAD converter'}));await waitFor(()=>expect(h.api.libraryWorkspaceAction).toHaveBeenCalledWith({action:'check_extension',extension_id:'cad'}));
    view.rerender(<LibraryWorkspace api={h.typed} tab="create" initialPrompt="A chair"/>);
    expect(screen.getByRole('button',{name:'Create asset'})).toHaveProperty('disabled',false);
  });
  it('uses schema inputs and tool_input CSV bytes for an explicit registered tool',async()=>{
    const h=harness({...empty(),extensions:[{extension_id:'analysis',title:'Local analysis',transport:'builtin',available:true,enabled:true,reason:null,version:'1',executable_configurable:false,tools:[{tool_id:'csv_summary',title:'CSV summary',input_schema:{type:'object',properties:{column:{type:'string'},threshold:{type:'number',minimum:0}},required:['column']},output_kind:'table'}]}]});
    render(<LibraryWorkspace api={h.typed} tab="connections"/>);await waitFor(()=>expect(screen.getByRole('option',{name:'CSV summary'})).toBeTruthy());
    fireEvent.change(screen.getByRole('combobox',{name:'Library tool'}),{target:{value:'csv_summary'}});
    fireEvent.change(screen.getByRole('textbox',{name:'column'}),{target:{value:'duration'}});
    fireEvent.change(screen.getByRole('spinbutton',{name:'threshold'}),{target:{value:'1.25'}});
    fireEvent.change(screen.getByLabelText('Library tool input file'),{target:{files:[localFile('durations.csv','text/csv','duration\n2\n3')]}});
    expect(h.api.libraryWorkspaceAction).not.toHaveBeenCalled();fireEvent.click(screen.getByRole('button',{name:'Run CSV summary'}));
    await waitFor(()=>expect(h.api.libraryWorkspaceAction).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({action:'run_tool',tool_id:'csv_summary',inputs:{column:'duration',threshold:1.25},attachment:expect.objectContaining({name:'durations.csv',role:'tool_input'})})));
    expect(h.api.applySceneEdit).not.toHaveBeenCalled();
  });
  it('renders worker tables and markup as React text without executing HTML',async()=>{
    const h=harness({...empty(),jobs:[{...job('registered'),result:{text:'<script>bad()</script>',columns:['Metric','Value'],rows:[['sum',5]]}}]});
    render(<LibraryWorkspace api={h.typed} tab="assets"/>);
    expect(await screen.findByText('<script>bad()</script>')).toBeTruthy();expect(screen.getByRole('cell',{name:'sum'})).toBeTruthy();
    expect(document.querySelector('script')).toBeNull();
  });
  it('pins asset and scene versions for preview, then uses the existing Apply transaction',async()=>{
    const h=harness({...empty(),assets:[savedAsset]});h.api.libraryWorkspaceAction.mockResolvedValue({...h.state,placement_preview:placement});const applied=vi.fn();
    render(<LibraryWorkspace api={h.typed} tab="assets" sceneRevision="scene-a" onSceneApplied={applied}/>);
    fireEvent.click(await screen.findByRole('button',{name:/Saved chair/}));
    fireEvent.click(screen.getByRole('button',{name:'Preview asset placement'}));
    await screen.findByRole('region',{name:'Library placement preview'});
    expect(h.api.libraryWorkspaceAction).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({action:'preview_placement',asset_id:'chair',version:savedAsset.version,expected_scene_revision:'scene-a',position_m:[0,0,0],yaw_deg:0}));
    expect(h.api.applySceneEdit).not.toHaveBeenCalled();fireEvent.click(screen.getByRole('button',{name:'Apply asset placement'}));
    await waitFor(()=>expect(applied).toHaveBeenCalledOnce(),{timeout:2000});
    expect(h.api.applyLibraryPlacement).toHaveBeenCalledExactlyOnceWith('saved-preview','digest');expect(h.api.applySceneEdit).not.toHaveBeenCalled();
    expect(h.api.sceneEditTransaction).toHaveBeenCalledOnce();expect(h.api.workflow).toHaveBeenCalledOnce();
  });
  it('invalidates a placement preview when the target scene revision changes',async()=>{
    const h=harness({...empty(),assets:[savedAsset]});h.api.libraryWorkspaceAction.mockResolvedValue({...h.state,placement_preview:placement});
    const view=render(<LibraryWorkspace api={h.typed} tab="assets" sceneRevision="scene-a"/>);fireEvent.click(await screen.findByRole('button',{name:/Saved chair/}));
    fireEvent.click(screen.getByRole('button',{name:'Preview asset placement'}));await screen.findByRole('button',{name:'Apply asset placement'});
    view.rerender(<LibraryWorkspace api={h.typed} tab="assets" sceneRevision="scene-new"/>);
    expect(screen.queryByRole('button',{name:'Apply asset placement'})).toBeNull();expect(screen.getByRole('button',{name:'Preview asset placement'})).toHaveProperty('disabled',true);
    expect(h.api.applySceneEdit).not.toHaveBeenCalled();
  });
  it('retains the same server preview across an unknown scene revision without allowing Apply',async()=>{
    const h=harness({...empty(),assets:[savedAsset]});const {view}=await placementView(h);
    const proposal=screen.getByRole('region',{name:'Library placement preview'});
    view.rerender(<LibraryWorkspace api={h.typed} tab="assets" sceneRevision={null}/>);
    expect(screen.queryByRole('button',{name:'Apply asset placement'})).toBeNull();
    expect(screen.getByRole('button',{name:'Preview asset placement'})).toHaveProperty('disabled',true);
    expect(h.api.applyLibraryPlacement).not.toHaveBeenCalled();
    view.rerender(<LibraryWorkspace api={h.typed} tab="assets" sceneRevision="scene-a"/>);
    expect(await screen.findByRole('button',{name:'Apply asset placement'})).toHaveProperty('disabled',false);
    expect(screen.getByRole('region',{name:'Library placement preview'}).textContent).toBe(proposal.textContent);
    expect(h.api.libraryWorkspaceAction).toHaveBeenCalledOnce();expect(h.api.applyLibraryPlacement).not.toHaveBeenCalled();
  });
  it('keeps the existing workspace revision fallback when sceneRevision is omitted or undefined',async()=>{
    const h=harness({...empty(),assets:[savedAsset]});h.api.libraryWorkspaceAction.mockResolvedValue({...h.state,placement_preview:placement});
    const view=render(<LibraryWorkspace api={h.typed} tab="assets"/>);
    fireEvent.click(await screen.findByRole('button',{name:/Saved chair/}));fireEvent.click(screen.getByRole('button',{name:'Preview asset placement'}));
    await screen.findByRole('button',{name:'Apply asset placement'});
    view.rerender(<LibraryWorkspace api={h.typed} tab="assets" sceneRevision={undefined}/>);
    expect(screen.getByRole('button',{name:'Apply asset placement'})).toHaveProperty('disabled',false);
    expect(h.api.libraryWorkspaceAction).toHaveBeenCalledOnce();expect(h.api.applyLibraryPlacement).not.toHaveBeenCalled();
  });
  it.each(['while-unknown','after-recovery'])('retains a pending preview response arriving %s only for the original confirmed scene',async timing=>{
    const h=harness({...empty(),assets:[savedAsset]});let resolve!:(state:LibraryWorkspaceState)=>void;
    h.api.libraryWorkspaceAction.mockImplementation(()=>new Promise(done=>{resolve=done;}));
    const view=render(<LibraryWorkspace api={h.typed} tab="assets" sceneRevision="scene-a"/>);
    fireEvent.click(await screen.findByRole('button',{name:/Saved chair/}));fireEvent.click(screen.getByRole('button',{name:'Preview asset placement'}));
    await waitFor(()=>expect(h.api.libraryWorkspaceAction).toHaveBeenCalledOnce());
    view.rerender(<LibraryWorkspace api={h.typed} tab="assets" sceneRevision={null}/>);
    if(timing==='while-unknown')await act(async()=>resolve({...h.state,placement_preview:placement}));
    expect(screen.queryByRole('button',{name:'Apply asset placement'})).toBeNull();
    view.rerender(<LibraryWorkspace api={h.typed} tab="assets" sceneRevision="scene-a"/>);
    if(timing==='after-recovery')await act(async()=>resolve({...h.state,placement_preview:placement}));
    expect(await screen.findByRole('button',{name:'Apply asset placement'})).toHaveProperty('disabled',false);
    expect(h.api.libraryWorkspaceAction).toHaveBeenCalledOnce();expect(h.api.applyLibraryPlacement).not.toHaveBeenCalled();
  });
  it('never revives a late preview after a different confirmed revision even when the old revision returns',async()=>{
    const h=harness({...empty(),assets:[savedAsset]});let resolve!:(state:LibraryWorkspaceState)=>void;
    h.api.libraryWorkspaceAction.mockImplementation(()=>new Promise(done=>{resolve=done;}));
    const view=render(<LibraryWorkspace api={h.typed} tab="assets" sceneRevision="scene-a"/>);
    fireEvent.click(await screen.findByRole('button',{name:/Saved chair/}));fireEvent.click(screen.getByRole('button',{name:'Preview asset placement'}));
    await waitFor(()=>expect(h.api.libraryWorkspaceAction).toHaveBeenCalledOnce());
    view.rerender(<LibraryWorkspace api={h.typed} tab="assets" sceneRevision="scene-other"/>);
    view.rerender(<LibraryWorkspace api={h.typed} tab="assets" sceneRevision={null}/>);
    view.rerender(<LibraryWorkspace api={h.typed} tab="assets" sceneRevision="scene-a"/>);
    await act(async()=>resolve({...h.state,placement_preview:placement}));
    expect(screen.queryByRole('button',{name:'Apply asset placement'})).toBeNull();expect(h.api.applyLibraryPlacement).not.toHaveBeenCalled();
  });
  it.each(['api','context'])('never revives a late preview after a %s switch and return to the previous owner',async kind=>{
    const h=harness({...empty(),assets:[savedAsset]});let resolve!:(state:LibraryWorkspaceState)=>void;
    h.api.libraryWorkspaceAction.mockImplementation(()=>new Promise(done=>{resolve=done;}));
    const view=render(<LibraryWorkspace api={h.typed} tab="assets" sceneRevision="scene-a"/>);
    fireEvent.click(await screen.findByRole('button',{name:/Saved chair/}));fireEvent.click(screen.getByRole('button',{name:'Preview asset placement'}));
    await waitFor(()=>expect(h.api.libraryWorkspaceAction).toHaveBeenCalledOnce());
    if(kind==='context')h.api.context='context-b';
    const other=harness({...empty(),assets:[savedAsset]});
    view.rerender(<LibraryWorkspace api={kind==='api'?other.typed:h.typed} tab="assets" sceneRevision={null}/>);
    await act(async()=>{await Promise.resolve();});
    h.api.context='context-a';view.rerender(<LibraryWorkspace api={h.typed} tab="assets" sceneRevision="scene-a"/>);
    await act(async()=>resolve({...h.state,placement_preview:placement}));
    expect(screen.queryByRole('button',{name:'Apply asset placement'})).toBeNull();expect(h.api.applyLibraryPlacement).not.toHaveBeenCalled();
  });
  it.each(['Asset instance ID','Asset X position','Asset yaw'])('discards the preserved preview after %s changes during an unknown revision, including a later form reversal',async name=>{
    const h=harness({...empty(),assets:[savedAsset]});const {view}=await placementView(h);
    const input=screen.getByLabelText(name) as HTMLInputElement,original=input.value;
    view.rerender(<LibraryWorkspace api={h.typed} tab="assets" sceneRevision={null}/>);
    expect(input.disabled||input.closest('fieldset')?.disabled).toBe(true);
    // A queued change must still invalidate its preview, even while Apply is unavailable.
    fireEvent.change(input,{target:{value:name==='Asset instance ID'?'new-instance':'1'}});
    fireEvent.change(input,{target:{value:original}});
    view.rerender(<LibraryWorkspace api={h.typed} tab="assets" sceneRevision="scene-a"/>);
    expect(screen.queryByRole('button',{name:'Apply asset placement'})).toBeNull();expect(h.api.libraryWorkspaceAction).toHaveBeenCalledOnce();
    expect(h.api.applyLibraryPlacement).not.toHaveBeenCalled();
  });
  it('discards a preserved preview after immutable asset version selection changes while the revision is unknown',async()=>{
    const newer={...savedAsset,version:'c'.repeat(64),title:'Chair new version'};
    const h=harness({...empty(),assets:[savedAsset,newer]});const {view}=await placementView(h);
    view.rerender(<LibraryWorkspace api={h.typed} tab="assets" sceneRevision={null}/>);
    fireEvent.click(screen.getByRole('button',{name:/Chair new version/}));fireEvent.click(screen.getByRole('button',{name:/Saved chair/}));
    view.rerender(<LibraryWorkspace api={h.typed} tab="assets" sceneRevision="scene-a"/>);
    expect(screen.queryByRole('button',{name:'Apply asset placement'})).toBeNull();expect(h.api.applyLibraryPlacement).not.toHaveBeenCalled();
  });
  it('waits for the matching transaction to be committed with its current frame before publishing workflow',async()=>{
    const h=harness({...empty(),assets:[savedAsset]});h.api.sceneEditTransaction.mockResolvedValue(placementTransaction('COMMITTED',false));
    const {applied}=await placementView(h);vi.useFakeTimers();
    await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'Apply asset placement'}));await vi.advanceTimersByTimeAsync(1000);});
    expect(h.api.sceneEditTransaction).toHaveBeenCalledOnce();expect(applied).not.toHaveBeenCalled();expect(h.api.workflow).not.toHaveBeenCalled();
    h.api.sceneEditTransaction.mockResolvedValue(placementTransaction());
    await act(async()=>{await vi.advanceTimersByTimeAsync(750);});
    expect(applied).toHaveBeenCalledOnce();expect(h.api.applyLibraryPlacement).toHaveBeenCalledExactlyOnceWith('saved-preview','digest');
    expect(h.api.applySceneEdit).not.toHaveBeenCalled();
  });
  it('does not claim success for another operation and recovers by an explicit read without another Apply',async()=>{
    const h=harness({...empty(),assets:[savedAsset]});h.api.applyLibraryPlacement.mockResolvedValue({...placementTransaction(),operation_id:'other'});
    const {applied}=await placementView(h);fireEvent.click(screen.getByRole('button',{name:'Apply asset placement'}));
    await screen.findByRole('button',{name:'Check placement result · read only'});
    expect(h.api.sceneEditTransaction).not.toHaveBeenCalled();expect(applied).not.toHaveBeenCalled();
    expect(screen.getByRole('button',{name:'Apply asset placement'})).toHaveProperty('disabled',true);
    vi.useFakeTimers();await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'Check placement result · read only'}));await vi.advanceTimersByTimeAsync(800);});
    expect(applied).toHaveBeenCalledOnce();expect(h.api.applyLibraryPlacement).toHaveBeenCalledTimes(1);
  });
  it('bounds even a hung transaction GET and never accepts a late completion after the deadline',async()=>{
    const h=harness({...empty(),assets:[savedAsset]});let complete!:(value:SceneEditTransaction)=>void;
    h.api.sceneEditTransaction.mockImplementation(()=>new Promise(resolve=>{complete=resolve;}));const {applied}=await placementView(h);vi.useFakeTimers();
    await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'Apply asset placement'}));await vi.advanceTimersByTimeAsync(135001);});
    expect(screen.getByRole('button',{name:'Check placement result · read only'})).toBeTruthy();
    expect(screen.getByRole('button',{name:'Apply asset placement'})).toHaveProperty('disabled',true);
    const reads=h.api.sceneEditTransaction.mock.calls.length;await act(async()=>{complete(placementTransaction());await vi.advanceTimersByTimeAsync(30000);});
    expect(h.api.sceneEditTransaction).toHaveBeenCalledTimes(reads);expect(applied).not.toHaveBeenCalled();expect(h.api.workflow).not.toHaveBeenCalled();expect(h.api.applyLibraryPlacement).toHaveBeenCalledOnce();
  });
  it('checks an unknown POST delivery using the preview operation ID without repeating it',async()=>{
    const h=harness({...empty(),assets:[savedAsset]});h.api.applyLibraryPlacement.mockRejectedValue(new ApiError('delivery_unknown','Apply response lost'));
    const {applied}=await placementView(h);vi.useFakeTimers();
    await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'Apply asset placement'}));await vi.advanceTimersByTimeAsync(800);});
    expect(h.api.sceneEditTransaction).toHaveBeenCalledOnce();expect(applied).toHaveBeenCalledOnce();expect(h.api.applyLibraryPlacement).toHaveBeenCalledOnce();expect(h.api.applySceneEdit).not.toHaveBeenCalled();
  });
  it('stops transaction polling on close and does not publish an in-flight late result',async()=>{
    const h=harness({...empty(),assets:[savedAsset]});let complete!:(value:SceneEditTransaction)=>void;
    h.api.sceneEditTransaction.mockImplementation(()=>new Promise(resolve=>{complete=resolve;}));const {view,applied}=await placementView(h);vi.useFakeTimers();
    await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'Apply asset placement'}));await vi.advanceTimersByTimeAsync(800);});
    view.unmount();await act(async()=>{complete(placementTransaction());await vi.advanceTimersByTimeAsync(2000);});
    expect(h.api.sceneEditTransaction).toHaveBeenCalledOnce();expect(applied).not.toHaveBeenCalled();expect(h.api.workflow).not.toHaveBeenCalled();
  });
  it('ignores a completed transaction from another operation until the exact saved operation arrives',async()=>{
    const h=harness({...empty(),assets:[savedAsset]});h.api.sceneEditTransaction.mockResolvedValue({...placementTransaction(),operation_id:'older-operation'});
    const {applied}=await placementView(h);vi.useFakeTimers();
    await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'Apply asset placement'}));await vi.advanceTimersByTimeAsync(2000);});
    expect(applied).not.toHaveBeenCalled();expect(h.api.workflow).not.toHaveBeenCalled();
    h.api.sceneEditTransaction.mockResolvedValue(placementTransaction());await act(async()=>{await vi.advanceTimersByTimeAsync(750);});
    expect(applied).toHaveBeenCalledOnce();expect(h.api.applyLibraryPlacement).toHaveBeenCalledOnce();
  });
  it('does not publish a late placement transaction after a project-context switch',async()=>{
    const h=harness({...empty(),assets:[savedAsset]});let complete!:(value:SceneEditTransaction)=>void;
    h.api.sceneEditTransaction.mockImplementation(()=>new Promise(resolve=>{complete=resolve;}));const {view,applied}=await placementView(h);vi.useFakeTimers();
    await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'Apply asset placement'}));await vi.advanceTimersByTimeAsync(800);});
    h.api.context='context-b';h.state.project_id='new-project';view.rerender(<LibraryWorkspace api={h.typed} tab="assets" sceneRevision="new-scene" onSceneApplied={applied}/>);
    await act(async()=>{complete(placementTransaction());await vi.advanceTimersByTimeAsync(2000);});
    expect(applied).not.toHaveBeenCalled();expect(h.api.workflow).not.toHaveBeenCalled();expect(h.api.sceneEditTransaction).toHaveBeenCalledOnce();
  });
  it('does not apply an old preview without a server ID',async()=>{
    const h=harness({...empty(),assets:[savedAsset]});h.api.libraryWorkspaceAction.mockResolvedValue({...h.state,placement_preview:{...placement,preview_id:''}});
    render(<LibraryWorkspace api={h.typed} tab="assets" sceneRevision="scene-a"/>);fireEvent.click(await screen.findByRole('button',{name:/Saved chair/}));
    fireEvent.click(screen.getByRole('button',{name:'Preview asset placement'}));await screen.findByText(/Create a fresh server-saved preview before Apply/);
    expect(screen.getByRole('button',{name:'Apply asset placement'})).toHaveProperty('disabled',true);expect(h.api.applyLibraryPlacement).not.toHaveBeenCalled();expect(h.api.applySceneEdit).not.toHaveBeenCalled();
  });
  it('defaults imported mesh centre Z to half its height while preserving edited coordinates',async()=>{
    const imported={...savedAsset,asset_id:'mesh',title:'Imported equipment',kind:'usd' as const,dimensions_m:[1,1,2] as [number,number,number]};
    const taller={...imported,asset_id:'tall',title:'Tall equipment',dimensions_m:[1,1,4] as [number,number,number]};
    const h=harness({...empty(),assets:[imported,taller,savedAsset]});render(<LibraryWorkspace api={h.typed} tab="assets"/>);
    fireEvent.click(await screen.findByRole('button',{name:/Imported equipment/}));
    expect(screen.getByRole('spinbutton',{name:'Asset Z position'})).toHaveProperty('value','1');
    expect(screen.getByText(/independent floor placement only.*half the asset height \(1 m\)/)).toBeTruthy();
    fireEvent.change(screen.getByRole('spinbutton',{name:'Asset X position'}),{target:{value:'3'}});
    fireEvent.click(screen.getByRole('button',{name:/Tall equipment/}));
    expect(screen.getByRole('spinbutton',{name:'Asset X position'})).toHaveProperty('value','3');
    expect(screen.getByRole('spinbutton',{name:'Asset Z position'})).toHaveProperty('value','2');
    fireEvent.change(screen.getByRole('spinbutton',{name:'Asset Z position'}),{target:{value:'2.7'}});
    fireEvent.click(screen.getByRole('button',{name:/Imported equipment/}));
    expect(screen.getByRole('spinbutton',{name:'Asset Z position'})).toHaveProperty('value','2.7');
    expect(h.api.libraryWorkspaceAction).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button',{name:/Saved chair/}));expect(screen.getByText(/Recipe placement uses the XY centre at floor level/)).toBeTruthy();
  });
  it('lists OBJ local inspection separately from optional USD formats without starting an import on selection',async()=>{
    const h=harness();render(<LibraryWorkspace api={h.typed} tab="import"/>);await screen.findByText(/OBJ mesh files.*built-in local inspector/);
    const input=screen.getByLabelText('Library asset file');expect(input.getAttribute('accept')).toContain('.obj');
    expect(input.getAttribute('accept')).toContain('.usd');expect(input.getAttribute('accept')).toContain('.usda');expect(input.getAttribute('accept')).toContain('.usdc');
    fireEvent.change(input,{target:{files:[localFile('machine.obj','model/obj')]}});
    expect(screen.getByText(/machine.obj · Library asset source/)).toBeTruthy();expect(h.api.libraryWorkspaceAction).not.toHaveBeenCalled();
  });
  it.each([{available:true,enabled:true},{available:true,enabled:false},{available:false,enabled:false}])('uses the usd_inspector availability $available / enabled $enabled for USD import',async flags=>{
    const h=harness({...empty(),extensions:[{extension_id:'usd_inspector',title:'USD inspector',transport:'cli',...flags,reason:flags.available?null:'Reviewed USD program not found',version:flags.available?'1.0':null,executable_configurable:true,tools:[{tool_id:'usd.inspect',title:'Inspect USD',input_schema:{},output_kind:'asset'}]}]});
    render(<LibraryWorkspace api={h.typed} tab="import" initialImport={localFile('machine.usda','model/vnd.usda')}/>);
    await screen.findByText(/USD support is limited to self-contained static meshes/);
    fireEvent.change(screen.getByRole('textbox',{name:'Asset license'}),{target:{value:'CC0'}});
    expect(screen.getByRole('button',{name:'Import asset'})).toHaveProperty('disabled',!flags.available||!flags.enabled);
    if(flags.available&&flags.enabled)expect(screen.getByText(/USD inspection available · 1.0/)).toBeTruthy();
    else if(flags.available)expect(screen.getByText(/USD inspection is disabled/)).toBeTruthy();
    else expect(screen.getByText(/USD inspection unavailable: Reviewed USD program not found/)).toBeTruthy();
    expect(h.api.libraryWorkspaceAction).not.toHaveBeenCalled();
    // Missing USD tooling does not prevent the built-in OBJ import branch.
    fireEvent.change(screen.getByLabelText('Library asset file'),{target:{files:[localFile('machine.obj','model/obj')]}});
    fireEvent.change(screen.getByRole('combobox',{name:'OBJ source units'}),{target:{value:'m'}});
    fireEvent.change(screen.getByRole('combobox',{name:'OBJ source up axis'}),{target:{value:'Z'}});
    expect(screen.getByRole('button',{name:'Import asset'})).toHaveProperty('disabled',false);
  });
  it('requires explicit OBJ units and up axis and sends them without replacing the import draft',async()=>{
    const h=harness();render(<LibraryWorkspace api={h.typed} tab="import" initialImport={localFile('machine.obj','model/obj')}/>);
    await screen.findByRole('combobox',{name:'OBJ source units'});
    fireEvent.change(screen.getByRole('textbox',{name:'Asset source provenance'}),{target:{value:'Original machine drawing'}});
    fireEvent.change(screen.getByRole('textbox',{name:'Asset license'}),{target:{value:'CC0'}});
    expect(screen.getByRole('combobox',{name:'OBJ source units'})).toHaveProperty('value','');
    expect(screen.getByRole('combobox',{name:'OBJ source up axis'})).toHaveProperty('value','');
    expect(screen.getByRole('button',{name:'Import asset'})).toHaveProperty('disabled',true);
    fireEvent.change(screen.getByRole('combobox',{name:'OBJ source units'}),{target:{value:'mm'}});
    expect(screen.getByRole('button',{name:'Import asset'})).toHaveProperty('disabled',true);
    fireEvent.change(screen.getByRole('combobox',{name:'OBJ source up axis'}),{target:{value:'Y'}});
    expect(h.api.libraryWorkspaceAction).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button',{name:'Import asset'}));
    await waitFor(()=>expect(h.api.libraryWorkspaceAction).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({action:'import_asset',source:'Original machine drawing',license:'CC0',source_units:'mm',source_up_axis:'Y',attachment:expect.objectContaining({name:'machine.obj',role:'asset_source'})})));
    expect(screen.getByRole('textbox',{name:'Asset source provenance'})).toHaveProperty('value','Original machine drawing');
    expect(screen.getByRole('textbox',{name:'Asset license'})).toHaveProperty('value','CC0');
    // A different source must receive its own explicit coordinate declaration.
    fireEvent.change(screen.getByLabelText('Library asset file'),{target:{files:[localFile('other.obj','model/obj')]}});
    expect(screen.getByRole('combobox',{name:'OBJ source units'})).toHaveProperty('value','');
    expect(screen.getByRole('combobox',{name:'OBJ source up axis'})).toHaveProperty('value','');
    expect(screen.getByRole('button',{name:'Import asset'})).toHaveProperty('disabled',true);
  });
  it('locks an unknown delivery and reconciles only the matching saved request without another POST',async()=>{
    const h=harness();h.api.libraryWorkspaceAction.mockRejectedValue(new ApiError('delivery_unknown','Response lost'));
    render(<LibraryWorkspace api={h.typed} tab="create" initialPrompt="A chair"/>);
    await waitFor(()=>expect(screen.getByRole('button',{name:'Create asset'})).toHaveProperty('disabled',false));fireEvent.click(screen.getByRole('button',{name:'Create asset'}));
    await screen.findByText(/Delivery unknown/);const body=h.api.libraryWorkspaceAction.mock.calls[0][0];
    fireEvent.click(screen.getByRole('button',{name:'Create asset'}));expect(h.api.libraryWorkspaceAction).toHaveBeenCalledTimes(1);
    h.state.jobs=[{...job(),request_id:'request_id'in body?body.request_id:''}];
    fireEvent.click(screen.getByRole('button',{name:'Check saved Library results · read only'}));
    await waitFor(()=>expect(screen.queryByText(/Delivery unknown/)).toBeNull());expect(h.api.libraryWorkspaceAction).toHaveBeenCalledTimes(1);
  });
  it('polls only active work and stops reading on close',async()=>{
    vi.useFakeTimers();const h=harness({...empty(),jobs:[job('running')]});const view=render(<LibraryWorkspace api={h.typed} tab="create"/>);
    await act(async()=>{await Promise.resolve();});expect(screen.getByText(/Recipe geometry checked/)).toBeTruthy();
    await act(async()=>{await vi.advanceTimersByTimeAsync(1100);});expect(h.api.libraryWorkspace.mock.calls.length).toBeGreaterThan(1);
    view.unmount();const reads=h.api.libraryWorkspace.mock.calls.length;await act(async()=>{await vi.advanceTimersByTimeAsync(3000);});expect(h.api.libraryWorkspace).toHaveBeenCalledTimes(reads);
  });
  it('discards a late action from a different project context',async()=>{
    const h=harness();let resolve!:(value:LibraryWorkspaceState)=>void;h.api.libraryWorkspaceAction.mockImplementation(()=>new Promise(done=>{resolve=done;}));
    const view=render(<LibraryWorkspace api={h.typed} tab="create" initialPrompt="A chair"/>);
    await waitFor(()=>expect(screen.getByRole('button',{name:'Create asset'})).toHaveProperty('disabled',false));fireEvent.click(screen.getByRole('button',{name:'Create asset'}));
    await waitFor(()=>expect(h.api.libraryWorkspaceAction).toHaveBeenCalledOnce());h.api.context='context-b';h.state.project_id='new-project';
    view.rerender(<LibraryWorkspace api={h.typed} tab="create" initialPrompt="A chair"/>);
    await act(async()=>{resolve({...empty(),jobs:[job()],message:'OLD PROJECT RESULT'});});expect(screen.queryByText('OLD PROJECT RESULT')).toBeNull();
    expect(screen.getByRole('button',{name:'Create asset'})).toHaveProperty('disabled',false);
  });
  it('does not post converted reference bytes after a project switch during the local file read',async()=>{
    const h=harness();const file=localFile('chair.jpg','image/jpeg');let bytes!:(buffer:ArrayBuffer)=>void;
    Object.defineProperty(file,'arrayBuffer',{value:()=>new Promise<ArrayBuffer>(done=>{bytes=done;}),configurable:true});
    const view=render(<LibraryWorkspace api={h.typed} tab="create" initialPrompt="chair" initialReference={file}/>);
    await waitFor(()=>expect(screen.getByRole('button',{name:'Create asset'})).toHaveProperty('disabled',false));fireEvent.click(screen.getByRole('button',{name:'Create asset'}));
    await waitFor(()=>expect(bytes).toBeTypeOf('function'));h.api.context='context-b';view.rerender(<LibraryWorkspace api={h.typed} tab="create"/>);
    await act(async()=>{bytes(new TextEncoder().encode('image').buffer);});expect(h.api.libraryWorkspaceAction).not.toHaveBeenCalled();
  });
  it('cancels owned active work explicitly without registering or applying its late result',async()=>{
    const h=harness({...empty(),jobs:[job('running')]});h.api.libraryWorkspaceAction.mockResolvedValue({...h.state,jobs:[job('cancelled')]});
    render(<LibraryWorkspace api={h.typed} tab="create"/>);fireEvent.click(await screen.findByRole('button',{name:'Cancel Library job'}));
    await waitFor(()=>expect(h.api.libraryWorkspaceAction).toHaveBeenCalledExactlyOnceWith({action:'cancel_job',job_id:'job'}));
    expect(screen.queryByRole('button',{name:'Register asset'})).toBeNull();expect(h.api.applySceneEdit).not.toHaveBeenCalled();
  });
  it('checks required fields, number ranges and JSON types from the declared tool schema',()=>{
    const schema={properties:{name:{type:'string'},count:{type:'integer',minimum:1},options:{type:'object'},mode:{enum:[1,2]}},required:['name']};
    expect(()=>toolInputs(schema,{})).toThrow('name is required');expect(()=>toolInputs(schema,{name:'a',count:'1.2'})).toThrow('integer');
    expect(()=>toolInputs(schema,{name:'a',count:'0'})).toThrow('range');expect(()=>toolInputs(schema,{name:'a',options:'[]'})).toThrow('JSON object');
    expect(toolInputs(schema,{name:'a',count:'2',options:'{"x":1}',mode:'2'})).toEqual({name:'a',count:2,options:{x:1},mode:2});
  });
});
