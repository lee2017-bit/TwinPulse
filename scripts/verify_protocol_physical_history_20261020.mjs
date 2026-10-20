// SPDX-License-Identifier: Apache-2.0
// Existing local physical evidence only; NEVER Connect/Prepare/LiDAR/motion.
import fs from 'node:fs/promises';import path from 'node:path';import {createHash} from 'node:crypto';
import {attachPoweredSession} from './robot_powered_ui_session.mjs';
const out=path.resolve(process.argv[2]??'');if(!process.argv[2])throw Error('Explicit output required');
const priorBytes=await fs.readFile('outputs/robot-powered-20261020-current07/operation.json'),prior=JSON.parse(priorBytes);
if(prior.operation_id!=='39557dac1c1f44d3aebc01615d2df74b'||!prior.manifest.complete)throw Error('Wrong original closed physical export');
const s=await attachPoweredSession(out),p=s.page,result={status:'IN_PROGRESS',identity:s.identity,scope:'COLD_LOCAL_PHYSICAL_HISTORY_NOT_LIVE_ROBOT',prior_sha256:createHash('sha256').update(priorBytes).digest('hex'),download_events:[]};
const wait=ms=>new Promise(r=>setTimeout(r,ms)),poll=async(fn,ms=30000)=>{const end=Date.now()+ms;while(Date.now()<end){if(fn())return;await wait(100);}throw Error('Observed UI state timeout');};
const canonical=v=>JSON.stringify(v,(_,x)=>x&&typeof x==='object'&&!Array.isArray(x)?Object.fromEntries(Object.keys(x).sort().map(k=>[k,x[k]])):x);
try{
 await p.getByText('Isaac connected',{exact:true}).first().waitFor({state:'visible',timeout:120000});
 await p.getByRole('button',{name:'Open '+prior.project_id,exact:true}).click();await p.getByRole('banner').filter({hasText:prior.project_id}).waitFor({state:'visible'});
 const show=p.getByRole('button',{name:'Show Twin',exact:true});if(await show.isVisible())await show.click();
 const label='Imported existing settings · unverified';await p.locator('.robot-fleet-row').filter({hasText:label}).click();
 const drawer=p.getByRole('region',{name:'Control '+label,exact:true});await drawer.getByRole('button',{name:'Operation logs',exact:true}).click();
 const button=drawer.getByRole('button',{name:'Download operation JSON',exact:true});await button.waitFor({state:'visible'});
 const directory=path.join(out,'downloads');await fs.mkdir(directory);const cdp=await s.browser.newBrowserCDPSession();
 cdp.on('Browser.downloadWillBegin',e=>result.download_events.push({kind:'begin',...e}));cdp.on('Browser.downloadProgress',e=>result.download_events.push({kind:'progress',...e}));
 await cdp.send('Browser.setDownloadBehavior',{behavior:'allow',downloadPath:directory,eventsEnabled:true});
 const download=async button=>{const offset=result.download_events.length;await button.click();await poll(()=>result.download_events.slice(offset).some(x=>['completed','canceled'].includes(x.state)),20000);
  const events=result.download_events.slice(offset),end=events.findLast(x=>['completed','canceled'].includes(x.state));if(end?.state!=='completed')throw Error('Actual browser download '+end?.state);
  const file=events.find(x=>x.kind==='begin').suggestedFilename;if(path.basename(file)!==file)throw Error('Unexpected download name');
  const bytes=await fs.readFile(path.join(directory,file));return {file,bytes,sha256:createHash('sha256').update(bytes).digest('hex')};};
 const summary=await download(button),record=JSON.parse(summary.bytes),manifest=record.manifest;
 result.operation={file:summary.file,bytes:summary.bytes.length,sha256:summary.sha256,id:record.operation_id,events:record.events.length,
  original_events_equal:canonical(record.events)===canonical(prior.events),original_stream_equal:canonical(manifest.stream)===canonical(prior.manifest.stream),
  original_source_equal:canonical(manifest.source_twin_context)===canonical(prior.manifest.source_twin_context),cleanup:manifest.cleanup_confirmed};
 if(record.operation_id!==prior.operation_id||!result.operation.original_events_equal||!result.operation.original_stream_equal||!result.operation.original_source_equal)throw Error('Original physical history mismatch');
 const evidence=drawer.getByText(/^Physical runtime evidence ·/);await evidence.click();
 const segment=prior.manifest.stream.segments[0],rawButton=drawer.getByRole('button',{name:new RegExp('^Download .*'+segment.path.replaceAll('.','\\.')+'$')});
 await rawButton.waitFor({state:'visible'});result.selected_button=await rawButton.innerText();const raw=await download(rawButton);
 result.sensor_segment={file:raw.file,bytes:raw.bytes.length,sha256:raw.sha256,original:segment};
 if(raw.sha256!==segment.sha256||raw.bytes.length!==segment.bytes)throw Error('Original sensor segment SHA/size mismatch');
 result.physical=(s.fleet?.robots??[]).filter(x=>x.kind==='physical').map(x=>({id:x.robot_id,state:x.connection_state,operation:x.operation_id,drive:x.capabilities.drive}));
 if(result.physical.some(x=>x.operation||x.state!=='DISCONNECTED'||x.drive))throw Error('History restored physical authority');
 if(s.fleet_requests.some(x=>['connect','prepare','drive','command','lidar','field_test','field_arm'].includes(x.action)))throw Error('Unexpected physical action');
 result.status='PASS_SCOPED_ORIGINAL_PHYSICAL_HISTORY_AND_RAW_EXPORT';await s.shot('physical-history-raw');
}catch(error){result.status='FAIL';result.error=String(error);}
finally{
 await fs.writeFile(path.join(out,'result.json'),JSON.stringify(result,null,2));try{await s.finishVideo();}catch(e){result.video_error=String(e);}
 try{await p.getByRole('button',{name:'Exit TwinPulse',exact:true}).click();result.exit='NORMAL_UI_CLICK';}catch(e){result.exit_error=String(e);}
 await fs.writeFile(path.join(out,'result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify({status:result.status,error:result.error,operation:result.operation,sensor:result.sensor_segment}));
}
process.exitCode=result.status.startsWith('PASS')?0:1;
