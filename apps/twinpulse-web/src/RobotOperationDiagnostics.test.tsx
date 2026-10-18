// SPDX-License-Identifier: Apache-2.0
import {act,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import type {RobotFleetOperation,RobotFleetRobot} from './robot-fleet-types';
import {RobotOperationDiagnostics} from './RobotOperationDiagnostics';
const webcrypto=(await import('node:'+'crypto')).webcrypto as Crypto;
const robot:RobotFleetRobot={robot_id:'robot-a',label:'Robot a',kind:'physical',connection_state:'DISCONNECTED',connection_epoch:null,motion_epoch:null,
  control_state:'UNPREPARED',lidar_state:'STREAMING',recording_state:'IDLE',operation_id:null,last_operation_id:'operation-a',reason:null,
  battery:{voltage_v:11.8,percent:null,source:'measured',age_ms:40000},pose:null,telemetry_age_ms:40000,telemetry_sequence:1,live_heartbeat:false,capabilities:{drive:false,lidar:false},scan:null,
  telemetry_diagnostic:{reason:'CURRENT',source_age_s:.034,sensor_receipt_age_s:.01,guard_receipt_age_s:.02}};
const operation:RobotFleetOperation={schema_version:'robot-operation-1.0',operation_id:'operation-a',robot_id:'robot-a',project_id:'project-a',manifest:{complete:false,
  source_twin_context:{scene_revision:'original-twin',alignment:{status:'UNALIGNED'}},stream:{event_count:50000,error:'FIELD_EVIDENCE_STALLED'}},events:[
  {kind:'stop_request',monotonic_s:990000,data:{request_id:'original-stop-request'}},
  {kind:'heartbeat',robot_monotonic_s:200,connection_epoch:'connection-a',data:{telemetry_diagnostic:{reason:'CURRENT',source_age_s:.034},field_evidence:{error:'FIELD_EVIDENCE_STALLED',complete:false}}},
  {kind:'cleanup',robot_monotonic_s:202,data:{confirmed:false,reason:'INCOMPLETE_EVIDENCE'}}]};
const textFile=(text:string)=>{const bytes=new TextEncoder().encode(text);return {name:'events-00000.jsonl',size:bytes.length,slice:(a:number,b:number)=>({arrayBuffer:async()=>bytes.slice(a,b).buffer})} as File;};
beforeEach(()=>vi.stubGlobal('crypto',webcrypto));afterEach(()=>vi.unstubAllGlobals());
describe('read-only operation diagnostic timeline',()=>{
  it('separates disconnected current validity from historical CURRENT, original clocks and incomplete records',()=>{
    const fetch=vi.fn();vi.stubGlobal('fetch',fetch);render(<RobotOperationDiagnostics robot={robot} operation={operation} available={true}/>);
    expect(screen.getByText('No current diagnostic · disconnected or receipt stale')).toBeTruthy();
    expect(screen.getByText(/bounded operation summary; not the complete raw stream/)).toBeTruthy();
    expect(screen.getByText('original-twin')).toBeTruthy();expect(screen.getByText('UNALIGNED')).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Recorded event cursor · read-only'),{target:{value:'1'}});
    const selected=screen.getByLabelText('Selected recorded diagnostic');expect(selected.textContent).toContain('robot_monotonic_s');expect(selected.textContent).toContain('200');
    expect(selected.textContent).toContain('FIELD_EVIDENCE_STALLED');
    fireEvent.click(screen.getByRole('button',{name:'Next recorded event'}));expect(selected.textContent).toContain('INCOMPLETE_EVIDENCE');
    fireEvent.change(screen.getByLabelText('Recorded category'),{target:{value:'input'}});
    expect(selected.textContent).toContain('original-stop-request');
    expect(fetch).not.toHaveBeenCalled();
  });
  it('does not invent an SD/p99 from a heartbeat-only summary or fill timing thresholds from defaults',()=>{
    render(<RobotOperationDiagnostics robot={robot} operation={operation} available={true}/>);
    expect(screen.getByText('Timing policy not recorded. No threshold has been inferred or changed.')).toBeTruthy();
    const table=screen.getByRole('columnheader',{name:'Unique samples'}).closest('table')!;
    const source=within(table).getByText('Sensor source age at original callback').closest('tr')!;
    expect(source.textContent).toContain('0');expect(within(source).getAllByText('insufficient evidence').length).toBeGreaterThan(2);
    expect(screen.getByText(/Repeated heartbeat diagnostics are excluded/)).toBeTruthy();
  });
  it('opens an identity-matched selected raw segment locally and can return to the historical summary without a network call',async()=>{
    const fetch=vi.fn();vi.stubGlobal('fetch',fetch);render(<RobotOperationDiagnostics robot={robot} operation={operation} available={true}/>);
    const file=textFile(JSON.stringify({operation_id:'operation-a',robot_id:'robot-a',kind:'raw',robot_monotonic_s:10,data:{source:'serialized_ros_message',topic:'sensor_state',stream_id:'stream',observation_sequence:1,callback_timing:{source_age_at_receipt_s:.025}}})+'\n');
    fireEvent.change(screen.getByLabelText(/Open recorded JSON/),{target:{files:[file]}});
    await screen.findByRole('button',{name:'Return to saved summary'});expect(screen.getByText(/Historical read-only record · selected JSONL segment/)).toBeTruthy();
    expect(screen.getByText(/origin remains unverified/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'Return to saved summary'}));
    expect(screen.getByText(/bounded operation summary; not the complete raw stream/)).toBeTruthy();expect(fetch).not.toHaveBeenCalled();
  });
  it('aborts a local read on robot/operation change and never accepts its late result into the new record',async()=>{
    let complete!:(value:ArrayBuffer)=>void;const source=textFile(JSON.stringify({operation_id:'operation-a',robot_id:'robot-a',kind:'stop'})+'\n');
    const slow={...source,slice:()=>({arrayBuffer:()=>new Promise<ArrayBuffer>(resolve=>{complete=resolve;})})} as unknown as File;
    const view=render(<RobotOperationDiagnostics robot={robot} operation={operation} available={true}/>);
    fireEvent.change(screen.getByLabelText(/Open recorded JSON/),{target:{files:[slow]}});await screen.findByRole('button',{name:'Cancel diagnostic reading'});
    view.rerender(<RobotOperationDiagnostics robot={robot} operation={{...operation,operation_id:'operation-b'}} available={true}/>);
    await act(async()=>{complete(new TextEncoder().encode('late').buffer);});
    expect(screen.queryByRole('button',{name:'Return to saved summary'})).toBeNull();expect(screen.queryByText(/selected JSONL segment/)).toBeNull();
    expect(screen.getByText('operation-b')).toBeTruthy();
  });
  it('shows local parse errors without replacing the valid prior summary with partial success',async()=>{
    render(<RobotOperationDiagnostics robot={robot} operation={operation} available={true}/>);
    fireEvent.change(screen.getByLabelText(/Open recorded JSON/),{target:{files:[textFile('{')]}});
    await waitFor(()=>expect(screen.getByRole('alert').textContent).toContain('No partial analysis was accepted'));
    expect(screen.getByText(/bounded operation summary; not the complete raw stream/)).toBeTruthy();
    expect(screen.queryByRole('button',{name:'Return to saved summary'})).toBeNull();
  });
  it('keeps a persisted historical trial result distinct from current permission and shows pending write phases',()=>{
    const field={...robot,field:{evidence_status:{phase:'ACK_FSYNC',phase_elapsed_s:.25,phase_max_s:.8,oldest_pending_s:.9,pending:2}}} as unknown as RobotFleetRobot;
    const saved={...operation,manifest:{...operation.manifest,field_trial_resolution:{status:'WRITER_INCOMPLETE',authority_restored:false,trials:[{trial_id:'trial-id',status:'INCONCLUSIVE',reason:'FIELD_EVIDENCE_ACK_UNCONFIRMED',persistence:{state:'UNCONFIRMED'}}]}}};
    render(<RobotOperationDiagnostics robot={field} operation={saved} available={true}/>);
    expect(screen.getByText('ACK_FSYNC')).toBeTruthy();expect(screen.getByText('250.00 ms')).toBeTruthy();
    expect(screen.getByText(/Historical field persistence resolution: WRITER_INCOMPLETE · authority restored false/)).toBeTruthy();
    expect(screen.getByRole('table',{name:'Historical field persistence resolution'}).textContent).toContain('FIELD_EVIDENCE_ACK_UNCONFIRMED');
    expect(screen.getByText(/PENDING_PERSISTENCE is not PASS/)).toBeTruthy();
  });
});
