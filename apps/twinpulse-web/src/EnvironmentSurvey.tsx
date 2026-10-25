// SPDX-License-Identifier: Apache-2.0
import {useEffect,useRef,useState} from 'react';
import type {TwinPulseApi} from './api';
import type {SceneEditPreview} from './types';
import type {EnvironmentPhotoProposal} from './environment-types';
interface Residual {candidate_id:string;position_xy_m:number[];observed_extent_xy_m:number[];uncertainty_m:number;return_count:number;view_indices:number[];view_baseline_m:number}
export interface SurveyState {
  context:{scene_revision:string}|null;references:{id:string;label:string;length_m:number}[];
  collections:{task_id:string;state:string;reason:string|null;kind:string;view_count:number;source_captured:boolean}[];
  job:{job_id:string;status:string;reason:string|null}|null;review_digest:string|null;visible:boolean;registration_active:boolean;
  review:{context:{scene_revision:string};status:string;source:string;view_count:number;maximum_view_baseline_m:number;obstacle_candidates:Residual[];physical_authority:false}|null;
  preview?:SceneEditPreview;
}
export type SurveyAction={action:'hide'|'cancel'|'clear_registration';request_id:string}|
  {action:'show'|'use_registration';request_id:string;review_digest:string}|
  {action:'check';request_id:string;expected_scene_revision:string;source:'TASK'|'CURRENT';task_id:string;robot_id:string;
   initial_pose:[number,number,number];reference_id:string;reference_length_m:number;reference_basis:'SIM_ONLY'|'OPERATOR_REFERENCE';height_m:number;compare_current_reviewed:boolean}|
  {action:'preview_obstacle';request_id:string;review_digest:string;candidate_id:string;kind:string;label:string;height_m:number;
   candidate_ref:{job_id:string;candidate_id:string}|null;duplicate_reviewed:true};

