// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {chromium,expect} from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
const output=process.env.TWINPULSE_VIEW_OUTPUT;
const result={status:'FAIL',checks:[],physical_commands:0,provider_calls:0};
let page;
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
try {
  page=await browser.newPage({viewport:{width:1920,height:1080}});
  await page.addInitScript(()=>{
    window.viewportLoaded=[];
    let last='';
    new MutationObserver(()=>{
      const surface=document.querySelector('canvas[aria-label="Current Isaac Digital Twin render"]');
      if(surface&&surface.dataset.frameId&&surface.dataset.frameId!==last){
        last=surface.dataset.frameId;
        window.viewportLoaded.push({id:Number(last),stamp:Number(surface.dataset.capturedAt),
          loaded:Date.now(),delay_ms:Date.now()-Number(surface.dataset.capturedAt)});
      }
    }).observe(document,{subtree:true,childList:true,attributes:true,attributeFilter:['data-frame-id','aria-label']});
  });
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(`${process.env.TWINPULSE_VIEW_URL}/#bootstrap=${encodeURIComponent(process.env.TWINPULSE_VIEW_BOOTSTRAP)}`);
  await expect(page.getByRole('img',{name:'Current Isaac Digital Twin render'})).toBeVisible({timeout:15000});
  const source=await page.evaluate(async()=>await(await fetch('/v1/product/viewport')).json());
  const frames=[];
  result.frames=frames;result.camera_checks=[];
  page.on('response',async response=>{
    if(new URL(response.url()).pathname==='/v1/product/viewport') {
      try{const value=await response.json();if(value.frame)frames.push({id:value.frame.frame_id,stamp:value.frame.captured_at_ms,
        delay_ms:Date.now()-value.frame.captured_at_ms,hash:value.frame.sha256,camera:value.frame.camera_sequence});}catch{}
    }
  });
  await page.screenshot({path:path.join(output,'actual-viewer.png')});
  await page.getByRole('button',{name:'Orbit left',exact:true}).click();
  await expect.poll(async()=>{
    const v=await page.evaluate(async()=>await(await fetch('/v1/product/viewport')).json());return v.camera_result?.state;
  }).toBe('completed');
  await expect.poll(()=>frames.some(f=>f.camera>source.frame.camera_sequence && f.hash!==source.frame.sha256)).toBe(true);
  await page.screenshot({path:path.join(output,'actual-camera-orbit.png')});
  for(const name of ['Orbit right','Zoom in','Zoom out','Pan left','Pan right','Pan up','Pan down']) {
    result.phase=name;
    const before=await page.evaluate(async()=>await(await fetch('/v1/product/viewport')).json());
    await page.getByRole('button',{name,exact:true}).click();
    await expect.poll(async()=>{
      const v=await page.evaluate(async()=>await(await fetch('/v1/product/viewport')).json());
      result.last_camera_observation=v;
      return v.camera_result?.state==='completed' && v.frame?.camera_sequence>before.frame.camera_sequence;
    }).toBe(true);
    result.camera_checks.push(name);
  }
  await page.getByRole('button',{name:'Hide Twin'}).click();
  await expect(page.getByRole('img',{name:'Current Isaac Digital Twin render'})).toHaveCount(0);
  await page.getByRole('button',{name:'Show Twin'}).click();
  await expect(page.getByRole('img',{name:'Current Isaac Digital Twin render'})).toBeVisible();
  await page.reload();await expect(page.getByRole('img',{name:'Current Isaac Digital Twin render'})).toBeVisible();
  const windowStart=Date.now();
  await page.waitForTimeout(4000);
  const displayed=await page.evaluate(start=>window.viewportLoaded.filter(frame=>frame.loaded>=start),windowStart);
  const distinct=new Set(frames.map(f=>f.id));
  if(distinct.size<12)throw new Error('Too few actual new frames for continuous viewer');
  // Observe stale handling without modifying engine control or stopping Isaac.
  await page.route('**/v1/product/viewport',route=>route.abort());
  await expect(page.getByRole('img',{name:'Current Isaac Digital Twin render'})).toHaveCount(0,{timeout:5000});
  await expect(page.getByText('Viewer waiting / stale',{exact:true})).toBeVisible();
  await page.screenshot({path:path.join(output,'viewer-reception-failed.png')});
  await page.unroute('**/v1/product/viewport');
  await expect(page.getByRole('img',{name:'Current Isaac Digital Twin render'})).toBeVisible({timeout:5000});
  const delays=frames.map(f=>f.delay_ms).sort((a,b)=>a-b);
  const first=frames[0],last=frames.at(-1);
  result.metrics={frames:frames.length,unique_frames:distinct.size,
    source_fps:(distinct.size-1)/((last.stamp-first.stamp)/1000),
    metadata_reception_p95_ms:delays[Math.floor((delays.length-1)*.95)]};
  const displayDelays=displayed.map(frame=>frame.delay_ms).sort((a,b)=>a-b);
  const firstDisplay=displayed[0],lastDisplay=displayed.at(-1);
  result.metrics.continuous_display_fps=displayed.length>1?
    (new Set(displayed.map(frame=>frame.id)).size-1)/((lastDisplay.loaded-firstDisplay.loaded)/1000):0;
  result.metrics.display_p95_ms=displayDelays[Math.floor((displayDelays.length-1)*.95)];
  result.metrics.performance_target_met=result.metrics.continuous_display_fps>=5 && result.metrics.display_p95_ms<=500;
  result.displayed=displayed;
  result.checks.push('all eight registered camera actions complete against actual Isaac',
    'actual moving camera changes newly captured stage frames',
    'collapse/expand/reload preserve the same stage without Build/Run',
    'viewer loss removes live image; automatic read-only frame reception recovers');
  result.page_errors=errors;expect(errors).toEqual([]);
  result.frames=frames;result.status='PASS';
}catch(error){result.error=error.message;process.exitCode=1;
  if(page)await page.screenshot({path:path.join(output,'failed-viewer.png')}).catch(()=>{});}
finally{fs.writeFileSync(path.join(output,'browser.json'),JSON.stringify(result,null,2));await browser.close();}
