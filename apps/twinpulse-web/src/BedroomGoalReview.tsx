// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {useRef,useState} from 'react';
import type {TwinPulseApi} from './api';
import type {BedroomReviewState} from './BedroomTwin';

export interface GeometryEvidence {
  revision:string;model_commit:string;base_link_to_scan_xyz_m:number[];wheel_separation_m:number;
  wheel_radius_m:number;collision_aabb_base_link_m:number[][];retained_guard_radius_m:number;
  saved_scan:{frames:number;boot_id:string};missing:string[];
}
export interface GoalPreview {
  status:string;twin_goal_xy_m:number[];odom_goal_candidate_m:number[]|null;
  max_residual_m?:number;boot_id?:string;motion_authorized:false;alignment_verified:false;
}
const missing:Record<string,string>={
  AS_BUILT_SENSOR_POSE_AND_FOOTPRINT:'Verify the as-built sensor pose and robot footprint',
  NATIVE_ANGLE_TO_ROS_SCAN_CONVENTION:'Verify saved native scan angles against ROS direction and rotation sign',
  SAME_TIME_ODOM_AND_TF:'Obtain odom pose and sensor TF from the same time',
  METRIC_TWIN_ODOM_CORRESPONDENCES:'Obtain measured metric correspondences between room Twin and odom',
  CURRENT_BOOT_AND_DEPLOYMENT:'Bind evidence to the current boot and deployment'};

export function BedroomGoalReview({api,review,backendReady}:{api:TwinPulseApi;review:BedroomReviewState;backendReady:boolean}){
  const [evidence,setEvidence]=useState<GeometryEvidence|null>(null),[goal,setGoal]=useState(['0','0']);
  const [reference,setReference]=useState(''),[result,setResult]=useState<GoalPreview|null>(null);
  const [busy,setBusy]=useState(false),[error,setError]=useState('');const epoch=useRef(0);
  function invalidate(){epoch.current++;setResult(null);setError('');}
  async function inspect(){
    invalidate();setEvidence(null);setBusy(true);
    try{setEvidence(await api.geometryEvidence());}catch{setError('Could not verify the model or saved sensor source.');}
    finally{setBusy(false);}
  }
  async function convert(){
    if(!evidence||busy)return;invalidate();const token=epoch.current;setBusy(true);
    try{
      if(goal.some(v=>!v.trim()||!Number.isFinite(Number(v))))throw Error();
      const candidate=await api.bedroomGoal(review.revision,evidence.revision,goal.map(Number),reference.trim()?JSON.parse(reference):null);
      if(token===epoch.current)setResult(candidate);
    }catch{if(token===epoch.current)setError('Invalid coordinates or reference evidence, or the source changed. The previous result is no longer usable.');}
    finally{setBusy(false);}
  }
  return <section aria-label="Room goal and robot coordinate review" className="native-quality room-goal-review">
    <h3>Room goal → robot coordinates · review only</h3>
    <p>Compare official model dimensions with the saved real scan. The window direction in a photo does not establish the odom origin or orientation.</p>
    <button disabled={busy||!backendReady} onClick={()=>void inspect()}>Inspect sensor pose and robot footprint evidence</button>
    {evidence&&<>
      <p>Official model: base_link → base_scan {evidence.base_link_to_scan_xyz_m.map(v=>(v*1000).toFixed(0)).join(' / ')} mm (X / Y / Z).
        Wheel separation {(evidence.wheel_separation_m*1000).toFixed(0)} mm · radius {(evidence.wheel_radius_m*1000).toFixed(0)} mm.</p>
      <p>Nominal collision bounds X {(1000*(evidence.collision_aabb_base_link_m[0][1]-evidence.collision_aabb_base_link_m[0][0])).toFixed(1)} mm × Y {(1000*(evidence.collision_aabb_base_link_m[1][1]-evidence.collision_aabb_base_link_m[1][0])).toFixed(1)} mm.
        Not as-built dimensions · existing guard radius {(evidence.retained_guard_radius_m*1000).toFixed(0)} mm retained.</p>
      <p>Saved real scan: {evidence.saved_scan.frames} frames · boot {evidence.saved_scan.boot_id}. Odom/TF and native scan direction remain unverified.</p>
      <ul>{evidence.missing.map(code=><li key={code}>{missing[code]??code}</li>)}</ul>
      <p>Click a goal on the approximate floor plan or enter XY. +Y points toward the window. This is not obstacle checking or path execution.</p>
      <svg role="img" aria-label="Select approximate room goal" viewBox="-150 -220 300 440" preserveAspectRatio="none" style={{width:'100%',maxWidth:320,aspectRatio:'300 / 440',height:'auto',background:'#101923',cursor:'crosshair'}}
        onClick={event=>{if(busy)return;const rect=event.currentTarget.getBoundingClientRect();
          const x=(event.clientX-rect.left)/rect.width*3-1.5,y=2.2-(event.clientY-rect.top)/rect.height*4.4;
          invalidate();setGoal([x.toFixed(3),y.toFixed(3)]);}}>
        {review.objects.filter(o=>o.kind!=='floor').map(o=><g key={o.id} transform={`translate(${o.transform.position_m[0]*100} ${-o.transform.position_m[1]*100}) rotate(${-(o.transform.rotation_rpy_deg?.[2]??0)})`}>
          <rect x={-o.shape.dimensions_m[0]*50} y={-o.shape.dimensions_m[1]*50} width={o.shape.dimensions_m[0]*100} height={o.shape.dimensions_m[1]*100} fill="#58697e"/>
        </g>)}
        {goal.every(v=>v.trim()&&Number.isFinite(Number(v)))&&<circle cx={Number(goal[0])*100} cy={-Number(goal[1])*100} r="5" fill="#ffc66d"/>}
      </svg>
      <div className="native-controls">{['X','Y'].map((axis,i)=><label key={axis}>Twin goal {axis} (m)
        <input aria-label={`Twin goal ${axis}`} type="number" step="0.01" value={goal[i]} disabled={busy} onChange={e=>{invalidate();setGoal(goal.map((v,j)=>j===i?e.target.value:v));}}/></label>)}</div>
      <details><summary>Enter explicit correspondence evidence · leave blank if unavailable</summary>
        <p>Provide 3–16 non-collinear pairs of the same points in twin_xy_m / odom_xy_m. Do not present estimated photo dimensions or example values as measurements.</p>
        <p>schema: twin-odom-reference-1.0 · scene_revision: {review.scene_revision} · evidence_revision: {evidence.revision} · boot_id · basis: operator_supplied_metric_reference or synthetic_test_fixture · pairs array.</p>
        <textarea aria-label="Twin odom correspondence evidence JSON" value={reference} disabled={busy} onChange={e=>{invalidate();setReference(e.target.value);}} style={{width:'100%',minHeight:100}}/>
      </details>
      <button disabled={busy||!backendReady} onClick={()=>void convert()}>Review goal coordinate mapping · no movement</button>
      {result&&<div role="status">{result.odom_goal_candidate_m?
        `Odom candidate: ${result.odom_goal_candidate_m.map(v=>v.toFixed(3)).join(' / ')} m · residual ${((result.max_residual_m??0)*1000).toFixed(1)} mm · source boot ${result.boot_id}`:
        'Coordinate mapping pending: no measured correspondence evidence, so no robot goal was generated.'}
        <p>A computed candidate is not proof of measured alignment or current-boot validity. It will not be sent to a physical mission.</p></div>}
    </>}
    {error&&<p role="alert">{error}</p>}
  </section>;
}
