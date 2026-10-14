// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {useEffect,useState} from 'react';
import type {TwinPulseApi} from './api';
import type {ConversationAction,SceneSensorContext,SceneSensorResult,SceneSensorSurvey} from './conversation-types';

export function SceneSensorFeedback({api,revision,stateSha,enabled,result,review}:{
  api:TwinPulseApi;revision:string;stateSha:string|null;enabled:boolean;result?:SceneSensorResult|null;
  review:(action:ConversationAction)=>void}) {
  const [maps,setMaps]=useState<{map_id:string;revision:string;keyframes:number}[]>([]);
  const [context,setContext]=useState<SceneSensorContext|null>(null);
  const [surveys,setSurveys]=useState<SceneSensorSurvey[]>([]);const [selectedSurvey,setSelectedSurvey]=useState('');
  const [selected,setSelected]=useState('');const [error,setError]=useState<string|null>(null);
  const [loading,setLoading]=useState(false);
  useEffect(()=>{
    let active=true;
    if(typeof api.automaticMaps!=='function'||typeof api.sceneSensorContext!=='function')return;
    setLoading(true);setContext(null);
    void Promise.all([api.automaticMaps(),api.sceneSensorContext(),typeof api.sceneSensorSurveys==='function'?api.sceneSensorSurveys():Promise.resolve({surveys:[]})]).then(([catalog,current,surveyCatalog])=>{
      if(active){setMaps(catalog.maps);setContext(current);setSurveys(surveyCatalog.surveys);setError(null);
        if(result?.status==='imported'&&catalog.maps.some(m=>m.map_id===result.map_id))setSelected(result.map_id!);}
    }).catch(e=>{if(active)setError(e instanceof Error?e.message:'Saved sensor review unavailable.');})
      .finally(()=>{if(active)setLoading(false);});
    return()=>{active=false;};
  },[api,revision,stateSha,enabled,result?.map_id,result?.map_revision]);
  const map=maps.find(m=>m.map_id===selected);
  const survey=surveys.find(s=>s.mission_id===selectedSurvey);
  const current=context?.current_scene_revision===revision&&context.current_state_sha256===stateSha;
  return <section className="chat-question" aria-label="Saved sensor feedback">
    <strong>Saved sensor feedback</strong>
    <p>Historical evidence only. One policy question follows; no live sensor, model request or robot command starts.</p>
    <label>Completed survey <select aria-label="Completed survey" value={selectedSurvey} disabled={!enabled||loading}
      onChange={e=>setSelectedSurvey(e.target.value)}><option value="">Choose a saved survey</option>
      {surveys.map(s=><option key={s.mission_id} value={s.mission_id}>{s.mission_id} · {s.status} · {s.provenance}</option>)}
    </select></label>
    <button type="button" disabled={!enabled||loading||!current||survey?.status!=='READY'||!survey.report_revision||
      result?.status==='imported'&&result.evidence?.source_job_id===survey.mission_id}
      onClick={()=>{if(survey?.report_revision&&context&&current)review({action:'sensor_import',request_id:crypto.randomUUID(),
        mission_id:survey.mission_id,expected_report_revision:survey.report_revision,expected_scene_revision:context.current_scene_revision,
        expected_state_sha256:context.current_state_sha256});}}>Import saved survey</button>
    {survey&&<p>Saved survey · {survey.status} · {survey.reason}</p>}
    <label>Saved sensor map <select aria-label="Saved sensor map" value={selected} disabled={!enabled||loading}
      onChange={e=>setSelected(e.target.value)}><option value="">Choose a saved map</option>
      {maps.map(m=><option key={m.map_id} value={m.map_id}>{m.map_id} · {m.keyframes} views</option>)}
    </select></label>
    <button type="button" disabled={!enabled||loading||!map||!current} onClick={()=>{
      if(map&&context&&current)review({action:'sensor_review',request_id:crypto.randomUUID(),map_id:map.map_id,
        expected_map_revision:map.revision,expected_scene_revision:context.current_scene_revision,
        expected_state_sha256:context.current_state_sha256});
    }}>Review saved sensor feedback</button>
    {loading&&<p role="status">Reading saved map and current Twin metadata…</p>}
    {error&&<p role="alert">{error}</p>}
    {result&&<div role="status" aria-label="Saved sensor review result">
      <p>Sensor review · {result.status}{result.reason&&` · ${result.reason}`}</p>
      {result.evidence&&<p>{result.evidence.provenance==='SYNTHETIC_TRANSPORT'?'Explicit synthetic typed sensor fixture — not a real scan':'Recorded historical sensor bytes — not current pose truth'} · map {result.evidence.map_id}</p>}
      {result.policy==='align_only'&&<p>Pose only: geometry, history and Build unchanged.</p>}
      {result.status==='imported'&&<p>Historical map registered. Geometry, history and Build unchanged; review a sensor policy separately.</p>}
      <p>No measured floor pose, calibration, physical readiness or motion authority is granted.</p>
      <details><summary>Sensor evidence and current-state binding</summary><pre>{JSON.stringify({context:result.context,evidence:result.evidence,alignment_status:result.alignment_status,geometry_status:result.geometry_status,room_from_map:result.room_from_map,proposals:result.proposals},null,2)}</pre></details>
    </div>}
  </section>;
}
