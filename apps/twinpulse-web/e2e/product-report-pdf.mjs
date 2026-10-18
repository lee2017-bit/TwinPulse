// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {chromium} from '@playwright/test';
import fs from 'node:fs';import path from 'node:path';import {pathToFileURL} from 'node:url';
const output=process.argv[2],destination=path.join(output,'TwinPulse-product-flow-final-report.pdf');
if(fs.existsSync(destination))throw new Error('Preserve the existing PDF');
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
try{
  const page=await browser.newPage({viewport:{width:1440,height:900}});
  await page.goto(pathToFileURL(path.join(output,'report-complete.html')).href);
  await page.evaluate(async()=>{
    // The complete original-run gallery stays in the single HTML. The PDF
    // contains the conclusion, numeric table/IDs and four actual key screens.
    document.querySelector('main > details')?.remove();
    for(const details of document.querySelectorAll('.box details')){
      const data=JSON.parse(details.querySelector('pre').textContent),section=document.createElement('div');
      const title=document.createElement('h3');title.textContent='회귀시험과 보존한 실패';section.append(title);
      for(const text of [...Object.values(data.regressions),...data.retained_failures,data.scope]){
        const paragraph=document.createElement('p');paragraph.textContent=text;section.append(paragraph);
      }
      details.replaceWith(section);
    }
    for(const image of document.images)image.loading='eager';
    await Promise.all([...document.images].map(image=>image.decode()));
  });
  await page.addStyleTag({content:'@media print {body{background:white;font-size:13px}main{padding:0;max-width:none}.box,section{padding:12px;margin:12px 0}figure{break-inside:avoid;page-break-inside:avoid}img{max-height:145mm;width:auto;max-width:100%;margin:auto}h1,h2,h3{break-after:avoid}tr{break-inside:avoid}table{font-size:11px}pre{font-size:11px}details{overflow:visible}}'});
  await page.pdf({path:destination,format:'A4',landscape:true,printBackground:true,
    displayHeaderFooter:true,headerTemplate:'<span></span>',footerTemplate:'<div style="font:9px Arial;width:100%;text-align:center;color:#556677">TwinPulse - 2026-10-13 - <span class="pageNumber"></span> / <span class="totalPages"></span></div>',
    margin:{top:'12mm',bottom:'16mm',left:'12mm',right:'12mm'}});
  console.log(JSON.stringify({pdf:destination,bytes:fs.statSync(destination).size}));
}finally{await browser.close();}
