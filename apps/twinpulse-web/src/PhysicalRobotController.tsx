// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { useEffect, useRef, useState } from 'react';
import type { TwinPulseApi } from './api';
import { driveDirection, driveKeyBlocked } from './driveKeys';
import { SessionHistory } from './SessionHistory';
import type { RobotDiagnosticsState } from './RobotDiagnostics';
import { DriveJoystick } from './DriveJoystick';
import { LidarScanView, type ScanPreview } from './LidarScanView';

export interface PhysicalState {
  state: string; job_id?: string | null; mode?: string; owned?: boolean; busy: boolean;
  sequence?: number; result?: string; reason?: string; cleanup_confirmed?: boolean; voltage_v?: number;
  stop_request?:'finish_stop'|'force_stop'|'close'|null;
  stop_delivery?: 'PIPE_WRITTEN';
  scan_preview?:ScanPreview|null;
  sensor_cleanup_confirmed?:boolean;
  motion_lease_policy?:'fresh-intent-1.0'|'bounded-hold-1.0';
  session_policy?:'until-stop-1.0'|'bounded-60s-1.0';
  manual_speed?:{linear_m_s:number;angular_rad_s:number};
  scan_display_fault?:string|null;
  lidar_result?: {operator_cancelled:boolean;data_quiet_after_stop:boolean;port_restored:boolean;
    stop_write_complete:boolean;physical_rotor_stopped:false};
  real_transport?: boolean;
  physical_verified?: boolean;
  evidence_recovery?:{status:string;job_id:string|null;transfer_only:true;
    receipt?:string|null;reason?:string|null};
  mission_readiness?:{start_available:boolean;basis:string;physical_ready:false};
  mission_scope?:{frame_id:'odom';waypoints:number[][];duration_s:number}|null;
  mission_progress?:{tick:number;status:string;decision:{reason:string;navigation:{pose_xy_yaw:number[]}}}|null;
  session_log_complete?: boolean;
  session_storage?: {accepted:number;saved:number;error:string|null}|null;
  session_evidence?: {pc_received:number;pipe_written:number;robot_accepted:number;robot_published:number;
    count_scope?:'RECENT_MEMORY_WINDOW';total_saved_event_count?:number;
    observations:number;last_observation:{t:number;encoders:number[];torque:boolean;source_age_s:number;voltage_v?:number}|null;
    floor_pose_measured:false;physical_success:null};
  cleanup_stage?: string; cleanup_error?: string;
  last_trial?: Pick<PhysicalState,'stop_assessment'|'stop_diagnostics'|'cleanup_confirmed'|'cleanup_stage'|'cleanup_error'> &
    {status:string;job_id:string;historical:true;boot_id?:string;release_id?:string};
  stop_diagnostics?: {stable_ms: number | null; required_stable_ms: number; window_ms: number; reason: string};
  stop_assessment?: {policy_id:string;status:string;reason:string;checks:Record<string,boolean>;
    metrics:{guard_observation_ms?:number;wheel_travel_mm?:number[];residual_span_mm?:number[];residual_rate_mm_s?:number[]};
    limits:{deceleration_budget_s:number;verification_s:number;wheel_travel_limit_mm:number;residual_rate_limit_mm_s:number}};
}
const descriptions: Record<string,string> = {
  NOT_STARTED:'Physical control locked — connection and stop verification required', STARTING:'Connecting and preparing robot — no movement yet',
  READY:'Robot-side preparation complete', TESTING:'Stop test running — keep watching the robot',
  RELEASING:'Button released — observing Motor OFF and idle state; connection remains open',
  LIDAR_RUNNING:'Physical lidar collection running · maximum 8 seconds', STOPPING:'Stop requested — awaiting physical stop confirmation',
  CONNECTION_LOST:'Connection lost — robot stop state unverified', FAILED:'Operation failed — review details',
  REJECTED:'Robot rejected the operation', FINISHED:'Operation ended', UNAVAILABLE:'Physical connection is unavailable in this mode',
};
const reasons:Record<string,string>={
  PHYSICAL_STOP_NOT_QUALIFIED_FOR_THIS_BOOT_RELEASE:'Manual control is locked because no passing stop test exists for this boot and package release. If the test already ran, review its saved failure. Repeating it or rebooting will not resolve that failure.',
  TRIAL_ALREADY_CONSUMED_REVIEW_REQUIRED:'The test already ran for this boot and release. Review the saved result. Do not reboot or reinstall just to repeat it.',
  STOP_TRAVEL_EXCEEDED:'Wheel travel after stop exceeded the design limit. Review the result without further control.',
  RESIDUAL_MOTION_EXCEEDED:'Wheel position change after the deceleration interval exceeded the design limit.',
  OBSERVATION_WINDOW_INCOMPLETE:'The observation window was too short for the new policy. A past test is not converted to a pass.',
  SENSOR_COVERAGE_INVALID:'Stop measurement samples were insufficient or interrupted. Do not treat this as stopped.',
  OBSERVATION_INTERRUPTED_BY_TORQUE_OFF:'Motor OFF occurred before observation completed. Cleanup confirmation and stopping performance are separate.',
  INPUT_OR_SESSION_TIMEOUT:'Input or session time limit ended the connection. After confirming shutdown, reconnect with step 3 if needed.',
  INPUT_DEADLINE_EXPIRED:'Fresh input did not arrive within 250 ms. Review connection latency and input records.',
  PROTOCOL_DELIVERY_STALLED:'Robot telemetry delivery stalled. Control ended; review protocol delivery timing and final cleanup.',
  PROTOCOL_WRITE_FAILED:'Robot telemetry transport failed. Review the robot original logs and final cleanup before reconnecting.',
  PROTOCOL_QUEUE_FULL:'Robot telemetry queue filled. Control ended rather than silently dropping evidence.',
  PROTOCOL_BYTE_BUDGET:'Robot telemetry queue exceeded its byte budget. Review saved evidence and transport throughput.',
  SESSION_JOURNAL_WRITE_STALLED:'Writing the robot local journal stalled. Review local journal timing and recording storage.',
  HOLD_LIMIT_EXCEEDED:'A continuous input reached the 2-second limit. Press briefly, then release.',
  SESSION_EXPIRED:'The 60-second manual session expired. Confirm shutdown before reconnecting.',
  OPERATOR_PRESENCE_EXPIRED:'Operator heartbeat lost. Control stopped; reconnect explicitly.',
  SESSION_EVENT_BUDGET:'Recording capacity reached. Control stopped; saved evidence is retained.',
  SESSION_LOG_BYTE_BUDGET:'Session log capacity reached. Control stopped; saved evidence is retained.',
  RECORDING_LOG_BUDGET:'Device log capacity reached. Control stopped; saved evidence is retained.',
  RECORDING_DISK_RESERVE:'Insufficient recording space. Control stopped; free space before reconnecting.',
  RELEASE_IDLE_UNCONFIRMED:'Motor OFF and wheel stability were not observed within the post-release limit.',
  RELEASE_TRAVEL_EXCEEDED:'Wheel travel after button release exceeded the limit. Review the session record.',
  RELEASE_SERVICE_UNCONFIRMED:'Stop or Motor OFF response after release was not confirmed.',
  INPUT_CLOSED_OR_OVERFLOW:'Control connection closed or input delivery failed.',
  INPUT_EXPIRED:'Late input was rejected. Confirm stopping before reconnecting.',
  TELEMETRY_STALE:'Sensor freshness is unverified. Review the status check.',
  BATTERY_BUTTON_OR_SOURCE_AGE:'Voltage, board button, or sensor age fell outside allowed conditions.',
  INITIAL_IDLE_UNCONFIRMED:'Motor-disabled and initial idle state were not verified. Review Motor OFF and status results.',
  STOP_READBACK_UNCONFIRMED:'Post-stop status readback failed. Review the independent cleanup check below.',
  MANUAL_SCAN_OR_ODOM_NOT_READY:'The owned LiDAR driver did not provide fresh scan and odometry during the 8-second wheels-disabled warmup. No manual movement started.',
  ISOLATED_SCAN_DRIVER_EARLY_EXIT:'The owned LiDAR driver exited unexpectedly. Driving was stopped; review the saved driver log and final cleanup.',
  ROS_SCAN_STALE_OR_PUBLISHER_UNOWNED:'LiDAR scan became stale or its publisher was not uniquely owned. Driving was stopped; review the saved scan record.',
  SCAN_DRIVER_STOP_UNCONFIRMED:'LiDAR driver or physical sensor-stop cleanup was not confirmed. Do not assume the rotor has stopped.',
  SCAN_ONLY_INPUT_REJECTED:'Scan-only sessions cannot move the robot. The operation ended without enabling driving.',
  SCAN_CANCELLED_BEFORE_READY:'LiDAR preparation was cancelled. Review the final sensor cleanup result.',
};
const results:Record<string,string>={QUALIFIED:'Stop verification passed for this boot and release',SETTLING_FAIL:'Stop stability failed — driving locked',
  STOP_POLICY_FAIL:'Stop criterion failed or lacked samples — driving locked',FINAL_ROS_STOP_UNCONFIRMED:'ROS stop confirmation failed — driving locked',
  PREPARED:'Package prepared — stop test separate',PREPARATION_FAILED:'Package preparation failed',
  LIDAR_DATA_QUIET:'Lidar data reception ended',IDLE_CONFIRMED:'Motor OFF and idle observed',
  FINAL_IDLE_UNCONFIRMED:'Final stop confirmation failed',FAILED:'Operation failed',OPERATOR_STOP:'Operator stop',
  MISSION_ARRIVED:'Mission reported arrival — cleanup confirmation separate',MISSION_CANCELLED:'Mission cancelled',
  COMMAND_SEGMENT_STOPPED:'Stopped after current command segment',FORCE_STOPPED:'Force STOP processed'};
