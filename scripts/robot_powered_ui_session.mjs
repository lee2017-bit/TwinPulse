// SPDX-License-Identifier: Apache-2.0
// Main-operated installed BrowserWindow UI and read-only evidence, never robot/API commands.
import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {spawn} from 'node:child_process';
const {chromium}=createRequire(import.meta.url)('../apps/twinpulse-web/node_modules/.pnpm/playwright-core@1.63.0/node_modules/playwright-core');

export async function attachPoweredSession(output,endpoint='http://127.0.0.1:19222') {
  await fs.mkdir(output,{recursive:false});
  await fs.mkdir(path.join(output,'frames'));
  let browser;const connectUntil=Date.now()+45000;
  // A passive recorder must not replace the interactive client's download
  // directory/focus emulation in the same default BrowserWindow context.
  while(!browser){try{browser=await chromium.connectOverCDP(endpoint,{timeout:2000,noDefaults:true});}
    catch(error){if(Date.now()>=connectUntil)throw error;await new Promise(r=>setTimeout(r,500));}}
  let pages;const pageUntil=Date.now()+30000;
  do{pages=browser.contexts().flatMap(c=>c.pages()).filter(p=>p.url().startsWith('http://127.0.0.1:8765/'));
    if(pages.length||Date.now()>=pageUntil)break;await new Promise(r=>setTimeout(r,500));}while(true);
  if(pages.length!==1)throw Error('Exactly one installed renderer required');
  const page=pages[0];page.setDefaultTimeout(10000);
  const session={output,browser,page,events:[],errors:[],fleet:null,registry:null,operation:null,stage:'ATTACH',frames:[],pending:Promise.resolve(),began:Date.now(),recording:true};
  let httpOrder=0;const requestRows=new WeakMap();session.fleet_requests=[];session.fleet_samples=[];
  page.on('request',request=>{if(new URL(request.url()).pathname!=='/v1/product/robot-fleet'||request.method()!=='POST')return;
    const row={...request.postDataJSON(),order:++httpOrder,at:Date.now()};requestRows.set(request,row);session.fleet_requests.push(row);});
  const redact=s=>String(s).replace(/#bootstrap=[^\s"']+/g,'#bootstrap=[REDACTED]');
  session.identity=await page.evaluate(()=>window.twinpulseDesktop?.versions());
  if(!session.identity?.engine?.launch_id)throw Error('Installed identity unavailable');
  session.save=async()=>fs.writeFile(path.join(output,'session.json'),JSON.stringify({identity:session.identity,began:new Date(session.began).toISOString(),stage:session.stage,events:session.events,errors:session.errors,frames:session.frames.length,elapsed_ms:Date.now()-session.began},null,2));
  page.on('pageerror',e=>session.errors.push({at:Date.now(),stage:session.stage,error:redact(e)}));
  page.on('requestfailed',r=>session.errors.push({at:Date.now(),stage:session.stage,path:new URL(r.url()).pathname,method:r.method(),failure:r.failure()}));
  page.on('response',async r=>{try{
    const pathname=new URL(r.url()).pathname,order=++httpOrder,requestRow=requestRows.get(r.request());
    if(!pathname.startsWith('/v1/product/'))return;
    const mini=body=>(body.fleet??body).robots?.map(v=>({robot_id:v.robot_id,operation_id:v.operation_id,connection_epoch:v.connection_epoch,motion_epoch:v.motion_epoch,applied_motion_epoch:v.applied_motion_epoch,control_state:v.control_state}));
    if(requestRow){requestRow.status=r.status();requestRow.response_order=order;const body=await r.json().catch(()=>null);if(body)requestRow.result_robots=mini(body);}
    if(r.status()>=400)session.errors.push({at:Date.now(),stage:session.stage,path:pathname,method:r.request().method(),status:r.status(),request:requestRow,body:await r.json().catch(()=>null)});
    if(pathname==='/v1/product/robot-fleet'&&r.ok()){
      const body=await r.json();session.fleet=body.fleet??body;
      session.fleet_samples.push({order,revision:session.fleet.revision,robots:mini(body)});
      const safe=JSON.stringify({at:Date.now(),stage:session.stage,method:r.request().method(),request:r.request().method()==='POST'?r.request().postDataJSON():undefined,response:body});
      session.pending=session.pending.then(()=>fs.appendFile(path.join(output,'fleet-observations.jsonl'),safe+'\n'));
    }
    if(pathname==='/v1/product/robots'&&r.ok())session.registry=await r.json();
    if(pathname==='/v1/product/conversation'&&r.ok()){
      const body=await r.json();
      if(!session.conversation||session.conversation.project_id!==body.project_id||body.revision>=session.conversation.revision)session.conversation=body;
    }
  }catch(e){session.errors.push({at:Date.now(),stage:session.stage,observer_error:redact(e)});}});
  const cdp=await page.context().newCDPSession(page);session.cdp=cdp;
  let lastFrame=0;
  session.capture_policy={format:'jpeg',quality:78,maxWidth:1600,maxHeight:1100,everyNthFrame:4,saved_min_interval_ms:450,
    scope:'Renderer screencast sampling only. Not application frame cadence, a load benchmark, native capture or a startup-cause repair.'};
  session.capture_received=0;session.capture_discarded=0;
  cdp.on('Page.screencastFrame',event=>{
    session.capture_received++;
    void cdp.send('Page.screencastFrameAck',{sessionId:event.sessionId}).catch(()=>{});
    const at=Date.now();if(!session.recording||at-lastFrame<450){session.capture_discarded++;return;}lastFrame=at;
    const name=String(session.frames.length).padStart(6,'0')+'.jpg';
    session.frames.push({file:'frames/'+name,at,stage:session.stage});
    session.pending=session.pending.then(()=>fs.writeFile(path.join(output,'frames',name),Buffer.from(event.data,'base64')));
  });
  // Discarding a received base64 frame cannot undo its renderer-side encoding
  // and transfer. Request a sampled stream as well as bounding saved frames.
  await cdp.send('Page.startScreencast',{format:'jpeg',quality:78,maxWidth:1600,maxHeight:1100,everyNthFrame:4});
  session.text=()=>page.locator('body').innerText();
  session.shot=async name=>{await page.screenshot({path:path.join(output,name+'.png'),timeout:8000});await session.save();};
  session.note=async(name,evidence={})=>{session.stage=name;session.events.push({at:Date.now(),name,evidence});await session.save();};
  session.download=async(button,name)=>{const pending=page.waitForEvent('download',{timeout:20000});await button.click();const download=await pending;await download.saveAs(path.join(output,name));const bytes=await fs.readFile(path.join(output,name));const receipt={name,bytes:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex')};await session.note('DOWNLOAD',receipt);return receipt;};
  session.finishVideo=async()=>{
    session.recording=false;await cdp.send('Page.stopScreencast').catch(error=>session.errors.push({at:Date.now(),stage:session.stage,recorder_stop:redact(error)}));await session.pending;
    const end=Date.now();await fs.writeFile(path.join(output,'frame-times.json'),JSON.stringify({began:session.began,end,frames:session.frames},null,2));
    await fs.writeFile(path.join(output,'fleet-http-receipts.json'),JSON.stringify({requests:session.fleet_requests,samples:session.fleet_samples},null,2));
    if(!session.frames.length)throw Error('No actual screencast frames received');
    const lines=['ffconcat version 1.0'];
    for(let i=0;i<session.frames.length;i++){const frame=session.frames[i],next=session.frames[i+1]?.at??end;lines.push("file '"+frame.file+"'",'duration '+Math.max(.02,(next-frame.at)/1000).toFixed(3));}
    lines.push("file '"+session.frames.at(-1).file+"'");
    await fs.writeFile(path.join(output,'screen.ffconcat'),lines.join('\n'));
    const log=await fs.open(path.join(output,'video-encode.log'),'wx');
    // B-frame reordering can make the MP4 track duration omit long static
    // holds even when packet PTS retains them. Keep monotonic decode/display
    // order and the original concat timestamps; never synthesize motion.
    const child=spawn('ffmpeg',['-nostdin','-hide_banner','-loglevel','warning','-copyts','-start_at_zero','-f','concat','-safe','0','-i',path.join(output,'screen.ffconcat'),'-vf','scale=1600:900:force_original_aspect_ratio=decrease,pad=1600:900:(ow-iw)/2:(oh-ih)/2','-fps_mode','passthrough','-enc_time_base','1/1000','-c:v','libx264','-bf','0','-preset','fast','-crf','24','-pix_fmt','yuv420p','-video_track_timescale','1000','-movflags','+faststart',path.join(output,'app-screen.mp4')],{windowsHide:true,stdio:['ignore',log.fd,log.fd]});
    const code=await new Promise((resolve,reject)=>{child.once('error',reject);child.once('exit',resolve);});await log.close();
    await session.note('VIDEO_ENCODE',{code,frames:session.frames.length,wall_ms:end-session.began,no_audio:true,source:'Actual same installed Electron renderer CDP screencast; not native desktop or robot camera.'});
    if(code!==0)throw Error('Video encode failed');return path.join(output,'app-screen.mp4');
  };
  await session.note('ATTACHED_RECORDING',{native:'NOT_RUN_RENDERER_RECORDING_ONLY',path:'Same installed explicit Test BrowserWindow',robot_authority:'Only public UI, no API mutation'});
  return session;
}
