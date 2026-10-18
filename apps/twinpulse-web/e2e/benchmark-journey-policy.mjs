// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
/** Fixed benchmark procedure, not a generated scene answer or robot command. */
export function stopReturnInput(previewArrival, semanticArrival, historicalSample=null) {
  for (const sample of [previewArrival, semanticArrival]) {
    if (!sample?.telemetry_available || sample.runtime_state !== 'completed' ||
        !Array.isArray(sample.position_m) || sample.position_m.length < 2 ||
        sample.position_m.slice(0,2).some(value => !Number.isFinite(value))) {
      throw new Error('BENCHMARK_STOP_START_EVIDENCE_INVALID');
    }
  }
  if (previewArrival.applied_revision !== semanticArrival.applied_revision) {
    throw new Error('BENCHMARK_STOP_REVISION_CHANGED');
  }
  let endpoint=previewArrival;
  const distance=sample=>Math.hypot(...sample.position_m.slice(0,2).map((v,i)=>v-semanticArrival.position_m[i]));
  if(distance(endpoint)<=.08&&historicalSample){
    if(!historicalSample.telemetry_available||historicalSample.runtime_state!=='running'||
        historicalSample.run_id!==previewArrival.run_id||historicalSample.applied_revision!==previewArrival.applied_revision||
        historicalSample.engine_session_id!==previewArrival.engine_session_id||historicalSample.stage_epoch!==previewArrival.stage_epoch||
        !Array.isArray(historicalSample.position_m)||historicalSample.position_m.slice(0,2).some(v=>!Number.isFinite(v)))
      throw new Error('BENCHMARK_STOP_START_EVIDENCE_INVALID');
    endpoint=historicalSample;
  }
  if (distance(endpoint) <= .08) {
    // Two overlapping 4cm arrival tolerances cannot establish a moving stop.
    throw new Error('BENCHMARK_STOP_ROUTE_TOO_SHORT');
  }
  const decimal=value=>Number(value.toFixed(6)).toString();
  return `Go to X=${decimal(endpoint.position_m[0])} Y=${decimal(endpoint.position_m[1])}`;
}

export function freshGoalReview(before,conversation,text,revision){
  const review=conversation.simulation_review;
  if(!review||review.request_id===before.simulation_review?.request_id||review.text!==text||review.scene_revision!==revision)
    throw new Error('BENCHMARK_GOAL_NOT_FRESH');
  const type=review.plan?'simulation_route_reviewed':'simulation_goal_clarification';
  const events=conversation.events.filter(e=>e.sequence>before.cursor&&e.type===type&&e.payload.scene_revision===revision);
  if(events.length!==1||review.plan&&events[0].payload.plan_id!==review.plan.plan_id||
      !review.plan&&events[0].payload.request_id!==review.request_id)throw new Error('BENCHMARK_GOAL_EVENT_UNBOUND');
  return {review,event:events[0]};
}

export function currentPlanSample(sample,plan,before,state){
  return !!sample&&sample.run_id===plan.plan_id&&sample.applied_revision===plan.scene_revision&&
    sample.engine_session_id===before.engine_session_id&&sample.stage_epoch===before.stage_epoch&&
    sample.sequence>before.sequence&&sample.telemetry_available&&sample.runtime_state===state&&!sample.safety_state;
}

export function diagnosticSnapshot(product,conversation) {
  const draft=product.workflow?.site_draft||product.site_draft;
  const sample=product.snapshot;
  return {scene_revision:draft?.revision,plan_sha256:draft?.plan_sha256,input_revision:draft?.input_revision,
    operations:(product.operations||[]).map(op=>({operation_id:op.operation_id,command_type:op.command_type})),
    snapshot:sample?Object.fromEntries(['runtime_state','telemetry_available','applied_revision','run_id','position_m'].map(k=>[k,sample[k]])):null,
    cursor:conversation.cursor};
}

export function diagnosticEvent(before,conversation,expected) {
  const kind=expected==='clarification'?'simulation_goal_clarification':'simulation_goal_rejected';
  const events=conversation.events.filter(e=>e.sequence>before.cursor&&e.type===kind);
  if(events.length!==1)throw new Error('BENCHMARK_DIAGNOSTIC_EVENT_NOT_UNIQUE');
  return events[0];
}

export function currentTargetChoice(conversation,expectedRevision) {
  const review=conversation.simulation_review;
  const cards=conversation.cards.filter(c=>c.kind==='simulation_target'&&c.state==='waiting');
  const targets=review?.choices;
  if(review?.scene_revision!==expectedRevision||cards.length!==1||!Array.isArray(targets)||
      targets.length<2||targets.length>32||new Set(targets.map(t=>t.id)).size!==targets.length||
      targets.some(t=>typeof t.id!=='string'||!t.id))throw new Error('BENCHMARK_CURRENT_TARGET_CHOICE_INVALID');
  // Frozen operator policy: resolve generic target ambiguity by saved ID,
  // never inspect the answer, choose a nearest route or mutate the scene.
  const index=targets.map((t,i)=>({id:t.id,index:i})).sort((a,b)=>a.id<b.id?-1:a.id>b.id?1:0)[0].index;
  const choice=cards[0].choices.find(c=>c.id===`object_${index}`&&c.enabled);
  if(!choice)throw new Error('BENCHMARK_TARGET_CHOICE_DISABLED');
  return {card_id:cards[0].id,choice_id:choice.id,label:choice.label,target_id:targets[index].id,
    scene_revision:expectedRevision,policy:'LEXICOGRAPHIC_CURRENT_SAVED_ID'};
}
