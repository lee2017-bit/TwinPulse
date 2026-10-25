// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,beforeEach,describe,it,expect,vi} from 'vitest';
import {TwinViewport,generationActivityLabel,generationStageLabel,generationIsIncomplete,generationRetentionRevalidationLabel} from './TwinViewport';
import type {TwinPulseApi} from './api';
import type {ViewportState} from './viewport-types';
import type {ConversationState} from './conversation-types';
// @ts-expect-error The UI tsconfig omits Node types; this read-only CSS fixture runs only in Vitest.
import {readFileSync} from 'node:fs';

function view(frame=1):ViewportState {return {state:'live',fps:6,age_ms:10,physical_authority:false,detail:'Real render',
  camera_pending:false,camera_result:null,frame:{frame_id:frame,captured_at_ms:Date.now(),applied_revision:'rev',
    stage_epoch:'stage',engine_session_id:'engine',width:960,height:640,camera_sequence:0,sha256:'hash',url:'unused'}};}
function harness(){return {conversationImage:vi.fn(async()=>new Blob(['photo'],{type:'image/png'})),viewportState:vi.fn(async()=>view()),viewportImage:vi.fn(async(_frameId:number)=>new Blob(['image'],{type:'image/jpeg'})),
  viewportCamera:vi.fn(async(_body:{request_id:string;frame_id:number;action:string})=>({...view(),camera_pending:true})),command:vi.fn()};}

