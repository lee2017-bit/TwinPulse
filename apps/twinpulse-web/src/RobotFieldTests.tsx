// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {useEffect,useState} from 'react';
import {fleetRobotFresh,type FieldObservation,type FieldSetupConfig,type FieldTestCase,type RobotFleetAction,type RobotFleetRobot} from './robot-fleet-types';
import './RobotFieldTests.css';

export const fieldTestCases:readonly {id:FieldTestCase;label:string;scope:string}[]=[
  {id:'stationary',label:'Stationary collection',scope:'8 s zero-motion native sensor collection; no movement proof.'},
  {id:'bootstrap_stop',label:'Bootstrap stop',scope:'Fixed forward 0.03 m/s for at most 0.6 s; actual-output guard, encoder/time bounds, watchdog observation and real zero/OFF receipt.'},
  {id:'forward',label:'Forward',scope:'Requested forward distance 0.10 m; supervised finite task, upper bound 2 m / 120 s.'},
  {id:'backward',label:'Backward',scope:'Requested backward distance 0.10 m; supervised finite task, upper bound 2 m / 120 s.'},
  {id:'left',label:'Left turn',scope:'Requested left angle 90°; supervised finite task, upper bound 2π rad / 120 s.'},
  {id:'right',label:'Right turn',scope:'Requested right angle 90°; supervised finite task, upper bound 2π rad / 120 s.'},
  {id:'full_turn',label:'Full turn',scope:'One bounded turn with collection; at most 2π rad / 120 s. A scan ring alone is not a chassis rotation.'},
  {id:'proximity',label:'Proximity observation',scope:'Requested forward distance 0.10 m; bounded supervised approach, never a deliberate collision. Receipt threshold is not physical stopping distance.'},
  {id:'stall',label:'Stall observation',scope:'Requested forward distance 0.10 m; bounded supervised observation, never deliberately jam the robot. Wheel stall is not independent chassis/slip proof.'},
  {id:'presence_gap',label:'App-input gap',scope:'Forward task up to 0.10 m with induced App-input presence gap after 0.6 s; not a real Wi-Fi/network outage test.'},
  {id:'soak',label:'Soak collection',scope:'300 s zero-motion sustained collection; no long-duration driving claim.'},
];
const numericFields=[
  ['footprint_radius_m','Outer footprint radius (m)',.08,.6],
  ['sensor_x_m','Sensor X (m)',-.6,.6],['sensor_y_m','Sensor Y (m)',-.6,.6],
  ['sensor_yaw_rad','Sensor yaw (rad)',-Math.PI,Math.PI],
  ['wheel_metres_per_tick','Wheel metres per tick',.000001,.01],['wheel_separation_m','Wheel separation (m)',.08,.8],
] as const;
type Draft=Record<typeof numericFields[number][0],string>&{angle_sign:string;provenance:FieldSetupConfig['provenance']};
const initialDraft:Draft={footprint_radius_m:'0.12',sensor_x_m:'0',sensor_y_m:'0',sensor_yaw_rad:'0',angle_sign:'1',wheel_metres_per_tick:String(2*Math.PI*.033/4096),wheel_separation_m:'0.16',provenance:'reference'};
type FieldAction=Extract<RobotFleetAction,{action:'field_setup'|'field_arm'|'field_test'|'field_review'}>;
type Props={robot:RobotFleetRobot;available:boolean;busy:boolean;onAction:(action:FieldAction['action'],payload:FieldAction['payload'])=>void;onOpenLogs:()=>void};
const pretty=(value:unknown)=>JSON.stringify(value,null,2);
export function RobotFieldTests({robot,available,busy,onAction,onOpenLogs}:Props){
  const [draft,setDraft]=useState<Draft>(initialDraft),[axesReviewed,setAxesReviewed]=useState(false);
  const [supervised,setSupervised]=useState(false),[testConfirmed,setTestConfirmed]=useState(false),[error,setError]=useState<string|null>(null);
  const [reviewTrial,setReviewTrial]=useState(''),[observed,setObserved]=useState<FieldObservation|''>(''),[clearance,setClearance]=useState('');
  const field=robot.field,binding=robot.setup?.binding_sha256??field?.config?.binding_sha256;
  const configHash=field?.config_sha256;
  const savedConfigKey=configHash??(field?.config?JSON.stringify(field.config):'');
  useEffect(()=>{
    const config=robot.field?.config;
    setDraft(config?Object.fromEntries([...numericFields.map(([name])=>[name,String(config[name])]),['angle_sign',String(config.angle_sign)],['provenance',config.provenance]]) as Draft:initialDraft);
    setAxesReviewed(false);setError(null);
  },[robot.robot_id,binding,savedConfigKey]);
  useEffect(()=>{setSupervised(false);setTestConfirmed(false);},[robot.connection_epoch,robot.motion_epoch,savedConfigKey,field?.armed]);
  const enabled=available&&!busy,live=enabled&&fleetRobotFresh(robot);
  const trials=field?.trials??[];
  const active=field?.active_trial;
  const running=active?.status==='RUNNING'||active?.status==='PENDING_PERSISTENCE';
  function save(){
    if(!enabled||!binding||!axesReviewed)return;
    const values:Record<string,number>={};
    for(const [name,label,minimum,maximum] of numericFields){
      const value=Number(draft[name]);
      if(!draft[name].trim()||!Number.isFinite(value)||value<minimum||value>maximum){setError(`${label} must be finite and within ${minimum} to ${maximum}.`);return;}
      values[name]=value;
    }
    if(!['-1','1'].includes(draft.angle_sign)){setError('Angle sign must be -1 or +1.');return;}
    setError(null);setAxesReviewed(false);
    onAction('field_setup',{config:{...values,schema:'supervised-field-test-1.0',robot_id:robot.robot_id,binding_sha256:binding,
      angle_sign:Number(draft.angle_sign) as -1|1,provenance:draft.provenance,axes_reviewed:true} as FieldSetupConfig});
  }
  const hasConfig=!!field?.config;
  return <section className="robot-field-tests" aria-label="Supervised field tests">
    <h5>Supervised household field tests</h5>
    <p>SUPERVISED_FIELD_TEST · separate from the measured protective profile. This is not an industrial safety guarantee or automatic calibration.</p>
    <section aria-label="Power-on test sequence">
      <h5>이번 전원 세션의 시험 순서</h5>
      <ol>
        <li>연결·현재 전압 확인 → Prepare → LiDAR On → 정지 수집 8초와 기록 확인.</li>
        <li>감독 확인·Arm → Bootstrap stop. 이것이 첫 저속 바퀴 시험이며, 물리 제동은 여기서 관찰합니다.</li>
        <li>정지 확인 후 패드·키보드 4방향 → 채팅 90도 → 한 바퀴 스캔 → Stop → 로그 반출·Disconnect.</li>
      </ol>
      <p>정지 수집에 원문 경고가 있어도 수집 자체의 완료와 이동 가능 여부는 별개입니다. 전체 프로토콜 해석·정밀 정합·5분 soak는 첫 감독시험의 선행조건이 아닙니다. 실제 Stop 실패·신선도/방향 관측 부족이면 이동만 중단하고 독립 수집·반출은 계속합니다.</p>
      <small>Pi 부하·실제 저장 지연·제동·주행: 실물 시험에서 측정할 결과입니다. 이 화면이나 SIM 통과가 실물 PASS를 뜻하지 않습니다.</small>
    </section>
    {field?.native_observation&&<section aria-label="Native raw integrity and control observation">
      <p>원문 회전: {field.native_observation.raw_ring_complete?'완전':'불완전 — 원문 경고 보존'} · 미해석 {field.native_observation.unknown_bytes} bytes · frame {field.native_observation.frame_sequence} · 원수신 나이 {Number.isFinite(field.native_observation.receipt_age_s)?Math.round(field.native_observation.receipt_age_s*1000):'unknown'} ms</p>
      <small>감독시험 정책: 미해석 회전은 불완전으로 보존합니다. 같은 stream의 마지막 완전 회전만 원래 350ms 수신 기한 안에서 사용하며, 새 불완전 회전의 근접·관측 공백도 이동을 차단합니다. 0/no-return은 빈 공간이 아니라 제외 표본입니다. 유효 거리만으로 진행 방향의 최대 5° 공백·10cm를 매 출력 검사하며, 새 시각을 만들거나 엄격 프로필·ICP 판정을 바꾸지 않습니다.</small>
    </section>}
    <details open><summary>Simple supervised setup · offline save</summary>
      <p>Editable Burger reference values, not measurements: nominal wheel radius 33 mm, 4096 ticks/revolution, separation 0.16 m; footprint and sensor pose are starting estimates. Review model applicability and replace values for your robot. Saving starts no connection, sensor or movement and restores no authority.</p>
      <small>Robot {robot.robot_id} · binding {binding??'unavailable — refresh registration before saving'}</small>
      <form aria-label="Supervised field setup" onSubmit={event=>{event.preventDefault();save();}}>
        <div className="robot-field-grid">{numericFields.map(([name,label,minimum,maximum])=><label key={name}>{label}<input type="number" step="any" min={minimum} max={maximum} required value={draft[name]} onChange={event=>{setDraft({...draft,[name]:event.target.value});setAxesReviewed(false);}}/></label>)}</div>
        <label>Native angle sign<select value={draft.angle_sign} onChange={event=>{setDraft({...draft,angle_sign:event.target.value});setAxesReviewed(false);}}><option value="1">+1</option><option value="-1">-1</option></select></label>
        <label>Setup provenance<select value={draft.provenance} onChange={event=>{setDraft({...draft,provenance:event.target.value as Draft['provenance']});setAxesReviewed(false);}}><option value="reference">Reference — not measured</option><option value="operator_reviewed">Operator reviewed</option><option value="operator_measured">Operator measured</option></select></label>
        <label className="robot-fleet-confirm"><input type="checkbox" checked={axesReviewed} onChange={event=>setAxesReviewed(event.target.checked)}/>I reviewed robot model applicability, forward X, left Y, sensor pose, native angle sign and these setup values.</label>
        <button disabled={!enabled||!binding||!axesReviewed}>Save supervised setup</button>
      </form>
      {configHash&&<p>Saved config SHA256 {configHash}</p>}
    </details>
    {error&&<p role="alert">{error}</p>}
    <section aria-label="Field test blockers"><h5>Current field prerequisites</h5>
      {!available&&<p>Fleet state unavailable; refresh before sending an action.</p>}
      {!fleetRobotFresh(robot)&&<p>Connect and wait for a fresh authenticated heartbeat. Offline setup remains available.</p>}
      {!hasConfig&&<p>Save a reviewed supervised setup first.</p>}
      {field?.blockers.length?<ul>{field.blockers.map((blocker,index)=><li key={index}>{blocker}</li>)}</ul>:<p>{field?'No field blockers reported; the server still checks each trial and its stop receipt.':'No current field receipt. Settings alone do not grant test authority.'}</p>}
    </section>
    <p role="status">{field?.armed?'Explicit supervision armed':'Supervision not armed'} · remaining {typeof field?.remaining_s==='number'&&Number.isFinite(field.remaining_s)?Math.max(0,Math.floor(field.remaining_s)):'unknown'} s (maximum 900 s). Stop and key release zero/OFF the motors and discard old movement. The current supervision session survives ordinary releases; each movement needs fresh input. LiDAR Off, disconnect, boot or config changes end supervision; reconnect never restores it.</p>
    <label className="robot-fleet-confirm"><input type="checkbox" checked={supervised} onChange={event=>setSupervised(event.target.checked)}/>I am supervising, charging is unplugged, the space is clear, and I can immediately power off the physical robot.</label>
    <button type="button" disabled={!live||!hasConfig||!supervised||!!running} onClick={()=>{setSupervised(false);onAction('field_arm',{confirmed:true});}}>Arm supervised field session</button>
    <p>Policy caps 0.03 m/s · 0.20 rad/s, not measured values. Input expiry 250 ms · local watchdog 400 ms. Arming uses the saved config, not unsaved edits. Bootstrap stop does not require a prior stop receipt; subsequent motion requires its current durable receipt and native directional coverage.</p>
    <label className="robot-fleet-confirm"><input type="checkbox" checked={testConfirmed} onChange={event=>setTestConfirmed(event.target.checked)}/>I reviewed the selected trial scope and explicitly confirm one supervised test.</label>
    <ol aria-label="Available field test cases">{fieldTestCases.map(test=><li key={test.id}><strong>{test.label}</strong><p>{test.scope}</p><button type="button" disabled={!live||!hasConfig||!testConfirmed||!!running} onClick={()=>{setTestConfirmed(false);onAction('field_test',{case:test.id,confirmed:true});}}>Run {test.label}</button></li>)}</ol>
    <small>Each click requests one bounded case; no automatic retries or next-case chaining. Backend prerequisites apply separately to collection, bootstrap and armed motion.</small>
    {active&&<p role="status">Active trial {active.trial_id} · {active.case} · {active.status} · {active.reason??'No reason reported'}</p>}
    <details><summary>Stop receipt · {field?.stop_receipt?'recorded':'unavailable'}</summary><pre>{pretty(field?.stop_receipt??null)}</pre></details>
    <section aria-label="Independent scan-relative tracking"><h5>Scan-relative body tracking</h5>
      <p>{field?.tracking?.status??'UNKNOWN'} · accuracy UNQUALIFIED · epoch {field?.tracking?.epoch??'unavailable'} · {field?.tracking?.reason??'No independent tracking receipt'}</p>
      <p>Scan-relative only, not Isaac/world alignment. No wheel seed or deskew. Ambiguity makes body-progress proof INCONCLUSIVE; fit residual is not certified pose error. Unknown beam acquisition time remains unqualified.</p>
      {field?.tracking&&<details><summary>Tracking receipt</summary><pre>{pretty(field.tracking)}</pre></details>}
    </section>
    <section aria-label="Field trial results"><h5>Individual trials · {trials.length}</h5>
      <p>PASS applies only to the recorded trial scope, not general physical safety, complete calibration or industrial qualification.</p>
      {trials.length?<ol>{trials.map(trial=><li key={trial.trial_id}><strong>{trial.case} · {trial.status}</strong><p>{trial.trial_id} · {trial.reason??'No reason reported'}</p>{trial.result?.collection_complete===true&&<p>수집 구간 완료 · 엄격 회전 품질 {String(trial.result.strict_ring_quality)} · 원문 저장 무결성은 센서 종료 manifest에서 별도 확인 · 이동 권한은 부여하지 않음. INCONCLUSIVE는 품질 판정이며, 시험 전체가 실행되지 않았다는 뜻은 아닙니다.</p>}<details><summary>Trial evidence and scope</summary><pre>{pretty(trial)}</pre></details></li>)}</ol>:<p>No trial receipts loaded for this connection. Saved operation logs may contain historical trials; they do not restore current qualification.</p>}
      <form aria-label="Review actual field trial" onSubmit={event=>{
        event.preventDefault();if(!enabled||!trials.some(trial=>trial.trial_id===reviewTrial)||observed==='')return;
        const distance=Number(clearance);
        if(clearance.trim()&&(!Number.isFinite(distance)||distance<0)){setError('Outer-body clearance must be a finite nonnegative distance in metres.');return;}
        setError(null);onAction('field_review',{trial_id:reviewTrial,observed,...(clearance.trim()?{clearance_m:distance}:{})});
      }}>
        <label>Actual trial to review<select value={reviewTrial} onChange={event=>setReviewTrial(event.target.value)}><option value="">Select a recorded trial</option>{trials.map(trial=><option key={trial.trial_id} value={trial.trial_id}>{trial.case} · {trial.trial_id}</option>)}</select></label>
        <label>Human observation<select value={observed} onChange={event=>setObserved(event.target.value as FieldObservation|'')}><option value="">Select an observation</option>{(['stopped','not_stopped','moved','not_moved','inconclusive'] as const).map(value=><option key={value} value={value}>{value}</option>)}</select></label>
        <label>Measured outer-body clearance (m, optional)<input type="number" step="any" min="0" value={clearance} onChange={event=>setClearance(event.target.value)}/></label>
        <p>A physical 10 cm clearance claim requires actual outer-body clearance measurement. Leaving this blank makes no such claim; a raw sensor threshold is insufficient.</p>
        <button disabled={!enabled||!trials.some(trial=>trial.trial_id===reviewTrial)||observed===''}>Save trial observation</button>
      </form>
    </section>
    <button type="button" disabled={!(robot.operation_id??robot.last_operation_id)} onClick={onOpenLogs}>Open field operation logs</button>
    <small>Operation {robot.operation_id??robot.last_operation_id??'unavailable'} · raw downloads below include only actual runtime files and their missing-evidence status.</small>
    {active?.status==='PENDING_PERSISTENCE'&&<p role="status">Result pending disk acknowledgement · not a durable PASS or driving permission.</p>}
    <small>Reviewed stream members: field-config.json, field-trials.json, field-stop.json, field-tracking.json, field-commits.jsonl. Trial decisions and exact-byte write acknowledgements must be combined with a complete writer receipt; pending data alone is not PASS. These are raw_source events inside the runtime segments and receipt.json, not separate file-download URLs. Missing members remain missing evidence.</small>
  </section>;
}
