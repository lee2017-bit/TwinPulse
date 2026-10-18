// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// Existing local API and built chat. Reactive fixture transport, never SSH.
import {chromium,expect} from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
const output=process.env.TWINPULSE_CHAT_OUTPUT;
const scenario=process.env.TWINPULSE_CHAT_CASE;
if(!output||!scenario.startsWith('robot-'))throw new Error('Explicit isolated robot fixture required');
const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
try {
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.goto(`${process.env.TWINPULSE_CHAT_URL}/#bootstrap=${encodeURIComponent(process.env.TWINPULSE_CHAT_BOOTSTRAP)}`);
  // The first authenticated observation restores a local draft. Wait for that
  // actual receipt before typing; do not race its intentional restoration.
  await expect(page.getByRole('banner')).toContainText('default · Choose a mode');
  await page.getByRole('textbox',{name:'Message TwinPulse'}).fill('Build a bedroom for my Burger');
  await page.getByRole('button',{name:'Send',exact:true}).click();
  await page.getByRole('button',{name:'Use my robot',exact:true}).click();
  await page.getByRole('button',{name:'TurtleBot3 Burger',exact:true}).click();
  const panel=page.getByRole('region',{name:'Robot preparation'});
  if(['robot-ssh','robot-release'].includes(scenario)){
    const reason=scenario==='robot-ssh'?'SSH_CONNECTION_REFUSED':'REVIEWED_RELEASE_MISMATCH';
    await expect(panel).toContainText(reason);
    await expect(page.getByRole('button',{name:'Check connection again',exact:true})).toBeEnabled();
    await expect(page.getByRole('button',{name:/Run once/})).toHaveCount(0);
  }else{
    await expect(page.getByRole('button',{name:'Run once · 0.03 m/s for 0.6 s',exact:true})).toBeEnabled();
    await page.screenshot({path:path.join(output,'qualification-choice.png')});
    await page.getByRole('button',{name:/Run once ·/}).click();
    if(scenario==='robot-stop'){
      await expect(panel).toContainText('QUALIFYING');
      await panel.getByRole('button',{name:'Force STOP',exact:true}).click();
      await expect(panel).toContainText('STOPPED');
    }else if(scenario==='robot-stop-failure'){
      await expect(panel).toContainText('STOP_FAILED');
      await panel.getByText('Evidence and blockers',{exact:true}).click();
      await expect(panel.getByRole('alert')).toContainText('MOTOR_OFF_READ_FAILED');
      await expect(page.getByRole('button',{name:'Movement and stop were normal',exact:true})).toHaveCount(0);
    }else{
      await expect(page.getByRole('button',{name:'Movement and stop were normal',exact:true})).toBeEnabled();
      await page.getByRole('button',{name:scenario==='robot-problem'?'Report a problem':'Movement and stop were normal',exact:true}).click();
      await expect(panel).toContainText(scenario==='robot-problem'?'OPERATOR_REPORTED_PROBLEM':'LINKED');
    }
  }
  if(['robot-collect','robot-transfer-failure','robot-local-failure'].includes(scenario)){
    const collection=page.getByRole('region',{name:'Stationary evidence collection'});
    await collection.getByRole('button',{name:'Approve source transfer and collect once',exact:true}).click();
    await expect(panel).toContainText('COLLECTION RESULT');
    if(scenario==='robot-local-failure'){
      await expect(collection).toContainText('BLOCKED LOCAL');
      await expect(collection).toContainText('LOCAL_CONTRACT_FAILED');
      await expect(collection.getByRole('button',{name:'Resume saved raw transfer only',exact:true})).toHaveCount(0);
    }else{
      await expect(collection).toContainText('odom: REJECTED');
      await expect(collection).toContainText('scan: NOT_RECEIVED');
      await collection.getByRole('button',{name:'Resume saved raw transfer only',exact:true}).click();
      await expect(collection).toContainText(scenario==='robot-transfer-failure'?'Recovery: INCOMPLETE':'Recovery: COMPLETE');
      await expect(collection).toContainText('Initial raw export: INCOMPLETE');
      if(scenario==='robot-collect')await expect(collection.getByRole('button',{name:'Resume saved raw transfer only',exact:true})).toHaveCount(0);
      if(scenario==='robot-transfer-failure')await expect(collection.getByRole('alert')).toContainText('TimeoutError');
    }
    await expect(page.getByRole('button',{name:/Run once ·/})).toBeDisabled();
  }
  if(scenario==='robot-inspection'){
    await expect(page.getByRole('button',{name:'Start inspection · bounded movement and LiDAR',exact:true})).toBeEnabled();
    await page.screenshot({path:path.join(output,'inspection-confirm.png')});
    await page.getByRole('button',{name:'Start inspection · bounded movement and LiDAR',exact:true}).click();
    const survey=page.getByRole('region',{name:'Twin inspection status'});
    await expect(survey).toContainText('FIXTURE_ADMISSION_FAILURE');
    await expect(page.getByRole('alert').filter({has:page.getByRole('button',{name:'Dismiss',exact:true})})).toContainText('FIXTURE_ADMISSION_FAILURE');
    await page.getByRole('button',{name:'Dismiss',exact:true}).click();
    await survey.getByRole('button',{name:'Refresh inspection readiness · no robot command',exact:true}).click();
    await expect(page.getByRole('button',{name:'Start inspection · bounded movement and LiDAR',exact:true}).last()).toBeEnabled();
  }
  const before=await page.evaluate(async()=>await(await fetch('/v1/product/conversation')).json());
  if(before.physical_authority!==false||before.robot_preparation.demo_ready!==false)throw new Error('Preparation promoted to mission authority');
  if(before.robot_preparation.transport!=='OFFLINE_TEST_TRANSPORT')throw new Error('Fixture mislabelled as physical');
  await page.screenshot({path:path.join(output,'desktop-result.png')});
  await page.setViewportSize({width:390,height:844});
  await expect(page.getByRole('banner').getByRole('button',{name:'Force STOP',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Hide Twin',exact:true}).click();
  await expect(panel).toBeVisible();
  await panel.scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(output,'mobile-result.png')});
  if(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth+2))throw new Error('Mobile overflow');
  await page.reload();
  await expect(panel).toContainText(before.robot_preparation.state.replaceAll('_',' '));
  if(errors.length)throw new Error(errors.join('\n'));
  fs.writeFileSync(path.join(output,'browser-result.json'),JSON.stringify({status:'PASS',scenario,
    runtime:'BUILT_WEB_AND_LOCAL_API',robot_transport:'REACTIVE_OFFLINE_CONTROLLER',physical_tests:0,
    state:before.robot_preparation.state,checks:['inline Q1/Q2/Q3/Q4','parallel generation/check',
      'failure cause and next question','single trial/no preview motion','Stop independent','mobile/reload/no new operation']},null,2));
}finally{await browser.close();}
