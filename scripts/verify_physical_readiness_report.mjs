// SPDX-License-Identifier: Apache-2.0
// Local report QA only. This is not an App, model, Isaac or hardware test.
import {chromium} from '../apps/twinpulse-web/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL,fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
const out=path.resolve('outputs/robot-physical-readiness-20261018');
const report=path.join(out,'report.html');
const data=JSON.parse(await fs.readFile(path.join(out,'report-data.json'),'utf8'));
const result={classification:'LOCAL_REPORT_RENDER_QA_NOT_PRODUCT_ACCEPTANCE',status:'IN_PROGRESS',broken_local_references:[]};
// Use the existing installed browser only; do not download test runtimes.
const executablePath='C:/Program Files/Google/Chrome/Application/chrome.exe';
await fs.access(executablePath);
const browser=await chromium.launch({headless:true,executablePath});
try{
 const page=await browser.newPage({viewport:{width:1440,height:1100}});
 await page.route(/^https?:/,route=>route.abort());
 await page.goto(pathToFileURL(report).href,{waitUntil:'load'});
 const references=await page.locator('a[href],img[src]').evaluateAll(nodes=>nodes.map(n=>n.tagName==='IMG'?n.src:n.href));
 for(const reference of new Set(references)){
  const url=new URL(reference);if(url.protocol!=='file:')continue;
  try{await fs.access(fileURLToPath(url));}catch{result.broken_local_references.push(reference);}
 }
 result.requirement_rows=await page.locator('table').first().locator('tr').count()-1;
 result.requirements_final=data.requirements.rows.every(row=>!/(?:PENDING|IN_PROGRESS)/.test(row.result));
 result.raw_result_sha_checks=0;result.raw_result_sha_mismatches=[];
 for(const attempt of data.attempts){
  const actual=createHash('sha256').update(await fs.readFile(path.join(out,attempt.path))).digest('hex');
  result.raw_result_sha_checks++;if(actual!==attempt.raw_sha256)result.raw_result_sha_mismatches.push(attempt.path);
 }
 result.final_ui=data.attempts.filter(a=>a.result.status==='PASS'&&['fresh','reopen'].includes(a.result.phase)&&
  a.result.desktop?.engine?.release_id===data.active_install.release_id).map(a=>({path:a.path,phase:a.result.phase,steps:a.result.steps.length,launch_id:a.result.desktop.engine.launch_id}));
 await page.screenshot({path:path.join(out,'report-qa-top.png')});
 await page.getByRole('heading',{name:'요구사항별 판정',exact:true}).scrollIntoViewIfNeeded();
 await page.screenshot({path:path.join(out,'report-qa-requirements.png')});
 result.report_sha256=createHash('sha256').update(await fs.readFile(report)).digest('hex');
 result.status=result.broken_local_references.length===0&&result.raw_result_sha_mismatches.length===0&&result.requirement_rows===18&&result.requirements_final&&result.final_ui.length===2?'PASS':'FAIL';
}catch(e){result.status='FAIL';result.error=String(e);}
finally{await browser.close();await fs.writeFile(path.join(out,'report-qa.json'),JSON.stringify(result,null,2));}
console.log(JSON.stringify(result));if(result.status!=='PASS')process.exitCode=1;
