// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import test from 'node:test';
import {checkScanDisplay,waitForScanDisplay} from './scan_display_observation.mjs';
const sample=()=>({present:true,visible:true,frame_live:true,preview_only:false,captured_at_ms:1000.25,observed_at_ms:1699,age_ms:698.75,
 robot_id:'robot',frame_id:41,frame_captured_at_ms:1650,stage_epoch:'stage',scene_revision:'revision',connection_epoch:'connection',motion_epoch:'motion'});
test('renderer age is unchanged by a later tool callback',()=>{
 const original=sample();assert.equal(checkScanDisplay({...original,node_callback_at_ms:999999}).age_ms,698.75);
});
test('expired same-renderer sample is rejected at original700ms',()=>{
 const original=sample();assert.throws(()=>checkScanDisplay({...original,observed_at_ms:1700.25,age_ms:700}),/Stale scan/);
 assert.throws(()=>checkScanDisplay({...original,observed_at_ms:1701,age_ms:700.75}),/Stale scan/);
 assert.throws(()=>checkScanDisplay({...original,observed_at_ms:999,age_ms:-1.25}),/Stale scan/);
});
test('absence, hidden, nonfinite or missing bindings cannot pass',()=>{
 const original=sample();
 for(const delta of [{present:false},{visible:false},{frame_live:false},{preview_only:true},{preview_only:null},{captured_at_ms:NaN},{age_ms:1},{frame_id:null},{frame_id:true},{robot_id:''},{motion_epoch:''},{frame_captured_at_ms:0}])
  assert.throws(()=>checkScanDisplay({...original,...delta}));
});
test('shared original visibility window accepts absent then current, never earlier visible violations',async()=>{
 const valid={...sample(),rays_count:1,points_count:2},absent={...valid,present:false,visible:false,captured_at_ms:null,age_ms:null};
 const window={started_at_ms:1600,deadline_ms:6600,timeout_ms:5000,expected:{robot_id:'robot',connection_epoch:'connection',motion_epoch:'motion'}};
 async function run(sequence){let index=0;const records=[];const page={evaluate:async()=>sequence[index++]};
  const result=await waitForScanDisplay(page,window,{record:sample=>records.push(sample),sleep:async()=>{},clock:()=>1699});return {result,records};}
 assert.equal((await run([absent,valid])).records.length,2);
 for(const prior of [{...valid,captured_at_ms:900,age_ms:799},{...valid,preview_only:true},{...valid,motion_epoch:'other'}])
  await assert.rejects(run([prior,valid]));
 await assert.rejects(run([absent,{...absent,observed_at_ms:6601}]),/deadline/);
 const records=[];await assert.rejects(waitForScanDisplay({evaluate:async()=>{throw Error('original observe');}},window,{record:s=>records.push(s),clock:()=>1699}),/original observe/);
 assert.equal(records.length,0);
 const late=[];let calls=0;
 await assert.rejects(waitForScanDisplay({evaluate:async()=>valid},window,{record:s=>late.push(s),clock:()=>calls++?6601:1699}),/deadline/);
 assert.equal(late[0].observed_at_ms,1699);assert.equal(late[0].received_at_ms,6601);
 await assert.rejects(waitForScanDisplay({evaluate:async()=>new Promise(()=>{})},window,{record:()=>{},clock:()=>6599}),/deadline/);
});
