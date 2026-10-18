// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {stopReturnInput,diagnosticSnapshot,diagnosticEvent,currentTargetChoice,freshGoalReview,currentPlanSample} from './benchmark-journey-policy.mjs';
const sample=(position_m,extra={})=>({position_m,telemetry_available:true,runtime_state:'completed',applied_revision:'r1',...extra});
const ambiguous=()=>({simulation_review:{scene_revision:'r1',choices:[{id:'z'},{id:'a'}]},
  cards:[{id:'current',kind:'simulation_target',state:'waiting',choices:[
    {id:'object_0',label:'chair z',enabled:true},{id:'object_1',label:'chair a',enabled:true}]}]});
test('Current target ambiguity uses one deterministic reviewed UI choice, not nearest geometry',()=>{
  const choice=currentTargetChoice(ambiguous(),'r1');
  assert.equal(choice.target_id,'a');assert.equal(choice.choice_id,'object_1');
  assert.equal(choice.policy,'LEXICOGRAPHIC_CURRENT_SAVED_ID');
});
test('Changed revision, duplicate/stale/disabled choices never unlock a benchmark route',()=>{
  assert.throws(()=>currentTargetChoice(ambiguous(),'other'),/INVALID/);
  const duplicate=ambiguous();duplicate.cards.push(duplicate.cards[0]);
  assert.throws(()=>currentTargetChoice(duplicate,'r1'),/INVALID/);
  const disabled=ambiguous();disabled.cards[0].choices[1].enabled=false;
  assert.throws(()=>currentTargetChoice(disabled,'r1'),/DISABLED/);
});
test('Stop exercise targets the actually observed earlier free start, not a bedroom constant',()=>{
  assert.equal(stopReturnInput(sample([1.25,-.75,0]),sample([2,1,0])),'Go to X=1.25 Y=-0.75');
});

test('Diagnostic state uses actual workflow and exact operation/idle pose identity',()=>{
  const product={workflow:{site_draft:{revision:'scene',plan_sha256:'plan',input_revision:'input'}},
    operations:[{operation_id:'op',command_type:'run',private:'NOT_EXPORTED'}],
    snapshot:sample([1,2,0])};
  const snapshot=diagnosticSnapshot(product,{cursor:3});
  assert.equal(snapshot.scene_revision,'scene');assert.equal(snapshot.cursor,3);
  assert.deepEqual(snapshot.operations,[{operation_id:'op',command_type:'run'}]);
  assert.deepEqual(snapshot.snapshot.position_m,[1,2,0]);
});
test('Only one fresh goal event is allowed, never a previous or duplicate failure',()=>{
  const event={sequence:4,type:'simulation_goal_rejected'};
  assert.equal(diagnosticEvent({cursor:3},{events:[{...event,sequence:2},event]},'rejection'),event);
  assert.throws(()=>diagnosticEvent({cursor:4},{events:[event]},'rejection'),/NOT_UNIQUE/);
  assert.throws(()=>diagnosticEvent({cursor:3},{events:[event,event]},'rejection'),/NOT_UNIQUE/);
});
test('A completed or changed/unknown position is never invented as a running stop',()=>{
  assert.throws(()=>stopReturnInput(sample([0,0]),sample([.04,0])),/ROUTE_TOO_SHORT/);
  assert.throws(()=>stopReturnInput(sample([0,0]),sample([1,0],{applied_revision:'r2'})),/REVISION_CHANGED/);
  assert.throws(()=>stopReturnInput(sample([0,0]),sample([1,0],{runtime_state:'running'})),/EVIDENCE_INVALID/);
  assert.throws(()=>stopReturnInput(sample([NaN,0]),sample([1,0])),/EVIDENCE_INVALID/);
});

test('Old preview or unrelated completed observations cannot acknowledge a new semantic goal',()=>{
  const before={cursor:10,simulation_review:{request_id:'old'}};
  const review={request_id:'fresh',text:'Go to desk',scene_revision:'r1',plan:{plan_id:'new-plan'}};
  const event={sequence:11,type:'simulation_route_reviewed',payload:{scene_revision:'r1',plan_id:'new-plan'}};
  assert.equal(freshGoalReview(before,{simulation_review:review,events:[event]},'Go to desk','r1').review,review);
  assert.throws(()=>freshGoalReview(before,{simulation_review:{...review,request_id:'old'},events:[event]},'Go to desk','r1'),/NOT_FRESH/);
  assert.throws(()=>freshGoalReview(before,{simulation_review:review,events:[{...event,sequence:10}]},'Go to desk','r1'),/UNBOUND/);
  assert.throws(()=>freshGoalReview(before,{simulation_review:review,events:[event]},'Go to chair','r1'),/NOT_FRESH/);
  const initial=sample([0,0],{engine_session_id:'e',stage_epoch:'s',sequence:1});
  const plan={plan_id:'new-plan',scene_revision:'r1'};
  assert.equal(currentPlanSample({...initial,run_id:'old-plan',sequence:2},plan,initial,'completed'),false);
  assert.equal(currentPlanSample({...initial,run_id:'new-plan',sequence:2},plan,initial,'completed'),true);
  assert.equal(currentPlanSample({...initial,run_id:'new-plan',sequence:2,stage_epoch:'changed'},plan,initial,'completed'),false);
});

test('A short return can use an actually observed earlier preview position, never invented coordinates',()=>{
  const arrival=sample([.4,0],{run_id:'preview'});
  const moving=sample([.02,0],{run_id:'preview',runtime_state:'running'});
  assert.equal(stopReturnInput(arrival,sample([.42,0]),moving),'Go to X=0.02 Y=0');
  assert.throws(()=>stopReturnInput(arrival,sample([.42,0]),{...moving,run_id:'other'}),/INVALID/);
});
