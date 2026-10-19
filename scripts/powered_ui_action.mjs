// SPDX-License-Identifier: Apache-2.0
// Each invocation acts only through visible installed Electron controls.
import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
const {chromium}=createRequire(import.meta.url)('../apps/twinpulse-web/node_modules/.pnpm/playwright-core@1.63.0/node_modules/playwright-core');
const [action,arg='']=process.argv.slice(2),out=process.env.TWINPULSE_POWERED_EVIDENCE??'C:/Users/jaewo/Documents/TwinPulse/outputs/robot-powered-ui-20261018-03';
const browser=await chromium.connectOverCDP('http://127.0.0.1:19222',{timeout:5000});
const page=browser.contexts()[0].pages().find(p=>p.url().startsWith('http://127.0.0.1:8765/'));
page.setDefaultTimeout(5000);
const label='Imported existing settings · unverified';
const control=page.getByRole('region',{name:'Control '+label,exact:true});
const began=Date.now();
let result={action,arg,began};
try {
 if(action==='status') result.text=(await page.getByRole('banner').innerText())+'\n'+(await page.locator('main').innerText()).slice(-6000);
 else if(action==='buttons') result.text=(await page.getByRole('button').allTextContents()).join('\n');
 else if(action==='room') await page.getByRole('button',{name:'Open chat_mvcck71j_6d94b13d',exact:true}).click({timeout:45000});
 else if(action==='current-default') await page.getByRole('button',{name:'Open saved chat · default',exact:true}).click();
 else if(action==='runtime') {await page.getByRole('button',{name:/^Isaac connection status:/}).click();result.text=await page.getByRole('dialog').innerText();}
 else if(action==='retry') {await page.getByRole('button',{name:'Retry owned engine',exact:true}).click();}
 else if(action==='view') {
   const reopen=page.getByRole('button',{name:'Reopen saved scene',exact:true});if(await reopen.isVisible())await reopen.click();
   await page.getByRole('button',{name:'Current Twin and SIM controls',exact:true}).click();
   await page.getByRole('button',{name:'View current Twin',exact:true}).click();
 }
 else if(action==='controller') await page.locator('.robot-fleet-row').filter({hasText:label}).click();
 else if(action==='connect') await control.getByRole('button',{name:'Connect',exact:true}).click();
 else if(action==='lidar-on'||action==='lidar-off') await control.getByRole('button',{name:action==='lidar-on'?'Turn LiDAR on':'Turn LiDAR off',exact:true}).click();
 else if(action==='prepare') {
   await control.getByRole('checkbox',{name:'I am present and confirm zero-command controller preparation.',exact:true}).check();
   await control.getByRole('button',{name:'Prepare',exact:true}).click();
 }
 else if(action==='arm') {
   await control.getByRole('checkbox',{name:'I am supervising, charging is unplugged, the space is clear, and I can immediately power off the physical robot.',exact:true}).check();
   await control.getByRole('button',{name:'Arm supervised field session',exact:true}).click();
 }
 else if(action==='trial') {
   if(!['Stationary collection','Bootstrap stop','Forward','Backward','Left turn','Right turn','Full turn','App-input gap','Soak collection'].includes(arg))throw Error('Trial not approved by this runner');
   await control.getByRole('checkbox',{name:'I reviewed the selected trial scope and explicitly confirm one supervised test.',exact:true}).check();
   await control.getByRole('button',{name:'Run '+arg,exact:true}).click();
 }
 else if(action==='stop') await control.getByRole('button',{name:'Stop',exact:true}).click();
 else if(action==='disconnect') await control.getByRole('button',{name:'Disconnect',exact:true}).click();
 else if(action==='pad') {
   if(!['forward','backward','left','right'].includes(arg))throw Error('Unknown direction');
   const button=control.getByRole('button',{name:'Hold '+arg,exact:true});
   await button.scrollIntoViewIfNeeded();if(!await button.isEnabled())throw Error('Drive button disabled');
   const box=await button.boundingBox();if(!box)throw Error('Visible button required');
   await page.mouse.move(box.x+box.width/2,box.y+box.height/2);
   await page.mouse.down();try{await new Promise(r=>setTimeout(r,500));}finally{await page.mouse.up();}
 }
 else if(action==='chat') {
   if(!['왼쪽 90도','오른쪽 90도','한 바퀴 돌아','정지','상태','라이다 켜','라이다 꺼'].includes(arg))throw Error('Unreviewed chat extent');
   await page.getByRole('textbox',{name:'Message TwinPulse',exact:true}).fill(label+' '+arg);
   await page.getByRole('button',{name:'Send',exact:true}).click();
 }
 else if(action==='logs') await control.getByRole('button',{name:'Operation logs',exact:true}).click();
 else if(action==='shot') await page.screenshot({path:out+'/'+arg+'.png',timeout:8000});
 else if(action==='exit') await page.getByRole('button',{name:'Exit TwinPulse',exact:true}).click();
 else throw Error('Unknown visible UI action');
 result.status='REQUESTED';result.elapsed_ms=Date.now()-began;
 if(action!=='exit')result.control_text=await control.innerText({timeout:1000}).catch(()=>null);
} catch(e) {result.status='FAIL';result.error=String(e);process.exitCode=1;}
try{await fs.appendFile(out+'/ui-actions.jsonl',JSON.stringify(result)+'\n');}catch{}
console.log(JSON.stringify({...result,control_text:result.control_text?.slice(0,1800),text:result.text?.slice(-6000)}));
await Promise.race([browser.close(),new Promise(r=>setTimeout(r,1000))]);process.exit(process.exitCode??0);
