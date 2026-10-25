// SPDX-License-Identifier: Apache-2.0
// Ordinary installed renderer only. Real configured planner, no interceptions,
// synthetic replies, direct API writes or physical connections/motion.
import {chromium,expect} from '../apps/twinpulse-web/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs/promises';import path from 'node:path';
import {createHash} from 'node:crypto';
import {recordRenderedPage} from './record_rendered_page.mjs';
import {reserveDevelopmentCall} from './development_call_allowance.mjs';
const [output,phase='survey',label='Aligned SIM 06',replayArg,allowanceFile,originalCondition]=process.argv.slice(2);
const replaySource=replayArg&&replayArg!=='-'?replayArg:null;
if(!output||!['survey','compose','cancel','cold'].includes(phase))throw Error('New output and known phase required');
await fs.mkdir(output,{recursive:false});
const root=path.resolve('outputs/robot-task-20261025-01');
const b=await chromium.connectOverCDP('http://127.0.0.1:19222');
const pages=b.contexts().flatMap(c=>c.pages()).filter(p=>p.url().startsWith('http://127.0.0.1:8765/'));if(pages.length!==1)throw Error('One installed renderer required');
const p=pages[0];p.setDefaultTimeout(30000);let finish,lastJob,lastFleet,lastFrame;const pending=new Set();
const result={status:'FAIL',phase,steps:[],errors:[],task_snapshots:[],requests:[],physical_actions:0,scope:'INSTALLED_SIM_TASK_COMPOSITION_NOT_PHYSICAL_OR_WHOLE_ROOM_QUALIFICATION'};
const save=()=>fs.writeFile(path.join(output,'result.json'),JSON.stringify(result,null,2));
const shot=async name=>{await p.screenshot({path:path.join(output,name+'.png')});await fs.writeFile(path.join(output,name+'.aria.txt'),await p.locator('body').ariaSnapshot());};
const step=async(name,fn)=>{await fn();result.steps.push({name,at:Date.now(),status:'PASS'});await save();console.log(name);};
const robot=()=>lastFleet?.robots?.find(r=>r.label===label);
p.on('pageerror',e=>result.errors.push(String(e)));
p.on('response',r=>{const work=(async()=>{const url=new URL(r.url()),request=r.request();
 if(url.pathname==='/v1/product/viewport/current')try{lastFrame=JSON.parse(r.headers()['x-twinpulse-viewport']).frame;}catch{}
 if(!['/v1/product/conversation','/v1/product/robot-fleet'].includes(url.pathname))return;
 let data;try{data=await r.json();}catch{return;}
 if(url.pathname.endsWith('robot-fleet'))lastFleet=data;
 if(data.robot_task){lastJob=data.robot_task;const key=JSON.stringify([lastJob.task_id,lastJob.state,lastJob.step_index,lastJob.segments,lastJob.stop_reconciled]);
  if(result.task_snapshots.at(-1)?.key!==key)result.task_snapshots.push({key,at:Date.now(),job:lastJob});}
 if(request.method()==='POST'){result.requests.push({path:url.pathname,status:r.status(),request:request.postDataJSON(),last_command:data.last_command??null,robot:robot()??null,error:data.error??null});}
 })();pending.add(work);void work.finally(()=>pending.delete(work));});
const fleet=p.getByRole('region',{name:'Robot fleet',exact:true}),control=p.getByRole('region',{name:'Control '+label,exact:true});
const choose=async name=>{await p.getByRole('radio',{name,exact:true}).check();await p.getByRole('button',{name:'Continue',exact:true}).click();};
const stop=async()=>{const response=p.waitForResponse(r=>new URL(r.url()).pathname==='/v1/product/robot-fleet'&&r.request().method()==='POST'&&r.request().postDataJSON()?.action==='stop');
 await control.getByRole('button',{name:'Stop',exact:true}).click();const r=await response,data=await r.json(),q=r.request().postDataJSON(),row=data.robots.find(x=>x.robot_id===q.robot_id);
 if(r.status()!==200||data.last_command?.request_id!==q.request_id||!row?.motion_epoch||row.motion_epoch===q.motion_epoch)throw Error('Missing exact new Stop ACK');
 await expect.poll(()=>robot()?.applied_motion_epoch).toBe(row.motion_epoch);result.stop={request:q,ack:data.last_command,robot:robot()};(result.stop_history??=[]).push(result.stop);};
