// SPDX-License-Identifier: Apache-2.0
// Read-only diagnosis through the same installed Test BrowserWindow.
import {chromium} from '../apps/twinpulse-web/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs/promises';
const output=process.argv[2];if(!output)throw Error('Output directory required');
await fs.mkdir(output,{recursive:false});
const browser=await chromium.connectOverCDP('http://127.0.0.1:19222');
try{
 const pages=browser.contexts().flatMap(c=>c.pages()).filter(p=>p.url().startsWith('http://127.0.0.1:8765/'));
 if(pages.length!==1)throw Error('One installed renderer required');const page=pages[0];
 const identity=await page.evaluate(()=>window.twinpulseDesktop?.versions());if(!identity?.engine?.launch_id)throw Error('No installed identity');
 await page.getByRole('button',{name:'Diagnostics',exact:true}).click();
 await page.waitForTimeout(1500);
 const text=(await page.locator('body').innerText()).replace(/#bootstrap=\S+/g,'#bootstrap=[REDACTED]');
 await fs.writeFile(output+'/visible.txt',text);await page.screenshot({path:output+'/diagnostics.png'});
 console.log(text.slice(-18000));
}finally{await browser.close();}
