// SPDX-License-Identifier: Apache-2.0
// Main-operated final installed UI. Saved scene, not fresh generation/hardware.
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {attachPoweredSession} from './robot_powered_ui_session.mjs';
import {currentControlView,checkControlView} from './control_view_acceptance.mjs';
const out=path.resolve(process.argv[2]??'');if(!process.argv[2])throw Error('Explicit output required');
const s=await attachPoweredSession(out),p=s.page;
const result={status:'IN_PROGRESS',identity:s.identity,scope:'FINAL_SAVED_SCENE_SIM_AND_PC_NOT_FRESH_GENERATION_OR_PHYSICAL',steps:[],download_events:[],samples:[]};
const wait=ms=>new Promise(r=>setTimeout(r,ms));
const poll=async(fn,limit=30000)=>{const end=Date.now()+limit;while(Date.now()<end){if(fn())return;await wait(100);}throw Error('Observed UI state timeout');};
const robot=name=>s.fleet?.robots.find(x=>x.label===name&&x.kind==='sim');
const drawer=name=>p.getByRole('region',{name:'Control '+name,exact:true});
const step=async(name,fn)=>{await s.note(name);const began=Date.now();try{const evidence=await fn();result.steps.push({name,status:'PASS',elapsed_ms:Date.now()-began,evidence});}
 catch(error){result.steps.push({name,status:'FAIL',error:String(error)});throw error;}};
const choose=async name=>{await p.locator('.robot-fleet-row').filter({hasText:name}).click();await poll(()=>s.fleet?.focused_robot_id===robot(name)?.robot_id);};
const stopped=name=>robot(name)?.control_state==='PAUSED'&&robot(name)?.motion_epoch===robot(name)?.applied_motion_epoch;
const sendCommand=async(name,text,main=false)=>{const old=robot(name)?.command?.request_id;
 const input=main?p.getByRole('textbox',{name:'Message TwinPulse',exact:true}):drawer(name).getByRole('textbox',{name:'Robot command',exact:true});
 await input.fill(text);await wait(3000);if(main)await p.getByRole('button',{name:'Send',exact:true}).click();else await input.press('Enter');
 await poll(()=>robot(name)?.command?.request_id!==old&&!!robot(name)?.command);
 await poll(()=>['COMPLETED','FAILED','CANCELLED','ARRIVED'].includes(robot(name)?.command?.state),45000);
 if(robot(name).command.state!=='COMPLETED')throw Error(JSON.stringify(robot(name).command));return structuredClone(robot(name).command);};
