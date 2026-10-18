// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// A read-only resource observer must not retain every network response body.
// Use an isolated owned Chrome and only the registered CDP observation/input
// domains. No Network.enable, cache clearing, forced GC or user-profile edits.
import {spawn} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';

export function isOwnedTemporaryProfile(profile,root) {
  return path.isAbsolute(profile)&&path.dirname(profile)===path.resolve(root)&&
    /^twinpulse-owned-observer-[a-zA-Z0-9]{6}$/.test(path.basename(profile));
}

export async function openOwnedChrome(output) {
  const temporaryRoot=path.resolve(os.tmpdir());
  const profile=fs.mkdtempSync(path.join(temporaryRoot,'twinpulse-owned-observer-'));
  const log=fs.openSync(path.join(output,'observer-chrome.log'),'wx');
  const child=spawn('C:/Program Files/Google/Chrome/Application/chrome.exe',[
    '--headless=new','--no-first-run','--no-default-browser-check',
    // These process-local isolation flags are already used by the installed
    // Playwright runtime. Do not start Chrome's unrelated model/component
    // downloads while measuring a local offline product.
    '--disable-background-networking','--disable-component-update',
    '--disable-component-extensions-with-background-pages','--disable-default-apps',
    '--disable-client-side-phishing-detection','--disable-extensions','--disable-sync',
    '--disable-features=OptimizationHints,MediaRouter,LensOverlay',
    '--metrics-recording-only','--no-service-autorun',
    '--remote-debugging-port=0','--remote-debugging-address=127.0.0.1',
    `--user-data-dir=${profile}`,'--window-size=1440,1000','about:blank',
  ],{windowsHide:true,stdio:['ignore','ignore',log]});
  fs.closeSync(log);
  const ended=new Promise(resolve=>{child.once('exit',code=>resolve(code));child.once('error',()=>resolve(-1));});
  let ws;let sequence=0;const pending=new Map();const pageErrors=[];
  const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const send=(method,params={},sessionId)=>new Promise((resolve,reject)=>{
    const id=++sequence;
    const timer=setTimeout(()=>{pending.delete(id);reject(new Error(`CDP_TIMEOUT:${method}`));},10000);
    pending.set(id,{resolve,reject,timer});
    try{ws.send(JSON.stringify({id,method,params,...(sessionId?{sessionId}:{})}));}
    catch{clearTimeout(timer);pending.delete(id);reject(new Error(`CDP_SEND_FAILED:${method}`));}
  });
  const close=async()=>{
    if(ws?.readyState===WebSocket.OPEN)await send('Browser.close').catch(()=>{});
    const code=await new Promise(resolve=>{
      const timer=setTimeout(()=>resolve('OWNED_CHROME_EXIT_TIMEOUT'),15000);
      ended.then(value=>{clearTimeout(timer);resolve(value);});
    });
    ws?.close();
    for(const row of pending.values()){clearTimeout(row.timer);row.reject(new Error('OWNED_CHROME_CLOSED'));}
    pending.clear();
    if(code!==0)throw new Error(`OWNED_CHROME_EXIT:${code}`);
    // Only the freshly created, identity-checked temporary leaf is removed,
    // after normal Chrome exit. Never retain session cookies/bootstrap data in
    // repository artifacts or touch a user browser profile.
    if(!isOwnedTemporaryProfile(profile,temporaryRoot)||fs.lstatSync(profile).isSymbolicLink())
      throw new Error('OWNED_TEMPORARY_PROFILE_IDENTITY_CHANGED');
    fs.rmSync(profile,{recursive:true,force:false});
    fs.writeFileSync(path.join(output,'observer-profile-cleanup.json'),JSON.stringify({
      status:'PASS',profile_removed:true,owned_normal_exit:true,
      background_updates_suppressed:true,user_profile_touched:false,
    }),{flag:'wx'});
    return code;
  };
  try{
    const endpointFile=path.join(profile,'DevToolsActivePort');
    const deadline=performance.now()+20000;let endpoint;
    while(performance.now()<deadline){
      if(fs.existsSync(endpointFile)){
        const [port,route]=fs.readFileSync(endpointFile,'utf8').trim().split(/\r?\n/);
        if(/^\d+$/.test(port)&&route?.startsWith('/devtools/browser/')){
          endpoint=`ws://127.0.0.1:${port}${route}`;break;
        }
      }
      if(child.exitCode!==null)throw new Error('OWNED_CHROME_START_FAILED');
      await wait(100);
    }
    if(!endpoint)throw new Error('OWNED_CHROME_ENDPOINT_TIMEOUT');
    ws=new WebSocket(endpoint);
    await new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>reject(new Error('OWNED_CHROME_SOCKET_TIMEOUT')),10000);
      ws.addEventListener('open',()=>{clearTimeout(timer);resolve();},{once:true});
      ws.addEventListener('error',()=>{clearTimeout(timer);reject(new Error('OWNED_CHROME_SOCKET_FAILED'));},{once:true});
    });
    ws.addEventListener('message',event=>{
      const message=JSON.parse(event.data);
      if(message.id){const row=pending.get(message.id);if(!row)return;
        clearTimeout(row.timer);pending.delete(message.id);
        if(message.error)row.reject(new Error(`CDP_REJECTED:${message.error.code}`));else row.resolve(message.result);
      }else if(message.method==='Runtime.exceptionThrown'){
        if(pageErrors.length<100)pageErrors.push(message.params.exceptionDetails.text);
      }
    });
    const version=await send('Browser.getVersion');
    const {targetId}=await send('Target.createTarget',{url:'about:blank'});
    const {sessionId}=await send('Target.attachToTarget',{targetId,flatten:true});
    const pageSend=(method,params={})=>send(method,params,sessionId);
    await pageSend('Page.enable');await pageSend('Runtime.enable');await pageSend('Performance.enable');
    await pageSend('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
    const evaluate=async expression=>{
      const result=await pageSend('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});
      if(result.exceptionDetails)throw new Error('OWNED_PAGE_EVALUATION_FAILED');
      return result.result.value;
    };
    const screenshot=async name=>{
      if(!/^[a-z0-9-]+\.png$/.test(name))throw new Error('ISOLATED_SCREENSHOT_NAME_REQUIRED');
      const {data}=await pageSend('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
      fs.writeFileSync(path.join(output,name),Buffer.from(data,'base64'),{flag:'wx'});
    };
    const click=async label=>{
      const point=await evaluate(`(()=>{const b=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===${JSON.stringify(label)}&&!b.disabled&&b.getClientRects().length);if(!b)return null;b.scrollIntoView({block:'center'});const r=b.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()`);
      if(!point)throw new Error(`UI_BUTTON_NOT_READY:${label}`);
      await pageSend('Input.dispatchMouseEvent',{type:'mouseMoved',...point});
      await pageSend('Input.dispatchMouseEvent',{type:'mousePressed',...point,button:'left',clickCount:1});
      await pageSend('Input.dispatchMouseEvent',{type:'mouseReleased',...point,button:'left',clickCount:1});
    };
    const chooseRadio=async label=>{
      const point=await evaluate(`(()=>{const l=[...document.querySelectorAll('.chat-question label')].find(l=>l.textContent.trim()===${JSON.stringify(label)}&&l.querySelector('input[type="radio"]:not(:disabled)')&&l.getClientRects().length);if(!l)return null;l.scrollIntoView({block:'center'});const r=l.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()`);
      if(!point)throw new Error(`UI_CHOICE_NOT_READY:${label}`);
      await pageSend('Input.dispatchMouseEvent',{type:'mouseMoved',...point});
      await pageSend('Input.dispatchMouseEvent',{type:'mousePressed',...point,button:'left',clickCount:1});
      await pageSend('Input.dispatchMouseEvent',{type:'mouseReleased',...point,button:'left',clickCount:1});
    };
    const message=async text=>{
      if(typeof text!=='string'||text.length>128)throw new Error('FIXED_TEST_MESSAGE_REQUIRED');
      const focused=await evaluate(`(()=>{const t=document.querySelector('textarea[aria-label="Message TwinPulse"]');if(!t||t.disabled)return false;t.focus();return true;})()`);
      if(!focused)throw new Error('UI_COMPOSER_NOT_READY');
      await pageSend('Input.insertText',{text});
      await pageSend('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
      await pageSend('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
    };
    return {send:pageSend,evaluate,click,chooseRadio,message,screenshot,close,pageErrors,version,
      navigate:url=>pageSend('Page.navigate',{url}),reload:()=>pageSend('Page.reload'),
      processInfo:()=>send('SystemInfo.getProcessInfo')};
  }catch(error){await close().catch(()=>{});throw error;}
}