export function PhysicalRobotController({api,backendReady=true,historyReady=backendReady,compact=false,observedRobot=null,localReleaseId=null}:{api:TwinPulseApi;backendReady?:boolean;historyReady?:boolean;compact?:boolean;observedRobot?:RobotDiagnosticsState['record'];localReleaseId?:string|null}) {
  const [state,setState]=useState<PhysicalState>({state:'NOT_STARTED',busy:false});
  const [confirmed,setConfirmed]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const [pressed,setPressed]=useState<string|null>(null);
  const [operationElapsed,setOperationElapsed]=useState(0),[lidarStopping,setLidarStopping]=useState(false);
  const [waypoints,setWaypoints]=useState(''),[duration,setDuration]=useState('15');
  const live=useRef(state), seq=useRef(0), held=useRef<string|null>(null), mounted=useRef(true);
  const pending=useRef(false), failed=useRef(false);
  const approvedSession=useRef(false);
  const qualifiedHere=useRef<PhysicalState['last_trial']>(undefined);
  const [selectedMode,setSelectedMode]=useState('control_scan');
  const [driveMode,setDriveMode]=useState('control_scan');
  const manualReadyAt=useRef<number|null>(null);
  const operationApproved=compact||confirmed;
  const terminalStop=useRef<'finish_stop'|'force_stop'|null>(null);
  const holdStarted=useRef(0), segmentPhase=useRef<'idle'|'moving'|'stopping'|'waiting-ready'>('idle');
  const epoch=useRef(0), starting=useRef(false), requestedJob=useRef<string|null>(null);
  const backend=useRef(backendReady);backend.current=backendReady;
  const panel=useRef<HTMLDivElement>(null);
  function apply(next:PhysicalState,newJob=false) {
    if (!mounted.current || (!newJob && next.job_id!==live.current.job_id)) return;
    if (!newJob && (next.sequence??0)<(live.current.sequence??0))return;
    if(newJob&&next.job_id!==live.current.job_id)manualReadyAt.current=null;
    if(manualReadyAt.current===null&&next.state==='READY'&&next.busy&&next.owned&&
      next.job_id===requestedJob.current&&['control','control_scan'].includes(next.mode??''))manualReadyAt.current=performance.now();
    if(next.result==='QUALIFIED'&&next.physical_verified===true&&next.cleanup_confirmed===true&&next.last_trial?.job_id===next.job_id)
      qualifiedHere.current=next.last_trial;
    live.current=next;setState(next);
  }
  async function input(action:string) {
    const job=live.current.job_id;
    if (!job || !live.current.busy)return;
    const stopping=['close','stop','finish_stop','force_stop'].includes(action);
    if(!stopping&&(!approvedSession.current||!backend.current))return;
    if (failed.current && !stopping)return;
    if(stopping)seq.current=Math.max(seq.current,live.current.sequence??0);
    const n=++seq.current;
    try {apply(await api.physicalInput(job,n,action));}
    catch {
      if(terminalStop.current&&!stopping)return; // Old in-flight watch cannot undo a stop decision.
      if (job!==live.current.job_id || n<seq.current || live.current.state==='FINISHED' || !live.current.busy)return;
      failed.current=true;held.current=null;setPressed(null);
      setError('Input delivery unverified. Control stopped. Do not approach the robot until its stop state is confirmed.');
      if(action!=='close')void input('close');
    }
  }
  function stop(close=false) {
    const alreadyStopping=segmentPhase.current==='stopping'||segmentPhase.current==='waiting-ready';
    segmentPhase.current='idle';
    held.current=null;setPressed(null);
    if(close){
      if(live.current.mode==='lidar'&&live.current.busy)setLidarStopping(true);
      epoch.current++;approvedSession.current=false;failed.current=true;setConfirmed(false);
      // Revoke UI authority immediately, even with no job id while start is pending.
      if(mounted.current)setState({...live.current});
    }
    if(close||!alreadyStopping)void input(close?'close':'stop');
  }
  function requestStop(action:'finish_stop'|'force_stop'){
    if(action==='finish_stop'&&(terminalStop.current||!['control','control_scan','mission'].includes(live.current.mode??'')))return;
    terminalStop.current=action;held.current=null;setPressed(null);
    segmentPhase.current='idle';
    epoch.current++;approvedSession.current=false;failed.current=true;setConfirmed(false);
    if(mounted.current)setState({...live.current});
    void input(action);
  }
  async function closeReturned(next:PhysicalState,id:string){
    // A late response may only close this request's owned job, never resume it.
    if(next.job_id!==id||!next.owned||!next.busy)return;
    const n=Math.max(seq.current,next.sequence??0)+1;seq.current=n;
    try{const closed=await api.physicalInput(id,n,'close');apply(closed);}
    catch{if(mounted.current)setError('Stop request delivery unverified. No automatic resume; check the result.');}
  }
  async function start(mode:string) {
    if(!backend.current||!operationApproved||starting.current||busy||live.current.busy)return;
    if(compact && ((mode==='control'&&!canConnect)||(mode==='control_scan'&&!canScanConnect)||(mode==='scan'&&!scanSourceReady)||(mode==='qualify'&&!canPrepareTest)||(mode==='prepare'&&!canPreparePackage)))return;
    let scope:NonNullable<PhysicalState['mission_scope']>|undefined;
    if(mode==='mission'){
      if(!live.current.mission_readiness?.start_available)return;
      try{
        const points:unknown=JSON.parse(waypoints),seconds=Number(duration);
        if(!Array.isArray(points)||points.length<1||points.length>16||points.some(p=>!Array.isArray(p)||p.length!==2||p.some(v=>typeof v!=='number'||!Number.isFinite(v)||Math.abs(v)>10))
          ||!Number.isFinite(seconds)||seconds<=0||seconds>45)throw Error('invalid scope');
        scope={frame_id:'odom',waypoints:points as number[][],duration_s:seconds};
      }catch{setError('Check mission scope: 1–16 absolute odom XY waypoints, each within ±10 m, and a time limit above 0 and at most 45 seconds.');return;}
    }
    starting.current=true;const context=epoch.current;
    setSelectedMode(mode);
    if(mode==='prepare')qualifiedHere.current=undefined;
    setLidarStopping(false);setOperationElapsed(0);
    setBusy(true);setError('');failed.current=false;terminalStop.current=null;held.current=null;setPressed(null);segmentPhase.current='idle';seq.current=0;
    const requestId=crypto.randomUUID().replaceAll('-','');
    requestedJob.current=requestId;
    approvedSession.current=true;
    try {
      const next=scope?await api.physicalMission(scope,requestId):await api.physicalStart(mode,requestId);
      const valid=mounted.current&&backend.current&&epoch.current===context&&approvedSession.current
        &&next.job_id===requestId&&next.owned===true;
      if(!valid){
        approvedSession.current=false;failed.current=true;
        apply(next,true);await closeReturned(next,requestId);
      }else apply(next,true);
      if(mounted.current)setConfirmed(false);
    } catch {
      approvedSession.current=false;failed.current=true;
      try{const observed=await api.physicalState();apply(observed,true);
        await closeReturned(observed,requestId);}catch{/* no retry or activation */}
      if(mounted.current)setError('Start response unverified. No automatic retry. Refresh results to check whether the operation ended.');
    }
    finally {starting.current=false;if(mounted.current)setBusy(false);}
  }
  useEffect(()=>{
    mounted.current=true;
    // Read saved PC state only. Never approve, start, resume or send watch input.
    if(backendReady)void Promise.resolve().then(()=>api.physicalState()).then(next=>{
      if(!approvedSession.current && live.current.state==='NOT_STARTED')apply(next,true);
    }).catch(()=>{/* Explicit refresh remains available; no automatic retry. */});
    const end=()=>stop(true);
    const hide=()=>{if(document.visibilityState!=='visible')end();};
    window.addEventListener('blur',end);window.addEventListener('pagehide',end);
    document.addEventListener('visibilitychange',hide);
    return()=>{end();mounted.current=false;window.removeEventListener('blur',end);
      window.removeEventListener('pagehide',end);document.removeEventListener('visibilitychange',hide);};
  },[api,backendReady]);
  useEffect(()=>{
    if(!state.busy||!state.owned||requestedJob.current!==state.job_id||!backendReady)return;
    let disposed=false, reading=false;
    const pulse=setInterval(async()=>{
      if(pending.current||failed.current||!approvedSession.current)return;
      pending.current=true;
      try {
        if(live.current.motion_lease_policy!=='fresh-intent-1.0'&&segmentPhase.current==='moving'&&held.current&&performance.now()-holdStarted.current>=1400){
          segmentPhase.current='stopping';
          await input('stop');
          if(segmentPhase.current==='stopping')segmentPhase.current='waiting-ready';
        }else if(segmentPhase.current==='waiting-ready'&&live.current.state==='READY'&&held.current){
          segmentPhase.current='moving';holdStarted.current=performance.now();
          await input(held.current);
        }else await input(segmentPhase.current==='moving'&&live.current.state==='READY'?held.current??'watch':'watch');
      } finally {pending.current=false;}
    },100);
    const poll=setInterval(async()=>{
      if(reading)return; reading=true;
      try {const next=await api.physicalState();if(!disposed)apply(next);}
      catch {if(!disposed){failed.current=true;stop(true);setError('Robot status query failed — no automatic resume.');}}
      finally{reading=false;}
    },200);
    return()=>{disposed=true;clearInterval(pulse);clearInterval(poll);};
  },[api,backendReady,state.busy,state.owned,state.job_id]);
  const enabled=backendReady&&!failed.current&&approvedSession.current&&state.owned===true
    &&requestedJob.current===state.job_id&&['control','control_scan'].includes(state.mode??'')&&state.state==='READY'&&state.busy&&!error;
  const manualRemaining=manualReadyAt.current===null?null:Math.max(0,60-Math.ceil((performance.now()-manualReadyAt.current)/1000));
  const untilStop=state.session_policy==='until-stop-1.0';
  const sessionLabel=untilStop?'Until Stop':`about ${manualRemaining??60}s remaining`;
  useEffect(()=>{if(enabled)panel.current?.focus({preventScroll:true});},[enabled]);
  useEffect(()=>{
    if(!busy&&!state.busy)return;
    const started=performance.now();
    const timer=window.setInterval(()=>setOperationElapsed(Math.floor((performance.now()-started)/1000)),1000);
    return()=>window.clearInterval(timer);
  },[busy,state.busy,state.job_id]);
  function press(action:string){if(enabled && !held.current){held.current=action;setPressed(action);holdStarted.current=performance.now();segmentPhase.current='moving';void input(action);}}
  function steer(action:string){
    if(held.current&&approvedSession.current&&!failed.current&&state.busy){held.current=action;setPressed(action);}
    else press(action);
  }
  const savedTrial=state.last_trial;
  const matchingPass=Boolean(compact&&state.result!=='PREPARED'&&state.mode!=='prepare'&&observedRobot?.boot_id&&observedRobot.release_id&&
    savedTrial?.boot_id===observedRobot.boot_id&&savedTrial.release_id===observedRobot.release_id&&
    savedTrial.status==='QUALIFIED'&&savedTrial.stop_assessment?.status==='PASS'&&savedTrial.cleanup_confirmed===true);
  // A just-completed owned physical trial is fresh for this page; a saved trial
  // after reload needs an independent read-only boot/release match. The robot
  // remains authoritative and rechecks its receipt on every control start.
  const pageTrial=qualifiedHere.current;
  const currentPass=Boolean(compact&&pageTrial?.status==='QUALIFIED'&&pageTrial.cleanup_confirmed&&
    pageTrial.boot_id===observedRobot?.boot_id&&(!savedTrial||savedTrial.status==='QUALIFIED'));
  const canConnect=!compact||matchingPass||currentPass;
  const scanReleaseReady=Boolean(localReleaseId&&(currentPass?pageTrial?.release_id===localReleaseId:
    matchingPass&&observedRobot?.release_id===localReleaseId));
  const canScanConnect=canConnect&&(!compact||scanReleaseReady);
  const scanSourceReady=!compact||Boolean(localReleaseId&&(observedRobot?.release_id===localReleaseId||
    currentPass&&pageTrial?.release_id===localReleaseId));
  const scanSession=['scan','control_scan'].includes(state.mode??'');
  const scanActive=scanSession&&state.busy&&state.state!=='STOPPING';
  const upgradeAvailable=Boolean(compact&&localReleaseId&&observedRobot?.release_id&&observedRobot.release_id!==localReleaseId);
  const hasFailedTrial=Boolean(compact&&observedRobot?.boot_id&&observedRobot.release_id&&
    savedTrial?.boot_id===observedRobot.boot_id&&savedTrial.release_id===observedRobot.release_id&&
    savedTrial.status!=='QUALIFIED');
  const canPreparePackage=!compact||((!canConnect&&!hasFailedTrial||upgradeAvailable&&!scanReleaseReady)&&state.result!=='PREPARED');
  const canPrepareTest=!compact||state.result==='PREPARED';
  const trial=state.stop_assessment||state.stop_diagnostics?state:state.last_trial;
  const assessment=trial?.stop_assessment;
  const history=trial===state.last_trial && !!trial;
  const cleanupFailure=assessment?.status==='PASS' && trial?.cleanup_confirmed===false;
  const next=enabled?state.motion_lease_policy==='fresh-intent-1.0'?'Ready to drive — drag the joystick. Fresh held input keeps moving; release to stop.':
    'Legacy package: movement pauses between bounded segments. Update the package for continuous fresh-input driving.':
    state.state==='RELEASING'?'Direction buttons will reactivate on the same connection after the stop observation completes. No new approval is needed.':
    state.busy?(state.mode==='mission'?'The robot is deciding within the approved mission scope. No approval per direction; cancellation or leaving the window ends the mission.':state.mode==='qualify'&&state.state==='READY'?'Ready. Run the test below while directly watching the robot.':'Waiting for the current operation to finish.'):
    state.result==='PREPARED'?'Package prepared. The physical stop test is the next required step; an older result does not authorize a changed release.':
    cleanupFailure?'Stop metrics passed but final Motor OFF confirmation failed. Review the cleanup error instead of repeating the test.':
    state.result==='QUALIFIED'?'Confirm on-site conditions, then connect manual control.':
    state.reason?(reasons[state.reason]??state.reason):
    'Confirm on-site conditions, then follow the available connection setup action above.';
  const sensorTools=<section className="console-card" aria-label="Sensors and shutdown">
    <div className="console-section-title"><h3>LiDAR / motor</h3><span>Separate session</span></div>
    <div className="console-sensor-buttons">
      <button disabled={!backendReady||!operationApproved||busy||state.busy} onClick={()=>void start('lidar')}>Start lidar · up to 8 seconds</button>
      <button disabled={!state.busy||state.mode!=='lidar'||lidarStopping} onClick={()=>stop(true)}>Stop lidar</button>
    </div>
    {state.mode==='lidar' && <p role="status" className="console-hint">{state.busy ?
      lidarStopping || state.state==='STOPPING' ? state.stop_delivery==='PIPE_WRITTEN' ?
        'Stop request transmitted — waiting for sensor data to end and port restoration. Cleanup can take several seconds.' :
        'Sending LiDAR stop request — waiting for delivery confirmation…' :
      state.state==='LIDAR_RUNNING' ? `LiDAR running · ${operationElapsed}s elapsed` : `Preparing LiDAR · ${operationElapsed}s elapsed` :
      state.lidar_result?.stop_write_complete && state.lidar_result.data_quiet_after_stop && state.lidar_result.port_restored && state.cleanup_confirmed ?
        'LiDAR STOP write confirmed · data quiet · port restored. Physical rotor stop is not measured.' :
        'LiDAR ended without complete stop evidence. Check the result; do not assume the rotor stopped.'}</p>}
    <button className="console-off" disabled={!backendReady||!operationApproved||busy||state.busy} onClick={()=>void start('off')}>Motor OFF · check status</button>
    <p className="console-hint">The native LiDAR-only test cannot run inside another session. Select Drive + LiDAR in Connection setup for simultaneous scan and driving; both resources are stopped together. A fresh scan is not a collision-clearance guarantee.</p>
  </section>;
  const stopControls=<section className="console-card console-stop-controls" aria-label="Stop controls">
      <div className="console-sensor-buttons">
        <button disabled={!state.owned||!state.busy||!['control','control_scan','mission'].includes(state.mode??'')||!!terminalStop.current||state.state==='STOPPING'}
          onClick={()=>requestStop('finish_stop')}>Stop after current command</button>
        <button className="controller-stop" onClick={()=>requestStop('force_stop')}>Force STOP · Esc</button>
      </div>
      <p>Stop cancels new movement input and queued commands, waits only for the current published segment, then stops and closes the connection. Maximum segment: manual 100 ms / mission 50 ms; it does not wait for the full route.</p>
      <p>Force STOP requests stop and Motor OFF without waiting for the remaining segment. It is available even while a stop is pending. Neither mode resumes automatically.</p>
      <p role="status">{state.state==='STOPPING'?(state.stop_request==='finish_stop'?'Waiting for segment end and stop confirmation — use Force STOP if unsafe':'Immediate stop requested — awaiting physical stop confirmation'):!state.busy?'No active control connection — this button alone cannot guarantee a robot stop.':'This is a software stop request. Communication or control failures may prevent delivery; it is not a physical emergency stop.'}</p>
      <p className="console-hint">Load reduction and braking distance for either stop mode are physically unverified. If unsafe, do not delay Force STOP over load concerns.</p>
    </section>;
  return <div ref={panel} className={`physical-console${compact?' is-compact':''}`} aria-label="Physical controller" role="region" tabIndex={0}
    onBlur={e=>{if((approvedSession.current||starting.current)&&!e.currentTarget.contains(e.relatedTarget as Node|null))stop(true);}}
    onKeyDown={e=>{if(e.key==='Escape'){e.preventDefault();e.stopPropagation();requestStop('force_stop');return;}
      if(driveKeyBlocked(e))return;
      const action=driveDirection(e);
      if(action && enabled){e.preventDefault();e.stopPropagation();if(!e.repeat)press(action);}}}
    onKeyUp={e=>{const action=driveDirection(e);if(action && held.current===action){e.preventDefault();e.stopPropagation();stop();}}}>
    <div className={`console-status ${enabled?'is-ready':cleanupFailure||error?'is-warning':''}`}>
      <div><span className="console-kicker">{state.real_transport===false?'TEST DEVICE · not a physical robot':compact?'LAST CONTROL OPERATION':'TWINPULSE / ROBOT CONTROL'}</span>
        <strong role="status">{descriptions[state.state]??'Status needs review'}{state.result?` · ${results[state.result]??state.result}`:''}</strong>
        <p>{compact&&!state.busy&&state.reason==='HOLD_LIMIT_EXCEEDED'?'Previous session hit the 2-second guard. Review the saved result below; the current connection steps are above.':next}</p></div>
      <button className="console-refresh" disabled={!backendReady} onClick={()=>void api.physicalState().then(next=>apply(next,true)).catch(()=>setError('Result query failed — no automatic connection.'))}>Refresh results · read-only</button>
    </div>
    {!compact&&stopControls}
    <div className="console-metrics">
      <div><span>Control connection</span><strong>{enabled?'Input ready':state.busy?'Operation running':'Disconnected'}</strong></div>
      <div><span>{history?'Recent saved test · not live':'Stop metrics'}</span><strong>{assessment?.status==='PASS'?'Passed':assessment?.status??'Not checked'}</strong></div>
      <div><span>Observed voltage for this connection</span><strong>{state.voltage_v!==undefined?`${state.voltage_v.toFixed(2)} V`:'—'}</strong></div>
    </div>
    {!backendReady&&<p role="status">PC connection is not ready, so no new operation can start. Recovery will not resume control automatically.</p>}
    {!compact&&<label className={`operator-confirm ${confirmed?'is-checked':''}`}><input type="checkbox" checked={confirmed} disabled={!backendReady||state.busy||busy} onChange={e=>setConfirmed(e.target.checked)}/>
      <span><strong>I am watching the robot directly</strong><small>I confirmed battery power, a level floor, and at least 30 cm of clearance. I approve the next selected operation.</small></span>
      <span className="confirm-tag">{confirmed?'Confirmed':state.busy?'Operation running':'Selection required'}</span></label>}
    {error&&state.state!=='FINISHED'&&<p role="alert" className="console-error">{error}</p>}
    {!compact&&<section className="console-card" aria-label="Autonomous mission">
      <div className="console-section-title"><h3>Mission-scoped execution</h3><span>{state.mission_readiness?.start_available?'TEST DEVICE · not physical':'Physical mission locked'}</span></div>
      <p>Once mission scope is approved, motion and turns are decided autonomously. The current system stops at obstacles; it does not detour.</p>
      {!state.mission_readiness?.start_available&&<p role="status">Development prerequisites are incomplete: reviewed physical deployment and coordinate calibration are missing. Powering the robot or repeating a stop test will not unlock this.</p>}
      <p className="console-hint">These are absolute odom coordinates (m), not photo or room-Twin coordinates. Room alignment is unverified. Starting below does not install a package or run a stop test automatically.</p>
      <label>Mission waypoints XY (JSON)<textarea aria-label="Mission waypoints XY" placeholder="[[0.08, 0]]" value={waypoints}
        disabled={busy||state.busy||!state.mission_readiness?.start_available}
        onChange={e=>{setWaypoints(e.target.value);setConfirmed(false);}}/></label>
      <label>Mission time limit (seconds)<input aria-label="Mission time limit" type="number" min="0.1" max="45" step="0.1" value={duration}
        disabled={busy||state.busy||!state.mission_readiness?.start_available}
        onChange={e=>{setDuration(e.target.value);setConfirmed(false);}}/></label>
      <div className="console-sensor-buttons">
        <button disabled={!backendReady||!state.mission_readiness?.start_available||!operationApproved||busy||state.busy||!waypoints.trim()}
          onClick={()=>void start('mission')}>Start approved mission</button>
        <button disabled={!state.busy||state.mode!=='mission'} onClick={()=>stop(true)}>Cancel mission</button>
      </div>
      {state.mode==='mission'&&state.mission_scope&&<p>Fixed scope for this mission: odom {JSON.stringify(state.mission_scope.waypoints)} · maximum {state.mission_scope.duration_s} seconds</p>}
      {state.mode==='mission'&&state.mission_progress&&<p aria-label="Mission decision status">Decision {state.mission_progress.tick} · {state.mission_progress.status} · {state.mission_progress.decision.reason} · odom {state.mission_progress.decision.navigation.pose_xy_yaw.map(v=>v.toFixed(3)).join(' / ')} (Not guaranteed continuous live observation or room alignment)</p>}
    </section>}
    <div className="console-grid">
    <section className="console-card console-scan" aria-label="Live LiDAR scan">
      <div className="console-section-title"><h3>LiDAR / local scan</h3><span>{scanActive?'Sensor session active':'Sensor stopped / unverified'}</span></div>
      <LidarScanView scan={state.scan_preview??null} active={scanActive} pending={scanSession&&(busy||state.state==='STARTING'||state.state==='PREPARING')&&state.busy}/>
      <div className="console-sensor-buttons">
        <button disabled={!backendReady||!operationApproved||busy||state.busy||!scanSourceReady} onClick={()=>void start('scan')}>Start LiDAR scan</button>
        <button disabled={!state.busy||!scanSession||state.state==='STOPPING'} onClick={()=>stop(true)}>Stop LiDAR scan{state.mode==='control_scan'?' + driving':''}</button>
      </div>
      {scanSession&&state.state==='STOPPING'&&<p role="status">Stopping LiDAR and closing the owned session — awaiting cleanup confirmation…</p>}
      {scanActive&&state.scan_display_fault&&state.scan_display_fault!=='NONE'&&<p role="alert">Scan display rejected: {state.scan_display_fault}. The sensor may be rotating; review the recorded ROS metadata.</p>}
      {scanSession&&!state.busy&&<p role="status">{state.sensor_cleanup_confirmed&&state.cleanup_confirmed?
        'Sensor STOP write, data quiet and port restoration confirmed. Physical rotor stop is not measured.':
        'Sensor cleanup is unverified. Review results before another operation.'}</p>}
      {!scanSourceReady&&<p className="console-hint">Scan display needs the current robot package. Prepare the package, then refresh the read-only connection status. No movement test is required for scan-only viewing.</p>}
      <p className="console-hint">{untilStop?'Drive + LiDAR stays connected until Stop or a safety/recording fault.':'Scan-only and older packages: up to 60 seconds.'} Select Drive + LiDAR in Connection setup for simultaneous driving and scan display. Stopping that scan also stops driving. This view is not collision avoidance.</p>
    </section>
    <section className="console-drive" aria-label="Directional control">
      <div className="console-section-title"><h3>Drive joystick</h3><span className={enabled?'ready-chip':'locked-chip'}>{enabled?state.mode==='control_scan'?'● Manual + LiDAR':'● Connected':state.busy&&state.state==='RELEASING'?'Stopping wheels':'Locked'}</span></div>
      <p role="status" className="console-hint">{enabled?`READY TO DRIVE · ${sessionLabel} · release stops wheels, not the connection`:busy||state.busy?
        state.state==='FINISHED'?'Robot operation ended — saving results. No movement or automatic reconnect.':
        state.state==='STOPPING'?'Stopping robot and LiDAR — waiting for cleanup confirmation.':
        state.state==='RELEASING'?'Stopping wheels — verifying idle. Connection and LiDAR remain open; joystick re-enables after confirmation.':
        `${selectedMode==='control_scan'?'Connecting drive + LiDAR':selectedMode==='control'?'Connecting drive':descriptions[state.state]??'Preparing'} · joystick locked until READY`:
        state.reason==='SESSION_EXPIRED'?'Session ended — the 60-second connection limit was reached, not a joystick-release fault. Click Connect above to open another session.':
        canConnect?'Choose a driving mode in Connection setup, then click Connect.':'Joystick locked — complete the enabled preparation action above.'}</p>
      {enabled&&state.manual_speed&&<p className="console-hint">Speed: {state.manual_speed.linear_m_s.toFixed(2)} m/s · turn: {state.manual_speed.angular_rad_s.toFixed(2)} rad/s. Supervised manual driving; no collision avoidance.</p>}
      {state.busy&&['READY','RELEASING'].includes(state.state)&&!untilStop&&manualRemaining!==null&&manualRemaining<=10&&<p role="status" className="console-error">Session expires in about {manualRemaining}s. The session then stops wheels and LiDAR; it will not reconnect automatically.</p>}
      <DriveJoystick disabled={!enabled&&!held.current}
        disabledMessage={state.busy&&state.state==='RELEASING'?'Stopping wheels · connection remains open':'Control locked'}
        onDirection={steer} onRelease={()=>stop()}/>
      <details className="joystick-fallback"><summary>Direction buttons</summary>
    <div className="controller-pad">
      {([['forward','↑ Forward'],['left','↶ Turn left'],['right','↷ Turn right'],['backward','↓ Backward']] as const).map(([action,label])=>
        <button key={action} className={`controller-${action}`} disabled={!enabled} aria-pressed={enabled&&pressed===action}
          onPointerDown={e=>{if(e.button!==0)return;e.preventDefault();e.currentTarget.setPointerCapture?.(e.pointerId);press(action);}}
          onPointerUp={()=>{if(held.current===action)stop();}}
          onPointerCancel={()=>stop(true)} onLostPointerCapture={()=>{if(held.current===action)stop();}}
          onContextMenu={e=>e.preventDefault()}>{label}</button>)}
      <button className="controller-stop" onClick={()=>requestStop('force_stop')}>Force STOP now</button>
    </div>
      </details>
      <div className="console-keyboard"><span><kbd>W</kbd><kbd>S</kbd> Forward / backward</span><span><kbd>A</kbd><kbd>D</kbd> Rotate in place</span><span><kbd>Esc</kbd> Stop</span></div>
      {compact&&stopControls}
      <p className="console-hint">{state.motion_lease_policy==='fresh-intent-1.0'?'Fresh movement input renews short intent segments without periodic braking. Missing input, release or leaving this window stops control.':
        'Legacy package: bounded hold with stop-and-resume. Update required for continuous driving.'} {untilStop?'Session stays open until Stop, lost heartbeat/window focus, low battery, sensor fault or recording capacity failure.':'Session limit: 60 seconds.'} No collision avoidance.</p>
    </section>
    <div className="console-actions">
      <section className="console-card" aria-label="Connection steps">
        <div className="console-section-title"><h3>Connection setup</h3><span>{canConnect?'Stop test recorded':'Motion locked'}</span></div>
        {!compact&&<p role="status" className="console-hint">{busy || state.busy ?
          `${state.mode==='prepare'?'Preparing package':state.mode==='qualify'&&state.state==='READY'?'Ready — click Execute stop test':
            state.state==='TESTING'?'Stop test running':enabled?'Manual control ready':descriptions[state.state]??'Preparing connection'} · ${operationElapsed}s elapsed` :
          state.result==='PREPARED'?'Package ready → select Prepare required stop test.':canConnect?
          'Setup ready → choose a driving mode, then Connect.':hasFailedTrial?
          'Setup blocked → review the failed stop test below.':'Setup pending → select the first enabled preparation action.'}</p>}
        {compact&&<p role="status" className="console-hint">{busy||state.busy?
          state.state==='FINISHED'?'Operation ended · saving results · joystick locked':
          state.state==='STOPPING'?'Stopping · cleanup in progress · joystick locked':
          enabled?`CONNECTED · ${state.mode==='control_scan'?'Drive + LiDAR':'Drive only'} · joystick READY · ${sessionLabel}`:
          state.busy&&state.state==='RELEASING'?`CONNECTED · stopping wheels · ${sessionLabel}`:
          `Preparing ${selectedMode.replaceAll('_',' ')} · ${operationElapsed}s · do not drive yet`:
          canConnect?'Ready to connect. Clicking Connect starts a supervised session; keep the robot in view.':
          state.reason?`Last operation ended: ${reasons[state.reason]??state.reason}`:'Use the first enabled action below.'}</p>}
        {compact&&<p className="console-hint" role="status">{canConnect?'This boot and package release have a passing stop record. No redeployment or repeated stop test is needed.':
          hasFailedTrial?'The saved stop test for this boot and release failed. Do not repeat or bypass it. Review the result below.':
          state.result==='PREPARED'?'Package prepared. The short physical stop test is required before manual control.':
          savedTrial?.status==='QUALIFIED'?'Saved stop test does not match this status snapshot. Use “Check again” above; if the release changed, a new test is required.':
          'The status check observes the robot but does not deploy code or test physical stopping. Complete the required preparation below.'}</p>}
        <div className="console-steps">
          {(!compact||!canConnect||upgradeAvailable&&!scanReleaseReady)&&<>
            <button disabled={!backendReady||!operationApproved||busy||state.busy||!canPreparePackage} onClick={()=>void start('prepare')}>Prepare package · deploy / Motor OFF</button>
            <button disabled={!backendReady||!operationApproved||busy||state.busy||!canPrepareTest} onClick={()=>void start('qualify')}>Prepare required stop test</button>
          </>}
          {compact?<>
            <label>Driving mode<select aria-label="Driving mode" value={driveMode} disabled={busy||state.busy}
              onChange={e=>setDriveMode(e.target.value)}>
              <option value="control_scan">Drive + LiDAR</option><option value="control">Drive only</option>
            </select></label>
            <button className="console-connect" disabled={!backendReady||busy||state.busy||!(driveMode==='control_scan'?canScanConnect:canConnect)}
              onClick={()=>void start(driveMode)}>{enabled?`Connected · ${state.mode==='control_scan'?'Drive + LiDAR':'Drive only'}`:
                state.busy&&state.state==='FINISHED'?'Saving results…':
                state.busy&&state.state==='STOPPING'?'Stopping…':
                state.busy&&state.state==='RELEASING'?'Connected · stopping wheels':
                busy||state.busy&&['control','control_scan'].includes(state.mode??'')?'Connecting…':
                driveMode==='control_scan'?'Connect drive + LiDAR':'Connect drive only'}</button>
          </>:<button className="console-connect" disabled={!backendReady||!operationApproved||busy||state.busy||!canConnect} onClick={()=>void start('control')}>3. Connect manual control</button>}
        </div>
        {compact&&upgradeAvailable&&!scanReleaseReady&&<p className="console-hint" role="status">Manual driving uses the verified current release. LiDAR + driving needs this App’s newer robot package and its own stop test. Select “Prepare package” once, then run the new release’s stop test before combined control. No automatic deployment or movement occurs.</p>}
        {compact&&canConnect&&!scanReleaseReady&&!upgradeAvailable&&<p className="console-hint" role="status">This PC could not verify the deployable robot-source version for LiDAR + driving. Existing manual control is available, but the combined mode remains locked. Check the local installation before deployment.</p>}
        {(!compact||!canConnect)&&<button className="console-trial" disabled={!backendReady||!approvedSession.current||!state.owned||failed.current||state.mode!=='qualify'||state.state!=='READY'||!state.busy||!!error}
          onClick={()=>void input('qualify')}>Execute stop test · short physical forward motion</button>}
        {!canConnect&&<p className="console-hint">Run only after stop-test preparation · current local package test: forward input at 0.05 m/s for 0.6 seconds (older packages: 0.03 m/s)</p>}
      </section>
      <details className="console-tools"><summary>Maintenance · native LiDAR test / Motor OFF</summary>{sensorTools}</details>
    </div>
    </div>
    <details className="console-result-details" open={!compact}>
    <summary>{state.reason ? `Results and causes · ${reasons[state.reason]??state.reason}` : 'Results, logs and detailed criteria'}</summary>
    <section className="console-evidence" aria-label="Results and causes">
    <div className="console-section-title"><h3>Results and causes</h3><span>Saved record · not motion authorization</span></div>
    {state.session_storage&&<div aria-label="Command and observation record">
      <p>PC records: {state.session_storage.saved} / {state.session_storage.accepted} saved · {state.busy?'recording':state.session_log_complete?'complete end record':'incomplete record'}</p>
      {state.session_storage.error&&<p role="alert">Control shutdown requested due to delayed or failed record storage: {state.session_storage.error}</p>}
      {state.session_evidence&&<>
        <p>{state.session_evidence.count_scope==='RECENT_MEMORY_WINDOW'?'Recent window · ':''}Input received {state.session_evidence.pc_received} · transmitted {state.session_evidence.pipe_written} · robot accepted {state.session_evidence.robot_accepted} · ROS published {state.session_evidence.robot_published} · observed {state.session_evidence.observations}</p>
        {state.session_evidence.last_observation&&<p>Last robot sample: encoder {state.session_evidence.last_observation.encoders.join(' / ')} · torque {state.session_evidence.last_observation.torque?'ON':'OFF'} · source age {state.session_evidence.last_observation.source_age_s.toFixed(3)}s (at sample time)</p>}
      </>}
      <p className="console-hint">Inputs include keepalive messages. Reception, transmission, and publication do not prove physical movement. Floor position and collision are unmeasured; PC and robot clocks differ. Unsaved tail data may be lost on abnormal termination.</p>
    </div>}
    {history&&<p className="console-hint">This is a recently saved stop test. The robot separately checks its validity for the current boot and release.</p>}
    {cleanupFailure&&<p className="console-error">Stop metrics PASS / cleanup confirmation failed — direction keys remain locked because of the final independent Motor OFF check, not deceleration performance.</p>}
    {state.reason&&<p>Robot result: {reasons[state.reason]??state.reason}</p>}
    {trial?.cleanup_stage&&<p>Cleanup stage: {trial.cleanup_stage==='confirmed'?'independently confirmed':trial.cleanup_stage==='independent_torque_off'?'independent Motor OFF':trial.cleanup_stage==='independent_idle_read'?'independent idle read':trial.cleanup_stage} {trial.cleanup_error&&`· ${trial.cleanup_error}`}</p>}
    {state.cleanup_confirmed!==undefined&&<p>Independent Motor OFF and idle observation after completion: {state.cleanup_confirmed?'confirmed':'unverified — inspect the robot directly'}</p>}
    {(state.result==='SETTLING_FAIL'||state.result==='STOP_POLICY_FAIL')&&<p role="alert">Manual control is locked because stop-test criteria failed or lacked observation. Do not repeat the same test.
      This does not diagnose overload or motor failure, and is separate from the cleanup stop confirmation below.</p>}
    <details className="console-details"><summary>View test metrics and operating criteria</summary>
    {assessment&&<div aria-label="Separated stop assessment">
      <p>Policy {assessment.policy_id} · result {assessment.status} ·
        deceleration interval {assessment.limits.deceleration_budget_s*1000}ms followed by separate verification {assessment.limits.verification_s*1000}ms</p>
      <p>Command-blocking observation: {assessment.metrics.guard_observation_ms?.toFixed(0)??'unverified'}ms</p>
      <p>Wheel travel left/right: {assessment.metrics.wheel_travel_mm?.map(v=>v.toFixed(2)).join(' / ')??'insufficient samples'}mm · limit {assessment.limits.wheel_travel_limit_mm}mm</p>
      <p>Residual position-change rate equivalent left/right: {assessment.metrics.residual_rate_mm_s?.map(v=>v.toFixed(2)).join(' / ')??'insufficient samples'}mm/s · limit {assessment.limits.residual_rate_limit_mm_s}mm/s</p>
      <p>Values are based on wheel encoders. Floor slip and actual body stopping are not measured; direct observation is required.</p>
    </div>}
    {trial?.stop_diagnostics&&<p>{assessment?'Previous-policy comparison only (not current passing criteria): ':''}Observation after stop signal {trial.stop_diagnostics.window_ms}ms ·
      stable duration {trial.stop_diagnostics.stable_ms===null?'insufficient samples':`${trial.stop_diagnostics.stable_ms.toFixed(1)}ms`} ·
      required {trial.stop_diagnostics.required_stable_ms}ms.
      Stable duration is calculated at the end of the prescribed observation window; it does not mean the robot stopped too early.</p>}
    <p>The design separates a 500 ms deceleration interval and a following 300 ms verification, checking wheel travel ≤10 mm and residual rate ≤1 mm/s equivalent. This is a low-speed, on-site-observed design criterion, not a manufacturer stop guarantee. Past failures are not converted to passes or automatically repeated.</p>
    <p>Initial preparation transfers only approved project code; it installs no system packages. Results are saved under PC artifacts/manual-control. A rehearsal cannot unlock physical control.</p>
    </details></section>
    <SessionHistory api={api} disabled={!historyReady||busy||state.busy}/>
    </details>
  </div>;
}