describe('Real Isaac viewport',()=>{
  it('keeps ordinary robot names transparent without a background card, shadow or second status line',()=>{
    const css=readFileSync('src/styles.css','utf8');
    const rule=css.match(/\.chat-workspace \.robot-anchor-layer \.robot-anchor-badge, \.robot-anchor-badge \{([^}]+)\}/)![1];
    expect(rule).toContain('background:transparent');expect(rule).toContain('box-shadow:none');expect(rule).toContain('border:0');
  });
  it('keeps an original current receipt during next-image delivery, uses its camera ID and expires it without timestamp renewal',async()=>{
    const first=view(1);let metadata=first;
    const api={...harness(),viewportImageFrame:vi.fn(async()=>({state:metadata,image:new Blob(['frame'],{type:'image/jpeg'})}))};
    api.viewportState.mockImplementation(async()=>metadata);
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi}/>);
    const canvas=await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});
    let finish!:(packet:{state:ViewportState;image:Blob})=>void;
    metadata=view(2);api.viewportImageFrame.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}));
    await waitFor(()=>expect(api.viewportImageFrame).toHaveBeenCalledTimes(2));
    expect(screen.getByRole('img',{name:'Current Isaac Digital Twin render'})).toBe(canvas);
    fireEvent.click(screen.getByRole('button',{name:'Orbit left'}));
    expect(api.viewportCamera.mock.calls[0][0].frame_id).toBe(1);
    await screen.findByRole('img',{name:'Last Isaac preview · not live'},{timeout:1800});
    expect(canvas.dataset.capturedAt).toBe(String(first.frame!.captured_at_ms));
    expect(screen.getByRole('button',{name:'Orbit left'})).toHaveProperty('disabled',true);
    metadata=view(3);
    await act(async()=>finish({state:metadata,image:new Blob(['new-frame'],{type:'image/jpeg'})}));
    await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});
    component.unmount();
  });
  it('keeps the decoded surface through control-view switching and folds details outside it',async()=>{
    const api=harness();const component=render(<TwinViewport api={api as unknown as TwinPulseApi}/>);
    const canvas=await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});
    component.rerender(<TwinViewport api={api as unknown as TwinPulseApi} controlView/>);
    expect(component.container.querySelector('canvas')).toBe(canvas);
    const details=screen.getByText('Camera, source photo and scene details').closest('details')!;
    expect(details.open).toBe(false);expect(details.contains(canvas)).toBe(false);
    component.rerender(<TwinViewport api={api as unknown as TwinPulseApi}/>);
    expect(component.container.querySelector('canvas')).toBe(canvas);component.unmount();
  });
  it.each(['accepted','running'])('labels %s resume revalidation as bounded local work without implying a model request',state=>{
    const stage='Rechecking saved candidates · local validation; no model request implied';
    expect(generationStageLabel('resume_revalidation')).toBe(stage);
    const label=generationActivityLabel({operation_id:'resumed',state,summary:'Resume requested',can_cancel:true,
      started_at:'now',last_progress_at:'now',error:null,progress:{stage:'render_review',
        generation_activity:{schema_version:'generation-activity-1.0',stage:'resume_revalidation',phase:'validating'}}});
    expect(label).toBe(`${stage} · validating the received candidate`);expect(label.length).toBeLessThan(140);
    expect(label).not.toContain('Reviewing the preview');expect(label).not.toContain('stage completed');
  });
  it.each([
    [{validation:'passed',same_plan:true,same_witness:true},'recheck passed; pending retained'],
    [{validation:'failed',same_plan:false,same_witness:true},'not saved: plan changed.'],
    [{validation:'failed',same_plan:true,same_witness:false},'not saved: pending evidence changed.'],
    [{validation:'failed',same_plan:false,same_witness:false},'not saved: plan changed; pending evidence changed.'],
    [{validation:'passed',same_plan:false,same_witness:true},'recheck unconfirmed'],
    [{validation:'failed',same_plan:true,same_witness:true},'recheck unconfirmed'],
    [{validation:'passed',same_plan:'true',same_witness:true},'recheck unconfirmed'],
    [{validation:'passed',same_plan:true,same_witness:true,gate:'unknown'},'recheck unconfirmed'],
    [{validation:'passed',same_plan:true,same_witness:true,physical_authority:true},'recheck unconfirmed'],
    [{validation:'unknown',same_plan:true,same_witness:true},'recheck unconfirmed'],
    [null,'recheck unconfirmed'],[[],'recheck unconfirmed'],['raw provider reason','recheck unconfirmed'],
  ])('bounds partial-retention recheck labels for %j', (payload,expected)=>{
    const value=payload&&typeof payload==='object'&&!Array.isArray(payload)?
      {gate:'exact_plan_and_support_witness',physical_authority:false,...payload,raw_reason:'UNBOUNDED'.repeat(1000)}:payload;
    const job={progress:{retention_revalidation:value}} as unknown as NonNullable<ConversationState['generation']>;
    const label=generationRetentionRevalidationLabel(job)!;
    expect(label).toContain(expected);expect(label).toContain('Photo quality and SIM remain unverified.');
    expect(label).not.toContain('UNBOUNDED');expect(label.length).toBeLessThan(160);
  });
  it('omits absent retention evidence and never replaces malformed terminal evidence with an earlier PASS',()=>{
    expect(generationRetentionRevalidationLabel({progress:{}} as NonNullable<ConversationState['generation']>)).toBeNull();
    const progress={retention_revalidation:{validation:'passed',gate:'exact_plan_and_support_witness',same_plan:true,same_witness:true,physical_authority:false}};
    for(const value of [undefined,null,{validation:'passed'}]){
      const job={progress,error:{diagnostics:{retention_revalidation:value}}} as unknown as NonNullable<ConversationState['generation']>;
      expect(generationRetentionRevalidationLabel(job)).toContain('recheck unconfirmed');
    }
  });
  it('adds retention evidence only inside existing details while retaining compact content, photo, canvas and camera guard',async()=>{
    const api=harness(),sourcePhoto={url:'/source',name:'room.jpg'};
    const generation:NonNullable<ConversationState['generation']>={operation_id:'retention',state:'running',summary:'Working',
      can_cancel:true,started_at:'now',last_progress_at:'now',error:null,progress:{
        generation_preview:{schema_version:'generation-preview-1.0',state:'ready',candidate_revision:'candidate',scene_revision:'rev',
          rendered_count:2,pending_count:1,inventory_count:3,preview_only:true,physical_authority:false}}};
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi} sourcePhoto={sourcePhoto} generation={generation}/>);
    const canvas=await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});
    const photo=screen.getByRole('img',{name:'Source photo: room.jpg'}),controls=screen.getByLabelText('Camera controls');
    const compact=component.container.querySelector('.twin-generation-summary')!,compactContent=compact.innerHTML;
    const details=screen.getByText('Progress details').closest('details')!;
    expect(screen.queryByLabelText('Partial scene retention recheck')).toBeNull();
    for(const payload of [
      {validation:'passed',gate:'exact_plan_and_support_witness',same_plan:true,same_witness:true,physical_authority:false},
      {validation:'failed',gate:'exact_plan_and_support_witness',same_plan:true,same_witness:false,physical_authority:false},
      {validation:'passed'},
    ]){
      component.rerender(<TwinViewport api={api as unknown as TwinPulseApi} sourcePhoto={sourcePhoto} appConnected={false}
        generation={{...generation,progress:{...generation.progress,retention_revalidation:payload as never}}}/>);
      const label=screen.getByLabelText('Partial scene retention recheck');
      expect(details.contains(label)).toBe(true);expect(details.open).toBe(false);expect(compact.innerHTML).toBe(compactContent);
      expect(component.container.querySelector('canvas')).toBe(canvas);expect(screen.getByRole('img',{name:'Source photo: room.jpg'})).toBe(photo);
      expect(screen.getByLabelText('Camera controls')).toBe(controls);expect(screen.getByRole('button',{name:'Orbit left'})).toHaveProperty('disabled',true);
    }
    expect(api.command).not.toHaveBeenCalled();expect(api.viewportCamera).not.toHaveBeenCalled();component.unmount();
  });
  it('follows same-input saved Apply and Undo revisions instead of the old generation pin',async()=>{
    const api=harness();let applied='rev';
    api.viewportState.mockImplementation(async()=>({...view(),frame:{...view().frame!,applied_revision:applied}}));
    const generation:NonNullable<ConversationState['generation']>={operation_id:'same-generation',origin_message_id:'photo-origin',
      state:'running',summary:'Working',can_cancel:true,started_at:'now',last_progress_at:'now',error:null,
      progress:{generation_preview:{schema_version:'generation-preview-1.0',state:'ready',candidate_revision:'candidate',scene_revision:'rev',
        rendered_count:2,pending_count:1,inventory_count:3,preview_only:true,physical_authority:false}}};
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi} projectId="one"/>);
    await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});
    component.rerender(<TwinViewport api={api as unknown as TwinPulseApi} projectId="one" generation={generation}/>);
    await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});
    const completed={...generation,state:'completed' as const,can_cancel:false};
    component.rerender(<TwinViewport api={api as unknown as TwinPulseApi} projectId="one" generation={completed} savedScene={{revision:'edited',partial:true}}/>);
    expect(screen.getByRole('img',{name:'Last Isaac preview · not live'})).toBeTruthy();
    expect(screen.getByRole('button',{name:'Orbit left'})).toHaveProperty('disabled',true);
    applied='edited';
    await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});
    component.rerender(<TwinViewport api={api as unknown as TwinPulseApi} projectId="one" generation={completed} savedScene={{revision:'undo',partial:true}}/>);
    expect(screen.getByRole('img',{name:'Last Isaac preview · not live'})).toBeTruthy();
    applied='undo';
    await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});
    expect(api.command).not.toHaveBeenCalled();component.unmount();
  });
  it('keeps a seen saved binding fail-closed across missing workflow and a late old decoder',async()=>{
    const api=harness();let revision='rev',sequence=1;
    api.viewportState.mockImplementation(async()=>({...view(sequence),frame:{...view(sequence).frame!,applied_revision:revision}}));
    const generation:NonNullable<ConversationState['generation']>={operation_id:'saved',origin_message_id:'same-photo',state:'completed',
      summary:'Saved',can_cancel:false,started_at:'now',last_progress_at:'now',error:null,
      progress:{generation_preview:{schema_version:'generation-preview-1.0',state:'ready',candidate_revision:'candidate',scene_revision:'rev',
        rendered_count:2,pending_count:1,inventory_count:3,preview_only:true,physical_authority:false}}};
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi} generation={generation} savedScene={{revision:'rev',partial:true}}/>);
    const canvas=await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});
    let finish!:(value:ImageBitmap)=>void;
    vi.mocked(createImageBitmap).mockImplementationOnce(()=>new Promise<ImageBitmap>(resolve=>{finish=resolve;}));
    sequence=2;await waitFor(()=>expect(createImageBitmap).toHaveBeenCalledTimes(2));
    component.rerender(<TwinViewport api={api as unknown as TwinPulseApi} generation={generation} savedScene={{revision:'edited',partial:true}}/>);
    component.rerender(<TwinViewport api={api as unknown as TwinPulseApi} generation={generation} savedScene={null}/>);
    const drawn=drawing.drawImage.mock.calls.length;
    await act(async()=>finish({width:960,height:640,close} as unknown as ImageBitmap));
    expect(screen.getByRole('img',{name:'Last Isaac preview · not live'})).toBe(canvas);
    expect(drawing.drawImage).toHaveBeenCalledTimes(drawn);
    expect(screen.getByRole('button',{name:'Orbit left'})).toHaveProperty('disabled',true);
    revision='edited';sequence=3;
    component.rerender(<TwinViewport api={api as unknown as TwinPulseApi} generation={generation} savedScene={{revision:'edited',partial:true}}/>);
    await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});
    expect(api.command).not.toHaveBeenCalled();component.unmount();
  });
  it('invalidates the layout assessment after an effective scene edit or blocked rebuild',async()=>{
    const api=harness();
    const generation:NonNullable<ConversationState['generation']>={operation_id:'reviewed',state:'completed',summary:'Partial',
      can_cancel:false,started_at:'now',last_progress_at:'now',error:null,progress:{
        generation_preview:{schema_version:'generation-preview-1.0',state:'ready',candidate_revision:'candidate',scene_revision:'rev',
          rendered_count:2,pending_count:1,inventory_count:3,preview_only:true,physical_authority:false},
        quality_review:{candidate_revision:'candidate',relative_layout:{status:'consistent_materialized_anchors',
          metric_scale:'estimated_not_measured',sensor_alignment:'not_run',physical_authority:false}}}};
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi} generation={generation} savedScene={{revision:'rev',partial:true}}/>);
    await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});
    expect(screen.getByLabelText('Relative layout review').textContent).toContain('not whole-photo acceptance');
    component.rerender(<TwinViewport api={api as unknown as TwinPulseApi} generation={generation} savedScene={{revision:'edited',partial:true}}/>);
    expect(screen.getByLabelText('Relative layout review').textContent).toContain('recheck required after candidate change');
    const blocked={...generation,progress:{...generation.progress,generation_preview:{...generation.progress!.generation_preview!,state:'blocked' as const}}};
    component.rerender(<TwinViewport api={api as unknown as TwinPulseApi} generation={blocked} savedScene={{revision:'rev',partial:true}}/>);
    expect(screen.getByLabelText('Relative layout review').textContent).toContain('recheck required after candidate change');
    component.unmount();
  });
  it('keeps decoded pixels and photo across a temporary App observation failure without camera authority',async()=>{
    const api=harness(),photoSource={url:'/source',name:'room.jpg'};
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi} sourcePhoto={photoSource}/>);
    const canvas=await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});
    const photo=await screen.findByRole('img',{name:'Source photo: room.jpg'});
    const clearCount=drawing.clearRect.mock.calls.length;
    component.rerender(<TwinViewport api={api as unknown as TwinPulseApi} sourcePhoto={photoSource} appConnected={false}/>);
    expect(screen.getByRole('img',{name:'Last Isaac preview · not live'})).toBe(canvas);
    expect(screen.getByRole('img',{name:'Source photo: room.jpg'})).toBe(photo);
    expect(drawing.clearRect).toHaveBeenCalledTimes(clearCount);
    expect(screen.getByRole('button',{name:'Orbit left'})).toHaveProperty('disabled',true);
    component.rerender(<TwinViewport api={api as unknown as TwinPulseApi} sourcePhoto={photoSource} appConnected/>);
    await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});
    expect(screen.getByRole('img',{name:'Source photo: room.jpg'})).toBe(photo);
    component.unmount();
  });
  it('does not label a fully rendered but photo-conflicting draft complete',()=>{
    const generation:NonNullable<ConversationState['generation']>={operation_id:'quality-ended',state:'completed',
      summary:'Saved approximate draft',can_cancel:false,started_at:'now',last_progress_at:'now',error:null,
      progress:{stage_acceptance:{approximate_draft:'partial',photo_quality:'needs_revision'}}};
    expect(generationIsIncomplete(generation)).toBe(true);
    expect(generationActivityLabel(generation)).toContain('photo layout conflicts remain');
    expect(generationActivityLabel(generation)).not.toContain('generation completed');
  });
  afterEach(()=>vi.unstubAllGlobals());
  let close:ReturnType<typeof vi.fn>;
  let drawing:{clearRect:ReturnType<typeof vi.fn>;drawImage:ReturnType<typeof vi.fn>};
  beforeEach(()=>{
    close=vi.fn();drawing={clearRect:vi.fn(),drawImage:vi.fn()};
    vi.spyOn(HTMLCanvasElement.prototype,'getContext').mockReturnValue(drawing as unknown as CanvasRenderingContext2D);
    vi.stubGlobal('createImageBitmap',vi.fn(async()=>({width:960,height:640,close})));
    vi.stubGlobal('Image',class {src='';naturalWidth=960;naturalHeight=640;async decode(){}});
  });
  it.each([0,.625])('expires the exact decoded frame at its original deadline with fractional clock %s',async(fraction)=>{
    vi.useFakeTimers();
    let component:ReturnType<typeof render>|undefined;
    try{
      const frame=view();frame.frame!.captured_at_ms=Date.now()-940+fraction;
      const api=harness();api.viewportState.mockImplementation(async()=>frame);
      component=render(<TwinViewport api={api as unknown as TwinPulseApi}/>);
      await act(async()=>{await vi.advanceTimersByTimeAsync(0);});
      expect(screen.getByRole('img',{name:'Current Isaac Digital Twin render'}).getAttribute('data-live')).toBe('true');
      await act(async()=>{await vi.advanceTimersByTimeAsync(59);});
      expect(screen.getByRole('img',{name:'Current Isaac Digital Twin render'})).toBeTruthy();
      await act(async()=>{await vi.advanceTimersByTimeAsync(2);});
      const last=screen.getByRole('img',{name:'Last Isaac preview · not live'});
      expect(last.getAttribute('data-live')).toBe('false');
      expect(last.getAttribute('data-captured-at')).toBe(String(frame.frame!.captured_at_ms));
      expect(screen.getByRole('button',{name:'Orbit left'})).toHaveProperty('disabled',true);
    }finally{component?.unmount();vi.useRealTimers();}
  });
  it.each([
    ['observer_structure','waiting_model','Estimating the initial room structure · waiting for model response'],
    ['repair','validating','Correcting the scene · validating the received candidate'],
    ['room','building','Preparing the room shell · applying the checked candidate in Isaac'],
    ['objects','awaiting_frame','Preparing object details · waiting for its current Isaac frame'],
    ['objects','ready','Preparing object details · stage completed'],
  ] as const)('describes the actual %s / %s activity without guessing model reasoning',(stage,phase,expected)=>{
    expect(generationActivityLabel({operation_id:'job',state:'running',summary:'Working',can_cancel:true,started_at:'now',last_progress_at:'now',error:null,
      progress:{generation_activity:{schema_version:'generation-activity-1.0',stage,phase}}})).toBe(expected);
  });
  it('shows repair targets, batch progress and stalled termination from the supplied activity',()=>{
    const generation:NonNullable<ConversationState['generation']>={operation_id:'job',state:'running',summary:'Working',can_cancel:true,started_at:'now',last_progress_at:'now',error:null,
      progress:{repair_count:2,max_repairs:3,generation_activity:{schema_version:'generation-activity-1.0',stage:'repair',phase:'waiting_model',batch_index:2,batch_total:5,affected_ids:['desk','shelf']}}};
    expect(generationActivityLabel(generation)).toContain('batch 2/5 · repair 2/3 · desk, shelf');
    expect(generationActivityLabel({...generation,state:'failed',error:{code:'REPAIR_STALLED',message:'No validated progress'}})).toBe('Correcting the scene · stopped after no validated repair progress (REPAIR_STALLED) · no confirmed 3D preview');
  });
  it.each(['failed','cancelled','interrupted'])('prioritizes terminal %s over a retained model-wait activity',state=>{
    const generation:NonNullable<ConversationState['generation']>={operation_id:'job',state,summary:'Stopped',can_cancel:false,
      started_at:'now',last_progress_at:'now',error:{code:'PROVIDER_TIMEOUT',message:'Provider timed out'},progress:{
        generation_activity:{schema_version:'generation-activity-1.0',stage:'objects',phase:'waiting_model'},
        generation_preview:{schema_version:'generation-preview-1.0',state:'ready',candidate_revision:'candidate',scene_revision:'rev',
          rendered_count:17,pending_count:8,inventory_count:25,preview_only:true,physical_authority:false}}};
    const label=generationActivityLabel(generation);
    expect(label).toBe(`Preparing object details · generation ${state} (PROVIDER_TIMEOUT) · last valid preview retained`);
    expect(label).not.toContain('waiting for model');expect(label).not.toContain('current Isaac preview confirmed');
    expect(generationActivityLabel({...generation,progress:{...generation.progress,generation_preview:undefined}})).toContain('no confirmed 3D preview');
  });
  it('prioritizes cancellation over a previous repair-stalled reason and uses the actual error over activity reasons',()=>{
    const generation:NonNullable<ConversationState['generation']>={operation_id:'job',state:'cancelled',summary:'Cancelled',can_cancel:false,
      started_at:'now',last_progress_at:'now',error:null,progress:{generation_activity:{schema_version:'generation-activity-1.0',stage:'repair',phase:'waiting_model',reason_codes:['REPAIR_STALLED']}}};
    expect(generationActivityLabel(generation)).toBe('Correcting the scene · generation cancelled · no confirmed 3D preview');
    expect(generationActivityLabel({...generation,state:'failed',error:{code:'CANDIDATE_INVALID',message:'Rejected'}})).toBe('Correcting the scene · generation failed (CANDIDATE_INVALID) · no confirmed 3D preview');
  });
  it.each(['observer_structure','objects','repair','final_validation'])('does not claim an Isaac frame when the %s stage is ready',stage=>{
    const label=generationActivityLabel({operation_id:'job',state:'running',summary:'Stage finished',can_cancel:true,started_at:'now',last_progress_at:'now',error:null,
      progress:{generation_activity:{schema_version:'generation-activity-1.0',stage,phase:'ready'}}});
    expect(label).toContain('stage completed');expect(label).not.toContain('Isaac preview confirmed');
  });
  it.each([0,1])('replaces stale validation activity when generation completes with %s objects still pending',pending=>{
    const generation:NonNullable<ConversationState['generation']>={operation_id:'finished',state:'completed',summary:'Finished',can_cancel:false,
      started_at:'now',last_progress_at:'now',error:null,progress:{generation_activity:{schema_version:'generation-activity-1.0',stage:'final_validation',phase:'validating'},
        generation_preview:{schema_version:'generation-preview-1.0',state:'ready',candidate_revision:'candidate',scene_revision:'rev',
          rendered_count:4-pending,pending_count:pending,inventory_count:4,preview_only:true,physical_authority:false},
        inventory_progress:{schema_version:'inventory-work-progress-1.0',observed_instances:4,inventory_count:4,parameterized_count:4,pending_count:0,
          parameter_batch_size:6,inventory_planned:true,parameters_complete:true,checkpoint_saved:true,draft_saved:true,automatic_resume:false,physical_authority:false},
        stage_acceptance:{photo_quality:'uncertain'}}};
    const label=generationActivityLabel(generation);expect(label).not.toContain('validating the received candidate');
    expect(label).toBe(pending?'Generation ended · incomplete preview retained':'Scene generation completed · photo quality and motion checks require separate review');
  });
  it('keeps canvas pixels, photo, caption and camera positions while a newer receipt awaits decoding',async()=>{
    const api=harness();const sourcePhoto={url:'/source',name:'room.jpg'};
    // An unchanged engine receipt keeps its capture time. Regenerating it on
    // every poll would advertise new frame keys and permit extra real draws.
    api.viewportState.mockResolvedValue(view(1));
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi} sourcePhoto={sourcePhoto}/>);
    const canvas=await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});
    const photo=screen.getByRole('img',{name:'Source photo: room.jpg'});
    const caption=component.container.querySelector('.twin-frame-caption')!;
    const actions=screen.getByLabelText('Camera controls');
    const children=Array.from(actions.parentElement!.children);
    let finish!:(bitmap:ImageBitmap)=>void;
    vi.mocked(createImageBitmap).mockImplementationOnce(()=>new Promise<ImageBitmap>(resolve=>{finish=resolve;}));
    const clears=drawing.clearRect.mock.calls.length,draws=drawing.drawImage.mock.calls.length;
    api.viewportState.mockResolvedValue(view(2));
    await waitFor(()=>expect(finish).toBeTypeOf('function'));
    expect(createImageBitmap).toHaveBeenCalledTimes(2);
    expect(screen.getByRole('img',{name:'Current Isaac Digital Twin render'})).toBe(canvas);
    expect(canvas.getAttribute('data-frame-id')).toBe('1');expect(drawing.clearRect).toHaveBeenCalledTimes(clears);
    expect(screen.getByRole('button',{name:'Orbit left'})).toHaveProperty('disabled',false);
    expect(component.container.querySelector('.twin-frame-caption')).toBe(caption);
    expect(caption.textContent).toContain('Frame 1');
    expect(screen.getByRole('img',{name:'Source photo: room.jpg'})).toBe(photo);
    expect(Array.from(actions.parentElement!.children)).toEqual(children);
    await act(async()=>{finish({width:960,height:640,close} as unknown as ImageBitmap);});
    await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});
    expect(drawing.drawImage).toHaveBeenCalledTimes(draws+1);expect(component.container.querySelector('.twin-frame-caption')).toBe(caption);
    expect(Array.from(actions.parentElement!.children)).toEqual(children);component.unmount();
  });
  it('bounds progress layout across active, repair and failed updates without replacing photo, canvas or camera controls',async()=>{
    const api=harness(),sourcePhoto={url:'/source',name:'room.jpg'};
    const generation:NonNullable<ConversationState['generation']>={operation_id:'job',origin_message_id:'source',state:'running',
      summary:'Working',can_cancel:true,started_at:'now',last_progress_at:'now',error:null,progress:{
        generation_activity:{schema_version:'generation-activity-1.0',stage:'observer',phase:'waiting_model'},
        generation_preview:{schema_version:'generation-preview-1.0',state:'ready',candidate_revision:'candidate',scene_revision:'rev',
          rendered_count:17,pending_count:8,inventory_count:25,preview_only:true,physical_authority:false}}};
    const component=(job:typeof generation)=><TwinViewport api={api as unknown as TwinPulseApi} sourcePhoto={sourcePhoto} generation={job}/>;
    const rendered=render(component(generation));
    const canvas=await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});
    const photo=screen.getByRole('img',{name:'Source photo: room.jpg'});
    const controls=screen.getByLabelText('Camera controls'),caption=rendered.container.querySelector('.twin-frame-caption');
    const panel=screen.getByRole('status',{name:'Twin generation progress'});
    expect(panel.tabIndex).toBe(0);expect(panel.getAttribute('aria-description')).toContain('arrow keys');
    // jsdom has no geometric layout. Check the shipped CSS bound here;
    // actual source/camera coordinates are measured in browser acceptance.
    const viewportStyles=readFileSync('src/chat.css','utf8');
    const progressRule=viewportStyles.match(/\.twin-generation-progress\s*\{([^}]+)\}/)![1];
    expect(progressRule).toContain('min-height:8rem');expect(progressRule).toContain('box-sizing:border-box');
    expect(progressRule).not.toMatch(/(?:^|;)\s*(?:height|max-height):/);expect(progressRule).not.toContain('overflow-y:auto');
    const detailRule=viewportStyles.match(/\.twin-generation-detail-body\s*\{([^}]+)\}/)![1];
    expect(detailRule).toContain('max-height:18rem');expect(detailRule).toContain('overflow-y:auto');expect(detailRule).toContain('scrollbar-gutter:stable');
    const expansion=screen.getByText('Progress details').closest('details')!;
    expect(expansion.open).toBe(false);fireEvent.click(screen.getByText('Progress details'));expect(expansion.open).toBe(true);
    const repair={...generation,progress:{...generation.progress,repair_count:2,max_repairs:3,
      generation_activity:{schema_version:'generation-activity-1.0' as const,stage:'repair',phase:'validating' as const,
        affected_ids:Array.from({length:25},(_,i)=>`object_${i}`)},generation_preview:{...generation.progress!.generation_preview!,
          state:'blocked' as const,pending_objects:[{id:'pending',reason_code:'SUPPORT_PENDING',blocked_by:['table']}]}}};
    rendered.rerender(component(repair));
    expect(expansion.open).toBe(true);expect(panel.querySelector('.twin-generation-summary')!.textContent).not.toContain('object_0');
    expect(panel.querySelector('.twin-generation-detail-body')!.textContent).toContain('object_0');
    const details=screen.getByText('Objects waiting for 3D · 1').parentElement as HTMLDetailsElement;
    fireEvent.click(screen.getByText('Objects waiting for 3D · 1'));details.open=true;
    expect(details.textContent).toContain('pending · support pending');
    rendered.rerender(component({...repair,state:'failed',can_cancel:false,error:{code:'REPAIR_STALLED',message:'Long failure detail '.repeat(60)}}));
    expect(panel.textContent).toContain('Long failure detail');expect(panel.className).toBe('twin-generation-progress');
    expect(expansion.open).toBe(true);fireEvent.click(screen.getByText('Progress details'));expect(expansion.open).toBe(false);
    const summary=panel.querySelector('.twin-generation-summary')!;
    expect(summary.textContent).toContain('Latest error: REPAIR_STALLED');expect(summary.textContent).toContain('current candidate blocked');
    expect(summary.textContent).not.toContain('Long failure detail');
    expect(screen.getByRole('status',{name:'Twin generation progress'})).toBe(panel);
    expect(rendered.container.querySelector('canvas')).toBe(canvas);expect(screen.getByRole('img',{name:'Source photo: room.jpg'})).toBe(photo);
    expect(screen.getByLabelText('Camera controls')).toBe(controls);expect(rendered.container.querySelector('.twin-frame-caption')).toBe(caption);
    expect(screen.getByRole('button',{name:'Orbit left'})).toHaveProperty('disabled',true);
    expect(api.viewportCamera).not.toHaveBeenCalled();rendered.unmount();
  });
  it('keeps compact parameter and confirmed-render counts separate, with the full existing record behind a closed disclosure',async()=>{
    const api=harness();
    const generation:NonNullable<ConversationState['generation']>={operation_id:'compact',state:'running',summary:'Working',
      can_cancel:true,started_at:'now',last_progress_at:'now',error:null,progress:{repair_count:1,max_repairs:3,elapsed_s:21,
        generation_activity:{schema_version:'generation-activity-1.0',stage:'render_review',phase:'waiting_model'},
        generation_preview:{schema_version:'generation-preview-1.0',state:'ready',candidate_revision:'candidate',scene_revision:'rev',
          rendered_count:30,pending_count:1,inventory_count:31,preview_only:true,physical_authority:false,
          pending_objects:[{id:'lamp',reason_code:'SUPPORT_PENDING',blocked_by:['desk']}]},
        inventory_progress:{schema_version:'inventory-work-progress-1.0',observed_instances:31,inventory_count:31,parameterized_count:31,
          pending_count:0,parameter_batch_size:6,inventory_planned:true,parameters_complete:true,checkpoint_saved:true,
          automatic_resume:false,physical_authority:false}}};
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi} generation={generation}/>);
    await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});
    const panel=screen.getByRole('status',{name:'Twin generation progress'}),compact=panel.querySelector('.twin-generation-summary')!;
    expect(compact.textContent).toContain('Parameters 31/31');expect(compact.textContent).toContain('Awaiting parameters 0');
    expect(compact.textContent).toContain('Last confirmed 3D 30/31');expect(compact.textContent).toContain('Not rendered 1');
    expect(compact.textContent).not.toContain('Last confirmed 3D 31/31');
    const details=screen.getByText('Progress details').closest('details')!;
    expect(details.open).toBe(false);expect(details.textContent).toContain('Repairs: 1/3 · 21 s');
    expect(details.textContent).toContain('Parameters: 31 of 31 objects prepared · 0 awaiting parameters');
    expect(details.textContent).toContain('Last confirmed 3D: 30 of 31 objects rendered · 1 not rendered');
    expect(details.textContent).toContain('Displayed image: decoded Isaac image available');expect(details.textContent).toContain('Candidate preview: ready');
    expect(details.textContent).toContain('Confirmed preview revision: rev');expect(details.textContent).toContain('Candidate revision: candidate');
    expect(details.textContent).toContain('lamp · support pending · waiting for: desk');expect(details.textContent).toContain('Resume checkpoint saved');
    expect(details.textContent).toContain('Whole-scene completion, simulation and physical execution require separate checks');
    const canvas=component.container.querySelector('canvas');fireEvent.click(screen.getByText('Progress details'));
    expect(details.open).toBe(true);expect(component.container.querySelector('canvas')).toBe(canvas);expect(api.viewportCamera).not.toHaveBeenCalled();component.unmount();
  });
  it('keeps long Korean stages and warning summaries outside the disclosure without clipping narrow layouts',()=>{
    vi.stubGlobal('innerWidth',360);const api=harness();
    const korean='긴 한국어 단계와 관측 검증 결과를 원문 그대로 확인합니다 '.repeat(12);
    const generation:NonNullable<ConversationState['generation']>={operation_id:'narrow',state:'running',summary:'Working',
      can_cancel:true,started_at:'now',last_progress_at:'now',error:{code:'MODEL_RESPONSE_INVALID',message:'Full detailed failure'},progress:{
        generation_activity:{schema_version:'generation-activity-1.0',stage:korean,phase:'blocked'},
        generation_preview:{schema_version:'generation-preview-1.0',state:'blocked',candidate_revision:'candidate',scene_revision:'rev',
          rendered_count:2,pending_count:1,inventory_count:3,preview_only:true,physical_authority:false,error_code:'PREVIEW_REBUILD_REQUIRED'},
        quality_review:{candidate_revision:'candidate',relative_layout:{status:'needs_revision',contradicted_anchor_ids:['desk'],
          metric_scale:'estimated_not_measured',sensor_alignment:'not_run',physical_authority:false}}}};
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi} generation={generation}/>);
    const panel=screen.getByRole('status',{name:'Twin generation progress'}),compact=panel.querySelector('.twin-generation-summary')!;
    expect(compact.textContent).toContain(korean);expect(compact.textContent).toContain('blocked');
    expect(compact.textContent).toContain('rebuild required');expect(compact.textContent).toContain('recheck required after candidate change');
    expect(compact.textContent).toContain('Latest error: MODEL_RESPONSE_INVALID');expect(compact.closest('details')).toBeNull();
    expect(compact.textContent).toContain('Parameters not confirmed');expect(compact.textContent).not.toContain('Parameters not planned');
    const details=screen.getByText('Progress details').closest('details')!;
    expect(details.open).toBe(false);expect(details.textContent).toContain('Full detailed failure');expect(details.textContent).toContain('Layout conflicts: desk');
    const css=readFileSync('src/chat.css','utf8');
    for(const selector of ['twin-generation-progress','twin-generation-summary','twin-generation-counts','twin-generation-warning']){
      const rule=css.match(new RegExp(`\\.${selector}\\s*\\{([^}]+)\\}`))![1];
      expect(rule).not.toMatch(/(?:^|;)\s*(?:height|max-height):|overflow[^;]*:\s*hidden|line-clamp|text-overflow|white-space:\s*nowrap/);
    }
    expect(css.match(/\.twin-generation-progress\s*\{([^}]+)\}/)![1]).toContain('overflow-wrap:anywhere');
    expect(api.viewportCamera).not.toHaveBeenCalled();component.unmount();
  });
  it('draws the atomically paired latest frame rather than the replaced metadata frame',async()=>{
    const api={...harness(),viewportImageFrame:vi.fn(async()=>({state:view(9),image:new Blob(['image'],{type:'image/jpeg'})}))};
    api.viewportState.mockImplementation(()=>new Promise(()=>{})); // A slow JSON metadata request cannot hold live JPEG reception.
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi}/>);
    expect((await screen.findByRole('img')).getAttribute('data-frame-id')).toBe('9');
    expect(api.viewportState).not.toHaveBeenCalled();expect(api.viewportImage).not.toHaveBeenCalled();expect(api.command).not.toHaveBeenCalled();component.unmount();
  });
  it('never pairs a JPEG-less atomic reply with a newer metadata receipt during cold restoration',async()=>{
    const api={...harness(),viewportImageFrame:vi.fn(async():Promise<{state:ViewportState;image:Blob|null}>=>({state:view(9),image:new Blob(['paired-nine'],{type:'image/jpeg'})}))};
    api.viewportImageFrame.mockResolvedValueOnce({state:{...view(),state:'waiting',frame:null},image:null});
    api.viewportState.mockResolvedValue(view(33)); // This frame has no paired image in the first response.
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi}/>);
    const canvas=await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});
    expect(canvas.getAttribute('data-frame-id')).toBe('9');expect(api.viewportState).toHaveBeenCalledTimes(1);
    expect(api.viewportImage).not.toHaveBeenCalled();expect(createImageBitmap).toHaveBeenCalledTimes(1);component.unmount();
  });
  it('restores the matching saved preview even when an older preview is still present in the atomic packet',async()=>{
    const sha='a'.repeat(64);
    const preview=(revision:string)=>({...view(8).frame!,applied_revision:revision,captured_at_ms:Date.now()-60000,
      sha256:sha,url:`/v1/product/viewport/preview/${sha}`,preview_only:true as const,physical_authority:false as const});
    const api={...harness(),viewportPreviewImage:vi.fn(async()=>new Blob(['saved'],{type:'image/jpeg'})),
      viewportImageFrame:vi.fn(async()=>({state:{...view(),state:'waiting' as const,frame:null,last_frame:preview('old')},image:null}))};
    api.viewportState.mockResolvedValue({...view(),state:'stale',frame:null,last_frame:preview('new')});
    const generation:NonNullable<ConversationState['generation']>={operation_id:'saved',state:'completed',summary:'Saved',
      can_cancel:false,started_at:'now',last_progress_at:'now',error:null};
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi} generation={generation} savedScene={{revision:'new',partial:true}}/>);
    const canvas=await screen.findByRole('img',{name:'Last Isaac preview · not live'});
    expect(canvas.dataset.frameId).toBe('8');expect(api.viewportState).toHaveBeenCalled();
    expect(api.viewportPreviewImage).toHaveBeenCalledWith(sha);expect(api.viewportImage).not.toHaveBeenCalled();
    expect(screen.getByRole('button',{name:'Orbit left'})).toHaveProperty('disabled',true);component.unmount();
  });
  it('retains a static preview when the atomic packet says the current scene has no frame',async()=>{
    let sequence=0;
    const api={...harness(),viewportImageFrame:vi.fn(async():Promise<{state:ViewportState;image:Blob|null}>=>({state:view(++sequence),image:new Blob(['image'],{type:'image/jpeg'})}))};
    api.viewportState.mockImplementation(async()=>view(++sequence));
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi}/>);await screen.findByRole('img');
    api.viewportImageFrame.mockImplementation(async()=>({state:{...view(),state:'waiting',frame:null},image:null}));
    await screen.findByRole('img',{name:'Last Isaac preview · not live'});
    expect((screen.getByRole('button',{name:'Orbit left'}) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.queryByRole('alert')).toBeNull();expect(api.viewportImage).not.toHaveBeenCalled();component.unmount();
  });
  it('uses the atomic packet identity when a revision changes during image delivery',async()=>{
    const newer=view(8);newer.frame!.applied_revision='new-revision';
    const api={...harness(),viewportImageFrame:vi.fn(async()=>({state:newer,image:new Blob(['image'],{type:'image/jpeg'})}))};
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi}/>);
    expect((await screen.findByRole('img')).getAttribute('data-frame-id')).toBe('8');
    expect(screen.getByText(/Frame 8/).textContent).toContain('stage stage');
    fireEvent.click(screen.getByRole('button',{name:'Orbit left'}));
    await waitFor(()=>expect(api.viewportCamera.mock.calls[0][0].frame_id).toBe(8));component.unmount();
  });
  it('loads authenticated frames and sends camera-only commands once',async()=>{
    URL.createObjectURL=vi.fn(()=>'blob:frame');URL.revokeObjectURL=vi.fn();
    const api=harness();const component=render(<TwinViewport api={api as unknown as TwinPulseApi}/>);
    expect(await screen.findByRole('img',{name:'Current Isaac Digital Twin render'})).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'Orbit left'}));
    await waitFor(()=>expect(api.viewportCamera).toHaveBeenCalledTimes(1));
    expect(api.viewportCamera.mock.calls[0][0].action).toBe('orbit_left');expect(api.command).not.toHaveBeenCalled();
    expect(close).toHaveBeenCalledTimes(1);expect(URL.createObjectURL).not.toHaveBeenCalled();component.unmount();
  });
  it('requests a top camera view without a scene or robot command',async()=>{
    const api=harness();const component=render(<TwinViewport api={api as unknown as TwinPulseApi}/>);
    await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});
    fireEvent.click(screen.getByRole('button',{name:'Top view'}));
    await waitFor(()=>expect(api.viewportCamera).toHaveBeenCalledTimes(1));
    expect(api.viewportCamera.mock.calls[0][0].action).toBe('top_view');expect(api.command).not.toHaveBeenCalled();component.unmount();
  });
  it('retains preview pixels on loss and never retries a camera mutation',async()=>{
    URL.createObjectURL=vi.fn(()=>'blob:frame');URL.revokeObjectURL=vi.fn();
    const api=harness();api.viewportCamera.mockRejectedValue(new Error('Camera delivery unknown'));
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi}/>);
    await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});
    fireEvent.click(screen.getByRole('button',{name:'Zoom in'}));
    expect(await screen.findByRole('alert')).toHaveProperty('textContent',expect.stringContaining('Camera delivery unknown'));
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve,300));});
    expect(screen.getByRole('alert').textContent).toContain('Camera delivery unknown');
    api.viewportState.mockRejectedValue(new Error('Viewer disconnected'));
    await waitFor(()=>expect(screen.queryByRole('img',{name:'Current Isaac Digital Twin render'})).toBeNull());
    expect(screen.getByRole('img',{name:'Last Isaac preview · not live'})).toBeTruthy();
    expect(api.viewportCamera).toHaveBeenCalledTimes(1);component.unmount();
  });
  it('expires the visible image even if a later metadata poll never returns',async()=>{
    URL.createObjectURL=vi.fn(()=>'blob:frame');URL.revokeObjectURL=vi.fn();
    const api=harness();const component=render(<TwinViewport api={api as unknown as TwinPulseApi}/>);
    await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});
    api.viewportState.mockImplementation(()=>new Promise(()=>{}));
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve,1100));});
    expect(screen.queryByRole('img',{name:'Current Isaac Digital Twin render'})).toBeNull();component.unmount();
  });
  it('reuses one surface and closes every decoded frame',async()=>{
    let frame=0;const api=harness();api.viewportState.mockImplementation(async()=>view(++frame));
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi}/>);
    await waitFor(()=>expect(drawing.drawImage.mock.calls.length).toBeGreaterThanOrEqual(3));
    expect(component.container.querySelectorAll('canvas')).toHaveLength(1);
    expect(close).toHaveBeenCalledTimes(drawing.drawImage.mock.calls.length);component.unmount();
  });
  it('closes late decodes after unmount without drawing',async()=>{
    let complete!:(bitmap:ImageBitmap)=>void;
    vi.stubGlobal('createImageBitmap',vi.fn(()=>new Promise<ImageBitmap>(resolve=>{complete=resolve;})));
    const api=harness();const component=render(<TwinViewport api={api as unknown as TwinPulseApi}/>);
    await waitFor(()=>expect(createImageBitmap).toHaveBeenCalledTimes(1));component.unmount();
    await act(async()=>{complete({width:960,height:640,close} as unknown as ImageBitmap);});
    expect(close).toHaveBeenCalledTimes(1);expect(drawing.drawImage).not.toHaveBeenCalled();
  });
  it('closes dimension-mismatched decodes and reports a visible error',async()=>{
    vi.stubGlobal('createImageBitmap',vi.fn(async()=>({width:1,height:1,close})));
    const api=harness();const component=render(<TwinViewport api={api as unknown as TwinPulseApi}/>);
    expect(await screen.findByRole('alert')).toHaveProperty('textContent',expect.stringContaining('dimensions'));
    expect(close).toHaveBeenCalledTimes(1);expect(drawing.drawImage).not.toHaveBeenCalled();component.unmount();
  });
  it('reports one typed display failure, retains its ID and clears only the current UI error on recovery',async()=>{
    const api={...harness(),viewportObservation:vi.fn(async()=>({execution_id:'display-id',physical_authority:false}))};
    api.viewportImage.mockRejectedValue(new Error('HTTP 503'));
    const report=vi.fn(),diagnose=vi.fn();
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi} report={report} diagnose={diagnose}/>);
    fireEvent.click(await screen.findByRole('button',{name:'View display diagnostics'}));
    expect(diagnose).toHaveBeenCalledWith('display-id');
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve,350));});
    expect(api.viewportObservation).toHaveBeenCalledTimes(1);
    expect(report.mock.calls.at(-1)?.[0]).toEqual({code:'viewport_http_error',execution_id:'display-id'});
    expect(api.command).not.toHaveBeenCalled();expect(api.viewportCamera).not.toHaveBeenCalled();
    api.viewportImage.mockResolvedValue(new Blob(['image'],{type:'image/jpeg'}));
    await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});
    expect(report.mock.calls.at(-1)?.[0]).toBeNull();expect(screen.queryByRole('alert')).toBeNull();component.unmount();
  });
  it('keeps a local display error when diagnosis delivery fails without retrying the POST',async()=>{
    const api={...harness(),viewportObservation:vi.fn(async()=>{throw new Error('diagnostics offline');})};
    api.viewportImage.mockRejectedValue(new Error('HTTP 503'));
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi}/>);
    await screen.findByRole('alert');
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve,350));});
    expect(api.viewportObservation).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('alert').textContent).toContain('Browser display is unavailable');component.unmount();
  });
  it('keeps still-fresh pixels across the normal metadata/image replacement race, then recovers without a false fault',async()=>{
    let sequence=0;const api={...harness(),viewportObservation:vi.fn()};
    api.viewportState.mockImplementation(async()=>view(++sequence));
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi}/>);
    await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});
    api.viewportImage.mockRejectedValue(Object.assign(new Error('Frame replaced'),{code:'viewport_frame_expired'}));
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve,350));});
    expect(screen.queryByRole('img')).toBeTruthy();expect(screen.queryByRole('alert')).toBeNull();
    expect(api.viewportObservation).not.toHaveBeenCalled();
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve,800));});
    expect(screen.getByRole('img',{name:'Last Isaac preview · not live'})).toBeTruthy();
    expect((screen.getByRole('button',{name:'Orbit left'}) as HTMLButtonElement).disabled).toBe(true);
    api.viewportImage.mockResolvedValue(new Blob(['image'],{type:'image/jpeg'}));
    await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});component.unmount();
  });
  it('does not resend the same optional diagnosis after recovery and recurrence in the same scene',async()=>{
    let sequence=0;const api={...harness(),viewportObservation:vi.fn(async()=>({execution_id:'same-id',physical_authority:false}))};
    api.viewportState.mockImplementation(async()=>view(++sequence));
    api.viewportImage.mockRejectedValue(new Error('HTTP 503'));
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi}/>);
    await screen.findByRole('button',{name:'View display diagnostics'});
    api.viewportImage.mockResolvedValue(new Blob(['image'],{type:'image/jpeg'}));
    await screen.findByRole('img');api.viewportImage.mockRejectedValue(new Error('HTTP 503'));
    await screen.findByRole('button',{name:'View display diagnostics'});
    expect(api.viewportObservation).toHaveBeenCalledTimes(1);component.unmount();
  });
  it('continues receiving images while optional diagnosis is pending and ignores its late UI result',async()=>{
    let complete!:(value:{execution_id:string;physical_authority:false})=>void;
    const api={...harness(),viewportObservation:vi.fn(()=>new Promise<{execution_id:string;physical_authority:false}>(resolve=>{complete=resolve;}))};
    api.viewportImage.mockRejectedValueOnce(new Error('HTTP 503'));
    const report=vi.fn();
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi} report={report}/>);
    await screen.findByRole('alert');
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve,320));});
    expect(screen.queryByRole('img')).toBeTruthy();
    expect(api.viewportObservation).toHaveBeenCalledTimes(1);
    await act(async()=>{complete({execution_id:'late-display-id',physical_authority:false});});
    expect(screen.queryByRole('alert')).toBeNull();expect(report.mock.calls.at(-1)?.[0]).toBeNull();
    // The late ID still belongs to the recorded failure if that fault recurs.
    api.viewportState.mockImplementation(async()=>view(2));api.viewportImage.mockRejectedValue(new Error('HTTP 503'));
    await screen.findByRole('button',{name:'View display diagnostics'});
    expect(report.mock.calls.at(-1)?.[0]).toEqual({code:'viewport_http_error',execution_id:'late-display-id'});
    expect(api.viewportObservation).toHaveBeenCalledTimes(1);component.unmount();
  });
  it.each(['image','decode'] as const)('does not report a late %s failure after generation switches to another candidate',async stage=>{
    const api={...harness(),viewportObservation:vi.fn()},report=vi.fn();let revision='rev',sequence=1,fail!:(error:Error)=>void;
    const generation:NonNullable<ConversationState['generation']>={operation_id:'generation',origin_message_id:'same-photo',state:'running',summary:'Working',can_cancel:true,started_at:'now',last_progress_at:'now',error:null,
      progress:{generation_preview:{schema_version:'generation-preview-1.0',state:'ready',candidate_revision:'candidate-a',scene_revision:'rev',rendered_count:1,pending_count:1,inventory_count:2,preview_only:true,physical_authority:false}}};
    api.viewportState.mockImplementation(async()=>({...view(sequence),frame:{...view(sequence).frame!,applied_revision:revision}}));
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi} generation={generation} report={report}/>);
    await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});
    if(stage==='image')api.viewportImage.mockImplementationOnce(()=>new Promise((_resolve,reject)=>{fail=reject;}));
    else vi.mocked(createImageBitmap).mockImplementationOnce(()=>new Promise((_resolve,reject)=>{fail=reject;}));
    sequence=2;await waitFor(()=>expect(fail).toBeTypeOf('function'));
    revision='new-rev';sequence=3;
    component.rerender(<TwinViewport api={api as unknown as TwinPulseApi} generation={{...generation,progress:{generation_preview:{...generation.progress!.generation_preview!,candidate_revision:'candidate-b',scene_revision:'new-rev'}}}} report={report}/>);
    await act(async()=>{fail(new Error(`Previous candidate ${stage} failed late`));});
    expect(screen.queryByRole('alert')).toBeNull();expect(api.viewportObservation).not.toHaveBeenCalled();
    expect(report.mock.calls.filter(([fault])=>fault!==null)).toHaveLength(0);
    await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});expect(api.viewportObservation).not.toHaveBeenCalled();component.unmount();
  });
  it('retires a prior candidate fault before its diagnosis ACK can reintroduce it',async()=>{
    let finish!:(value:{execution_id:string;physical_authority:false})=>void;
    const api={...harness(),viewportObservation:vi.fn(()=>new Promise<{execution_id:string;physical_authority:false}>(resolve=>{finish=resolve;}))};
    api.viewportImage.mockRejectedValue(new Error('Candidate A image failed'));
    const generation:NonNullable<ConversationState['generation']>={operation_id:'generation',origin_message_id:'same-photo',state:'running',summary:'Working',can_cancel:true,started_at:'now',last_progress_at:'now',error:null,
      progress:{generation_preview:{schema_version:'generation-preview-1.0',state:'ready',candidate_revision:'candidate-a',scene_revision:'rev',rendered_count:1,pending_count:1,inventory_count:2,preview_only:true,physical_authority:false}}};
    const report=vi.fn();const component=render(<TwinViewport api={api as unknown as TwinPulseApi} generation={generation} report={report}/>);
    await screen.findByRole('alert');expect(api.viewportObservation).toHaveBeenCalledOnce();
    api.viewportState.mockImplementation(()=>new Promise(()=>{}));
    component.rerender(<TwinViewport api={api as unknown as TwinPulseApi} generation={{...generation,progress:{generation_preview:{...generation.progress!.generation_preview!,candidate_revision:'candidate-b',scene_revision:'new-rev'}}}} report={report}/>);
    expect(screen.queryByRole('alert')).toBeNull();expect(report.mock.calls.at(-1)?.[0]).toBeNull();
    await act(async()=>{finish({execution_id:'old-candidate-diagnostic',physical_authority:false});});
    expect(report.mock.calls.at(-1)?.[0]).toBeNull();expect(screen.queryByRole('button',{name:'View display diagnostics'})).toBeNull();component.unmount();
  });
  it('handles an explicitly discarded same-frame observation as superseded while retaining a static preview without camera authority',async()=>{
    type Result={execution_id:string|null;physical_authority:false;disposition:'discarded';reason:'scene_superseded'};
    let finish!:(value:Result)=>void,sequence=1;
    const api={...harness(),viewportObservation:vi.fn(()=>new Promise<Result>(resolve=>{finish=resolve;}))},report=vi.fn();
    api.viewportState.mockImplementation(async()=>view(sequence));const component=render(<TwinViewport api={api as unknown as TwinPulseApi} report={report}/>);
    const canvas=await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});
    sequence=2;api.viewportImage.mockRejectedValue(new Error('Image read interrupted by scene change'));await screen.findByRole('alert');
    await act(async()=>{finish({execution_id:null,physical_authority:false,disposition:'discarded',reason:'scene_superseded'});});
    expect(screen.queryByRole('alert')).toBeNull();expect(screen.getByRole('img',{name:'Last Isaac preview · not live'})).toBe(canvas);
    expect(screen.getByRole('button',{name:'Orbit left'})).toHaveProperty('disabled',true);expect(report.mock.calls.at(-1)?.[0]).toBeNull();
    expect(screen.getByText(/display observation belonged to an earlier scene/)).toBeTruthy();
    sequence=3;api.viewportImage.mockResolvedValue(new Blob(['image'],{type:'image/jpeg'}));await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});
    expect(screen.queryByText(/display observation belonged to an earlier scene/)).toBeNull();expect(api.command).not.toHaveBeenCalled();component.unmount();
  });
  it('does not let a late discarded observation retire a newly recovered current frame',async()=>{
    type Result={execution_id:null;physical_authority:false;disposition:'discarded';reason:'scene_superseded'};
    let finish!:(value:Result)=>void,sequence=1;
    const api={...harness(),viewportObservation:vi.fn(()=>new Promise<Result>(resolve=>{finish=resolve;}))},report=vi.fn();
    api.viewportImage.mockRejectedValueOnce(new Error('Old image failure'));api.viewportState.mockImplementation(async()=>view(sequence++));
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi} report={report}/>);await screen.findByRole('alert');
    const canvas=await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});
    await act(async()=>{finish({execution_id:null,physical_authority:false,disposition:'discarded',reason:'scene_superseded'});});
    expect(screen.getByRole('img',{name:'Current Isaac Digital Twin render'})).toBe(canvas);
    expect(screen.getByRole('button',{name:'Orbit left'})).toHaveProperty('disabled',false);expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.queryByText(/display observation belonged to an earlier scene/)).toBeNull();expect(report.mock.calls.at(-1)?.[0]).toBeNull();component.unmount();
  });
  it('does not let a discarded older frame clear a newer genuine failure of the same scene and cause',async()=>{
    type Result={execution_id:string|null;physical_authority:false;disposition:'recorded'|'discarded';reason?:'scene_superseded'};
    let finish!:(value:Result)=>void,sequence=1;
    const api={...harness(),viewportObservation:vi.fn<(_body:unknown)=>Promise<Result>>().mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;})).mockResolvedValue({execution_id:'newer-failure',physical_authority:false,disposition:'recorded'})};
    api.viewportImage.mockRejectedValue(new Error('Current frame image failed'));api.viewportState.mockImplementation(async()=>view(sequence));
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi}/>);await screen.findByRole('alert');sequence=2;
    await waitFor(()=>expect(api.viewportImage.mock.calls.some(([id])=>id===2)).toBe(true));
    await act(async()=>{finish({execution_id:null,physical_authority:false,disposition:'discarded',reason:'scene_superseded'});});
    expect(screen.getByRole('alert').textContent).toContain('Current frame image failed');
    expect(screen.queryByText(/display observation belonged to an earlier scene/)).toBeNull();
    await screen.findByRole('button',{name:'View display diagnostics'});expect(api.viewportObservation).toHaveBeenCalledTimes(2);
    expect(api.viewportObservation.mock.calls[1][0]).toMatchObject({frame_id:2});component.unmount();
  });
  it('keeps a genuine static-preview decode error visible without attributing it to a different live frame',async()=>{
    const previewFrame={...view(18).frame!,applied_revision:'partial-rev',sha256:'a'.repeat(64),url:`/v1/product/viewport/preview/${'a'.repeat(64)}`,preview_only:true as const,physical_authority:false as const};
    const api={...harness(),viewportObservation:vi.fn(),viewportPreviewImage:vi.fn(async()=>new Blob(['image'],{type:'image/jpeg'}))};
    api.viewportState.mockResolvedValue({...view(),last_frame:previewFrame});
    vi.mocked(createImageBitmap).mockRejectedValue(new Error('Static preview decoder failed'));
    const generation:NonNullable<ConversationState['generation']>={operation_id:'generation',state:'failed',summary:'Stopped',can_cancel:false,started_at:'now',last_progress_at:'now',error:null,
      progress:{generation_preview:{schema_version:'generation-preview-1.0',state:'blocked',error_code:'PREVIEW_REBUILD_REQUIRED',candidate_revision:'partial',scene_revision:'partial-rev',rendered_count:1,pending_count:1,inventory_count:2,preview_only:true,physical_authority:false}}};
    const report=vi.fn();const component=render(<TwinViewport api={api as unknown as TwinPulseApi} generation={generation} report={report}/>);
    expect((await screen.findByRole('alert')).textContent).toContain('Static preview decoder failed');
    expect(api.viewportObservation).not.toHaveBeenCalled();expect(report.mock.calls.at(-1)?.[0]).toEqual({code:'viewport_decode_failed',execution_id:null});
    expect(screen.getByRole('button',{name:'Orbit left'})).toHaveProperty('disabled',true);component.unmount();
  });
  it.each(['engine_session_id','stage_epoch','applied_revision'] as const)('retires prior pixels to preview on %s change even across a normal image replacement race',async field=>{
    const api={...harness(),viewportObservation:vi.fn()};
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi}/>);
    await screen.findByRole('img');
    api.viewportState.mockImplementation(async()=>{const next=view(2);next.frame![field]='new-identity';return next;});
    api.viewportImage.mockRejectedValue(Object.assign(new Error('Frame replaced'),{code:'viewport_frame_expired'}));
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve,220));});
    expect(screen.queryByRole('img',{name:'Current Isaac Digital Twin render'})).toBeNull();
    expect(screen.getByRole('img',{name:'Last Isaac preview · not live'}).getAttribute('data-frame-id')).toBe('1');
    expect((screen.getByRole('button',{name:'Orbit left'}) as HTMLButtonElement).disabled).toBe(true);
    expect(api.viewportObservation).not.toHaveBeenCalled();expect(api.viewportCamera).not.toHaveBeenCalled();
    api.viewportImage.mockResolvedValue(new Blob(['image'],{type:'image/jpeg'}));
    await screen.findByRole('img');component.unmount();
  });
  it('invalidates the prior API pixels before waiting for a replacement API response',async()=>{
    const old=harness();const component=render(<TwinViewport api={old as unknown as TwinPulseApi}/>);
    await screen.findByRole('img');
    const next=harness();next.viewportState.mockImplementation(()=>new Promise(()=>{}));
    component.rerender(<TwinViewport api={next as unknown as TwinPulseApi}/>);
    expect(screen.queryByRole('img')).toBeNull();expect((screen.getByRole('button',{name:'Orbit left'}) as HTMLButtonElement).disabled).toBe(true);
    component.unmount();
  });
  it('loads a saved stale preview once with its own receipt and never grants camera authority',async()=>{
    const frame={...view(18).frame!,captured_at_ms:Date.now()-60000,sha256:'a'.repeat(64),
      url:`/v1/product/viewport/preview/${'a'.repeat(64)}`,preview_only:true as const,physical_authority:false as const};
    const api={...harness(),viewportPreviewImage:vi.fn(async()=>new Blob(['image'],{type:'image/jpeg'}))};
    api.viewportState.mockResolvedValue({...view(),state:'stale',frame:null,last_frame:frame});
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi} projectId="project-a"/>);
    expect((await screen.findByRole('img',{name:'Last Isaac preview · not live'})).getAttribute('data-frame-id')).toBe('18');
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve,330));});
    expect(api.viewportPreviewImage).toHaveBeenCalledTimes(1);expect(api.viewportPreviewImage).toHaveBeenCalledWith('a'.repeat(64));
    expect(api.viewportImage).not.toHaveBeenCalled();expect(createImageBitmap).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button',{name:'Orbit left'}));expect(api.viewportCamera).not.toHaveBeenCalled();
    expect(screen.getByText(/Static preview from revision rev/)).toBeTruthy();component.unmount();
  });
  it('uses only the exact candidate static receipt when a completed preview requires rebuilding',async()=>{
    const sha='c'.repeat(64),frame={...view(18).frame!,captured_at_ms:Date.now()-60000,sha256:sha,
      url:`/v1/product/viewport/preview/${sha}`,preview_only:true as const,physical_authority:false as const};
    const api={...harness(),viewportPreviewImage:vi.fn(async()=>new Blob(['candidate'],{type:'image/jpeg'})),
      viewportImageFrame:vi.fn(async()=>({state:view(99),image:new Blob(['current'],{type:'image/jpeg'})}))};
    let matching=false;api.viewportState.mockImplementation(async()=>({...view(99),last_frame:{...frame,applied_revision:matching?'rev':'another-candidate'}}));
    const generation:NonNullable<ConversationState['generation']>={operation_id:'rollback',state:'completed',summary:'Best candidate retained',can_cancel:false,
      started_at:'now',last_progress_at:'now',error:null,progress:{generation_preview:{schema_version:'generation-preview-1.0',state:'blocked',
        error_code:'PREVIEW_REBUILD_REQUIRED',candidate_revision:'best-candidate',scene_revision:'rev',rendered_count:2,pending_count:1,inventory_count:3,
        preview_only:true,physical_authority:false}}};
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi} generation={generation}/>);
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve,180));});
    expect(screen.queryByRole('img')).toBeNull();expect(api.viewportPreviewImage).not.toHaveBeenCalled();
    expect(screen.getByText(/Candidate rebuild required · no exact static preview decoded/)).toBeTruthy();
    matching=true;
    expect((await screen.findByRole('img',{name:'Last Isaac preview · not live'})).getAttribute('data-frame-id')).toBe('18');
    expect(screen.getByText(/Exact candidate static preview · rebuild required/)).toBeTruthy();
    expect(api.viewportPreviewImage).toHaveBeenCalledWith(sha);expect(api.viewportImageFrame).not.toHaveBeenCalled();expect(api.viewportImage).not.toHaveBeenCalled();
    expect(screen.getByRole('button',{name:'Orbit left'})).toHaveProperty('disabled',true);expect(api.viewportCamera).not.toHaveBeenCalled();component.unmount();
  });
  it('retains already decoded same-input pixels while a different best candidate awaits rebuild',async()=>{
    const api=harness();
    const generation:NonNullable<ConversationState['generation']>={operation_id:'same-input',origin_message_id:'source',
      state:'running',summary:'Creating',can_cancel:true,started_at:'now',last_progress_at:'now',error:null,
      progress:{generation_preview:{schema_version:'generation-preview-1.0',state:'ready',candidate_revision:'first',
        scene_revision:'rev',rendered_count:2,pending_count:1,inventory_count:3,preview_only:true,physical_authority:false}}};
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi} generation={generation}/>);
    const canvas=await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});
    component.rerender(<TwinViewport api={api as unknown as TwinPulseApi} generation={{...generation,state:'failed',can_cancel:false,
      progress:{generation_preview:{...generation.progress!.generation_preview!,candidate_revision:'best',scene_revision:'restored',
        state:'blocked',error_code:'PREVIEW_REBUILD_REQUIRED'}}}}/>);
    expect(screen.getByRole('img',{name:'Last Isaac preview · not live'})).toBe(canvas);
    expect(screen.getByText(/last decoded earlier candidate shown, not the restored scene/)).toBeTruthy();
    expect(screen.getByRole('button',{name:'Orbit left'})).toHaveProperty('disabled',true);
    expect(screen.getByText(/Static preview from revision rev/)).toBeTruthy();
    component.unmount();
  });
  it('retires a recovered metadata-only fault while rollback still rejects the old receipt',async()=>{
    const api=harness(),report=vi.fn();let metadataFails=false;
    api.viewportState.mockImplementation(async()=>{
      if(metadataFails)throw new Error('Local state read exceeded 3 seconds.');
      return view();
    });
    const generation:NonNullable<ConversationState['generation']>={operation_id:'same-input',origin_message_id:'source',
      state:'running',summary:'Creating',can_cancel:true,started_at:'now',last_progress_at:'now',error:null,
      progress:{generation_preview:{schema_version:'generation-preview-1.0',state:'ready',candidate_revision:'first',
        scene_revision:'rev',rendered_count:2,pending_count:1,inventory_count:3,preview_only:true,physical_authority:false}}};
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi} generation={generation} report={report}/>);
    const canvas=await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});
    metadataFails=true;
    expect((await screen.findByRole('alert')).textContent).toContain('Local state read exceeded');
    component.rerender(<TwinViewport api={api as unknown as TwinPulseApi} generation={{...generation,state:'failed',can_cancel:false,
      progress:{generation_preview:{...generation.progress!.generation_preview!,candidate_revision:'best',scene_revision:'restored',
        state:'blocked',error_code:'PREVIEW_REBUILD_REQUIRED'}}}} report={report}/>);
    const drawn=drawing.drawImage.mock.calls.length;
    metadataFails=false;
    await waitFor(()=>expect(screen.queryByRole('alert')).toBeNull());
    expect(report.mock.calls.at(-1)?.[0]).toBeNull();
    expect(screen.getByRole('img',{name:'Last Isaac preview · not live'})).toBe(canvas);
    expect(drawing.drawImage).toHaveBeenCalledTimes(drawn);
    expect(screen.getByRole('button',{name:'Orbit left'})).toHaveProperty('disabled',true);
    expect(api.viewportCamera).not.toHaveBeenCalled();component.unmount();
  });
  it('clears only a metadata fault when the recovered response has no current or static frame',async()=>{
    const api=harness(),report=vi.fn();let metadataFails=true;
    api.viewportState.mockImplementation(async()=>{
      if(metadataFails)throw new Error('Local state read exceeded 3 seconds.');
      return {...view(),state:'waiting',frame:null,last_frame:null};
    });
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi} report={report}/>);
    await screen.findByRole('alert');metadataFails=false;
    await waitFor(()=>expect(screen.queryByRole('alert')).toBeNull());
    expect(report.mock.calls.at(-1)?.[0]).toBeNull();expect(screen.queryByRole('img')).toBeNull();
    expect(screen.getByRole('button',{name:'Orbit left'})).toHaveProperty('disabled',true);
    expect(api.viewportImage).not.toHaveBeenCalled();expect(api.viewportCamera).not.toHaveBeenCalled();component.unmount();
  });
  it('retires a metadata fault before reusing the same authenticated static pixels',async()=>{
    const sha='e'.repeat(64),live={...view(),frame:{...view().frame!,sha256:sha}};
    const last={...live.frame!,url:`/v1/product/viewport/preview/${sha}`,preview_only:true as const,physical_authority:false as const};
    const api={...harness(),viewportPreviewImage:vi.fn(async()=>new Blob(['static'],{type:'image/jpeg'}))},report=vi.fn();
    let phase='live';api.viewportState.mockImplementation(async()=>{
      if(phase==='fault')throw new Error('Local state read exceeded 3 seconds.');
      return phase==='live'?live:{...live,state:'stale',frame:null,last_frame:last};
    });
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi} report={report}/>);
    const canvas=await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});
    phase='fault';await screen.findByRole('alert');phase='static';
    await waitFor(()=>expect(screen.queryByRole('alert')).toBeNull());
    expect(screen.getByRole('img',{name:'Last Isaac preview · not live'})).toBe(canvas);
    expect(createImageBitmap).toHaveBeenCalledTimes(1);expect(api.viewportPreviewImage).not.toHaveBeenCalled();
    expect(report.mock.calls.at(-1)?.[0]).toBeNull();
    expect(screen.getByRole('button',{name:'Orbit left'})).toHaveProperty('disabled',true);component.unmount();
  });
  it('waits for new metadata after an exact static-preview replacement without reporting a display fault',async()=>{
    const sha='f'.repeat(64),frame={...view().frame!,sha256:sha,url:`/v1/product/viewport/preview/${sha}`,
      preview_only:true as const,physical_authority:false as const};
    const api={...harness(),viewportPreviewImage:vi.fn(async()=>{throw {code:'viewport_preview_expired'};})},report=vi.fn();
    api.viewportState.mockImplementation(async()=>({...view(),state:'stale',frame:null,last_frame:frame}));
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi} report={report}/>);
    await waitFor(()=>expect(api.viewportPreviewImage.mock.calls.length).toBeGreaterThan(1));
    expect(screen.queryByRole('alert')).toBeNull();
    expect(report.mock.calls.filter(([fault])=>fault!==null)).toHaveLength(0);
    expect(api.viewportCamera).not.toHaveBeenCalled();component.unmount();
  });
  it('does not retire a genuine decode fault merely because metadata requests keep succeeding',async()=>{
    const api=harness(),report=vi.fn();let sequence=1;
    api.viewportState.mockImplementation(async()=>view(sequence));
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi} report={report}/>);
    await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});
    vi.mocked(createImageBitmap).mockRejectedValue(new Error('Actual decoder failure'));sequence=2;
    await screen.findByRole('alert');const readCount=api.viewportState.mock.calls.length;
    await waitFor(()=>expect(api.viewportState.mock.calls.length).toBeGreaterThan(readCount+1));
    expect(screen.getByRole('alert').textContent).toContain('Actual decoder failure');
    expect(report.mock.calls.at(-1)?.[0]).toEqual({code:'viewport_decode_failed',execution_id:null});
    expect(screen.getByRole('button',{name:'Orbit left'})).toHaveProperty('disabled',true);
    component.unmount();
  });
  it('retains photo and camera positions when the same decoded JPEG is rebound to a checked static candidate',async()=>{
    const sha='d'.repeat(64),live={...view(1),frame:{...view(1).frame!,sha256:sha}};
    const frame={...live.frame!,url:`/v1/product/viewport/preview/${sha}`,preview_only:true as const,physical_authority:false as const};
    const api={...harness(),viewportPreviewImage:vi.fn(async()=>new Blob(['candidate'],{type:'image/jpeg'}))};
    api.viewportState.mockResolvedValue(live);
    const generation:NonNullable<ConversationState['generation']>={operation_id:'same',state:'completed',summary:'Ready',can_cancel:false,
      started_at:'now',last_progress_at:'now',error:null,progress:{generation_preview:{schema_version:'generation-preview-1.0',state:'ready',
        candidate_revision:'same-candidate',scene_revision:'rev',rendered_count:2,pending_count:0,inventory_count:2,preview_only:true,physical_authority:false}}};
    const sourcePhoto={url:'/v1/product/conversation/image/source',name:'room.jpg'};
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi} generation={generation} sourcePhoto={sourcePhoto}/>);
    const canvas=await screen.findByRole('img',{name:'Current Isaac Digital Twin render'}),photo=await screen.findByRole('img',{name:'Source photo: room.jpg'});
    const controls=screen.getByLabelText('Camera controls'),caption=component.container.querySelector('.twin-frame-caption');
    const children=Array.from(controls.parentElement!.children),draws=drawing.drawImage.mock.calls.length;
    api.viewportState.mockResolvedValue({...live,last_frame:frame});
    component.rerender(<TwinViewport api={api as unknown as TwinPulseApi} sourcePhoto={{...sourcePhoto}} generation={{...generation,progress:{
      generation_preview:{...generation.progress!.generation_preview!,state:'blocked',error_code:'PREVIEW_REBUILD_REQUIRED'}}}}/>);
    expect(await screen.findByRole('img',{name:'Last Isaac preview · not live'})).toBe(canvas);
    expect(api.viewportPreviewImage).not.toHaveBeenCalled();expect(drawing.drawImage).toHaveBeenCalledTimes(draws);
    expect(screen.getByRole('img',{name:'Source photo: room.jpg'})).toBe(photo);expect(api.conversationImage).toHaveBeenCalledTimes(1);
    expect(component.container.querySelector('.twin-frame-caption')).toBe(caption);expect(Array.from(controls.parentElement!.children)).toEqual(children);
    expect(screen.getByRole('button',{name:'Orbit left'})).toHaveProperty('disabled',true);component.unmount();
  });
  it('keeps one source-photo DOM node through metadata-first delayed image delivery and generation changes',async()=>{
    let metadata=view(1),finish!:(packet:{state:ViewportState;image:Blob})=>void;
    const api={...harness(),viewportImageFrame:vi.fn(async()=>({state:metadata,image:new Blob(['frame'],{type:'image/jpeg'})}))};
    api.viewportState.mockImplementation(async()=>metadata);
    const sourcePhoto={url:'/v1/product/conversation/image/source',name:'room.jpg'};
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi} sourcePhoto={sourcePhoto}/>);
    const photo=await screen.findByRole('img',{name:'Source photo: room.jpg'}),figure=photo.parentElement;
    const firstCanvas=await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});
    const frameSlot=firstCanvas.parentElement;
    expect(frameSlot?.classList.contains('twin-frame-slot')).toBe(true);
    expect(frameSlot?.parentElement?.classList.contains('twin-render-grid')).toBe(true);
    expect(frameSlot?.parentElement?.nextElementSibling).toBe(photo.closest('figure'));
    expect(screen.getByRole('img',{name:'Source photo: room.jpg'})).toBe(photo);
    metadata=view(2);
    api.viewportImageFrame.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}));
    await waitFor(()=>expect(api.viewportImageFrame).toHaveBeenCalledTimes(2));
    expect(screen.getByRole('img',{name:'Current Isaac Digital Twin render'}).getAttribute('data-frame-id')).toBe('1');
    expect(screen.getByRole('img',{name:'Source photo: room.jpg'})).toBe(photo);expect(photo.parentElement).toBe(figure);
    expect((screen.getByRole('button',{name:'Orbit left'}) as HTMLButtonElement).disabled).toBe(false);
    await act(async()=>{finish({state:metadata,image:new Blob(['new-frame'],{type:'image/jpeg'})});});
    expect((await screen.findByRole('img',{name:'Current Isaac Digital Twin render'})).getAttribute('data-frame-id')).toBe('2');
    const generation:NonNullable<ConversationState['generation']>={operation_id:'same-job',state:'running',summary:'Repairing',can_cancel:true,
      started_at:'now',last_progress_at:'now',error:null,progress:{stage:'repair',generation_preview:{schema_version:'generation-preview-1.0',
        state:'building',candidate_revision:'candidate',scene_revision:null,rendered_count:2,pending_count:2,inventory_count:4,
        preview_only:true,physical_authority:false}}};
    component.rerender(<TwinViewport api={api as unknown as TwinPulseApi} sourcePhoto={{...sourcePhoto}} generation={generation}/>);
    expect(screen.getByRole('img',{name:'Source photo: room.jpg'})).toBe(photo);
    component.rerender(<TwinViewport api={api as unknown as TwinPulseApi} sourcePhoto={{...sourcePhoto}} generation={{...generation,state:'failed',
      error:{code:'REPAIR_STALLED',message:'No further valid correction'}}}/>);
    expect(screen.getByRole('img',{name:'Source photo: room.jpg'})).toBe(photo);expect(photo.parentElement).toBe(figure);
    expect(api.viewportCamera).not.toHaveBeenCalled();expect(api.command).not.toHaveBeenCalled();component.unmount();
  });
  it('shows completed parameters separately from a shell-only confirmed render and retains pending identities and reasons',async()=>{
    const api=harness();const component=render(<TwinViewport api={api as unknown as TwinPulseApi} generation={{
      operation_id:'geometry-pending',state:'running',summary:'Checking geometry',can_cancel:true,started_at:'now',last_progress_at:'now',error:null,
      progress:{stage:'final_validation',generation_preview:{schema_version:'generation-preview-1.0',state:'ready',candidate_revision:'candidate',
        scene_revision:'rev',rendered_count:0,pending_count:12,inventory_count:12,preview_only:true,physical_authority:false,
        pending_objects:[{id:'lamp',reason_code:'PARENT_NOT_READY',blocked_by:['desk']},{id:'desk',reason_code:'GEOMETRY_CHECK_FAILED'}]},
        inventory_progress:{schema_version:'inventory-work-progress-1.0',observed_instances:12,inventory_count:12,parameterized_count:12,
          pending_count:0,parameter_batch_size:6,inventory_planned:true,parameters_complete:true,checkpoint_saved:false,
          automatic_resume:false,physical_authority:false}}}}/>);
    await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});
    const progress=screen.getByRole('status',{name:'Twin generation progress'});
    expect(progress.textContent).toContain('Parameters: 12 of 12 objects prepared · 0 awaiting parameters');
    expect(progress.textContent).toContain('Last confirmed 3D: 0 of 12 objects rendered · 12 not rendered');
    const previewDetails=screen.getByText('Preview details').closest('details')!;
    expect(previewDetails.open).toBe(false);expect(previewDetails.textContent).toContain('Confirmed preview revision: rev');
    expect(previewDetails.textContent).toContain('Candidate revision: candidate');
    expect(progress.textContent).toContain('lamp · parent not ready · waiting for: desk');
    expect(progress.textContent).toContain('desk · geometry check failed');expect(progress.textContent).toContain('The full inventory is retained');
    expect(progress.textContent).toContain('Incomplete · Preview');expect(progress.textContent).not.toContain('12 of 12 objects rendered');
    expect(api.command).not.toHaveBeenCalled();component.unmount();
  });
  it('keeps room-shell progress separate from observations before the object inventory is planned',()=>{
    const api=harness();api.viewportState.mockResolvedValue({...view(),state:'waiting',frame:null});
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi} generation={{operation_id:'room-shell',state:'running',
      summary:'Preparing the room',can_cancel:true,started_at:'now',last_progress_at:'now',error:null,progress:{stage:'room',
        generation_preview:{schema_version:'generation-preview-1.0',state:'ready',candidate_revision:'room-candidate',scene_revision:'room',
          rendered_count:0,pending_count:0,inventory_count:0,preview_only:true,physical_authority:false},
        inventory_progress:{schema_version:'inventory-work-progress-1.0',observed_instances:24,inventory_count:0,parameterized_count:0,
          pending_count:0,parameter_batch_size:6,inventory_planned:false,parameters_complete:false,checkpoint_saved:false,
          automatic_resume:false,physical_authority:false}}}}/>);
    const progress=screen.getByRole('status',{name:'Twin generation progress'});
    expect(progress.textContent).toContain('Preparing the room shell');expect(progress.textContent).toContain('Observation: 24 provisional instances');
    expect(progress.textContent).toContain('object inventory not planned');expect(progress.textContent).toContain('Parameters: 0 objects prepared · awaiting inventory');
    expect(progress.textContent).toContain('room shell only');expect(progress.textContent).toContain('Incomplete · Preview');component.unmount();
  });
  it.each(['project','operation','api'] as const)('does not reuse confirmed object counts after %s replacement',async replacement=>{
    const api=harness(),building:NonNullable<ConversationState['generation']>={operation_id:'same-job',state:'running',summary:'Working',can_cancel:true,
      started_at:'now',last_progress_at:'now',error:null,progress:{generation_preview:{schema_version:'generation-preview-1.0',state:'building',
        candidate_revision:'next',scene_revision:null,rendered_count:8,pending_count:4,inventory_count:12,preview_only:true,physical_authority:false}}};
    const ready={...building,progress:{generation_preview:{...building.progress!.generation_preview!,state:'ready' as const,scene_revision:'rev',rendered_count:6,pending_count:6}}};
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi} projectId="a" generation={ready}/>);
    await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});
    component.rerender(<TwinViewport api={api as unknown as TwinPulseApi} projectId="a" generation={building}/>);
    expect(screen.getByRole('status',{name:'Twin generation progress'}).textContent).toContain('Last confirmed 3D: 6 of 12 objects rendered');
    component.rerender(<TwinViewport api={(replacement==='api'?harness():api) as unknown as TwinPulseApi}
      projectId={replacement==='project'?'b':'a'} generation={replacement==='operation'?{...building,operation_id:'new-job'}:building}/>);
    expect(screen.getByRole('status',{name:'Twin generation progress'}).textContent).toContain('Last confirmed 3D: not confirmed');component.unmount();
  });
  it('labels the prior scene as preview while a candidate builds and binds live display to its ready revision',async()=>{
    const api=harness();const component=render(<TwinViewport api={api as unknown as TwinPulseApi}/>);
    await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});
    const generation:NonNullable<ConversationState['generation']>={operation_id:'job',state:'running',summary:'Working',
      can_cancel:true,started_at:'now',last_progress_at:'now',error:null,progress:{stage:'objects',generation_preview:{
        schema_version:'generation-preview-1.0',state:'building',candidate_revision:'candidate',scene_revision:null,
        rendered_count:6,pending_count:6,inventory_count:12,preview_only:true,physical_authority:false}}};
    component.rerender(<TwinViewport api={api as unknown as TwinPulseApi} generation={generation}/>);
    expect(screen.getByRole('img',{name:'Last Isaac preview · not live'})).toBeTruthy();
    expect((screen.getByRole('button',{name:'Orbit left'}) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByRole('status',{name:'Twin generation progress'}).textContent).toContain('render not confirmed');
    generation.progress!.generation_preview={...generation.progress!.generation_preview!,state:'ready',scene_revision:'rev'};
    component.rerender(<TwinViewport api={api as unknown as TwinPulseApi} generation={{...generation}}/>);
    expect(screen.getByRole('img',{name:'Current Isaac Digital Twin render'})).toBeTruthy();
    expect(screen.getByRole('status',{name:'Twin generation progress'}).textContent).toContain('Last confirmed 3D: 6 of 12 objects rendered');
    generation.progress!.generation_preview={...generation.progress!.generation_preview!,state:'building',scene_revision:null,rendered_count:8,pending_count:4};
    component.rerender(<TwinViewport api={api as unknown as TwinPulseApi} generation={{...generation}}/>);
    expect(screen.getByRole('status',{name:'Twin generation progress'}).textContent).toContain('Last confirmed 3D: 6 of 12 objects rendered');
    expect(screen.getByRole('status',{name:'Twin generation progress'}).textContent).toContain('Candidate preview: 8 of 12 objects selected');
    expect(screen.getByRole('status',{name:'Twin generation progress'}).textContent).not.toContain('8 of 12 objects rendered');
    generation.progress!.generation_preview={...generation.progress!.generation_preview!,state:'blocked',scene_revision:'rev',rendered_count:6,pending_count:6,error_code:'bad_candidate'};
    component.rerender(<TwinViewport api={api as unknown as TwinPulseApi} generation={{...generation,state:'failed'}}/>);
    expect(screen.getByRole('img',{name:'Last Isaac preview · not live'})).toBeTruthy();
    expect(screen.getByRole('status',{name:'Twin generation progress'}).textContent).toContain('Last valid preview retained · current candidate blocked');
    expect((screen.getByRole('button',{name:'Orbit left'}) as HTMLButtonElement).disabled).toBe(true);component.unmount();
  });
  it('keeps the legacy completed generation live without inventing an incomplete result',async()=>{
    const api=harness();const component=render(<TwinViewport api={api as unknown as TwinPulseApi} generation={{
      operation_id:'old',state:'completed',summary:'Done',can_cancel:false,started_at:'now',last_progress_at:'now',error:null}}/>);
    await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});
    expect(screen.getByRole('status',{name:'Twin generation progress'}).textContent).toContain('Preview · generation complete');
    expect(screen.getByRole('status',{name:'Twin generation progress'}).textContent).not.toContain('Incomplete');component.unmount();
  });
  it('marks an explicitly completed empty-room preview complete with no pending inventory',async()=>{
    const api=harness();const component=render(<TwinViewport api={api as unknown as TwinPulseApi} savedScene={{revision:'rev',partial:false}} generation={{
      operation_id:'empty-room',state:'completed',summary:'Empty room ready',can_cancel:false,started_at:'now',last_progress_at:'now',error:null,
      progress:{generation_preview:{schema_version:'generation-preview-1.0',state:'ready',candidate_revision:'empty-candidate',
        scene_revision:'rev',rendered_count:0,pending_count:0,inventory_count:0,preview_only:true,physical_authority:false},
        inventory_progress:{schema_version:'inventory-work-progress-1.0',observed_instances:0,inventory_count:0,parameterized_count:0,
          pending_count:0,parameter_batch_size:6,inventory_planned:true,parameters_complete:true,checkpoint_saved:true,
          observation_saved:true,draft_saved:true,automatic_resume:false,physical_authority:false}}}}/>);
    await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});
    const progress=screen.getByRole('status',{name:'Twin generation progress'});
    expect(progress.textContent).toContain('Preview · generation complete');expect(progress.textContent).toContain('0 of 0 objects rendered');
    expect(progress.textContent).toContain('0 awaiting parameters');expect(progress.textContent).toContain('0 not rendered');
    expect(progress.textContent).toContain('Scene draft saved');
    expect(progress.textContent).not.toContain('Incomplete');expect(api.command).not.toHaveBeenCalled();component.unmount();
  });
  it('preserves the last pixels through a failed newer frame and clears the error on a new valid frame',async()=>{
    let sequence=0;const api=harness();api.viewportState.mockImplementation(async()=>view(++sequence));
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi}/>);
    const first=await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});const frame=first.getAttribute('data-frame-id');
    api.viewportImage.mockRejectedValue(new Error('JPEG unavailable'));
    await screen.findByRole('alert');expect(screen.getByRole('img',{name:'Last Isaac preview · not live'}).getAttribute('data-frame-id')).toBe(frame);
    expect((screen.getByRole('button',{name:'Zoom in'}) as HTMLButtonElement).disabled).toBe(true);
    api.viewportImage.mockResolvedValue(new Blob(['new-image'],{type:'image/jpeg'}));
    await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});expect(screen.queryByRole('alert')).toBeNull();component.unmount();
  });
  it('clears pixels on project replacement and ignores the old pending decoder',async()=>{
    const api=harness();const component=render(<TwinViewport api={api as unknown as TwinPulseApi} projectId="a"/>);
    await screen.findByRole('img');let finish!:(bitmap:ImageBitmap)=>void;
    vi.mocked(createImageBitmap).mockImplementationOnce(()=>new Promise<ImageBitmap>(resolve=>{finish=resolve;}));
    api.viewportState.mockImplementation(async()=>view(2));
    await waitFor(()=>expect(createImageBitmap).toHaveBeenCalledTimes(2));
    const drawn=drawing.drawImage.mock.calls.length;
    api.viewportState.mockImplementation(()=>new Promise(()=>{}));
    component.rerender(<TwinViewport api={api as unknown as TwinPulseApi} projectId="b"/>);
    expect(screen.queryByRole('img')).toBeNull();
    await act(async()=>{finish({width:960,height:640,close} as unknown as ImageBitmap);});
    expect(screen.queryByRole('img')).toBeNull();expect(drawing.drawImage).toHaveBeenCalledTimes(drawn);
    expect(close).toHaveBeenCalledTimes(2);component.unmount();
  });
  it('clears the previous input in the same project and rejects old live receipts until the new confirmed revision arrives',async()=>{
    const api=harness();let sequence=1,revision='rev';
    api.viewportState.mockImplementation(async()=>{const next=view(sequence++);next.frame!.applied_revision=revision;return next;});
    const original:NonNullable<ConversationState['generation']>={operation_id:'first',origin_message_id:'input-a',state:'completed',
      summary:'Ready',can_cancel:false,started_at:'now',last_progress_at:'now',error:null};
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi} projectId="same" generation={original}/>);
    await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});
    const decodes=vi.mocked(createImageBitmap).mock.calls.length;
    const next={...original,operation_id:'next',origin_message_id:'input-b',state:'running',can_cancel:true};
    component.rerender(<TwinViewport api={api as unknown as TwinPulseApi} projectId="same" generation={next}/>);
    expect(screen.queryByRole('img')).toBeNull();expect(screen.getByRole('button',{name:'Orbit left'})).toHaveProperty('disabled',true);
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve,180));});
    expect(screen.queryByRole('img')).toBeNull();expect(createImageBitmap).toHaveBeenCalledTimes(decodes);
    const ready={...next,progress:{generation_preview:{schema_version:'generation-preview-1.0' as const,state:'ready' as const,
      candidate_revision:'new-candidate',scene_revision:'new-rev',rendered_count:2,pending_count:1,inventory_count:3,
      preview_only:true as const,physical_authority:false as const}}};
    component.rerender(<TwinViewport api={api as unknown as TwinPulseApi} projectId="same" generation={ready}/>);
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve,180));});
    expect(screen.queryByRole('img')).toBeNull();expect(createImageBitmap).toHaveBeenCalledTimes(decodes);
    revision='new-rev';await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});
    expect(createImageBitmap).toHaveBeenCalledTimes(decodes+1);expect(api.viewportCamera).not.toHaveBeenCalled();component.unmount();
  });
  it.each([
    ['accepted','live'],['running','live'],['failed','live'],
    ['accepted','static'],['running','static'],['failed','static'],
  ] as const)('rejects old %s generation / %s receipts on reload before a confirmed preview exists',async(state,receipt)=>{
    const sha='a'.repeat(64),api={...harness(),viewportPreviewImage:vi.fn(async()=>new Blob(['image'],{type:'image/jpeg'}))};
    if(receipt==='static')api.viewportState.mockImplementation(async()=>({...view(),state:'stale',frame:null,last_frame:{...view(18).frame!,
      sha256:sha,url:`/v1/product/viewport/preview/${sha}`,preview_only:true,physical_authority:false}}));
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi} projectId="same" generation={{
      operation_id:'new-input',origin_message_id:'new-origin',state,summary:'No confirmed preview',can_cancel:state!=='failed',
      started_at:'now',last_progress_at:'now',error:null}}/>);
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve,180));});
    expect(screen.queryByRole('img')).toBeNull();expect(screen.getByText('No current 3D frame')).toBeTruthy();
    expect(screen.getByRole('status',{name:'Twin generation progress'}).textContent).toContain('waiting for a decoded Isaac frame');
    expect(api.viewportState.mock.calls.length).toBeGreaterThan(1);
    expect(api.viewportImage).not.toHaveBeenCalled();expect(api.viewportPreviewImage).not.toHaveBeenCalled();expect(createImageBitmap).not.toHaveBeenCalled();
    expect(screen.getByRole('button',{name:'Orbit left'})).toHaveProperty('disabled',true);component.unmount();
  });
  it('restores a saved incomplete static image only when its confirmed scene revision matches on initial mount',async()=>{
    const sha='b'.repeat(64),api={...harness(),viewportPreviewImage:vi.fn(async()=>new Blob(['image'],{type:'image/jpeg'}))};
    let revision='another-input';api.viewportState.mockImplementation(async()=>({...view(),state:'stale',frame:null,last_frame:{...view(18).frame!,
      applied_revision:revision,sha256:sha,url:`/v1/product/viewport/preview/${sha}`,preview_only:true,physical_authority:false}}));
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi} projectId="same" generation={{operation_id:'saved-incomplete',
      origin_message_id:'saved-origin',state:'failed',summary:'Saved partial',can_cancel:false,started_at:'now',last_progress_at:'now',error:null,
      progress:{generation_preview:{schema_version:'generation-preview-1.0',state:'blocked',candidate_revision:'partial-candidate',scene_revision:'partial-rev',
        rendered_count:17,pending_count:8,inventory_count:25,preview_only:true,physical_authority:false}}}}/>);
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve,180));});
    expect(screen.queryByRole('img')).toBeNull();expect(api.viewportPreviewImage).not.toHaveBeenCalled();
    revision='partial-rev';await screen.findByRole('img',{name:'Last Isaac preview · not live'});
    expect(api.viewportPreviewImage).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('status',{name:'Twin generation progress'}).textContent).toContain('17 of 25 objects rendered · 8 not rendered');
    expect(screen.getByRole('button',{name:'Orbit left'})).toHaveProperty('disabled',true);expect(api.viewportCamera).not.toHaveBeenCalled();component.unmount();
  });
  it('retains the last image for a failed input resumed under a new operation or a temporarily omitted origin',async()=>{
    const api=harness();const original:NonNullable<ConversationState['generation']>={operation_id:'first',origin_message_id:'same-input',
      state:'failed',summary:'Partial',can_cancel:false,started_at:'now',last_progress_at:'now',error:null,progress:{generation_preview:{
        schema_version:'generation-preview-1.0',state:'blocked',candidate_revision:'candidate',scene_revision:'rev',rendered_count:2,
        pending_count:1,inventory_count:3,preview_only:true,physical_authority:false}}};
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi} projectId="same" generation={original}/>);
    const canvas=await screen.findByRole('img',{name:'Last Isaac preview · not live'});
    const clears=drawing.clearRect.mock.calls.length,metadataReads=api.viewportState.mock.calls.length;
    component.rerender(<TwinViewport api={api as unknown as TwinPulseApi} projectId="same" generation={{...original,operation_id:'resume',state:'running',can_cancel:true,progress:undefined}}/>);
    expect(screen.getByRole('img',{name:'Last Isaac preview · not live'})).toBe(canvas);
    expect(drawing.clearRect).toHaveBeenCalledTimes(clears);expect(api.viewportState).toHaveBeenCalledTimes(metadataReads);
    component.rerender(<TwinViewport api={api as unknown as TwinPulseApi} projectId="same" generation={{...original,operation_id:'resume',origin_message_id:undefined,state:'running'}}/>);
    expect(screen.getByRole('img',{name:'Last Isaac preview · not live'})).toBe(canvas);
    expect(drawing.clearRect).toHaveBeenCalledTimes(clears);expect(api.viewportState).toHaveBeenCalledTimes(metadataReads);
    expect(screen.getByRole('button',{name:'Orbit left'})).toHaveProperty('disabled',true);component.unmount();
  });
  it('releases a previous input decoder without drawing it into the new input',async()=>{
    const api=harness();const original:NonNullable<ConversationState['generation']>={operation_id:'first',origin_message_id:'input-a',
      state:'completed',summary:'Ready',can_cancel:false,started_at:'now',last_progress_at:'now',error:null};
    api.viewportState.mockResolvedValue(view(1));
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi} projectId="same" generation={original}/>);
    await screen.findByRole('img');let finish!:(bitmap:ImageBitmap)=>void;
    vi.mocked(createImageBitmap).mockImplementationOnce(()=>new Promise<ImageBitmap>(resolve=>{finish=resolve;}));
    api.viewportState.mockResolvedValue(view(2));await waitFor(()=>expect(finish).toBeTypeOf('function'));
    expect(createImageBitmap).toHaveBeenCalledTimes(2);
    const draws=drawing.drawImage.mock.calls.length;
    const next=view(3);next.frame!.applied_revision='new-rev';api.viewportState.mockResolvedValue(next);
    component.rerender(<TwinViewport api={api as unknown as TwinPulseApi} projectId="same" generation={{...original,origin_message_id:'input-b',progress:{
      generation_preview:{schema_version:'generation-preview-1.0',state:'ready',candidate_revision:'candidate-b',scene_revision:'new-rev',
        rendered_count:2,pending_count:0,inventory_count:2,preview_only:true,physical_authority:false}}}}/>);
    expect(screen.queryByRole('img')).toBeNull();expect(createImageBitmap).toHaveBeenCalledTimes(2);
    await act(async()=>{finish({width:960,height:640,close} as unknown as ImageBitmap);});
    expect(drawing.drawImage).toHaveBeenCalledTimes(draws);
    await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});
    expect(drawing.drawImage).toHaveBeenCalledTimes(draws+1);expect(close).toHaveBeenCalledTimes(3);component.unmount();
  });
  it('rejects another input static receipt and accepts only the new confirmed static revision without camera authority',async()=>{
    const sha='a'.repeat(64),api={...harness(),viewportPreviewImage:vi.fn(async()=>new Blob(['image'],{type:'image/jpeg'}))};
    let revision='rev';api.viewportState.mockImplementation(async()=>({...view(),state:'stale',frame:null,last_frame:{...view(18).frame!,
      applied_revision:revision,sha256:sha,url:`/v1/product/viewport/preview/${sha}`,preview_only:true,physical_authority:false}}));
    const original:NonNullable<ConversationState['generation']>={operation_id:'first',origin_message_id:'input-a',state:'failed',
      summary:'Partial',can_cancel:false,started_at:'now',last_progress_at:'now',error:null,progress:{generation_preview:{
        schema_version:'generation-preview-1.0',state:'blocked',candidate_revision:'candidate-a',scene_revision:'rev',rendered_count:2,
        pending_count:1,inventory_count:3,preview_only:true,physical_authority:false}}};
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi} projectId="same" generation={original}/>);
    await screen.findByRole('img',{name:'Last Isaac preview · not live'});
    const next={...original,origin_message_id:'input-b',operation_id:'new',progress:{generation_preview:{schema_version:'generation-preview-1.0' as const,
      state:'blocked' as const,candidate_revision:'candidate-b',scene_revision:'new-rev',rendered_count:2,pending_count:1,inventory_count:3,
      preview_only:true as const,physical_authority:false as const}}};
    component.rerender(<TwinViewport api={api as unknown as TwinPulseApi} projectId="same" generation={next}/>);
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve,180));});
    expect(screen.queryByRole('img')).toBeNull();expect(api.viewportPreviewImage).toHaveBeenCalledTimes(1);
    revision='new-rev';await screen.findByRole('img',{name:'Last Isaac preview · not live'});
    expect(api.viewportPreviewImage).toHaveBeenCalledTimes(2);
    expect(screen.getByRole('button',{name:'Orbit left'})).toHaveProperty('disabled',true);expect(api.viewportCamera).not.toHaveBeenCalled();component.unmount();
  });
  it('does not stack native decoders across API replacement and releases the old result before decoding the new project',async()=>{
    let finish!:(bitmap:ImageBitmap)=>void;
    vi.mocked(createImageBitmap).mockImplementationOnce(()=>new Promise<ImageBitmap>(resolve=>{finish=resolve;}));
    const old=harness();const component=render(<TwinViewport api={old as unknown as TwinPulseApi} projectId="a"/>);
    await waitFor(()=>expect(createImageBitmap).toHaveBeenCalledTimes(1));
    const next=harness();component.rerender(<TwinViewport api={next as unknown as TwinPulseApi} projectId="b"/>);
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve,220));});
    expect(createImageBitmap).toHaveBeenCalledTimes(1);expect(next.viewportImage).not.toHaveBeenCalled();
    await act(async()=>{finish({width:960,height:640,close} as unknown as ImageBitmap);});
    await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});
    expect(drawing.drawImage).toHaveBeenCalledTimes(1);expect(close).toHaveBeenCalledTimes(2);component.unmount();
  });
  it('shows the source photo and incomplete progress without inventing a draft for a zero-count observer failure',async()=>{
    const api=harness();api.viewportState.mockResolvedValue({...view(),state:'waiting',frame:null});
    const generation:NonNullable<ConversationState['generation']>={operation_id:'job',state:'failed',summary:'Stopped',
      can_cancel:false,started_at:'now',last_progress_at:'now',error:{code:'observer_failed',message:'No valid observation',diagnostics:{
        stage:'observer',generation_preview:{schema_version:'generation-preview-1.0',state:'blocked',candidate_revision:null,
          scene_revision:null,rendered_count:0,pending_count:0,inventory_count:0,preview_only:true,physical_authority:false}}},
      progress:{repair_count:1,max_repairs:3,inventory_progress:{schema_version:'inventory-work-progress-1.0',observed_instances:0,
        inventory_count:0,parameterized_count:0,pending_count:0,parameter_batch_size:6,inventory_planned:false,
        parameters_complete:false,checkpoint_saved:true,observation_saved:false,draft_saved:false,automatic_resume:false,physical_authority:false}}};
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi} generation={generation}
      sourcePhoto={{url:'/v1/product/conversation/image/source',name:'room.jpg'}}/>);
    expect((await screen.findByRole('img',{name:'Source photo: room.jpg'})).getAttribute('src')).toMatch(/^blob:/);
    expect(api.conversationImage).toHaveBeenCalledWith('/v1/product/conversation/image/source');
    const progress=screen.getByRole('status',{name:'Twin generation progress'});
    expect(progress.textContent).toContain('Incomplete · Preview');expect(progress.textContent).toContain('Reading the source photo');
    expect(progress.textContent).toContain('Repairs: 1/3');expect(progress.textContent).toContain('Latest error: No valid observation');
    expect(progress.textContent).toContain('Resume checkpoint saved');expect(progress.textContent).not.toContain('Scene draft saved');
    expect(api.viewportCamera).not.toHaveBeenCalled();component.unmount();
  });
  it.each(['accepted','running','failed'])('labels a checkpoint without observation or draft according to actual %s state',state=>{
    const api=harness();api.viewportState.mockResolvedValue({...view(),state:'waiting',frame:null});
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi} generation={{operation_id:'checkpoint',state,
      summary:'Checkpoint recorded',can_cancel:state!=='failed',started_at:'now',last_progress_at:'now',error:null,progress:{
        inventory_progress:{schema_version:'inventory-work-progress-1.0',observed_instances:0,inventory_count:0,parameterized_count:0,
          pending_count:0,parameter_batch_size:6,inventory_planned:false,parameters_complete:false,checkpoint_saved:true,
          observation_saved:false,draft_saved:false,automatic_resume:false,physical_authority:false}}}}/>);
    const progress=screen.getByRole('status',{name:'Twin generation progress'});
    expect(progress.textContent).toContain('Resume checkpoint saved');expect(progress.textContent).not.toContain('Failure record saved');component.unmount();
  });
  it('expires a stalled decoder without stacking native decodes, keeps polling and releases its late bitmap',async()=>{
    let finish!:(bitmap:ImageBitmap)=>void;
    const lateClose=vi.fn(),lateBitmap={width:960,height:640,close:lateClose} as unknown as ImageBitmap;
    vi.stubGlobal('createImageBitmap',vi.fn()
      .mockImplementationOnce(()=>new Promise<ImageBitmap>(resolve=>{finish=resolve;}))
      .mockImplementation(async()=>({width:960,height:640,close})));
    let frame=0;const api={...harness(),viewportObservation:vi.fn(async()=>({execution_id:'decode-id',physical_authority:false}))};
    api.viewportState.mockImplementation(async()=>view(++frame));
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi}/>);
    await waitFor(()=>expect(createImageBitmap).toHaveBeenCalledTimes(1));
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve,1200));});
    expect(screen.queryByRole('img')).toBeNull();expect(screen.getByRole('alert').textContent).toContain('decode');
    expect(api.viewportState.mock.calls.length).toBeGreaterThan(1);expect(createImageBitmap).toHaveBeenCalledTimes(1);
    expect(api.viewportObservation.mock.calls[0]).toEqual([expect.objectContaining({error_code:'viewport_decode_expired'})]);
    await act(async()=>{finish(lateBitmap);});
    // The next healthy decode may finish in this same act() flush. Track the
    // expired bitmap separately, rather than timing an unrelated close/draw.
    expect(lateClose).toHaveBeenCalledTimes(1);
    expect(drawing.drawImage.mock.calls.every(call=>call[0]!==lateBitmap)).toBe(true);
    await screen.findByRole('img');expect(close.mock.calls.length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByRole('alert')).toBeNull();component.unmount();
  });
  it('identifies slow image delivery before decoding and records bounded stage timings, then recovers',async()=>{
    const api={...harness(),viewportObservation:vi.fn(async(_body:unknown)=>({execution_id:'transport-id',physical_authority:false}))};
    let sequence=0;api.viewportState.mockImplementation(async()=>view(++sequence));
    api.viewportImage.mockImplementationOnce(async()=>{
      await new Promise(resolve=>setTimeout(resolve,1100));return new Blob(['image'],{type:'image/jpeg'});
    });
    const component=render(<TwinViewport api={api as unknown as TwinPulseApi}/>);
    await waitFor(()=>expect(api.viewportObservation).toHaveBeenCalled(),{timeout:2000});
    const body=api.viewportObservation.mock.calls[0][0] as unknown as {error_code:string;timings:Record<string,number>};
    expect(body.error_code).toBe('viewport_image_expired');
    expect(body.timings.image_ms).toBeGreaterThanOrEqual(1000);expect(body.timings.decode_ms).toBe(0);
    expect(body.timings.frame_age_ms).toBeGreaterThanOrEqual(1000);
    expect(createImageBitmap).not.toHaveBeenCalled();
    await screen.findByRole('img');expect(api.command).not.toHaveBeenCalled();
    expect(api.viewportObservation).toHaveBeenCalledTimes(1);component.unmount();
  });
});
