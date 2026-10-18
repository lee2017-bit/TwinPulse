// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// Real built React, owned loopback App; physical endpoints are intercepted synthetic UI fixtures.
// No SSH, robot process, driver or device is started by this test.
import { chromium, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
const base=process.env.TWINPULSE_REHEARSAL_URL,bootstrap=process.env.TWINPULSE_REHEARSAL_BOOTSTRAP;
const output=process.env.TWINPULSE_REHEARSAL_OUTPUT,chrome=process.env.TWINPULSE_REHEARSAL_CHROME;
if(!base||new URL(base).hostname!=='127.0.0.1'||!bootstrap||!output||!chrome)throw Error('Owned loopback required');
const result={status:'FAIL',data:'SYNTHETIC_UI_ONLY',stages:[],external_requests:0,physical_server_requests:0,page_errors:0};
let browser,page,stage='start',boot,physical={state:'NOT_STARTED',busy:false},runningScan=false;
const actions=[],modes=[];
function preview(){return {schema:'lidar-display-1.0',frame_id:'synthetic_scan',source_stamp_ns:1000000000,
  sample_s:1,receipt_s:1.02,angle_min_rad:0,angle_increment_rad:Math.PI*2/360,range_min_m:.1,range_max_m:8,
  ranges_m:Array.from({length:360},(_,i)=>i%23===0?null:1.5+.6*Math.sin(i*.04)),
  display_only:true,alignment_verified:false,receipt_age_s:.02,source_age_at_emit_s:.03,transport_delay_measured:false};}
function state(){return {...physical,...(runningScan?{scan_preview:preview()}:{})};}
try{
  browser=await chromium.launch({executablePath:chrome,headless:true});
  const context=await browser.newContext({viewport:{width:1440,height:1100}});
  await context.route('**/*',async route=>{
    const url=new URL(route.request().url());
    if(url.origin!==base&&!['blob:','data:'].includes(url.protocol)){result.external_requests++;return route.abort();}
    if(url.pathname==='/v1/product/commands')return route.abort();
    if(url.pathname==='/v1/product/robot/diagnostics'){
      const response=await route.fetch(),data=await response.json();
      data.local_release_id='synthetic-release';if(data.record){data.record.release_id='synthetic-release';boot=data.record.boot_id;}
      return route.fulfill({response,json:data});
    }
    if(url.pathname.startsWith('/v1/product/robot/physical')){
      if(url.pathname.endsWith('/start')){
        const body=route.request().postDataJSON();modes.push(body.mode);
        runningScan=['scan','control_scan'].includes(body.mode);
        physical={...physical,state:'READY',busy:true,owned:true,job_id:body.request_id,mode:body.mode,sequence:0,real_transport:false,motion_lease_policy:'fresh-intent-1.0',
          session_policy:body.mode==='control_scan'?'until-stop-1.0':'bounded-60s-1.0',manual_speed:body.mode==='control_scan'?{linear_m_s:.05,angular_rad_s:.30}:null};
      }else if(url.pathname.endsWith('/input')){
        const body=route.request().postDataJSON();actions.push(body.action);physical.sequence=body.sequence;
        if(body.action==='stop'){
          physical={...physical,state:'RELEASING'};
          setTimeout(()=>{if(physical.busy&&physical.state==='RELEASING')physical={...physical,state:'READY'};},450);
        }
        if(['close','force_stop','finish_stop'].includes(body.action)){
          runningScan=false;physical={...physical,state:'FINISHED',busy:false,cleanup_confirmed:true,sensor_cleanup_confirmed:true,scan_preview:preview()};
        }
      }else if(url.pathname!=='/v1/product/robot/physical'){return route.abort();}
      return route.fulfill({json:state()});
    }
    return route.continue();
  });
  page=await context.newPage();page.on('pageerror',()=>result.page_errors++);
  await page.goto(`${base}/#robot-console=1&bootstrap=${encodeURIComponent(bootstrap)}`);
  const status=page.getByRole('region',{name:'Robot connection status'});
  await expect(status.getByText('Connected — status received')).toBeVisible({timeout:15000});
  const controller=page.getByRole('region',{name:'Physical controller'});
  const joystick=controller.getByRole('button',{name:'Drive joystick'});
  stage='scan_only';
  await expect(joystick).toBeDisabled();await expect(controller.getByRole('checkbox')).toHaveCount(0);
  await controller.getByRole('button',{name:'Start LiDAR scan'}).click();
  await expect(page.getByText('Receiving /scan',{exact:true})).toBeVisible();
  await expect(joystick).toBeDisabled();expect(modes).toEqual(['scan']);
  expect(await page.locator('.scan-points circle').count()).toBeGreaterThan(300);
  await controller.getByRole('button',{name:'Stop LiDAR scan',exact:true}).click();
  await expect(page.getByText(/Sensor STOP write, data quiet/)).toBeVisible();
  expect(actions.some(a=>['forward','backward','left','right'].includes(a))).toBe(false);
  result.stages.push('scan_only_display_without_motion_receipt_and_cleanup');
  stage='combined_joystick';
  physical={state:'FINISHED',busy:false,last_trial:{historical:true,job_id:'synthetic-trial',boot_id:boot,
    release_id:'synthetic-release',status:'QUALIFIED',cleanup_confirmed:true,stop_assessment:{
      policy_id:'supervised-stop-2.0',status:'PASS',checks:{},metrics:{},limits:{deceleration_budget_s:.5,verification_s:.3,wheel_travel_limit_mm:10,residual_rate_limit_mm_s:1}}}};
  await controller.getByRole('button',{name:'Refresh results · read-only'}).click();
  await controller.getByRole('button',{name:'Connect drive + LiDAR'}).click();
  await expect(joystick).toBeEnabled();await expect(page.getByText('Receiving /scan',{exact:true})).toBeVisible();
  const setup=controller.getByRole('region',{name:'Connection steps'}),scan=controller.getByRole('region',{name:'Live LiDAR scan'});
  expect((await setup.boundingBox()).y).toBeLessThan((await scan.boundingBox()).y);
  await joystick.scrollIntoViewIfNeeded();let box=await joystick.boundingBox();
  await joystick.focus();
  result.joystick_box=box;
  result.joystick_hit=await page.evaluate(b=>document.elementFromPoint(b.x+b.width/2,b.y+b.height/2)?.outerHTML.slice(0,220),box);
  stage='joystick_forward';await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();
  await page.mouse.move(box.x+box.width/2,box.y+25);await expect.poll(()=>actions.includes('forward')).toBe(true);
  const stoppedBefore=actions.filter(a=>a==='stop').length;
  await page.waitForTimeout(3100);
  expect(actions.filter(a=>a==='stop').length).toBe(stoppedBefore);
  await expect(joystick).toBeEnabled();
  stage='joystick_right';await page.mouse.move(box.x+box.width-25,box.y+box.height/2);await expect.poll(()=>actions.includes('right')).toBe(true);
  stage='joystick_release';await page.mouse.up();await expect.poll(()=>actions.includes('stop')).toBe(true);
  await expect(joystick).toBeEnabled();expect(modes).toEqual(['scan','control_scan']);
  const closes=actions.filter(a=>a==='close').length;
  stage='joystick_second_gesture';
  await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();
  await page.mouse.move(box.x+box.width/2,box.y+box.height-25);
  await expect.poll(()=>actions.includes('backward')).toBe(true);await page.mouse.up();
  await expect(joystick).toBeEnabled();expect(actions.filter(a=>a==='close').length).toBe(closes);
  await page.screenshot({path:path.join(output,'joystick-scan-desktop.png'),fullPage:true});
  await controller.locator('.console-grid').screenshot({path:path.join(output,'joystick-scan-controls.png')});
  result.stages.push('joystick_over_three_seconds_delayed_idle_readback_second_gesture_keeps_same_session_and_scan');
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:path.join(output,'joystick-scan-mobile.png'),fullPage:true});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  await controller.getByRole('button',{name:'Stop LiDAR scan + driving'}).click();
  await expect(joystick).toBeDisabled();
  result.stages.push('mobile_no_overflow_combined_stop_locks_drive');
  stage='existing_attention_failure';
  await status.getByRole('button',{name:'Check again'}).click();
  await expect(status.getByText('Connected — review robot status')).toBeVisible({timeout:15000});
  await status.getByRole('button',{name:'Check again'}).click();
  await expect(status.getByText(/Connection or remote check failed/)).toBeVisible({timeout:15000});
  await expect(controller).toHaveCount(0);
  result.stages.push('failed_connection_hides_controls');
  expect(result.external_requests).toBe(0);expect(result.page_errors).toBe(0);
  result.synthetic_modes=modes;result.synthetic_actions=[...new Set(actions)];result.status='PASS';
}catch(error){result.synthetic_modes=modes;result.synthetic_actions=actions;result.failed_stage=stage;result.error_type=error.constructor?.name;
  if(page)await page.screenshot({path:path.join(output,'failed.png'),fullPage:true});
  result.error_summary=String(error.message).split(bootstrap).join('[redacted]').split(base).join('[local]').split('\n').slice(0,5).join('\n');}
finally{if(browser)await browser.close();fs.writeFileSync(path.join(output,'browser-result.json'),JSON.stringify(result,null,2));}
process.exitCode=result.status==='PASS'?0:1;
