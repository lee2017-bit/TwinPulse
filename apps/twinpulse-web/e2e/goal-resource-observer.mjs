// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// Same built product, synthetic native world and actual Isaac. Observe live
// resources without the automation framework's response-body capture agent.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {openOwnedChrome} from './owned-chrome-observer.mjs';
const output=process.env.TWINPULSE_VIEW_OUTPUT;
if(!output)throw new Error('Explicit isolated output required');
const duration=Number(process.env.TWINPULSE_SOAK_SECONDS??0);
assert.ok(duration===0||duration===1800);
const result={status:'FAIL',checks:[],robot_connections:0,qualification:'EXPLICIT_TEST_ONLY',
  observer:'OWNED_CDP_NO_NETWORK_CAPTURE',cache_clearing:false,forced_gc:false};
let chrome;
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(query,test,timeout=65000){
  const deadline=performance.now()+timeout;
  while(performance.now()<deadline){const value=await query();if(test(value))return value;await wait(200);}
  throw new Error('UI_CONDITION_DEADLINE');
}
try{
  chrome=await openOwnedChrome(output);result.chrome_version=chrome.version;
  await chrome.navigate(`${process.env.TWINPULSE_VIEW_URL}/#bootstrap=${encodeURIComponent(process.env.TWINPULSE_VIEW_BOOTSTRAP)}`);
  const chat=()=>chrome.evaluate(`fetch('/v1/product/conversation').then(r=>r.json())`);
  const state=()=>chrome.evaluate(`fetch('/v1/product/state').then(r=>r.json())`);
  const buttonReady=label=>chrome.evaluate(`(()=>{const b=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===${JSON.stringify(label)});return !!b&&!b.disabled&&b.getClientRects().length>0;})()`);
  const choiceReady=async label=>await buttonReady(label)||await chrome.evaluate(`[...document.querySelectorAll('.chat-question label')].some(l=>l.textContent.trim()===${JSON.stringify(label)}&&l.querySelector('input[type="radio"]:not(:disabled)')&&l.getClientRects().length>0)`);
  const chooseCurrent=async label=>{
    await until(()=>choiceReady(label),Boolean,15000);
    if(await buttonReady(label))return chrome.click(label);
    await chrome.chooseRadio(label);
    await until(()=>buttonReady('Continue'),Boolean,15000);
    await chrome.click('Continue');
  };
  await until(state,c=>c.snapshot?.capabilities?.includes('exact_goal_demonstration_v1'),150000);
  await until(()=>chrome.evaluate(`(()=>{const t=document.querySelector('textarea[aria-label="Message TwinPulse"]');return !!t&&!t.disabled;})()`),Boolean,15000);
  await chrome.message('Go x=.05 y=-.6');
  const preview=await until(chat,c=>c.navigation?.demonstration?.state==='COMPLETED'&&c.navigation?.review?.plan);
  assert.equal(preview.navigation.demonstration.review_id,preview.navigation.review.plan.plan_id);
  assert.equal(preview.navigation.demonstration.robot_review_parked,true);
  const plan=preview.navigation.review.plan;
  await until(()=>choiceReady('Confirm goal route · bounded movement'),Boolean,15000);
  await chrome.screenshot('goal-preview.png');await chooseCurrent('Confirm goal route · bounded movement');
  await until(()=>chrome.evaluate(`!!document.querySelector('[aria-label="Current worker telemetry"]')`),Boolean,15000);
  const arrived=await until(chat,c=>c.navigation?.job?.state==='MISSION_ARRIVED');
  assert.deepEqual(arrived.navigation.job.approved_preview,plan);
  assert.equal(arrived.navigation.job.telemetry,null);
  const telemetry=arrived.navigation.job.events.filter(e=>e.kind==='mission_telemetry');
  assert.ok(telemetry.some(e=>e.data.telemetry.battery?.measured_capacity===false));
  assert.ok(telemetry.some(e=>e.data.telemetry.next_waypoint));
  await chooseCurrent('Repeat A ↔ B');
  const started=performance.now(),samples=[];
  if(duration)fs.writeFileSync(path.join(output,'soak-started'),'');
  while(true){
    const conversation=await chat(),task=conversation.navigation?.task_loop;
    assert.equal(task?.worker_active,true);assert.match(task.state,/^(PREPARING|DRIVING)$/);
    assert.ok(conversation.events.length<=2100&&conversation.messages.length<=1000&&conversation.cards.length<=500);
    const metrics=(await chrome.send('Performance.getMetrics')).metrics;
    const heap=metrics.find(m=>m.name==='JSHeapUsedSize')?.value;
    assert.ok(heap<256*1024**2);
    const frame=await chrome.evaluate(`(()=>{const c=document.querySelector('canvas[aria-label="Current Isaac Digital Twin render"]');return c?.dataset.frameId??null;})()`);
    const sample={elapsed_s:(performance.now()-started)/1000,state:task.state,completed_legs:task.completed_legs,
      events:conversation.events.length,messages:conversation.messages.length,cards:conversation.cards.length,
      js_heap_bytes:heap,painted_frame_id:frame};
    samples.push(sample);fs.appendFileSync(path.join(output,'browser-soak.jsonl'),JSON.stringify(sample)+'\n');
    if(duration?(performance.now()-started>=duration*1000):task.completed_legs>=6)break;
    if(!duration&&performance.now()-started>450000)throw new Error('REPEAT_LEG_DEADLINE');
    await wait(10000);
  }
  assert.ok(new Set(samples.filter(s=>s.painted_frame_id!==null).map(s=>s.painted_frame_id)).size>=6);
  result.soak={elapsed_s:(performance.now()-started)/1000,completed_legs:samples.at(-1).completed_legs,samples,
    duration_policy:'REAL_BROWSER_PERFORMANCE_WALL_TIME_NO_ACCELERATION'};
  if(duration)fs.writeFileSync(path.join(output,'soak-ended'),'');
  result.process_info=await chrome.processInfo();
  result.loop_before_stop=(await chat()).navigation.task_loop;
  await chrome.screenshot('loop-active.png');await chrome.click('Stop after current command');
  const stopped=await until(chat,c=>!c.navigation?.task_loop?.worker_active&&c.navigation?.task_loop?.state==='STOPPED',45000);
  result.loop_after_stop=stopped.navigation.task_loop;
  assert.deepEqual(stopped.messages.filter(m=>m.operation_id===result.loop_after_stop.task_id&&m.status==='pending'),[]);
  const operations=(await state()).operations.length;
  await chrome.reload();await until(()=>chrome.evaluate(`!!document.querySelector('textarea[aria-label="Message TwinPulse"]')`),Boolean,15000);
  const reloaded=await chat();assert.equal(reloaded.navigation.task_loop.worker_active,false);
  assert.equal((await state()).operations.length,operations);assert.deepEqual(chrome.pageErrors,[]);
  await chrome.screenshot('loop-stopped-reloaded.png');
  result.checks.push('trusted UI input → exact actual Isaac preview → one Confirm → native synthetic arrival',
    'one Repeat approval; fresh bounded A/B legs, source/time-bound live telemetry and actual painted frames',
    'ordinary Stop prevents next leg; reload starts no operation; fixed wall-time/resource/history budgets unchanged',
    'no Network capture domain, cache clearing, forced GC, accelerated clock or robot connection');
  result.status='PASS';
}catch(error){result.error=String(error).slice(0,1000);if(chrome){
  result.failure_ui=await chrome.evaluate('document.body.innerText.slice(-10000)').catch(()=>null);
  await chrome.screenshot('failure.png').catch(()=>{});
}}finally{
  if(chrome){try{result.chrome_exit_code=await chrome.close();}catch(error){result.status='FAIL';result.cleanup_error=String(error);}}
  fs.writeFileSync(path.join(output,'browser.json'),JSON.stringify(result,null,2),{flag:'wx'});
}
process.exitCode=result.status==='PASS'?0:1;
