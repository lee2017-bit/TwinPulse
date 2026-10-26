// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Jaewon Lee
// Multi-viewport check of the physical session gate against a running TwinPulse web UI (source launcher in browser
// mode, or the installed App's HTTP port). Drives a local Chromium/Edge, never the robot. For each viewport: open the
// project, select the physical robot, switch to Control view, then verify that the three confirmations plus the Arm
// and Bootstrap rows are visible (in the viewport, or reachable by the card's own scroll with the buttons in view),
// that the Twin pane is not clipped by the panel, and that no two gate children overlap (2-column layout check).
// usage: node scripts/session_gate_viewports.mjs <ui-url> [project-id] [robot-label-prefix] [out-dir]
import {chromium} from '../apps/twinpulse-web/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs';
import path from 'node:path';

const [url,projectId='chat_mvp9mbiw_9253ff0c',prefix='Imported existing settings',outDir='outputs/session-gate']=process.argv.slice(2);
if(!url)throw new Error('usage: session_gate_viewports.mjs <ui-url> [project-id] [robot-label-prefix] [out-dir]');
const VIEWPORTS=[[1536,800],[1536,864],[1920,1080],[1280,720],[1099,800],[1101,800]];
// 'cdp:<endpoint>' attaches to a browser the launcher opened with the one-use bootstrap link (session already valid);
// otherwise a local headless Edge is launched and the url must carry a valid session.
const viaCdp=url.startsWith('cdp:');
const target=url.startsWith('file:')?fs.readFileSync(url.slice(5),'utf-8').trim():url;  // file:<path> holds a one-use bootstrap link; never print it
let sharedContext=null,sharedPage=null;
const browser=viaCdp?await chromium.connectOverCDP(url.slice(4),{timeout:15000}):await chromium.launch({channel:'msedge',headless:true});
fs.mkdirSync(outDir,{recursive:true});
const results=[];
for(const [width,height] of VIEWPORTS){
  let context,page,cdp=null;
  if(viaCdp){context=browser.contexts()[0];page=context.pages().find(x=>/^http:\/\/127\.0\.0\.1:\d+\//.test(x.url()))||context.pages()[0];
    cdp=await context.newCDPSession(page);await cdp.send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});await page.waitForTimeout(1200);}
  else{if(!sharedContext){sharedContext=await browser.newContext({viewport:{width,height},deviceScaleFactor:1});sharedPage=await sharedContext.newPage();await sharedPage.goto(target,{waitUntil:'domcontentloaded',timeout:60000});await sharedPage.waitForTimeout(4000);}
    context=sharedContext;page=sharedPage;await page.setViewportSize({width,height});await page.waitForTimeout(1200);}
  const problems=[];let value=null;
  try{
    // the session was bootstrapped once on the shared page; re-opening the project per viewport is idempotent
    const toggle=page.getByRole('button',{name:'Toggle conversations and projects',exact:true});
    const open=page.getByRole('button',{name:'Open '+projectId,exact:true});
    if(!(await open.count())&&await toggle.count()){await toggle.first().click();await page.waitForTimeout(1200);}
    if(await open.count()){await open.first().click();await page.waitForTimeout(3500);}
    if(await toggle.count()&&(await toggle.first().getAttribute('aria-expanded'))==='true'){await toggle.first().click();await page.waitForTimeout(800);}
    const region=page.getByRole('region',{name:'Robot fleet',exact:true});
    const row=region.getByRole('button',{name:new RegExp(prefix+'.* Physical')}).last();
    if(!(await page.getByRole('region',{name:new RegExp('^Control '+prefix)}).count())){await row.click();await page.waitForTimeout(1500);}
    const cv=page.getByRole('button',{name:'Control view',exact:true});
    if(await cv.count()&&!(await page.evaluate(()=>!!document.querySelector('.is-control-view')))){await cv.click();await page.waitForTimeout(1500);}
    value=await page.evaluate(prefix=>{
      const dock=[...document.querySelectorAll('.robot-fleet-drawer')].find(e=>(e.getAttribute('aria-label')||'').startsWith('Control '+prefix));
      const card=dock?.closest('.robot-fleet'),gate=dock?.querySelector('.robot-fleet-session-gate'),panel=document.querySelector('.chat-twin-panel'),slot=document.querySelector('.twin-frame-slot');
      if(!card||!gate)return {found:false};
      const r=e=>e.getBoundingClientRect();
      const inView=b=>b.top>=0&&b.bottom<=innerHeight&&b.left>=0&&b.right<=innerWidth;
      const items={};
      for(const [key,sel] of [['present','input[type=checkbox]'],['arm','button']]){}
      const boxes=[...gate.querySelectorAll('input[type=checkbox]')].map(e=>r(e));
      const buttons=[...gate.querySelectorAll('button')].map(e=>({name:e.textContent.trim(),box:r(e)}));
      // overlap check among direct children of the gate (2-column layout)
      const children=[...gate.children].map(e=>({cls:e.className||e.tagName,box:r(e)})).filter(c=>c.box.width>0&&c.box.height>0);
      const overlaps=[];
      for(let i=0;i<children.length;i++)for(let j=i+1;j<children.length;j++){const a=children[i].box,b=children[j].box;
        const ix=Math.min(a.right,b.right)-Math.max(a.left,b.left),iy=Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top);
        if(ix>2&&iy>2)overlaps.push([children[i].cls.slice(0,30),children[j].cls.slice(0,30),Math.round(ix),Math.round(iy)]);}
      const cardBox=r(card),gateBox=r(gate),panelBox=panel?r(panel):null,slotBox=slot?r(slot):null;
      // reachable by the card's own scroll: scroll the gate into view inside the card and re-measure the buttons
      gate.scrollIntoView({block:'end'});
      const afterScroll={gate:r(gate),buttons:[...gate.querySelectorAll('button')].map(e=>({name:e.textContent.trim(),box:r(e)}))};
      return {found:true,viewport:{width:innerWidth,height:innerHeight},card:{height:cardBox.height,scrollHeight:card.scrollHeight,clientHeight:card.clientHeight},
        gate:{top:gateBox.top,bottom:gateBox.bottom,height:gateBox.height},checkboxes:boxes.map(b=>({w:b.width,h:b.height,inView:inView(b)})),
        buttons:buttons.map(b=>({name:b.name,inView:inView(b.box)})),afterScroll:{gateInView:inView(afterScroll.gate),buttons:afterScroll.buttons.map(b=>({name:b.name,inView:inView(b.box)}))},
        overlaps,panel:panelBox?{scrollHeight:panel.scrollHeight,clientHeight:panel.clientHeight,bottom:panelBox.bottom}:null,
        twinSlot:slotBox?{height:slotBox.height,inView:inView(slotBox),top:slotBox.top,bottom:slotBox.bottom}:null,controlView:!!document.querySelector('.is-control-view')};
    },prefix);
    if(!value.found)problems.push('robot card or session gate missing');
    else{
      const required=['Run same-boot stop qualification','Arm supervised field session','Run Bootstrap stop'];
      const visibleNow=value.buttons.filter(b=>required.includes(b.name)&&b.inView).length;
      const visibleAfter=value.afterScroll.buttons.filter(b=>required.includes(b.name)&&b.inView).length;
      if(visibleNow<3&&visibleAfter<3)problems.push(`Arm/Bootstrap rows not reachable: ${visibleNow} visible, ${visibleAfter} after card scroll`);
      if(value.checkboxes.length<4||value.checkboxes.some(c=>c.w<16||c.h<16))problems.push('a confirmation checkbox is small');
      if(value.overlaps.length)problems.push('gate children overlap: '+JSON.stringify(value.overlaps));
      if(value.twinSlot&&(value.twinSlot.height<100||value.twinSlot.top<0))problems.push(`Twin pane clipped/too small: ${JSON.stringify(value.twinSlot)}`);
    }
  }catch(error){problems.push('error: '+String(error.message||error).slice(0,200));}
  const shot=path.join(outDir,`gate-${width}x${height}.png`);await page.screenshot({path:shot,fullPage:false}).catch(()=>{});
  results.push({viewport:`${width}x${height}`,problems,value,screenshot:shot});
  console.log((problems.length?'FAIL ':'PASS ')+`${width}x${height} `+JSON.stringify({problems,card:value?.card,gate:value?.gate,twin:value?.twinSlot,overlaps:value?.overlaps,buttonsNow:value?.buttons?.filter(b=>b.inView).map(b=>b.name),buttonsAfterScroll:value?.afterScroll?.buttons?.filter(b=>b.inView).map(b=>b.name)}).slice(0,600));
  if(viaCdp){await cdp.send('Emulation.clearDeviceMetricsOverride').catch(()=>{});}
}
if(sharedContext)await sharedContext.close();
fs.writeFileSync(path.join(outDir,'viewports.json'),JSON.stringify(results,null,1));
await browser.close();
if(results.some(r=>r.problems.length))process.exit(1);
