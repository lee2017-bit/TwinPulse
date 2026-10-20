// SPDX-License-Identifier: Apache-2.0
// Actual same installed BrowserWindow clicks; no product API mutation or model mock.
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {attachPoweredSession} from './robot_powered_ui_session.mjs';
const out=process.argv[2];if(!out)throw Error('Explicit output required');
const s=await attachPoweredSession(path.resolve(out)),p=s.page;
const result={status:'IN_PROGRESS',identity:s.identity,scope:'COLD_HISTORY_UI_EXPORT_ONLY_NO_ROBOT_CONNECTION',steps:[],downloads:[]};
const wait=ms=>new Promise(r=>setTimeout(r,ms));
const disk=async()=>{const v=await fs.statfs('C:\\');return Number(v.bavail)*Number(v.bsize);};
const canonical=v=>JSON.stringify(v,(_,x)=>x&&typeof x==='object'&&!Array.isArray(x)?Object.fromEntries(Object.keys(x).sort().map(k=>[k,x[k]])):x);
try{
 result.free_before=await disk();
 await p.getByText('Isaac connected',{exact:true}).first().waitFor({state:'visible',timeout:120000});
 const open=p.getByRole('button',{name:'Open chat_mvf2wo4i_587adab8',exact:true});
 const readyUntil=Date.now()+120000;while(!await open.isEnabled()){if(Date.now()>=readyUntil)throw Error('Original saved chat not enabled after startup');await wait(200);}
 await open.click();
 await p.getByRole('banner').filter({hasText:'chat_mvf2wo4i_587adab8'}).waitFor({state:'visible',timeout:30000});
 await p.locator('.robot-fleet-row').filter({hasText:'TurtleBot3'}).click();
 const drawer=p.getByRole('region',{name:'Control TurtleBot3',exact:true});
 await drawer.getByRole('button',{name:'Operation logs',exact:true}).click();
 const button=drawer.getByRole('button',{name:'Download operation JSON',exact:true});await button.waitFor({state:'visible'});
 const directory=path.resolve(out,'downloads');await fs.mkdir(directory);
 const cdp=await s.browser.newBrowserCDPSession();
 cdp.on('Browser.downloadWillBegin',e=>result.downloads.push({kind:'begin',...e}));
 cdp.on('Browser.downloadProgress',e=>result.downloads.push({kind:'progress',...e}));
 await cdp.send('Browser.setDownloadBehavior',{behavior:'allow',downloadPath:directory,eventsEnabled:true});
 await button.click();
 const until=Date.now()+20000;while(Date.now()<until&&!result.downloads.some(x=>['completed','canceled'].includes(x.state)))await wait(100);
 result.free_at_download=await disk();
 const ended=result.downloads.findLast(x=>['completed','canceled'].includes(x.state));
 if(ended?.state!=='completed')throw Error('Actual native browser transfer '+(ended?.state??'NOT_OBSERVED'));
 const filename=result.downloads.find(x=>x.kind==='begin').suggestedFilename;
 const bytes=await fs.readFile(path.join(directory,filename)),record=JSON.parse(bytes);
 const originalPath=process.argv[3]??'outputs/robot-protocol-prep-20261020/preserved-ui01/05-b29466e53e804d0e96af28f03cf6371f.json';
 const originalBytes=await fs.readFile(originalPath),original=JSON.parse(originalBytes);
 result.prior={path:originalPath,sha256:createHash('sha256').update(originalBytes).digest('hex')};
 const equal=record.operation_id===original.operation_id&&canonical(record.events)===canonical(original.events)
   &&canonical(record.manifest.source_twin_context)===canonical(original.manifest.source_twin_context);
 result.file={filename,bytes:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex'),operation_id:record.operation_id,
  events:record.events.length,original_canonical_events_and_source_equal:equal,manifest:record.manifest};
 if(!equal)throw Error('Original closed operation differs');
 result.steps.push({name:'Actual cold UI download, exact original canonical events and Twin source',status:'PASS'});
 await p.getByRole('button',{name:'Robots',exact:true}).click();
 const panel=p.getByRole('dialog'),pc=panel.getByRole('button',{name:'Check PC preparation',exact:true});
 await pc.click();const checks=panel.getByRole('region',{name:'PC connection preparation',exact:true});
 await checks.getByText('PC prerequisites found · robot connection not checked',{exact:true}).waitFor({state:'visible',timeout:20000});
 if(!await panel.getByRole('button',{name:'Check connection (read-only)',exact:true}).isEnabled())throw Error('Connection entry unavailable');
 result.steps.push({name:'Actual Robots PC preparation and enabled explicit connection entry; no SSH request',status:'PASS',evidence:await checks.innerText()});
 await s.shot('pc-preparation');await panel.getByRole('button',{name:/^Close/}).click();
 result.status='PASS_SCOPED_COLD_UI_EXPORT';
 await s.shot('export-result');
}catch(error){result.status='FAIL';result.error=String(error);}
finally{
 result.physical=(s.fleet?.robots??[]).filter(x=>x.kind==='physical').map(x=>({id:x.robot_id,state:x.connection_state,operation:x.operation_id}));
 await fs.writeFile(path.join(out,'result.json'),JSON.stringify(result,null,2));
 try{await s.finishVideo();}catch(error){result.video_error=String(error);}
 try{await p.getByRole('button',{name:'Exit TwinPulse',exact:true}).click();result.exit='NORMAL_UI_CLICK';}catch(error){result.exit_error=String(error);}
 await fs.writeFile(path.join(out,'result.json'),JSON.stringify(result,null,2));
 console.log(JSON.stringify({status:result.status,error:result.error,free:result.free_at_download,file:result.file?.filename,download:result.downloads.at(-1)}));
}
process.exitCode=result.status.startsWith('PASS')?0:1;
