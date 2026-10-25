// SPDX-License-Identifier: Apache-2.0
import {useEffect,useRef,useState} from 'react';
import type {TwinPulseApi} from './api';
export interface AlignmentState {
  context:{scene_revision:string}|null;references:{id:string;label:string;length_m:number;ends_m:number[][]}[];
  job:{job_id:string;status:string;reason:string|null}|null;visible:boolean;review_digest:string|null;
  review:{status:string;source:string;reference:{status:string;ratio:number;basis:string};
    match:{body_pose:number[];validation:{mean_error_m:number;inlier_fraction:number;normal_diversity:number;first_hit_mean_error_m?:number;first_hit_inlier_fraction?:number}};
    temporal_validation:{mean_error_m:number;inlier_fraction:number}[];physical_authority:false}|null;
  physical_authority:false;world_registration_verified:false;
}
export type AlignmentAction={action:'hide'|'cancel';request_id:string}|{action:'show';request_id:string;review_digest:string}|{
  action:'check';request_id:string;expected_scene_revision:string;source:'CURRENT'|'SAVED';robot_id:string;operation_id:string;
  start_sequence:number;initial_pose:[number,number,number];reference_id:string;reference_length_m:number;
  reference_basis:'SIM_ONLY'|'OPERATOR_REFERENCE';height_m:number};

