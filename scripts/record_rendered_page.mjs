// SPDX-License-Identifier: Apache-2.0
// Record on the UI driver's existing connection. Never attach a second browser
// client (which can change Chromium's browser-wide download destination).
import fs from 'node:fs/promises';
import path from 'node:path';
import {spawn} from 'node:child_process';
import {installRecordingPointer} from './recording_pointer.mjs';
export async function recordRenderedPage(page,output){
 await fs.mkdir(path.join(output,'frames'),{recursive:true});
 const cdp=await page.context().newCDPSession(page),frames=[];
 const finishPointer=await installRecordingPointer(page);
 let pending=Promise.resolve(),active=true,last=0,closedAt=null;
 const began=Date.now();page.once('close',()=>{closedAt=Date.now();active=false;});
 cdp.on('Page.screencastFrame',event=>{
  void cdp.send('Page.screencastFrameAck',{sessionId:event.sessionId}).catch(()=>{});
  const at=Date.now();if(!active||at-last<450)return;last=at;
  const file='frames/'+String(frames.length).padStart(6,'0')+'.jpg';
  frames.push({file,at});pending=pending.then(()=>fs.writeFile(path.join(output,file),Buffer.from(event.data,'base64')));
 });
 try{await cdp.send('Page.startScreencast',{format:'jpeg',quality:78,maxWidth:1600,maxHeight:1100,everyNthFrame:4});}
 catch(error){await finishPointer();throw error;}
 return async()=>{
  active=false;const end=closedAt??Date.now();let stopError=null;
  await cdp.send('Page.stopScreencast').catch(error=>{stopError=String(error);});await pending;
  const pointer=await finishPointer();
  await fs.writeFile(path.join(output,'frame-times.json'),JSON.stringify({began,end,frames,
   source:'Same existing installed Electron renderer; not native desktop/robot footage',
   no_second_browser_connection:true,stop_error:stopError,pointer},null,2),{flag:'wx'});
  if(!frames.length)throw Error('No actual renderer frames');
  const lines=['ffconcat version 1.0'];
  for(let i=0;i<frames.length;i++)lines.push("file '"+frames[i].file+"'",'duration '+Math.max(.02,((frames[i+1]?.at??end)-frames[i].at)/1000).toFixed(3));
  lines.push("file '"+frames.at(-1).file+"'");
  await fs.writeFile(path.join(output,'screen.ffconcat'),lines.join('\n'),{flag:'wx'});
  const log=await fs.open(path.join(output,'video-encode.log'),'wx');
  const child=spawn('ffmpeg',['-nostdin','-hide_banner','-loglevel','warning','-copyts','-start_at_zero',
   '-f','concat','-safe','0','-i',path.join(output,'screen.ffconcat'),
   '-vf','scale=1600:900:force_original_aspect_ratio=decrease,pad=1600:900:(ow-iw)/2:(oh-ih)/2',
   '-fps_mode','passthrough','-enc_time_base','1/1000','-c:v','libx264','-bf','0','-preset','fast','-crf','24',
   '-pix_fmt','yuv420p','-video_track_timescale','1000','-movflags','+faststart',path.join(output,'app-screen.mp4')],
   {windowsHide:true,stdio:['ignore',log.fd,log.fd]});
  const code=await new Promise((resolve,reject)=>{child.once('error',reject);child.once('exit',resolve);});await log.close();
  if(code!==0)throw Error('Actual renderer video encoding failed');
  return {path:'recording/app-screen.mp4',frames:frames.length,began,end,wall_ms:end-began,no_second_browser_connection:true,pointer};
 };
}
