// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { useEffect, useState } from "react";
import type { TwinPulseApi } from "./api";
import type { ProductState } from "./types";
import type { Operation } from "./engine-contracts";
import {BedroomGoalReview} from './BedroomGoalReview';
import {RoomLocalization} from './RoomLocalization';
import { roomSummary, routeLabel } from './legacyBedroomText';

const objectNames: Record<string, string> = { floor: "Floor", wall_left: "Left wall", wall_right: "Right wall",
  wall_window: "Window wall", bed: "Bed", wardrobe: "Wardrobe", wardrobe_open_door: "Open wardrobe door",
  desk: "Desk", chair: "Chair", fan_boxes: "Fan and boxes", bag: "Bag", left_luggage: "Left-side luggage" };
export interface BedroomReviewState {
  revision: string; scene_revision: string; summary: string; limits: string[];
  objects: { id: string; kind: string; transform: { position_m: number[];rotation_rpy_deg?:number[] }; shape: { dimensions_m: number[] } }[];
  robot_placement: { pose_status: string; position_m: number[]; yaw_deg: number };
  physical_validation: "NOT_RUN"; alignment_verified: false; active_project_changed: false; motion_authorized: false;
}

export interface BedroomMissionResult {
  status:string; scenario:string; revision:string; scene_revision:string; provenance:string;
  physical_validation:'NOT_RUN'; motion_authorized:false; duration_s:number; distance_m:number; command_count:number;
  waypoints:number[][]; events:{t:number;pose_after:number[];proposed:number[];decision:{allowed:boolean;reason:string}}[];
  replan_events?:{t:number;status:string;reason:string;output_zero:boolean;waypoints?:number[][]}[];
}

export interface BedroomComparison {
  revision:string;conditions_revision:string;eligible_for_efficiency_comparison:boolean;
  b_minus_a:{duration_s:number;distance_m:number}|null;
  candidates:{label:string;record:BedroomMissionResult;metrics:{status:string;arrived:boolean;duration_s:number;
    distance_m:number;goal_error_m:number;min_guard_margin_m:number|null;near_guard_samples:number;guard_samples:number;
    guard_denials:number;collision_count:null}}[];
}

export interface BedroomOfflineAcceptance {
  schema:'bedroom-offline-acceptance-1.0';revision:string;scene_revision:string;source_revision:string;
  provenance:'SYNTHETIC_PHOTO_APPROXIMATION';physical_validation:'NOT_RUN';motion_authorized:false;
  robot_connection:false;isaac_run:false;status:'SYNTHETIC_PASS'|'SYNTHETIC_FAIL';
  checks:Record<string,boolean>;records:Record<string,BedroomMissionResult>;comparison:BedroomComparison;
  evaluation:{physical_validation:'NOT_RUN';overall_score:null};
}

