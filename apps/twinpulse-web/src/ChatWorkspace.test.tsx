// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
// @ts-expect-error The UI tsconfig omits Node types; this read-only CSS fixture runs only in Vitest.
import { readFileSync } from 'node:fs';
import { ActionCard, ChatWorkspace, conversationTurns, generationSourceAttachment, generationResumePresentation } from './ChatWorkspace';
import { App } from './App';
import { ApiError } from './api';
import type { TwinPulseApi } from './api';
import type { ConversationState } from './conversation-types';
import type {LibraryWorkspaceState} from './library-workspace-types';

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

describe('Imported space next steps',()=>{
  it('offers to rebuild the Twin in Isaac when the imported scene is not applied, through the environment Build action',async()=>{
    const api=Object.assign(harness(),{environmentAction:vi.fn().mockResolvedValue({})});
    api.runtimeState.mockResolvedValue({status:'ready',message:'ready'} as never);
    api.productState.mockResolvedValue({engine_connected:true,snapshot:{applied_revision:'other'}} as never);
    api.workflow.mockResolvedValue({phase:'draft_ready',provider:{configured:true,label:'Import'},site_draft:{revision:'a'.repeat(64),scene_state_sha256:'b'.repeat(64),input_revision:'input',artifact_id:'artifact',provider_name:'local-environment-import'}} as never);
    render(<ChatWorkspace api={api as never} advanced={()=>{}}/>);
    const button=await screen.findByRole('button',{name:'Rebuild Twin in Isaac'});
    await waitFor(()=>expect((button as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(button);
    await waitFor(()=>expect(api.environmentAction).toHaveBeenCalledTimes(1));
    expect(api.environmentAction.mock.calls[0][0].action).toBe('build');
  });
  // An imported room after a committed photo add (Twin edits: Auto-apply), as in the 2026-10-27 real-app run.
  const revision='a'.repeat(64),committed={operation_id:'environment_edit_photo',state:'COMMITTED',engine_acknowledged:true,durable_committed:true,current_frame:true,result_revision:revision,error:null,command_id:'c'};
  const said=(message_id:string,role:'user'|'assistant',content:string)=>({message_id,role,content,status:'completed',attachments:[],created_at:'now',operation_id:null});
  function importedChat(chat:Record<string,unknown>={}){
    const api=harness(),imported={project_id:'room',status:'imported',job_id:'inspection',error:null,source_name:'Room.usdz',source_sha256:'c'.repeat(64),
      units_basis:'authored',objects:[{id:'Sofa0',category:'Sofa',label:'Sofa0',position_m:[1,1,0]}],scene_revision:revision};
    let state={...initial(),mode:'REAL',twin_edit_approval:'auto',messages:[said('m1','user','Twin edits: Auto-apply')],scene_edit_transaction:committed,...chat} as ConversationState;
    api.conversation.mockImplementation(async()=>state);api.runtimeState.mockResolvedValue({status:'ready',message:'ready'} as never);
    api.conversationAction.mockImplementation(async body=>{if(body.action==='message'&&body.text==='Undo'){const question='Undo the last edit as a fresh revision? Review the before/after changes, then update this Twin?';
      state={...state,revision:1,cursor:1,accepted_request_ids:[body.request_id],messages:[...state.messages,said('m2','user','Undo'),said('m3','assistant',question)],
        cards:[{id:'q3',message_id:'m3',kind:'scene_edit',question,state:'waiting',selected_choice_id:null,operation_id:'edit_undo',expected_session_revision:1,
          choices:[{id:'apply',label:'Apply and update Twin',enabled:true,disabled_reason:null},{id:'cancel',label:'Cancel',enabled:true,disabled_reason:null}]}],
        scene_edit_preview:{operation:{operation_id:'edit_undo'},preview_digest:'d',source_revision:'s',parent_revision:revision,result_revision:'e'.repeat(64),
          affected_before:{Added_basket:{position_m:[1.8,1.8,.2],dimensions_m:[.35,.3,.4],kind:'basket'}},affected_after:{},preserved_object_count:1,review_required:true,physical_validation:'NOT_RUN'}} as ConversationState;}
      return state;});
    api.productState.mockResolvedValue({engine_connected:true,operations:[],snapshot:{applied_revision:revision}} as never);
    api.workflow.mockResolvedValue({phase:'draft_ready',provider:{configured:true,label:'Import'},site_draft:{revision,scene_state_sha256:'b'.repeat(64),input_revision:'input',artifact_id:'artifact',provider_name:'local-environment-import'}} as never);
    return Object.assign(api,{environment:vi.fn(async()=>imported),environmentAction:vi.fn(async()=>imported),sceneEditTransaction:vi.fn(async()=>null),applyEnvironmentEdit:vi.fn()});
  }
  const openPanel=async()=>{fireEvent.click(screen.getByRole('button',{name:'Import space'}));
    const panel=await screen.findByRole('region',{name:'Import space'});await within(panel).findByText('Space imported · saved environment.');return panel;};
  it('undoes a committed photo add from the open Import space panel with the Apply of that Undo in view',async()=>{
    // 2026-10-27 real app (Control view, 787 px tall): the open panel covered the chat's Twin update card, and then the Apply card of the chat Undo it asks for.
    const api=importedChat(),view=render(<ChatWorkspace api={api as never} advanced={()=>{}}/>);
    within(await screen.findByRole('status',{name:'Twin update status'})).getByRole('button',{name:'Undo last edit · preview'});
    const panel=await openPanel();fireEvent.wheel(document.querySelector('.chat-message-list')!,{deltaY:-120});  // the reader scrolled the chat up looking for the card
    const undo=within(panel).getByRole('button',{name:'Undo last edit in chat · closes this panel'});
    expect(undo.parentElement!.style.position).toBe('sticky');  // stays at the panel's bottom edge however far the panel is scrolled
    await waitFor(()=>expect(undo).toHaveProperty('disabled',false));fireEvent.click(undo);
    await waitFor(()=>expect(api.conversationAction).toHaveBeenCalledTimes(1));
    expect(api.conversationAction.mock.calls[0][0]).toEqual({action:'message',request_id:expect.any(String),text:'Undo',mode:'change',attachment:null});  // the same chat Undo, no new action
    expect(api.environmentAction).not.toHaveBeenCalled();
    const card=await screen.findByRole('region',{name:/^Undo the last edit as a fresh revision\?/});
    expect(screen.queryByRole('region',{name:'Import space'})).toBeNull();  // nothing covers the card any more
    within(card).getByRole('radio',{name:'Apply and update Twin'});within(card).getByRole('button',{name:'Continue'});
    await act(async()=>{});expect(screen.queryByRole('button',{name:'New updates ↓'})).toBeNull();  // the chat follows its newest card again
    view.unmount();
  });
  it('offers the panel Undo only for a committed edit while the chat flow is idle and its scene observation fresh',async()=>{
    // The same gates as the chat's Twin update card, now on a second surface (2026-10-27 review).
    const waiting=importedChat({revision:1,cursor:1,messages:[said('m1','user','Twin edits: Auto-apply'),said('m2','assistant','Do you have a physical robot?')],
      cards:[{id:'q2',message_id:'m2',kind:'robot_presence',question:'Do you have a physical robot?',state:'waiting',selected_choice_id:null,operation_id:null,expected_session_revision:1,
        choices:[{id:'sim',label:'Simulation only',enabled:true,disabled_reason:null},{id:'real',label:'Use my robot',enabled:true,disabled_reason:null}]}]});
    const stale=importedChat(),draft=await stale.workflow();stale.workflow.mockRejectedValue(new Error('workflow delayed')).mockResolvedValueOnce(draft);  // first read only
    const cases=[[importedChat(),()=>screen.findByText('Twin update · COMMITTED'),true],[waiting,()=>screen.findByRole('region',{name:'Do you have a physical robot?'}),false],
      [stale,()=>screen.findByRole('status',{name:'Workflow observation'},{timeout:3000}),false],
      [importedChat({scene_edit_transaction:{...committed,state:'ROLLED_BACK',durable_committed:false}}),()=>screen.findByText('Twin update · ROLLED BACK'),false]] as const;
    for(const [api,settled,offered] of cases){const view=render(<ChatWorkspace api={api as never} advanced={()=>{}}/>);
      const panel=await openPanel();await settled();
      await waitFor(()=>expect(!!within(panel).queryByRole('button',{name:'Undo last edit in chat · closes this panel'})).toBe(offered));
      expect(!!within(screen.getByRole('status',{name:'Twin update status'})).queryByRole('button',{name:'Undo last edit · preview'})).toBe(offered);  // the chat card agrees
      view.unmount();}
  });
});

describe('Chat-first product workspace',()=> {
  beforeEach(()=>vi.stubGlobal('Image',class {src='';naturalWidth=960;naturalHeight=640;async decode(){}}));
  afterEach(()=>vi.unstubAllGlobals());
  it('opens Control view with the live render at the top and a Twin pane that input focus cannot scroll',async()=>{
    vi.stubGlobal('innerWidth',1522);
    const api=harness();const view=render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    const pane=await screen.findByRole('complementary',{name:'Digital Twin'});
    pane.scrollTop=1150;  // 2026-10-27: a robot-card input focus in the normal view left the render and Stop scrolled away
    fireEvent.click(screen.getByRole('button',{name:'Control view'}));
    expect(pane.scrollTop).toBe(0);
    const css=readFileSync('src/chat.css','utf8');
    expect(css.match(/\.is-control-view \.chat-twin-panel \{([^}]+)\}/)![1]).toMatch(/overflow:clip;/);  // hidden still scrolls on focus
    expect(readFileSync('src/styles.css','utf8').match(/\.robot-fleet-drawer>header \{([^}]+)\}/)![1]).toMatch(/position:sticky; top:0;/);  // Stop stays in view
    view.unmount();
  });
  it('recovers the first conversation read failure without requiring a restored draft or replaying an action',async()=>{
    const api=harness();api.conversation.mockRejectedValueOnce(new ApiError('state_read_timeout','First local state read exceeded 3 seconds.'));
    const view=render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    await screen.findAllByText('First local state read exceeded 3 seconds.');
    fireEvent.change(screen.getByRole('textbox',{name:'Message TwinPulse'}),{target:{value:'typed while the first read is unavailable'}});
    await waitFor(()=>expect(screen.getByText('chat-test · Choose a mode')).toBeTruthy(),{timeout:2500});
    expect(screen.getByRole('textbox',{name:'Message TwinPulse'})).toHaveProperty('value','typed while the first read is unavailable');
    expect(api.bootstrap).toHaveBeenCalledOnce();expect(api.conversation.mock.calls.length).toBeGreaterThanOrEqual(2);
    expect(api.conversationAction).not.toHaveBeenCalled();view.unmount();
  });
  it('recovers a first-read timeout after a successful project switch without restoring the old context',async()=>{
    const api=harness();let switched=false,failNext=false;
    api.runtimeState.mockResolvedValue({status:'ready'} as never);
    api.conversation.mockImplementation(async()=>{
      if(failNext){failNext=false;throw new ApiError('state_read_timeout','Selected first read exceeded 3 seconds.');}
      return {...initial(),project_id:switched?'next':'old',context_id:switched?'ctx-next':'ctx-old',revision:switched?1:900,
        messages:[{message_id:switched?'next-message':'old-message',role:'user' as const,content:switched?'Selected context restored':'Old context content',status:'completed',attachments:[],created_at:'now',operation_id:null}]};
    });
    const extended={...api,context:'ctx-old',projects:vi.fn(async()=>({projects:[{project_id:'old',active:true,status:'review_required'},{project_id:'next',active:false,status:'empty'}]})),
      switchProject:vi.fn(async()=>{switched=true;failNext=true;extended.context='ctx-next';return {status:'switched',project_id:'next',context_id:'ctx-next',new_session_required:false};})};
    const view=render(<ChatWorkspace api={extended as unknown as TwinPulseApi} advanced={()=>{}}/>);
    await screen.findByText('Old context content');fireEvent.click(await screen.findByRole('button',{name:'Open next'}));
    await screen.findAllByText('Selected first read exceeded 3 seconds.');
    await waitFor(()=>expect(screen.getAllByText('Selected context restored').length).toBeGreaterThan(0),{timeout:2500});
    expect(screen.queryByText('Old context content')).toBeNull();expect(extended.switchProject).toHaveBeenCalledOnce();
    expect(api.bootstrap).toHaveBeenCalledOnce();expect(api.conversationAction).not.toHaveBeenCalled();view.unmount();
  });
  it('does not promote a fulfilled old-context body into current connection or writer readiness',async()=>{
    const api=Object.assign(harness(),{context:'ctx-current'});
    api.conversation.mockResolvedValue({...initial(),context_id:'ctx-old',mode:'SIM',messages:[{
      message_id:'old',role:'user',content:'Rejected old body',status:'completed',attachments:[],created_at:'now',operation_id:null}]});
    api.workflow.mockResolvedValue({phase:'draft_ready',provider:{configured:true,label:'Saved'},site_draft:{revision:'a'.repeat(64),scene_state_sha256:'b'.repeat(64),input_revision:'input',artifact_id:'artifact'}} as never);
    const view=render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    await screen.findAllByText('Waiting for the selected conversation state. No action was replayed.');
    expect(screen.queryByText('Rejected old body')).toBeNull();expect(screen.getByRole('button',{name:'Send'})).toHaveProperty('disabled',true);
    api.conversation.mockResolvedValue({...initial(),context_id:'ctx-current'});
    await waitFor(()=>expect(screen.getByText('chat-test · Choose a mode')).toBeTruthy(),{timeout:2500});
    expect(api.conversationAction).not.toHaveBeenCalled();view.unmount();
  });
  it.each(['workflow','conversation','product'])('retains the sensor panel but locks scene writers across a temporary %s read failure',async failed=>{
    const revision='a'.repeat(64),sha='b'.repeat(64);
    const api=Object.assign(harness(),{context:'ctx-a',sceneSensorContext:vi.fn(),automaticMaps:vi.fn().mockResolvedValue({maps:[]}),
      sceneSensorSurveys:vi.fn().mockResolvedValue({surveys:[]}),sceneEditTransaction:vi.fn().mockResolvedValue(null),
      obstacleFeedbackState:vi.fn().mockResolvedValue({schema_version:'obstacle-feedback-1.0',context:{project_id:'chat-test',current_scene_revision:revision,current_state_sha256:sha},observations:[],targets:[],physical_authority:false})});
    const chat={...initial(),mode:'SIM' as const,messages:[{message_id:'source',role:'user' as const,content:'Saved room',status:'completed' as const,attachments:[],created_at:'now',operation_id:null}]};
    const workflow={phase:'draft_ready',provider:{configured:true,label:'Saved'},site_draft:{revision,scene_state_sha256:sha,input_revision:'input-a',artifact_id:'artifact'}};
    api.conversation.mockResolvedValue(chat);api.workflow.mockResolvedValue(workflow as never);
    const view=render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    fireEvent.click(await screen.findByText('Sensor correction',{selector:'summary'}));
    const panel=await screen.findByRole('region',{name:'Obstacle observation feedback'});await screen.findByText(/No saved obstacle observation/);
    const undo=screen.getByRole('button',{name:'Preview Undo last scene edit'});expect(undo).toHaveProperty('disabled',false);
    fireEvent.change(screen.getByRole('textbox',{name:'Message TwinPulse'}),{target:{value:'Move the chair'}});
    const source=failed==='workflow'?api.workflow:failed==='conversation'?api.conversation:api.productState;
    source.mockRejectedValue(new ApiError('state_read_timeout','Supplementary 3-second read failure'));
    await waitFor(()=>expect(undo).toHaveProperty('disabled',true),{timeout:2500});
    expect(screen.getByRole('region',{name:'Obstacle observation feedback'})).toBe(panel);
    expect(screen.getByRole('button',{name:'Send'})).toHaveProperty('disabled',true);fireEvent.click(undo);expect(api.conversationAction).not.toHaveBeenCalled();
    if(failed!=='product')expect(screen.getByRole('status',{name:'Workflow observation'})).toHaveProperty('textContent',expect.stringContaining('display only'));
    else expect(screen.getByRole('status',{name:'Scene state observation'})).toBeTruthy();
    // Other successful observations do not confer freshness on the failed read.
    await new Promise(resolve=>setTimeout(resolve,800));expect(undo).toHaveProperty('disabled',true);
    if(failed==='workflow')api.workflow.mockResolvedValue(workflow as never);
    if(failed==='conversation')api.conversation.mockResolvedValue(chat);
    if(failed==='product')api.productState.mockResolvedValue({engine_connected:false});
    await waitFor(()=>expect(undo).toHaveProperty('disabled',false),{timeout:2500});
    expect(screen.getByRole('region',{name:'Obstacle observation feedback'})).toBe(panel);
    expect(api.obstacleFeedbackState).toHaveBeenCalledOnce();expect(api.conversationAction).not.toHaveBeenCalled();view.unmount();
  });
  it.each(['empty','null-draft','context'])('does not retain an old sensor scene after a confirmed %s change',async change=>{
    const api=Object.assign(harness(),{context:'ctx-a',sceneSensorContext:vi.fn()});
    api.conversation.mockResolvedValue({...initial(),mode:'SIM',messages:[{message_id:'source',role:'user',content:'Saved',status:'completed',attachments:[],created_at:'now',operation_id:null}]});
    api.workflow.mockResolvedValue({phase:'draft_ready',provider:{configured:false,label:'Saved'},site_draft:{revision:'r',input_revision:'i',artifact_id:'artifact'}} as never);
    const view=render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);await screen.findByRole('region',{name:'Obstacle observation feedback'});
    if(change==='context'){api.context='ctx-b';api.workflow.mockRejectedValue(new ApiError('state_read_timeout','Not observed'));view.rerender(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);}
    else api.workflow.mockResolvedValue({phase:change==='empty'?'empty':'draft_ready',provider:{configured:false,label:'Saved'},site_draft:null} as never);
    await waitFor(()=>expect(screen.queryByRole('region',{name:'Obstacle observation feedback'})).toBeNull(),{timeout:2500});
    expect(api.conversationAction).not.toHaveBeenCalled();view.unmount();
  });
  it.each([
    ['GENERATION_CANCELLED','Continue unfinished work'],['PROVIDER_OUTPUT_TRUNCATED','Continue unfinished work'],
    ['NEEDS_REQUEST_BUDGET','Review resume options'],
    ...['GENERATION_LOCAL_STATE_FAILED','REPAIR_STALLED','REPAIR_LIMIT_REACHED','QUALITY_REPAIR_LIMIT_REACHED',
      'REQUEST_LIMIT_REACHED','NEEDS_TIME_BUDGET','REMOTE_OUTCOME_UNKNOWN','VALIDATION_EVIDENCE_FAILED']
      .map(reason=>[reason,'Recheck retained draft · no new model requests']),
    ['UNRECOGNIZED_STOP','Recheck retained draft'],['generation_cancelled','Recheck retained draft'],
  ])('describes the retained budget stop %s without changing continuation authority', (reason,label)=>{
    const job={progress:{budget:{stop_reason:reason}},error:{code:'provider_response_invalid',message:'Saved provider failure'}} as NonNullable<ConversationState['generation']>;
    const presentation=generationResumePresentation(job);expect(presentation.label).toBe(label);
    expect(presentation.explanation).not.toContain('Saved provider failure');
    if(reason==='NEEDS_REQUEST_BUDGET')expect(presentation.explanation).toContain('check the saved stage and remaining allowance');
  });
  it('uses known public cancellation only as a fallback and keeps missing or conflicting generic status neutral',()=>{
    const job=(code?:string)=>({error:code?{code,message:'Saved failure'}:null}) as NonNullable<ConversationState['generation']>;
    expect(generationResumePresentation(job('generation_cancelled')).label).toBe('Continue unfinished work');
    expect(generationResumePresentation(job()).label).toBe('Recheck retained draft');
    expect(generationResumePresentation(job('generation_failed')).label).toBe('Recheck retained draft');
    expect(generationResumePresentation({...job('PROVIDER_OUTPUT_TRUNCATED'),progress:{budget:{stop_reason:'GENERATION_LOCAL_STATE_FAILED'}}}).label)
      .toBe('Recheck retained draft · no new model requests');
    const budgetUnknown=generationResumePresentation({...job('GENERATION_LOCAL_STATE_FAILED'),progress:{budget:{stop_reason:'UNRECOGNIZED_STOP'}}});
    expect(budgetUnknown.label).toBe('Recheck retained draft');expect(budgetUnknown.explanation).not.toContain('no new model requests');
  });
  it('uses explicitly cancelled job state when no retained stop or error is present',()=>{
    const job={state:'cancelled',error:null} as NonNullable<ConversationState['generation']>;
    const presentation=generationResumePresentation(job);
    expect(presentation.label).toBe('Continue unfinished work');
    expect(presentation.explanation).toContain('remaining original allowance');
    expect(presentation.explanation).toContain('No automatic restart or budget reset');
  });
  it('does not let cancelled state override a known hard stop, remote uncertainty or unknown saved stop',()=>{
    for(const reason of ['GENERATION_LOCAL_STATE_FAILED','REMOTE_OUTCOME_UNKNOWN','UNRECOGNIZED_STOP']){
      const job={state:'cancelled',error:null,progress:{budget:{stop_reason:reason}}} as NonNullable<ConversationState['generation']>;
      expect(generationResumePresentation(job).label).not.toBe('Continue unfinished work');
    }
    const job={state:'cancelled',error:{code:'REMOTE_OUTCOME_UNKNOWN',message:'Saved uncertainty'}} as NonNullable<ConversationState['generation']>;
    expect(generationResumePresentation(job).label).toBe('Recheck retained draft · no new model requests');
  });
  it.each([
    ['GENERATION_LOCAL_STATE_FAILED','Recheck retained draft · no new model requests'],
    ['REPAIR_STALLED','Recheck retained draft · no new model requests'],
    ['NEEDS_REQUEST_BUDGET','Review resume options'],['GENERATION_CANCELLED','Continue unfinished work'],
  ])('keeps the original explicit generation_retry action while explaining %s',async(reason,label)=>{
    const api=harness();api.conversation.mockResolvedValue({...initial(),budgeted_generation_available:true,
      generation:{operation_id:'retained-operation',state:'failed',summary:'Retained failed generation',can_cancel:false,
        started_at:'now',last_progress_at:'now',error:{code:'generation_failed',message:'Saved failure'},
        progress:{budget:{stop_reason:reason,requests:8,max_requests:24,repairs:3,max_repairs:3}}}});
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    const button=await screen.findByRole('button',{name:label});expect(api.conversationAction).not.toHaveBeenCalled();
    if(reason==='GENERATION_LOCAL_STATE_FAILED'||reason==='REPAIR_STALLED'){
      expect(screen.getByText(/It may end with the same failure/)).toBeTruthy();
      expect(screen.queryByRole('button',{name:'Continue unfinished work'})).toBeNull();
    }
    if(reason==='NEEDS_REQUEST_BUDGET')expect(screen.queryByRole('button',{name:/no new model requests/})).toBeNull();
    fireEvent.click(button);
    await waitFor(()=>expect(api.conversationAction).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({
      action:'generation_retry',operation_id:'retained-operation',request_id:expect.any(String)})));
  });
  it('keeps a polled cancellation retry disabled until the pending Stop submission finishes',async()=>{
    const api=harness();const running={...initial(),budgeted_generation_available:true,
      generation:{operation_id:'cancelled-operation',state:'running',summary:'Generating retained draft',can_cancel:true,
        started_at:'now',last_progress_at:'now',error:null}};
    const cancelled={...running,revision:1,generation:{...running.generation,state:'cancelled',can_cancel:false,summary:'Retained cancelled draft'}};
    let observed=running;let finish:(state:ConversationState)=>void=()=>{};
    api.conversation.mockImplementation(async()=>observed);
    api.conversationAction.mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
    const view=render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    fireEvent.click(await screen.findByRole('button',{name:'Stop response'}));
    expect(api.conversationAction).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({action:'cancel',operation_id:'cancelled-operation'}));
    observed=cancelled;
    const retry=await screen.findByRole('button',{name:'Continue unfinished work'});
    expect(retry).toHaveProperty('disabled',true);
    fireEvent.click(retry);expect(api.conversationAction).toHaveBeenCalledTimes(1);
    await act(async()=>finish(cancelled));
    await waitFor(()=>expect(retry).toHaveProperty('disabled',false));
    fireEvent.click(retry);
    expect(api.conversationAction).toHaveBeenCalledTimes(2);
    expect(api.conversationAction).toHaveBeenLastCalledWith(expect.objectContaining({action:'generation_retry',operation_id:'cancelled-operation'}));
    expect(retry).toHaveProperty('disabled',true);
    await act(async()=>finish(cancelled));view.unmount();
  });
  it('keeps a retained retry disabled while delivery remains unconfirmed',async()=>{
    const api=harness();const cancelled={...initial(),budgeted_generation_available:true,
      generation:{operation_id:'unknown-delivery-operation',state:'cancelled',summary:'Retained cancelled draft',can_cancel:false,
        started_at:'now',last_progress_at:'now',error:null}};
    api.conversation.mockResolvedValue(cancelled);api.conversationAction.mockRejectedValue(new TypeError('Lost fixture response'));
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    const retry=await screen.findByRole('button',{name:'Continue unfinished work'});fireEvent.click(retry);
    await screen.findByRole('button',{name:'Check saved result · no re-execution'});
    expect(retry).toHaveProperty('disabled',true);fireEvent.click(retry);
    expect(api.conversationAction).toHaveBeenCalledTimes(1);
  });
  it('waits for the matching generation to settle and only retries after an explicit later click',async()=>{
    const api=harness();let observed:ConversationState={...initial(),budgeted_generation_available:true,
      generation_settling:{operation_id:'settling-operation',generation_id:'current-generation'},
      generation:{operation_id:'settling-operation',generation_id:'current-generation',state:'cancelled',summary:'Cancelled draft',
        can_cancel:false,started_at:'now',last_progress_at:'now',error:null}};
    api.conversation.mockImplementation(async()=>observed);
    api.conversationAction.mockImplementation(async body=>({...observed,accepted_request_ids:[body.request_id]}));
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    const retry=await screen.findByRole('button',{name:'Continue unfinished work'});
    expect(retry).toHaveProperty('disabled',true);fireEvent.click(retry);
    expect(api.conversationAction).not.toHaveBeenCalled();
    expect(screen.getByRole('region',{name:'Current step'}).textContent).toContain('Cancellation is still settling');
    observed={...observed,generation_settling:null};
    await waitFor(()=>expect(retry).toHaveProperty('disabled',false));
    expect(api.conversationAction).not.toHaveBeenCalled();fireEvent.click(retry);
    await waitFor(()=>expect(api.conversationAction).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({
      action:'generation_retry',operation_id:'settling-operation',request_id:expect.any(String)})));
  });
  it.each([
    {operation_id:'other-operation',generation_id:'current-generation'},
    {operation_id:'current-operation',generation_id:'old-generation'},
  ])('ignores a settling hint not bound to both current job identifiers: %o',async hint=>{
    const api=harness();api.conversation.mockResolvedValue({...initial(),budgeted_generation_available:true,generation_settling:hint,
      generation:{operation_id:'current-operation',generation_id:'current-generation',state:'cancelled',summary:'Current cancelled draft',
        can_cancel:false,started_at:'now',last_progress_at:'now',error:null}});
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    expect(await screen.findByRole('button',{name:'Continue unfinished work'})).toHaveProperty('disabled',false);
    expect(screen.getByRole('region',{name:'Current step'}).textContent).not.toContain('Cancellation is still settling');
    expect(api.conversationAction).not.toHaveBeenCalled();
  });
  it('reports a stale enabled DOM submission guard without queueing or sending a duplicate request',async()=>{
    const api=harness();const cancelled:ConversationState={...initial(),budgeted_generation_available:true,
      generation:{operation_id:'stale-click-operation',state:'cancelled',summary:'Retained draft',can_cancel:false,
        started_at:'now',last_progress_at:'now',error:null}};
    api.conversation.mockResolvedValue(cancelled);let finish:(state:ConversationState)=>void=()=>{};
    const view=render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    const retry=await screen.findByRole('button',{name:'Continue unfinished work'});
    // Exercise the ref guard before the first event's busy state can commit.
    api.conversationAction.mockImplementation(()=>{fireEvent.click(retry);return new Promise(resolve=>{finish=resolve;});});
    fireEvent.click(retry);
    expect(await screen.findByRole('alert')).toHaveProperty('textContent',expect.stringContaining('Previous action is still settling; no new request was sent'));
    expect(api.conversationAction).toHaveBeenCalledTimes(1);
    await act(async()=>finish(cancelled));expect(api.conversationAction).toHaveBeenCalledTimes(1);view.unmount();
  });
  it.each(['cancelled','interrupted'])('describes a retained %s checkpoint instead of returning to a new scene prompt',async state=>{
    const api=harness();api.conversation.mockResolvedValue({...initial(),budgeted_generation_available:true,
      generation:{operation_id:'retained-stop',state,summary:'Retained response',can_cancel:false,started_at:'now',last_progress_at:'now',error:null,
        progress:{inventory_progress:{schema_version:'inventory-work-progress-1.0',observed_instances:4,inventory_count:4,parameterized_count:2,
          pending_count:2,parameter_batch_size:6,inventory_planned:true,parameters_complete:false,checkpoint_saved:true,
          automatic_resume:false,physical_authority:false}}}});
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    const step=await screen.findByRole('region',{name:'Current step'});
    await waitFor(()=>expect(step.textContent).toContain(`Generation ${state} · checkpoint and any last preview retained`));
    expect(step.textContent).toContain(`Select ${state==='cancelled'?'Continue unfinished work':'Recheck retained draft'} when ready`);
    expect(step.textContent).toContain('nothing resumes automatically');
    expect(step.textContent).not.toContain('Describe a space');expect(api.conversationAction).not.toHaveBeenCalled();
  });
  it('routes a CAD attachment to Library import while preserving the unsent scene text and photo on cancel',async()=>{
    const api={...harness(),modelLibrary:vi.fn(async()=>({models:[]})),libraryWorkspace:vi.fn(async()=>({schema_version:'library-workspace-1.0',project_id:'chat-test',current_scene_revision:null,assets:[],jobs:[],extensions:[]} as LibraryWorkspaceState)),libraryWorkspaceAction:vi.fn()};
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    await waitFor(()=>expect(api.conversation).toHaveBeenCalled());
    const message=screen.getByRole('textbox',{name:'Message TwinPulse'});fireEvent.change(message,{target:{value:'Keep this room description'}});
    const input=document.querySelector('input[type=file]')!;
    fireEvent.change(input,{target:{files:[new File(['photo'],'room.jpg',{type:'image/jpeg'})]}});
    fireEvent.change(input,{target:{files:[new File(['CAD'],'machine.step',{type:'application/step'})]}});
    expect(await screen.findByRole('dialog',{name:'Model library'})).toBeTruthy();
    expect(await screen.findByText(/machine.step · Library asset source · selected locally/)).toBeTruthy();
    expect(api.libraryWorkspaceAction).not.toHaveBeenCalled();expect(api.conversationAction).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button',{name:'Close library'}));
    expect(message).toHaveProperty('value','Keep this room description');expect(screen.getByText(/room.jpg · environment reference photo/)).toBeTruthy();
    expect(screen.getByText(/machine.step · Library asset source · scene draft kept/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'Send'}));expect(await screen.findByRole('dialog',{name:'Model library'})).toBeTruthy();
    expect(api.conversationAction).not.toHaveBeenCalled();
  });
  it('marks an image as an asset reference and opens creation without sending it as a scene photo',async()=>{
    const api={...harness(),modelLibrary:vi.fn(async()=>({models:[]})),libraryWorkspace:vi.fn(async()=>({schema_version:'library-workspace-1.0',project_id:'chat-test',current_scene_revision:null,assets:[],jobs:[],extensions:[]} as LibraryWorkspaceState)),libraryWorkspaceAction:vi.fn()};
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);await waitFor(()=>expect(api.conversation).toHaveBeenCalled());
    fireEvent.change(screen.getByRole('textbox',{name:'Message TwinPulse'}),{target:{value:'Create this chair'}});
    fireEvent.change(document.querySelector('input[type=file]')!,{target:{files:[new File(['chair'],'chair.jpg',{type:'image/jpeg'})]}});
    fireEvent.change(screen.getByRole('combobox',{name:'Attached image role'}),{target:{value:'asset_reference'}});
    expect(await screen.findByRole('textbox',{name:'Describe Library asset'})).toHaveProperty('value','Create this chair');
    expect(screen.getByText('chair.jpg · asset_reference')).toBeTruthy();expect(api.libraryWorkspaceAction).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button',{name:'Close library'}));fireEvent.click(screen.getByRole('button',{name:'Send'}));
    expect(await screen.findByRole('textbox',{name:'Describe Library asset'})).toBeTruthy();expect(api.conversationAction).not.toHaveBeenCalled();
  });
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
    expect(screen.getByRole('button',{name:'Recheck retained draft'}).closest('.chat-turn')?.getAttribute('data-turn-id')).toBe('generate-origin');
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
  it.each([830,999,1000])('restores the narrow composer only after successful New chat at %spx',async width=>{
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
    if(width<1000)fireEvent.click(screen.getByRole('button',{name:'Show Twin'}));
    const toggle=screen.getByRole('button',{name:'Toggle conversations and projects'});
    if(width<1000)fireEvent.click(toggle);
    for(const action of ['project','new-chat']){
      if(toggle.getAttribute('aria-expanded')==='false')fireEvent.click(toggle);
      const actionButton=await screen.findByRole('button',{name:action==='project'?'Open next':'＋ New chat'});
      await waitFor(()=>expect(actionButton).toHaveProperty('disabled',false));fireEvent.click(actionButton);
      await waitFor(()=>expect(switchProject).toHaveBeenCalledTimes(action==='project'?1:2));
      // Keep the overlay and existing switch locks until the acknowledgement.
      expect(toggle.getAttribute('aria-expanded')).toBe('true');
      expect(screen.getByRole('button',{name:'Hide Twin'}).getAttribute('aria-expanded')).toBe('true');
      expect(screen.getByRole('button',{name:'＋ New chat'})).toHaveProperty('disabled',true);
      expect(screen.getByRole('button',{name:'Open chat-test'})).toHaveProperty('disabled',true);
      const switchingComposer=screen.getByRole('textbox',{name:'Message TwinPulse',hidden:true});
      expect(switchingComposer).toHaveProperty('disabled',true);
      fireEvent.change(switchingComposer,{target:{value:'Do not send to the previous project'}});
      fireEvent.keyDown(switchingComposer,{key:'Enter',code:'Enter'});
      expect(api.conversationAction).not.toHaveBeenCalled();
      const target=switchProject.mock.calls.at(-1)![0];
      await act(async()=>finish({status:'switched',project_id:target,context_id:`ctx-${target}`,new_session_required:false}));
      await screen.findByText(`${target} · Choose a mode`);
      expect(toggle.getAttribute('aria-expanded')).toBe(width<1000?'false':'true');
      expect(screen.getByRole('button',{name:width<1000&&action==='new-chat'?'Show Twin':'Hide Twin'}).getAttribute('aria-expanded'))
        .toBe(width<1000&&action==='new-chat'?'false':'true');
      expect(screen.getByRole('button',{name:'Attach image'})).toBeTruthy();
    }
    expect(extended.createProject).toHaveBeenCalledOnce();expect(api.conversationAction).not.toHaveBeenCalled();
  });
  it.each(['create','switch'])('preserves the current narrow Twin and composer draft after New chat %s failure',async failure=>{
    vi.stubGlobal('innerWidth',830);
    const api=harness();api.runtimeState.mockResolvedValue({status:'ready'} as never);
    const catalog={projects:[{project_id:'chat-test',active:true,status:'empty'}]};
    const rejected=new ApiError('project_busy','New chat rejected');
    const extended={...api,projects:vi.fn(async()=>catalog),
      createProject:failure==='create'?vi.fn().mockRejectedValue(rejected):vi.fn(async()=>({catalog})),
      switchProject:vi.fn().mockRejectedValue(rejected)};
    render(<ChatWorkspace api={extended as unknown as TwinPulseApi} advanced={()=>{}}/>);
    await screen.findByText('chat-test · Choose a mode');
    fireEvent.change(screen.getByRole('textbox',{name:'Message TwinPulse'}),{target:{value:'Keep this unsent draft'}});
    fireEvent.click(screen.getByRole('button',{name:'Show Twin'}));
    fireEvent.click(screen.getByRole('button',{name:'Toggle conversations and projects'}));
    fireEvent.click(await screen.findByRole('button',{name:'＋ New chat'}));
    await waitFor(()=>expect(screen.getByRole('alert').textContent).toContain('New chat rejected'));
    expect(screen.getByRole('button',{name:'Hide Twin'}).getAttribute('aria-expanded')).toBe('true');
    expect(screen.getByRole('textbox',{name:'Message TwinPulse'})).toHaveProperty('value','Keep this unsent draft');
    expect(sessionStorage.getItem('twinpulse.chat.draft.chat-test')).toBe('Keep this unsent draft');
    expect(extended.createProject).toHaveBeenCalledOnce();
    expect(extended.switchProject).toHaveBeenCalledTimes(failure==='create'?0:1);
    expect(api.conversationAction).not.toHaveBeenCalled();
  });
  it.each(['project','new-chat'])('suspends actual child polling before %s POST and restores the same draft after rejection',async action=>{
    const base=harness();base.runtimeState.mockResolvedValue({status:'ready'} as never);
    let rejectImage!:(error:Error)=>void,rejectSwitch!:(error:Error)=>void;
    const frame={state:'live',fps:6,age_ms:0,detail:'Current Isaac frame',physical_authority:false,camera_pending:false,camera_result:null,
      frame:{frame_id:1,captured_at_ms:Date.now(),applied_revision:'scene',engine_session_id:'engine',stage_epoch:'stage',camera_sequence:0,width:960,height:640,sha256:'a'.repeat(64),url:'unused'}};
    const catalog={projects:[{project_id:'chat-test',active:true,status:'empty'},{project_id:'next',active:false,status:'empty'}]};
    const paused=()=>expect(screen.queryByRole('complementary',{name:'Digital Twin'})).toBeNull();
    const api={...base,projects:vi.fn(async()=>catalog),
      createProject:vi.fn(async()=>{paused();return {catalog};}),
      switchProject:vi.fn(()=>{paused();return new Promise((_resolve,reject)=>{rejectSwitch=reject;});}),
      viewportState:vi.fn(async()=>frame),viewportImage:vi.fn(()=>new Promise<Blob>((_resolve,reject)=>{rejectImage=reject;})),
      viewportObservation:vi.fn()};
    const view=render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    await waitFor(()=>expect(api.viewportImage).toHaveBeenCalled());
    const composer=screen.getByRole('textbox',{name:'Message TwinPulse'});
    fireEvent.change(composer,{target:{value:'Keep old owner draft'}});
    fireEvent.change(document.querySelector('input[type=file]')!,{target:{files:[new File(['photo'],'old.jpg',{type:'image/jpeg'})]}});
    const photo=await screen.findByAltText('Attached image preview');
    fireEvent.click(await screen.findByRole('button',{name:action==='project'?'Open next':'＋ New chat'}));
    await waitFor(()=>expect(api.switchProject).toHaveBeenCalledOnce());
    const reads={chat:api.conversation.mock.calls.length,viewport:api.viewportState.mock.calls.length,workflow:api.workflow.mock.calls.length};
    await act(async()=>{rejectImage(new Error('Old frame failed during transition'));await new Promise(resolve=>setTimeout(resolve,850));});
    expect(api.conversation).toHaveBeenCalledTimes(reads.chat);expect(api.workflow).toHaveBeenCalledTimes(reads.workflow);
    expect(api.viewportState).toHaveBeenCalledTimes(reads.viewport);expect(api.viewportObservation).not.toHaveBeenCalled();
    await act(async()=>{rejectSwitch(new ApiError('project_busy','Switch rejected'));});
    expect(screen.getByRole('textbox',{name:'Message TwinPulse'})).toBe(composer);expect(composer).toHaveProperty('value','Keep old owner draft');
    expect(screen.getByAltText('Attached image preview')).toBe(photo);expect(screen.getByText('chat-test · Choose a mode')).toBeTruthy();
    await waitFor(()=>expect(api.conversation.mock.calls.length).toBeGreaterThan(reads.chat));
    await waitFor(()=>expect(api.viewportState.mock.calls.length).toBeGreaterThan(reads.viewport));
    expect(api.bootstrap).toHaveBeenCalledOnce();expect(api.conversationAction).not.toHaveBeenCalled();view.unmount();
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
  it.each([false,true])('distinguishes environment-only SIM from an explicit robot alternative still waiting=%s',async waiting=>{
    const api=harness();api.conversation.mockResolvedValue({...initial(),mode:'SIM',robot_id:null,
      cards:waiting?[{id:'robot-choice',message_id:'robot-message',kind:'robot_selection',question:'Choose a supported alternative',
        state:'waiting',selected_choice_id:null,operation_id:null,expected_session_revision:0,
        choices:[{id:'turtlebot3_burger',label:'Use TurtleBot3 Burger instead',enabled:true,disabled_reason:null}]}]:[]});
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    expect(await screen.findByText(waiting?'Simulation asset selection pending':'Environment only · no robot selected')).toBeTruthy();
    expect(api.conversationAction).not.toHaveBeenCalled();
    expect(screen.queryByRole('button',{name:'Run simulation'})).toBeNull();
  });
  it.each([false,true])('exposes a reopened edited Twin above long history with bounded generation origin=%s',async bounded=>{
    // Sanitized projection of final20b-sim-display-inspect's actual saved state:
    // the generation preview is old, an edit is durable but has no current frame,
    // and the current draft has neither a SIM review nor a currently applied scene.
    const api=harness();const messages=Array.from({length:32},(_,index)=>({message_id:`history-${index}`,
      role:(index%2?'assistant':'user') as 'assistant'|'user',content:`Saved history ${index}`,status:'completed',
      attachments:[],created_at:`2026-10-16T10:${String(index).padStart(2,'0')}:00Z`,operation_id:null}));
    const revision='edited-current-revision';
    api.conversation.mockResolvedValue({...initial(),mode:'SIM',restored_session:true,messages,
      simulation_review:null,scene_edit_transaction:{operation_id:'saved-edit',state:'COMMITTED',
        engine_acknowledged:true,durable_committed:true,current_frame:false,result_revision:revision} as never,
      generation:{operation_id:'original-generation',origin_message_id:bounded?'outside-history':'history-0',
        state:'completed',summary:'Historical generation',can_cancel:false,started_at:'2026-10-16T10:00:00Z',
        last_progress_at:'2026-10-16T10:01:00Z',error:null,
        progress:{generation_preview:{state:'ready',scene_revision:'original-generation-revision',
          rendered_count:3,pending_count:0,inventory_count:3,preview_only:true,physical_authority:false}}} as never});
    api.workflow.mockResolvedValue({phase:'draft_ready',provider:{configured:true,label:'Saved provider'},
      site_draft:{revision,artifact_id:'edited-artifact'}} as never);
    api.productState.mockResolvedValue({project_id:'chat-test',engine_connected:true,engine_session_id:'engine',stage_epoch:'epoch',lease_owned:false,control_lease_id:null,operations:[],build_view:null,
      engine_readiness:{site_scene_build_v2:{feature:'site_scene_build_v2',ready:false,code:'runtime_command_unavailable'}},
      snapshot:{project_id:'chat-test',engine_session_id:'engine',stage_epoch:'epoch',applied_revision:null,runtime_state:'idle',safety_state:null,
        permitted_commands:['get_state','focus_scene'],capabilities:['site_scene_build_v2','site_simulation_v1']}} as never);
    const extended={...api,acquireLease:vi.fn(),acknowledge:vi.fn(),command:vi.fn(),simulationPlan:vi.fn(),simulationRun:vi.fn()};
    render(<ChatWorkspace api={extended as unknown as TwinPulseApi} advanced={()=>{}}/>);
    fireEvent.click(await screen.findByRole('button',{name:/Open saved chat/}));
    const panel=await screen.findByRole('region',{name:'Current Twin and SIM preparation'});
    const route=screen.getByRole('region',{name:'Simulation route'});
    expect(panel.contains(route)).toBe(true);expect(panel.closest('.chat-turn')).toBeNull();
    const firstTurn=document.querySelector('.chat-turn')!;
    expect(panel.compareDocumentPosition(firstTurn)&Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getAllByRole('region',{name:'Simulation route'})).toHaveLength(1);
    expect(screen.getByRole('button',{name:'View current Twin'})).toHaveProperty('disabled',false);
    expect(screen.getByRole('button',{name:'Preview SIM route'})).toHaveProperty('disabled',false);
    expect(screen.getByRole('button',{name:'Run simulation'})).toHaveProperty('disabled',true);
    expect(screen.getByText(/Transaction 3D frame: not currently confirmed/)).toBeTruthy();
    const scroll=vi.fn();panel.scrollIntoView=scroll;
    fireEvent.click(screen.getByRole('button',{name:'Current Twin and SIM controls'}));
    expect(scroll).toHaveBeenCalledWith({block:'start'});expect(document.activeElement).toBe(panel);
    for(const call of [extended.acquireLease,extended.acknowledge,extended.command,extended.simulationPlan,extended.simulationRun,api.conversationAction])
      expect(call).not.toHaveBeenCalled();
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
  it.each([
    ['progress',{validation:'passed',same_plan:true,same_witness:true},'recheck passed; pending retained'],
    ['diagnostics',{validation:'failed',same_plan:false,same_witness:true},'not saved: plan changed.'],
    ['diagnostics',{validation:'failed',same_plan:true,same_witness:false},'not saved: pending evidence changed.'],
    ['diagnostics',{validation:'passed',same_plan:true},'recheck unconfirmed'],
    ['absent',null,null],
  ])('shows bounded %s partial-retention evidence in the left generation card',async(source,payload,expected)=>{
    const api=harness();const value={gate:'exact_plan_and_support_witness',physical_authority:false,...payload as object};
    const generation={operation_id:'retention-stop',state:'failed',summary:'Bounded generation stopped',can_cancel:false,
      started_at:'now',last_progress_at:'now',error:{code:'TIME_BUDGET_EXHAUSTED',message:'Time limit reached',
        ...(source==='diagnostics'?{diagnostics:{retention_revalidation:value}}:{})},
      ...(source==='progress'?{progress:{retention_revalidation:value}}:{})};
    api.conversation.mockResolvedValue({...initial(),generation:generation as never});
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    await screen.findByText('Bounded generation stopped');
    const card=Array.from(document.querySelectorAll('.chat-tool-progress')).find(node=>node.textContent?.includes('Scene generation · failed'))!;
    const label=card.querySelector('[aria-label="Partial scene retention recheck"]');
    if(expected){expect(label?.textContent).toContain(expected);expect(label?.textContent).toContain('Photo quality and SIM remain unverified.');}
    else expect(label).toBeNull();
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
    api.runtimeState.mockResolvedValue({status:'ready',message:'Engine ready'} as never);
    const snapshot={project_id:'chat-test',engine_session_id:'engine',stage_epoch:'epoch',applied_revision:'scene',runtime_state:'built',run_id:null,safety_state:null,
      permitted_commands:['build_site_scene'],capabilities:['site_scene_build_v2','site_simulation_v1','site_simulation_preview_v1']};
    const operations=[{command_id:'build',command_type:'build_site_scene',status:'succeeded',receipt:null}];
    api.productState.mockResolvedValue({project_id:'chat-test',engine_connected:true,engine_session_id:'engine',stage_epoch:'epoch',lease_owned:true,control_lease_id:'lease',snapshot,operations,
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
  it('does not unmount the viewer or reload its source photo after one failed conversation observation',async()=>{
    vi.stubGlobal('innerWidth',1920);
    const api={...harness(),viewportState:vi.fn().mockResolvedValue({state:'waiting',frame:null})};
    const state={...initial(),messages:[{message_id:'source',role:'user' as const,content:'Photo',status:'completed',
      attachments:[{name:'room.jpg',media_type:'image/jpeg',preview_url:'/source'}],created_at:'now',operation_id:null}]};
    api.conversation.mockResolvedValue(state);
    const component=render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    const photo=await screen.findByRole('img',{name:'Source photo: room.jpg'});
    const canvas=component.container.querySelector('canvas');
    const photoLoads=api.conversationImage.mock.calls.length;
    api.conversation.mockRejectedValue(new Error('Temporary conversation observation failure'));
    await waitFor(()=>expect(screen.getByRole('status',{name:'App connection observation'}).textContent)
      .toContain('Temporary conversation observation failure'),{timeout:2500});
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.getByRole('img',{name:'Source photo: room.jpg'})).toBe(photo);
    expect(component.container.querySelector('canvas')).toBe(canvas);
    expect(api.conversationImage).toHaveBeenCalledTimes(photoLoads);
    api.conversation.mockResolvedValue(state);
    await waitFor(()=>expect(screen.getByRole('status',{name:'App connection observation'}).textContent)
      .toBe('App connection available'),{timeout:2500});
    expect(screen.getByRole('img',{name:'Source photo: room.jpg'})).toBe(photo);
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
  it.each(['new text','rewritten same text','new attachment'])('preserves %s written before a late composer ACK',async change=>{
    const api=harness();let finish!:(state:ConversationState)=>void;
    api.conversationAction.mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    const box=screen.getByRole('textbox',{name:'Message TwinPulse'});
    fireEvent.change(box,{target:{value:'Alpha stop'}});
    if(change==='new attachment'){
      const original=new File(['original'],'original.png',{type:'image/png'});
      Object.defineProperty(original,'arrayBuffer',{value:async()=>new Uint8Array([1]).buffer});
      fireEvent.drop(box.closest('form')!,{dataTransfer:{files:[original]}});
    }
    await waitFor(()=>expect(screen.getByRole('button',{name:'Send'})).toHaveProperty('disabled',false));
    fireEvent.click(screen.getByRole('button',{name:'Send'}));await waitFor(()=>expect(finish).toBeTypeOf('function'));
    if(change==='new attachment'){
      fireEvent.click(screen.getByRole('button',{name:'Remove image'}));
      fireEvent.drop(box.closest('form')!,{dataTransfer:{files:[new File(['next'],'next.png',{type:'image/png'})]}});
    }else{
      fireEvent.change(box,{target:{value:change==='new text'?'Alpha forward 10 cm':''}});
      if(change==='rewritten same text')fireEvent.change(box,{target:{value:'Alpha stop'}});
    }
    const sent=api.conversationAction.mock.calls[0][0];
    await act(async()=>finish({...initial(),revision:1,accepted_request_ids:[sent.request_id]}));
    if(change==='new attachment')expect(screen.getByText(/next.png · environment reference photo/)).toBeTruthy();
    else expect(box).toHaveProperty('value',change==='new text'?'Alpha forward 10 cm':'Alpha stop');
    expect(api.conversationAction).toHaveBeenCalledTimes(1);
  });
  it.each(['unchanged','text only','reselected file','image role'])('clears only sent composer components after ACK with %s edits',async change=>{
    const api=Object.assign(harness(),{modelLibrary:vi.fn(async()=>({models:[]}))});let finish!:(state:ConversationState)=>void;
    api.conversationAction.mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    const box=screen.getByRole('textbox',{name:'Message TwinPulse'}),original=new File(['original'],'original.png',{type:'image/png'});
    Object.defineProperty(original,'arrayBuffer',{value:async()=>new Uint8Array([1]).buffer});
    fireEvent.change(box,{target:{value:'Original description'}});fireEvent.drop(box.closest('form')!,{dataTransfer:{files:[original]}});
    await waitFor(()=>expect(screen.getByRole('button',{name:'Send'})).toHaveProperty('disabled',false));
    fireEvent.click(screen.getByRole('button',{name:'Send'}));await waitFor(()=>expect(finish).toBeTypeOf('function'));
    if(change==='text only')fireEvent.change(box,{target:{value:'Next description'}});
    if(change==='reselected file'){
      fireEvent.click(screen.getByRole('button',{name:'Remove image'}));fireEvent.drop(box.closest('form')!,{dataTransfer:{files:[original]}});
    }
    const role=screen.getByLabelText('Attached image role');
    if(change==='image role')fireEvent.change(role,{target:{value:'asset_reference'}});
    await act(async()=>finish({...initial(),revision:1}));
    expect(box).toHaveProperty('value',change==='text only'?'Next description':'');
    if(['reselected file','image role'].includes(change)){
      expect(within(box.closest('form')!).getByText(/original.png · /)).toBeTruthy();
      expect(role).toHaveProperty('value',change==='image role'?'asset_reference':'environment_reference');
    }else expect(screen.queryByAltText('Attached image preview')).toBeNull();
  });
  it('preserves a newer draft when an unknown delivery is acknowledged by Check saved result',async()=>{
    const api=harness();api.conversationAction.mockRejectedValue(new TypeError('Response lost'));
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    const box=screen.getByRole('textbox',{name:'Message TwinPulse'});fireEvent.change(box,{target:{value:'Alpha stop'}});
    await waitFor(()=>expect(screen.getByRole('button',{name:'Send'})).toHaveProperty('disabled',false));fireEvent.click(screen.getByRole('button',{name:'Send'}));
    const check=await screen.findByRole('button',{name:'Check saved result · no re-execution'});
    fireEvent.change(box,{target:{value:'Alpha forward 10 cm'}});
    const sent=api.conversationAction.mock.calls[0][0];api.conversation.mockResolvedValue({...initial(),revision:1,accepted_request_ids:[sent.request_id]});
    fireEvent.click(check);await waitFor(()=>expect(screen.queryByRole('button',{name:'Check saved result · no re-execution'})).toBeNull());
    expect(box).toHaveProperty('value','Alpha forward 10 cm');expect(api.conversationAction).toHaveBeenCalledTimes(1);
  });
  it('ignores a late composer ACK after the authenticated context changes',async()=>{
    const api=Object.assign(harness(),{context:'old-context'});let finish!:(state:ConversationState)=>void;
    api.conversationAction.mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
    const view=render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    const box=screen.getByRole('textbox',{name:'Message TwinPulse'});fireEvent.change(box,{target:{value:'Alpha stop'}});
    await waitFor(()=>expect(screen.getByRole('button',{name:'Send'})).toHaveProperty('disabled',false));fireEvent.click(screen.getByRole('button',{name:'Send'}));
    await waitFor(()=>expect(finish).toBeTypeOf('function'));
    api.context='next-context';view.rerender(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    fireEvent.change(box,{target:{value:'New context draft'}});
    await act(async()=>finish({...initial(),context_id:'old-context',revision:1}));
    expect(box).toHaveProperty('value','New context draft');expect(api.conversationAction).toHaveBeenCalledTimes(1);
  });
  it.each(['accepted','unaccepted','error'])('keeps UNKNOWN B owned after duplicate saved-result checks for A settle late with %s',async outcome=>{
    const api=harness();api.conversationAction.mockRejectedValue(new TypeError('Response lost'));
    let checkA=false,observed=initial();const checks:{resolve:(state:ConversationState)=>void;reject:(error:Error)=>void}[]=[];
    api.conversation.mockImplementation(()=>checkA?new Promise((resolve,reject)=>checks.push({resolve,reject})):Promise.resolve(observed));
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    const box=screen.getByRole('textbox',{name:'Message TwinPulse'});fireEvent.change(box,{target:{value:'Alpha stop'}});
    await waitFor(()=>expect(screen.getByRole('button',{name:'Send'})).toHaveProperty('disabled',false));fireEvent.click(screen.getByRole('button',{name:'Send'}));
    const check=await screen.findByRole('button',{name:'Check saved result · no re-execution'}),a=api.conversationAction.mock.calls[0][0];
    checkA=true;fireEvent.click(check);fireEvent.click(check);checkA=false;
    observed={...initial(),revision:1,accepted_request_ids:[a.request_id]};
    await act(async()=>checks.at(-1)!.resolve(observed));
    await waitFor(()=>expect(screen.queryByRole('button',{name:'Check saved result · no re-execution'})).toBeNull());
    fireEvent.change(box,{target:{value:'Beta stop'}});fireEvent.click(screen.getByRole('button',{name:'Send'}));
    await screen.findByRole('button',{name:'Check saved result · no re-execution'});
    fireEvent.change(box,{target:{value:'Keep the next draft'}});const unknown=screen.getByRole('alert').textContent;
    // A guarded UI has only one check. An unguarded UI still has the older A
    // read: settle it after B becomes UNKNOWN to reproduce the original race.
    if(checks.length>1)await act(async()=>{
      if(outcome==='error')checks[0].reject(new Error('Retired A read failed'));
      else checks[0].resolve(outcome==='accepted'?observed:{...initial(),revision:2});
    });
    expect(screen.getByRole('button',{name:'Check saved result · no re-execution'})).toBeTruthy();
    expect(screen.getByRole('alert').textContent).toBe(unknown);expect(box).toHaveProperty('value','Keep the next draft');
    expect(screen.getByRole('button',{name:'Send'})).toHaveProperty('disabled',true);
    expect(checks).toHaveLength(1);expect(api.conversationAction).toHaveBeenCalledTimes(2);
  });
  it('releases its attachment-conversion spinner when workflow freshness expires before admission',async()=>{
    const api=harness();let finish!:(bytes:ArrayBuffer)=>void;
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    const box=screen.getByRole('textbox',{name:'Message TwinPulse'}),image=new File(['original'],'pending.png',{type:'image/png'});
    Object.defineProperty(image,'arrayBuffer',{value:()=>new Promise<ArrayBuffer>(resolve=>{finish=resolve;})});
    fireEvent.change(box,{target:{value:'Keep attachment draft'}});fireEvent.drop(box.closest('form')!,{dataTransfer:{files:[image]}});
    await waitFor(()=>expect(screen.getByRole('button',{name:'Send'})).toHaveProperty('disabled',false));fireEvent.click(screen.getByRole('button',{name:'Send'}));
    await waitFor(()=>expect(finish).toBeTypeOf('function'));
    api.workflow.mockRejectedValue(new ApiError('state_read_timeout','Workflow observation expired'));
    await screen.findByRole('status',{name:'Workflow observation'});
    await act(async()=>finish(new Uint8Array([1]).buffer));
    expect(screen.queryByText('Sending…')).toBeNull();expect(box).toHaveProperty('value','Keep attachment draft');
    expect(screen.getByText(/pending.png · environment reference photo/)).toBeTruthy();expect(api.conversationAction).not.toHaveBeenCalled();
  });
  it('releases only its attachment spinner when a project switch starts before attachment admission',async()=>{
    const api=Object.assign(harness(),{context:'same-context',projects:vi.fn(async()=>({projects:[{project_id:'chat-test',active:true,status:'empty'},{project_id:'next',active:false,status:'empty'}]})),
      switchProject:vi.fn(()=>new Promise(()=>{}))});api.runtimeState.mockResolvedValue({status:'ready'} as never);
    let finish!:(bytes:ArrayBuffer)=>void;
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    const open=await screen.findByRole('button',{name:'Open next'});await waitFor(()=>expect(open).toHaveProperty('disabled',false));
    const box=screen.getByRole('textbox',{name:'Message TwinPulse'}),image=new File(['original'],'pending.png',{type:'image/png'});
    Object.defineProperty(image,'arrayBuffer',{value:()=>{fireEvent.click(open);return new Promise<ArrayBuffer>(resolve=>{finish=resolve;});}});
    fireEvent.change(box,{target:{value:'Keep project draft'}});fireEvent.drop(box.closest('form')!,{dataTransfer:{files:[image]}});
    fireEvent.click(screen.getByRole('button',{name:'Send'}));await waitFor(()=>expect(api.switchProject).toHaveBeenCalledTimes(1));
    await act(async()=>finish(new Uint8Array([1]).buffer));
    expect(screen.queryByText('Sending…')).toBeNull();expect(box).toHaveProperty('value','Keep project draft');
    expect(box).toHaveProperty('disabled',true);expect(open).toHaveProperty('disabled',true);
    expect(screen.getByText(/pending.png · environment reference photo/)).toBeTruthy();expect(api.conversationAction).not.toHaveBeenCalled();
  });
  it('does not release the next context request busy owner when an old attachment conversion settles',async()=>{
    let selected=initial(),finishSwitch!:()=>void,finishOld!:(bytes:ArrayBuffer)=>void,finishNew!:(state:ConversationState)=>void;
    const api=Object.assign(harness(),{context:'old-context',projects:vi.fn(async()=>({projects:[{project_id:'chat-test',active:true,status:'empty'},{project_id:'next',active:false,status:'empty'}]})),
      switchProject:vi.fn(()=>new Promise(resolve=>{finishSwitch=()=>{
        api.context='next-context';selected={...initial(),project_id:'next',context_id:'next-context'};
        resolve({status:'switched',project_id:'next',context_id:'next-context',new_session_required:false});
      };}))});
    api.runtimeState.mockResolvedValue({status:'ready'} as never);api.conversation.mockImplementation(async()=>selected);
    api.conversationAction.mockImplementation(()=>new Promise(resolve=>{finishNew=resolve;}));
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    const open=await screen.findByRole('button',{name:'Open next'});await waitFor(()=>expect(open).toHaveProperty('disabled',false));
    const box=screen.getByRole('textbox',{name:'Message TwinPulse'}),image=new File(['old'],'old.png',{type:'image/png'});
    Object.defineProperty(image,'arrayBuffer',{value:()=>{fireEvent.click(open);return new Promise<ArrayBuffer>(resolve=>{finishOld=resolve;});}});
    fireEvent.change(box,{target:{value:'Old context image'}});fireEvent.drop(box.closest('form')!,{dataTransfer:{files:[image]}});
    fireEvent.click(screen.getByRole('button',{name:'Send'}));await waitFor(()=>expect(finishSwitch).toBeTypeOf('function'));
    await act(async()=>finishSwitch());await screen.findByText('next · Choose a mode');
    fireEvent.change(box,{target:{value:'Next context action'}});
    await waitFor(()=>expect(screen.getByRole('button',{name:'Send'})).toHaveProperty('disabled',false));fireEvent.click(screen.getByRole('button',{name:'Send'}));
    await waitFor(()=>expect(finishNew).toBeTypeOf('function'));
    await act(async()=>finishOld(new Uint8Array([1]).buffer));
    expect(screen.getByText('Sending…')).toBeTruthy();expect(api.conversationAction).toHaveBeenCalledTimes(1);
    expect(api.conversationAction.mock.calls[0][0]).toMatchObject({text:'Next context action',attachment:null});
    await act(async()=>finishNew({...selected,revision:1}));expect(screen.queryByText('Sending…')).toBeNull();
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
