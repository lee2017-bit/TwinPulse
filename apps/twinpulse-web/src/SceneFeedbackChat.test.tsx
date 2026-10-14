// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {ChatWorkspace} from './ChatWorkspace';
import type {TwinPulseApi} from './api';
import type {ConversationState,QuestionCard} from './conversation-types';

const initial=():ConversationState=>({schema_version:'conversation-1.0',session_id:'feedback-chat',project_id:'feedback-ui',
  revision:1,cursor:1,mode:'SIM',robot_id:null,physical_authority:false,restore_error:null,
  messages:[],cards:[],events:[],generation:null,accepted_request_ids:[]});
function harness(state=initial()){
  return {bootstrap:vi.fn().mockResolvedValue(undefined),conversation:vi.fn().mockResolvedValue(state),
    conversationAction:vi.fn().mockResolvedValue(state),runtimeState:vi.fn().mockResolvedValue({status:'ready'}),
    productState:vi.fn().mockResolvedValue({engine_connected:true}),
    workflow:vi.fn().mockResolvedValue({phase:'draft_ready',mode:'explicit_fixture',provider:{configured:true,label:'scripted'},site_draft:{revision:'current',artifact_id:null}}),
    recoverSceneEdit:vi.fn().mockResolvedValue({state:'COMPENSATING'})};
}
function question(kind:string,choices:QuestionCard['choices']):QuestionCard{
  return {id:'q',message_id:'m',kind,question:kind==='scene_edit_clarify'?'Which retained item should be restored?':'Update the checked Twin?',
    state:'waiting',selected_choice_id:null,expected_session_revision:1,operation_id:'edit',choices};
}
const choice=(id:string,label:string)=>({id,label,enabled:true,disabled_reason:null});

