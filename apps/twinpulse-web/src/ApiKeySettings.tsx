// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {useEffect, useRef, useState} from 'react';
import {ApiError, type TwinPulseApi} from './api';
import './api-key-settings.css';

export type ProviderKeyList = {
  schema_version: '1.0'; network_called: boolean; note: string;
  entries: {id: string; name: string; provider_profile: string; model_id: string;
    base_url: string; configured: boolean; active: boolean; removable: boolean; stage_selected?:boolean}[];
  stage_routing?: StageRoutingState;
  default_setup?: {state:'applied'|'unavailable';metadata_gets:number;code?:string;message?:string};
};
type StageChoice={key_id:string;model_id:string;max_output_tokens?:number;thinking_mode?:'default'|'disabled'};
type GenerationPolicy={schema_version:'generation-policy-1.0';per_call_timeout_s:number;total_timeout_s:number;
  max_requests:number;max_repairs:number;stalled_repairs:number;initial_timeout_s:number;
  repair_timeout_s:number;final_timeout_s:number;repair_start_margin_s:number;external_final_review:boolean};
type StageRoute={observer:StageChoice;planner:StageChoice;generation_timeout_s?:number;generation_policy?:GenerationPolicy;model_catalog_sha256?:string};
type StageOption=StageChoice&{provider:string;key_name:string;configured:boolean;wire_model_id:string};
type StageRoutingState={enabled:boolean;route:StageRoute|null;recommended:StageRoute|null;
  options:{observer:StageOption[];planner:StageOption[]};automatic_fallback:false;note:string;
  default_output_tokens?:{observer:number;planner:number};max_output_tokens?:number;
  default_generation_timeout_s?:number;max_generation_timeout_s?:number;
  recommended_profile?:string;recommended_name?:string;recommended_unavailable_reason?:string|null;
  generation_policy_default?:GenerationPolicy;generation_policy_requires_separate_approval?:boolean};
const generationPolicyDefault:GenerationPolicy={schema_version:'generation-policy-1.0',per_call_timeout_s:300,
  total_timeout_s:900,max_requests:12,max_repairs:3,stalled_repairs:2,initial_timeout_s:540,
  repair_timeout_s:300,final_timeout_s:60,repair_start_margin_s:90,external_final_review:false};
const choiceId=(choice:StageChoice)=>JSON.stringify([choice.key_id,choice.model_id]);
const modelLabel=(model:string)=>({
  'gpt-5.4-mini':'GPT-5.4 mini',
  'nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B':'Nemotron Nano',
  'nvidia/Nemotron-3_5-Lightning':'Nemotron 3.5 Lightning',
  'nvidia/nemotron-3-super-120b-a12b':'Nemotron 3 Super 120B',
  'deepseek-ai/DeepSeek-V4.1-Flash':'DeepSeek V4.1 Flash',
  'Qwen/Qwen3.8-27B':'Qwen 3.8 27B',
  'gpt-6-luna':'GPT6 Luna · structured mode: none',
  'google/gemma-3-27b-it':'Gemma 3',
  'openbmb/MiniCPM-V-4_5':'MiniCPM-V',
} as Record<string,string>)[model]??model;
const nano='nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B';
const supportsNoThinking=(model:string)=>[nano,'nvidia/Nemotron-3_5-Lightning'].includes(model);

