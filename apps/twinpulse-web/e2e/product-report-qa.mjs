// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {chromium,expect} from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const output=process.argv[2],name=process.argv[3]??'report-final.html',report=path.join(output,name),stem=path.parse(name).name;
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
const evidence={status:'FAIL',layouts:[],external_requests:[],errors:[]};
try{
  const page=await browser.newPage();page.on('pageerror',e=>evidence.errors.push(e.message));
  page.on('request',r=>{if(/^https?:/.test(r.url()))evidence.external_requests.push(r.url());});
  for(const size of [{width:1440,height:900},{width:430,height:900}]){
    await page.setViewportSize(size);await page.goto(pathToFileURL(report).href);
    const images=await page.evaluate(async()=>{
      const imgs=[...document.images];for(const img of imgs)img.loading='eager';
      await Promise.all(imgs.map(img=>img.decode()));return imgs.length;
    });
    const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
    expect(overflow).toBe(false);await expect(page.getByRole('heading',{level:1})).toHaveText('TwinPulse 실제 사용자 흐름 검증');
    await page.screenshot({path:path.join(output,`${stem}-qa-${size.width}.png`)});
    evidence.layouts.push({...size,images,overflow});
  }
  expect(evidence.external_requests).toEqual([]);expect(evidence.errors).toEqual([]);evidence.status='PASS';
}catch(error){evidence.error=String(error);}
finally{await browser.close();fs.writeFileSync(path.join(output,`${stem}-qa.json`),JSON.stringify(evidence,null,2));}
console.log(JSON.stringify(evidence));process.exitCode=evidence.status==='PASS'?0:1;