describe('Ordinary feedback chat UI',()=>{
  afterEach(()=>vi.unstubAllGlobals());
  it('allows a natural-language answer to the one clarification card',async()=>{
    const card=question('scene_edit_clarify',[choice('cancel','Cancel feedback')]);
    const state={...initial(),cards:[card],messages:[{message_id:'m',role:'assistant' as const,content:card.question,status:'completed',attachments:[],created_at:'now',operation_id:'feedback'}],
      scene_feedback:{operation_id:'feedback',state:'clarify',error:null,clarification_count:0}};
    const api=harness(state);render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    expect(await screen.findByText(/Reply to this one question in chat/)).toBeTruthy();
    fireEvent.change(screen.getByRole('textbox',{name:'Message TwinPulse'}),{target:{value:'The retained item on the table.'}});
    expect(screen.getByRole('button',{name:'Send'})).toHaveProperty('disabled',false);
    fireEvent.click(screen.getByRole('button',{name:'Send'}));
    await waitFor(()=>expect(api.conversationAction).toHaveBeenCalledWith(expect.objectContaining({action:'message',text:'The retained item on the table.',mode:'new'})));
  });
  it('shows before/after and needs the explicit apply choice',async()=>{
    const card=question('scene_edit',[choice('apply','Apply and update Twin'),choice('cancel','Cancel')]);
    const state={...initial(),cards:[card],messages:[{message_id:'m',role:'assistant' as const,content:card.question,status:'completed',attachments:[],created_at:'now',operation_id:'edit'}],
      scene_edit_preview:{operation:{operation_id:'edit'},preview_digest:'digest',source_revision:'source',parent_revision:'current',result_revision:'after',
        affected_before:{support:{position_m:[0,0,.45],dimensions_m:[.8,.4,.9],kind:'table'}},
        affected_after:{support:{position_m:[.2,0,.45],dimensions_m:[1.4,.8,.9],kind:'table'}},preserved_object_count:3,review_required:true as const,physical_validation:'NOT_RUN' as const}};
    const api=harness(state);render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    expect(await screen.findByRole('region',{name:'Scene edit before and after'})).toHaveProperty('textContent',expect.stringContaining('support'));
    expect(api.conversationAction).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('radio',{name:'Apply and update Twin'}));
    expect(api.conversationAction).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button',{name:'Continue'}));
    await waitFor(()=>expect(api.conversationAction).toHaveBeenCalledWith(expect.objectContaining({action:'answer',choice_id:'apply',card_id:'q'})));
  });
  it('retains UNKNOWN and sends one recovery only after the explicit CTA',async()=>{
    const state={...initial(),scene_edit_transaction:{operation_id:'edit',state:'ENGINE_STATE_UNKNOWN',current_frame:false,
      durable_committed:false,engine_acknowledged:false,error:'ACK timeout',command_id:'command'}};
    const api=harness(state);render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    const button=await screen.findByRole('button',{name:'Recover saved Twin in Isaac'});
    expect(api.recoverSceneEdit).not.toHaveBeenCalled();expect(api.conversationAction).not.toHaveBeenCalled();
    expect(screen.getByRole('region',{name:'Current step'}).textContent).toContain('Run locked');
    fireEvent.click(button);await waitFor(()=>expect(api.recoverSceneEdit).toHaveBeenCalledTimes(1));
    expect(api.conversationAction).not.toHaveBeenCalled();
  });
  it('sends an attached image with genuinely empty textarea text',async()=>{
    vi.stubGlobal('URL',{createObjectURL:vi.fn(()=> 'blob:image-only'),revokeObjectURL:vi.fn()});
    const api=harness();render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    await waitFor(()=>expect(api.conversation).toHaveBeenCalled());
    const box=screen.getByRole('textbox',{name:'Message TwinPulse'});
    expect(box).toHaveProperty('value','');
    fireEvent.paste(box,{clipboardData:{files:[new File(['image-only'],'room.png',{type:'image/png'})]}});
    fireEvent.click(screen.getByRole('button',{name:'Send'}));
    await waitFor(()=>expect(api.conversationAction).toHaveBeenCalledWith(expect.objectContaining({action:'message',text:'',attachment:expect.objectContaining({name:'room.png',media_type:'image/png'})})));
  });
  it('distinguishes compensation ACK and the restored current frame from a disk commit',async()=>{
    const state={...initial(),scene_edit_transaction:{operation_id:'edit',state:'ROLLED_BACK',current_frame:true,
      durable_committed:false,engine_acknowledged:true,compensation_acknowledged:true,displayed_revision:'before',
      error:'OSError',command_id:'rejected-command'}};
    const api=harness(state);render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    expect(await screen.findByText(/Previous saved Twin restored · Compensation ACK: confirmed/)).toBeTruthy();
    // The compensation transaction receipt is not a later View-current-Twin receipt.
    expect(screen.getByText(/Disk commit: not committed · Transaction 3D frame: confirmed/)).toBeTruthy();
    expect(screen.getByText(/Transaction frame above refers to that restored revision/)).toBeTruthy();
    expect(api.recoverSceneEdit).not.toHaveBeenCalled();expect(api.conversationAction).not.toHaveBeenCalled();
  });
  it('preserves natural feedback and blocks Send plus Enter during child-local Build before a backend poll sees it',async()=>{
    const state=initial();const api=harness(state);
    const product={engine_connected:true,lease_owned:true,operations:[] as {command_id:string;status:string}[],
      snapshot:{engine_session_id:'engine',stage_epoch:'epoch',applied_revision:'current',runtime_state:'built',
        safety_state:null,capabilities:['site_scene_build_v2'],telemetry_available:false,run_id:null},
      engine_readiness:{site_scene_build_v2:{ready:true}}};
    api.productState.mockImplementation(async()=>product);
    api.workflow.mockResolvedValue({phase:'draft_ready',mode:'explicit_fixture',provider:{configured:true,label:'scripted'},
      site_draft:{revision:'current',artifact_id:'artifact'}});
    let release!:(value:unknown)=>void;
    const command=vi.fn(()=>new Promise(resolve=>{release=resolve;}));
    const extended={...api,acquireLease:vi.fn().mockResolvedValue({control_lease_id:'lease'}),
      renewLease:vi.fn().mockResolvedValue({}),acknowledge:vi.fn().mockResolvedValue({}),command};
    render(<ChatWorkspace api={extended as unknown as TwinPulseApi} advanced={()=>{}}/>);
    const view=await screen.findByRole('button',{name:'View current Twin'});
    const box=screen.getByRole('textbox',{name:'Message TwinPulse'});
    const text='Move only desk1 to the left and preserve every other object.';
    fireEvent.change(box,{target:{value:text}});
    fireEvent.click(view);
    await waitFor(()=>expect(command).toHaveBeenCalledTimes(1));
    expect(product.operations).toEqual([]); // The parent poll still sees no command.
    expect(screen.getByRole('button',{name:'Send'})).toHaveProperty('disabled',true);
    fireEvent.click(screen.getByRole('button',{name:'Send'}));
    fireEvent.keyDown(box,{key:'Enter',code:'Enter'});
    expect(api.conversationAction).not.toHaveBeenCalled();expect(box).toHaveProperty('value',text);
    expect(screen.getByText(/Your text and attachment are kept/)).toBeTruthy();
    const operation={command_id:'build',status:'succeeded'};product.operations.push(operation);
    release(operation);
    await waitFor(()=>expect(screen.getByRole('button',{name:'Send'})).toHaveProperty('disabled',false));
    expect(api.conversationAction).not.toHaveBeenCalled();expect(box).toHaveProperty('value',text);
    fireEvent.click(screen.getByRole('button',{name:'Send'}));
    await waitFor(()=>expect(api.conversationAction).toHaveBeenCalledWith(expect.objectContaining({action:'message',text,mode:'new'})));
    expect(command).toHaveBeenCalledTimes(1);
  });
  it('keeps text and an attached image while an observed engine command is pending',async()=>{
    vi.stubGlobal('URL',{createObjectURL:vi.fn(()=> 'blob:held-image'),revokeObjectURL:vi.fn()});
    const api=harness();api.productState.mockResolvedValue({engine_connected:true,
      operations:[{command_id:'build',command_type:'build_site_scene',status:'running'}]});
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    await waitFor(()=>expect(api.conversation).toHaveBeenCalled());
    const box=screen.getByRole('textbox',{name:'Message TwinPulse'});
    fireEvent.change(box,{target:{value:'Keep this feedback and image.'}});
    fireEvent.paste(box,{clipboardData:{files:[new File(['held-image'],'held.png',{type:'image/png'})]}});
    expect(await screen.findByAltText('Attached image preview')).toBeTruthy();
    expect(screen.getByRole('button',{name:'Send'})).toHaveProperty('disabled',true);
    fireEvent.keyDown(box,{key:'Enter',code:'Enter'});
    expect(api.conversationAction).not.toHaveBeenCalled();expect(box).toHaveProperty('value','Keep this feedback and image.');
    expect(screen.getByText('held.png · ready to send')).toBeTruthy();
  });
  it.each(['Status','Stop'])('keeps explicit %s available during an observed pending Build without retrying feedback',async text=>{
    const api=harness();api.productState.mockResolvedValue({engine_connected:true,
      operations:[{command_id:'build',command_type:'build_site_scene',status:'accepted'}]});
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    await waitFor(()=>expect(api.conversation).toHaveBeenCalled());
    const box=screen.getByRole('textbox',{name:'Message TwinPulse'});
    fireEvent.change(box,{target:{value:text}});
    expect(screen.getByRole('button',{name:'Send'})).toHaveProperty('disabled',false);
    fireEvent.keyDown(box,{key:'Enter',code:'Enter'});
    await waitFor(()=>expect(api.conversationAction).toHaveBeenCalledTimes(1));
    expect(api.conversationAction).toHaveBeenCalledWith(expect.objectContaining({text}));
  });
});
