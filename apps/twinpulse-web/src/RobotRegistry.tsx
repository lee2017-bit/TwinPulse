// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {useEffect,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {ApiError,type TwinPulseApi} from './api';
import './api-key-settings.css';
import {RobotBatterySettings,type BatteryDisplayConfig,type BatteryPresets} from './RobotBatterySettings';

export type RobotEndpoint={host:string;user:string;port:number;ros_domain_id:number};
type DiscoveryCandidate={candidate_id:string;transport:'network'|'serial'|'bluetooth';address:string;label:string;identity_verified:false;
  endpoint?:RobotEndpoint;adapter_id?:string|null;hostname?:string;observed_at_utc?:string;remaining_seconds?:number;
  registered_matches?:{id:string;label:string}[]};
export type RobotRegistryState={schema_version:'robot-registry-1.0';revision:number;active_id:string|null;
  robots:{id:string;label:string;adapter_id:string;adapter_version?:string;endpoint:RobotEndpoint;
    discovery_presence?:{state:'recent_address_response'|'not_seen'|'unknown';observed_at_utc?:string;remaining_seconds:number;identity_verified:false};
    connection_state:'unverified'|'verified_observation';motion_authorized:false;battery_display?:BatteryDisplayConfig;battery_display_sha256?:string}[];
  battery_display_presets?:BatteryPresets;
  adapters:{id:string;label:string;supported:boolean}[];
  discovery:{state:'idle'|'running'|'completed'|'failed';run_id?:string;candidates:DiscoveryCandidate[];known_devices?:DiscoveryCandidate[];
    freshness?:'none'|'recent'|'expired';remaining_seconds?:number;finished_at_utc?:string;sources?:Record<string,unknown>};
  connection?:{state?:string;code?:string;message?:string;job_id?:string;finished_at_utc?:string;health_status?:string;sensor_status?:string;diagnostic_code?:string;next_step?:string;
    execution_id?:string;logs_saved?:boolean;scan_count?:number;artifact_id?:string};guide?:Record<string,unknown>;
  observation_history?:{job_id:string;execution_id:string;result_code:string;finished_at_utc:string;scan_count:number}[];
  capabilities?:{registration:boolean;discovery:boolean;local_preparation:boolean;selected_preparation_available?:boolean;read_only_connection:boolean;physical_control:boolean;unavailable_reason:string|null};
  preparation?:{schema_version:'robot-local-preparation-1.0';state:'not_checked'|'ready'|'needs_attention'|'stale';pc_ready:boolean;
    checked_at_utc?:string;instance_id?:string;binding_sha256?:string;registry_revision?:number;connection_verified:false;motion_authorized:false;
    checks:{id:string;state:'ready'|'needs_attention';detail:string;next_step:string}[]}};
const emptyEndpoint:RobotEndpoint={host:'',user:'twinpulse',port:22,ros_domain_id:86};

export function observedBatterySummary(log:Record<string,unknown>){
  const record=log.record&&typeof log.record==='object'?log.record as Record<string,unknown>:{};
  const battery=record.battery&&typeof record.battery==='object'?record.battery as Record<string,unknown>:{};
  const v=battery.voltage_v,p=battery.estimated_percent;
  if(typeof v!=='number'||!Number.isFinite(v))return null;
  const percent=typeof p==='number'&&Number.isFinite(p)&&p>=0&&p<=100?`approximately ${p.toFixed(0)}% (voltage estimate) · `:'';
  return `Battery at observation: ${percent}${v.toFixed(2)} V · historical record, not current charge`;
}

