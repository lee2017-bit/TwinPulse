// SPDX-License-Identifier: Apache-2.0
// Independent public UI preparation after a preserved partial fresh failure.
import {chromium,expect} from '../apps/twinpulse-web/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs/promises';
const output=process.argv[2],label='Imported existing settings · unverified';
if(!output)throw Error('New output directory required');await fs.mkdir(output,{recursive:false});
const browser=await chromium.connectOverCDP('http://127.0.0.1:19222');
try{
 const pages=browser.contexts().flatMap(c=>c.pages()).filter(p=>p.url().startsWith('http://127.0.0.1:8765/'));
 if(pages.length!==1)throw Error('One installed renderer required');const page=pages[0],mutations=[];
 const identity=await page.evaluate(()=>window.twinpulseDesktop?.versions());
 page.on('request',r=>{if(r.method()==='POST'){let b;try{b=r.postDataJSON();}catch{}mutations.push({path:new URL(r.url()).pathname,action:b?.action,request_id:b?.request_id});}});
 const drawer=page.getByRole('region',{name:'Control '+label,exact:true});
 if(!await drawer.isVisible())await page.locator('.robot-fleet-row').filter({hasText:label}).click();
 await expect(drawer).toBeVisible();
 const marker=drawer.getByText('Estimated Twin marker',{exact:true});if(await marker.locator('..').getAttribute('open')===null)await marker.click();
 for(const [name,value] of [['Marker X (m)','3.5'],['Marker Y (m)','2'],['Marker yaw (rad)','0']])await drawer.getByRole('spinbutton',{name,exact:true}).fill(value);
 await drawer.getByRole('button',{name:'Place estimated robot marker',exact:true}).click();
 await expect(drawer.getByText('Static visualization estimate',{exact:false})).toBeVisible({timeout:20000});
 await drawer.getByRole('button',{name:'Close robot controls',exact:true}).click();
 await expect(page.getByRole('button',{name:'Select '+label+' in Twin',exact:true})).toBeVisible({timeout:20000});
 await page.screenshot({path:output+'/marker-prepared.png'});
 if(mutations.some(m=>m.path==='/v1/product/robot-fleet'&&!['set_twin_pose','focus'].includes(m.action)))throw Error('Unexpected robot action in visualization-only setup');
 const closing=page.waitForEvent('close',{timeout:60000});await page.getByRole('button',{name:'Exit TwinPulse',exact:true}).click();await closing;
 await fs.writeFile(output+'/result.json',JSON.stringify({status:'PASS_SCOPED_MARKER_SETUP_NOT_FRESH_ACCEPTANCE',identity,mutations,
  classification:'Explicit marker prerequisite was never created in failed fresh08. Current UI placement only; original cold08 FAIL preserved. No physical activation or authority.'},null,2),{flag:'wx'});
}finally{await browser.close();}
