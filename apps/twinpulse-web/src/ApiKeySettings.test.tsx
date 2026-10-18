// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,describe,it,expect,vi} from 'vitest';
import {ApiKeySettings,type ProviderKeyList} from './ApiKeySettings';
import type {TwinPulseApi} from './api';
afterEach(cleanup);
const state:ProviderKeyList={schema_version:'1.0',network_called:false,note:'인증 미검증',entries:[
  {id:'legacy',name:'기존 키',provider_profile:'nebius_token_factory',model_id:'Nano',base_url:'https://api.tokenfactory.nebius.com/v1/',
    configured:true,active:true,removable:false},
  {id:'new',name:'GPT 키',provider_profile:'openai',model_id:'gpt-5.4-mini',base_url:'https://api.openai.com/v1/',
    configured:true,active:false,removable:true}]};
function setup(){const api={providerKeys:vi.fn().mockResolvedValue(state),updateProviderKeys:vi.fn().mockResolvedValue(state)};
  const close=vi.fn();render(<ApiKeySettings api={api as unknown as TwinPulseApi} close={close}/>);return {api,close};}
describe('API key settings',()=>{
  it('opening only lists keys, never selects or dispatches',async()=>{const {api}=setup();
    await screen.findByText('기존 키');expect(api.updateProviderKeys).not.toHaveBeenCalled();
    expect(screen.getAllByRole('button',{name:'Use this key'})[0]).toHaveProperty('disabled',true);
  });
  it('registers explicitly and clears secret input without auto-selection',async()=>{const {api}=setup();
    await screen.findByText('기존 키');fireEvent.change(screen.getByLabelText('Key name'),{target:{value:'새 GPT'}});
    fireEvent.change(screen.getByLabelText('API key'),{target:{value:'key-canary'}});
    fireEvent.click(screen.getByRole('button',{name:'Register key'}));
    await waitFor(()=>expect(api.updateProviderKeys).toHaveBeenCalledTimes(1));
    expect(api.updateProviderKeys).toHaveBeenCalledWith({action:'register',name:'새 GPT',provider_profile:'openai',model_id:'gpt-5.4-mini',api_key:'key-canary'});
    expect(screen.getByLabelText('API key')).toHaveProperty('value','');
    expect(sessionStorage.getItem('api_key')).toBeNull();
  });
  it('reports saved key and applied default Flash Super separately without another settings mutation',async()=>{
    const {api}=setup();await screen.findByText('기존 키');
    api.updateProviderKeys.mockResolvedValue({...state,network_called:true,default_setup:{state:'applied',metadata_gets:2}});
    fireEvent.change(screen.getByLabelText('Provider'),{target:{value:'nebius_token_factory'}});
    fireEvent.change(screen.getByLabelText('Key name'),{target:{value:'First Nebius'}});
    fireEvent.change(screen.getByLabelText('API key'),{target:{value:'key-canary'}});
    fireEvent.click(screen.getByRole('button',{name:'Register key'}));
    const notice=await screen.findByRole('status');
    expect(notice.textContent).toContain('Key saved. Default Flash/Super models applied for the next generation.');
    expect(notice.textContent).toContain('Model metadata requests: 2. No inference or robot command started.');
    expect(api.updateProviderKeys).toHaveBeenCalledOnce();expect(api.updateProviderKeys).toHaveBeenCalledWith(expect.objectContaining({action:'register'}));
    expect(screen.getByLabelText('API key')).toHaveProperty('value','');expect(screen.queryByText(/key-canary/)).toBeNull();
    expect(screen.getByText(/Registering the first Nebius key may query the model list/)).toBeTruthy();
  });
  it.each([
    {state:'unavailable' as const,metadata_gets:2,message:'The selected models are unavailable for this account.',code:'model_unavailable'},
    {state:'unavailable' as const,metadata_gets:0,code:'metadata_unavailable'},
  ])('preserves key registration while explaining unavailable default setup $code',async default_setup=>{
    const {api}=setup();await screen.findByText('기존 키');api.updateProviderKeys.mockResolvedValue({...state,network_called:default_setup.metadata_gets>0,default_setup});
    fireEvent.change(screen.getByLabelText('Key name'),{target:{value:'Nebius'}});
    fireEvent.change(screen.getByLabelText('API key'),{target:{value:'key-canary'}});
    fireEvent.click(screen.getByRole('button',{name:'Register key'}));
    const notice=await screen.findByRole('status');expect(notice.textContent).toContain('Key saved. Default Flash/Super setup unavailable.');
    expect(notice.textContent).toContain(default_setup.message??`Setup could not be applied (${default_setup.code}).`);
    expect(notice.textContent).toContain(`Model metadata requests: ${default_setup.metadata_gets}.`);
    expect(screen.queryByRole('alert')).toBeNull();expect(api.updateProviderKeys).toHaveBeenCalledOnce();
  });
  it('selects explicitly and requires delete confirmation',async()=>{const {api}=setup();
    await screen.findByText('GPT 키');fireEvent.click(screen.getAllByRole('button',{name:'Use this key'})[1]);
    await waitFor(()=>expect(api.updateProviderKeys).toHaveBeenCalledWith({action:'select',id:'new'}));
    fireEvent.click(screen.getByRole('button',{name:'Delete'}));expect(api.updateProviderKeys).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button',{name:'Confirm deletion'}));
    await waitFor(()=>expect(api.updateProviderKeys).toHaveBeenCalledWith({action:'remove',id:'new'}));
  });
  it('clears keys on provider change and sanitizes errors',async()=>{const {api}=setup();await screen.findByText('GPT 키');
    fireEvent.change(screen.getByLabelText('API key'),{target:{value:'key-canary'}});
    fireEvent.change(screen.getByLabelText('Provider'),{target:{value:'nebius_token_factory'}});
    expect(screen.getByLabelText('API key')).toHaveProperty('value','');
    api.updateProviderKeys.mockRejectedValue(new Error('secret-canary'));
    fireEvent.click(screen.getAllByRole('button',{name:'Use this key'})[1]);
    await screen.findByRole('alert');expect(screen.queryByText(/secret-canary/)).toBeNull();
  });
});

