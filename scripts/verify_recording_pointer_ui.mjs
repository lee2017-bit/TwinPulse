// SPDX-License-Identifier: Apache-2.0
// Short real installed-window recording check. No generation, robot action or product API mutation.
import {chromium,expect} from '../apps/twinpulse-web/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';
import {recordRenderedPage} from './record_rendered_page.mjs';
import {installRecordingPointer} from './recording_pointer.mjs';
const args=process.argv.slice(2),arg=n=>args[args.indexOf(n)+1];
const out=arg('--output'),endpoint=arg('--cdp'),launch=arg('--launch');
if(!out||!/^http:\/\/127\.0\.0\.1:\d+$/.test(endpoint)||!launch)throw Error('Explicit current endpoint, launch and new output required');
await fs.mkdir(out,{recursive:false});
const result={status:'IN_PROGRESS',scope:'INSTALLED_RENDERER_POINTER_AND_CLICK_ANNOTATION_ONLY',physical:'OFF_NO_CONTACT',provider_generation_actions:0,steps:[],page_errors:[]};
let browser,page,finish;
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const observe=()=>page.evaluate(()=>{const h=document.querySelector('[data-tp-recording-pointer]');const s=window.__twinpulseRecordingPointerV1?.snapshot();
 const p=h?.getBoundingClientRect(),hit=s?.last?document.elementFromPoint(s.last.x,s.last.y):null;
 return {count:document.querySelectorAll('[data-tp-recording-pointer]').length,visible:!!h&&getComputedStyle(h).visibility==='visible',
  pointerEvents:h&&getComputedStyle(h).pointerEvents,ring:h?.shadowRoot?.querySelector('[data-press-ring]')?.getAttribute('opacity'),
  down:h?.dataset.down,hitIsOverlay:!!h&&(hit===h||h.contains(hit)),tipError:s?.last&&p?Math.hypot(p.x+24-s.last.x,p.y+24-s.last.y):null,
  ringsInsideSvg:!!h&&[...h.shadowRoot.querySelectorAll('circle')].every(c=>{const x=Number(c.getAttribute('cx')),y=Number(c.getAttribute('cy')),r=Number(c.getAttribute('r'))+1.5;return x-r>=0&&y-r>=0&&x+r<=64&&y+r<=64;}),...s};});
try{
 browser=await chromium.connectOverCDP(endpoint,{timeout:15000});
 const pages=browser.contexts().flatMap(c=>c.pages()).filter(p=>p.url().startsWith('http://127.0.0.1:8765/'));
 if(pages.length!==1)throw Error('Exactly one installed TwinPulse required');[page]=pages;page.setDefaultTimeout(15000);
 page.on('pageerror',e=>result.page_errors.push(String(e).replace(/#bootstrap=[^\s"']+/g,'#bootstrap=[REDACTED]')));
 result.identity=await page.evaluate(()=>window.twinpulseDesktop?.versions());
 if(result.identity?.engine?.launch_id!==launch)throw Error('Launch identity mismatch');
 await expect(page.getByRole('heading',{name:'What would you like to build?',exact:true})).toBeVisible();
 await expect(page.getByText('Isaac connected',{exact:true}).first()).toBeVisible({timeout:120000});
 finish=await recordRenderedPage(page,path.join(out,'recording'));
 if((await observe()).visible)throw Error('Cursor invented before a real event');
 const library=page.getByRole('button',{name:'Library',exact:true});await library.hover();await sleep(1000);
 const moved=await observe();if(!moved.visible||moved.tipError>.1||!moved.ringsInsideSvg||moved.pointerEvents!=='none'||moved.hitIsOverlay)throw Error('Pointer geometry/hit-test failed');
 result.steps.push({name:'Actual trusted hover follows position without intercepting input',status:'PASS',evidence:moved});
 await page.screenshot({path:path.join(out,'01-pointer.png')});await library.click();
 const dialog=page.getByRole('dialog',{name:'Model library'});await expect(dialog).toBeVisible();
 const clicked=await observe();if(clicked.presses<1||clicked.ring!=='1'||clicked.down!=='false')throw Error('Recent click not visible after actual button release');
 result.steps.push({name:'Actual click opens Library and records recent press, not held authority',status:'PASS',evidence:clicked});
 await page.screenshot({path:path.join(out,'02-click.png')});await sleep(1100);
 if((await observe()).ring!=='0')throw Error('Press annotation did not expire');
 const search=dialog.getByRole('textbox',{name:'Search models'});await search.click();await search.pressSequentially('desk',{delay:170});await sleep(1100);
 await expect(search).toHaveValue('desk');await page.screenshot({path:path.join(out,'03-search.png')});
 await dialog.getByRole('button',{name:'Close library',exact:true}).hover();await sleep(800);await dialog.getByRole('button',{name:'Close library',exact:true}).click();await sleep(1200);
 result.video=await finish();finish=null;
 await expect(page.locator('[data-tp-recording-pointer]')).toHaveCount(0);
 result.steps.push({name:'Recording stop removes overlay and listeners',status:'PASS',evidence:result.video.pointer});
 const cleanup=await installRecordingPointer(page);await page.reload();await expect(page.getByRole('heading',{name:'What would you like to build?',exact:true})).toBeVisible();
 await library.hover();await sleep(250);const reloaded=await observe();if(!reloaded.visible||reloaded.count!==1)throw Error('Reload pointer not restored exactly once');
 const reloadReceipt=await cleanup();if(reloadReceipt.documents!==2||reloadReceipt.errors.length)throw Error('Reload installation receipt failed');
 result.steps.push({name:'Reload reattaches once and cleanup retains no annotation',status:'PASS',evidence:reloadReceipt});
 await expect(page.locator('[data-tp-recording-pointer]')).toHaveCount(0);
 if(result.page_errors.length)throw Error('Unexpected renderer error during pointer check');
 await page.getByRole('button',{name:'Exit TwinPulse',exact:true}).click();await page.waitForEvent('close',{timeout:60000});
 result.status='PASS_POINTER_RECORDING';
}catch(e){result.status='FAIL';result.error=String(e).replace(/#bootstrap=[^\s"']+/g,'#bootstrap=[REDACTED]');if(page&&!page.isClosed())await page.screenshot({path:path.join(out,'failure.png')}).catch(()=>{});}
finally{if(finish)result.video=await finish().catch(e=>({error:String(e)}));if(browser)await browser.close();await fs.writeFile(path.join(out,'result.json'),JSON.stringify(result,null,2),{flag:'wx'});}
console.log(JSON.stringify({status:result.status,error:result.error,steps:result.steps.map(s=>s.name)}));
if(result.status!=='PASS_POINTER_RECORDING')process.exitCode=1;
