// SPDX-License-Identifier: Apache-2.0
// Local report QA only. Separate Chrome is never App acceptance.
import {chromium,expect} from '../apps/twinpulse-web/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
const out=path.resolve('outputs/robot-app-field-tests-20261018');
const data=JSON.parse(await fs.readFile(path.join(out,'report-data.json'),'utf8'));
const results=[];
for(const attempt of data.attempts){
 const raw=await fs.readFile(path.join(out,attempt.path));
 if(createHash('sha256').update(raw).digest('hex')!==attempt.sha256)throw Error('Raw attempt changed');
 results.push({path:attempt.path,status:attempt.result.status,sha256:attempt.sha256});
}
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
const page=await browser.newPage({viewport:{width:1440,height:1000}});
await page.goto(pathToFileURL(path.join(out,'report.html')).href);
await expect(page.getByRole('heading',{name:'TwinPulse · 로봇 전원 이후 앱만으로 진행하는 시험 준비'})).toBeVisible();
const targets=await page.locator('a[href],img[src]').evaluateAll(nodes=>nodes.map(n=>n.getAttribute('href')??n.getAttribute('src')));
for(const target of targets)await fs.access(path.resolve(out,target));
await page.screenshot({path:path.join(out,'report-overview.png')});
await page.getByRole('heading',{name:'요구별 판정',exact:true}).scrollIntoViewIfNeeded();
await page.screenshot({path:path.join(out,'report-requirements.png')});
await browser.close();
const qa={status:'PASS_LOCAL_DOCUMENT_QA_ONLY',links_and_images:targets.length,raw_attempts:results,
 report_sha256:createHash('sha256').update(await fs.readFile(path.join(out,'report.html'))).digest('hex')};
await fs.writeFile(path.join(out,'report-qa.json'),JSON.stringify(qa,null,2));console.log(JSON.stringify({status:qa.status,links:targets.length}));
