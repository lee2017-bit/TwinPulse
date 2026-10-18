// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {useEffect,useState} from 'react';
import type {TwinPulseApi} from './api';
import type {ConversationAction,SceneSensorContext,SceneSensorResult,SceneSensorSurvey} from './conversation-types';
import {ObstacleFeedback} from './ObstacleFeedback';

export function SceneSensorFeedback({api,revision,stateSha,enabled,fresh=true,result,review}:{
  api:TwinPulseApi;revision:string;stateSha:string|null;enabled:boolean;fresh?:boolean;result?:SceneSensorResult|null;
  review:(action:ConversationAction)=>void}) {
  const [maps,setMaps]=useState<{map_id:string;revision:string;keyframes:number}[]>([]);
  const [context,setContext]=useState<SceneSensorContext|null>(null);
  const [surveys,setSurveys]=useState<SceneSensorSurvey[]>([]);const [selectedSurvey,setSelectedSurvey]=useState('');
  const [selected,setSelected]=useState('');const [error,setError]=useState<string|null>(null);
  const [loading,setLoading]=useState(false);
  const [catalogBinding,setCatalogBinding]=useState<{api:TwinPulseApi;context:string;revision:string;stateSha:string|null}|null>(null);
  const catalogCurrent=catalogBinding?.api===api&&catalogBinding.context===api.context&&catalogBinding.revision===revision&&catalogBinding.stateSha===stateSha;
  useEffect(()=>{
    let active=true;const apiContext=api.context;
    const owned=()=>active&&api.context===apiContext;
    setContext(null);setCatalogBinding(null);setMaps([]);setSurveys([]);setError(null);
    // Disabled is a real admission state, not just a greyed-out button. Do not
    // race the Build/Run POST with an edit-context read while its ACK is pending.
    if(!enabled){setLoading(false);return()=>{active=false;};}
    setLoading(true);
    void (async()=>{
      if(typeof api.automaticMaps!=='function'||typeof api.sceneSensorSurveys!=='function')
        throw new Error('Saved sensor catalogs are unavailable. Evidence availability is unconfirmed.');
      const [catalog,surveyCatalog]=await Promise.all([api.automaticMaps(),api.sceneSensorSurveys()]);
      if(!owned())return;
      if(!Array.isArray(catalog.maps)||!Array.isArray(surveyCatalog.surveys))
        throw new Error('Saved sensor catalogs are invalid. Evidence availability is unconfirmed.');
      setMaps(catalog.maps);setSurveys(surveyCatalog.surveys);setCatalogBinding({api,context:apiContext,revision,stateSha});
      if(result?.status==='imported'&&catalog.maps.some(m=>m.map_id===result.map_id))setSelected(result.map_id!);
      // Only actual saved evidence needs strict current-scene replay. Two
      // successfully empty catalogs establish absence, never review authority.
      if(catalog.maps.length||surveyCatalog.surveys.length){
        if(typeof api.sceneSensorContext!=='function')throw new Error('Current Twin sensor context is unavailable.');
        const current=await api.sceneSensorContext();if(owned())setContext(current);
      }
    })().catch(e=>{if(owned())setError(e instanceof Error?e.message:'Saved sensor review unavailable.');})
      .finally(()=>{if(owned())setLoading(false);});
    return()=>{active=false;};
  },[api,api.context,revision,stateSha,enabled,result?.map_id,result?.map_revision]);
  const map=maps.find(m=>m.map_id===selected);
  const survey=surveys.find(s=>s.mission_id===selectedSurvey);
  const current=enabled&&fresh&&catalogCurrent&&context?.current_scene_revision===revision&&context.current_state_sha256===stateSha;
  return <section className="chat-question" aria-label="Saved sensor feedback">
    <ObstacleFeedback api={api} revision={revision} stateSha={stateSha} enabled={enabled} fresh={fresh}/>
    <strong>Saved sensor feedback</strong>
    <p>Historical evidence only. One policy question follows; no live sensor, model request or robot command starts.</p>
    <label>Completed survey <select aria-label="Completed survey" value={selectedSurvey} disabled={!enabled||!fresh||loading}
      onChange={e=>setSelectedSurvey(e.target.value)}><option value="">Choose a saved survey</option>
      {surveys.map(s=><option key={s.mission_id} value={s.mission_id}>{s.mission_id} · {s.status} · {s.provenance}</option>)}
    </select></label>
    <button type="button" disabled={!enabled||loading||!current||survey?.status!=='READY'||!survey.report_revision||
      result?.status==='imported'&&result.evidence?.source_job_id===survey.mission_id}
      onClick={()=>{if(survey?.report_revision&&context&&current)review({action:'sensor_import',request_id:crypto.randomUUID(),
        mission_id:survey.mission_id,expected_report_revision:survey.report_revision,expected_scene_revision:context.current_scene_revision,
        expected_state_sha256:context.current_state_sha256});}}>Import saved survey</button>
    {survey&&<p>Saved survey · {survey.status} · {survey.reason}</p>}
    <label>Saved sensor map <select aria-label="Saved sensor map" value={selected} disabled={!enabled||!fresh||loading}
      onChange={e=>setSelected(e.target.value)}><option value="">Choose a saved map</option>
      {maps.map(m=><option key={m.map_id} value={m.map_id}>{m.map_id} · {m.keyframes} views</option>)}
    </select></label>
    <button type="button" disabled={!enabled||loading||!map||!current} onClick={()=>{
      if(map&&context&&current)review({action:'sensor_review',request_id:crypto.randomUUID(),map_id:map.map_id,
        expected_map_revision:map.revision,expected_scene_revision:context.current_scene_revision,
        expected_state_sha256:context.current_state_sha256});
    }}>Review saved sensor feedback</button>
    {loading&&<p role="status">Reading saved sensor catalogs; current Twin binding is checked only for saved evidence…</p>}
    {!enabled&&<p role="status">Saved sensor review is waiting for the current operation to finish. No sensor action has started.</p>}
    {!fresh&&<p role="status" aria-label="Saved sensor feedback availability">Saved sensor feedback is display only while scene observation is stale. Import and review remain locked.</p>}
    {enabled&&catalogCurrent&&!loading&&!error&&maps.length===0&&surveys.length===0&&<div role="status" aria-label="Sensor preparation next steps">
      <p>No saved sensor evidence is available for this project. Photo dimensions and furniture positions remain estimates.</p>
      <p>First robot test: verify the connection and collect a stationary scan with its timestamps, pose and sensor frame. This does not move the robot or prove room alignment.</p>
      <p>Wall correction needs a cleaned, same-room multi-view survey. A stationary scan alone cannot establish that fit; furniture labels and upper supports are not automatically corrected by LiDAR.</p>
      <p>No robot connection, scan or motion starts from this panel.</p>
    </div>}
    {error&&<p role="alert">{error}</p>}
    {result&&<div role="status" aria-label="Saved sensor review result">
      <p>Sensor review · {result.status}{result.reason&&` · ${result.reason}`}</p>
      {result.evidence&&<p>{result.evidence.provenance==='SYNTHETIC_TRANSPORT'?'Explicit synthetic typed sensor fixture — not a real scan':'Recorded historical sensor bytes — not current pose truth'} · map {result.evidence.map_id}</p>}
      {result.policy==='align_only'&&<p>Pose only: geometry, history and Build unchanged.</p>}
      {result.status==='imported'&&<p>Historical map registered. Geometry, history and Build unchanged; review a sensor policy separately.</p>}
      {result.diagnostics&&<div aria-label="Sensor alignment diagnostics">
        <p>Saved views: {result.diagnostics.view_count} · sensor-view span: {result.diagnostics.view_span_m.toFixed(3)} m. This is recorded odometry spread, not independently measured accuracy.</p>
        <p>Structural wall hypotheses only. Furniture correspondence is not implemented; rejected fit alternatives are not the robot pose.</p>
        <details><summary>Fit, held-out residuals and competing hypotheses</summary><pre>{JSON.stringify(result.diagnostics,null,2)}</pre></details>
      </div>}
      <p>No measured floor pose, calibration, physical readiness or motion authority is granted.</p>
      <details><summary>Sensor evidence and current-state binding</summary><pre>{JSON.stringify({context:result.context,evidence:result.evidence,alignment_status:result.alignment_status,geometry_status:result.geometry_status,room_from_map:result.room_from_map,proposals:result.proposals},null,2)}</pre></details>
    </div>}
  </section>;
}
