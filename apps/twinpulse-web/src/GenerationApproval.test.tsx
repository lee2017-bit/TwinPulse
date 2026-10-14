// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {describe,expect,it,vi} from 'vitest';
import {ActionCard,ChatWorkspace} from './ChatWorkspace';
import type {ConversationState,QuestionCard} from './conversation-types';
import type {TwinPulseApi} from './api';

const card=():QuestionCard=>({id:'grant',message_id:'m',kind:'generation_approval',question:'Approve generation?',
  state:'waiting',selected_choice_id:null,operation_id:null,expected_session_revision:3,
  choices:[{id:'approve',label:'Approve generation',enabled:true,disabled_reason:null},{id:'cancel',label:'Not now',enabled:true,disabled_reason:null}],
  generation_approval:{schema_version:'ordinary-generation-preview-1.0',input_sha256:'a'.repeat(64),input_revision:'r',preview_sha256:'b'.repeat(64),
    image_count:1,purpose:'Create an approximate 3D scene',pricing_valid_until:'2026-10-16',default_limit_usd:'1.00',
    worst_single_reserve_usd:'.318',minimum_initial_reserve_usd:'.36',checkpoint_id:'c'.repeat(64),prior_requests:2,prior_active_s:20,
    prior_cost:{estimated_usage_usd:'.01',reserved_unknown_usd:'0',invoice_verified:false},
    policy:{per_call_timeout_s:300,total_timeout_s:900,max_requests:12,max_repairs:3,stalled_repairs:2},
    models:[{stage:'observer',model_id:'GPT',origin:'https://api.openai.com/v1',max_output_tokens:4000,thinking_mode:'default',
      full_context_reserve_usd:'.318',price_source:'https://developers.openai.com',price_verified_at:'2026-10-08'}]}});

describe('Ordinary generation continuation',()=>{
  it('starts the fresh SIM choice without a generation cap or another approval screen',()=>{
    const question=card();question.kind='robot_presence';question.question='Do you have a physical robot?';
    question.choices=[{id:'sim',label:'Simulation only',enabled:true,disabled_reason:null},
      {id:'real',label:'Use my robot',enabled:true,disabled_reason:null}];
    question.generation_approval!.checkpoint_id=null;
    const act=vi.fn();render(<ActionCard card={question} busy={false} act={act}/>);
    expect(screen.queryByText(/Approve this scene/)).toBeNull();expect(act).not.toHaveBeenCalled();
    expect(screen.queryByLabelText('Maximum spend for this action (USD)')).toBeNull();
    fireEvent.click(screen.getByRole('radio',{name:'Simulation only'}));
    fireEvent.click(screen.getByRole('button',{name:'Create Twin'}));
    expect(act).toHaveBeenCalledWith(question,'sim');
  });
  it('shows derived-render upload and automatic preview Build before any approval',()=>{
    const question=card();question.kind='robot_presence';question.choices=[{id:'sim',label:'Simulation only',enabled:true,disabled_reason:null}];const act=vi.fn();
    question.generation_approval={...question.generation_approval!,render_review_approved:true,
      purpose:'Send the source photo and derived Isaac renders for comparison. Automatic idle preview Build; no Run or robot movement.'};
    render(<ActionCard card={question} busy={false} act={act}/>);
    expect(screen.getByText(/source photo and derived Isaac renders/)).toBeTruthy();
    expect(screen.getByText(/Automatic idle preview Build/)).toBeTruthy();
    expect(act).not.toHaveBeenCalled();
  });
  it('keeps robot choice explicit and sends no financial input',()=>{
    const question=card();question.kind='robot_presence';question.choices=[{id:'sim',label:'Simulation only',enabled:true,disabled_reason:null},
      {id:'real',label:'Use my robot',enabled:true,disabled_reason:null}];
    const act=vi.fn();render(<ActionCard card={question} busy={false} act={act}/>);
    expect(act).not.toHaveBeenCalled();expect(screen.getByRole('button',{name:'Continue'})).toHaveProperty('disabled',true);
    expect(screen.queryByText(/Previous cost: USD/)).toBeNull();expect(screen.queryByLabelText('Maximum spend for this action (USD)')).toBeNull();
    fireEvent.click(screen.getByRole('radio',{name:'Use my robot'}));
    expect(act).not.toHaveBeenCalled();fireEvent.click(screen.getByRole('button',{name:'Continue'}));
    expect(act).toHaveBeenCalledWith(question,'real');
  });
  it('never executes a legacy pending financial approval when shown by itself',()=>{
    const act=vi.fn();render(<ActionCard card={card()} busy={false} act={act}/>);
    expect(screen.queryByRole('radio')).toBeNull();expect(screen.queryByRole('button')).toBeNull();
    expect(screen.queryByRole('textbox')).toBeNull();expect(act).not.toHaveBeenCalled();
  });
  it('renders historical approval as non-executable even if it was left waiting',()=>{
    const act=vi.fn();render(<ActionCard card={card()} busy={false} act={act} current={false}/>);
    expect(screen.queryByRole('button')).toBeNull();expect(screen.queryByRole('textbox')).toBeNull();expect(act).not.toHaveBeenCalled();
  });
  it('continues unfinished work once without another financial approval question',async()=>{
    const state:ConversationState={schema_version:'conversation-1.0',session_id:'s',project_id:'p',revision:3,cursor:3,
      mode:'SIM',robot_id:null,physical_authority:false,restore_error:null,budgeted_generation_available:true,
      messages:[],cards:[],events:[],accepted_request_ids:[],generation:{operation_id:'failed',state:'failed',summary:'Output truncated',
      can_cancel:false,started_at:'now',last_progress_at:'now',error:{code:'provider_response_invalid',message:'Output truncated'}}};
    let current=state;
    const api={bootstrap:vi.fn().mockResolvedValue(undefined),conversation:vi.fn(async()=>current),
      runtimeState:vi.fn().mockResolvedValue({status:'starting'}),productState:vi.fn().mockResolvedValue({engine_connected:false}),
      workflow:vi.fn().mockResolvedValue({phase:'generation_failed'}),conversationAction:vi.fn(async()=>{
        current={...state,revision:4,cursor:4,generation:{...state.generation!,state:'running',error:null}};return current;})};
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    const review=await screen.findByRole('button',{name:'Continue unfinished work'});
    expect(api.conversationAction).not.toHaveBeenCalled();fireEvent.click(review);
    await waitFor(()=>expect(api.conversationAction).toHaveBeenCalledWith(expect.objectContaining({action:'generation_retry',operation_id:'failed'})));
    expect(api.conversationAction).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('radio',{name:'Approve generation'})).toBeNull();
    expect(screen.queryByLabelText('Maximum spend for this action (USD)')).toBeNull();
  });
});
