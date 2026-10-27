// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {app, BrowserWindow, ipcMain, utilityProcess, shell} from 'electron';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {EventEmitter} from 'node:events';
import {Socket} from 'node:net';
import {mkdirSync,appendFileSync} from 'node:fs';
import {EngineChannel, checkedAppUrl, allowAppNavigation, PROTOCOL_VERSION} from './protocol.mjs';
import {createSelfTestHost} from './automation.cjs';

const directory = path.dirname(fileURLToPath(import.meta.url));
const args = process.argv;
const stateIndex = args.indexOf('--twinpulse-state');
if (stateIndex < 0 || !args[stateIndex + 1] || !path.isAbsolute(args[stateIndex + 1])) {
  app.exit(2);
} else {
  const stateDirectory=path.join(args[stateIndex + 1], 'desktop-window');
  mkdirSync(stateDirectory,{recursive:true});
  globalThis.desktopLog=code=>{
    try {appendFileSync(path.join(stateDirectory,'host.log'),new Date().toISOString()+' '+String(code).replace(/#bootstrap=[A-Za-z0-9_-]+/g,'#bootstrap=[REDACTED]')+'\n');} catch {}
  };
  desktopLog('HOST_START');
  app.setName('TwinPulse');
  app.setPath('userData', stateDirectory);
  if (!app.requestSingleInstanceLock()) app.quit();
  else start().catch(error => {desktopLog('HOST_START_FAILED '+String(error?.stack??error));app.exit(1);});
}

async function start() {
  let window, windowPromise, baseUrl, launchId, stopped = false, disconnected = false,
    closePending = false, rendererReady = false, rendererCrashed = false;
  const port=Number(process.env.TWINPULSE_HOST_PORT), secret=process.env.TWINPULSE_HOST_SECRET;
  delete process.env.TWINPULSE_HOST_PORT; delete process.env.TWINPULSE_HOST_SECRET;
  if(!Number.isInteger(port)||port<1024||port>65535||!secret||!/^[A-Za-z0-9_-]{40,128}$/.test(secret))
    throw Error('DESKTOP_PRIVATE_TRANSPORT_REQUIRED');
  const socket=new Socket();
  const transport = new EventEmitter();
  transport.stdout = socket;
  transport.stdin = socket;
  const channel = new EngineChannel(transport);
  desktopLog('CHANNEL_CREATED');
  const hostVersions = Object.freeze({desktop:'0.1.0',electron:process.versions.electron,
    chromium:process.versions.chrome,node:process.versions.node,protocol:PROTOCOL_VERSION});
  const focus = () => { if (window) {if (window.isMinimized()) window.restore(); window.show(); window.focus();} };
  const trusted = event => window && event.sender === window.webContents && event.senderFrame === window.webContents.mainFrame &&
    baseUrl && allowAppNavigation(event.senderFrame.url, baseUrl);
  const debugPort=app.commandLine.getSwitchValue('remote-debugging-port');
  const automation=createSelfTestHost({utilityProcess,shell,directory,
    stateDirectory:path.join(args[stateIndex+1],'desktop-window'),
    endpoint:app.commandLine.getSwitchValue('remote-debugging-address')==='127.0.0.1'&&/^\d{4,5}$/.test(debugPort)
      ?`http://127.0.0.1:${debugPort}`:'',appUrl:()=>baseUrl,launch:()=>launchId,
    available:()=>rendererReady&&!closePending&&!stopped&&!disconnected&&!rendererCrashed});
  app.on('will-quit',()=>automation.close());
  ipcMain.handle('twinpulse:automation-status',event=>{if(!trusted(event))throw Error('DESKTOP_SENDER_REJECTED');return automation.status();});
  ipcMain.handle('twinpulse:automation-run',event=>{if(!trusted(event))throw Error('DESKTOP_SENDER_REJECTED');return automation.run();});
  ipcMain.handle('twinpulse:automation-open',event=>{if(!trusted(event))throw Error('DESKTOP_SENDER_REJECTED');return automation.open();});
  const waitingUrl = 'data:text/html;charset=utf-8,' + encodeURIComponent('<!doctype html><meta charset="utf-8"><title>TwinPulse</title><style>body{font:18px system-ui;background:#f6f8fb;color:#183142;display:grid;place-content:center;height:90vh}p{color:#536879}</style><h1>TwinPulse</h1><p>앱을 연결하는 중입니다…</p>');
  app.on('second-instance', focus);
  app.on('before-quit', event => {
    if (!stopped && !disconnected && window && !window.isDestroyed()) {event.preventDefault(); window.close();}
  });
  app.on('window-all-closed', () => {if (stopped || disconnected) app.quit();});
  channel.on('focus', () => {
    focus();
    if (rendererCrashed) channel.request('focus', {reload:true}).catch(() => {
      window?.setTitle('TwinPulse · 실행 관리자 재연결 실패');
    });
  });
  // Bootstrap can arrive before app.whenReady. Serialize creation and loads
  // so the connecting placeholder cannot overwrite the authenticated App.
  let opening = Promise.resolve();
  channel.on('ui-ready', value => {
    opening = opening.then(async () => {
      const checked = checkedAppUrl(value.url);
      baseUrl = checked.origin + '/'; launchId = value.launch_id;
      await createWindow();
      rendererReady=false; rendererCrashed=false;
      await window.loadURL(value.url);
      focus();
    }).catch(() => { window?.setTitle('TwinPulse · 앱 연결 실패 · 다시 실행하세요'); rendererCrashed=true; });
  });
  channel.on('stopped', value => {
    if (value.launch_id !== launchId) return;
    stopped = true; app.quit();
  });
  channel.on('diagnostic', value => {if (window) window.setTitle('TwinPulse · ' + String(value.code ?? '연결 상태 확인'));});
  channel.on('disconnected', value => {
    automation.close();
    desktopLog('MANAGER_DISCONNECTED '+value.code);
    disconnected = true;
    if (window) window.setTitle('TwinPulse · 실행 관리자 연결 끊김 · 종료 상태 미확인');
    // Release this UI-only singleton. Otherwise a dead manager's shell can
    // focus forever while rejecting the next legitimate manager's window.
    app.quit();
  });
  ipcMain.handle('twinpulse:versions', async event => {
    if (!trusted(event)) throw new Error('DESKTOP_SENDER_REJECTED');
    return {...hostVersions, engine:await channel.request('versions')};
  });
  ipcMain.on('twinpulse:exit-result', (event, result) => {
    if (!trusted(event) || !result || typeof result.requested !== 'boolean') return;
    if (result.requested) window?.setTitle('TwinPulse · 정상 종료 중…');
    else {closePending = false; window?.setTitle('TwinPulse · 작업 상태를 확인한 뒤 종료하세요');}
  });
  ipcMain.on('twinpulse:listener-ready', event => {if (trusted(event)) rendererReady=true;});
  await new Promise((resolve,reject)=>{
    socket.once('connect',()=>{socket.write(JSON.stringify({version:PROTOCOL_VERSION,auth_nonce:secret})+'\n');resolve();});
    socket.once('error',reject);socket.connect(port,'127.0.0.1');
  });
  await channel.request('initialize', {protocol:PROTOCOL_VERSION, host:hostVersions});
  desktopLog('MANAGER_INITIALIZED');
  await createWindow();
  desktopLog('WINDOW_CREATED');

  async function createWindow() {
    if (windowPromise) return windowPromise;
    windowPromise = makeWindow();
    return windowPromise;
  }
  async function makeWindow() {
    await app.whenReady();
    window = new BrowserWindow({width:1440,height:960,minWidth:800,minHeight:600,title:'TwinPulse',icon:path.join(directory,'icon.ico'),
      backgroundColor:'#f6f8fb',show:false,webPreferences:{preload:path.join(directory,'preload.cjs'),
        contextIsolation:true,nodeIntegration:false,sandbox:true,webSecurity:true,webviewTag:false,
        // Keep observation/session clocks active while occluded. Focus loss
        // still releases held input; this setting grants no motion authority.
        backgroundThrottling:false}});
    window.removeMenu();
    window.webContents.setWindowOpenHandler(() => ({action:'deny'}));
    window.webContents.on('will-navigate', (event, target) => {
      if (!baseUrl || !allowAppNavigation(target, baseUrl)) event.preventDefault();
    });
    window.webContents.session.setPermissionRequestHandler((_contents,_permission,callback) => callback(false));
    window.webContents.session.setPermissionCheckHandler(() => false);
    window.webContents.on('render-process-gone', () => {
      automation.close();
      rendererReady=false; rendererCrashed=true; closePending=false;
      window.setTitle('TwinPulse · 화면 오류 · Start-TwinPulse로 다시 여세요');
    });
    window.on('close', event => {
      if (stopped || disconnected) return;
      event.preventDefault();
      if (closePending) return;
      if (!rendererReady) {window.setTitle('TwinPulse · 화면 연결 후 종료할 수 있습니다 · 연결 오류 시 Start로 다시 여세요'); return;}
      closePending = true;
      window.webContents.send('twinpulse:exit-requested');
    });
    await window.loadURL(waitingUrl);
    window.show();
  }
}
