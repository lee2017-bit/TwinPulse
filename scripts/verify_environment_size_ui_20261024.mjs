// SPDX-License-Identifier: Apache-2.0
// Current installed Electron UI, read-only inspection of the saved project.
// No physical actions, API writes, model calls or intercepted requests.
import {chromium,expect} from '../apps/twinpulse-web/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';
const [output]=process.argv.slice(2);
if(!output)throw Error('New output directory required');
await fs.mkdir(output,{recursive:false});
const result={status:'FAIL',scope:'INSTALLED_SIZE_AND_HELP_UI_ONLY_NOT_FULL_JOURNEY_OR_HARDWARE',steps:[],errors:[],requests:[],hardware_actions:0};
const browser=await chromium.connectOverCDP('http://127.0.0.1:19222');
const pages=browser.contexts().flatMap(c=>c.pages()).filter(p=>p.url().startsWith('http://127.0.0.1:8765/'));
if(pages.length!==1)throw Error('One installed renderer required');
const p=pages[0];p.setDefaultTimeout(30000);
p.on('pageerror',e=>result.errors.push(String(e).slice(0,1000)));
p.on('request',r=>{const url=new URL(r.url());if(url.pathname.startsWith('/v1/')&&r.method()!=='GET'){
  const row={path:url.pathname,method:r.method()};if(url.pathname.endsWith('/conversation'))try{row.action=r.postDataJSON().action;}catch{}
  result.requests.push(row);}});
const save=()=>fs.writeFile(path.join(output,'result.json'),JSON.stringify(result,null,2));
try{
 result.identity=await p.evaluate(()=>window.twinpulseDesktop?.versions());
 await expect(p.getByText('Isaac connected',{exact:true}).first()).toBeVisible({timeout:120000});
 const toggle=p.getByRole('button',{name:'Toggle conversations and projects',exact:true});
 if(await toggle.getAttribute('aria-expanded')!=='true')await toggle.click();
 await p.getByRole('button',{name:'Open chat_mvki3gm9_e212190a',exact:true}).click();
 const reopen=p.getByRole('button',{name:'Reopen saved scene',exact:true});await reopen.waitFor();await reopen.click();await reopen.waitFor({state:'hidden',timeout:40000});
 await p.getByRole('button',{name:'Import space',exact:true}).first().click();
 const panel=p.getByRole('region',{name:'Import space',exact:true});
 await expect(panel.getByText('Space imported · saved environment.',{exact:true})).toBeVisible();
 await panel.getByText('Objects and size',{exact:true}).click();
 await expect(panel.getByText(/not measured object dimensions/)).toBeVisible();
 const rows=panel.locator('li');await expect(rows).toHaveCount(30);
 result.inventory=await rows.allTextContents();
 if(result.inventory.filter(s=>/Sofa0/.test(s)).length!==1||result.inventory.filter(s=>/Chair[01]/.test(s)).length!==2)throw Error('Original object inventory mismatch');
 if(result.inventory.some(s=>!s.includes(' m')||s.includes('unavailable')))throw Error('Missing calculated bounds');
 for(const size of [[1280,720],[1024,768]]){
  await p.setViewportSize({width:size[0],height:size[1]});
  await panel.getByText('Objects and size',{exact:true}).scrollIntoViewIfNeeded();
  result.steps.push({size,status:'PASS',dimensions:await panel.evaluate(el=>({clientWidth:el.clientWidth,scrollWidth:el.scrollWidth}))});
  const dimensions=result.steps.at(-1).dimensions;if(dimensions.scrollWidth>dimensions.clientWidth+1)throw Error('Import panel horizontal overflow');
  await p.screenshot({path:path.join(output,`size-${size[0]}x${size[1]}.png`)});
 }
 // Close metadata without showing/replacing the Twin or connecting a robot.
 await panel.getByRole('button',{name:'Close import space',exact:true}).click();
 if(result.requests.some(r=>r.path.includes('robot-fleet')||r.path.includes('/physical-live')||r.path.includes('/environment/action')))throw Error('Unexpected mutation');
 if(result.errors.length)throw Error('Renderer errors');
 result.status='PASS_SCOPED';await save();
 await p.getByRole('button',{name:'Exit TwinPulse',exact:true}).click();await p.waitForEvent('close',{timeout:60000});
 result.exit='WINDOW_CLOSED';await save();
}catch(error){result.errors.push(String(error));await save();throw error;}
finally{await browser.close();}
