// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// Local report QA only; no product mutations or external requests.
import {chromium, expect} from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
function option(name,fallback){const index=process.argv.indexOf(name);return index>=0?process.argv[index+1]:fallback;}
const output=path.resolve(option('--output','../../outputs/generation-preview-20261012'));
if(!['generation-preview-20261012','progressive-preview-20261013'].some(name=>output===path.resolve('../../outputs',name)))throw Error('Unsupported local report output');
const stem=option('--stem','report');
if(!/^[a-z0-9-]+$/.test(stem))throw new Error('Invalid local report stem');
const expectedImages=Number(option('--images','18'));
const expectedHeadings=Number(option('--headings','8'));
const title=option('--title','TwinPulse 생성 미리보기 검증 결과');
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
const result={status:'FAIL',external_requests:0,page_errors:[],views:[]};
try{
  const context=await browser.newContext();
  await context.route('**/*',route=>{
    if(!['file:','data:'].includes(new URL(route.request().url()).protocol)){
      result.external_requests++;return route.abort();
    }
    return route.continue();
  });
  const page=await context.newPage();page.on('pageerror',error=>result.page_errors.push(error.message));
  for(const size of [{width:1440,height:1000},{width:390,height:844}]){
    await page.setViewportSize(size);
    await page.goto(pathToFileURL(path.join(output,`${stem}.html`)).href);
    await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible();
    const state=await page.evaluate(()=>({
      images:[...document.images].map(image=>({loaded:image.complete&&image.naturalWidth>0,source:image.src.startsWith('data:')})),
      width:document.documentElement.scrollWidth,viewport:innerWidth,
      headings:[...document.querySelectorAll('h2')].length,
    }));
    expect(state.images).toHaveLength(expectedImages);expect(state.images.every(image=>image.loaded&&image.source)).toBe(true);
    expect(state.width).toBeLessThanOrEqual(size.width);expect(state.headings).toBe(expectedHeadings);
    await page.screenshot({path:path.join(output,`${stem}-${size.width}.png`)});
    result.views.push({...size,...state});
  }
  expect(result.external_requests).toBe(0);expect(result.page_errors).toEqual([]);result.status='PASS';
  if(process.argv.includes('--pdf')){
    await page.setViewportSize({width:1440,height:1000});
    await page.pdf({path:path.join(output,`${stem}.pdf`),format:'A4',printBackground:true,
      margin:{top:'14mm',bottom:'16mm',left:'12mm',right:'12mm'},displayHeaderFooter:true,
      headerTemplate:'<span></span>',footerTemplate:'<div style="font-size:9px;color:#555;width:100%;text-align:center">TwinPulse | <span class="pageNumber"></span> / <span class="totalPages"></span></div>'});
    result.pdf=`${stem}.pdf`;
  }
}catch(error){result.error=String(error);process.exitCode=1;}
finally{await browser.close();fs.writeFileSync(path.join(output,`${stem}-qa.json`),JSON.stringify(result,null,2));}
console.log(`REPORT_QA_${result.status}`);
