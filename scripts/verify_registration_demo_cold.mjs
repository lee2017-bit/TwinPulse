// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// Actual same installed BrowserWindow; original result is read-only input.
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {expect} from '../apps/twinpulse-web/node_modules/@playwright/test/index.mjs';
import {attachPoweredSession} from './robot_powered_ui_session.mjs';
const [out,priorPath]=process.argv.slice(2);if(!out||!priorPath)throw Error('New output and original fresh demo required');
const raw=await fs.readFile(priorPath),prior=JSON.parse(raw);
if(prior.status!=='PASS_SEPARATE_FRESH_DEMO'||!prior.registration_event)throw Error('Original actual demo not accepted');
const s=await attachPoweredSession(out),page=s.page,result={status:'IN_PROGRESS',identity:s.identity,project:prior.project,
 source_sha256:createHash('sha256').update(raw).digest('hex'),physical:'OFF_NO_CONTACT',steps:[]};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function poll(fn){const until=Date.now()+30000;while(Date.now()<until){if(fn())return;await sleep(100);}throw Error('Actual observed restore timeout');}
let finished=false;
try{
 await expect(page.getByText('Isaac connected',{exact:true}).first()).toBeVisible({timeout:120000});
 await page.getByRole('button',{name:'Open '+prior.project,exact:true}).click();
 await poll(()=>s.conversation?.project_id===prior.project&&s.fleet?.robots.some(r=>r.robot_id===prior.registration_event.payload.registration.robot_id));
 const events=s.conversation.events.filter(e=>e.type==='fleet_sim_registered'&&e.payload.registration.robot_id===prior.registration_event.payload.registration.robot_id);
 if(events.length!==1||JSON.stringify(events[0])!==JSON.stringify(prior.registration_event))throw Error('Saved event missing, changed or duplicated');
 const row=s.fleet.robots.find(r=>r.robot_id===events[0].payload.registration.robot_id);
 if(row.connection_state!=='DISCONNECTED'||row.connection_epoch||row.motion_epoch||row.operation_id)throw Error('Restored registration resumed authority');
 const message=s.conversation.messages.find(m=>m.message_id===events[0].payload.message_id);
 if(!message||message.reply_to!==events[0].payload.menu_message_id)throw Error('Menu reply linkage lost');
 await page.getByText('SIM robot registered: TurtleBot3.',{exact:false}).scrollIntoViewIfNeeded();await s.shot('restored-registration');await sleep(3000);
 if(s.errors.length)throw Error('Unclassified restore error: '+JSON.stringify(s.errors));
 result.status='PASS_CHAT_REGISTRATION_COLD';result.event=events[0];result.message=message;result.robot=row;
 result.video=await s.finishVideo();finished=true;
 const closing=page.waitForEvent('close',{timeout:20000});await page.getByRole('button',{name:'Exit TwinPulse',exact:true}).click();await closing;
}catch(error){result.status='FAIL_CHAT_REGISTRATION_COLD';result.error=String(error);await s.shot('failure').catch(()=>{});if(!finished)await s.finishVideo().catch(()=>{});}
finally{await fs.writeFile(path.join(out,'result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify({status:result.status,error:result.error}));await s.browser.close();}
if(result.status!=='PASS_CHAT_REGISTRATION_COLD')process.exitCode=1;
