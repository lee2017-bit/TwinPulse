// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {useEffect,useRef,useState} from 'react';
import type {TwinPulseApi} from './api';
type Arm={state:string;error?:string;distance_m:number;source_elapsed_s:number;pc_runtime_s:number;
  collision_episodes:number;collision_penalty_points:number;score:number;geometry_corrected:boolean;trajectory:number[][]};
export interface ComparisonState {job:null|{job_id:string;state:string;arm:string|null;error?:string;
  report_revision?:string;report_error?:string;result:null|{arms:{baseline:Arm;corrected:Arm};comparable_arrivals:boolean;
  distance_reduction_m:number|null;source_time_reduction_s:number|null;score_change:number}};}
export function AutomaticComparison({api,available,projectId}:{api:TwinPulseApi;available:boolean;projectId:string}){
  const [state,setState]=useState<ComparisonState>({job:null}),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const [x,setX]=useState('0'),[y,setY]=useState('-.6'),[yaw,setYaw]=useState('0'),[gx,setGX]=useState('.15'),[gy,setGY]=useState('-.6');
  const epoch=useRef(0),currentJob=useRef<ComparisonState['job']>(null);currentJob.current=state.job;
  const active=!!state.job&&!['COMPLETED','FAILED','CANCELLED'].includes(state.job.state);
  const awaitingReport=!!state.job&&!state.job.report_revision&&!state.job.report_error;
  async function bounded<T>(value:Promise<T>):Promise<T>{let timer:ReturnType<typeof setTimeout>|undefined;
    try{return await Promise.race([value,new Promise<never>((_,reject)=>{timer=setTimeout(()=>reject(Error('Comparison request timed out. Refresh status; no automatic retry.')),15000);})]);}
    finally{clearTimeout(timer);}}
  useEffect(()=>{const token=++epoch.current;setState({job:null});setBusy(false);setError('');
    if(available&&typeof api.automaticComparisonState==='function')bounded(api.automaticComparisonState()).then(v=>{
      if(epoch.current===token)setState(v);}).catch(e=>{if(epoch.current===token)setError(String(e.message??e));});
    return()=>{epoch.current++;const job=currentJob.current;
      if(job&&!['COMPLETED','FAILED','CANCELLED'].includes(job.state))void api.automaticComparisonStop(job.job_id).catch(()=>{});};
  },[api,projectId]);
  useEffect(()=>{if(!active&&!awaitingReport)return;let pending=false;const token=epoch.current;
    const timer=setInterval(()=>{if(pending)return;pending=true;bounded(api.automaticComparisonState()).then(v=>{
      if(token===epoch.current){setState(v);if(v.job?.error||v.job?.report_error)setError(v.job.error??v.job.report_error??'');}})
      .catch(e=>{if(token===epoch.current)setError(String(e.message??e));}).finally(()=>{pending=false;});},500);
    return()=>clearInterval(timer);},[api,active,awaitingReport]);
  async function action(kind:'start'|'stop'|'refresh'){
    const token=epoch.current;setBusy(true);setError('');
    try{const v=await bounded(kind==='start'?api.automaticComparisonStart([Number(x),Number(y),Number(yaw)],[Number(gx),Number(gy)]):
      kind==='stop'?api.automaticComparisonStop(state.job!.job_id):api.automaticComparisonState());
      if(token===epoch.current){setState(v);if(v.job?.error)setError(v.job.error);}
      else if(kind==='start'&&v.job)void api.automaticComparisonStop(v.job.job_id).catch(()=>{});
    }catch(e){if(token===epoch.current)setError(e instanceof Error?e.message:'Comparison failed');}
    finally{if(token===epoch.current)setBusy(false);}}
  const result=state.job?.result;
  return <section className="native-quality" aria-label="Automatic mission comparison">
    <h3>Same-condition automatic mission comparison</h3>
    <p>Offline synthetic rehearsal only. Two fresh starts use the same assumed room, goal, footprint and dynamics. Baseline aligns without edits; candidate permits bounded wall correction. This does not test your physical room.</p>
    <div className="native-controls">{[['Start X',x,setX],['Start Y',y,setY],['Start yaw (rad)',yaw,setYaw],['Compare goal X',gx,setGX],['Compare goal Y',gy,setGY]].map(([label,value,setter])=>
      <label key={label as string}>{label as string}<input aria-label={label as string} type="number" step=".05" value={value as string} disabled={active||busy}
        onChange={e=>(setter as (v:string)=>void)(e.target.value)}/></label>)}
      <button disabled={!available||busy||active||awaitingReport||typeof api.automaticComparisonStart!=='function'} onClick={()=>void action('start')}>Start offline comparison</button>
      <button disabled={!active} onClick={()=>void action('stop')}>Stop comparison</button>
      <button disabled={busy||typeof api.automaticComparisonState!=='function'} onClick={()=>void action('refresh')}>Refresh comparison</button>
    </div>
    <p role="status" aria-live="polite">{busy?'Processing comparison request…':state.job?.state==='SAVING'?'Saving comparison report…':state.job?`${state.job.state}${state.job.arm?` · ${state.job.arm}`:''}`:'Ready for an explicit offline comparison'}</p>
    {error&&<dialog open role="alertdialog" aria-label="Comparison error"><p>{error}</p><button onClick={()=>setError('')}>Dismiss</button></dialog>}
    {result&&<><table><caption>Executed synthetic missions · no physical validation</caption><thead><tr><th>Policy</th><th>Outcome</th><th>Distance</th><th>Source time</th><th>Collisions</th><th>Score</th><th>Wall edit</th></tr></thead>
      <tbody>{Object.entries(result.arms).map(([key,a])=><tr key={key}><th>{key}</th><td>{a.state}{a.error?` · ${a.error}`:''}</td><td>{a.distance_m.toFixed(3)} m</td>
        <td>{a.source_elapsed_s.toFixed(2)} s</td><td>{a.collision_episodes} (−{a.collision_penalty_points})</td><td>{a.score}</td><td>{a.geometry_corrected?'Derived revision':'No edit'}</td></tr>)}</tbody></table>
      <p>{result.comparable_arrivals?'Both missions arrived; compare measured synthetic outcomes.':'Arrival comparison unavailable: at least one arm failed or stopped. Failure is not improvement.'}</p>
      <svg viewBox="-250 -250 500 500" role="img" aria-label="Comparison executed trajectories" style={{width:'100%',maxWidth:500,background:'#101923'}}>
        {Object.entries(result.arms).map(([key,a])=><polyline key={key} points={a.trajectory.map(p=>`${p[1]*50},${-p[2]*50}`).join(' ')} fill="none" stroke={key==='baseline'?'#e4ab52':'#59ead9'}/>)}</svg>
      <p>Amber: baseline. Teal: corrected policy. Synthetic PC runtime and source-clock time are separate; no faster or safer physical motion is claimed.</p></>}
    {state.job?.report_revision&&<p>Comparison report saved · {state.job.report_revision.slice(0,12)}</p>}
  </section>;
}
