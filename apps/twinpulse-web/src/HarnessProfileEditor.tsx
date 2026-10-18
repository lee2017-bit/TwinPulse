// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {useEffect,useRef,useState} from 'react';
import {ApiError,type TwinPulseApi} from './api';

export type HarnessReference={id:string;revision:number;sha256:string};
export type HarnessProfile={schema_version:'harness-profile-1.0';id:string;revision:number;provider:string;model_id:string;
  role:string;baseline_sha256:string;instructions:Record<string,string>;compatibility:'baseline'|'unverified'};
type Editor={profile:HarnessProfile;reference:HarnessReference|null;available:HarnessReference[]};
const refKey=(value:HarnessReference)=>JSON.stringify(value);

export function HarnessProfileEditor({api,stage,choice,disabled,onBusy,onSaved}:{api:TwinPulseApi;stage:'observer'|'planner';
  choice:{key_id:string;model_id:string;harness_profile?:HarnessReference|null};disabled:boolean;onBusy:(busy:boolean)=>void;
  onSaved:(reference:HarnessReference|null)=>void}){
  const [editor,setEditor]=useState<Editor|null>(null),[id,setId]=useState(''),[instructions,setInstructions]=useState<Record<string,string>>({});
  const [error,setError]=useState<string|null>(null),[notice,setNotice]=useState('');
  const mounted=useRef(true),pending=useRef(false);
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
  const action=async(operation:'draft'|'save'|'reset',reference?:HarnessReference|null)=>{
    if(pending.current||disabled)return;
    pending.current=true;onBusy(true);setError(null);setNotice('');
    try{
      const value=await api.updateProviderKeys({action:'harness_profile',operation,stage,key_id:choice.key_id,model_id:choice.model_id,
        ...(operation==='draft'?{reference:reference===undefined?choice.harness_profile??null:reference}:{}),
        ...(operation==='save'?{base_reference:editor?.reference??null,id,instructions}:{})});
      if(!mounted.current)return;
      if(operation==='draft'){
        const next=value.harness_editor;if(!next||next.stage!==stage||next.key_id!==choice.key_id||next.model_id!==choice.model_id)throw new Error('Invalid profile response');
        setEditor(next);setId(next.profile.id);setInstructions({...next.profile.instructions});
      }else{
        const next=value.harness_saved;if(!next||next.stage!==stage||next.profile.model_id!==choice.model_id)throw new Error('Invalid profile response');
        setEditor({profile:next.profile,reference:next.reference,available:[...(editor?.available??[]).filter(row=>refKey(row)!==refKey(next.reference)),next.reference]});
        setId(next.profile.id);setInstructions({...next.profile.instructions});onSaved(next.reference);
        setNotice('Snapshot saved. Save model routing to apply it to the next generation. Current work is unchanged.');
      }
    }catch(caught){if(mounted.current)setError(`Could not ${operation==='draft'?'read':'save'} this profile${caught instanceof ApiError&&/^[a-z0-9_]+$/.test(caught.code)?` (${caught.code})`:''}. Refresh the profile to check saved status.`);}
    finally{pending.current=false;onBusy(false);}
  };
  return <details className="harness-profile-editor"><summary>{stage==='observer'?'Photo':'Planning and repair'} harness profile</summary>
    <p>Model-specific instructions are layered onto the host’s validation and tool rules. Saved snapshots apply only after saving model routing.</p>
    <p>{choice.harness_profile?`Selected: ${choice.harness_profile.id} · revision ${choice.harness_profile.revision}`:choice.harness_profile===null?'Legacy instructions selected · for previous checkpoint recovery.':'Built-in model default selected.'}</p>
    <label>Instruction family<select disabled={disabled} value={choice.harness_profile===null?'legacy':'current'} onChange={event=>{
      if(event.target.value==='legacy'){onSaved(null);setNotice('Legacy instructions selected for previous checkpoints. Save model routing to apply; checkpoint compatibility is still checked by the host.');}
      else void action('reset');
    }}><option value="current">Current model harness</option><option value="legacy">Legacy instructions · previous checkpoints</option></select></label>
    <button disabled={disabled} onClick={()=>void action('draft')}>Load profile</button>
    {error&&<p role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}
    {editor&&<fieldset disabled={disabled}>
      <p>{editor.profile.compatibility==='unverified'?'Compatibility unverified · custom or copied instructions. Validate results before relying on them.':'Built-in baseline instructions · model quality still requires validation.'}</p>
      <label>Saved snapshot<select aria-label={`${stage} saved snapshot`} value={editor.reference?refKey(editor.reference):''} onChange={event=>{
        const selected=editor.available.find(row=>refKey(row)===event.target.value);if(selected)void action('draft',selected);
      }}><option value="" disabled>Built-in draft</option>{editor.available.map(row=><option key={refKey(row)} value={refKey(row)}>{row.id} · revision {row.revision}</option>)}</select></label>
      <button onClick={()=>{if(editor.reference)onSaved(editor.reference);setNotice('Snapshot selected. Save model routing to apply it.');}} disabled={disabled||!editor.reference}>Select snapshot</button>
      <label>Profile ID<input aria-label={`${stage} profile ID`} maxLength={80} pattern="[a-z0-9][a-z0-9_.-]{0,79}" value={id} onChange={event=>setId(event.target.value)}/></label>
      <button onClick={()=>{setId(`${id.slice(0,75)}-copy`);setNotice('Edit the copied instructions, then save a new snapshot.');}}>Duplicate profile</button>
      {Object.entries(instructions).map(([name,value])=><label key={name}>{name.replaceAll('_',' ')}
        <textarea aria-label={`${stage} ${name}`} rows={5} maxLength={6000} value={value} onChange={event=>setInstructions(current=>({...current,[name]:event.target.value}))}/></label>)}
      <button disabled={disabled||!/^[a-z0-9][a-z0-9_.-]{0,79}$/.test(id)||Object.values(instructions).some(value=>!value.trim()||value.length>6000)} onClick={()=>void action('save')}>Save new snapshot</button>
      <button onClick={()=>void action('reset')}>Restore built-in default</button>
      <small>SHA-256: {editor.reference?.sha256??editor.profile.baseline_sha256}</small>
    </fieldset>}
  </details>;
}