export function EnvironmentAlignment({api,revision,disabled=false}:{api:TwinPulseApi;revision:string;disabled?:boolean}){
  const [state,setState]=useState<AlignmentState|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const [source,setSource]=useState<'CURRENT'|'SAVED'>('CURRENT'),[robot,setRobot]=useState(''),[robots,setRobots]=useState<{robot_id:string;label:string;kind:string}[]>([]);
  const [operation,setOperation]=useState(''),[sequence,setSequence]=useState('0'),[pose,setPose]=useState(['','','0']);
  const [ref,setRef]=useState(''),[length,setLength]=useState(''),[basis,setBasis]=useState<'SIM_ONLY'|'OPERATOR_REFERENCE'>('OPERATOR_REFERENCE');
  const [height,setHeight]=useState('0.182');const alive=useRef(true),lock=useRef(false),generation=useRef(0),context=api.context;
  useEffect(()=>{alive.current=true;const epoch=++generation.current;let reading=false;const current=()=>alive.current&&generation.current===epoch;
    setState(null);setRobots([]);setError('');setBusy(false);lock.current=false;
    const load=async()=>{if(reading||lock.current)return;reading=true;
      try{const next=await api.alignment();if(current())setState(next);}catch(e){if(current())setError(e instanceof Error?e.message:String(e));}finally{reading=false;}};
    void load();void api.robotFleet().then(v=>{if(current())setRobots(v.robots.map(r=>({robot_id:r.robot_id,label:r.label,kind:r.kind})));}).catch(()=>{});
    const timer=setInterval(()=>void load(),1000);return()=>{alive.current=false;++generation.current;clearInterval(timer);};
  },[api,context,revision]);
  const perform=async(body:AlignmentAction)=>{if(lock.current)return;const epoch=generation.current;const current=()=>alive.current&&generation.current===epoch;lock.current=true;setBusy(true);setError('');
    try{const next=await api.alignmentAction(body);if(current())setState(next);}catch(e){if(current())setError(e instanceof Error?e.message:String(e));}
    finally{if(current()){lock.current=false;setBusy(false);}}};
  const check=()=>{const nums=pose.map(Number),span=Number(length),z=Number(height),seq=Number(sequence);
    if(pose.some(s=>!s.trim())||!length.trim()||!height.trim()||!nums.every(Number.isFinite)||!Number.isFinite(span)||!Number.isFinite(z)||!Number.isInteger(seq)||seq<0){setError('Enter a finite pose, reference span and height.');return;}
    void perform({action:'check',request_id:crypto.randomUUID(),expected_scene_revision:revision,source,robot_id:robot,operation_id:operation,
      start_sequence:seq,initial_pose:nums as [number,number,number],reference_id:ref,reference_length_m:span,reference_basis:basis,height_m:z});};
  const running=state?.job&&['CHECKING','TRACKING'].includes(state.job.status);
  return <section aria-label="Scan alignment review" className="environment-alignment">
    <p>Set an approximate body pose once. Check fixed wall geometry against separate scan returns and frames. This review grants no driving permission.</p>
    {error&&<p role="alert">{error}</p>}
    <p role="status">{state?.job?`Alignment: ${state.job.status}${state.job.reason?' · '+state.job.reason:''}`:'No alignment checked.'}</p>
    <fieldset disabled={disabled||busy||!!running}><legend>Initial alignment</legend>
      <label className="library-field">Scan source<select aria-label="Alignment scan source" value={source} onChange={e=>setSource(e.target.value as typeof source)}>
        <option value="CURRENT">Current connected sensor</option><option value="SAVED">Closed recording</option></select></label>
      {source==='CURRENT'?<label className="library-field">Robot<select aria-label="Alignment robot" value={robot} onChange={e=>setRobot(e.target.value)}><option value="">Choose a robot…</option>
        {robots.map(r=><option key={r.robot_id} value={r.robot_id}>{r.label} · {r.kind}</option>)}</select></label>:<>
        <label className="library-field">Operation ID<input aria-label="Alignment operation ID" value={operation} onChange={e=>setOperation(e.target.value)} maxLength={32}/></label>
        <label className="library-field">First frame sequence<input aria-label="Alignment first sequence" type="number" min="0" value={sequence} onChange={e=>setSequence(e.target.value)}/></label>
        <small>Uses the first three complete valid rings at or after this sequence. Original receipt and segment hashes are checked. A saved scan is not a live sensor.</small></>}
      <div className="library-position">{['X (m)','Y (m)','Yaw (rad)'].map((name,i)=><label key={name}>{name}<input aria-label={'Alignment '+name} type="number" step="any" value={pose[i]} onChange={e=>setPose(v=>v.map((n,j)=>i===j?e.target.value:n))}/></label>)}</div>
      <label className="library-field">Reference wall span<select aria-label="Alignment reference wall" value={ref} onChange={e=>{setRef(e.target.value);setLength('');}}><option value="">Choose a wall…</option>
        {state?.references.map(r=><option key={r.id} value={r.id}>{r.label} · scene span {r.length_m.toFixed(3)} m</option>)}</select></label>
      {state?.references.find(r=>r.id===ref)&&<small>Exact scene endpoints: {state.references.find(r=>r.id===ref)!.ends_m.map(p=>p.map(n=>n.toFixed(3)).join(', ')).join(' → ')}</small>}
      <label className="library-field">Reported span (m)<input aria-label="Alignment reference length" type="number" step="any" min="0.3" value={length} onChange={e=>setLength(e.target.value)}/></label>
      <label className="library-field">Reference basis<select aria-label="Alignment reference basis" value={basis} onChange={e=>setBasis(e.target.value as typeof basis)}>
        <option value="OPERATOR_REFERENCE">Operator-reported physical reference</option><option value="SIM_ONLY">SIM scale check only</option></select></label>
      <label className="library-field">Sensor plane (m)<input aria-label="Alignment sensor height" type="number" step="any" value={height} onChange={e=>setHeight(e.target.value)}/></label>
      <small>Nominal review height; not measured extrinsics. One consistent span does not certify all room dimensions. A scale mismatch is held; the original geometry is not resized.</small>
      <button type="button" disabled={!ref||!length||source==='CURRENT'&&!robot||source==='SAVED'&&!operation} onClick={check}>Check alignment</button>
    </fieldset>
    <div className="action-row"><button disabled={busy||!state?.review||state.review.status!=='GEOMETRIC_REVIEW'||!state.review_digest||state.job?.status==='HELD'||state.job?.status==='CANCELLED'} onClick={()=>void perform({action:'show',request_id:crypto.randomUUID(),review_digest:state!.review_digest!})}>Show aligned scan</button>
      <button disabled={busy} onClick={()=>void perform({action:'hide',request_id:crypto.randomUUID()})}>Hide aligned scan</button>
      <button disabled={busy||!running} onClick={()=>void perform({action:'cancel',request_id:crypto.randomUUID()})}>Stop checking</button></div>
    {state?.review&&<details><summary>Alignment details</summary>
      <p>Reference: {state.review.reference.status} · ratio {state.review.reference.ratio.toFixed(4)}</p>
      <p>Geometric review: {state.review.status} · held-out mean {state.review.match.validation.mean_error_m.toFixed(3)} m · inliers {Math.round(state.review.match.validation.inlier_fraction*100)}%</p>
      {state.review.match.validation.first_hit_mean_error_m!==undefined&&<p>First visible wall: {state.review.match.validation.first_hit_mean_error_m.toFixed(3)} m · inliers {Math.round((state.review.match.validation.first_hit_inlier_fraction??0)*100)}%</p>}
      <p>Review body pose: {state.review.match.body_pose.map(n=>n.toFixed(3)).join(', ')} · {state.review.temporal_validation.length} separate validation frames</p>
      <p>Not surveyed localization, body-motion qualification, free-space proof or navigation approval.</p></details>}
    <small>{state?.visible?'Overlay requested · confirm the fresh Twin frame.':'Overlay hidden.'} Cold reopen restores a review, not live tracking or robot authority.</small>
  </section>;
}
