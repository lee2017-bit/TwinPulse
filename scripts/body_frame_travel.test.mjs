// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {measuredBodyTranslation,requireBodyTranslation} from './body_frame_travel.mjs';
const row=(p)=>({robot_id:'r',operation_id:'op',connection_epoch:'connection',pose:{position_m:p,frame_id:'isaac_world',source:'isaac_usd_kinematic',aligned:true}});
test('Original50 full10cm reverse at rotated saved yaw is not world-X undertravel',()=>{
 const a=row([2.751686479106736,.9468449085827928,-.5015999997298083]),b=row([2.6640050432887046,.9949278142030586,-.5015999997298083]);
 assert.ok(a.pose.position_m[0]-b.pose.position_m[0]<.09);
 const result=requireBodyTranslation(a,b,'backward',.09);assert.ok(Math.abs(result.forward_m+.1)<1e-12);assert.ok(Math.abs(result.lateral_m)<1e-12);
});
test('Original5cm/9cm criteria work across absolute headings and accumulated yaw',()=>{
 for(const yaw of [0,Math.PI/2,-Math.PI/2,Math.PI,-Math.PI,108.78249])for(const [direction,distance,minimum] of [['forward',.06,.05],['backward',-.1,.09]]){
  const a=row([1,2,yaw]),b=row([1+Math.cos(yaw)*distance,2+Math.sin(yaw)*distance,yaw]);
  assert.doesNotThrow(()=>requireBodyTranslation(a,b,direction,minimum));
 }
});
test('Wrong direction, only lateral, subthreshold and altered heading never pass',()=>{
 const a=row([0,0,0]);
 for(const p of [[.1,0,0],[0,.1,0],[-.089,0,0],[-.1,0,.02],[-.1,.006,0]])assert.throws(()=>requireBodyTranslation(a,row(p),'backward',.09));
 assert.throws(()=>requireBodyTranslation(a,row([.05,0,0]),'forward',.05));
 assert.doesNotThrow(()=>requireBodyTranslation(a,row([-.09,0,0]),'backward',.09));
});
test('Nonfinite, unsupported source and another actor/session fail closed',()=>{
 const a=row([0,0,0]);
 for(const p of [[NaN,0,0],[Infinity,0,0],[1e308,0,0]])assert.throws(()=>measuredBodyTranslation(a,row(p)));
 for(const key of ['robot_id','operation_id','connection_epoch']){const b=row([-.1,0,0]);b[key]='other';assert.throws(()=>measuredBodyTranslation(a,b));}
 const b=row([-.1,0,0]);b.pose.frame_id='odom';assert.throws(()=>measuredBodyTranslation(a,b));
});