try{
 await step('Installed Home startup and original saved scene displayed',async()=>{
  await p.getByText('Isaac connected',{exact:true}).first().waitFor({state:'visible',timeout:120000});
  await s.shot('home');await p.getByRole('button',{name:'Open chat_mvf2wo4i_587adab8',exact:true}).click();
  await p.getByRole('banner').filter({hasText:'chat_mvf2wo4i_587adab8'}).waitFor({state:'visible'});
  await p.getByRole('button',{name:'Reopen saved scene',exact:true}).click();
  await p.getByRole('button',{name:'View current Twin',exact:true}).waitFor({state:'visible',timeout:60000});await p.getByRole('button',{name:'View current Twin',exact:true}).click();
  await p.getByRole('img',{name:'Current Isaac Digital Twin render',exact:true}).waitFor({state:'visible',timeout:45000});
  await poll(()=>!!robot('TurtleBot3'));result.project='chat_mvf2wo4i_587adab8';return {no_new_generation:true};
 });
 await step('Two explicit SIM definitions, connection and independent LiDAR',async()=>{
  if(!robot('Beta')){
   await p.getByRole('button',{name:'Manage robot fleet',exact:true}).click();await p.getByText('Add SIM robot',{exact:true}).click();
   await p.getByRole('textbox',{name:'Name',exact:true}).fill('Beta');
   for(const [name,value] of [['X (m)','-1'],['Y (m)','-1'],['Yaw (rad)','0']])await p.getByRole('spinbutton',{name,exact:true}).fill(value);
   await p.getByRole('button',{name:'Add SIM robot',exact:true}).click();await poll(()=>!!robot('Beta'));
   await p.getByRole('button',{name:'Manage robot fleet',exact:true}).click();
  }
  for(const name of ['Beta','TurtleBot3']){
   await choose(name);await drawer(name).getByRole('button',{name:'Connect',exact:true}).click();await poll(()=>robot(name)?.connection_state==='CONNECTED');
   await drawer(name).getByRole('button',{name:'Prepare',exact:true}).click();await poll(()=>['READY','PAUSED'].includes(robot(name)?.control_state));
   await drawer(name).getByRole('button',{name:'Turn LiDAR on',exact:true}).click();await poll(()=>robot(name)?.lidar_state==='STREAMING');
  }
  result.operation_id=robot('TurtleBot3').operation_id;result.source_twin_context=structuredClone(robot('TurtleBot3').source_twin_context);
  return {robots:['Beta','TurtleBot3'].map(n=>({id:robot(n).robot_id,operation:robot(n).operation_id}))};
 });
 await step('Uninterrupted62second hold: current frame/model/name/Stop/pad and release ACK',async()=>{
  const box=await drawer('TurtleBot3').getByRole('button',{name:'Hold left',exact:true}).boundingBox();
  await p.mouse.move(box.x+box.width/2,box.y+box.height/2);await p.mouse.down();
  try{await poll(()=>robot('TurtleBot3')?.control_state==='DRIVING');const began=Date.now();while(Date.now()-began<62000){const v=await currentControlView(p,'TurtleBot3');checkControlView(v);result.samples.push(v);if(robot('TurtleBot3').control_state!=='DRIVING')throw Error('Unexpected hold pause');await wait(250);}}
  finally{await p.mouse.up();}
  await poll(()=>stopped('TurtleBot3'));if(robot('Beta').connection_state!=='CONNECTED')throw Error('Other robot disconnected');
  await s.shot('hold-release');return {samples:result.samples.length,frame_age_max:Math.max(...result.samples.map(x=>x.frame_age_ms))};
 });
 await step('Four real pad directions and individual applied release Stops',async()=>{
  for(const direction of ['forward','backward','right','left']){await wait(500);const box=await drawer('TurtleBot3').getByRole('button',{name:'Hold '+direction,exact:true}).boundingBox();await p.mouse.move(box.x+box.width/2,box.y+box.height/2);await p.mouse.down();await wait(600);await p.mouse.up();await poll(()=>stopped('TurtleBot3'));}
  return {directions:4};
 });
 await step('Actual command field90degrees',()=>sendCommand('TurtleBot3','Turn right 90 degrees'));
 await step('Actual main chat: one complete360degree LiDAR scan',async()=>{const command=await sendCommand('TurtleBot3','TurtleBot3 robot one full turn and scan lidar',true);return {command,points:robot('TurtleBot3').scan?.points?.length};});
 await step('Stop all ACK and both applied epochs, LiDAR Off and Disconnect',async()=>{
  const pending=p.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname==='/v1/product/robot-fleet'&&r.request().postDataJSON()?.action==='stop_all');
  await p.getByRole('button',{name:'Stop all',exact:true}).click();
  const response=await pending,body=await response.json(),request=response.request().postDataJSON();
  if(response.status()!==200)throw Error('Stop all HTTP failure');
  const ack={status:response.status(),request,body};
  for(const name of ['Beta','TurtleBot3']){
   const actual=body.robots?.find(x=>x.robot_id===robot(name).robot_id);
   if(!actual?.motion_epoch||actual.connection_epoch!==robot(name).connection_epoch||!actual.operation_id)throw Error('Stop all exact robot/connection receipt missing');
   await poll(()=>robot(name)?.operation_id===actual.operation_id&&robot(name)?.connection_epoch===actual.connection_epoch&&robot(name)?.motion_epoch===actual.motion_epoch&&robot(name)?.applied_motion_epoch===actual.motion_epoch&&robot(name)?.control_state==='PAUSED');
  }
  for(const name of ['Beta','TurtleBot3']){await choose(name);await drawer(name).getByRole('button',{name:'Turn LiDAR off',exact:true}).click();await poll(()=>robot(name)?.lidar_state==='OFF');await drawer(name).getByRole('button',{name:'Disconnect',exact:true}).click();await poll(()=>robot(name)?.connection_state==='DISCONNECTED');}
  return {ack,physical:(s.fleet.robots??[]).filter(x=>x.kind==='physical').map(x=>({id:x.robot_id,state:x.connection_state,operation:x.operation_id}))};
 });
 await step('Actual final operation file export after Disconnect',async()=>{
  const directory=path.join(out,'downloads');await fs.mkdir(directory);const cdp=await s.browser.newBrowserCDPSession();
  cdp.on('Browser.downloadWillBegin',e=>result.download_events.push({kind:'begin',...e}));cdp.on('Browser.downloadProgress',e=>result.download_events.push({kind:'progress',...e}));
  await cdp.send('Browser.setDownloadBehavior',{behavior:'allow',downloadPath:directory,eventsEnabled:true});
  const rows=[];
  for(const name of ['TurtleBot3','Beta']){await choose(name);await drawer(name).getByRole('button',{name:'Operation logs',exact:true}).click();const button=drawer(name).getByRole('button',{name:'Download operation JSON',exact:true});await button.waitFor({state:'visible'});
   const at=result.download_events.length;await button.click();await poll(()=>result.download_events.slice(at).some(x=>['completed','canceled'].includes(x.state)),20000);
   const events=result.download_events.slice(at),end=events.findLast(x=>['completed','canceled'].includes(x.state));if(end?.state!=='completed')throw Error('Native export '+end?.state);
   const file=events.find(x=>x.kind==='begin').suggestedFilename,bytes=await fs.readFile(path.join(directory,file)),record=JSON.parse(bytes);
   if(record.operation_id!==robot(name).last_operation_id||!record.manifest.complete)throw Error('Wrong or incomplete operation');
   rows.push({name,file,operation_id:record.operation_id,sha256:createHash('sha256').update(bytes).digest('hex'),bytes:bytes.length,events:record.events.length,source_twin_context:record.manifest.source_twin_context});
  }
  result.exports=rows;await s.shot('final-export');return rows;
 });
 result.raw_errors=structuredClone(s.errors);result.expected_release_fences=[];
 for(const e of s.errors){const r=e.request,stop=s.fleet_requests.find(x=>x.action==='stop'&&x.status===200&&x.order>r?.order&&x.response_order<r?.response_order&&x.robot_id===r?.robot_id&&x.motion_epoch===r?.motion_epoch);
  if(e.status===409&&e.body?.error?.code==='fleet_motion_changed'&&r?.action==='drive'&&stop)result.expected_release_fences.push({error:e,stop});else throw Error('Unclassified actual request failure '+JSON.stringify(e));}
 result.status='PASS_SCOPED_FINAL_SAVED_SIM_AND_EXPORT';
}catch(error){result.status='FAIL';result.error=String(error);}
finally{
 await fs.writeFile(path.join(out,'result.json'),JSON.stringify(result,null,2));
 try{await s.finishVideo();}catch(error){result.video_error=String(error);}
 try{await p.getByRole('button',{name:'Exit TwinPulse',exact:true}).click();result.exit='NORMAL_UI_CLICK';}catch(error){result.exit_error=String(error);}
 await fs.writeFile(path.join(out,'result.json'),JSON.stringify(result,null,2));
 console.log(JSON.stringify({status:result.status,error:result.error,steps:result.steps.map(x=>({name:x.name,status:x.status})),operation:result.operation_id}));
}
process.exitCode=result.status.startsWith('PASS')?0:1;
