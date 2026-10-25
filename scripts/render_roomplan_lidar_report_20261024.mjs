// SPDX-License-Identifier: Apache-2.0
// Local report-only rendering with existing Chrome; not product acceptance.
import {chromium} from '../apps/twinpulse-web/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const out=path.resolve('outputs/roomplan-lidar-review-20261024-02');
const browser=await chromium.launch({channel:'chrome',headless:true});
try{
 const p=await browser.newPage({viewport:{width:1280,height:900}}),errors=[];
 p.on('pageerror',e=>errors.push(String(e)));
 await p.goto(pathToFileURL(path.join(out,'report.html')).href);
 await p.locator('img').evaluateAll(images=>Promise.all(images.map(image=>image.decode())));
 await p.screenshot({path:path.join(out,'report-top.png')});
 await p.getByRole('img').screenshot({path:path.join(out,'overlay-hypothesis.png')});
 await fs.writeFile(path.join(out,'render-check.json'),JSON.stringify({status:errors.length?'FAIL':'PASS_REPORT_RENDER_ONLY',errors,
  images:await p.locator('img').evaluateAll(images=>images.map(i=>({complete:i.complete,width:i.naturalWidth,height:i.naturalHeight}))),
  overflow:await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth)},null,2),{flag:'wx'});
}finally{await browser.close();}
