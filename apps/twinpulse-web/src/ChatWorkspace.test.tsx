// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ActionCard, ChatWorkspace, conversationTurns, generationSourceAttachment } from './ChatWorkspace';
import { App } from './App';
import { ApiError } from './api';
import type { TwinPulseApi } from './api';
import type { ConversationState } from './conversation-types';

const initial = (): ConversationState => ({schema_version:'conversation-1.0',session_id:'chat-1',project_id:'chat-test',revision:0,cursor:0,
  mode:null,robot_id:null,physical_authority:false,restore_error:null,messages:[],cards:[],events:[],generation:null,accepted_request_ids:[]});
function harness() {
  let state = initial();
  const api = {bootstrap:vi.fn().mockResolvedValue(undefined),conversation:vi.fn(async()=>state),conversationImage:vi.fn(async()=>new Blob(['photo'],{type:'image/png'})),
    conversationAction:vi.fn(async body=> {
      if(body.action==='message') {
        state={...state,revision:1,cursor:1,accepted_request_ids:[body.request_id],messages:[
          {message_id:'m1',role:'user',content:body.text,status:'completed',attachments:[],created_at:'now',operation_id:null},
          {message_id:'m2',role:'assistant',content:'Do you have a physical robot?',status:'completed',attachments:[],created_at:'now',operation_id:null}],
          cards:[{id:'q1',message_id:'m2',kind:'robot_presence',question:'Do you have a physical robot?',state:'waiting',selected_choice_id:null,operation_id:null,expected_session_revision:1,
          choices:[{id:'sim',label:'Simulation only',enabled:true,disabled_reason:null},{id:'real',label:'Use my robot',enabled:true,disabled_reason:null}]}]};
      }
      return state;
    }), runtimeState:vi.fn().mockResolvedValue({status:'starting',message:'Starting owned engine'}),
    productState:vi.fn().mockResolvedValue({engine_connected:false}),workflow:vi.fn().mockResolvedValue({phase:'empty',provider:{configured:false,label:'Provider'}})};
  return api;
}