export function EnvironmentSurvey({api,revision,photo,onPreview,onInvalidate,disabled=false}:{api:TwinPulseApi;revision:string;photo?:EnvironmentPhotoProposal|null;onPreview:(v:SceneEditPreview)=>void;onInvalidate:()=>void;disabled?:boolean}){
  const [state,setState]=useState<SurveyState|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const [source,setSource]=useState<'TASK'|'CURRENT'>('TASK'),[task,setTask]=useState(''),[robot,setRobot]=useState('');
  const [robots,setRobots]=useState<{robot_id:string;label:string}[]>([]),[pose,setPose]=useState(['','','0']);
  const [reference,setReference]=useState(''),[span,setSpan]=useState(''),[basis,setBasis]=useState<'SIM_ONLY'|'OPERATOR_REFERENCE'>('OPERATOR_REFERENCE');
  const [height,setHeight]=useState('0.182'),[compare,setCompare]=useState(false),[candidate,setCandidate]=useState('');
  const [kind,setKind]=useState('basket'),[label,setLabel]=useState('Reviewed obstacle'),[objectHeight,setObjectHeight]=useState('0.5');
  const [photoId,setPhotoId]=useState(''),[duplicates,setDuplicates]=useState(false);
  const generation=useRef(0),lock=useRef(false),context=api.context;
  const invalidate=useRef(onInvalidate);invalidate.current=onInvalidate;
  useEffect(()=>{invalidate.current();},[candidate,kind,label,objectHeight,photoId,duplicates,state?.review_digest,revision,context]);
  useEffect(()=>{const epoch=++generation.current;let reading=false;setState(null);setError('');setBusy(false);lock.current=false;
    const load=async()=>{if(reading||lock.current)return;reading=true;try{const v=await api.environmentSurvey();if(generation.current===epoch)setState(v);}catch(e){if(generation.current===epoch)setError(String(e));}finally{reading=false;}};
    void load();void api.robotFleet().then(v=>{if(generation.current===epoch)setRobots(v.robots);}).catch(()=>{});
    const timer=setInterval(()=>void load(),1500);return()=>{generation.current++;clearInterval(timer);};
  },[api,context,revision]);
  const act=async(body:SurveyAction)=>{if(lock.current)return;lock.current=true;setBusy(true);setError('');const epoch=generation.current;
    try{const next=await api.environmentSurveyAction(body);if(generation.current===epoch){setState(next);if(next.preview)onPreview(next.preview);}}
    catch(e){if(generation.current===epoch)setError(e instanceof Error?e.message:String(e));}
    finally{if(generation.current===epoch){lock.current=false;setBusy(false);}}};
  const running=state?.job?.status==='CHECKING',ready=state?.review?.status==='GEOMETRIC_REVIEW'&&!!state.review_digest&&state.context?.scene_revision===revision&&state.review.context.scene_revision===revision&&['GEOMETRIC_REVIEW','SAVED'].includes(state.job?.status??'');
  const blocked=disabled||busy||running;
  return <section aria-label="Collected survey review" className="environment-alignment">
    <p>Review saved moving observations in their original odometry frame. Keep the USD structure; review missing obstacles before applying an edit.</p>
    {error&&<p role="alert">{error}</p>}<p role="status">Survey: {state?.job?.status??'not checked'}{state?.job?.reason?' · '+state.job.reason:''}</p>
    <fieldset disabled={blocked}><legend>Survey alignment</legend>
      <label className="library-field">Source<select aria-label="Survey source" value={source} onChange={e=>setSource(e.target.value as typeof source)}><option value="TASK">Saved task collection</option><option value="CURRENT">Current stopped sensor</option></select></label>
      {source==='TASK'?<label className="library-field">Collection<select aria-label="Survey collection" value={task} onChange={e=>setTask(e.target.value)}><option value="">Choose a collection…</option>{state?.collections.map(c=><option key={c.task_id} value={c.task_id} disabled={!c.source_captured||c.view_count<3}>{c.task_id.slice(0,8)} · {c.kind} · {c.view_count} views · {c.state}{!c.source_captured?' · recapture required':''}</option>)}</select></label>:
        <label className="library-field">Robot<select aria-label="Survey robot" value={robot} onChange={e=>setRobot(e.target.value)}><option value="">Choose a robot…</option>{robots.map(r=><option key={r.robot_id} value={r.robot_id}>{r.label}</option>)}</select></label>}
      <div className="library-position">{['X (m)','Y (m)','Yaw (rad)'].map((name,i)=><label key={name}>{name}<input aria-label={'Survey '+name} type="number" step="any" value={pose[i]} onChange={e=>setPose(v=>v.map((n,j)=>i===j?e.target.value:n))}/></label>)}</div>
      <label className="library-field">Reference wall<select aria-label="Survey reference wall" value={reference} onChange={e=>{setReference(e.target.value);setSpan('');}}><option value="">Choose a wall…</option>{state?.references.map(r=><option key={r.id} value={r.id}>{r.label} · {r.length_m.toFixed(3)} m</option>)}</select></label>
      <label className="library-field">Reported span (m)<input aria-label="Survey reference span" type="number" step="any" value={span} onChange={e=>setSpan(e.target.value)}/></label>
      <label className="library-field">Reference basis<select aria-label="Survey reference basis" value={basis} onChange={e=>setBasis(e.target.value as typeof basis)}><option value="OPERATOR_REFERENCE">Operator reference</option><option value="SIM_ONLY">SIM only</option></select></label>
      <label className="library-field">Sensor plane (m)<input aria-label="Survey sensor height" type="number" step="any" value={height} onChange={e=>setHeight(e.target.value)}/></label>
      <label><input type="checkbox" checked={compare} onChange={e=>setCompare(e.target.checked)}/>Compare with the current edited model</label>
      <small>Required if this model differs from the collection. Original data and the previous task outcome remain unchanged.</small>
      <button type="button" disabled={!reference||!span||pose.some(v=>!v.trim())||source==='TASK'&&!task||source==='CURRENT'&&!robot} onClick={()=>{
        const values=[...pose.map(Number),Number(span),Number(height)];if(!values.every(Number.isFinite)){setError('Enter finite pose, span and height.');return;}
        void act({action:'check',request_id:crypto.randomUUID(),expected_scene_revision:revision,source,task_id:task,robot_id:robot,initial_pose:pose.map(Number) as [number,number,number],reference_id:reference,reference_length_m:Number(span),reference_basis:basis,height_m:Number(height),compare_current_reviewed:compare});}}>Check survey</button>
    </fieldset>
    <div className="action-row"><button disabled={!!blocked||!ready} onClick={()=>void act({action:'show',request_id:crypto.randomUUID(),review_digest:state!.review_digest!})}>Show survey</button>
      <button disabled={busy} onClick={()=>void act({action:'hide',request_id:crypto.randomUUID()})}>Hide survey</button>
      <button disabled={busy||!running} onClick={()=>void act({action:'cancel',request_id:crypto.randomUUID()})}>Cancel check</button>
      <button disabled={!!blocked||!ready||state?.review?.source!=='CURRENT'} onClick={()=>void act({action:'use_registration',request_id:crypto.randomUUID(),review_digest:state!.review_digest!})}>Use session alignment</button>
      <button disabled={busy||!state?.registration_active} onClick={()=>void act({action:'clear_registration',request_id:crypto.randomUUID()})}>Clear session alignment</button></div>
    <small>{state?.registration_active?'Session alignment active · wheel-relative estimate.':'No active session alignment.'} No driving permission or calibrated pose is granted. Cold reopen restores review only.</small>
    {state?.review&&<p>{state.review.view_count} original views · baseline {state.review.maximum_view_baseline_m.toFixed(2)} m · {state.review.obstacle_candidates.length} residual candidates. Whole-room coverage remains unverified.</p>}
    <fieldset disabled={!!blocked||!ready||state?.review?.source!=='TASK'}><legend>Missing obstacle</legend>
      <label className="library-field">LiDAR candidate<select aria-label="Survey residual candidate" value={candidate} onChange={e=>{setCandidate(e.target.value);setDuplicates(false);}}><option value="">Choose a candidate…</option>{state?.review?.obstacle_candidates.map(c=><option key={c.candidate_id} value={c.candidate_id}>{c.candidate_id} · {c.return_count} returns / {c.view_indices.length} views</option>)}</select></label>
      <label className="library-field">Photo association<select aria-label="Survey photo association" value={photoId} onChange={e=>{setPhotoId(e.target.value);const c=photo?.candidates.find(c=>c.id===e.target.value);if(c){setKind(c.kind);setLabel(c.label);}setDuplicates(false);}}><option value="">No photo class · manual review</option>{photo?.status==='ready'&&photo.candidates.map(c=><option key={c.id} value={c.id}>{c.label} · {c.kind}</option>)}</select></label>
      <label className="library-field">Kind<input aria-label="Survey obstacle kind" value={kind} onChange={e=>setKind(e.target.value)} disabled={!!photoId}/></label>
      <label className="library-field">Label<input aria-label="Survey obstacle label" value={label} onChange={e=>setLabel(e.target.value)}/></label>
      <label className="library-field">Estimated height (m)<input aria-label="Survey obstacle height" type="number" min="0.05" max="2.5" step="any" value={objectHeight} onChange={e=>setObjectHeight(e.target.value)}/></label>
      <small>XY and visible extent come from residual returns at one sensor plane, not full object dimensions. Photo association and height require operator review.</small>
      <label><input type="checkbox" checked={duplicates} onChange={e=>setDuplicates(e.target.checked)}/>I reviewed the class, extent and possible duplicates</label>
      <button type="button" disabled={!candidate||!duplicates||!objectHeight.trim()} onClick={()=>void act({action:'preview_obstacle',request_id:crypto.randomUUID(),review_digest:state!.review_digest!,candidate_id:candidate,kind,label,height_m:Number(objectHeight),candidate_ref:photoId&&photo?.job_id?{job_id:photo.job_id,candidate_id:photoId}:null,duplicate_reviewed:true})}>Preview missing obstacle</button>
    </fieldset>
  </section>;
}
