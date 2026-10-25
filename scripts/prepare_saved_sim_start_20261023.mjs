// SPDX-License-Identifier: Apache-2.0
// Explicit visible SIM-only start preparation. Never an acceptance replacement.
import {chromium,expect} from '../apps/twinpulse-web/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {currentControlView,checkControlView} from './control_view_acceptance.mjs';
const args=process.argv.slice(2),arg=n=>args[args.indexOf(n)+1];
const out=arg('--output'),endpoint=arg('--cdp'),prior=arg('--prior'),profile=args.includes('--profile')?arg('--profile'):'after-bed-rejection';
if(!['after-bed-rejection','after-final-stop'].includes(profile))throw Error('Only explicit fixed preparation profiles allowed');
if(!out||!prior||!/^http:\/\/127\.0\.0\.1:\d+$/.test(endpoint))throw Error('Explicit new output/CDP/original failure required');
const oldBytes=await fs.readFile(prior),old=JSON.parse(oldBytes);
const project='chat_mvh8rm7k_4dafa4c1',revision='37ba75c8f38889ac556d49af289203e42e3376a2c6822be8cf31ecf93459453e';
if(old.status!=='FAIL'||old.project!==project||!old.error.includes(profile==='after-bed-rejection'?'NAVIGATION_NO_REACHABLE_APPROACH':'Final Stop all request/HTTP200/two-robot evidence missing'))throw Error('Exact original failed journey required');
const previous=old.samples.at(-1).robots.find(r=>r.label==='Alpha'&&r.kind==='sim');
if(previous.source_twin_context.scene_revision!==revision)throw Error('Wrong original revision');
await fs.mkdir(out,{recursive:false});
const result={status:'IN_PROGRESS',classification:'EXPLICIT_VISIBLE_SAVED_GEOMETRY_START_PREPARATION_NOT_WHOLE_PASS',
 project,revision,prior:{path:prior,sha256:createHash('sha256').update(oldBytes).digest('hex')},
 predeclared:{profile,turn:profile==='after-bed-rejection'?'Turn left 90 degrees':'Turn right 160 degrees',travel:'Forward 40cm',original_pose:previous.pose.position_m,
  expected_final_xy:[previous.pose.position_m[0]+.4*Math.cos(previous.pose.position_m[2]+(profile==='after-bed-rejection'?Math.PI/2:-160*Math.PI/180)),previous.pose.position_m[1]+.4*Math.sin(previous.pose.position_m[2]+(profile==='after-bed-rejection'?Math.PI/2:-160*Math.PI/180))],
  final_xy_bounds:profile==='after-bed-rejection'?[1.1,.65,1.35,.85]:[1.0,.5,1.35,.85],position_tolerance_m:.015,unchanged_planner_clearance_m:.25,
  rationale:'Existing original floor open southwest of chair legs; enough room for the fixed later manual movements. Guard/speed/timeouts unchanged. No teleport/registration/state-file edits.'},
 requests:[],samples:[],commands:[],errors:[],physical_actions:null};