export function RobotRegistry({api,close,runtimeReady}:{api:TwinPulseApi;close:()=>void;runtimeReady:boolean}){
  const [state,setState]=useState<RobotRegistryState|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState<string|null>(null);
  const [pollError,setPollError]=useState<string|null>(null);
  const [label,setLabel]=useState(''),[adapter,setAdapter]=useState('unreviewed'),[endpoint,setEndpoint]=useState<RobotEndpoint>(emptyEndpoint);
  const [manual,setManual]=useState(false),[notice,setNotice]=useState('');
  const [observationLog,setObservationLog]=useState<Record<string,unknown>|null>(null),[logBusy,setLogBusy]=useState(false),[logError,setLogError]=useState<string|null>(null),[logBinding,setLogBinding]=useState<number|null>(null);
  const [logSelection,setLogSelection]=useState<{jobId:string;source:'current'|'saved'}|null>(null);
  const logRequest=useRef(0),logPending=useRef(false);
  const [now,setNow]=useState(()=>performance.now());
  const receivedAt=useRef(performance.now());
  const active=useRef(true),pending=useRef(false),sequence=useRef(0),panel=useRef<HTMLDivElement>(null);
  useEffect(()=>{
    active.current=true;const previous=document.activeElement as HTMLElement|null;panel.current?.focus();
    let closed=false,timer:ReturnType<typeof setTimeout>|undefined;
    const tick=setInterval(()=>setNow(performance.now()),1000);
    const poll=async()=>{
      if(closed||!active.current)return;
      if(!pending.current){const current=++sequence.current,requestedAt=performance.now();
        try{const next=await api.robotRegistry();if(!closed&&active.current&&current===sequence.current){receivedAt.current=requestedAt;setNow(performance.now());setState(next);setPollError(null);}}
        catch{if(!closed&&active.current&&current===sequence.current)setPollError('Could not refresh robot status. The last observation may be stale.');}}
      if(!closed&&active.current)timer=setTimeout(()=>void poll(),1000);
    };
    void poll();return()=>{closed=true;active.current=false;++sequence.current;clearTimeout(timer);clearInterval(tick);previous?.focus();};
  },[api]);
  const action=async(body:object,message:string)=>{
    if(pending.current||!state||!runtimeReady&&(!('action' in body)||body.action!=='set_battery_display'))return false;
    pending.current=true;++sequence.current;setBusy(true);setError(null);setNotice('');
    const requestedAt=performance.now();
    try{const next=await api.updateRobotRegistry({...body,expected_revision:state.revision});
      if(active.current){receivedAt.current=requestedAt;setNow(performance.now());setState(next);setPollError(null);setNotice(message);return true;}}
    catch(caught){if(active.current)setError(`Robot request was not confirmed${caught instanceof ApiError&&/^[a-z0-9_]+$/.test(caught.code)?` (${caught.code})`:''}. Refresh the saved status before retrying.`);}
    finally{pending.current=false;if(active.current)setBusy(false);}
    return false;
  };
  const selected=state?.robots.find(row=>row.id===state.active_id);
  const jobId=state?.connection?.job_id;
  const currentLogSaved=state?.connection?.logs_saved===true;
  const history=state?.observation_history??[];
  const available={jobId,history,currentLogSaved};
  const availableLogs=useRef(available);useLayoutEffect(()=>{availableLogs.current=available;});
  const logAvailable=(selection:NonNullable<typeof logSelection>,values=availableLogs.current)=>selection.source==='current'
    ?values.currentLogSaved&&values.jobId===selection.jobId:values.history.some(row=>row.job_id===selection.jobId);
  const logOwner=useRef({api,context:api.context,robot:state?.active_id,epoch:0});
  const renderedOwner=useMemo(()=>({api,context:api.context,robot:state?.active_id,epoch:logOwner.current.epoch+1}),[api,api.context,state?.active_id]);
  useLayoutEffect(()=>{logOwner.current=renderedOwner;},[renderedOwner]);
  const logEpoch=renderedOwner.epoch;
  const selectionInvalid=!!logSelection&&!logAvailable(logSelection,available);
  // Retire the previous owner before the newly rendered log buttons become
  // interactive, not in a later passive effect that could erase a fresh click.
  useLayoutEffect(()=>{++logRequest.current;logPending.current=false;setObservationLog(null);setLogSelection(null);setLogBinding(null);setLogError(null);setLogBusy(false);},[logEpoch,selectionInvalid]);
  const readLog=async(requestedJob=jobId,source:'current'|'saved'='current')=>{
    if(logPending.current||logBusy||!requestedJob||typeof api.robotObservation!=='function')return;
    const selection={jobId:requestedJob,source};if(!logAvailable(selection))return;
    const request=++logRequest.current,owner=logOwner.current;
    logPending.current=true;
    setLogSelection(selection);setLogBusy(true);setObservationLog(null);setLogError(null);
    try{const value=await api.robotObservation(requestedJob);
      if(active.current&&request===logRequest.current&&logOwner.current===owner&&api.context===owner.context&&logAvailable(selection)){
        if(!value||typeof value!=='object'||Array.isArray(value)||typeof value.job_id==='string'&&value.job_id!==requestedJob)throw new Error('ROBOT_OBSERVATION_INVALID');
        setObservationLog(value);setLogBinding(owner.epoch);
      }}
    catch{if(active.current&&request===logRequest.current&&logOwner.current===owner)setLogError('Connection log could not be read. No connection check was repeated.');}
    finally{if(active.current&&request===logRequest.current&&logOwner.current===owner){logPending.current=false;setLogBusy(false);}}
  };
  const downloadLog=async()=>{
    if(logPending.current||!observationLog||!logSelection||!logAvailable(logSelection)||logBinding!==logEpoch)return;
    const owner=logOwner.current,selection=logSelection,request=++logRequest.current;
    logPending.current=true;setLogBusy(true);setLogError(null);
    const current=()=>active.current&&request===logRequest.current&&logOwner.current===owner&&api.context===owner.context&&logAvailable(selection);
    try{
      if(typeof api.robotObservationExport!=='function')throw new Error('ROBOT_RAW_EXPORT_UNAVAILABLE');
      const value=await api.robotObservationExport(selection.jobId);
      if(!current())return;
      if(value?.schema_version!=='robot-observation-export-1.0'||value.job_id!==selection.jobId||typeof value.json_text!=='string'||
        !/^[a-f0-9]{64}$/.test(value.file_sha256)||!/^[a-f0-9]{64}$/.test(value.export_sha256)||
        typeof observationLog.sha256==='string'&&value.export_sha256!==observationLog.sha256)throw new Error('ROBOT_RAW_EXPORT_INVALID');
      // Never stringify parsed JS numbers: 0.0 -> 0 would invalidate the
      // hash-bound sensor export when it is later imported for refinement.
      const url=URL.createObjectURL(new Blob([value.json_text],{type:'application/json'}));
      const anchor=document.createElement('a');anchor.href=url;anchor.download='twinpulse-observation-'+selection.jobId.replace(/[^a-zA-Z0-9_-]/g,'').slice(0,100)+'.json';anchor.click();
      setTimeout(()=>URL.revokeObjectURL(url),0);
    }catch{if(current())setLogError('The original observation export could not be downloaded. No connection was repeated.');}
    finally{if(current()){logPending.current=false;setLogBusy(false);}}
  };
  const supported=state?.adapters.some(row=>row.id===selected?.adapter_id&&row.supported)??false;
  const connectionAvailable=state?.capabilities?.read_only_connection!==false;
  const preparation=state?.preparation;
  const elapsed=Math.max(0,(now-receivedAt.current)/1000);
  const networkCandidates=state?.discovery.candidates.filter(candidate=>candidate.transport==='network')??[];
  const remainingCandidates=networkCandidates.filter(candidate=>(candidate.remaining_seconds??0)>elapsed);
  const searchRecent=!pollError&&state?.discovery.freshness==='recent'&&(state.discovery.remaining_seconds??0)>elapsed
    &&(!networkCandidates.length||remainingCandidates.length>0);
  const candidates=searchRecent?remainingCandidates:[];
  const knownDevices=[...(state?.discovery.known_devices??[]),...(state?.discovery.candidates.filter(candidate=>candidate.transport!=='network')??[])];
  const presenceText=(row:NonNullable<typeof state>['robots'][number])=>{
    const presence=row.discovery_presence;
    if(!searchRecent||!presence||(presence.remaining_seconds??0)<=elapsed)return 'Discovery status unknown · search to refresh';
    return presence.state==='recent_address_response'?'Service advertisement observed at this address · identity unverified'
      :presence.state==='not_seen'?'Not observed in the latest search · not proof of power-off':'Discovery status unknown · search to refresh';
  };
  const copyCandidate=(candidate:DiscoveryCandidate,network:boolean)=>{
    // Also guard the action itself after a suspended tab resumes, before the next render.
    if(network&&(pollError||state?.discovery.freshness!=='recent'||(candidate.remaining_seconds??0)<=(performance.now()-receivedAt.current)/1000)){
      setNow(performance.now());setNotice('Search result expired or could not be refreshed. Search again before using this address.');return;
    }
    setLabel(candidate.label);setAdapter(candidate.adapter_id??'unreviewed');
    setEndpoint(candidate.endpoint?{...candidate.endpoint}:{...emptyEndpoint});setManual(true);
    setNotice(network?'Candidate copied to registration. Review its SSH address and adapter before saving.'
      :'Remembered device copied to manual registration. Current presence and a supported robot connection are unknown.');
  };
  const valid=label.trim()&&endpoint.host.trim()&&endpoint.user.trim()&&Number.isInteger(endpoint.port)&&endpoint.port>=1&&endpoint.port<=65535&&Number.isInteger(endpoint.ros_domain_id)&&endpoint.ros_domain_id>=0&&endpoint.ros_domain_id<=232;
  return <div className="key-settings-backdrop"><div ref={panel} tabIndex={-1} className="key-settings-panel robot-registry-panel" role="dialog" aria-modal="true" aria-labelledby="robot-registry-title" onKeyDown={event=>{
    if(event.key==='Escape'&&!busy)close();
    if(event.key==='Tab'){
      const elements=Array.from(panel.current?.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),select:not(:disabled),summary')??[]).filter(element=>!element.closest('details:not([open])')||element.tagName==='SUMMARY');
      const first=elements[0],last=elements[elements.length-1];
      if(event.shiftKey&&(document.activeElement===first||document.activeElement===panel.current)){event.preventDefault();last?.focus();}
      if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
    }
  }}><header><h2 id="robot-registry-title">Robots</h2><button disabled={busy} onClick={close}>Close</button></header>
    <p>Choose a robot, check this PC, then request a read-only connection check. Registration and search results do not establish a connection.</p>
    <p>Robot selection → PC check → connection check → observation log. An editable estimated Twin can be created without a scan; sensor correction is a later, separate review.</p>
    {!runtimeReady&&<p role="status">Waiting for launcher readiness · registration and connection checks are paused. Saved observations remain readable. No request will be replayed automatically.</p>}
    {error&&<p role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}
    {pollError&&<p role="alert">{pollError}</p>}
    {!state&&<p>Reading the local robot registry…</p>}
    <details><summary>New robot guide</summary>
      <ol><li>Power on the robot and wait for its network connection. Search observes advertised services on the local network, not every powered device. The robot must advertise a supported service and network discovery must be allowed. If it does not appear, use its known current address; absence is not proof of power-off.</li>
      <li>Register the address, SSH account and port, and ROS domain used by this robot. Select the reviewed adapter for its actual model, then select the saved robot.</li>
      <li>Use <strong>Check PC preparation</strong>. The check reads local file metadata and the selected address entry in known_hosts; it does not connect to the robot.</li>
      <li>The reviewed Burger adapter uses the existing automation key at <code>%USERPROFILE%\.ssh\twinpulse-burger\id_ed25519_automation</code>. Verify the robot fingerprint before adding its address to your OpenSSH known_hosts. Never upload the private key. TwinPulse does not create credentials or accept host keys automatically.</li>
      <li>A connection-enabled build can run <strong>Check connection (read-only)</strong>. This explicitly runs bounded SSH health reads, existing ROS topic observations and the reviewed board-read check. It does not deploy software, start a driver or enable a motor. Confirm the fresh identity, sensor and idle observations before moving on to stationary collection. A saved result is not a permanent live connection.</li>
      <li>Stationary collection checks sensor data only. Room alignment and wall correction require a completed, cleaned-up multi-position survey or map of the same room. Review its alignment in the Twin project before applying a correction. Connection alone does not validate a route or authorize movement.</li></ol>
      <p>Remembered Bluetooth devices and OS-known serial ports are shown separately, not as current search responses. A saved name does not prove power, presence, robot identity or a motor protocol. Unsupported hardware requires an adapter review before use.</p>
      <p><a href="https://emanual.robotis.com/docs/en/platform/turtlebot3/bringup/" target="_blank" rel="noreferrer">ROBOTIS TurtleBot3 setup reference</a> · Use the domain configured for your robot; do not replace it with an example value.</p></details>
    {state&&<>
      <section aria-label="Registered robots"><h3>Registered robots</h3>
        <p>Saved robots remain here when switched off. Registration is not current discovery or connectivity.</p>
        {state.robots.length===0&&<p>No robots registered. Discover devices or enter a robot address below.</p>}
        <label>Active robot<select disabled={busy||!runtimeReady} value={state.active_id??''} onChange={event=>void action({action:'select',id:event.target.value||null},'Active robot selection saved. Connectivity is unverified until checked.')}>
          <option value="">No active robot</option>{state.robots.map(row=><option key={row.id} value={row.id}>{row.label} · {row.endpoint.host}</option>)}</select></label>
        {selected&&<article><strong>{selected.label}</strong><p>{selected.endpoint.user}@{selected.endpoint.host}:{selected.endpoint.port} · ROS domain {selected.endpoint.ros_domain_id}</p>
          <p aria-label="Selected robot discovery status">{presenceText(selected)}</p>
          <p>Adapter: {selected.adapter_id}</p><p>{selected.connection_state==='verified_observation'?'Read-only observation recorded · not a live connection guarantee':'Connection unverified'} · Motion not authorized</p>
          <RobotBatterySettings key={selected.id} config={selected.battery_display} presets={state.battery_display_presets} busy={busy}
            onSave={config=>action({action:'set_battery_display',id:selected.id,config,expected_display_sha256:selected.battery_display_sha256},'Battery display saved. Connection and driving protection are unchanged.')}/>
          <button disabled={busy||!runtimeReady||state.capabilities?.selected_preparation_available===false||state.discovery.state==='running'||state.connection?.state==='running'} onClick={()=>void action({action:'prepare'},'PC preparation checked. Review each result below; no robot connection was opened.')}>Check PC preparation</button>
          <button disabled={busy||!runtimeReady||!supported||state.capabilities?.selected_preparation_available===false||!connectionAvailable||state.connection?.state==='running'} onClick={()=>void action({action:'connect'},'Read-only connection check requested. Wait for the observation result.')}>Check connection (read-only)</button>
        </article>}
        {!connectionAvailable&&<p className="robot-preparation-note">{state.capabilities?.unavailable_reason==='ROBOT_OBSERVATION_OWNER_UNAVAILABLE'
          ?'The read-only robot service could not acquire its local workspace. Close the other robot session normally and restart TwinPulse. Registration and PC preparation remain available.'
          :'This SIM alpha supports registration, discovery and PC preparation. Live robot connection is unavailable in this build. Use a connection-enabled build for the read-only observation step; saved registrations are retained.'}</p>}
        {state.capabilities?.read_only_connection&&state.capabilities.physical_control===false&&<p className="robot-preparation-note">Read-only robot mode: an explicit connection check can collect bounded observations. Deployment, continuous survey collection and motion are unavailable in this build.</p>}
        {selected&&!supported&&<p>This hardware needs a reviewed adapter before a live connection check.</p>}
        {selected&&preparation&&<section aria-label="PC connection preparation" className="robot-preparation-checklist"><h4>PC connection preparation</h4>
          <p role="status">{preparation.state==='not_checked'?'Not checked for this robot':preparation.state==='stale'?'Preparation changed or expired. Check this PC again.':preparation.pc_ready?'PC prerequisites found · robot connection not checked':'Preparation needs attention'}</p>
          {preparation.checked_at_utc&&<small>Checked {new Date(preparation.checked_at_utc).toLocaleString()}</small>}
          <ul>{preparation.checks.map(check=><li key={check.id}><strong>{check.state==='ready'?'✓':'Needs attention'} · {check.detail}</strong>{check.next_step&&<p>{check.next_step}</p>}</li>)}</ul>
        </section>}
        {state.connection&&<p role="status">Connection check: {state.connection.state??'unknown'}{state.connection.code?` · ${state.connection.code}`:''}{state.connection.message?` · ${state.connection.message}`:''}</p>}
        {state.connection?.job_id&&<article aria-label="Read-only connection result"><strong>Observation {state.connection.job_id}</strong>
          {state.connection.finished_at_utc&&<p>Observed {new Date(state.connection.finished_at_utc).toLocaleString()}</p>}
          {state.connection.health_status&&<p>Health: {state.connection.health_status}</p>}{state.connection.sensor_status&&<p>Sensors: {state.connection.sensor_status}</p>}
          {state.connection.diagnostic_code&&<p>{state.connection.diagnostic_code}</p>}{state.connection.next_step&&<p>{state.connection.next_step}</p>}
          {state.connection.execution_id&&<p>Execution: {state.connection.execution_id}</p>}
          {state.connection.logs_saved!==undefined&&<p>{state.connection.logs_saved?'Observation logs saved locally':'Observation log storage not confirmed'}{state.connection.scan_count!==undefined&&` · ${state.connection.scan_count} scan snapshots`}</p>}
          {state.connection.artifact_id&&<p>Observation artifact: {state.connection.artifact_id}</p>}
          <button type="button" disabled={!currentLogSaved||logBusy||typeof api.robotObservation!=='function'} onClick={()=>void readLog()}>View connection log</button>
          {!currentLogSaved&&<p role="status">Waiting for local observation log storage confirmation. Viewing is unavailable until the log is saved; no log request is sent.</p>}
        </article>}
        <details><summary>Saved connection observations</summary>
          <p>Historical local records for the selected robot, not a current connection or fresh sensor check. Viewing a log does not reconnect the robot.</p>
          {history.length===0&&<p>No saved connection observations listed for this robot.</p>}
          {history.map(row=><article key={row.job_id} aria-label={`Saved observation ${row.job_id}`}>
            <strong>Saved observation {row.job_id}</strong><p>Execution: {row.execution_id}</p>
            <p>Recorded {new Date(row.finished_at_utc).toLocaleString()} · {row.result_code} · {row.scan_count} scan snapshots</p>
            <button type="button" disabled={logBusy||typeof api.robotObservation!=='function'} onClick={()=>void readLog(row.job_id,'saved')}>View saved observation log</button>
          </article>)}
        </details>
        {logBusy&&<p role="status">Reading the saved connection observation · read only…</p>}
        {logError&&<p role="alert">{logError}</p>}
        {observationLog&&logSelection&&!selectionInvalid&&logBinding===logEpoch&&<details open><summary>Connection observation log · historical, not motion authority</summary>
            <p>{logSelection.source==='saved'?'Saved':'Selected'} observation: {logSelection.jobId} · Not a current connection guarantee.</p>
            {observedBatterySummary(observationLog)&&<p aria-label="Recorded battery estimate">{observedBatterySummary(observationLog)}</p>}
            <p>Review before sharing. Downloaded obstacle_observation can be imported separately in the Twin's obstacle feedback panel with an explicitly estimated sensor pose.</p>
            <pre>{JSON.stringify(observationLog,null,2).slice(0,20000)}</pre>
            {JSON.stringify(observationLog).length>20000&&<p>Displayed JSON is limited; the download contains the returned observation record.</p>}
            <button type="button" onClick={()=>void downloadLog()} disabled={logBusy}>Download observation JSON</button>
          </details>}
      </section>
      <section aria-label="Robot discovery"><h3>Responded during network search</h3><p>Discovery: {state.discovery.state}</p>
        <p>Only service advertisements received during an explicit search appear here. They do not verify robot identity, an SSH connection or that the device is still powered on.</p>
        {state.discovery.finished_at_utc&&<p>Last search: <time dateTime={state.discovery.finished_at_utc}>{new Date(state.discovery.finished_at_utc).toLocaleString()}</time></p>}
        {Object.entries(state.discovery.sources??{}).map(([name,value])=>{
          const source=value&&typeof value==='object'?value as {state?:unknown}:null;
          const descriptions:Record<string,string>={network:'Network advertisements (mDNS)',serial:'OS-known serial/USB ports (not opened)',bluetooth:'OS-known Bluetooth devices (no pairing or radio scan)'};
          return typeof source?.state==='string'?<p key={name}>{descriptions[name]??name}: {source.state}</p>:null;
        })}
        <button disabled={busy||!runtimeReady||state.discovery.state==='running'} onClick={()=>void action({action:'discover'},'Search requested. Only current network responses are discovery candidates; no connection is opened.')}>Search for robots</button>
        {state.discovery.state==='running'&&<p role="status">Listening for network service advertisements…</p>}
        {state.discovery.state==='failed'&&<p role="alert">Discovery did not complete. Review diagnostics or register a known address manually.</p>}
        {state.discovery.state==='completed'&&!searchRecent&&<p role="status">Search results expired or unavailable. Search again for recent advertisements; saved robots are unchanged.</p>}
        {state.discovery.state==='completed'&&searchRecent&&candidates.length===0&&<p>No network advertisements observed. The robot may be off, not advertising or unreachable. Saved robots and manual connection checks remain available.</p>}
        {candidates.map(candidate=><article key={candidate.candidate_id}><strong>{candidate.registered_matches?.length?candidate.registered_matches.map(row=>row.label).join(' / '):candidate.label}</strong>
          <p>Advertised name: {candidate.label} · {candidate.address}</p>
          <p>Service advertisement observed · {Math.max(0,Math.ceil((candidate.remaining_seconds??0)-elapsed))} s until refresh required · Identity unverified</p>
          {!!candidate.registered_matches?.length&&<p>Saved names match this address and port only; robot identity has not been authenticated.</p>}
          {candidate.registered_matches?.length===1?<button disabled={busy} onClick={()=>{
            if(!pollError&&(candidate.remaining_seconds??0)>(performance.now()-receivedAt.current)/1000)
              void action({action:'select',id:candidate.registered_matches![0].id},'Saved robot selected. Use Check connection for an authenticated observation.');
            else{setNow(performance.now());setNotice('Search result expired. Search again.');}
          }}>Select saved robot</button>:candidate.registered_matches?.length?<p>Select the intended robot from Registered robots above.</p>
            :<button disabled={busy} onClick={()=>copyCandidate(candidate,true)}>Review and register</button>}
        </article>)}
      </section>
      <details><summary>Remembered devices and local ports · {knownDevices.length}</summary>
        <p>Local OS inventory only. These are not current network search results. Bluetooth entries can remain after a device is off or out of range; ports have not been opened. No radio scan, pairing or robot authentication has occurred.</p>
        {knownDevices.map(candidate=><article key={candidate.candidate_id}><strong>{candidate.label}</strong>
          <p>{candidate.transport} · {candidate.address} · Current presence unknown</p>
          <button disabled={busy} onClick={()=>copyCandidate(candidate,false)}>Use in manual registration</button>
        </article>)}
      </details>
      <details open={manual} onToggle={event=>setManual(event.currentTarget.open)}><summary>Manual registration</summary>
        <form onSubmit={event=>{event.preventDefault();void action({action:'register',label:label.trim(),adapter_id:adapter,endpoint},'Robot registered. Select it explicitly and check read-only connectivity.');}}>
          <fieldset disabled={busy||!runtimeReady}><label>Robot label<input required maxLength={80} value={label} onChange={event=>setLabel(event.target.value)}/></label>
          <label>Robot adapter<select value={adapter} onChange={event=>setAdapter(event.target.value)}>{state.adapters.map(row=><option key={row.id} value={row.id}>{row.label}{row.supported?'':' · unsupported / review required'}</option>)}</select></label>
          {adapter==='turtlebot3_burger_v1'&&<p>The reviewed Burger preparation/control path requires SSH user twinpulse, port 22 and ROS domain 86. Read-only diagnostics can check other endpoint settings; preparation will reject unsupported settings.</p>}
          <label>Robot host<input required maxLength={253} placeholder="192.168.1.20 or robot.local" value={endpoint.host} onChange={event=>setEndpoint({...endpoint,host:event.target.value})}/></label>
          <label>SSH user<input required maxLength={64} value={endpoint.user} onChange={event=>setEndpoint({...endpoint,user:event.target.value})}/></label>
          <label>SSH port<input type="number" min={1} max={65535} step={1} value={Number.isNaN(endpoint.port)?'':endpoint.port} onChange={event=>setEndpoint({...endpoint,port:event.target.valueAsNumber})}/></label>
          <label>ROS domain ID<input type="number" min={0} max={232} step={1} value={Number.isNaN(endpoint.ros_domain_id)?'':endpoint.ros_domain_id} onChange={event=>setEndpoint({...endpoint,ros_domain_id:event.target.valueAsNumber})}/></label>
          <button disabled={!valid} type="submit">Register robot</button></fieldset>
        </form>
      </details>
    </>}
  </div></div>;
}