const mixed={observer:{key_id:'new',model_id:'gpt-5.4-mini'},planner:{key_id:'legacy',model_id:'nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B'}};
function staged(enabled=false){
  const options={observer:[
    {...mixed.observer,provider:'openai',key_name:'GPT 키',configured:true,wire_model_id:'gpt-5.4-mini-2026-03-17'},
    {key_id:'legacy',model_id:'google/gemma-3-27b-it',provider:'nebius',key_name:'기존 키',configured:true,wire_model_id:'google/gemma-3-27b-it'}],
    planner:[{...mixed.planner,provider:'nebius',key_name:'기존 키',configured:true,wire_model_id:mixed.planner.model_id},
      {...mixed.observer,provider:'openai',key_name:'GPT 키',configured:true,wire_model_id:'gpt-5.4-mini-2026-03-17'}]};
  const value:ProviderKeyList={...state,stage_routing:{enabled,route:enabled?mixed:null,recommended:mixed,options,
    automatic_fallback:false,note:'저장으로 모델을 호출하지 않습니다.'}};
  const api={providerKeys:vi.fn().mockResolvedValue(value),updateProviderKeys:vi.fn().mockImplementation(async body=>
    ({...value,stage_routing:{...value.stage_routing,enabled:body.route!==null,route:body.route}}))};
  render(<ApiKeySettings api={api as unknown as TwinPulseApi} close={vi.fn()}/>);
  return {api,value};
}
describe('persistent stage model settings',()=>{
  it('drops a changed model profile while preserving the other stage profile',async()=>{
    const {api,value}=staged(true);cleanup();
    const photoRef={id:'photo-custom',revision:2,sha256:'c'.repeat(64)},plannerRef={id:'planner-custom',revision:4,sha256:'d'.repeat(64)};
    api.providerKeys.mockResolvedValue({...value,stage_routing:{...value.stage_routing!,harness_enabled:true,
      route:{observer:{...mixed.observer,harness_profile:photoRef},planner:{...mixed.planner,harness_profile:plannerRef}}}});
    render(<ApiKeySettings api={api as unknown as TwinPulseApi} close={vi.fn()}/>);await screen.findByLabelText('Photo analysis');
    fireEvent.change(screen.getByLabelText('Photo analysis'),{target:{value:JSON.stringify(['legacy','google/gemma-3-27b-it'])}});
    fireEvent.click(screen.getByRole('button',{name:'Save model routing'}));
    await waitFor(()=>expect(api.updateProviderKeys).toHaveBeenCalledWith({action:'stage_routing',route:{
      observer:{key_id:'legacy',model_id:'google/gemma-3-27b-it'},planner:{...mixed.planner,harness_profile:plannerRef}}}));
  });
  it('applies the full Flash Super recommendation without old caps policy or disabled thinking',async()=>{
    const {api,value}=staged(true);cleanup();
    const policy={schema_version:'generation-policy-1.0' as const,per_call_timeout_s:300,total_timeout_s:900,
      max_requests:12,max_repairs:3,stalled_repairs:2,initial_timeout_s:540,repair_timeout_s:300,
      final_timeout_s:60,repair_start_margin_s:90,external_final_review:false};
    const selected={observer:{key_id:'legacy',model_id:'deepseek-ai/DeepSeek-V4.1-Flash',max_output_tokens:40000},
      planner:{key_id:'legacy',model_id:'nvidia/nemotron-3-super-120b-a12b',max_output_tokens:40000},
      generation_policy:policy,model_catalog_sha256:'a'.repeat(64)};
    api.providerKeys.mockResolvedValue({...value,stage_routing:{...value.stage_routing!,
      route:{...mixed,planner:{...mixed.planner,thinking_mode:'disabled'}},recommended:selected,
      generation_policy_default:policy,options:{
        observer:[...value.stage_routing!.options.observer,{...selected.observer,provider:'nebius',key_name:'기존 키',configured:true,wire_model_id:selected.observer.model_id}],
        planner:[...value.stage_routing!.options.planner,{...selected.planner,provider:'nebius',key_name:'기존 키',configured:true,wire_model_id:selected.planner.model_id}]}}});
    render(<ApiKeySettings api={api as unknown as TwinPulseApi} close={vi.fn()}/>);
    await screen.findByRole('option',{name:'Nebius · Nemotron 3 Super 120B · 기존 키'});
    fireEvent.click(screen.getByRole('button',{name:'Use recommended models'}));
    expect(screen.queryByLabelText('Nemotron reasoning mode')).toBeNull();
    expect(screen.queryByLabelText('Generation timeout (seconds)')).toBeNull();
    expect(screen.getByLabelText('Whole generation timeout (seconds)')).toHaveProperty('value','900');
    expect(screen.getByLabelText('Planning and repair output token limit')).toHaveProperty('value','40000');
    expect(api.updateProviderKeys).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button',{name:'Save model routing'}));
    await waitFor(()=>expect(api.updateProviderKeys).toHaveBeenCalledWith({action:'stage_routing',route:selected}));
  });
  it('clears an unsupported disabled mode when selecting Super manually',async()=>{
    const {api,value}=staged(true);cleanup();
    const superChoice={key_id:'legacy',model_id:'nvidia/nemotron-3-super-120b-a12b'};
    api.providerKeys.mockResolvedValue({...value,stage_routing:{...value.stage_routing!,
      route:{...mixed,planner:{...mixed.planner,thinking_mode:'disabled'}},
      options:{...value.stage_routing!.options,planner:[...value.stage_routing!.options.planner,
        {...superChoice,provider:'nebius',key_name:'기존 키',configured:true,wire_model_id:superChoice.model_id}]}}});
    render(<ApiKeySettings api={api as unknown as TwinPulseApi} close={vi.fn()}/>);
    await screen.findByLabelText('Planning and repair');
    fireEvent.change(screen.getByLabelText('Planning and repair'),{target:{value:JSON.stringify(['legacy',superChoice.model_id])}});
    fireEvent.click(screen.getByRole('button',{name:'Save model routing'}));
    await waitFor(()=>expect(api.updateProviderKeys).toHaveBeenCalledWith({action:'stage_routing',route:{...mixed,planner:superChoice}}));
  });
  it('shows the reviewed combination with exact names and persists only explicit selection',async()=>{
    const {api,value}=staged();cleanup();
    const selected={observer:{key_id:'legacy',model_id:'deepseek-ai/DeepSeek-V4.1-Flash'},
      planner:{key_id:'legacy',model_id:'nvidia/Nemotron-3_5-Lightning'}};
    api.providerKeys.mockResolvedValue({...value,stage_routing:{...value.stage_routing!,recommended:selected,
      options:{observer:[{...selected.observer,provider:'nebius',key_name:'기존 키',configured:true,wire_model_id:selected.observer.model_id}],
        planner:[{...selected.planner,provider:'nebius',key_name:'기존 키',configured:true,wire_model_id:selected.planner.model_id}]}}});
    render(<ApiKeySettings api={api as unknown as TwinPulseApi} close={vi.fn()}/>);
    await screen.findByRole('option',{name:'Nebius · DeepSeek V4.1 Flash · 기존 키'});
    expect(screen.getByRole('option',{name:'Nebius · Nemotron 3.5 Lightning · 기존 키'})).toBeTruthy();
    expect(api.updateProviderKeys).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('Nemotron reasoning mode'),{target:{value:'disabled'}});
    fireEvent.click(screen.getByRole('button',{name:'Save model routing'}));
    await waitFor(()=>expect(api.updateProviderKeys).toHaveBeenCalledWith({action:'stage_routing',
      route:{...selected,planner:{...selected.planner,thinking_mode:'disabled'}}}));
  });
  it('keeps complete saved experimental policy without silently enabling it',async()=>{
    const {api,value}=staged(true);await screen.findByLabelText('Photo analysis');
    // A later backend response exposes the opt-in policy. No inferred migration.
    const policy={schema_version:'generation-policy-1.0' as const,per_call_timeout_s:300,total_timeout_s:900,
      max_requests:12,max_repairs:3,stalled_repairs:2,initial_timeout_s:540,repair_timeout_s:300,
      final_timeout_s:60,repair_start_margin_s:90,external_final_review:false as const};
    cleanup();
    api.providerKeys.mockResolvedValue({...value,stage_routing:{...value.stage_routing!,generation_policy_default:policy}});
    render(<ApiKeySettings api={api as unknown as TwinPulseApi} close={vi.fn()}/>);
    const toggle=await screen.findByLabelText('Use experimental staged generation');
    expect(screen.queryByText(/approved spending limits|spending\/input approval|expired price metadata|approve spending/)).toBeNull();
    expect(toggle).toHaveProperty('checked',false);expect(api.updateProviderKeys).not.toHaveBeenCalled();
    fireEvent.click(toggle);
    expect(screen.getByLabelText('Whole generation timeout (seconds)')).toHaveProperty('value','900');
    fireEvent.change(screen.getByLabelText('Total model request limit'),{target:{value:'4'}});
    expect(screen.getByRole('button',{name:'Save model routing'})).toHaveProperty('disabled',true);
    fireEvent.change(screen.getByLabelText('Total model request limit'),{target:{value:'12'}});
    const review=screen.getByLabelText('Compare current Isaac renders with the source photo');
    expect(review).toHaveProperty('checked',false);
    fireEvent.click(review);expect(api.updateProviderKeys).not.toHaveBeenCalled();
    fireEvent.click(review);
    fireEvent.click(screen.getByRole('button',{name:'Save model routing'}));
    await waitFor(()=>expect(api.updateProviderKeys).toHaveBeenCalledWith({action:'stage_routing',route:{...mixed,generation_policy:policy}}));
  });
  it('explicitly saves Nano no-thinking without dispatch and clears it for OpenAI',async()=>{
    const {api}=staged(true);await screen.findByLabelText('Nemotron reasoning mode');
    fireEvent.change(screen.getByLabelText('Nemotron reasoning mode'),{target:{value:'disabled'}});
    expect(api.updateProviderKeys).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button',{name:'Save model routing'}));
    await waitFor(()=>expect(api.updateProviderKeys).toHaveBeenCalledWith({action:'stage_routing',route:{
      ...mixed,planner:{...mixed.planner,thinking_mode:'disabled'}}}));
    expect(screen.getByLabelText('Nemotron reasoning mode')).toHaveProperty('value','disabled');
    fireEvent.change(screen.getByLabelText('Planning and repair'),{target:{value:JSON.stringify(['new','gpt-5.4-mini'])}});
    expect(screen.queryByLabelText('Nemotron reasoning mode')).toBeNull();
    fireEvent.click(screen.getByRole('button',{name:'Save model routing'}));
    await waitFor(()=>expect(api.updateProviderKeys).toHaveBeenLastCalledWith({action:'stage_routing',route:{
      ...mixed,planner:{key_id:'new',model_id:'gpt-5.4-mini'}}}));
  });
  it('validates and explicitly persists total timeout, keeping it on model and preset changes',async()=>{
    const {api}=staged(true);await screen.findByLabelText('Generation timeout (seconds)');
    const timeout=screen.getByLabelText('Generation timeout (seconds)');
    expect(timeout).toHaveProperty('value','90');
    for(const value of ['301','0','2.5','']){
      fireEvent.change(timeout,{target:{value}});
      expect(screen.getByRole('button',{name:'Save model routing'})).toHaveProperty('disabled',true);
    }
    fireEvent.change(timeout,{target:{value:'300'}});
    fireEvent.change(screen.getByLabelText('Photo analysis'),{target:{value:JSON.stringify(['legacy','google/gemma-3-27b-it'])}});
    expect(timeout).toHaveProperty('value','300');
    fireEvent.click(screen.getByRole('button',{name:'Use recommended models'}));
    expect(timeout).toHaveProperty('value','300');
    expect(api.updateProviderKeys).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button',{name:'Save model routing'}));
    await waitFor(()=>expect(api.updateProviderKeys).toHaveBeenCalledWith({action:'stage_routing',route:{...mixed,generation_timeout_s:300}}));
    expect(screen.getByLabelText('Generation timeout (seconds)')).toHaveProperty('value','300');
    expect(screen.getByRole('button',{name:'Save model routing'})).toHaveProperty('disabled',true);
  });
  it('edits independent output caps, validates integers and saves them explicitly',async()=>{
    const {api}=staged();await screen.findByLabelText('Photo analysis');
    const photo=screen.getByLabelText('Photo output token limit');
    const planner=screen.getByLabelText('Planning and repair output token limit');
    expect(photo).toHaveProperty('value','4000');expect(planner).toHaveProperty('value','20000');
    expect(planner).toHaveProperty('max','40000');
    fireEvent.change(planner,{target:{value:'40001'}});
    expect(screen.getByRole('button',{name:'Save model routing'})).toHaveProperty('disabled',true);
    fireEvent.change(planner,{target:{value:''}});
    expect(screen.getByRole('button',{name:'Save model routing'})).toHaveProperty('disabled',true);
    fireEvent.change(planner,{target:{value:'40000'}});
    fireEvent.change(photo,{target:{value:'5000'}});
    expect(api.updateProviderKeys).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button',{name:'Save model routing'}));
    await waitFor(()=>expect(api.updateProviderKeys).toHaveBeenCalledWith({action:'stage_routing',route:{
      observer:{...mixed.observer,max_output_tokens:5000},planner:{...mixed.planner,max_output_tokens:40000}}}));
    expect(screen.getByLabelText('Planning and repair output token limit')).toHaveProperty('value','40000');
  });
  it('prefills GPT/Nemotron but opening or changing selection never saves',async()=>{
    const {api}=staged();await screen.findByLabelText('Photo analysis');
    expect(screen.getByLabelText('Photo analysis')).toHaveProperty('value',JSON.stringify(['new','gpt-5.4-mini']));
    expect(screen.getByLabelText('Planning and repair')).toHaveProperty('value',JSON.stringify(['legacy',mixed.planner.model_id]));
    fireEvent.change(screen.getByLabelText('Photo analysis'),{target:{value:JSON.stringify(['legacy','google/gemma-3-27b-it'])}});
    expect(api.updateProviderKeys).not.toHaveBeenCalled();
    expect(screen.getByText(/Unsaved selection/)).toBeTruthy();
  });
  it('explicit save shows applied status and locks single-provider switches',async()=>{
    const {api}=staged();await screen.findByLabelText('Photo analysis');
    fireEvent.click(screen.getByRole('button',{name:'Save model routing'}));
    await waitFor(()=>expect(api.updateProviderKeys).toHaveBeenCalledWith({action:'stage_routing',route:mixed}));
    await screen.findByText(/Applied · saved models/);
    expect(screen.getAllByRole('button',{name:'Use this key'}).every(button=>(button as HTMLButtonElement).disabled)).toBe(true);
    expect(screen.getByRole('button',{name:'Save model routing'})).toHaveProperty('disabled',true);
  });
  it('allows independent planner replacement and explicit legacy restoration',async()=>{
    const {api}=staged(true);await screen.findByLabelText('Planning and repair');
    fireEvent.change(screen.getByLabelText('Planning and repair'),{target:{value:JSON.stringify(['new','gpt-5.4-mini'])}});
    fireEvent.click(screen.getByRole('button',{name:'Save model routing'}));
    await waitFor(()=>expect(api.updateProviderKeys).toHaveBeenCalledWith({action:'stage_routing',route:{observer:mixed.observer,planner:mixed.observer}}));
    await waitFor(()=>expect(screen.getByRole('button',{name:'Switch to single-provider mode'})).toHaveProperty('disabled',false));
    fireEvent.click(screen.getByRole('button',{name:'Switch to single-provider mode'}));
    await waitFor(()=>expect(api.updateProviderKeys).toHaveBeenLastCalledWith({action:'stage_routing',route:null}));
    await screen.findByText(/Single-provider mode ·/);
  });
  it('failed save retains unapplied state and never echoes transport secrets',async()=>{
    const {api}=staged();await screen.findByLabelText('Photo analysis');
    await waitFor(()=>expect(screen.getByRole('button',{name:'Save model routing'})).toHaveProperty('disabled',false));
    api.updateProviderKeys.mockRejectedValue(new Error('route-secret-canary'));
    fireEvent.click(screen.getByRole('button',{name:'Save model routing'}));
    await screen.findByRole('alert');expect(screen.queryByText(/route-secret-canary/)).toBeNull();
    expect(screen.getByText(/Single-provider mode ·/)).toBeTruthy();
  });
  it('refresh cannot race a settings save and completion after close is ignored',async()=>{
    const {api,value}=staged();await screen.findByLabelText('Photo analysis');
    let finish!:(value:ProviderKeyList)=>void;
    api.providerKeys.mockImplementationOnce(()=>new Promise<ProviderKeyList>(resolve=>{finish=resolve;}));
    fireEvent.click(screen.getByRole('button',{name:'Refresh list'}));
    expect(screen.getByRole('button',{name:'Applying…'})).toHaveProperty('disabled',true);
    fireEvent.click(screen.getByRole('button',{name:'Applying…'}));
    expect(api.updateProviderKeys).not.toHaveBeenCalled();
    cleanup();finish(value);
    await Promise.resolve();expect(api.updateProviderKeys).not.toHaveBeenCalled();
  });
});
