// SPDX-License-Identifier: Apache-2.0
import {beforeEach,describe,expect,it,vi} from 'vitest';
import type {RobotFleetOperation,RobotFleetRobot} from './robot-fleet-types';
import {currentDiagnosticStatus,diagnosticContinuity,diagnosticFileLimit,diagnosticPauseWindows,diagnosticStatistics,lidarDiagnosticLabel,projectDiagnosticEvents,readDiagnosticFile} from './robot-operation-diagnostics';
// Test runner has Node crypto; the browser application intentionally has no
// Node type dependency or bundled Node polyfill.
const webcrypto=(await import('node:'+'crypto')).webcrypto as Crypto;
const operation:RobotFleetOperation={schema_version:'robot-operation-1.0',operation_id:'operation-a',robot_id:'robot-a',project_id:'project',events:[],manifest:{}};
const sensor=(sequence=1,age=.025):Record<string,unknown>=>({operation_id:'operation-a',robot_id:'robot-a',kind:'raw',sequence,connection_epoch:'connection',robot_monotonic_s:12+sequence,
  data:{source:'serialized_ros_message',topic:'sensor_state',stream_id:'ros-stream',observation_sequence:sequence,receipt_end_s:12+sequence,base64:'not rendered',callback_timing:{source_age_at_receipt_s:age,source_stamp_ns:100,receipt_ros_now_ns:200}}});