try{
 result.versions=await p.evaluate(()=>window.twinpulseDesktop?.versions());await p.setViewportSize({width:1440,height:1000});
 finish=await recordRenderedPage(p,path.join(output,'recording'));
 const panel=p.getByRole('region',{name:'Import space',exact:true});if(await panel.isVisible())await panel.getByRole('button',{name:'Close import space',exact:true}).click();
 const view=p.getByRole('button',{name:'Control view',exact:true});if(await view.getAttribute('aria-pressed')!=='true')await view.click();
 if(replaySource){
  if(phase!=='survey'||path.resolve(replaySource)!==path.join(root,'survey04/result.json'))throw Error('Only exact original SIM survey starting condition may be reset');
  const original=JSON.parse(await fs.readFile(replaySource,'utf8')),pose=original.start.pose.position_m;
  result.original_failed_survey={path:replaySource,task_id:original.final_task.task_id,pose};
  const existing=await fleet.getByRole('button',{name:new RegExp(label+' SIM ')}).count();
  if(existing>1)throw Error('Ambiguous SIM replay label');
  if(!existing)
  await step('Explicit new SIM registration resets the original failed survey starting pose',async()=>{
   await fleet.getByRole('button',{name:'Manage robot fleet',exact:true}).click();const registration=fleet.locator('details.robot-fleet-register');
   if(await registration.getAttribute('open')===null)await registration.locator('summary').click();
   await fleet.getByLabel('Name',{exact:true}).fill(label);await fleet.getByLabel('X (m)',{exact:true}).fill(String(pose[0]));await fleet.getByLabel('Y (m)',{exact:true}).fill(String(pose[1]));await fleet.getByLabel('Yaw (rad)',{exact:true}).fill(String(pose[2]));
   await shot('original-start-registration');await p.waitForTimeout(3000);await fleet.getByRole('button',{name:'Add SIM robot',exact:true}).click();
   result.original_failed_survey={path:replaySource,task_id:original.final_task.task_id,pose};
   await fleet.getByRole('button',{name:'Manage robot fleet',exact:true}).click();
  });
 }
 await step('Select existing registered TurtleBot3 SIM only',async()=>{await fleet.getByRole('button',{name:new RegExp(label+' SIM ')}).click();await expect(control).toBeVisible();await expect.poll(()=>robot()?.kind).toBe('sim');});
 if(replaySource)await step('Exact original failed survey starting pose is preserved',async()=>{await expect.poll(()=>robot()?.pose?.position_m).toEqual(result.original_failed_survey.pose);});
 if(phase==='cold'){
  await step('Cold history does not resume a task or connection',async()=>{await expect.poll(()=>robot()?.connection_state).toBe('DISCONNECTED');
   result.physical_rows=(lastFleet?.robots??[]).filter(r=>r.kind==='physical');
   if(!result.physical_rows.length||result.physical_rows.some(r=>r.connection_state!=='DISCONNECTED'||r.live_heartbeat||(r.capabilities??{}).drive))throw Error('Cold physical authority restored');
   await expect(p.getByRole('radio',{name:'Run task',exact:true})).toHaveCount(0);await expect(p.getByRole('radio',{name:'Plan task',exact:true})).toHaveCount(0);
   await shot('cold-history-no-authority');});
 }else{
  await step('Explicit SIM Connect Prepare with current engine epoch',async()=>{
   if(robot()?.connection_state!=='CONNECTED'){await control.getByRole('button',{name:'Connect',exact:true}).click();await expect(control.getByRole('button',{name:'Prepare',exact:true})).toBeEnabled();await control.getByRole('button',{name:'Prepare',exact:true}).click();}
   await expect.poll(()=>robot()?.control_state).toMatch(/READY|PAUSED/);await expect.poll(()=>robot()?.applied_motion_epoch).toBe(robot().motion_epoch);result.start=robot();
  });
  if(originalCondition)await step('Original failed compound command starting condition is unchanged',async()=>{
   if(phase!=='compose'||path.resolve(originalCondition)!==path.resolve('outputs/environment-task-loop-20261025-01/compose17/result.json'))throw Error('Exact failed compound evidence required');
   const bytes=await fs.readFile(originalCondition),original=JSON.parse(bytes),a=original.start.pose.position_m,c=robot().pose.position_m;
   if(original.status!=='FAIL'||Math.hypot(a[0]-c[0],a[1]-c[1])>.001||Math.abs(Math.atan2(Math.sin(a[2]-c[2]),Math.cos(a[2]-c[2])))>.001)throw Error('Original failure starting pose changed');
   result.original_failed_condition={path:originalCondition,sha256:createHash('sha256').update(bytes).digest('hex'),task_id:original.proposal.task_id,pose:a,text:original.proposal.text};
  });
  await step('Camera frames the actual robot body before the task',async()=>{
   const details=p.locator('details.twin-display-details');if(await details.getAttribute('open')===null)await details.locator('summary').click();
   const bounds=async()=>{let a;await expect.poll(()=>{a=lastFrame?.robot_anchors?.find(a=>a.robot_id===robot()?.robot_id&&a.visible);return !!a;},{timeout:10000}).toBe(true);return a.screen_bounds_uv;};
   const camera=async name=>{await p.getByRole('button',{name,exact:true}).click();await p.waitForTimeout(350);};
   const center=async()=>{for(const axis of [0,1])for(let i=0;i<12;i++){const a=await bounds(),v=(a[axis]+a[axis+2])/2;if(Math.abs(v-.5)<.035)break;await camera(axis===0?(v<.5?'Pan left':'Pan right'):(v<.5?'Pan up':'Pan down'));}};
   await camera('Top view');await center();for(let i=0;i<12;i++){const a=await bounds();if(a[2]-a[0]>.04)break;await camera('Zoom in');}await center();
   result.body_bounds_before=await bounds();await details.locator('summary').click();await shot('00-body-framed');
  });
  const text=phase==='survey'?'Measure the reachable room by moving to observation locations, then return to the start and stop. This short SIM test has a total travel limit of 2.5 metres, 180 seconds and 64 finite segments.':
   phase==='compose'?'Move forward 10 centimetres, then turn left 30 degrees, then return to the start and stop. Limit the entire task to 1 metre, 90 seconds and 20 finite segments.':
   'Inspect the reachable room by moving between observation positions, collect LiDAR observations and return to the start. Stop at 2 metres or 120 seconds.';
  const previous=lastJob?.task_id;
  if(result.original_failed_condition&&result.original_failed_condition.text!==text)throw Error('Original failed compound command changed');
  await step('Natural goal through Robot command waits three seconds before Enter',async()=>{const input=control.getByRole('textbox',{name:'Robot command'});await input.fill(text);await p.waitForTimeout(3000);await input.press('Enter');await expect(input).toHaveValue('');await expect(p.getByRole('radio',{name:'Plan task',exact:true})).toBeVisible();await shot('01-text-consent');});
  await step('One approved text-only configured planner request',async()=>{
   if(allowanceFile){result.call_claim=await reserveDevelopmentCall(allowanceFile,'text',{text,phase});}
   else{
   const approval=JSON.parse(await fs.readFile(path.join(root,'approval.json'),'utf8'));if(approval.max_requests!==3||approval.physical_operation_allowed!==false)throw Error('Allowance changed');
   let maxClaims=3;
   try{const extra=JSON.parse(await fs.readFile(path.join(root,'approval-additional01.json'),'utf8'));
    if(extra.additional_max_requests!==2||extra.cumulative_max_requests!==5||extra.physical_operation_allowed!==false||extra.coordinates_allowed!==false||extra.photos_allowed!==false||extra.usd_allowed!==false||extra.physical_logs_allowed!==false||extra.user_answer!=='텍스트 검증 2회 추가 허용')throw Error('Additional allowance changed');maxClaims=5;
   }catch(e){if(e.code!=='ENOENT')throw e;}
   try{const extra=JSON.parse(await fs.readFile(path.join(root,'approval-additional02.json'),'utf8'));
    if(maxClaims!==5||extra.additional_max_requests!==2||extra.cumulative_max_requests!==7||extra.physical_operation_allowed!==false||extra.coordinates_allowed!==false||extra.photos_allowed!==false||extra.usd_allowed!==false||extra.physical_logs_allowed!==false||extra.user_answer!=='텍스트 검증 2회 더 허용')throw Error('Final additional allowance changed');maxClaims=7;
   }catch(e){if(e.code!=='ENOENT')throw e;}
   try{const extra=JSON.parse(await fs.readFile(path.join(root,'approval-additional03.json'),'utf8'));
    if(maxClaims!==7||extra.additional_max_requests!==10||extra.cumulative_max_requests!==17||extra.physical_operation_allowed!==false||extra.coordinates_allowed!==false||extra.photos_allowed!==false||extra.usd_allowed!==false||extra.physical_logs_allowed!==false||extra.user_answer!=='추가 10회 승인')throw Error('Additional ten-call allowance changed');maxClaims=17;
   }catch(e){if(e.code!=='ENOENT')throw e;}
   const folder=path.join(root,'call-claims');await fs.mkdir(folder,{recursive:true});let claim;
   for(let i=1;i<=maxClaims;i++)try{claim={index:i,text,phase,at:Date.now(),authorization:i<=3?'approval.json':i<=5?'approval-additional01.json':i<=7?'approval-additional02.json':'approval-additional03.json',status:'RESERVED_BEFORE_SUBMISSION_UNKNOWN_COUNTS_AS_USED'};await fs.writeFile(path.join(folder,String(i)+'.json'),JSON.stringify(claim,null,2),{flag:'wx'});break;}catch(e){if(e.code!=='EEXIST')throw e;claim=null;}
   if(!claim)throw Error('Approved text-call grant exhausted');result.call_claim=claim;
   }
   await choose('Plan task');await expect.poll(()=>lastJob?.task_id&&lastJob.task_id!==previous?lastJob.state:'WAIT_NEW_JOB',{timeout:120000}).toMatch(/PLANNING|READY|FAILED|HELD/);
   if(phase==='cancel')return;
   await expect.poll(()=>lastJob?.state,{timeout:120000}).toMatch(/READY|FAILED|HELD|CANCELLED/);result.planning_result=lastJob;
   if(lastJob.state!=='READY')throw Error('Actual planner did not produce an executable proposal: '+lastJob.reason);
   result.proposal=lastJob;await expect(p.getByRole('radio',{name:'Run task',exact:true})).toBeVisible();await shot('02-model-proposal');
  });
  if(phase==='cancel'){
   await step('Stop after planner submission prevents late execution',async()=>{await p.waitForTimeout(1000);result.cancel_at_state=lastJob?.state;result.cancel_worker_active=lastJob?.worker_active;result.cancel_before_stop_at=Date.now();await stop();await expect.poll(()=>lastJob?.state,{timeout:120000}).toMatch(/CANCELLED|FAILED/);await expect.poll(()=>lastJob?.worker_active,{timeout:120000}).toBe(false);await p.waitForTimeout(3000);
    if(lastJob.state==='READY'||lastJob.segments!==0)throw Error('Cancelled plan revived');await expect(p.getByRole('radio',{name:'Run task',exact:true})).toHaveCount(0);result.cancelled=lastJob;await shot('cancelled-no-run');});
  }else{
   await step('Explicit exact-plan Run uses measured child results and observations',async()=>{
    await choose('Run task');await expect.poll(()=>lastJob?.state,{timeout:45000}).toMatch(/RUNNING|FAILED|HELD/);await shot('03-started');
    await expect.poll(()=>lastJob?.segments,{timeout:45000}).toBeGreaterThan(0);await p.waitForTimeout(1500);result.moving_frame=lastFrame;await shot('04-measured-motion');
    await expect.poll(()=>lastJob?.state,{timeout:230000}).toMatch(/COMPLETED|PARTIAL|FAILED|HELD/);result.final_task=lastJob;result.end=robot();
    if(!['COMPLETED','PARTIAL'].includes(lastJob.state))throw Error('Task failed: '+JSON.stringify(lastJob));
    const events=lastJob.events??[],children=events.filter(e=>e.kind==='child_completed');if(children.length<2)throw Error('No multi-segment motion evidence');
    if(!events.some(e=>e.kind==='stop_confirmed')||lastJob.stop_error)throw Error('No confirmed final Stop');
    if(Math.hypot(robot().pose.position_m[0]-result.start.pose.position_m[0],robot().pose.position_m[1]-result.start.pose.position_m[1])>.05)throw Error('Not returned to initial position');
    if(phase==='survey'&&(lastJob.measured_coverage?.observations<2||lastJob.whole_room_coverage_verified!==false))throw Error('Measured scan coverage missing or overclaimed');
    if(children.some(e=>e.new_motion_epoch!==e.applied_motion_epoch))throw Error('Child Stop epoch was not applied');await shot('05-return-and-stop');
   });
  }
  await step('Final exact Stop LiDAR OFF Disconnect without physical calls',async()=>{await stop();
   if(robot()?.lidar_state!=='OFF'){
    const response=p.waitForResponse(r=>new URL(r.url()).pathname==='/v1/product/robot-fleet'&&r.request().method()==='POST'&&r.request().postDataJSON()?.action==='lidar'&&r.request().postDataJSON()?.payload?.enabled===false);
    const at=Date.now();await control.getByRole('button',{name:'Turn LiDAR off',exact:true}).click();const r=await response,data=await r.json(),q=r.request().postDataJSON(),row=data.robots.find(v=>v.robot_id===q.robot_id);
    if(r.status()!==200||data.last_command?.request_id!==q.request_id||!row?.motion_epoch||row.motion_epoch===q.motion_epoch)throw Error('Missing exact OFF zero epoch ACK');
    await expect.poll(()=>robot()?.applied_motion_epoch).toBe(row.motion_epoch);
    await expect.poll(()=>lastFrame?.captured_at_ms>at&&!lastFrame?.lidar_overlay).toBe(true);
    await expect(p.getByText('LiDAR sensor: OFF',{exact:true})).toBeVisible();
    if(robot()?.connection_state!=='CONNECTED'||robot()?.scan!==null)throw Error('OFF did not clear scan while retaining connection');
    result.off={request:q,ack:data.last_command,robot:robot(),frame:lastFrame,at};await shot('06-lidar-off-before-disconnect');
   }
   await expect.poll(()=>robot()?.lidar_state).toBe('OFF');await control.getByRole('button',{name:'Disconnect',exact:true}).click();await expect.poll(()=>robot()?.connection_state).toBe('DISCONNECTED');});
 }
 if(result.errors.length)throw Error('Renderer error');result.status='PASS_SCOPED';
}catch(e){result.errors.push(String(e));await shot('failure').catch(()=>{});}finally{await Promise.all([...pending]);if(finish)result.recording=await finish().catch(e=>({error:String(e)}));await save();await b.close();}
if(result.status!=='PASS_SCOPED')throw Error(result.errors.join('\n'));
