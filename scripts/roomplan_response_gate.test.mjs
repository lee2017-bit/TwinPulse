// SPDX-License-Identifier: Apache-2.0
import {test} from 'node:test';import assert from 'node:assert/strict';
import {classifyRoomplanResponses as gate} from './roomplan_response_gate.mjs';
const robot=(epoch='old')=>({robot_id:'robot',connection_epoch:'conn',motion_epoch:epoch,applied_motion_epoch:epoch,operation_id:'operation',control_state:'PAUSED',reason:'OPERATOR_STOP',telemetry_sequence:4,pose:{position_m:[.05,0,0]}});
function fixture(){const after=robot('new');return {operation_events:[{operation_id:'operation',robot_id:'robot',kind:'engine_observation',source:'isaac_usd_kinematic',position_m:[.025,0,0],telemetry_sequence:3,utc:new Date(1000).toISOString(),reason:null}],gestures:[{direction:'forward',before:robot(),down:{at:900,trusted:true},up:{at:1100,trusted:true},after,stable_after:{...after,telemetry_sequence:6},interruptions:[]}],responses:[
 {at:1111,status:409,native_start_ms:1000,native_timing:{responseEnd:110},request:{action:'drive',request_id:'drive',robot_id:'robot',connection_epoch:'conn',motion_epoch:'old',payload:{direction:'forward',sequence:1,expires_at_ms:1350}},body:{error:{code:'fleet_motion_changed'}}},
 {at:1108,status:200,native_start_ms:1101,native_timing:{responseEnd:5},request:{action:'stop',request_id:'stop',robot_id:'robot',connection_epoch:'conn',motion_epoch:'old'},body:{robots:[after]}},
 {at:1120,status:200,native_start_ms:1115,native_timing:{responseEnd:5},body:{robots:[after]}},
 ]};}
test('only fully correlated in-flight Stop rejection is expected',()=>assert.equal(gate(fixture()).expected_stop_rejections.length,1));
for(const kind of ['other_error','after_release','expired_before_stop','wrong_operation','untrusted_release','interrupted','missing_timing','queued_drive','no_ack','moving_after_stop','missing_sequence','nan_sequence','old_stable_ack','other_stable_operation','other_stable_robot','other_stable_connection','bad_pose','held_input_stale','missing_engine_events','prior_concurrent_drive'])test('reject '+kind,()=>{
 const value=fixture(),[drive,stop,ack]=value.responses,g=value.gestures[0];
 if(kind==='other_error')drive.body.error.code='fleet_input_expired';
 if(kind==='after_release')drive.native_start_ms=1110;
 if(kind==='expired_before_stop')drive.request.payload.expires_at_ms=1099;
 if(kind==='wrong_operation')stop.body.robots[0]={...robot('new'),operation_id:'other'};
 if(kind==='untrusted_release')g.up.trusted=false;
 if(kind==='interrupted')g.interruptions.push({type:'blur'});
 if(kind==='missing_timing')delete drive.native_timing;
 if(kind==='queued_drive')value.responses.push({...drive,native_start_ms:1111,request:{...drive.request,request_id:'retry'}});
 if(kind==='no_ack'){g.after.applied_motion_epoch='old';stop.body.robots[0]={...robot('new'),applied_motion_epoch:'old'};ack.body.robots[0]={...robot('new'),applied_motion_epoch:'old'};}
 if(kind==='moving_after_stop')g.stable_after.pose={position_m:[.06,0,0]};
 if(kind==='missing_sequence')delete g.stable_after.telemetry_sequence;
 if(kind==='nan_sequence')g.after.telemetry_sequence=NaN;
 if(kind==='old_stable_ack')g.stable_after.applied_motion_epoch='old';
 if(kind==='other_stable_operation')g.stable_after.operation_id='other';
 if(kind==='other_stable_robot')g.stable_after.robot_id='other';
 if(kind==='other_stable_connection')g.stable_after.connection_epoch='other';
 if(kind==='bad_pose')g.stable_after.pose={position_m:[NaN,0,0]};
 if(kind==='held_input_stale')value.operation_events[0].reason='INPUT_STALE';
 if(kind==='missing_engine_events')delete value.operation_events;
 if(kind==='prior_concurrent_drive')value.responses.push({...drive,status:200,native_start_ms:950,native_timing:{responseEnd:100},request:{...drive.request,request_id:'overlap'}});
 assert.equal(gate(value).status,'FAIL');
});
