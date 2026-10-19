// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// Visible privacy preparation only; never seeds App/scene state or calls APIs.
import {chromium,expect} from '../apps/twinpulse-web/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs/promises';
const out=process.argv[2];if(!out)throw Error('New output directory required');
await fs.mkdir(out,{recursive:false});
const browser=await chromium.connectOverCDP('http://127.0.0.1:19222');
try{
 const pages=browser.contexts().flatMap(c=>c.pages()).filter(p=>p.url().startsWith('http://127.0.0.1:8765/'));
 if(pages.length!==1)throw Error('Expected actual installed BrowserWindow');
 const page=pages[0];
 await expect(page.getByRole('heading',{name:'What would you like to build?',exact:true})).toBeVisible({timeout:120000});
 const sidebar=page.locator('.chat-sidebar-slot');if(await sidebar.isVisible())await page.getByRole('button',{name:'Toggle conversations and projects',exact:true}).click();
 await expect(sidebar).toBeHidden();await expect(page.getByRole('button',{name:'＋ Start a new chat',exact:true})).toBeVisible();
 await page.screenshot({path:out+'/home-before-new-chat.png'});
 await fs.writeFile(out+'/result.json',JSON.stringify({status:'PASS_HOME_BEFORE_NEW_CHAT',actual_installed_browserwindow:true,
  scene_created_or_reused:false,private_sidebar_collapsed_by_visible_button:true,
  css_viewport:await page.evaluate(()=>({width:innerWidth,height:innerHeight,devicePixelRatio})),
  viewport_emulation:false,at:Date.now()},null,2));
 console.log('PASS_HOME_BEFORE_NEW_CHAT');
}finally{await browser.close();}
