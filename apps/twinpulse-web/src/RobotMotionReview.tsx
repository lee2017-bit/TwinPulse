// SPDX-License-Identifier: Apache-2.0
import {useEffect,useRef,useState} from 'react';
import type {TwinPulseApi} from './api';
export type MotionReviewState={job:{job_id:string;operation_id:string;project_id:string;status:string;errors?:string[]}|null;
  review:Record<string,unknown>|null;scope:string;authority_restored:false};
const obj=(v:unknown):Record<string,unknown>=>v!==null&&typeof v==='object'&&!Array.isArray(v)?v as Record<string,unknown>:{};
const text=(v:unknown)=>typeof v==='string'?v.slice(0,180):typeof v==='number'?String(v):'not recorded';
const value=(v:unknown,scale=1)=>typeof v==='number'&&Number.isFinite(v)?(v*scale).toFixed(2):'unknown';
export function RobotMotionReview({api,operation,physical}:{api:TwinPulseApi;operation:string|null;physical:boolean}){
  const [open,setOpen]=useState(false),[state,setState]=useState<MotionReviewState|null>(null),[error,setError]=useState<string|null>(null),[busy,setBusy]=useState(false);
  const generation=useRef(0);const identity=`${api.context}:${operation}`;const current=useRef(identity);current.current=identity;
  useEffect(()=>{generation.current++;setState(null);setError(null);setBusy(false);setOpen(false);},[identity]);
  useEffect(()=>{
    if(!open||!physical||!operation)return;let cancelled=false,timer:ReturnType<typeof setTimeout>|undefined;
    const captured=identity;
    async function poll(){try{const result=await api.robotMotionReview(operation!);if(cancelled||current.current!==captured)return;
      setState(result);if(result.job&&['STARTING','RUNNING','CANCEL_REQUESTED','REAPING'].includes(result.job.status))timer=setTimeout(()=>void poll(),1000);
    }catch(e){if(!cancelled&&current.current===captured)setError(e instanceof Error?e.message:'Review is unavailable.');}}
    void poll();return()=>{cancelled=true;if(timer)clearTimeout(timer);};
  },[api,identity,open,physical,operation,busy]);
  async function action(cancel=false){
    if(!operation)return;const captured=identity,token=++generation.current;setBusy(true);setError(null);
    try{const result=await api.robotMotionReviewAction(operation,cancel&&state?.job?{action:'cancel',request_id:crypto.randomUUID(),job_id:state.job.job_id}:{action:'start',request_id:crypto.randomUUID()});
      if(current.current===captured&&generation.current===token)setState(result);
    }catch(e){if(current.current===captured&&generation.current===token)setError(e instanceof Error?e.message:'Review failed.');}
    finally{if(current.current===captured&&generation.current===token)setBusy(false);}
  }
  if(!physical||!operation)return null;
  const running=!!state?.job&&['STARTING','RUNNING','CANCEL_REQUESTED','REAPING'].includes(state.job.status);
  const review=state?.review,rows=Array.isArray(review?.windows)?review.windows.map(obj):[];
  return <details aria-label="Saved motion review" open={open} onToggle={e=>setOpen(e.currentTarget.open)}>
    <summary>Motion review · offline</summary>
    <p>Compare the closed original recording, wheel observations, independent LiDAR fits and same-session zero-output noise. No robot connection or motion is started.</p>
    <button type="button" disabled={busy||running} onClick={()=>void action()}>Analyze recording</button>
    {running&&<button type="button" disabled={busy} onClick={()=>void action(true)}>Cancel analysis</button>}
    {state?.job&&<p role="status">Analysis: {state.job.status}{state.job.errors?.length?` · ${state.job.errors.join(', ')}`:''}</p>}
    {error&&<p role="alert">{error}</p>}
    {review&&<><p>Saved review: {text(review.status)} · Original complete: {String(review.original_complete??'unknown')} · {text(review.original_error)}</p>
      <p>Operation {text(review.operation_id)} · Twin {text(obj(review.source_twin_context).scene_revision)}.</p>
      <small>Historical derived result for receipt SHA {text(review.input_receipt_sha256)}. Opening it does not revalidate current raw files, restore authority or certify chassis movement. Zero-output collection is not proof of physical immobility; observed noise is not a statistical error bound.</small>
      <div className="robot-diagnostics-table"><table aria-label="Command sensor comparison"><thead><tr><th>Command / linkage</th><th>Wheel estimate</th><th>Independent LiDAR</th><th>Matched noise / comparison</th></tr></thead>
        <tbody>{rows.map((row,i)=>{const wheel=obj(row.wheel),scan=obj(row.lidar),noise=obj(row.stationary_baseline);return <tr key={i}>
          <td>{text(row.direction)}<small>Request {text(row.request_id)} · {text(row.linkage)} · {text(row.command_end_reason)}</small></td>
          <td>{value(wheel.centre_m,1000)} mm · {value(wheel.yaw_rad,180/Math.PI)}°<small>{text(wheel.wheel_data_quality)}</small></td>
          <td>{text(scan.status)}<small>{value(scan.translation_m,1000)} mm · {value(scan.yaw_rad,180/Math.PI)}° · residual {value(scan.max_residual_m,1000)} mm · {text(scan.pairs)} adjacent fits</small></td>
          <td>{text(noise.windows)} matched windows<small>{text(row.comparison)} · Body unqualified / unknown</small></td>
        </tr>;})}</tbody></table></div>
      {!rows.length&&<p>No bounded command intervals were available. This is not evidence of no movement.</p>}
      <details><summary>Review identities and exact evidence</summary><pre>{JSON.stringify(review,null,2)}</pre></details>
    </>}
  </details>;
}