export function BedroomTwin({ api, product, refresh, backendReady }: {
  api: TwinPulseApi; product: ProductState; refresh: () => Promise<void>; backendReady: boolean;
}) {
  const [review, setReview] = useState<BedroomReviewState | null>(null);
  const [ack, setAck] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [operation, setOperation] = useState<Operation | null>(null);
  const [mission, setMission] = useState<BedroomMissionResult | null>(null);
  const [frame,setFrame] = useState(0);
  const [playbackTime,setPlaybackTime] = useState(0);
  const [playing,setPlaying] = useState(false);
  const [playbackSpeed,setPlaybackSpeed] = useState(1);
  const [submittedFrame,setSubmittedFrame] = useState<number|null>(null);
  const [comparison,setComparison] = useState<BedroomComparison|null>(null);
  const [offlineAcceptance,setOfflineAcceptance] = useState<BedroomOfflineAcceptance|null>(null);
  const visualReadiness = product.engine_readiness?.bedroom_visual_v1;
  // Build obtains the control lease after click. A missing permission in the
  // current snapshot is therefore requestable, not proof of an absent feature.
  const capable = Boolean(product.engine_connected && product.snapshot &&
    (visualReadiness ? (visualReadiness.ready || visualReadiness.code === "runtime_command_unavailable") :
      product.snapshot.capabilities.includes("bedroom_visual_v1")
      && !["running", "off_route", "unstable", "error", "disconnected", "stage_invalid"].includes(product.snapshot.runtime_state)));
  const readinessReason: Record<string, string> = {
    runtime_disconnected: "Isaac is disconnected.",
    runtime_snapshot_missing: "Current scene state has not been received.",
    runtime_identity_stale: "Isaac session or scene information is stale.",
    capability_unavailable: "This Isaac build cannot display the room.",
    runtime_safety_latched: "Check Isaac safety state first.",
    runtime_command_unavailable: "Build is unavailable with the current scene state or control connection.",
  };
  const current = product.operations.find(item => item.command_id === operation?.command_id) ?? operation;
  const finished = current?.status === "succeeded" && product.engine_connected
    && product.snapshot?.applied_revision === review?.scene_revision;
  const pending = current?.status === "accepted" || current?.status === "running";
  useEffect(()=>{
    if(!playing||!mission||busy||pending)return;
    const duration=mission.events.at(-1)?.t??0;
    const timer=window.setInterval(()=>{
      const next=Math.min(duration,playbackTime+.1*playbackSpeed);
      setPlaybackTime(next);
      setFrame(mission.events.filter(event=>event.t<=next).length);
      if(next>=duration)setPlaying(false);
    },100);
    return ()=>window.clearInterval(timer);
  },[playing,mission,playbackTime,playbackSpeed,busy,pending]);
  async function prepare() {
    setPlaying(false);setPlaybackTime(0);setBusy(true); setAck(false); setReview(null); setOperation(null); setError(null);setMission(null);setComparison(null);setOfflineAcceptance(null);
    try { setReview(await api.prepareBedroom()); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not inspect the room source."); }
    finally { setBusy(false); }
  }
  async function rehearse(scenario:string) {
    if(!review || busy)return;
    setBusy(true);setError(null);setMission(null);setComparison(null);
    setOfflineAcceptance(null);
    setPlaying(false);setPlaybackTime(0);setFrame(0);setSubmittedFrame(null);setOperation(null);
    try{setMission(await api.rehearseBedroom(review.revision,scenario));}
    catch(e){setError(e instanceof Error?e.message:'Offline rehearsal failed. No automatic retry.');}
    finally{setBusy(false);}
  }
  async function runOfflineAcceptance(){
    if(!review||busy)return;
    setBusy(true);setError(null);setMission(null);setComparison(null);setOfflineAcceptance(null);
    setPlaying(false);setPlaybackTime(0);setFrame(0);setSubmittedFrame(null);setOperation(null);
    try{
      const result=await api.offlineBedroomAcceptance(review.revision);
      showOfflineAcceptance(result);
    }catch(e){setError(e instanceof Error?e.message:'The PC synthetic suite failed. No automatic retry.');}
    finally{setBusy(false);}
  }
  function showOfflineAcceptance(result:BedroomOfflineAcceptance){
    setOfflineAcceptance(result);setComparison(result.comparison);setMission(result.records.route);
  }
  async function importOfflineAcceptance(file:File|undefined){
    if(!file||!review||busy)return;
    setBusy(true);setError(null);setOfflineAcceptance(null);setMission(null);setComparison(null);
    setPlaying(false);setPlaybackTime(0);setFrame(0);setSubmittedFrame(null);setOperation(null);
    try{
      if(file.size<1||file.size>4*1024*1024)throw new Error('Saved synthetic record must be between 1 byte and 4 MiB.');
      showOfflineAcceptance(await api.importBedroomOfflineAcceptance(review.revision,await file.text()));
    }catch(e){setError(e instanceof Error?e.message:'Could not reopen the saved synthetic record.');}
    finally{setBusy(false);}
  }
  async function exportOfflineAcceptance(){
    if(!review||!offlineAcceptance||busy)return;
    setBusy(true);setError(null);
    try{
      const data=await api.exportBedroomOfflineAcceptance(review.revision,offlineAcceptance.revision);
      const bytes=new TextEncoder().encode(data.json_text);
      const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');
      if(data.acceptance_revision!==offlineAcceptance.revision||digest!==data.sha256||
          JSON.parse(data.json_text).revision!==offlineAcceptance.revision)throw new Error('The PC synthetic suite record changed. Run it again.');
      const url=URL.createObjectURL(new Blob([bytes],{type:'application/json'}));
      const a=document.createElement('a');a.href=url;a.download=`bedroom-pc-suite-${offlineAcceptance.revision.slice(0,12)}.json`;a.click();
      window.setTimeout(()=>URL.revokeObjectURL(url),1000);
    }catch(e){setError(e instanceof Error?e.message:'Could not save the PC synthetic suite record.');}
    finally{setBusy(false);}
  }
  async function exportMission() {
    if(!mission||!review||busy)return;
    setBusy(true);setError(null);
    try {
      const data=await api.exportBedroomRehearsal(review.revision,mission.scenario,mission.revision);
      const bytes=new TextEncoder().encode(data.json_text);
      const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');
      if(data.record_revision!==mission.revision||digest!==data.sha256||
          JSON.parse(data.json_text).revision!==mission.revision)throw new Error('The synthetic record changed or saved file verification failed.');
      const url=URL.createObjectURL(new Blob([bytes],{type:'application/json'}));
      const a=document.createElement('a');a.href=url;a.download=`bedroom-rehearsal-${mission.revision.slice(0,12)}.json`;a.click();
      window.setTimeout(()=>URL.revokeObjectURL(url),1000);
    }catch(e){setError(e instanceof Error?e.message:'Could not save the synthetic record.');}
    finally{setBusy(false);}
  }
  async function compare(){
    if(!review||busy)return;
    setPlaying(false);setPlaybackTime(0);setBusy(true);setError(null);setComparison(null);setMission(null);setOperation(null);setSubmittedFrame(null);setFrame(0);
    setOfflineAcceptance(null);
    try{setComparison(await api.compareBedroom(review.revision));}
    catch(e){setError(e instanceof Error?e.message:'Same-condition comparison failed. No automatic retry.');}
    finally{setBusy(false);}
  }
  function selectCandidate(record:BedroomMissionResult){
    setPlaying(false);setPlaybackTime(0);setMission(record);setFrame(0);setSubmittedFrame(null);setOperation(null);
  }
  async function exportComparison(){
    if(!comparison||!review||busy)return;
    setBusy(true);setError(null);
    try {
      const data=await api.exportBedroomComparison(review.revision,comparison.revision);
      const bytes=new TextEncoder().encode(data.json_text);
      const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');
      if(data.comparison_revision!==comparison.revision||digest!==data.sha256||
          JSON.parse(data.json_text).revision!==comparison.revision)throw new Error('The comparison record changed or saved file verification failed.');
      const url=URL.createObjectURL(new Blob([bytes],{type:'application/json'}));
      const a=document.createElement('a');a.href=url;a.download=`bedroom-comparison-${comparison.revision.slice(0,12)}.json`;a.click();
      window.setTimeout(()=>URL.revokeObjectURL(url),1000);
    }catch(e){setError(e instanceof Error?e.message:'Could not save the comparison record.');}
    finally{setBusy(false);}
  }
  async function build(replay = false) {
    if (!review || !ack) return;
    if(replay && (!mission || !product.snapshot?.capabilities.includes('bedroom_replay_v1')))return;
    setBusy(true); setError(null); setOperation(null);
    try {
      await api.acquireLease();
      // The production bridge must observe the lease before it advertises Build.
      // Bounded read-only waiting, never an automatic mutation retry.
      let ready = false;
      for (let attempt = 0; attempt < 15; attempt++) {
        const state = await api.productState();
        if (!state.engine_connected) throw new Error("Isaac disconnected. Reconnect before displaying the scene.");
        if (state.lease_owned && (state.engine_readiness?.bedroom_visual_v1?.ready ??
          Boolean(state.snapshot?.capabilities.includes("bedroom_visual_v1")
            && state.snapshot.permitted_commands.includes("build_site_scene")))) { ready = true; break; }
        await new Promise(resolve => window.setTimeout(resolve, 200));
      }
      if (!ready) throw new Error("Isaac scene control is not ready. Check the connection.");
      if(replay && mission){
        setOperation(await api.replayBedroom(review.revision,{scenario:mission.scenario,revision:mission.revision,frame},crypto.randomUUID()));
        setSubmittedFrame(frame);
      }else{setOperation(await api.buildBedroom(review.revision, true, crypto.randomUUID()));setSubmittedFrame(null);}
      await refresh();
    } catch (e) { setAck(false); setError(e instanceof Error ? e.message : "Check the Isaac connection."); }
    finally { setBusy(false); }
  }
  return <section className="panel bedroom-twin" aria-label="Photo-based room Digital Twin">
    <p className="eyebrow">PHOTO → ROOM + BURGER / OFFLINE PREVIEW</p>
    <h2>My room · Burger Digital Twin</h2>
    <p>Uses the saved room photo and existing Burger model. Review without robot power or paid generation.</p>
    <button disabled={!backendReady || busy || pending} onClick={() => void prepare()}>Load saved room and model</button>
    {review && <>
      <h3>{roomSummary(review.summary)}</h3>
      <div className="bedroom-objects" aria-label="Photo-based objects">{review.objects.map(item => <span key={item.id}>{objectNames[item.id] ?? item.id}</span>)}</div>
      <p>Initial layout with +Y toward the window. Furniture geometry is approximate; dimensions, robot pose, and measured coordinate alignment are unverified.</p>
      <label><input type="checkbox" checked={ack} disabled={busy} onChange={e => setAck(e.target.checked)} />
        I understand this is an approximate scene and will replace the TwinPulse area of the current Isaac workspace with this preview.</label>
      <p>Existing project files are preserved. Burger is for display only; no driving or physics simulation starts.</p>
      <button disabled={busy || pending || !ack || !capable} onClick={() => void build()}>Display room + Burger in Isaac</button>
      {!capable && <p role="status">{readinessReason[visualReadiness?.code ?? ""] ?? "An updated Isaac connection is required. The button enables when scene display is ready."}</p>}
      {current && <p role="status">{finished ? "Room + Burger displayed · not physical validation" : current.status === "succeeded" ? "Past display success · current scene unverified" : `Scene request: ${current.status}`}
        {finished && submittedFrame!==null ? ` · Synthetic frame ${submittedFrame} displayed (not continuous playback)` : ''}
        {current.receipt?.message ? ` · ${current.receipt.message}` : ""}</p>}
      <h3>Room Twin mission rehearsal · PC synthetic computation</h3>
      <BedroomGoalReview key={review.revision} api={api} review={review} backendReady={backendReady}/>
      <RoomLocalization key={`localization-${review.revision}`} api={api} review={review} backendReady={backendReady}
        canPreview={capable&&Boolean(product.snapshot?.capabilities.includes('room_scan_replay_v1'))} refresh={refresh}/>
      <p>One button computes multiple movement and rotation decisions. Clearance is checked with synthetic 2D distances from approximate furniture.
        This is not live lidar, physical control, or Isaac physics driving. The bounded detour uses an injected synthetic obstacle and its simulator geometry, not measured free space.</p>
      <div className="native-controls">
        <button disabled={busy||pending} onClick={()=>void runOfflineAcceptance()}>Run complete PC synthetic suite</button>
        <button disabled={busy||pending} onClick={()=>void rehearse('route')}>Run synthetic mission</button>
        <button disabled={busy||pending} onClick={()=>void rehearse('detour')}>Test synthetic stop and detour</button>
        <button disabled={busy||pending} onClick={()=>void rehearse('detour_no_path')}>Test no-path stop</button>
        <button disabled={busy||pending} onClick={()=>void rehearse('blocked')}>Rehearse obstacle stop</button>
        <button disabled={busy||pending} onClick={()=>void rehearse('stale_scan')}>Rehearse stale-sensor stop</button>
        <button disabled={busy||pending} onClick={()=>void compare()}>Compare two routes under identical conditions</button>
      </div>
      <label>Reopen saved PC synthetic suite (read-only, current room source required)
        <input type="file" accept=".json,application/json" disabled={busy||pending}
          onChange={e=>{void importOfflineAcceptance(e.target.files?.[0]);e.target.value='';}} />
      </label>
      {offlineAcceptance&&<div aria-label="PC synthetic suite result">
        <h3>{offlineAcceptance.status} · robot and Isaac not run</h3>
        <p>One local suite covers two route candidates, injected-obstacle stop and detour, no-path stop, and stale-sensor stop. It is not the field qualification or PC-ready verdict.</p>
        <ul>{Object.entries(offlineAcceptance.checks).map(([name,passed])=><li key={name}>{name.replaceAll('_',' ')}: {passed?'PASS':'FAIL'}</li>)}</ul>
        <div className="native-controls">{Object.entries(offlineAcceptance.records).map(([name,record])=><button key={name} disabled={busy||pending}
          onClick={()=>selectCandidate(record)}>Review {name.replaceAll('_',' ')} record</button>)}</div>
        <button disabled={busy} onClick={()=>void exportOfflineAcceptance()}>Save all synthetic records and comparison</button>
      </div>}
      {comparison && <div aria-label="Same-condition synthetic comparison">
        <h3>Same room, start, goal, and control conditions · synthetic comparison</h3>
        <p>Route A uses fixed waypoints; route B heads directly to the goal. This is not automatic optimization or physical driving evaluation. Collisions were not measured.</p>
        <p>Both use the same XY goal and arrival tolerance; final headings may differ.</p>
        <div className="bedroom-objects">{comparison.candidates.map((c,i)=><section key={c.record.revision} aria-label={routeLabel(c.label)}>
          <h4>{routeLabel(c.label)}</h4><p>{c.metrics.status}</p>
          <p>Synthetic {c.metrics.duration_s.toFixed(2)}s · {c.metrics.distance_m.toFixed(3)}m · goal error {c.metrics.goal_error_m.toFixed(3)}m</p>
          <p>Minimum guard margin {c.metrics.min_guard_margin_m===null?'unobserved':`${c.metrics.min_guard_margin_m.toFixed(3)}m`} · Motion denials {c.metrics.guard_denials}</p>
          <p>Samples within 5 cm margin {c.metrics.near_guard_samples}/{c.metrics.guard_samples} · collisions: unmeasured</p>
          <button disabled={busy||pending} onClick={()=>selectCandidate(c.record)}>{i===0?'A':'B'} review record</button>
        </section>)}</div>
        {comparison.eligible_for_efficiency_comparison && comparison.b_minus_a ?
          <p>B − A: Synthetic time {comparison.b_minus_a.duration_s.toFixed(2)}s · distance {comparison.b_minus_a.distance_m.toFixed(3)}m. A negative value means B is smaller; this does not prove physical superiority.</p>:
          <p>Neither route arrived, so no efficiency difference is reported.</p>}
        <p>Guard margin subtracts radius, clearance, and stopping budget from synthetic distance. It is not measured obstacle distance or collision rate.</p>
        <button onClick={exportComparison}>Save comparison and both records as JSON</button>
      </div>}
      {mission && <div aria-label="Synthetic mission result">
        <p role="status">{mission.status} · not physical validation</p>
        {mission.replan_events?.map((event,i)=><p key={`${event.t}-${i}`}>Synthetic obstacle at {event.t.toFixed(2)}s · {event.status} · zero output before planning: {event.output_zero?'yes':'NO'}
          {event.waypoints?` · ${event.waypoints.length} candidate waypoints`:''}. No measured lidar map or real clearance claim.</p>)}
        <p>Synthetic time {mission.duration_s.toFixed(2)}s · integrated distance {mission.distance_m.toFixed(3)}m · decisions {mission.command_count}</p>
        <svg role="img" aria-label="Synthetic XY path · not Isaac playback" viewBox="-140 -210 280 420" style={{maxHeight:300,width:'100%',background:'#101923'}}>
          {review.objects.filter(o=>o.kind!=='floor').map(o=><g key={o.id} transform={`translate(${o.transform.position_m[0]*100} ${-o.transform.position_m[1]*100}) rotate(${-(o.transform.rotation_rpy_deg?.[2]??0)})`}>
            <title>{objectNames[o.id]??o.id} · approximate geometry</title><rect x={-o.shape.dimensions_m[0]*50} y={-o.shape.dimensions_m[1]*50}
              width={o.shape.dimensions_m[0]*100} height={o.shape.dimensions_m[1]*100} fill="#56677c" stroke="#8193a9" strokeWidth=".7"/>
          </g>)}
          <polyline points={mission.events.slice(0,frame).map(e=>`${e.pose_after[0]*100},${-e.pose_after[1]*100}`).join(' ')} fill="none" stroke="#65d6ba" strokeWidth="2"/>
          {frame>0&&mission.events[frame-1]&&<circle cx={mission.events[frame-1].pose_after[0]*100} cy={-mission.events[frame-1].pose_after[1]*100} r="4" fill="#f9dd79"/>}
          {mission.waypoints.map((p,i)=><circle key={i} cx={p[0]*100} cy={-p[1]*100} r="3" fill="#ffc66d"/>)}
        </svg>
        <p>Green: synthetic path · orange: goal. Furniture dimensions, robot pose, measured alignment, and actual stopping are unverified.</p>
        <button onClick={exportMission}>Save synthetic commands and observations as JSON</button>
        <h3>Review 3D record frame · not physical driving</h3>
        <p>Frame 0 is the starting pose; later frames are synthetic poses after each command. Play, pause, and seek animate only this local 2D preview. Displaying one selected frame in Isaac still requires a separate click; playback sends no engine or robot commands.</p>
        <div className="native-controls" aria-label="Synthetic timeline controls">
          <button disabled={busy||pending||mission.events.length===0} onClick={()=>{if(frame>=mission.events.length){setFrame(0);setPlaybackTime(0);}setPlaying(value=>!value);}}>{playing?'Pause replay':'Play replay'}</button>
          <button disabled={busy||pending} onClick={()=>{setPlaying(false);setFrame(0);setPlaybackTime(0);}}>Restart replay</button>
          <label>Playback speed <select aria-label="Synthetic replay speed" value={playbackSpeed} onChange={e=>setPlaybackSpeed(Number(e.target.value))}>
            <option value={0.5}>0.5×</option><option value={1}>1×</option><option value={2}>2×</option><option value={4}>4×</option>
          </select></label>
        </div>
        <label>Synthetic record frame {frame} / {mission.events.length}
          <input aria-label="Synthetic record frame" type="range" min={0} max={mission.events.length} value={frame} disabled={busy||pending}
            onChange={e=>{const next=Number(e.target.value);setPlaying(false);setFrame(next);setPlaybackTime(next?mission.events[next-1].t:0);}}/></label>
        {frame>0 && mission.events[frame-1] && <p>Command time {mission.events[frame-1].t.toFixed(2)}s · proposed {mission.events[frame-1].proposed.join(' / ')} · decision {mission.events[frame-1].decision.reason}</p>}
        <button disabled={busy||pending||!ack||!capable||!product.snapshot?.capabilities.includes('bedroom_replay_v1')}
          onClick={()=>void build(true)}>Display selected record in Isaac</button>
      </div>}
    </>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
