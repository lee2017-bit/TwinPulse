// SPDX-License-Identifier: Apache-2.0
// Visible SIM-only inverse of two completed children, not task acceptance.
import {chromium,expect} from '../apps/twinpulse-web/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs/promises';
const out=process.argv[2];if(!out)throw Error('New evidence file required');
const prior=JSON.parse(await fs.readFile('outputs/environment-task-loop-20261025-01/survey16/result.json','utf8'));
const cleanup=JSON.parse(await fs.readFile('outputs/environment-task-loop-20261025-01/survey16-cleanup.json','utf8'));
if(prior.status!=='FAIL'||cleanup.status!=='PASS'||cleanup.final.kind!=='sim')throw Error('Exact failed survey and SIM cleanup required');
const b=await chromium.connectOverCDP('http://127.0.0.1:19222');const p=b.contexts().flatMap(c=>c.pages()).find(p=>p.url().startsWith('http://127.0.0.1:8765/'));let fleet;
const row=()=>fleet?.robots?.find(r=>r.label==='Ready SIM 02');const control=p.getByRole('region',{name:'Control Ready SIM 02',exact:true});
const result={status:'FAIL',scope:'EXPLICIT_SIM_START_RESTORATION_NOT_WHOLE_TASK_SUCCESS',physical_actions:0,model_calls:0,goal:prior.start.pose,commands:['right 0.500000000 rad','backward 0.500000000 m'],requests:[]};
p.on('response',async r=>{if(new URL(r.url()).pathname==='/v1/product/robot-fleet')try{fleet=await r.json();if(r.request().method()==='POST')result.requests.push({status:r.status(),request:r.request().postDataJSON(),ack:fleet.last_command,robot:row()});}catch{}});
try{result.versions=await p.evaluate(()=>window.twinpulseDesktop?.versions());await expect.poll(()=>row()?.kind).toBe('sim');
 if(row().robot_id!==cleanup.final.robot_id||JSON.stringify(row().pose.position_m)!==JSON.stringify(cleanup.final.pose.position_m))throw Error('Original failed endpoint changed');
 for(const name of ['Connect','Prepare']){await control.getByRole('button',{name,exact:true}).click();await p.waitForTimeout(500);}
 await expect.poll(()=>row()?.applied_motion_epoch).toBe(row().motion_epoch);
 for(const text of result.commands){const input=control.getByRole('textbox',{name:'Robot command'});await input.fill(text);await p.waitForTimeout(3000);const response=p.waitForResponse(r=>new URL(r.url()).pathname==='/v1/product/robot-fleet'&&r.request().method()==='POST'&&r.request().postDataJSON()?.action==='command');await input.press('Enter');const r=await response,q=r.request().postDataJSON(),v=await r.json();if(r.status()!==200||v.last_command?.request_id!==q.request_id)throw Error('No exact command ACK');await expect.poll(()=>row()?.command?.request_id===q.request_id?row()?.command?.state:'WAIT_NEW_COMMAND',{timeout:45000}).toBe('COMPLETED');await expect.poll(()=>row()?.applied_motion_epoch).toBe(row().motion_epoch);}
 const current=row().pose.position_m,goal=result.goal.position_m;const angle=Math.atan2(Math.sin(current[2]-goal[2]),Math.cos(current[2]-goal[2]));if(Math.hypot(current[0]-goal[0],current[1]-goal[1])>.001||Math.abs(angle)>.001)throw Error('Original starting pose not restored');result.restored=row();
 for(const [name,action] of [['Stop','stop'],['Disconnect','disconnect']]){const response=p.waitForResponse(r=>new URL(r.url()).pathname==='/v1/product/robot-fleet'&&r.request().method()==='POST'&&r.request().postDataJSON()?.action===action);await control.getByRole('button',{name,exact:true}).click();const r=await response,v=await r.json(),q=r.request().postDataJSON();if(r.status()!==200||v.last_command?.request_id!==q.request_id)throw Error('No exact '+action+' ACK');if(action==='stop')await expect.poll(()=>row()?.applied_motion_epoch).toBe(row().motion_epoch);}
 await expect.poll(()=>row()?.connection_state).toBe('DISCONNECTED');result.final=row();result.status='PASS_SCOPED';
}catch(e){result.error=String(e);}finally{await fs.writeFile(out,JSON.stringify(result,null,2),{flag:'wx'});await b.close();}if(result.status!=='PASS_SCOPED')throw Error(result.error);