export function ApiKeySettings({api,close}: {api:TwinPulseApi;close:()=>void}) {
  const [list,setList]=useState<ProviderKeyList|null>(null);
  const [name,setName]=useState('');
  const [profile,setProfile]=useState('openai');
  const [model,setModel]=useState('gpt-5.4-mini');
  const [key,setKey]=useState('');
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState<string|null>(null);
  const [notice,setNotice]=useState('');
  const [remove,setRemove]=useState<string|null>(null);
  const [route,setRoute]=useState<StageRoute|null>(null);
  const active=useRef(true);
  const inFlight=useRef(false);
  const panel=useRef<HTMLDivElement>(null);
  const applyList=(value:ProviderKeyList)=>{
    setList(value);
    setRoute(value.stage_routing?.route??value.stage_routing?.recommended??null);
  };
  useEffect(()=>{
    active.current=true;
    const previous=document.activeElement as HTMLElement|null;
    panel.current?.focus();
    void api.providerKeys().then(value=>{if(active.current)applyList(value);})
      .catch(()=>{if(active.current)setError('Could not read the key list. Refresh or review diagnostics.');});
    return ()=>{active.current=false;previous?.focus();};
  },[api]);
  const action=async(body:object, message:string)=>{
    if(inFlight.current)return;
    inFlight.current=true;setBusy(true);setError(null);setNotice('');
    // The input is cleared before awaiting HTTP and never persisted in browser storage.
    setKey('');
    try {
      const value=await api.updateProviderKeys(body);
      if(active.current){
        applyList(value);
        const setup='action' in body&&body.action==='register'?value.default_setup:undefined;
        if(setup){
          const reason=setup.message??(setup.code?`Setup could not be applied (${setup.code}).`:'Review model availability in the routing settings.');
          setNotice(`Key saved. ${setup.state==='applied'?
            'Default Flash/Super models applied for the next generation.':`Default Flash/Super setup unavailable. ${reason}`} `+
            `Model metadata requests: ${setup.metadata_gets}. No inference or robot command started.`);
        }else setNotice(message);
        setRemove(null);
      }
    } catch (caught) {
      // Do not echo a transport/proxy exception that could contain a request body.
      const code=caught instanceof ApiError&&/^[a-z0-9_]+$/.test(caught.code)?` (${caught.code})`:'';
      if(active.current)setError(`The request could not be completed${code}. Refresh to check saved status before retrying. Re-enter the key if needed.`);
    } finally {inFlight.current=false;if(active.current)setBusy(false);}
  };
  const refresh=async()=>{
    if(inFlight.current)return;
    inFlight.current=true;setBusy(true);setKey('');setError(null);setNotice('');
    try {const value=await api.providerKeys();if(active.current)applyList(value);}
    catch {if(active.current)setError('Could not read the key list. Saved settings were not changed.');}
    finally {inFlight.current=false;if(active.current)setBusy(false);}
  };
  const capFor=(stage:'observer'|'planner')=>route?.[stage].max_output_tokens??list?.stage_routing?.default_output_tokens?.[stage]??(stage==='observer'?4000:20000);
  const limitsValid=!!route&&(['observer','planner'] as const).every(stage=>Number.isInteger(capFor(stage))&&capFor(stage)>=1&&capFor(stage)<=(list?.stage_routing?.max_output_tokens??40000));
  const timeout=route?.generation_timeout_s??list?.stage_routing?.default_generation_timeout_s??90;
  const timeoutValid=Number.isInteger(timeout)&&timeout>=1&&timeout<=(list?.stage_routing?.max_generation_timeout_s??300);
  const policy=route?.generation_policy;
  const policyBounds=[['per_call_timeout_s',1,300],['total_timeout_s',1,3600],['max_requests',1,32],
    ['max_repairs',0,8],['stalled_repairs',1,4],['initial_timeout_s',1,3600],['repair_timeout_s',0,3600],
    ['final_timeout_s',1,3600],['repair_start_margin_s',1,300]] as const;
  const policyValid=!policy||policyBounds.every(([key,min,max])=>Number.isInteger(policy[key])&&policy[key]>=min&&policy[key]<=max)&&
    policy.initial_timeout_s+policy.repair_timeout_s+policy.final_timeout_s<=policy.total_timeout_s&&
    policy.max_requests-policy.max_repairs-Number(policy.external_final_review)>=2&&(!policy.max_repairs||policy.repair_timeout_s>=policy.repair_start_margin_s);
  return <div className="key-settings-backdrop">
    <div ref={panel} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby="key-settings-title"
      className="key-settings-panel" onKeyDown={event=>{
        if(event.key==='Escape'&&!busy)close();
        if(event.key==='Tab'){
          const buttons=Array.from(panel.current?.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),select:not(:disabled)')??[]);
          const first=buttons[0],last=buttons[buttons.length-1];
          if(event.shiftKey&&(document.activeElement===first||document.activeElement===panel.current)){event.preventDefault();last?.focus();}
          if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
        }
      }}>
      <header><h2 id="key-settings-title">API keys</h2><button disabled={busy} onClick={close}>Close</button></header>
      <p>Keys are saved in Windows Credential Manager. Registering the first Nebius key may query the model list to configure Flash/Super. No inference or robot command starts when saving or selecting a key.</p>
      {error&&<p role="alert">{error}</p>}
      {notice&&<p role="status">{notice}</p>}
      {list?.stage_routing&&<section aria-label="Model routing" className="stage-routing-settings">
        <h3>Model routing</h3>
        <p role="status">{list.stage_routing.enabled?'Applied · saved models will be used for the next generation.':'Single-provider mode · the choices below are not applied until saved.'}</p>
        <p>Photos go only to the photo model. Planning and repair receive its observations and your description.</p>
        {(['observer','planner'] as const).map(stage=><div key={stage}><label>
          {stage==='observer'?'Photo analysis':'Planning and repair'}
          <select disabled={busy} value={route?choiceId(route[stage]):''} onChange={event=>{
            const option=list.stage_routing!.options[stage].find(v=>choiceId(v)===event.target.value);
            if(!option)return;
            const other=stage==='observer'?'planner':'observer';
            const otherOption=route?.[other]??list.stage_routing!.options[other].find(v=>v.configured);
            if(otherOption)setRoute({...route,[stage]:{key_id:option.key_id,model_id:option.model_id,
              ...(route?.[stage].max_output_tokens!==undefined?{max_output_tokens:route[stage].max_output_tokens}:{}),
              ...(stage==='planner'&&option.provider==='nebius'&&supportsNoThinking(option.model_id)&&route?.planner.thinking_mode?{thinking_mode:route.planner.thinking_mode}:{})},
              [other]:{key_id:otherOption.key_id,model_id:otherOption.model_id,
                ...(otherOption.max_output_tokens!==undefined?{max_output_tokens:otherOption.max_output_tokens}:{}),
                ...(otherOption.thinking_mode?{thinking_mode:otherOption.thinking_mode}:{})}} as StageRoute);
          }}>
            <option value="" disabled>Choose a saved key and model</option>
            {list.stage_routing!.options[stage].map(option=><option key={choiceId(option)} value={choiceId(option)} disabled={!option.configured}>
              {option.provider==='openai'?'OpenAI':'Nebius'} · {modelLabel(option.model_id)} · {option.key_name}{!option.configured?' (key missing)':''}
            </option>)}
          </select>
        </label><label>{stage==='observer'?'Photo output token limit':'Planning and repair output token limit'}
          <input type="number" min={1} max={list.stage_routing?.max_output_tokens??40000} step={1}
            disabled={busy||!route} value={Number.isNaN(capFor(stage))?'':capFor(stage)}
            onChange={event=>{if(route)setRoute({...route,[stage]:{...route[stage],max_output_tokens:event.target.valueAsNumber}});}}/>
        </label></div>)}
        {route&&supportsNoThinking(route.planner.model_id)&&<label>Nemotron reasoning mode
          <select disabled={busy} value={route.planner.thinking_mode??'default'} onChange={event=>{
            setRoute({...route,planner:{...route.planner,thinking_mode:event.target.value as 'default'|'disabled'}});
          }}><option value="default">Model default</option><option value="disabled">Disabled · structured JSON only</option></select>
        </label>}
        {route&&supportsNoThinking(route.planner.model_id)&&<p>Applies to both planning and repair. Disabling reasoning may reduce output-budget exhaustion; scene quality still requires validation.</p>}
        <p>Output limits include reasoning tokens. If an output limit is reached, generation stops without automatic repair or another model request.</p>
        <p>The host allows up to 40,000 tokens; model output and context limits still apply.</p>
        {!policy&&<><label>Generation timeout (seconds)
          <input type="number" min={1} max={list.stage_routing.max_generation_timeout_s??300} step={1}
            disabled={busy||!route} value={Number.isNaN(timeout)?'':timeout}
            onChange={event=>{if(route)setRoute({...route,generation_timeout_s:event.target.valueAsNumber});}}/>
        </label>
        <p>Total time for photo analysis, planning and repair, not per request. 300 seconds = 5 minutes. Changes apply to the next generation only; robot safety timers are unchanged.</p>
        {route&&!timeoutValid&&<p role="alert">Enter an integer generation timeout from 1 to 300 seconds.</p>}</>}
        {route&&!limitsValid&&<p role="alert">Enter an integer output limit from 1 to 40,000 for each stage.</p>}
        {route&&list.stage_routing.generation_policy_default&&<details>
          <summary>Generation limits</summary>
          <p>This separates per-request time from the whole generation and reserves shared repair capacity. Request generation or continue unfinished work in chat to start inference. Saving settings does not start inference.</p>
          <label><input type="checkbox" disabled={busy} checked={!!policy} onChange={event=>{
            const selected={...route};
            if(event.target.checked)selected.generation_policy={...(list.stage_routing!.generation_policy_default??generationPolicyDefault)};
            else delete selected.generation_policy;
            setRoute(selected);
          }}/>Use experimental staged generation</label>
          {policy&&<>
            <label><input type="checkbox" disabled={busy} checked={policy.external_final_review}
              onChange={event=>setRoute({...route,generation_policy:{...policy,external_final_review:event.target.checked}})}/>
              Compare current Isaac renders with the source photo</label>
            {policy.external_final_review&&<p>When you request generation, Build idle previews and send the photo plus renders to the selected photo model. Corrections and re-reviews share the request, repair and time limits. No Run or robot movement. Text-only input needs no image review.</p>}
            {policyBounds.map(([field,min,max])=><label key={field}>{({per_call_timeout_s:'Per-request timeout (seconds)',
              total_timeout_s:'Whole generation timeout (seconds)',max_requests:'Total model request limit',
              max_repairs:'Shared repair request limit',stalled_repairs:'Consecutive stalled repair limit',
              initial_timeout_s:'Initial generation time allocation (seconds)',repair_timeout_s:'Shared repair time allocation (seconds)',
              final_timeout_s:'Completion / render review time reserve (seconds)',repair_start_margin_s:'Minimum time before starting repair (seconds)'} as const)[field]}
              <input type="number" disabled={busy} min={min} max={max} step={1}
                value={Number.isNaN(policy[field])?'':policy[field]}
                onChange={event=>setRoute({...route,generation_policy:{...policy,[field]:event.target.valueAsNumber}})}/>
            </label>)}
            <p>These are shared limits, not a guarantee of three full-length repair requests. Transport retry is off and output exhaustion always stops. Saving settings does not start inference or robot movement.</p>
            {!policyValid&&<p role="alert">Check integer limits, time allocations and reserved repair requests. Leave at least two initial requests.</p>}
          </>}
        </details>}
        {!route&&<p>Register a key for each stage first.</p>}
        {route&&<p className="stage-route-summary">Photo: {modelLabel(route.observer.model_id)} → Planning and repair: {modelLabel(route.planner.model_id)}
          {JSON.stringify(route)!==JSON.stringify(list.stage_routing.route)&&' · Unsaved selection'}</p>}
        <button disabled={busy||!list.stage_routing.recommended} onClick={()=>{
          const recommended=list.stage_routing!.recommended;
          if(recommended)setRoute({...recommended,...(!recommended.generation_policy&&route?.generation_timeout_s!==undefined?{generation_timeout_s:route.generation_timeout_s}:{}),
            ...(!recommended.generation_policy&&route?.generation_policy?{generation_policy:route.generation_policy}:{})});
        }}>Use recommended models</button>
        {list.stage_routing.recommended_name&&<p>{list.stage_routing.recommended_name}</p>}
        {!list.stage_routing.recommended&&list.stage_routing.recommended_unavailable_reason&&<p>{list.stage_routing.recommended_unavailable_reason}</p>}
        <button disabled={busy||!route||!limitsValid||!timeoutValid||!policyValid||JSON.stringify(route)===JSON.stringify(list.stage_routing.route)}
          onClick={()=>void action({action:'stage_routing',route},'Saved and applied to the generation gateway. Used from the next generation; no model request was sent.')}>
          {busy?'Applying…':'Save model routing'}</button>
        {list.stage_routing.enabled&&<button disabled={busy} onClick={()=>void action({action:'stage_routing',route:null},'Switched to single-provider settings. No model request was sent.')}>Switch to single-provider mode</button>}
        <small>{list.stage_routing.note} Failures never switch providers automatically.</small>
      </section>}
      <section aria-label="Saved keys"><h3>Saved keys</h3>
        {!list&&<p>Reading key list…</p>}
        {list?.entries.length===0&&<p>No registered keys.</p>}
        {list?.entries.map(entry=><article key={entry.id}>
          <strong>{entry.name}</strong><span>{entry.stage_selected?' · Used in model routing':entry.active?' · Selected (single-provider)':''}</span>
          <p>{entry.provider_profile} · {entry.model_id}</p><small>{entry.base_url}</small>
          <p>{entry.configured?'Securely saved · authentication unverified':'Key missing · register again'}</p>
          <button disabled={busy||entry.active||!entry.configured||list.stage_routing?.enabled} onClick={()=>void action({action:'select',id:entry.id},
            'Selected this key. Reselect input and review the scene before running. Generation was not started.')}>Use this key</button>
          {entry.removable&&!entry.active&&<button disabled={busy} onClick={()=>setRemove(entry.id)}>Delete</button>}
          {remove===entry.id&&<div><p>Delete this key from secure storage? Recovery requires entering it again.</p>
            <button disabled={busy} onClick={()=>void action({action:'remove',id:entry.id},'Deleted the selected key.')}>Confirm deletion</button>
            <button disabled={busy} onClick={()=>setRemove(null)}>Cancel</button></div>}
        </article>)}
      </section>
      <form autoComplete="off" onSubmit={event=>{event.preventDefault();void action({action:'register',name,
        provider_profile:profile,model_id:model,api_key:key},'Saved. Choose which key to use in the list. Authentication has not been tested.');}}>
        <h3>Register a key</h3>
        <fieldset disabled={busy||!list}>
          <label>Key name<input required maxLength={80} value={name} onChange={e=>setName(e.target.value)} placeholder="e.g. OpenAI personal"/></label>
          <label>Provider<select value={profile} onChange={e=>{setProfile(e.target.value);setModel(e.target.value==='openai'?'gpt-5.4-mini':nano);setKey('');}}>
            <option value="openai">OpenAI</option><option value="nebius_token_factory">Nebius Token Factory</option>
            <option value="nebius_site_v2">Nebius Site v2</option></select></label>
          <label>Model<input required maxLength={256} disabled={profile!=='openai'} value={model} onChange={e=>setModel(e.target.value)}/></label>
          <label>API key<input required type="password" autoComplete="new-password" spellCheck={false} value={key} onChange={e=>setKey(e.target.value)}/></label>
          <button disabled={!key.trim()||!name.trim()} type="submit">{busy?'Saving…':'Register key'}</button>
        </fieldset>
      </form>
      <p>{list?.note}</p>
      <button disabled={busy} onClick={()=>void refresh()}>Refresh list</button>
    </div>
  </div>;
}
