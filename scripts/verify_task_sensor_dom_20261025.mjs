// SPDX-License-Identifier: Apache-2.0
// Separate current-release sensor/decoded-render journey, not a task retry.
// Ordinary installed UI only: zero model calls, translation or physical actions.
import {chromium,expect} from '../apps/twinpulse-web/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs/promises';import path from 'node:path';
const output=process.argv[2];if(!output)throw Error('New output required');await fs.mkdir(output,{recursive:false});
const b=await chromium.connectOverCDP('http://127.0.0.1:19222'),p=b.contexts().flatMap(c=>c.pages()).find(p=>p.url().startsWith('http://127.0.0.1:8765/'));
const frames=new Map();let fleet;const r={status:'FAIL',scope:'SEPARATE_SENSOR_DOM_NOT_TASK_CONTINUATION',model_calls:0,physical_actions:0,motion_commands:0};
const label='Task Survey Final',robot=()=>fleet?.robots.find(v=>v.label===label),control=p.getByRole('region',{name:'Control '+label,exact:true});
const pending=new Set();p.on('response',response=>{const task=(async()=>{const u=new URL(response.url());
 if(u.pathname==='/v1/product/robot-fleet')try{fleet=await response.json();}catch{}
 if(u.pathname==='/v1/product/viewport/current')try{const f=JSON.parse(response.headers()['x-twinpulse-viewport']).frame;frames.set(String(f.frame_id),f);if(frames.size>64)frames.delete(frames.keys().next().value);}catch{}
})();pending.add(task);void task.finally(()=>pending.delete(task));});
async function action(name,predicate){const response=p.waitForResponse(v=>new URL(v.url()).pathname==='/v1/product/robot-fleet'&&v.request().method()==='POST'&&predicate(v.request().postDataJSON()));
 await control.getByRole('button',{name,exact:true}).click();const v=await response,data=await v.json(),q=v.request().postDataJSON(),row=data.robots.find(x=>x.robot_id===q.robot_id);
 if(v.status()!==200||data.last_command.request_id!==q.request_id||data.last_command.robot_id!==q.robot_id)throw Error('Missing exact UI ACK');return{request:q,ack:data.last_command,robot:row};}
async function drawn(after,scan){let dom,frame;const canvas=p.getByRole('img',{name:'Current Isaac Digital Twin render',exact:true});
 await expect.poll(async()=>{dom=await canvas.evaluate(c=>({frame_id:c.dataset.frameId,captured_at_ms:Number(c.dataset.capturedAt),scene:c.dataset.sceneRevision,stage:c.dataset.stageEpoch,live:c.dataset.live,width:c.width,height:c.height,
   colors:new Set(Array.from(c.getContext('2d').getImageData(0,0,c.width,c.height).data).filter((_,i)=>i%97===0)).size})).catch(()=>null);
   frame=dom&&frames.get(dom.frame_id);return !!(frame&&dom.live==='true'&&dom.captured_at_ms>after&&dom.scene===frame.applied_revision&&dom.stage===frame.stage_epoch&&dom.captured_at_ms===frame.captured_at_ms&&dom.colors>12&&!!frame.lidar_overlay===scan);
 },{timeout:20000}).toBe(true);
 return{dom,frame};}
try{
 r.versions=await p.evaluate(()=>window.twinpulseDesktop.versions());await p.getByRole('region',{name:'Robot fleet',exact:true}).getByRole('button',{name:new RegExp(label+' SIM ')}).click();
 await expect.poll(()=>robot()?.kind).toBe('sim');
 await action('Connect',q=>q.action==='connect');await expect(control.getByRole('button',{name:'Prepare',exact:true})).toBeEnabled();await action('Prepare',q=>q.action==='prepare');
 await expect.poll(()=>robot()?.control_state).toMatch(/PAUSED|READY/);
 r.on=await action('Turn LiDAR on',q=>q.action==='lidar'&&q.payload.enabled);await expect.poll(()=>robot()?.lidar_state).toBe('STREAMING');r.on_drawn=await drawn(0,true);
 await expect(p.getByLabel('Latest frame-bound simulated LiDAR hits',{exact:true})).toBeVisible();await p.screenshot({path:path.join(output,'01-on.png')});
 r.stop=await action('Stop',q=>q.action==='stop');await expect.poll(()=>robot()?.applied_motion_epoch).toBe(r.stop.robot.motion_epoch);r.stop.applied=robot();
 const at=Date.now();r.off=await action('Turn LiDAR off',q=>q.action==='lidar'&&q.payload.enabled===false);await expect.poll(()=>robot()?.applied_motion_epoch).toBe(r.off.robot.motion_epoch);
 r.off_drawn=await drawn(at,false);r.off.observed=robot();await expect(p.getByLabel('Latest frame-bound simulated LiDAR hits',{exact:true})).toHaveCount(0);await expect(p.getByText('LiDAR sensor: OFF',{exact:true})).toBeVisible();
 if(robot().scan!==null||robot().connection_state!=='CONNECTED')throw Error('OFF did not clear scan with connection retained');await p.screenshot({path:path.join(output,'02-off-connected.png')});
 r.disconnect=await action('Disconnect',q=>q.action==='disconnect');await expect.poll(()=>robot()?.connection_state).toBe('DISCONNECTED');r.status='PASS_SCOPED';
}catch(e){r.error=String(e);await p.screenshot({path:path.join(output,'failure.png')}).catch(()=>{});}
finally{await Promise.all([...pending]);await fs.writeFile(path.join(output,'result.json'),JSON.stringify(r,null,2));await b.close();}
if(r.status!=='PASS_SCOPED')throw Error(r.error);
