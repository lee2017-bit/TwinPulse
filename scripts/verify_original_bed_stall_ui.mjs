// SPDX-License-Identifier: Apache-2.0
// Original saved scene/goal regression via the installed Test BrowserWindow.
// Not fresh generation, physical evidence, or an API-injected reproduction.
import {expect} from '../apps/twinpulse-web/node_modules/@playwright/test/index.mjs';
import {attachPoweredSession} from './robot_powered_ui_session.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';
import{createHash}from'node:crypto';
const out=process.argv[2];if(!out)throw Error('New output required');
const originalStart=process.argv.includes('--original-start'),label=originalStart?'Original bed '+path.basename(out):'TurtleBot3';
const s=await attachPoweredSession(out),p=s.page;
const result={status:'IN_PROGRESS',identity:s.identity,scope:'ORIGINAL_SAVED_SCENE_SAME_BED_NO_HARDWARE',steps:[]};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const poll=async(fn,ms=30000)=>{const until=Date.now()+ms;while(Date.now()<until){if(fn())return;await sleep(100);}throw Error('Observed state timeout');};
const robot=()=>s.fleet?.robots.find(r=>r.label===label);
const drawer=()=>p.getByRole('region',{name:'Control '+label,exact:true});
try{
 await expect(p.getByText('Isaac connected',{exact:true}).first()).toBeVisible({timeout:120000});
 if(!await p.locator('.chat-sidebar-slot').isVisible())await p.getByRole('button',{name:'Toggle conversations and projects',exact:true}).click();
 await p.getByRole('button',{name:'Open chat_mvewllbw_bcfb924c',exact:true}).click();
 await expect(p.getByRole('banner')).toContainText('chat_mvewllbw_bcfb924c');
 const reopen=p.getByRole('button',{name:'Reopen saved scene',exact:true});if(await reopen.isVisible())await reopen.click();
 if(!await p.getByRole('img',{name:'Current Isaac Digital Twin render',exact:true}).isVisible()){
  const view=p.getByRole('button',{name:'View current Twin',exact:true});
  if(!await view.isVisible())await p.getByRole('button',{name:'Current Twin and SIM controls',exact:true}).click();
  await view.click();
 }
 await expect(p.getByRole('img',{name:'Current Isaac Digital Twin render',exact:true})).toBeVisible({timeout:120000});
 if(originalStart){
  const file='outputs/command-draft-enter-20261019/failure-demo03-logs/after-exit/07-2802fd74905d4c4d9879277ac17e1089.json';
  const bytes=await fs.readFile(file),record=JSON.parse(bytes),index=record.events.findIndex(e=>e.kind==='command_accepted'&&e.command_id==='5ea6a35d-8b77-4fe3-bba1-87b75ca8a42f');
  if(createHash('sha256').update(bytes).digest('hex')!=='66c960bc62fe70b3fc9a5be9106d095cb57c5164023e5d9255aa261831c94096')throw Error('Original immutable operation SHA mismatch');
  if(index<0)throw Error('Original request missing');
  const prior=record.events.slice(0,index).findLast(e=>e.kind==='engine_observation'&&e.position_m);
  result.expected_scene_revision=record.manifest.source_twin_context.scene_revision;
  result.original_bed_goal=record.events.find(e=>e.kind==='navigation_state'&&e.command?.request_id==='5ea6a35d-8b77-4fe3-bba1-87b75ca8a42f'&&e.command?.goal_xy)?.command;
  if(!result.original_bed_goal?.target_id)throw Error('Original bed target receipt missing');
  result.original_start_source={file,sha256:createHash('sha256').update(bytes).digest('hex'),event_sequence:prior.event_sequence,position_m:prior.position_m};
  await p.getByRole('button',{name:'Manage robot fleet',exact:true}).click();
  await p.getByText('Add SIM robot',{exact:true}).click();
  await p.getByRole('textbox',{name:'Name',exact:true}).fill(label);
  for(const [i,name] of ['X (m)','Y (m)','Yaw (rad)'].entries())await p.getByRole('spinbutton',{name,exact:true}).fill(String(prior.position_m[i]));
  await p.getByRole('button',{name:'Add SIM robot',exact:true}).click();await poll(()=>!!robot());
  await p.getByRole('button',{name:'Manage robot fleet',exact:true}).click();
 }
 await poll(()=>!!robot());await s.shot('original-scene');
 await p.locator('.robot-fleet-row').filter({hasText:label}).click();
 await drawer().getByRole('button',{name:'Connect',exact:true}).click();await poll(()=>robot()?.connection_state==='CONNECTED');
 await expect(drawer().getByRole('button',{name:'Prepare',exact:true})).toBeEnabled({timeout:30000});
 await drawer().getByRole('button',{name:'Prepare',exact:true}).click();
 const on=drawer().getByRole('button',{name:'Turn LiDAR on',exact:true});if(await on.isVisible())await on.click();
 await poll(()=>robot()?.lidar_state==='STREAMING');
 result.start_pose=structuredClone(robot().pose);result.operation_id=robot().operation_id;
 result.source_twin_context=structuredClone(robot().source_twin_context);
 if(originalStart&&result.source_twin_context?.scene_revision!==result.expected_scene_revision)throw Error('Wrong saved scene revision; not the original failure');
 for(const kind of ['bed','chair']){
  await s.note('Original scene destination '+kind);const input=drawer().getByRole('textbox',{name:'Robot command',exact:true});
  const previous=robot().command?.request_id;await input.fill('Go to the nearest '+kind);await sleep(3000);await input.press('Enter');
  await poll(()=>robot()?.command?.request_id!==previous&&robot()?.command?.target_kind===kind);
  await poll(()=>['ARRIVED','FAILED','CANCELLED'].includes(robot()?.command?.state),125000);
  result.steps.push({kind,command:structuredClone(robot().command),pose:structuredClone(robot().pose)});await s.shot(kind+'-result');
  if(robot().command.state!=='ARRIVED')throw Error(kind+' failed: '+robot().reason);
  if(originalStart&&kind==='bed'&&(robot().command.target_id!==result.original_bed_goal.target_id||
    robot().command.goal_xy.some((v,i)=>Math.abs(v-result.original_bed_goal.goal_xy[i])>1e-6)))throw Error('Different original bed approach goal');
 }
 await p.getByRole('button',{name:'Stop all',exact:true}).click();
 result.status='PASS_ORIGINAL_SAVED_SCENE_GOALS';
}catch(e){result.status='FAIL';result.error=String(e);await s.shot('failure').catch(()=>{});}
finally{await s.finishVideo().catch(e=>result.video_error=String(e));await fs.writeFile(path.join(out,'result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));await s.browser.close();}
if(result.status==='FAIL')process.exitCode=1;
