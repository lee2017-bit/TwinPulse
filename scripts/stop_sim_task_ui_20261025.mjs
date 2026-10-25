// SPDX-License-Identifier: Apache-2.0
// Normal UI cleanup only. Never Connect/Prepare/Arm or select a physical robot.
import {chromium,expect} from '../apps/twinpulse-web/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs/promises';
const [output,label]=process.argv.slice(2);if(!output||!label)throw Error('New result and SIM label required');
const b=await chromium.connectOverCDP('http://127.0.0.1:19222');
const p=b.contexts().flatMap(c=>c.pages()).find(p=>p.url().startsWith('http://127.0.0.1:8765/'));
const value={status:'FAIL',scope:'NO_MODEL_SIM_ONLY_UI_CLEANUP',physical_actions:0,acks:[]};let row;
p.on('response',async r=>{if(new URL(r.url()).pathname==='/v1/product/robot-fleet')try{row=(await r.json()).robots.find(x=>x.label===label);}catch{}});
try{
 const fleet=p.getByRole('region',{name:'Robot fleet',exact:true});await fleet.getByRole('button',{name:new RegExp(label+' SIM ')}).click();
 const control=p.getByRole('region',{name:'Control '+label,exact:true});await expect.poll(()=>row?.kind).toBe('sim');
 for(const [name,action] of [['Stop','stop'],['Turn LiDAR off','lidar'],['Disconnect','disconnect']]){
  if(action==='lidar'&&row.lidar_state==='OFF')continue;
  const response=p.waitForResponse(r=>new URL(r.url()).pathname==='/v1/product/robot-fleet'&&r.request().method()==='POST'&&r.request().postDataJSON()?.action===action);
  await control.getByRole('button',{name,exact:true}).click();const r=await response,data=await r.json(),q=r.request().postDataJSON();
  if(r.status()!==200||data.last_command?.request_id!==q.request_id)throw Error('Missing exact '+action+' ACK');
  const result=data.robots.find(x=>x.robot_id===q.robot_id);value.acks.push({request:q,ack:data.last_command,row:result});
  if(action!=='disconnect')await expect.poll(()=>row?.applied_motion_epoch).toBe(result.motion_epoch);
 }
 await expect.poll(()=>row?.connection_state).toBe('DISCONNECTED');value.status='PASS';value.final=row;
}catch(e){value.error=String(e);}finally{await fs.writeFile(output,JSON.stringify(value,null,2),{flag:'wx'});await b.close();}
if(value.status!=='PASS')throw Error(value.error);