describe('Chat-first product workspace',()=> {
  beforeEach(()=>vi.stubGlobal('Image',class {src='';naturalWidth=960;naturalHeight=640;async decode(){}}));
  afterEach(()=>vi.unstubAllGlobals());
  it('binds the source photo to the generation origin through SIM answers, later photos and restored history',()=>{
    const photo={name:'origin.jpg',media_type:'image/jpeg',preview_url:'/origin'};
    const user=(id:string,attachments:ConversationState['messages'][number]['attachments'],operation:string|null='job')=>({
      message_id:id,role:'user' as const,content:id,status:'completed',created_at:'now',attachments,operation_id:operation});
    const state={...initial(),messages:[user('origin',[photo]),user('sim',[]),user('later',[{...photo,name:'other.jpg',preview_url:'/other'}],'other')],
      generation:{operation_id:'job',origin_message_id:'origin',state:'running',summary:'Working',can_cancel:true,started_at:'now',last_progress_at:'now',error:null}};
    expect(generationSourceAttachment(state)).toBe(photo);
    expect(generationSourceAttachment({...state,restored_session:true} as ConversationState)).toBe(photo);
    expect(generationSourceAttachment({...state,generation:{...state.generation,origin_message_id:'sim'}})).toBeUndefined();
    expect(generationSourceAttachment({...state,generation:{...state.generation,origin_message_id:'missing'}})).toBeUndefined();
    expect(generationSourceAttachment({...state,generation:{...state.generation,origin_message_id:undefined}})).toBe(photo);
    expect(generationSourceAttachment({...state,generation:{...state.generation,origin_message_id:undefined,operation_id:'unrelated'}})).toBeUndefined();
  });
  it('starts mode selection without a price input or approval choice',()=>{
    const card={id:'mode',message_id:'reply',kind:'robot_presence',question:'Choose a mode',state:'waiting',selected_choice_id:null,
      operation_id:null,expected_session_revision:1,choices:[{id:'sim',label:'Simulation only',enabled:true,disabled_reason:null},
      {id:'real',label:'Use my robot',enabled:true,disabled_reason:null}],generation_approval:{image_count:0,purpose:'Generate a Twin',
      policy:{max_requests:12,max_repairs:3,per_call_timeout_s:30},models:[]}};
    const actChoice=vi.fn();render(<ActionCard card={card as never} busy={false} act={actChoice}/>);
    fireEvent.click(screen.getByRole('radio',{name:'Simulation only'}));fireEvent.click(screen.getByRole('button',{name:'Create Twin'}));
    expect(actChoice).toHaveBeenCalledWith(card,'sim');
    expect(screen.queryByRole('textbox',{name:/Maximum spend/})).toBeNull();expect(screen.queryByText(/USD/)).toBeNull();
    expect(screen.queryByRole('button',{name:/Approve/})).toBeNull();
  });
  it('groups late replies with their request and retains orphan cards at their historical time',()=>{
    const user=(id:string,time:string)=>({message_id:id,role:'user' as const,content:id,status:'completed',created_at:time,attachments:[],operation_id:null});
    const messages=[user('first','2026-10-13T10:00:00Z'),user('second','2026-10-13T10:02:00Z'),
      {...user('late','2026-10-13T10:03:00Z'),role:'assistant' as const,reply_to:'first'}];
    const card={id:'retained',message_id:'missing-old',created_at:'2026-10-13T10:01:00Z'};
    const turns=conversationTurns({messages,cards:[card as never]});
    expect(turns.map(turn=>turn.id)).toEqual(['first','legacy-card:retained','second']);
    expect(turns[0].messages.map(message=>message.message_id)).toEqual(['first','late']);
    expect(turns[1].cards[0].id).toBe('retained');
  });
  it('keeps generation, feedback and transaction results under their originating turns',async()=>{
    const api=harness();const user=(id:string)=>({message_id:id,role:'user' as const,content:id,status:'completed',created_at:'now',attachments:[],operation_id:null});
    api.conversation.mockResolvedValue({...initial(),messages:[user('generate-origin'),user('feedback-origin'),user('edit-origin'),user('later-status')],
      generation:{operation_id:'job',origin_message_id:'generate-origin',state:'failed',summary:'Retained generation result',can_cancel:false,started_at:'now',last_progress_at:'now',error:null},
      scene_feedback:{operation_id:'feedback',origin_message_id:'feedback-origin',state:'preview_ready',error:null,clarification_count:0},
      scene_edit_transaction:{operation_id:'edit',origin_message_id:'edit-origin',state:'COMMITTED',execution_id:null,current_frame:true,durable_committed:true,error:null,command_id:'command'}});
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    expect((await screen.findByText('Retained generation result')).closest('.chat-turn')?.getAttribute('data-turn-id')).toBe('generate-origin');
    expect(screen.getByRole('status',{name:'Scene feedback status'}).closest('.chat-turn')?.getAttribute('data-turn-id')).toBe('feedback-origin');
    expect(screen.getByRole('status',{name:'Twin update status'}).closest('.chat-turn')?.getAttribute('data-turn-id')).toBe('edit-origin');
    expect(screen.getByRole('button',{name:'Continue unfinished work'}).closest('.chat-turn')?.getAttribute('data-turn-id')).toBe('generate-origin');
  });
  it('switches workspace context in the same tab and clears the previous composer and review state',async()=>{
    const api=harness();let selected={...initial(),context_id:'ctx-old',revision:900,project_id:'old',messages:[{
      message_id:'old-message',role:'user' as const,content:'Old scene request',status:'completed',attachments:[],created_at:'now',operation_id:null}]};
    api.runtimeState.mockResolvedValue({status:'ready'} as never);api.conversation.mockImplementation(async()=>selected);
    const projects=vi.fn(async()=>({projects:[{project_id:'old',active:true,status:'review_required'},{project_id:'next',active:false,status:'empty'}]}));
    const switchProject=vi.fn(async()=>{selected={...initial(),context_id:'ctx-next',project_id:'next',revision:1,messages:[]};
      extended.context='ctx-next';return {status:'switched',project_id:'next',context_id:'ctx-next',new_session_required:false};});
    const extended={...api,projects,switchProject,context:'ctx-old'};const address=location.href;
    render(<ChatWorkspace api={extended as unknown as TwinPulseApi} advanced={()=>{}}/>);
    await screen.findByText('Old scene request');fireEvent.change(screen.getByRole('textbox',{name:'Message TwinPulse'}),{target:{value:'unsent old draft'}});
    fireEvent.click(await screen.findByRole('button',{name:'Open next'}));
    await waitFor(()=>expect(screen.getByText(/next · Choose a mode/)).toBeTruthy());
    expect(screen.queryByText('Old scene request')).toBeNull();expect(screen.getByRole('textbox',{name:'Message TwinPulse'})).toHaveProperty('value','');
    expect(sessionStorage.getItem('twinpulse.chat.draft.old')).toBe('unsent old draft');
    expect(api.bootstrap).toHaveBeenCalledOnce();expect(switchProject).toHaveBeenCalledOnce();expect(location.href).toBe(address);
  });
  it.each([999,1000])('closes only the narrow sidebar after project selection or New chat at %spx',async width=>{
    vi.stubGlobal('innerWidth',width);
    const api=harness();let selected={...initial(),context_id:'ctx-old'};
    api.runtimeState.mockResolvedValue({status:'ready'} as never);api.conversation.mockImplementation(async()=>selected);
    const catalog={projects:[{project_id:'chat-test',active:true,status:'empty'},{project_id:'next',active:false,status:'empty'}]};
    let finish!:(result:{status:string;project_id:string;context_id:string;new_session_required:boolean})=>void;
    const switchProject=vi.fn((project_id:string)=>new Promise(resolve=>{finish=result=>{
      selected={...initial(),project_id,context_id:result.context_id};extended.context=result.context_id;resolve(result);
    };}));
    const extended={...api,context:'ctx-old',projects:vi.fn(async()=>catalog),createProject:vi.fn(async()=>({catalog})),switchProject};
    render(<ChatWorkspace api={extended as unknown as TwinPulseApi} advanced={()=>{}}/>);
    await screen.findByText('chat-test · Choose a mode');
    const toggle=screen.getByRole('button',{name:'Toggle conversations and projects'});
    if(width<1000)fireEvent.click(toggle);
    for(const action of ['project','new-chat']){
      if(toggle.getAttribute('aria-expanded')==='false')fireEvent.click(toggle);
      const actionButton=await screen.findByRole('button',{name:action==='project'?'Open next':'＋ New chat'});
      await waitFor(()=>expect(actionButton).toHaveProperty('disabled',false));fireEvent.click(actionButton);
      await waitFor(()=>expect(switchProject).toHaveBeenCalledTimes(action==='project'?1:2));
      // Keep the overlay and existing switch locks until the acknowledgement.
      expect(toggle.getAttribute('aria-expanded')).toBe('true');
      expect(screen.getByRole('button',{name:'＋ New chat'})).toHaveProperty('disabled',true);
      expect(screen.getByRole('button',{name:'Open chat-test'})).toHaveProperty('disabled',true);
      const target=switchProject.mock.calls.at(-1)![0];
      await act(async()=>finish({status:'switched',project_id:target,context_id:`ctx-${target}`,new_session_required:false}));
      await screen.findByText(`${target} · Choose a mode`);
      expect(toggle.getAttribute('aria-expanded')).toBe(width<1000?'false':'true');
      expect(screen.getByRole('button',{name:'Attach image'})).toBeTruthy();
    }
    expect(extended.createProject).toHaveBeenCalledOnce();expect(api.conversationAction).not.toHaveBeenCalled();
  });
  it('keeps restored SIM route controls under the goal request without restoring Run authority',async()=>{
    const api=harness();const user=(id:string)=>({message_id:id,role:'user' as const,content:id,status:'completed',created_at:'now',attachments:[],operation_id:null});
    api.conversation.mockResolvedValue({...initial(),mode:'SIM',messages:[user('generation-origin'),user('goal-origin'),user('later-status')],
      simulation_review:{origin_message_id:'goal-origin',request_id:'goal-request',text:'Go to the bed',scene_revision:'saved',start_source:'saved',
        plan:null,target:null,choices:[],drawing:{bounds:[0,0,5,5],boxes:[],discs:[]}}});
    api.workflow.mockResolvedValue({phase:'draft_ready',site_draft:{revision:'saved',artifact_id:'artifact'}} as never);
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    expect((await screen.findByRole('button',{name:'Preview SIM route'})).closest('.chat-turn')?.getAttribute('data-turn-id')).toBe('goal-origin');
    expect(screen.getByRole('button',{name:'Run simulation'})).toHaveProperty('disabled',true);expect(api.conversationAction).not.toHaveBeenCalled();
  });
  it('shows retained incomplete inventory without resuming or claiming a verified scene',async()=>{
    const api=harness();api.conversation.mockResolvedValue({...initial(),budgeted_generation_available:true,
      generation:{operation_id:'partial',state:'failed',summary:'NEEDS_REQUEST_BUDGET',can_cancel:false,
        started_at:'now',last_progress_at:'now',error:{code:'NEEDS_REQUEST_BUDGET',message:'NEEDS_REQUEST_BUDGET'},
        progress:{inventory_progress:{schema_version:'inventory-work-progress-1.0',observed_instances:60,
          inventory_count:60,parameterized_count:42,pending_count:18,parameter_batch_size:6,
          inventory_planned:true,parameters_complete:false,checkpoint_saved:true,automatic_resume:false,physical_authority:false}}}});
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    const progress=await screen.findByRole('status',{name:'Inventory work progress'});
    expect(progress.textContent).toContain('42 of 60 objects parameterized · 18 awaiting parameters');
    expect(progress.textContent).toContain('not a verified scene');
    expect(screen.getByText(/Resume checkpoint saved · review the stop reason/)).toBeTruthy();
    expect(api.conversationAction).not.toHaveBeenCalled();
  });
  it('shows retained observation without saying that a scene draft was saved',async()=>{
    const api=harness();api.conversation.mockResolvedValue({...initial(),mode:'SIM',generation:{
      operation_id:'observer-stop',state:'failed',summary:'Observer stopped',can_cancel:false,started_at:'now',last_progress_at:'now',
      error:{code:'observer_failed',message:'Observer failed'},progress:{inventory_progress:{schema_version:'inventory-work-progress-1.0',
        observed_instances:24,inventory_count:0,parameterized_count:0,pending_count:0,parameter_batch_size:6,
        inventory_planned:false,parameters_complete:false,checkpoint_saved:true,observation_saved:true,draft_saved:false,
        automatic_resume:false,physical_authority:false}}}});
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    const progress=await screen.findByRole('status',{name:'Inventory work progress'});
    expect(progress.textContent).toContain('Resume checkpoint saved');
    expect(screen.queryByText(/Incomplete draft saved · review the stop reason/)).toBeNull();
    expect(screen.getByText(/Resume checkpoint saved · review the stop reason/)).toBeTruthy();
    expect(api.conversationAction).not.toHaveBeenCalled();
  });
  it.each(['accepted','running','failed'])('does not turn a %s checkpoint into a false failure record',async state=>{
    const api=harness();api.conversation.mockResolvedValue({...initial(),mode:'SIM',generation:{operation_id:'checkpoint',state,
      summary:'Checkpoint recorded',can_cancel:state!=='failed',started_at:'now',last_progress_at:'now',error:null,progress:{
        inventory_progress:{schema_version:'inventory-work-progress-1.0',observed_instances:0,inventory_count:0,parameterized_count:0,
          pending_count:0,parameter_batch_size:6,inventory_planned:false,parameters_complete:false,checkpoint_saved:true,
          observation_saved:false,draft_saved:false,automatic_resume:false,physical_authority:false}}}});
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    const progress=await screen.findByRole('status',{name:'Inventory work progress'});
    expect(progress.textContent).toContain('Resume checkpoint saved');expect(progress.textContent).not.toContain('failure record');
    expect(progress.textContent).not.toContain('Scene draft saved');expect(api.conversationAction).not.toHaveBeenCalled();
  });
  it.each(['completed','failed'])('keeps photo conflicts distinct from actual %s scene acceptance and saving',async state=>{
    const saved=state==='completed',api=harness();api.conversation.mockResolvedValue({...initial(),mode:'SIM',generation:{
      operation_id:'photo-quality',state,summary:'Photo conflicts remain',can_cancel:false,started_at:'now',last_progress_at:'now',error:null,
      progress:{stage_acceptance:{approximate_draft:saved?'passed':'blocked',photo_quality:'needs_revision'},
        inventory_progress:{schema_version:'inventory-work-progress-1.0',observed_instances:4,inventory_count:4,parameterized_count:4,
          pending_count:0,parameter_batch_size:6,inventory_planned:true,parameters_complete:true,checkpoint_saved:true,
          draft_saved:saved,automatic_resume:false,physical_authority:false},generation_preview:{schema_version:'generation-preview-1.0',
          state:saved?'ready':'blocked',candidate_revision:'candidate',scene_revision:saved?'rev':null,rendered_count:saved?4:0,
          pending_count:saved?0:4,inventory_count:4,preview_only:true,physical_authority:false}}}});
    if(saved)api.workflow.mockResolvedValue({phase:'draft_ready',input:{revision:'input'},site_draft:{revision:'rev',input_revision:'input'}} as never);
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    if(saved){
      expect(await screen.findByText(/Photo layout conflicts remain in the saved approximate draft/)).toBeTruthy();
      expect(screen.getByRole('status',{name:'Inventory work progress'}).textContent).toContain('Scene draft saved');
      expect(screen.queryByText(/Correction stopped without accepting a scene/)).toBeNull();
    }else expect(await screen.findByText(/Correction stopped without accepting a scene/)).toBeTruthy();
    expect(screen.queryByText(/Reviewed visual checks are consistent/)).toBeNull();expect(api.conversationAction).not.toHaveBeenCalled();
  });
  it.each([0,1])('reports draft completion without claiming photo quality when %s objects remain unrendered',async pending=>{
    const api=harness();api.conversation.mockResolvedValue({...initial(),mode:'SIM',generation:{
      operation_id:'finished',state:'completed',summary:'Scene generation finished',can_cancel:false,started_at:'now',last_progress_at:'now',error:null,
      progress:{generation_activity:{schema_version:'generation-activity-1.0',stage:'final_validation',phase:'validating'},
        inventory_progress:{schema_version:'inventory-work-progress-1.0',observed_instances:4,inventory_count:4,parameterized_count:4,pending_count:0,
          parameter_batch_size:6,inventory_planned:true,parameters_complete:true,checkpoint_saved:true,draft_saved:true,automatic_resume:false,physical_authority:false},
        generation_preview:{schema_version:'generation-preview-1.0',state:'ready',candidate_revision:'candidate',scene_revision:'rev',
          rendered_count:4-pending,pending_count:pending,inventory_count:4,preview_only:true,physical_authority:false},stage_acceptance:{photo_quality:'uncertain'}}}});
    api.workflow.mockResolvedValue({phase:'draft_ready',input:{revision:'input'},site_draft:{revision:'rev',input_revision:'input'}} as never);
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    const inventory=await screen.findByRole('status',{name:'Inventory work progress'});
    expect(inventory.textContent).toContain('4 of 4 objects parameterized · 0 awaiting parameters');
    expect(screen.queryByText(/validating the received candidate/)).toBeNull();
    if(pending){
      expect(inventory.textContent).toContain('Resume checkpoint saved');expect(inventory.textContent).toContain('Continue only unfinished work');
      expect(inventory.textContent).toContain('Saved partial scene');
      expect(screen.getByRole('status',{name:'Twin generation progress'}).textContent).toContain('Incomplete · Preview');
    }else{
      expect(inventory.textContent).toContain('Scene draft saved');expect(inventory.textContent).toContain('require separate checks');
      expect(inventory.textContent).not.toContain('incomplete');expect(inventory.textContent).not.toContain('Continue only unfinished work');
      expect(screen.getByRole('status',{name:'Twin generation progress'}).textContent).toContain('Scene generation completed');
    }
    expect(screen.getByText(/Photo fidelity remains uncertain/)).toBeTruthy();
    expect(screen.queryByText(/Reviewed visual checks are consistent/)).toBeNull();expect(api.conversationAction).not.toHaveBeenCalled();
  });
  it.each(['completed','failed','cancelled'])('does not present %s semantic checkpoint flags as an accepted saved scene',async state=>{
    const api=harness();api.conversation.mockResolvedValue({...initial(),mode:'SIM',generation:{operation_id:'checkpoint-only',state,
      summary:'Semantic parameters retained',can_cancel:false,started_at:'now',last_progress_at:'now',error:null,progress:{
        inventory_progress:{schema_version:'inventory-work-progress-1.0',observed_instances:4,inventory_count:4,parameterized_count:4,pending_count:0,
          parameter_batch_size:6,inventory_planned:true,parameters_complete:true,checkpoint_saved:true,draft_saved:true,automatic_resume:false,physical_authority:false},
        generation_preview:{schema_version:'generation-preview-1.0',state:'ready',candidate_revision:'candidate',scene_revision:'rev',
          rendered_count:4,pending_count:0,inventory_count:4,preview_only:true,physical_authority:false}}}});
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    const progress=await screen.findByRole('status',{name:'Inventory work progress'});
    expect(progress.textContent).toContain('Resume checkpoint saved');expect(progress.textContent).toContain('does not confirm an accepted saved scene');
    expect(progress.textContent).not.toContain('Scene draft saved');expect(progress.textContent).not.toContain('Saved partial scene');
    expect(screen.getByRole('status',{name:'Twin generation progress'}).textContent).not.toContain('Scene draft saved');
    expect(api.conversationAction).not.toHaveBeenCalled();
  });
  it.each(['input','revision','persistence'])('does not use mismatched %s storage information to label a completed checkpoint saved',async mismatch=>{
    const api=harness();api.conversation.mockResolvedValue({...initial(),mode:'SIM',generation:{operation_id:'finished',state:'completed',
      summary:'Finished',can_cancel:false,started_at:'now',last_progress_at:'now',error:null,progress:{
        inventory_progress:{schema_version:'inventory-work-progress-1.0',observed_instances:4,inventory_count:4,parameterized_count:4,pending_count:0,
          parameter_batch_size:6,inventory_planned:true,parameters_complete:true,checkpoint_saved:true,draft_saved:true,automatic_resume:false,physical_authority:false},
        generation_preview:{schema_version:'generation-preview-1.0',state:'ready',candidate_revision:'candidate',scene_revision:'rev',
          rendered_count:4,pending_count:0,inventory_count:4,preview_only:true,physical_authority:false}}}});
    api.workflow.mockResolvedValue({phase:'draft_ready',input:{revision:'input'},
      site_draft:{revision:mismatch==='revision'?'another-scene':'rev',input_revision:mismatch==='input'?'another-input':'input'},
      error:mismatch==='persistence'?{code:'project_persistence_failed',message:'Not saved'}:null} as never);
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    const progress=await screen.findByRole('status',{name:'Inventory work progress'});
    expect(progress.textContent).toContain('Resume checkpoint saved');expect(progress.textContent).not.toContain('Scene draft saved');
    expect(screen.getByRole('status',{name:'Twin generation progress'}).textContent).not.toContain('Scene draft saved');
  });
  it('passes the current authenticated source photo and candidate progress to the Twin pane',async()=>{
    const api=harness();api.conversation.mockResolvedValue({...initial(),mode:'SIM',messages:[{
      message_id:'source',role:'user',content:'Build this room',status:'completed',created_at:'now',operation_id:null,
      attachments:[{name:'room.jpg',media_type:'image/jpeg',preview_url:'/v1/product/conversation/image/source'}]}],
      generation:{operation_id:'building',origin_message_id:'source',state:'running',summary:'Checking the room',can_cancel:true,started_at:'now',last_progress_at:'now',error:null,
        progress:{stage:'final_validation',repair_count:2,max_repairs:3,generation_preview:{schema_version:'generation-preview-1.0',
          state:'building',candidate_revision:'candidate',scene_revision:'scene',rendered_count:4,pending_count:8,inventory_count:12,
          preview_only:true,physical_authority:false}}}});
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    expect((await screen.findByRole('img',{name:'Source photo: room.jpg'})).getAttribute('src')).toMatch(/^blob:/);
    expect((await screen.findByRole('img',{name:'room.jpg'})).getAttribute('src')).toMatch(/^blob:/);
    expect(api.conversationImage).toHaveBeenCalledWith('/v1/product/conversation/image/source');
    const progress=screen.getByRole('status',{name:'Twin generation progress'});
    expect(progress.textContent).toContain('Checking the final scene');expect(progress.textContent).toContain('Repairs: 2/3');
    expect(progress.textContent).toContain('Candidate preview: 4 of 12 objects selected · 8 not included yet');expect(progress.textContent).toContain('render not confirmed');
    expect(progress.textContent).toContain('Last confirmed 3D: not confirmed');
    expect(progress.textContent).toContain('Incomplete · Preview');
    expect(api.conversationAction).not.toHaveBeenCalled();
  });
  it('explains a bounded observer capacity failure with counts instead of only a technical code',async()=>{
    const api=harness();api.conversation.mockResolvedValue({...initial(),mode:'SIM',generation:{
      operation_id:'capacity-fail',state:'failed',summary:'Observation capacity exceeded',can_cancel:false,
      started_at:'now',last_progress_at:'now',error:{code:'provider_response_invalid',message:'Observation capacity exceeded',
        diagnostics:{scene_contract:{issues:[{code:'OBSERVER_INSTANCE_LIMIT_EXCEEDED',path:'$.entities',actual_count:33,
          maximum:32,structural_metadata_count:4}],issue_count:1,issues_truncated:false,blocked_checks:[],physical_authority:false}}}}});
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    expect(await screen.findByText(/Count: 33.*Capacity: 32.*Separate metadata: 4/)).toBeTruthy();
    expect(api.conversationAction).not.toHaveBeenCalled();
  });
  it('starts restored history at the conversation home without resurfacing past failures',async()=>{
    const api=harness();api.conversation.mockResolvedValue({...initial(),restored_session:true,messages:[
      {message_id:'old-user',role:'user',content:'지난 침실',status:'completed',attachments:[],created_at:'2026-10-06T10:00:00Z',operation_id:null},
      {message_id:'old-failure',role:'assistant',content:'provider exceeded 90s timeout',status:'failed',attachments:[],created_at:'2026-10-06T10:01:00Z',operation_id:'old'}],
      generation:{operation_id:'old',state:'failed',summary:'Old failure',can_cancel:false,started_at:'then',last_progress_at:'then',error:{code:'provider_timeout',message:'provider exceeded 90s timeout'}}});
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    expect(await screen.findByRole('region',{name:'Conversation home'})).toBeTruthy();
    expect(screen.queryByRole('alert')).toBeNull();expect(screen.queryByRole('textbox',{name:'Message TwinPulse'})).toBeNull();
    fireEvent.click(screen.getByRole('button',{name:/Open saved chat/}));
    expect(await screen.findByRole('textbox',{name:'Message TwinPulse'})).toBeTruthy();
    expect(screen.getByText('provider exceeded 90s timeout')).toBeTruthy();
    expect(screen.getByText(/Saved conversation · previous execution history/)).toBeTruthy();
    expect(screen.queryByRole('alert')).toBeNull();expect(api.conversationAction).not.toHaveBeenCalled();
    expect(screen.queryByRole('button',{name:'New updates ↓'})).toBeNull();
  });
  it('labels pending support subset separately and retains entanglement task lock',async()=>{
    const api=harness();api.workflow.mockResolvedValue({phase:'draft_ready',site_draft:{revision:'saved',artifact_id:'artifact',
      progressive_twin:{current:true,inventory_count:3,materialized_count:2,unresolved:[{id:'cloth',parent_id:'bed',reason:'SURFACE_CAPACITY_EXCEEDED',hazard:'entanglement'}]},
      draft_refinement:{schema_version:'draft-refinement-1.1',acceptance:'MATERIALIZED_SUBSET_VALID_REFINEMENT_INCOMPLETE',
        current:true,stop_reason:'REPAIR_STALLED',quality_review:{status:'needs_revision',issues:[]}}}} as never);
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    const card=await screen.findByRole('status',{name:'Photo refinement retained'});
    expect(card.textContent).toContain('materialized subset');expect(card.textContent).toContain('whole-inventory geometry did not pass');
    expect(card.textContent).toContain('Unresolved hazards keep SIM and REAL tasks locked');
    expect(screen.getByText(/retained entanglement hazard/)).toBeTruthy();
    expect(screen.queryByText(/saved candidate passed its geometry compiler checks/)).toBeNull();
    expect(api.conversationAction).not.toHaveBeenCalled();
  });
  it('retains incomplete photo issues after reopen without promoting quality or adding a blanket SIM lock',async()=>{
    const api=harness();api.workflow.mockResolvedValue({phase:'draft_ready',site_draft:{revision:'saved',
      artifact_id:'artifact',draft_refinement:{schema_version:'draft-refinement-1.0',
      acceptance:'GEOMETRY_VALID_REFINEMENT_INCOMPLETE',current:false,assessment_state:'recheck_required',
      stop_reason:'QUALITY_REPAIR_LIMIT_REACHED',physical_authority:false,
      quality_review:{status:'needs_revision',issues:[{code:'PHOTO_RELATIVE_ORDER_CONTRADICTION',target_ids:['parent'],related_ids:['other'],violation_m:.4}]}}}} as never);
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    const card=await screen.findByRole('status',{name:'Photo refinement retained'});
    expect(card.textContent).toContain('Approximate Twin saved · photo refinement incomplete');
    expect(card.textContent).toContain('QUALITY_REPAIR_LIMIT_REACHED');
    expect(card.textContent).toContain('PHOTO_RELATIVE_ORDER_CONTRADICTION');
    expect(card.textContent).toContain('needs revalidation');
    expect(screen.getByRole('button',{name:'Preview SIM route'})).toBeTruthy();
    expect(screen.queryByText(/Photo geometry and fidelity passed/)).toBeNull();
    expect(api.conversationAction).not.toHaveBeenCalled();
  });
  it('distinguishes historical transaction frame confirmation from a later current view without promoting it',async()=>{
    const api=harness();api.workflow.mockResolvedValue({phase:'draft_ready',site_draft:{revision:'same-saved-scene'}} as never);
    api.productState.mockResolvedValue({engine_connected:false,build_view:{command_id:'later-view',
      scene_revision:'same-saved-scene'}} as never);
    api.conversation.mockResolvedValue({...initial(),scene_edit_transaction:{operation_id:'saved-operation',
      state:'COMMITTED',command_id:'original-build',engine_acknowledged:true,durable_committed:true,current_frame:false,
      result_revision:'same-saved-scene'} as never});
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    expect(await screen.findByText(/Transaction 3D frame: not currently confirmed/)).toBeTruthy();
    expect(screen.getByText(/original transaction frame receipt is separate from a later View current Twin/)).toBeTruthy();
    expect(screen.queryByText(/Transaction 3D frame: confirmed/)).toBeNull();
    expect(api.conversationAction).not.toHaveBeenCalled();
  });
  it('guides a reopened saved Twin with unset mode without implying a new input or motion',async()=>{
    const api=harness();api.workflow.mockResolvedValue({phase:'draft_ready',provider:{configured:false,label:'Saved provider'},
      site_draft:{revision:'saved-scene'}} as never);
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    await waitFor(()=>expect(screen.getByRole('region',{name:'Current step'}).textContent).toContain('Current Twin saved'));
    expect(screen.getByRole('region',{name:'Current step'}).textContent).toContain('request an edit or a goal');
    expect(api.conversationAction).not.toHaveBeenCalled();
  });
  it('keeps pending choice above saved-Twin guidance when mode is unset',async()=>{
    const api=harness();api.workflow.mockResolvedValue({phase:'draft_ready',site_draft:{revision:'saved-scene'}} as never);
    api.conversation.mockResolvedValue({...initial(),cards:[{id:'policy',message_id:'m',kind:'scene_sensor_policy',
      question:'Choose a sensor policy',state:'waiting',selected_choice_id:null,operation_id:null,expected_session_revision:0,
      choices:[{id:'cancel',label:'Cancel sensor review',enabled:true,disabled_reason:null}]}]});
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    await waitFor(()=>expect(screen.getByRole('region',{name:'Current step'}).textContent).toContain('Choose a sensor policy'));
    expect(screen.getByRole('region',{name:'Current step'}).textContent).not.toContain('Current Twin saved');
    expect(api.conversationAction).not.toHaveBeenCalled();
  });
  it('does not present a partial compile as all draft checks passed',async()=>{
    const api=harness();api.conversation.mockResolvedValue({...initial(),mode:'SIM',generation:{
      operation_id:'partial',state:'completed',summary:'Partial draft retained',can_cancel:false,started_at:'now',last_progress_at:'now',
      error:null,progress:{stage_acceptance:{approximate_draft:'partial',SIM_Run_Stop:'not_run'}}}});
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    expect(await screen.findByText(/Partial candidate checks passed; accepted scene storage is not confirmed/)).toBeTruthy();
    expect(screen.queryByText(/Approximate draft checks passed/)).toBeNull();
    expect(api.conversationAction).not.toHaveBeenCalled();
  });
  it('retains partial inventory on reload without claiming render or motion success',async()=>{
    const api=harness();api.workflow.mockResolvedValue({phase:'draft_ready',provider:{configured:true,label:'Saved provider'},
      site_draft:{schema_version:'2.0',artifact_id:null,revision:'scene',room_inventory:{items:[]},
        progressive_twin:{schema_version:'progressive-twin-1.0',policy_version:'progressive-acceptance-1.0',
          plan_sha256:'plan',current:true,inventory_count:2,materialized_count:1,
          axes:{draft_ready:'compiled_pending_runtime',sim_task_pass:'not_run',real_task_ready:'not_run',visual_review:'needs_refinement'},
          unresolved:[{id:'any_prop',parent_id:'any_host',code:'PHOTO_SUPPORT_PLACEMENT_UNAVAILABLE',
            reason:'SURFACE_CAPACITY_EXCEEDED',status:'deferred',impact:'task_context_required'}],physical_authority:false}}} as never);
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    expect(await screen.findByText(/1\/2 input objects materialized/)).toBeTruthy();
    expect(screen.getByText(/Draft compiled.*current 3D display checked separately.*physical execution unverified/)).toBeTruthy();
    expect(screen.getByText(/any_prop.*any_host/)).toBeTruthy();
    expect(api.conversationAction).not.toHaveBeenCalled();
  });
  it('shows expanded counts without claiming individual pose or complete coverage',async()=>{
    const api=harness();api.conversation.mockResolvedValue({...initial(),mode:'SIM',generation:{
      operation_id:'instances',state:'completed',summary:'Approximate inventory',can_cancel:false,started_at:'now',last_progress_at:'now',
      error:null,progress:{instance_grounding:{status:'count_partially_unverified',effective_object_count:4,
        expanded_groups:1,unresolved_counts:1,individual_pose_verified:false}}}});
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    expect(await screen.findByText(/4 provisional object instances recorded in inventory/)).toBeTruthy();
    expect(screen.getByText(/Object counts remain partly unverified/)).toBeTruthy();
    expect(api.conversationAction).not.toHaveBeenCalled();
  });
  it('shows automatic quality repair and host-approved scope without a new action',async()=>{
    const api=harness();api.conversation.mockResolvedValue({...initial(),mode:'SIM',generation:{
      operation_id:'scope',state:'running',summary:'Correcting layout',can_cancel:true,started_at:'now',last_progress_at:'now',
      error:null,progress:{stage:'photo_quality',repair_decision:{decision:'initial',repair_kind:'quality',stage_complete:false},
        stage_acceptance:{approximate_draft:'blocked',photo_quality:'needs_revision'},
        scope_decision:{schema_version:'geometry-scope-1.0',physical_authority:false,
          accepted:[{id:'desk',anchor_id:'device',reason_code:'support_alternative'}]}}}});
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    expect(await screen.findByText(/Correcting observed photo layout conflicts within the shared repair budget/)).toBeTruthy();
    expect(screen.getByText(/Host-approved related objects: desk \(support_alternative\)/)).toBeTruthy();
    expect(api.conversationAction).not.toHaveBeenCalled();
  });
  it('keeps draft readiness separate from uncertain photo fidelity',async()=>{
    const api=harness();api.conversation.mockResolvedValue({...initial(),mode:'SIM',generation:{
      operation_id:'quality',state:'completed',summary:'Approximate draft ready',can_cancel:false,started_at:'now',last_progress_at:'now',
      error:null,progress:{stage_acceptance:{approximate_draft:'passed',photo_quality:'uncertain',SIM_Run_Stop:'not_run'}}}});
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    expect(await screen.findByText(/Approximate draft checks passed/)).toBeTruthy();
    expect(screen.getByText(/Photo fidelity remains uncertain.*support relationships.*current 3D render/)).toBeTruthy();
    expect(api.conversationAction).not.toHaveBeenCalled();
  });
  it('shows real check advancement as incomplete with blocked and failed details',async()=>{
    const api=harness();api.conversation.mockResolvedValue({...initial(),mode:'SIM',generation:{
      operation_id:'checks',state:'failed',summary:'More correction required',can_cancel:false,started_at:'now',last_progress_at:'now',
      error:{code:'geometry_invalid',message:'Candidate failed',diagnostics:{
        repair_decision:{decision:'advanced_checks',progressed:true,stage_complete:false},
        scene_contract:{issues:[{code:'PHOTO_PLACEMENT_DRAPE_BELOW_FLOOR',target_ids:['fabric'],
          geometry_values_m:{bottom_m:-.4,support_top_m:.5},violation_m:.4,expected_bounds_m:{max_height_m:.5}}],
          issue_count:1,issues_truncated:false,blocked_checks:[],physical_authority:false,
          checks:[{check_id:'model_relations',status:'passed',blocked_by:[]},
            {check_id:'attachment_placement',status:'failed',blocked_by:[]},
            {check_id:'placement_validation',status:'blocked',blocked_by:['attachment_placement']}]}}}}});
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    expect(await screen.findByText(/Correction advanced to the next checks.*not ready to Run/)).toBeTruthy();
    expect(screen.getByText(/Object: fabric.*Bottom: -0.4 m.*Support top: 0.5 m.*Violation: 0.4 m/)).toBeTruthy();
    expect(screen.getByText('model_relations: passed')).toBeTruthy();
    expect(screen.getByText(/placement_validation: blocked.*attachment_placement/)).toBeTruthy();
    expect(api.conversationAction).not.toHaveBeenCalled();
  });
  it('distinguishes patch acceptance from the full scene check and shows bounded geometry feedback',async()=>{
    const api=harness();api.conversation.mockResolvedValue({...initial(),mode:'SIM',generation:{
      operation_id:'geometry',state:'failed',summary:'Checking scene',can_cancel:false,started_at:'now',last_progress_at:'now',
      error:{code:'geometry_invalid',message:'Scene check failed',diagnostics:{
        attempts:[{attempt_id:'patch',stage:'repair',validation:'passed',patch_shape:'passed',patch_effect:'changed',candidate_validation:'failed'}],
        scene_contract:{issues:[{code:'PHOTO_RELATION_WALL_HEIGHT_INVALID',path:'$.objects.shade.placement.elevation_m',
          target_ids:['shade'],actual_m:2.2,expected_bounds_m:{min_m:.25,max_m:2.15}}],
          issue_count:1,issues_truncated:false,blocked_checks:['packing'],physical_authority:false}}}}});
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    const history=await screen.findByRole('region',{name:'Generation attempt history',hidden:true});
    expect(history.textContent).toContain('Patch format: passed');
    expect(history.textContent).toContain('Full scene check: failed');
    expect(screen.getByText(/Object: shade.*Current: 2.2 m.*Allowed: 0.25 to 2.15 m/)).toBeTruthy();
    expect(api.conversationAction).not.toHaveBeenCalled();
  });
  it('shows every recorded attempt with repair role and ID without dispatching',async()=>{
    const api=harness();api.conversation.mockResolvedValue({...initial(),mode:'SIM',generation:{
      operation_id:'g',state:'failed',summary:'Saved failure',can_cancel:false,started_at:'now',last_progress_at:'now',
      error:{code:'REPAIR_STALLED',message:'No further repair',diagnostics:{attempts_total:4,attempts_truncated:false,
        attempts:Array.from({length:4},(_,index)=>({attempt_id:`attempt-${index}`,stage:index?'structure':'observer',
          role:index>1?'repair' as const:'initial' as const,status:'received',validation:index?'failed':'passed'}))}}}});
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    const history=await screen.findByRole('region',{name:'Generation attempt history',hidden:true});
    expect(history.textContent).toContain('Recorded attempts: 4/4');
    expect(history.textContent).toContain('Attempt ID: attempt-3');
    expect(history.textContent).toContain('structure · repair · received · Validation: failed');
    expect(api.conversationAction).not.toHaveBeenCalled();
  });
  it('shows grouped source errors and a no-progress repair without dispatching a retry',async()=>{
    const api=harness();api.conversation.mockResolvedValue({...initial(),mode:'SIM',generation:{
      operation_id:'g',state:'failed',summary:'Scene rejected',can_cancel:false,started_at:'now',last_progress_at:'now',
      error:{code:'provider_response_invalid',message:'Source evidence failed',diagnostics:{repair_no_progress:true,
        scene_contract:{issues:[{code:'PHOTO_LAYOUT_OBJECT_WITHOUT_EVIDENCE',path:'$.objects[0].source'},
          {code:'REPAIR_NO_PROGRESS',path:'$'}],issue_count:2,issues_truncated:false,blocked_checks:['packing'],physical_authority:false}}}}});
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    expect(await screen.findByText(/Repair made no progress/)).toBeTruthy();
    expect(screen.getByText('PHOTO_LAYOUT_OBJECT_WITHOUT_EVIDENCE · $.objects[0].source')).toBeTruthy();
    expect(screen.getByText('REPAIR_NO_PROGRESS · $')).toBeTruthy();
    expect(api.conversationAction).not.toHaveBeenCalled();
  });
  it('does not overwrite text typed before the first conversation and saved draft finish loading',async()=>{
    const api=harness();let finish!:(state:ConversationState)=>void;
    api.conversation.mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
    sessionStorage.setItem('twinpulse.chat.draft.chat-test','Older stored text');
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    fireEvent.change(screen.getByRole('textbox',{name:'Message TwinPulse'}),{target:{value:'My new bedroom description'}});
    await waitFor(()=>expect(api.conversation).toHaveBeenCalled());
    await act(async()=>{finish(initial());});
    await waitFor(()=>expect(screen.getByRole('button',{name:'Send'})).toHaveProperty('disabled',false));
    expect(screen.getByRole('textbox',{name:'Message TwinPulse'})).toHaveProperty('value','My new bedroom description');
    expect(api.conversationAction).not.toHaveBeenCalled();sessionStorage.removeItem('twinpulse.chat.draft.chat-test');
  });
  it('distinguishes failed apply from missing frame and opens its exact command',async()=>{
    const api=harness();const identity='a'.repeat(32);
    api.productState.mockResolvedValue({engine_connected:true,build_view:{phase:'apply',status:'failed',error_code:'RuntimeError',execution_id:identity},
      snapshot:{runtime_state:'error',safety_reason:'SIM_TEST_APPLY_FAILED'}} as never);
    const diagnostics=vi.fn().mockRejectedValue(new Error('Test detail unavailable'));Object.assign(api,{executionDiagnostics:diagnostics,listExecutionDiagnostics:vi.fn().mockResolvedValue({executions:[]})});
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    const alert=await screen.findByRole('alert');expect(alert.textContent).toContain('3D scene apply failed');
    expect(alert.textContent).not.toContain('Scene apply succeeded');
    fireEvent.click(screen.getByRole('button',{name:'View diagnostics'}));
    await waitFor(()=>expect(diagnostics).toHaveBeenCalledWith(identity));
    expect(api.conversationAction).not.toHaveBeenCalled();
  });
  it('exposes an unsaved in-memory draft without a Run card',async()=>{
    const api=harness();api.conversation.mockResolvedValue({...initial(),mode:'SIM'});
    api.workflow.mockResolvedValue({phase:'draft_ready',execution_id:'b'.repeat(32),error:{code:'project_persistence_failed',message:'save failed'},site_draft:{artifact_id:'a',revision:'r'}} as never);
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    expect((await screen.findByRole('alert')).textContent).toContain('draft is only in memory');
    expect(screen.getByRole('region',{name:'Current step'}).textContent).toContain('Scene not saved');
    expect(screen.queryByRole('heading',{name:'Run your Twin · SIM only'})).toBeNull();
    expect(api.conversationAction).not.toHaveBeenCalled();
  });
  it('shows actual bounded repair stage and elapsed time without dispatching another action',async()=>{
    const api=harness();
    api.conversation.mockResolvedValue({...initial(),mode:'SIM',generation:{operation_id:'g',request_id:'r',
      state:'running',summary:'Adjusting the layout · attempt 1 of 1',can_cancel:true,started_at:'now',last_progress_at:'now',error:null,
      progress:{stage:'planner',status:'running',elapsed_s:12.4,repair_count:1,max_repairs:1}}});
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    expect(await screen.findByText(/Stage: Designing the space · running · 12.4 s · Repairs: 1\/1/)).toBeTruthy();
    expect(api.conversationAction).not.toHaveBeenCalled();
  });
  it('opens a popup containing root, native, adapter and report failure diagnoses',async()=>{
    const api=harness();api.conversation.mockResolvedValue({...initial(),mode:'REAL',navigation:{
      review:null,error:null,current_pose_available:false,motion_authorized:false,physical_demo_ready:false,
      job:{job_id:'j',state:'FAILED',elapsed_s:2,error:'INPUT_DEADLINE_EXPIRED',
        native_cleanup_errors:[{stage:'mission_halt',code:'STOP_READBACK_UNCONFIRMED',error_type:'ValueError'}],
        cleanup_error:'OWNED_SENSOR_STOP_UNCONFIRMED',report_error:'MISSION_REPORT_STORAGE_FULL'}}});
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    const popup=await screen.findByRole('alertdialog',{name:'Goal mission failure'});
    for(const code of ['INPUT_DEADLINE_EXPIRED','STOP_READBACK_UNCONFIRMED','OWNED_SENSOR_STOP_UNCONFIRMED','MISSION_REPORT_STORAGE_FULL'])
      expect(popup.textContent).toContain(code);
    expect(api.conversationAction).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button',{name:'Dismiss failure'}));
    expect(screen.queryByRole('alertdialog')).toBeNull();
  });
  it.each(['DRIVING','MISSION_ARRIVED'])('connects right-sidebar battery and waypoint to the same expiring %s worker receipt',async phase=>{
    const api=harness();
    api.conversation.mockResolvedValue({...initial(),mode:'REAL',navigation:{review:null,error:null,
      current_pose_available:false,motion_authorized:false,physical_demo_ready:false,
      job:{job_id:'j',state:phase,elapsed_s:1,worker_active:true,telemetry_status:'RECENT_WORKER_RECEIPT',
        telemetry_age_s:.05,telemetry:{battery:{voltage_v:12,estimated_percent:83.3,measured_capacity:false},
          next_waypoint:{index:0,count:2,xy_room:[.1,.2]},motor_load:'UNSUPPORTED'}}}});
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    const battery=await screen.findByLabelText('Mission battery status');
    if(phase==='DRIVING'){
      await waitFor(()=>expect(battery.textContent).toContain('83.3% estimated'));
      expect(screen.getByLabelText('Mission next waypoint').textContent).toContain('1/2');
    }else{
      expect(battery.textContent).toBe('Current receipt unavailable');
      expect(screen.getByLabelText('Mission next waypoint').textContent).toBe('Current receipt unavailable');
    }
  });
  it('distinguishes saved wall correction from 3D recomposition and travel approval',async()=>{
    const api=harness();
    api.conversation.mockResolvedValue({...initial(),mode:'REAL',robot_id:'turtlebot3_burger',inspection:{
      state:'SURVEY_COMPLETE',owned:true,busy:false,motion_authorized:false,demo_ready:false,
      photo_correction:{status:'ROBOT_IDLE_BINDING_ACKNOWLEDGED',applied_revision:'a'.repeat(64),
        effective_revision:'b'.repeat(64),goal_revalidation:'SURVEY_CURRENT_SENSOR_VERIFIED_NO_GOAL',
        isaac_geometry_status:'RECOMPOSITION_REQUIRED'}}});
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>undefined}/>);
    expect(await screen.findByText(/Display progress is separate below; no goal travel approved/)).toBeTruthy();
    expect(api.conversationAction).not.toHaveBeenCalled();
  });
  it('separates static integrity gaps and bounded repair from current engine capabilities',async()=>{
    const api=harness();
    api.runtimeState.mockResolvedValue({status:'ready',message:'Engine ready',startup_checks:[
      {id:'web_dependencies',state:'needs_action',detail:'BUILD_DIGEST_MISMATCH',action:'Restore reviewed Web build',sampled_at:'now'},
      {id:'owned_engine_directory',state:'ready',detail:'Created owned directory',action:null,sampled_at:'now',attempts:1}]} as never);
    api.productState.mockResolvedValue({engine_connected:true,engine_readiness:{
      site_scene_build_v2:{ready:false,code:'CAPABILITY_MISSING'}}} as never);
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    await waitFor(()=>expect(api.conversation).toHaveBeenCalled());
    fireEvent.click(screen.getByRole('button',{name:/Readiness/}));
    expect(await screen.findByText(/BUILD_DIGEST_MISMATCH Restore reviewed Web build/)).toBeTruthy();
    expect(screen.getByText(/Runtime capability · site scene build v2 · CAPABILITY_MISSING/)).toBeTruthy();
    expect(screen.getByText(/Repair attempts: 1\/1/)).toBeTruthy();
  });
  it('generation chosen here prepares its polled preview; restored history never rearms it',async()=>{
    const api=harness();
    const snapshot={applied_revision:'scene',runtime_state:'built',run_id:null,safety_state:null,capabilities:['site_simulation_v1','site_simulation_preview_v1']};
    const operations=[{command_id:'build',command_type:'build_site_scene',status:'succeeded',receipt:null}];
    api.productState.mockResolvedValue({engine_connected:true,lease_owned:true,snapshot,operations,
      engine_readiness:{site_scene_build_v2:{ready:true}}} as never);
    api.workflow.mockResolvedValue({phase:'draft_ready',provider:{configured:true,label:'Explicit fixture'},site_draft:{revision:'scene',artifact_id:'artifact'}} as never);
    Object.assign(api,{acquireLease:vi.fn().mockResolvedValue({control_lease_id:'lease'}),acknowledge:vi.fn().mockResolvedValue({}),renewLease:vi.fn().mockResolvedValue({}),command:vi.fn().mockResolvedValue(operations[0]),simulationRun:vi.fn()});
    const view=render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    await waitFor(()=>expect(api.conversation).toHaveBeenCalled());
    fireEvent.change(screen.getByRole('textbox',{name:'Message TwinPulse'}),{target:{value:'Create my room'}});
    fireEvent.click(screen.getByRole('button',{name:'Send'}));
    await screen.findByRole('radio',{name:'Simulation only'});
    const state=await api.conversation();
    let request='';
    const job={operation_id:'generate-1',state:'running',summary:'Generating',can_cancel:true,started_at:'now',last_progress_at:'now',error:null};
    api.conversationAction.mockImplementation(async body=>{request=body.request_id;return {...state,mode:'SIM',generation:{...job,request_id:body.request_id}} as ConversationState;});
    fireEvent.click(screen.getByRole('radio',{name:'Simulation only'}));
    fireEvent.click(screen.getByRole('button',{name:'Create Twin'}));
    await waitFor(()=>expect(request).not.toBe(''));
    const completed:ConversationState={...state,cards:state.cards.map(c=>({...c,state:'answered',selected_choice_id:'sim'})),revision:2,cursor:2,mode:'SIM',generation:{...job,state:'completed',can_cancel:false},
      simulation_review:{request_id:request,text:'Generated SIM preview',scene_revision:'scene',start_source:'planned_sim_spawn',target:null,choices:[],drawing:{bounds:[-2,2,-2,2],boxes:[],discs:[]},
        plan:{plan_id:'plan',scene_revision:'scene',mode:'SIM',asset_id:'turtlebot3_burger',start:[0,0],goal:[0,.4],route:[[0,.4]],yaw_rad:0,max_linear_mps:.15,max_angular_rps:.6,physical_authority:false}}};
    api.conversation.mockResolvedValue(completed);
    await waitFor(()=>expect(screen.getByRole('button',{name:'Run simulation'})).toHaveProperty('disabled',false));
    expect((api as unknown as {simulationRun:ReturnType<typeof vi.fn>}).simulationRun).not.toHaveBeenCalled();
    view.unmount();
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    await screen.findByRole('heading',{name:'Run your Twin · SIM only'});
    expect(screen.getByRole('button',{name:'Run simulation'})).toHaveProperty('disabled',true);
    expect((api as unknown as {acquireLease:ReturnType<typeof vi.fn>}).acquireLease).toHaveBeenCalledTimes(1);
  });
  it('does not poll the viewer before App authentication completes',async()=> {
    const api={...harness(),viewportState:vi.fn().mockResolvedValue({state:'waiting',frame:null})};
    let finish:()=>void=()=>{};
    api.bootstrap.mockImplementation(()=>new Promise<void>(resolve=>{finish=resolve;}));
    const component=render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    expect(api.viewportState).not.toHaveBeenCalled();
    await act(async()=>finish());
    await waitFor(()=>expect(api.viewportState).toHaveBeenCalled());
    component.unmount();
  });
  it('is the default App, not the old multi-form workflow',async()=> {
    const api=harness();render(<App api={api as unknown as TwinPulseApi}/>);
    expect(await screen.findByRole('textbox',{name:'Message TwinPulse'})).toBeTruthy();
    expect(screen.queryByText('Virtual controller')).toBeNull();
  });
  it('shows a typed question in the conversation, disables repeat send, never auto answers',async()=> {
    const api=harness();render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    await waitFor(()=>expect(api.conversation).toHaveBeenCalled());
    fireEvent.change(screen.getByRole('textbox'),{target:{value:'Build a bedroom'}});
    fireEvent.click(screen.getByRole('button',{name:'Send'}));
    expect(await screen.findByRole('radio',{name:'Simulation only'})).toBeTruthy();
    expect(screen.getByRole('button',{name:'Continue'})).toHaveProperty('disabled',true);
    expect(screen.getByText('Current step · choose an option, then continue')).toBeTruthy();
    expect((screen.getByRole('button',{name:'Send'}) as HTMLButtonElement).disabled).toBe(true);
    expect(api.conversationAction).toHaveBeenCalledTimes(1);
  });
  it('locks duplicate clicks locally before the HTTP response returns',async()=> {
    const api=harness();let finish:(s:ConversationState)=>void=()=>{};
    api.conversationAction.mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    await waitFor(()=>expect(api.conversation).toHaveBeenCalled());
    fireEvent.change(screen.getByRole('textbox'),{target:{value:'Build'}});
    fireEvent.click(screen.getByRole('button',{name:'Send'}));fireEvent.click(screen.getByRole('button',{name:'Send'}));
    expect(api.conversationAction).toHaveBeenCalledTimes(1);
    expect(screen.getByText('Sending…')).toBeTruthy();
    await act(async()=>finish(initial()));
  });
  it('keeps the draft and image when rejected, and reports the actual reason',async()=> {
    const api=harness();api.conversationAction.mockRejectedValue(new ApiError('existing_scene_protected','Existing scene is protected'));
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    await waitFor(()=>expect(api.conversation).toHaveBeenCalled());
    fireEvent.change(screen.getByRole('textbox'),{target:{value:'Build'}});
    fireEvent.click(screen.getByRole('button',{name:'Send'}));
    expect(await screen.findByRole('alert')).toHaveProperty('textContent',expect.stringContaining('Existing scene is protected'));
    expect((screen.getByRole('textbox') as HTMLTextAreaElement).value).toBe('Build');
  });
  it('does not send on IME Enter or Shift+Enter and never leaks WASD to drive',async()=> {
    const api=harness();render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    await waitFor(()=>expect(api.conversation).toHaveBeenCalled());
    const box=screen.getByRole('textbox');fireEvent.change(box,{target:{value:'방을 만들어줘'}});
    fireEvent.keyDown(box,{key:'Enter',isComposing:true});fireEvent.keyDown(box,{key:'Enter',shiftKey:true});fireEvent.keyDown(box,{key:'w'});
    expect(api.conversationAction).not.toHaveBeenCalled();
    fireEvent.keyDown(box,{key:'Enter'});await waitFor(()=>expect(api.conversationAction).toHaveBeenCalledTimes(1));
  });
  it('a lost response is queried, not repeated',async()=> {
    const api=harness();api.conversationAction.mockRejectedValue(new TypeError('Failed to fetch'));
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    await waitFor(()=>expect(api.conversation).toHaveBeenCalled());
    fireEvent.change(screen.getByRole('textbox'),{target:{value:'Build'}});fireEvent.click(screen.getByRole('button',{name:'Send'}));
    expect(await screen.findByRole('button',{name:'Check saved result · no re-execution'})).toBeTruthy();
    expect(api.conversationAction).toHaveBeenCalledTimes(1);
    expect((screen.getByRole('textbox') as HTMLTextAreaElement).value).toBe('Build');
  });
  it('shows engine failure separately and keeps the failed reason after dismiss',async()=> {
    const api=harness();api.runtimeState.mockResolvedValue({status:'error',phase:'isaac_init',message:'Owned engine exited',retry_remaining:1} as never);
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    expect(await screen.findByRole('alert')).toHaveProperty('textContent',expect.stringContaining('isaac_init'));
    fireEvent.click(screen.getByRole('button',{name:'Dismiss'}));
    expect(screen.queryByRole('alert')).toBeNull();expect(screen.getByText(/Isaac runtime failed/)).toBeTruthy();
  });
  it('opens the exact runtime monitor execution rather than a recent unrelated record',async()=>{
    const api={...harness(),executionDiagnostics:vi.fn().mockRejectedValue(new Error('Exact fixture detail unavailable'))};
    api.runtimeState.mockResolvedValue({status:'error',phase:'engine_exited',message:'Owned engine exited',diagnostic_execution_id:'a'.repeat(32)} as never);
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    await screen.findByRole('alert');fireEvent.click(screen.getByRole('button',{name:/^View diagnostics$/}));
    await waitFor(()=>expect(api.executionDiagnostics).toHaveBeenCalledWith('a'.repeat(32)));
    expect(await screen.findByText('Exact fixture detail unavailable')).toBeTruthy();
  });
  it('shows current SIM work in the Twin pane, but never stale engine work',async()=>{
    const api=harness();const sim={engine_connected:true,snapshot:{applied_revision:'scene',run_id:'sim-plan',runtime_state:'running',
      capabilities:['site_simulation_v1'],telemetry_available:true}};
    api.productState.mockResolvedValue(sim as never);
    api.workflow.mockResolvedValue({phase:'draft_ready',provider:{configured:false,label:'Provider'},site_draft:{revision:'scene'}} as never);
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    expect(await screen.findByText('SIM navigation · running')).toBeTruthy();
    expect(screen.getByText('Burger · simulated')).toBeTruthy();
    api.productState.mockResolvedValue({...sim,engine_connected:false} as never);
    await waitFor(()=>expect(screen.queryByText('SIM navigation · running')).toBeNull());
    expect(screen.getByText('Task state unavailable')).toBeTruthy();
  });
  it('shows a current engine safety failure even without pose telemetry',async()=>{
    const api=harness();api.productState.mockResolvedValue({engine_connected:true,snapshot:{applied_revision:'scene',run_id:'sim-plan',runtime_state:'error',
      capabilities:['site_simulation_v1'],telemetry_available:false,safety_state:'simulation_error',safety_reason:'RuntimeError: SIM_PROGRESS_STALLED'}} as never);
    api.workflow.mockResolvedValue({phase:'draft_ready',provider:{configured:false,label:'Provider'},site_draft:{revision:'scene'}} as never);
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    expect(await screen.findByRole('alert')).toHaveProperty('textContent',expect.stringContaining('SIM_PROGRESS_STALLED'));
    expect(screen.getByRole('region',{name:'Current step'}).textContent).toContain('Isaac execution stopped');
    expect(screen.getByText('SIM navigation · error')).toBeTruthy();
  });
  it('opens the exact runtime fault instead of an unrelated generation failure',async()=>{
    const api=harness();const identity='e'.repeat(32);
    api.productState.mockResolvedValue({engine_connected:true,snapshot_execution_id:identity,
      snapshot:{runtime_state:'error',safety_state:'simulation_error',safety_reason:'RuntimeError: SIM_TEST_POSE_LOST',
        telemetry_available:false}} as never);
    api.workflow.mockResolvedValue({error:'unrelated generation failure',execution_id:'f'.repeat(32)} as never);
    const diagnostics=vi.fn().mockRejectedValue(new Error('Saved fault unavailable'));
    Object.assign(api,{executionDiagnostics:diagnostics,executionList:vi.fn()});
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    await screen.findByRole('button',{name:'View diagnostics'});
    fireEvent.click(screen.getByRole('button',{name:'View diagnostics'}));
    await waitFor(()=>expect(diagnostics).toHaveBeenCalledWith(identity));
    expect(api.conversationAction).not.toHaveBeenCalled();
  });
  it('shows missing first frame separately from successful apply and opens its exact diagnosis',async()=>{
    const api=harness();const identity='a'.repeat(32);
    api.productState.mockResolvedValue({engine_connected:true,build_view:{status:'failed',
      error_code:'first_current_frame_timeout',execution_id:identity}} as never);
    const diagnostics=vi.fn().mockRejectedValue(new Error('Saved observation unavailable'));
    Object.assign(api,{executionDiagnostics:diagnostics,executionList:vi.fn()});
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    expect(await screen.findByRole('alert')).toHaveProperty('textContent',expect.stringContaining('Scene apply succeeded'));
    expect(screen.getByRole('region',{name:'Current step'}).textContent).toContain('3D display not confirmed');
    fireEvent.click(screen.getByRole('button',{name:'View diagnostics'}));
    await waitFor(()=>expect(diagnostics).toHaveBeenCalledWith(identity));
    expect(api.conversationAction).not.toHaveBeenCalled();
  });
  it('does not hide a stage failure after run identity and pose were invalidated',async()=>{
    const api=harness();api.productState.mockResolvedValue({engine_connected:true,snapshot:{applied_revision:null,run_id:null,runtime_state:'stage_invalid',
      capabilities:['site_simulation_v1'],telemetry_available:false,safety_state:null,safety_reason:'Stage changed or site geometry no longer matches the build'}} as never);
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    expect(await screen.findByRole('alert')).toHaveProperty('textContent',expect.stringContaining('site geometry no longer matches'));
  });
  it('drop and paste keep one removable image and invalid attachments keep the draft',async()=> {
    vi.stubGlobal('URL',{createObjectURL:vi.fn(()=> 'blob:preview'),revokeObjectURL:vi.fn()});
    const api=harness();render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    await waitFor(()=>expect(api.conversation).toHaveBeenCalled());
    const box=screen.getByRole('textbox');fireEvent.change(box,{target:{value:'My room'}});
    fireEvent.paste(box,{clipboardData:{files:[new File(['image'],'room.png',{type:'image/png'})]}});
    expect(screen.getByAltText('Attached image preview')).toBeTruthy();
    fireEvent.drop(box.closest('form')!,{dataTransfer:{files:[new File(['image'],'second.png',{type:'image/png'})]}});
    expect(screen.getByRole('alert')).toHaveProperty('textContent',expect.stringContaining('One image per message'));
    fireEvent.click(screen.getByRole('button',{name:'Remove image'}));
    fireEvent.drop(box.closest('form')!,{dataTransfer:{files:[new File(['bad'],'room.txt',{type:'text/plain'})]}});
    expect(screen.queryByAltText('Attached image preview')).toBeNull();expect(box).toHaveProperty('value','My room');
    expect(api.conversationAction).not.toHaveBeenCalled();vi.unstubAllGlobals();
  });
  it('accepts an items-only image pasted outside the input, without dispatch or losing text',async()=>{
    vi.stubGlobal('URL',{createObjectURL:vi.fn(()=> 'blob:preview'),revokeObjectURL:vi.fn()});
    const api=harness();render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    await waitFor(()=>expect(api.conversation).toHaveBeenCalled());
    const box=screen.getByRole('textbox',{name:'Message TwinPulse'});
    fireEvent.change(box,{target:{value:'Keep my room description'}});
    const image=new File(['image'],'clipboard.png',{type:'image/png'});
    fireEvent.paste(document.body,{clipboardData:{files:[],items:[{kind:'file',type:'image/png',getAsFile:()=>image}],getData:()=>''}});
    expect(screen.getByAltText('Attached image preview')).toBeTruthy();
    expect(box).toHaveProperty('value','Keep my room description');expect(api.conversationAction).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});
