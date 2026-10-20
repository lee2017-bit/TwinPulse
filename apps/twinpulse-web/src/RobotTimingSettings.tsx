// SPDX-License-Identifier: Apache-2.0
import {useEffect,useRef,useState} from 'react';
export type TimingProfile={schema_version:string;robot_id:string;binding_sha256:string;mode:'unmeasured'|'measured_default'|'custom';
  values:Record<string,number>;adaptive:false;qualification:string;
  evidence:{operation_id:string;measurement_sha256:string;algorithm:string;coverage:string}|null};
export type TimingSettings={profile:TimingProfile;profile_sha256:string;apply_policy:string;last_measurement_origin:string|null;
  measurement_operation_id?:string|null;measurement_sha256?:string|null;recommendation_origin?:string|null;recommendation_sha256?:string|null;
  measurement:{duration_s:number;metrics:Record<string,{n:number;invalid:number;mean_ms:number;sample_std_ms:number|null;p99_upper_ms:number;maximum_ms:number}>}|null;
  recommendation:{profile:TimingProfile;capped_fields:string[];invalid_metrics?:string[];coverage:string;warning:string}|null};
export type TimingFields=Record<string,{minimum_ms:number;maximum_ms:number;preset_ms:number;label:string}>;

export function RobotTimingSettings({settings,fields={},runtime,busy,onSave,onImport,onRecalculate,onApply}:{settings?:TimingSettings;fields?:TimingFields;busy:boolean;
  runtime?:{state:string;profile_sha256:string|null;values:Record<string,number>|null;output_guard:{output_timeout_ms:number}|null};
  onSave:(values:Record<string,number>,mode:'custom')=>Promise<boolean>;onImport:(report:unknown)=>Promise<boolean>;
  onRecalculate:()=>Promise<boolean>;onApply:(recommendationSha256:string)=>Promise<boolean>}){
  const [draft,setDraft]=useState<Record<string,string>>({}),[dirty,setDirty]=useState(false),[fileError,setFileError]=useState<string|null>(null);
  const fileInput=useRef<HTMLInputElement>(null),[fileName,setFileName]=useState('');
  const key=settings?.profile_sha256;
  useEffect(()=>{if(settings&&!dirty)setDraft(Object.fromEntries(Object.entries(settings.profile.values).map(([k,v])=>[k,String(v)])));},[key,dirty]);
  if(!settings)return null;
  const values=Object.fromEntries(Object.keys(fields).map(k=>[k,draft[k]?.trim()?Number(draft[k]):NaN]));
  const valid=Object.keys(fields).length>0&&Object.entries(values).every(([k,v])=>Number.isInteger(v)&&v>=fields[k].minimum_ms&&v<=fields[k].maximum_ms)
    &&values.input_ttl_ms>=2*Math.max(values.input_renewal_ms,values.input_window_ms)
    &&values.output_timeout_ms>=values.input_ttl_ms+Math.max(50,values.input_window_ms)
    &&values.operator_presence_ms>=values.input_ttl_ms+values.input_renewal_ms
    &&(!('odom_source_ms' in values)||values.odom_source_ms>=values.odom_interval_ms+50)
    &&(!('tracking_delivery_ms' in values)||values.tracking_delivery_ms>=values.icp_compute_ms+values.input_window_ms);
  return <details className="robot-timing-settings"><summary>Timing settings · {settings.profile.mode==='unmeasured'?'Not measured':settings.profile.mode==='custom'?'Custom':'Measured defaults'}</summary>
    <p>Milliseconds · applies on the next connection. The active session is unchanged.</p>
    <details className="timing-help"><summary>How timing settings work</summary>
    <p>Per-robot milliseconds. Saved values apply on the next explicit connection, never during a hold or task. Original input/sample timestamps are preserved; receiving or retrying does not restart a lifetime.</p>
    <p role="status">{settings.profile.mode==='unmeasured'?'No first measurement yet · engineering presets, not measured defaults. After registration, explicitly Connect in the Twin controls: passive timing starts without motor enable. Disconnect saves the first measured baseline automatically. Prepare/LiDAR adds separate load measurements; unmeasured fields retain presets.':`Saved ${settings.profile.mode} · ${settings.profile.evidence?.coverage??'no measured evidence'}`}</p>
    <p>After the initial calculation, registered values stay unchanged. New measurements are saved only. Click Recalculate parameters to update a recommendation, then Apply recommended values to change the registered values. Neither step changes an active connection.</p>
    <p>Measurement uses descriptive observed tails plus engineering margin, not a Gaussian assumption, manufacturer standard, braking certificate, or guarantee of continuous driving.</p>
    <p>Calculation: round up to 25 ms after max(observed maximum, p99 histogram upper edge) + max(25 ms, 25% of that tail), retaining preset floors. Output adds at least 100 ms beyond input. Missing load/metric coverage stays PROVISIONAL. Measured braking/geometry constraints remain separate and may be stricter; these settings never rewrite their evidence.</p>
    </details>
    <fieldset disabled={busy}>
      <legend>Registered values</legend>
      <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(235px,1fr))',gap:'10px'}}>
        {Object.entries(fields).map(([k,f])=><label key={k}>{f.label} (ms)<input aria-label={`${f.label} (ms)`} type="number" step="1" min={f.minimum_ms} max={f.maximum_ms} value={draft[k]??''}
          onChange={e=>{setDraft({...draft,[k]:e.target.value});setDirty(true);}}/><small>{f.minimum_ms}–{f.maximum_ms} ms</small></label>)}
      </div>
      {!valid&&dirty&&<p role="alert">Enter integer limits in range. Input lifetime must cover two renewal/window periods; output needs at least 50 ms beyond input; presence must cover input plus renewal; odometry freshness needs 50 ms beyond its sample interval. Zero/disabled protection is not allowed.</p>}
      {dirty&&<p>Unsaved changes · the active session is unchanged.</p>}
      <div className="timing-actions">
      <button aria-label="Save timing settings" disabled={!dirty||!valid} onClick={async()=>{if(await onSave(values,'custom'))setDirty(false);}}>Save</button>
      <button aria-label="Cancel timing changes" disabled={!dirty} onClick={()=>{setDirty(false);setDraft(Object.fromEntries(Object.entries(settings.profile.values).map(([k,v])=>[k,String(v)])));}}>Cancel</button>
      <button aria-label="Recalculate parameters" title="Calculate a recommendation from the latest saved measurements. Registered values stay unchanged." disabled={!settings.measurement||!settings.measurement_operation_id} onClick={()=>void onRecalculate()}>Recalculate</button>
      </div>
      {!settings.measurement&&<p>No recorded measurements yet. Recalculation becomes available after a measurement is saved.</p>}
      {settings.recommendation&&<section aria-label="Parameter recommendation">
        <h4>Recommended values</h4>
        <p>{settings.recommendation_origin==='LEGACY_AUTOMATIC'?'Previously calculated recommendation · retained, not automatically refreshed.':'Calculated on request · registered values are unchanged until applied.'} {settings.recommendation.coverage}.</p>
        {settings.recommendation.profile.evidence?.measurement_sha256!==settings.profile.evidence?.measurement_sha256&&<p>The recommendation may use different measurements from the registered profile.</p>}
        {settings.measurement_sha256!==settings.recommendation.profile.evidence?.measurement_sha256&&<p>Newer measurements are available. Recalculate parameters to use them; the displayed recommendation has not changed.</p>}
        <div style={{maxHeight:230,overflow:'auto'}}><table style={{minWidth:0,tableLayout:'fixed'}}><colgroup><col style={{width:'50%'}}/><col style={{width:'25%'}}/><col style={{width:'25%'}}/></colgroup><thead><tr><th>Parameter</th><th>Registered (ms)</th><th>Recommended (ms)</th></tr></thead><tbody>
          {Object.entries(fields).map(([k,f])=><tr key={k}><td>{f.label}</td><td>{settings.profile.values[k]}</td><td>{settings.recommendation!.profile.values[k]}</td></tr>)}
        </tbody></table></div>
        <p>Source operation: {settings.recommendation.profile.evidence?.operation_id}. {settings.recommendation.warning}</p>
        {dirty&&<p>Save or cancel your unsaved edits before applying recommended values.</p>}
        {(!!settings.recommendation.capped_fields.length||!!settings.recommendation.invalid_metrics?.length)&&<p role="alert">This recommendation cannot be applied: a configured bound was exceeded or measurements contain invalid samples.</p>}
      </section>}
      <button aria-label="Apply recommended values" title="Replace registered values with this recommendation for the next connection" disabled={dirty||!settings.recommendation||!settings.recommendation_sha256||!!settings.recommendation.capped_fields.length||!!settings.recommendation.invalid_metrics?.length}
        onClick={async()=>{if(await onApply(settings.recommendation_sha256!))setDirty(false);}}>Apply recommended</button>
      <div className="timing-import"><button type="button" onClick={()=>fileInput.current?.click()} title="Import recorded timing measurements locally; no robot connection">Import measurements</button>
      <small>{fileName||'Local JSON · no robot connection'}</small>
      <input ref={fileInput} hidden aria-label="Import recorded timing measurements (local JSON, no robot connection)" type="file" accept=".json,application/json" onChange={async e=>{
        const file=e.target.files?.[0];if(!file)return;setFileName(file.name);setFileError(null);
        try{if(file.size>262144)throw new Error('size');const report=JSON.parse(await file.text());await onImport(report);}
        catch{setFileError('Could not import this measurement. Use a hash-bound timing export for this same robot and endpoint.');}
      }}/></div>{fileError&&<p role="alert">{fileError}</p>}
    </fieldset>
    <p>Runtime: {runtime?.state??'DISCONNECTED'} · {runtime?.profile_sha256===settings.profile_sha256&&runtime?.output_guard?'saved profile reported':'saved values not confirmed on a live worker'}</p>
    <details className="timing-provenance"><summary>Profile and measurements</summary>
    <p>Saved profile SHA: <code style={{overflowWrap:'anywhere'}}>{settings.profile_sha256}</code>. Runtime readback is separate; an older robot binary cannot claim the new output cutoff was applied.</p>
    <p aria-label="Runtime timing readback">Runtime: {runtime?.state??'DISCONNECTED'} · {runtime?.profile_sha256===settings.profile_sha256?'same saved profile reported':'saved settings not confirmed on a live worker'} · final output {runtime?.output_guard?.output_timeout_ms===undefined?'readback not confirmed':`${runtime.output_guard.output_timeout_ms} ms (last robot report)`}. No movement authority is restored by this display.</p>
    {settings.profile.evidence&&<p>Registered profile source operation {settings.profile.evidence.operation_id} · {settings.profile.evidence.coverage}. Unmeasured fields retain labelled presets.</p>}
    {settings.measurement&&<p>Latest recorded measurement operation {settings.measurement_operation_id??'unknown'} · {settings.last_measurement_origin}. Recording does not recalculate recommendations or change registered values after initialization.</p>}
    {settings.measurement&&<details><summary>Measured timing distribution · {settings.measurement.duration_s.toFixed(1)} seconds</summary>
      <p>Correlated samples; 5 ms histogram upper edges. Short records cannot establish a p99.9 bound or stops per hour. Base, LiDAR and tracking/recording loads stay separate.</p>
      <div style={{overflowX:'auto'}}><table><thead><tr><th>Load / metric</th><th>Samples</th><th>Mean</th><th>Sample SD</th><th>p99 upper</th><th>Max</th><th>Invalid</th></tr></thead><tbody>
        {Object.entries(settings.measurement.metrics).map(([k,r])=><tr key={k}><td>{k}</td><td>{r.n}</td><td>{r.mean_ms.toFixed(1)}</td><td>{r.sample_std_ms?.toFixed(1)??'—'}</td><td>{r.p99_upper_ms}</td><td>{r.maximum_ms.toFixed(1)}</td><td>{r.invalid}</td></tr>)}
      </tbody></table></div></details>}
    </details>
  </details>;
}
