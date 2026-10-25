// SPDX-License-Identifier: Apache-2.0
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {recordStopReceipt,assertFinalStopReceipt,exactStopAllApplied} from './control_stop_receipt.mjs';
const row=(id,epoch)=>({robot_id:id,operation_id:'op-'+id,connection_epoch:'connection-'+id,motion_epoch:epoch,applied_motion_epoch:epoch,control_state:'PAUSED'});
const fixture=()=>{
 const meta={action:'stop_all',request_id:'stop-id',status:200},robots=[row('A','new-A'),row('B','new-B')];
 recordStopReceipt(meta,{revision:42,robots});
 return {fleet_requests:[meta],final_fault_recovery:{stop_request_id:'stop-id',stopped_robots:robots,before_stop_robots:[row('A','old-A'),row('B','old-B')]}};
};
test('both single Stop and Stop all preserve actual returned identities',()=>{
 for(const action of ['stop','stop_all']){const meta={action};recordStopReceipt(meta,{revision:3,robots:[row('A','new')]});assert.equal(meta.result_revision,3);assert.equal(meta.result_robots[0].operation_id,'op-A');}
});
test('ordinary responses do not become invented Stop receipts',()=>{const meta={action:'drive'};recordStopReceipt(meta,{revision:1,robots:[]});assert.equal(meta.result_robots,undefined);});
test('complete exact Stop all receipt is accepted',()=>assert.doesNotThrow(()=>assertFinalStopReceipt(fixture())));
test('original omitted Stop all body is rejected',()=>{const value=fixture();delete value.fleet_requests[0].result_robots;assert.throws(()=>assertFinalStopReceipt(value));});
test('old/wrong operation or unapplied epoch never passes',()=>{
 for(const mutate of [v=>v.fleet_requests[0].result_robots[0].operation_id='other',v=>v.final_fault_recovery.stopped_robots[0].applied_motion_epoch='old',v=>v.final_fault_recovery.before_stop_robots[0].motion_epoch='new-A']){
  const value=fixture();mutate(value);assert.throws(()=>assertFinalStopReceipt(value));}
});

const observation=()=>{
 const before=[{...row('A','old-A'),kind:'sim'},{...row('B','old-B'),kind:'sim'}];
 const response={revision:42,robots:[{...row('A','new-A'),kind:'sim'},{...row('B','new-B'),kind:'sim'}]};
 return {before,response,current:structuredClone(response)};
};
test('own final Stop requires both exact new epochs at or after its revision',()=>{
 const v=observation();assert.equal(exactStopAllApplied(v.before,v.response,v.current),true);
});
test('already-paused original snapshot cannot acknowledge newly clicked Stop',()=>{
 const v=observation();v.current={revision:41,robots:structuredClone(v.before)};
 assert.equal(exactStopAllApplied(v.before,v.response,v.current),false);
 v.current.revision=43;assert.equal(exactStopAllApplied(v.before,v.response,v.current),false);
});
test('wrong or missing operation, connection, epoch and physical rows never acknowledge SIM Stop',()=>{
 for(const change of [v=>v.response.robots[0].operation_id='other',v=>v.current.robots[1].connection_epoch='other',
  v=>v.current.robots[0].applied_motion_epoch='old-A',v=>v.response.robots[0].motion_epoch='old-A',
  v=>v.current.robots.pop(),v=>v.current.robots[0].kind='physical',v=>v.response.revision=undefined]){
  const v=observation();change(v);assert.equal(exactStopAllApplied(v.before,v.response,v.current),false);
 }
});