const file=(text:string,name='events-00000.jsonl')=>{const bytes=new TextEncoder().encode(text);return {name,size:bytes.length,slice:(from:number,to:number)=>({arrayBuffer:async()=>bytes.slice(from,to).buffer})} as File;};
const hash=async(text:string)=>[...new Uint8Array(await webcrypto.subtle.digest('SHA-256',new TextEncoder().encode(text)))].map(value=>value.toString(16).padStart(2,'0')).join('');
beforeEach(()=>vi.stubGlobal('crypto',webcrypto));
describe('original diagnostic evidence projection',()=>{
  it('counts explicit callbacks once and never promotes repeated heartbeat snapshots to independent sensor samples',()=>{
    const heartbeat={kind:'heartbeat',robot_monotonic_s:20,data:{telemetry_diagnostic:{reason:'CURRENT',source_age_s:.199,callback_timing:{source_age_at_receipt_s:.1,source_stamp_ns:100}}}};
    const data=projectDiagnosticEvents([sensor(),sensor(),sensor(2,.075),...Array.from({length:200},()=>heartbeat)]);
    const stat=diagnosticStatistics(data.rows,'sensor');expect(stat.n).toBe(2);expect(stat.mean).toBe(50);expect(stat.sd).toBeCloseTo(Math.sqrt(1250));expect(stat.p99).toBe(75);
    expect(data.rows.some(row=>row.values.some(([,value])=>value.includes('not rendered')))).toBe(false);
    expect(diagnosticStatistics(projectDiagnosticEvents([heartbeat]).rows,'sensor').n).toBe(0);
  });
  it('refuses a statistical result for conflicting values under one original callback identity',()=>{
    const stat=diagnosticStatistics(projectDiagnosticEvents([sensor(1,.02),sensor(1,.04),sensor(2,.08)]).rows,'sensor');
    expect(stat.conflicting).toBe(1);expect(stat.sd).toBeNull();expect(stat.p99).toBeNull();
  });
  it('keeps host and robot clocks as different recorded fields with no fabricated elapsed-time subtraction',()=>{
    const data=projectDiagnosticEvents([{kind:'stop_requested',monotonic_s:800000,data:{request_id:'stop-id'}},sensor(),{kind:'cleanup',utc:'2026-10-18T14:00:00Z',data:{confirmed:false}}]);
    expect(data.rows.map(row=>row.clock)).toEqual(['monotonic_s · host domain unqualified','robot_monotonic_s','recorded UTC']);
    expect(data.rows.map(row=>row.time)).toEqual([800000,13,'2026-10-18T14:00:00Z']);
    expect(data.rows[0].request).toBe('stop-id');expect(data.rows[2].values).toContainEqual(['stop confirmed','false']);
  });
  it('projects the actual PC command envelope without replacing its original send clock with robot time',()=>{
    const [row]=projectDiagnosticEvents([{schema:'physical-live-pc-command-2.0',action:'drive',request_id:'pc-input',pc_sent_monotonic_s:900001,payload:{direction:'forward',source_age_ms:11},request_twin_context:{scene_revision:'requested-twin'}}]).rows;
    expect(row.kind).toBe('input drive');expect(row.clock).toBe('pc_sent_monotonic_s');expect(row.time).toBe(900001);
    expect(row.values).toContainEqual(['input source_age_ms','11']);expect(row.scene).toBe('requested-twin');
  });
  it('counts measured tracking jobs once, preserving job timing separately from original sample time',()=>{
    const row={kind:'heartbeat',connection_epoch:'connection',data:{field:{tracking:{status:'ESTIMATED',sample_s:2,stream_id:'stream',compute_timing:{job_id:2,compute_elapsed_s:.02,delivery_elapsed_s:.03}}}}};
    const data=projectDiagnosticEvents([row,row,{...row,data:{field:{tracking:{...row.data.field.tracking,compute_timing:{job_id:3,compute_elapsed_s:.04}}}}}]);
    const stat=diagnosticStatistics(data.rows,'compute');expect(stat.n).toBe(2);expect(stat.mean).toBe(30);expect(data.rows[0].values).toContainEqual(['tracking sample_s','2']);
  });
  it('uses nearest-rank p99.9, original callback intervals within each stream and the recorded source threshold',()=>{
    const rows=projectDiagnosticEvents([sensor(1,.1),sensor(1,.1),sensor(2,.2),sensor(3,.3),{...sensor(1,.1),data:{...sensor(1,.1).data as object,stream_id:'other-stream',receipt_end_s:80000}}]).rows;
    expect(diagnosticStatistics(rows,'sensor').p999).toBe(300);
    expect(diagnosticContinuity(rows,200)).toMatchObject({callbacks:4,gaps:2,maximumGapMs:1000,over:2,ageSamples:4,overPercent:50});
    expect(diagnosticContinuity(rows,null).overPercent).toBeNull();
    const invalid=projectDiagnosticEvents([{...sensor(),data:{...sensor().data as object,receipt_end_s:null}},sensor(2)]).rows;
    expect(diagnosticContinuity(invalid,200).maximumGapMs).toBeNull();
  });
  it('counts only observed PAUSED transitions, excluding repeated heartbeats and an initially paused state',()=>{
    const events=['PAUSED','PAUSED','READY','PAUSED','PAUSED'].map((control_state,index)=>({kind:'heartbeat',connection_epoch:'epoch',robot_monotonic_s:index*10,data:{control_state}}));
    expect(diagnosticPauseWindows(projectDiagnosticEvents(events).rows)).toEqual([expect.objectContaining({seconds:40,count:1,initialPaused:1,perHour:90,method:'observed PAUSED transitions · lower bound'})]);
    const changed=projectDiagnosticEvents([...events,{kind:'heartbeat',connection_epoch:'different',robot_monotonic_s:2000,data:{control_state:'PAUSED'}}]);
    expect(diagnosticPauseWindows(changed.rows)).toHaveLength(2);expect(diagnosticPauseWindows(changed.rows)[1].perHour).toBeNull();
  });
  it('uses actual control_pause IDs once and preserves the measured zero/OFF readback field',()=>{
    const pause={kind:'control_pause',connection_epoch:'epoch',robot_monotonic_s:10,data:{pause_id:'epoch:1',reason:'INPUT_EXPIRED',observed_monotonic_s:9.99,motion_generation:3,zero_off_readback_confirmed:true}};
    const rows=projectDiagnosticEvents([{kind:'heartbeat',connection_epoch:'epoch',robot_monotonic_s:0,data:{control_state:'READY'}},pause,pause,{kind:'heartbeat',connection_epoch:'epoch',robot_monotonic_s:12,data:{control_state:'PAUSED'}}]).rows;
    expect(diagnosticPauseWindows(rows)[0]).toMatchObject({count:1,method:'explicit distinct pause IDs',seconds:12});
    expect(rows[1].values).toContainEqual(['stop zero_off_readback_confirmed','true']);
    expect(rows[1].values).toContainEqual(['stop observed_monotonic_s','9.99']);
  });
  it('keeps payload-lock timing and wheel estimates separate from independent body evidence',()=>{
    const [row]=projectDiagnosticEvents([{kind:'control_pause',robot_monotonic_s:10,data:{reason:'INPUT_DEADLINE_EXPIRED',
      event_delivery:{payload_prepare_s:.002,order_lock_wait_s:.003,payload_started_s:9.99,ordered_s:10},
      motion_observation:{centre_m:.010681,yaw_rad:.02,body_progress:'UNKNOWN',result:'INCONCLUSIVE_BODY_MOTION',request_id:'original-request'}}}]).rows;
    expect(row.values).toContainEqual(['event order-lock wait','3.00 ms']);
    expect(row.values).toContainEqual(['wheel centre mm','10.68']);
    expect(row.values).toContainEqual(['wheel body_progress','UNKNOWN']);
    expect(row.values).toContainEqual(['wheel request_id','original-request']);
  });
  it('preserves an original failed check after cleanup replaced the current diagnostic',()=>{
    const [row]=projectDiagnosticEvents([{kind:'heartbeat',data:{telemetry_diagnostic:{reason:'CURRENT',guard_receipt_age_s:.01},
      last_control_fault:{reason:'TELEMETRY_STALE',telemetry:{reason:'GUARD_RECEIPT_STALE',guard_receipt_age_s:.212418531,checked_monotonic_s:5913.5714}}}}]).rows;
    expect(row.values).toContainEqual(['original failed check reason','GUARD_RECEIPT_STALE']);
    expect(row.values).toContainEqual(['original failed guard receipt age','212.42 ms']);
    expect(row.values).toContainEqual(['guard callback receipt age','10.00 ms']);
  });
  it('does not label disconnected historical STREAMING or a missing check clock as current diagnostics',()=>{
    const r={kind:'physical',connection_state:'DISCONNECTED',live_heartbeat:false,lidar_state:'STREAMING',telemetry_age_ms:20,telemetry_diagnostic:{reason:'CURRENT'}} as unknown as RobotFleetRobot;
    expect(lidarDiagnosticLabel(r)).toContain('No current stream · last reported STREAMING');
    expect(currentDiagnosticStatus(r,true)).toContain('No current diagnostic');
    r.connection_state='CONNECTED';r.live_heartbeat=true;expect(currentDiagnosticStatus(r,true)).toContain('validity not established');
    r.timing_policy={limits:{ros_receipt:{seconds:.2}}};r.telemetry_diagnostic={checked_monotonic_s:30,check_age_s:.01,reason:'CURRENT'};
    expect(currentDiagnosticStatus(r,true)).toContain('Current diagnostic check');
    expect(currentDiagnosticStatus(r,false)).toContain('No current diagnostic');
  });
});
describe('bounded local diagnostic file reading',()=>{
  it('verifies one original segment identity, bytes and SHA without retaining its raw base64',async()=>{
    const original=JSON.stringify(sensor())+'\n'+JSON.stringify(sensor(2,.075))+'\n',source=file(original),sha=await hash(original);
    const result=await readDiagnosticFile(source,{...operation,manifest:{stream:{segments:[{path:source.name,bytes:source.size,sha256:sha}]}}},new AbortController().signal);
    expect(result.sha256).toBe(sha);expect(result.verifiedManifest).toBe(true);expect(result.scope).toBe('selected JSONL segment');expect(result.projection.rows).toHaveLength(2);
    expect(JSON.stringify(result.projection)).not.toContain('not rendered');
  });
  it('rejects a manifest mismatch, malformed line and mixed operation instead of accepting a partial projection',async()=>{
    const source=file(JSON.stringify(sensor())+'\n');
    await expect(readDiagnosticFile(source,{...operation,manifest:{stream:{segments:[{path:source.name,bytes:source.size,sha256:'0'.repeat(64)}]}}},new AbortController().signal)).rejects.toThrow('differ');
    await expect(readDiagnosticFile(file(JSON.stringify(sensor())+'\n{'),operation,new AbortController().signal)).rejects.toThrow('line 2');
    await expect(readDiagnosticFile(file(JSON.stringify({...sensor(),operation_id:'other'})),operation,new AbortController().signal)).rejects.toThrow('identity differs');
  });
  it('rejects oversized files before reading and respects an explicit cancel during a chunk read',async()=>{
    await expect(readDiagnosticFile({name:'too-large.jsonl',size:diagnosticFileLimit+1} as File,operation,new AbortController().signal)).rejects.toThrow('8 MiB');
    let finish!:(value:ArrayBuffer)=>void;const cancel=new AbortController(),source=file(JSON.stringify(sensor())+'\n');
    const pending=readDiagnosticFile({...source,slice:()=>({arrayBuffer:()=>new Promise<ArrayBuffer>(resolve=>{finish=resolve;})})} as unknown as File,operation,cancel.signal);
    cancel.abort();finish(new TextEncoder().encode('ignored').buffer);await expect(pending).rejects.toThrow('cancelled');
  });
  it('keeps a UTF-8 record across chunk boundaries and labels a summary import as a partial scope',async()=>{
    const text=JSON.stringify({...sensor(),comment:'가'.repeat(23000)})+'\n';
    const result=await readDiagnosticFile(file(text),operation,new AbortController().signal);expect(result.projection.sourceEvents).toBe(1);
    const saved=await readDiagnosticFile(file(JSON.stringify({...operation,events:[{kind:'stop',monotonic_s:4,data:{reason:'operator'}}]}),'saved-operation.json'),operation,new AbortController().signal);
    expect(saved.scope).toBe('selected operation JSON');expect(saved.verifiedManifest).toBe(false);expect(saved.projection.unverifiedIdentities).toBe(1);
  });
});
