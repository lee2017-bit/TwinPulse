// SPDX-License-Identifier: Apache-2.0
// Explicit recovery UI only; does not change any failed journey's verdict.
import {chromium,expect} from '../apps/twinpulse-web/node_modules/@playwright/test/index.mjs';
import fs from 'node:fs/promises';
const [output,label='Aligned SIM 06']=process.argv.slice(2);if(!output)throw Error('new output required');
const b=await chromium.connectOverCDP('http://127.0.0.1:19222');const p=b.contexts().flatMap(c=>c.pages()).find(p=>p.url().startsWith('http://127.0.0.1:8765/'));
const result={scope:'RECOVERY_ONLY_ORIGINAL_FAILURE_UNCHANGED',steps:[]};
try{
 const cancel=p.getByRole('radio',{name:'Cancel',exact:true});if(await cancel.count()===1){await cancel.check();await p.getByRole('button',{name:'Continue',exact:true}).click();result.steps.push('cancel pending review without inference');}
 const c=p.getByRole('region',{name:'Control '+label,exact:true});
 if(await c.isVisible()){
  await c.getByRole('button',{name:'Stop',exact:true}).click();result.steps.push('explicit Stop requested');await p.waitForTimeout(1000);
  const off=c.getByRole('button',{name:'Turn LiDAR off',exact:true});if(await off.isVisible())await off.click();
  const disconnect=c.getByRole('button',{name:'Disconnect',exact:true});if(await disconnect.isEnabled())await disconnect.click();result.steps.push('OFF/Disconnect requested');
 }
 await fs.writeFile(output,JSON.stringify(result,null,2),{flag:'wx'});
}finally{await b.close();}
