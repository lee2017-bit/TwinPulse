// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {fireEvent,render,screen,within} from '@testing-library/react';
import {describe,it,expect,vi} from 'vitest';
import {ActionCard,ChatWorkspace} from './ChatWorkspace';
import type {QuestionCard} from './conversation-types';
import type {TwinPulseApi} from './api';

const card=(state='waiting'):QuestionCard=>({id:'q',message_id:'m',kind:'robot_presence',question:'Do you have a physical robot?',state:state as QuestionCard['state'],selected_choice_id:state==='answered'?'sim':null,operation_id:null,expected_session_revision:1,
  choices:[{id:'sim',label:'Simulation only',enabled:true,disabled_reason:null},{id:'real',label:'Use my robot',enabled:true,disabled_reason:null}]});

describe('One current chat step',()=>{
  it('selection is local; only Continue submits once',()=>{
    const act=vi.fn();render(<ActionCard card={card()} busy={false} act={act}/>);
    expect(screen.getAllByRole('button')).toHaveLength(1);
    expect(screen.getByRole('button',{name:'Continue'})).toHaveProperty('disabled',true);
    fireEvent.click(screen.getByRole('radio',{name:'Simulation only'}));
    expect(act).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button',{name:'Create Twin'}));
    expect(act).toHaveBeenCalledWith(expect.objectContaining({id:'q'}),'sim');
  });
  it('past and future questions never offer clickable choices',()=>{
    const act=vi.fn();const view=render(<ActionCard card={card('answered')} busy={false} act={act}/>);
    expect(screen.queryByRole('button')).toBeNull();expect(screen.getByText('Simulation only')).toBeTruthy();
    view.rerender(<ActionCard card={card()} current={false} busy={false} act={act}/>);
    expect(screen.queryByRole('radio')).toBeNull();expect(screen.queryByRole('button')).toBeNull();
  });
  it('robot selection hides premature preparation and inspection actions',async()=>{
    const current={...card(),kind:'robot_selection',choices:[{id:'turtlebot3_burger',label:'TurtleBot3 Burger',enabled:true,disabled_reason:null}]};
    const state={schema_version:'conversation-1.0',session_id:'s',project_id:'p',revision:1,cursor:1,mode:'REAL',robot_id:null,physical_authority:false,restore_error:null,
      messages:[{message_id:'m',role:'assistant',content:current.question,status:'completed',attachments:[],created_at:'now',operation_id:null}],cards:[current],events:[],generation:null,accepted_request_ids:[],inspection:{state:'NOT_STARTED'}};
    const api={bootstrap:vi.fn().mockResolvedValue(undefined),conversation:vi.fn().mockResolvedValue(state),runtimeState:vi.fn().mockResolvedValue({status:'ready'}),productState:vi.fn().mockResolvedValue({engine_connected:false}),workflow:vi.fn().mockResolvedValue({phase:'empty',provider:{configured:false}})};
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    const section=await screen.findByLabelText(current.question);
    expect(within(section).getAllByRole('button')).toHaveLength(1);
    expect(screen.queryByRole('button',{name:/Check robot connection|collect once|Refresh inspection/})).toBeNull();
  });
  it('observes the derived SIM revision without restoring Run authority',async()=>{
    const state={schema_version:'conversation-1.0',session_id:'s',project_id:'p',revision:1,cursor:1,mode:'SIM',robot_id:'turtlebot3_burger',physical_authority:false,restore_error:null,
      messages:[],cards:[],events:[],generation:null,accepted_request_ids:[],simulation_review:{plan:{scene_revision:'derived'}}};
    const api={bootstrap:vi.fn().mockResolvedValue(undefined),conversation:vi.fn().mockResolvedValue(state),runtimeState:vi.fn().mockResolvedValue({status:'ready'}),
      productState:vi.fn().mockResolvedValue({engine_connected:true,snapshot:{applied_revision:'derived',run_id:'run',runtime_state:'running',capabilities:['site_simulation_v1']}}),
      workflow:vi.fn().mockResolvedValue({phase:'draft_ready',site_draft:{revision:'original',artifact_id:'artifact'},provider:{configured:true}}),acquireLease:vi.fn(),simulationRun:vi.fn()};
    render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
    expect(await screen.findByText('SIM navigation · running')).toBeTruthy();
    expect(api.acquireLease).not.toHaveBeenCalled();expect(api.simulationRun).not.toHaveBeenCalled();
  });
});
