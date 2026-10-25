// SPDX-License-Identifier: Apache-2.0
// Device-free recorder unit tests; no App or provider activity.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {beginGestureAttempt,gestureAttemptDiagnostic} from './roomplan_gesture_audit.mjs';
const before={robot_id:'robot',operation_id:'operation',connection_epoch:'connection',motion_epoch:'held',control_state:'READY'};
const request=(action='drive')=>({action,request_id:action,robot_id:'robot',connection_epoch:'connection',motion_epoch:'held',payload:{direction:'forward',sequence:5,expires_at_ms:1350}});
function attempt(){return beginGestureAttempt({direction:'forward',before,auditStart:1,responseStart:0,failedRequestStart:0,observedAtMs:900});}
const down={type:'pointerdown',at:1000,native_event_ms:314.37,button:'Hold forward',trusted:true};
const up={type:'pointerup',at:2200,native_event_ms:1514.38,button:'Hold forward',trusted:true};
test('failed held request retains original before/epoch, actual events and automatic Stop chronology',()=>{
 const a=attempt();a.status='FAIL';a.up_requested_at_ms=2199;a.up_returned_at_ms=2201;
 const audit={status:'CAPTURED',events:[{type:'unrelated'},down,{type:'blur',at:1500,native_event_ms:814.4,trusted:true},up]};
 const rows=[{at:1600,path:'/v1/product/robot-fleet',method:'POST',status:200,request:request('stop'),native_start_ms:1590,native_timing:{responseEnd:10}}];
 const failures=[{at:1550,path:'/v1/product/robot-fleet',method:'POST',request:request(),error:'net::ERR_ABORTED'}];
 const result=gestureAttemptDiagnostic(a,{audit,rows,failedRequests:failures,finalRobot:{...before,motion_epoch:'stopped'},error:'Release Stop waiter expired'});
 assert.equal(result.status,'FAIL');assert.deepEqual(result.before,before);assert.equal(result.expected_input_identity.motion_epoch,'held');
 assert.deepEqual(result.actual_down,down);assert.deepEqual(result.actual_up,up);assert.equal(result.interruptions[0].at,1500);
 assert.equal(result.observed_requests[0].native_start_ms,1590);assert.ok(result.observed_requests[0].native_start_ms<result.actual_up.at);
 assert.equal(result.observed_failed_requests[0].request.payload.sequence,5);assert.equal(result.failure,'Release Stop waiter expired');
});
test('missing actual up stays null and Node call markers never manufacture a release',()=>{
 const a=attempt();a.status='FAIL';a.up_requested_at_ms=2200;a.up_returned_at_ms=2201;
 const r=gestureAttemptDiagnostic(a,{audit:{status:'CAPTURED',events:[{},down]},error:'failed'});
 assert.equal(r.actual_up,null);assert.equal(r.status,'FAIL');assert.deepEqual(r.actual_down,down);
});
test('an actual up outside the original button retains its time and target without inventing a matching release',()=>{
 const otherUp={...up,button:'Stop'},r=gestureAttemptDiagnostic(attempt(),{audit:{status:'CAPTURED',events:[{},down,otherUp]}});
 assert.deepEqual(r.actual_up,otherUp);assert.equal(r.up_button_matches_direction,false);assert.notEqual(r.status,'PASS');
});
test('a completed attempt keeps its original array window instead of borrowing later gesture events',()=>{
 const a=attempt();a.audit_end_index=3;
 const r=gestureAttemptDiagnostic(a,{audit:{status:'CAPTURED',events:[{},down,up,{type:'blur',at:9000}]}});
 assert.deepEqual(r.passive_events,[down,up]);assert.deepEqual(r.interruptions,[]);
});
test('unavailable browser audit is explicit, not an empty successful gesture',()=>{
 const r=gestureAttemptDiagnostic(attempt(),{audit:{status:'UNAVAILABLE_PAGE_CLOSED'},error:'closed'});
 assert.equal(r.passive_events,null);assert.equal(r.interruptions,null);assert.equal(r.actual_up,null);assert.equal(r.audit_status,'UNAVAILABLE_PAGE_CLOSED');
 assert.notEqual(r.status,'PASS');
});
test('original before, all event values and input records remain unchanged',()=>{
 const a=attempt(),audit={status:'CAPTURED',events:[{},down,up]},rows=[{request:request(),native_timing:{startTime:1200}}];
 const inputs=structuredClone({a,audit,rows});gestureAttemptDiagnostic(a,{audit,rows});assert.deepEqual({a,audit,rows},inputs);
 before.motion_epoch='later';assert.equal(a.before.motion_epoch,'held');before.motion_epoch='held';
});
test('other connection input and earlier observations are not relabelled into the failed gesture',()=>{
 const a=attempt();a.response_start_index=1;a.failed_request_start_index=1;
 const rows=[{request:request()},{request:{...request(),connection_epoch:'other'}},{request:request('stop')}];
 const r=gestureAttemptDiagnostic(a,{audit:{status:'CAPTURED',events:[{},down,up]},rows,failedRequests:[{request:request()}]});
 assert.equal(r.observed_requests.length,1);assert.equal(r.observed_requests[0].response_index,2);assert.equal(r.observed_failed_requests.length,0);
});
