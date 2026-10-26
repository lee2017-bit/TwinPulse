// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Jaewon Lee
// Viewport acceptance for the physical session gate (PHYS09): in the real App window (Test-mode CDP), emulate a
// 1536x800 CSS-px viewport, open the physical robot card in Control view and assert that the robot card is at least
// 320 px tall and that the session gate (confirmations, Prepare, Arm, Bootstrap stop) is fully visible without an
// inner scrollbar. Read-only DOM measurement; the only clicks are the robot row and the Control view toggle.
// usage: node scripts/session_gate_acceptance.mjs [robot-label-prefix="Imported existing settings"] [out-dir=outputs/session-gate]
import {chromium} from '../apps/twinpulse-web/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs';
import path from 'node:path';

export async function measureSessionGate(page,label){
 return page.evaluate(label=>{
  const dock=[...document.querySelectorAll('.robot-fleet-drawer')].find(e=>e.getAttribute('aria-label')==='Control '+label);
  const card=dock?.closest('.robot-fleet'),gate=dock?.querySelector('.robot-fleet-session-gate'),link=dock?.querySelector('.robot-fleet-link-status');
  if(!card||!gate)return {found:false,card:!!card,gate:!!gate};
  const r=gate.getBoundingClientRect(),c=card.getBoundingClientRect();
  const clipped=[];
  for(let parent=gate.parentElement;parent;parent=parent.parentElement){
   const s=getComputedStyle(parent);const box=parent.getBoundingClientRect();
   if(['hidden','clip','auto','scroll'].includes(s.overflowY)&&(r.top<box.top-1||r.bottom>box.bottom+1))clipped.push(parent.className||parent.tagName);
  }
  const checkboxes=[...gate.querySelectorAll('input[type=checkbox]')].map(e=>{const b=e.getBoundingClientRect();return {w:b.width,h:b.height,inside:b.top>=0&&b.bottom<=innerHeight};});
  return {found:true,viewport:{width:innerWidth,height:innerHeight},card_height:c.height,gate:{top:r.top,bottom:r.bottom,height:r.height,scrollHeight:gate.scrollHeight,clientHeight:gate.clientHeight},
   gate_in_viewport:r.top>=0&&r.bottom<=innerHeight,clipped_by:clipped,checkboxes,link_status:link?.textContent??null,
   control_view:!!document.querySelector('.is-control-view')};
 },label);
}
export function checkSessionGate(value){
 const problems=[];
 if(!value.found)problems.push('robot card or session gate missing');
 else{
  if(value.card_height<320)problems.push(`robot card height ${value.card_height.toFixed(0)} px < 320`);
  if(value.gate.scrollHeight>value.gate.clientHeight+2)problems.push('session gate has an inner scrollbar');
  if(!value.gate_in_viewport)problems.push('session gate leaves the viewport');
  if(value.clipped_by.length)problems.push('session gate clipped by '+value.clipped_by.join(', '));
  if(value.checkboxes.length<4||value.checkboxes.some(c=>c.w<16||c.h<16||!c.inside))problems.push('a confirmation checkbox is small or off-screen');
 }
 return problems;
}

if(import.meta.url===`file:///${process.argv[1].replace(/\\/g,'/')}`||process.argv[1]?.endsWith('session_gate_acceptance.mjs')){
 const prefix=process.argv[2]||'Imported existing settings',outDir=process.argv[3]||'outputs/session-gate';
 const browser=await chromium.connectOverCDP('http://127.0.0.1:19222',{timeout:15000});
 const page=browser.contexts().flatMap(c=>c.pages()).find(x=>/^http:\/\/127\.0\.0\.1:\d+\//.test(x.url()));
 if(!page)throw new Error('TwinPulse page not found on the Test-mode CDP endpoint');
 const session=await page.context().newCDPSession(page);
 await session.send('Emulation.setDeviceMetricsOverride',{width:1536,height:800,deviceScaleFactor:1,mobile:false});
 await page.waitForTimeout(1200);
 const region=page.getByRole('region',{name:'Robot fleet',exact:true});
 const row=region.getByRole('button',{name:new RegExp(prefix+'.* Physical')}).last();
 const label=(await row.getAttribute('title'))?.split(' · ')[0]??prefix;
 if(!(await page.getByRole('region',{name:'Control '+label,exact:true}).count())){await row.click();await page.waitForTimeout(1500);}
 const cv=page.getByRole('button',{name:'Control view',exact:true});
 if(await cv.count()&&!(await page.evaluate(()=>!!document.querySelector('.is-control-view')))){await cv.click();await page.waitForTimeout(1500);}
 fs.mkdirSync(outDir,{recursive:true});
 const value=await measureSessionGate(page,label);const problems=checkSessionGate(value);
 const shot=path.join(outDir,`session-gate-1536x800-${Date.now()}.png`);await page.screenshot({path:shot});
 fs.writeFileSync(path.join(outDir,'session-gate-measure.json'),JSON.stringify({value,problems,screenshot:shot},null,1));
 await session.send('Emulation.clearDeviceMetricsOverride');
 console.log((problems.length?'FAIL ':'PASS ')+JSON.stringify({problems,card_height:value.card_height,gate:value.gate,link_status:value.link_status,screenshot:shot}));
 await browser.close();
 if(problems.length)process.exit(1);
}
