// SPDX-License-Identifier: Apache-2.0
import {chromium} from '../apps/twinpulse-web/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs/promises';
const output=process.argv[2];if(!output)throw Error('Explicit output required');
const browser=await chromium.connectOverCDP('http://127.0.0.1:19222');
try{
 const pages=browser.contexts().flatMap(c=>c.pages()).filter(p=>p.url().startsWith('http://127.0.0.1:8765/'));
 if(pages.length!==1)throw Error('One installed renderer required');const page=pages[0];
 const identity=await page.evaluate(()=>window.twinpulseDesktop?.versions());if(!identity?.engine?.launch_id)throw Error('No installed identity');
 const diag=page.getByRole('button',{name:'Close diagnostics',exact:true});if(await diag.isVisible())await diag.click();
 const modal=page.getByRole('dialog');if(await modal.isVisible())await modal.getByRole('button',{name:'Close',exact:true}).click();
 const closing=page.waitForEvent('close',{timeout:60000});const start=Date.now();
 await page.getByRole('button',{name:'Exit TwinPulse',exact:true}).click();await closing;
 await fs.writeFile(output,JSON.stringify({status:'PASS_NORMAL_UI_EXIT_TEST_MODE',identity,elapsed_ms:Date.now()-start},null,2),{flag:'wx'});
}finally{await browser.close();}
