// SPDX-License-Identifier: Apache-2.0
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {recordStopReceipt,assertFinalStopReceipt} from './control_stop_receipt.mjs';
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