const wanted=result.predeclared.expected_final_xy,bounds=result.predeclared.final_xy_bounds;
if(!(bounds[0]<wanted[0]&&wanted[0]<bounds[2]&&bounds[1]<wanted[1]&&wanted[1]<bounds[3]))throw Error('Fixed preparation falls outside predeclared open region');
await fs.writeFile(path.join(out,'predeclared.json'),JSON.stringify(result,null,2),{flag:'wx'});
const browser=await chromium.connectOverCDP(endpoint);let page,fleet,context,closing=false;const byContext=new Map(),tasks=[];
const pause=ms=>new Promise(r=>setTimeout(r,ms));
const poll=async(fn,ms=15000)=>{const end=Date.now()+ms;while(Date.now()<end){if(fn())return;await pause(100);}throw Error('Original bounded observation timed out');};
const robot=()=>fleet?.robots.find(r=>r.label==='Alpha'&&r.kind==='sim');
const drawer=()=>page.getByRole('region',{name:'Control Alpha',exact:true});
try{
 const pages=browser.contexts().flatMap(c=>c.pages()).filter(p=>p.url().startsWith('http://127.0.0.1:8765/'));
 if(pages.length!==1)throw Error('One installed renderer required');page=pages[0];
 result.identity=await page.evaluate(()=>window.twinpulseDesktop?.versions());
 page.on('response',r=>tasks.push((async()=>{
  const p=new URL(r.url()).pathname,c=r.headers()['x-twinpulse-context']??'';
  if(p==='/v1/product/conversation'&&r.status()===200){const v=await r.json();if(v.project_id===project){context=c;fleet=byContext.get(c);}}
  if(p==='/v1/product/robot-fleet'&&r.status()===200){const v=await r.json(),prev=byContext.get(c);if(!prev||v.revision>=prev.revision)byContext.set(c,v);
   if(c===context)fleet=byContext.get(c);result.samples.push({at:Date.now(),context:c,state:v});
   if(r.request().method()==='POST'){const b=r.request().postDataJSON();result.requests.push({at:Date.now(),request:b,status:r.status(),response:v});}
  }else if(r.status()>=400)result.errors.push({path:p,status:r.status()});
 })().catch(e=>result.errors.push(String(e)))));
 await expect(page.getByText('Isaac connected',{exact:true}).first()).toBeVisible({timeout:120000});
 if(!await page.locator('.chat-sidebar-slot').isVisible())await page.getByRole('button',{name:'Toggle conversations and projects',exact:true}).click();
 await page.getByRole('button',{name:'Open '+project,exact:true}).click();await poll(()=>robot());
 if(fleet.robots.some(r=>r.kind==='sim'&&r.connection_state!=='DISCONNECTED'))throw Error('Restored authority');
 const reopen=page.getByRole('button',{name:'Reopen saved scene',exact:true});if(await reopen.isVisible())await reopen.click();
 await page.getByRole('button',{name:'Current Twin and SIM controls',exact:true}).click();
 await page.getByRole('button',{name:'View current Twin',exact:true}).click();
 await expect(page.getByRole('img',{name:'Current Isaac Digital Twin render',exact:true})).toBeVisible({timeout:60000});
 await page.locator('.robot-fleet-row').filter({hasText:'Alpha'}).click();await expect(drawer()).toBeVisible();
 await drawer().getByRole('button',{name:'Connect',exact:true}).click();await poll(()=>robot()?.connection_state==='CONNECTED');
 await drawer().getByRole('button',{name:'Prepare',exact:true}).click();
 if(robot().lidar_state!=='STREAMING')await drawer().getByRole('button',{name:'Turn LiDAR on',exact:true}).click();
 await poll(()=>robot()?.lidar_state==='STREAMING'&&robot()?.sim_readiness?.ready);
 result.before=structuredClone(robot());
 if(robot().source_twin_context.scene_revision!==revision||robot().pose.position_m.some((v,i)=>Math.abs(v-previous.pose.position_m[i])>.001))throw Error('Original preserved initial pose changed; no adaptive preparation');
 const command=async(text,timeout)=>{
  const before=structuredClone(robot());await drawer().getByRole('textbox',{name:'Robot command',exact:true}).fill(text);
  const [request]=await Promise.all([page.waitForRequest(r=>{if(r.method()!=='POST'||new URL(r.url()).pathname!=='/v1/product/robot-fleet')return false;const b=r.postDataJSON();return b.action==='command'&&b.robot_id===before.robot_id&&b.payload?.text===text;},{timeout:5000}),drawer().getByRole('button',{name:'Send command',exact:true}).click()]);
  const id=request.postDataJSON().request_id;
  await poll(()=>{const c=robot()?.command;if(c?.request_id!==id)return false;if(['FAILED','CANCELLED'].includes(c.state))throw Error('Preparation command failed '+JSON.stringify(c));return c.state==='COMPLETED';},timeout);
  const after=structuredClone(robot());if(after.operation_id!==before.operation_id||after.connection_epoch!==before.connection_epoch)throw Error('Preparation identity changed');
  result.commands.push({text,request_id:id,before,after});
 };
 await command(result.predeclared.turn,15000);await command(result.predeclared.travel,15000);
 const arrived=robot().pose.position_m;
 if(Math.hypot(arrived[0]-wanted[0],arrived[1]-wanted[1])>.015)throw Error('Did not reach predeclared open region');
 const beforeStop=structuredClone(robot());
 const [stopRequest]=await Promise.all([page.waitForRequest(r=>{if(r.method()!=='POST'||new URL(r.url()).pathname!=='/v1/product/robot-fleet')return false;
  const b=r.postDataJSON();return b.action==='stop'&&b.robot_id===beforeStop.robot_id&&b.connection_epoch===beforeStop.connection_epoch&&b.motion_epoch===beforeStop.motion_epoch;
 },{timeout:5000}),drawer().getByRole('button',{name:'Stop',exact:true}).click()]);
 const stopResponse=await stopRequest.response();if(stopResponse?.status()!==200)throw Error('Explicit Stop not accepted');
 const stoppedState=await stopResponse.json(),ownStop=stoppedState.robots.find(r=>r.robot_id===beforeStop.robot_id);
 if(!ownStop||ownStop.operation_id!==beforeStop.operation_id||ownStop.connection_epoch!==beforeStop.connection_epoch||ownStop.motion_epoch===beforeStop.motion_epoch)throw Error('Own Stop identity/new epoch missing');
 result.stop_receipt={request:stopRequest.postDataJSON(),status:stopResponse.status(),response:stoppedState};
 await poll(()=>robot()?.control_state==='PAUSED'&&robot().operation_id===beforeStop.operation_id&&robot().connection_epoch===beforeStop.connection_epoch&&robot().motion_epoch===ownStop.motion_epoch&&robot().applied_motion_epoch===ownStop.motion_epoch);
 result.stopped=structuredClone(robot());await pause(800);result.after=structuredClone(robot());
 if(result.after.pose.position_m.some((v,i)=>Math.abs(v-result.stopped.pose.position_m[i])>.001))throw Error('Preparation Stop not stationary');
 result.current_frame=await currentControlView(page,'Alpha');checkControlView(result.current_frame);
 if(result.current_frame.scene_revision!==revision||result.current_frame.stage_epoch!==robot().source_twin_context.stage_epoch)throw Error('Preparation current frame/context does not match original scene');
 await page.screenshot({path:path.join(out,'prepared-open-start.png'),timeout:5000});
 await drawer().getByRole('button',{name:'Turn LiDAR off',exact:true}).click();await poll(()=>robot()?.lidar_state==='OFF');
 await drawer().getByRole('button',{name:'Operation logs',exact:true}).click();
 const downloading=page.waitForEvent('download');await drawer().getByRole('button',{name:'Download operation JSON',exact:true}).click();await (await downloading).saveAs(path.join(out,'operation.json'));
 await drawer().getByRole('button',{name:'Disconnect',exact:true}).click();await poll(()=>robot()?.connection_state==='DISCONNECTED');
 await Promise.all(tasks);
 result.physical_actions=result.requests.filter(r=>r.request.robot_id&&r.response.robots.find(v=>v.robot_id===r.request.robot_id)?.kind==='physical').length;
 if(result.physical_actions||result.requests.some(r=>r.request.robot_id&&!r.response.robots.some(v=>v.robot_id===r.request.robot_id&&v.kind==='sim')))throw Error('Non-SIM or unknown target touched');
 if(result.errors.length)throw Error('Preparation HTTP/read evidence errors');
 closing=true;const closed=page.waitForEvent('close',{timeout:60000});await page.getByRole('button',{name:'Exit TwinPulse',exact:true}).click();await closed;
 result.status='PASS_EXPLICIT_START_PREPARATION_NOT_WHOLE_ACCEPTANCE';
}catch(e){result.status='FAIL';result.error=String(e).slice(0,2000);result.cleanup_status='CLEANUP_PENDING_NO_NEXT_START';}
finally{await Promise.all(tasks);await fs.writeFile(path.join(out,'result.json'),JSON.stringify(result,null,2),{flag:'wx'});await browser.close();}
console.log(JSON.stringify({status:result.status,error:result.error,commands:result.commands.map(c=>c.text)}));
if(result.status==='FAIL')process.exitCode=1;
