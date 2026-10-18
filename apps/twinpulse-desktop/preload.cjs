// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
const {contextBridge, ipcRenderer} = require('electron');
contextBridge.exposeInMainWorld('twinpulseDesktop', Object.freeze({
  versions: () => ipcRenderer.invoke('twinpulse:versions'),
  automationStatus: () => ipcRenderer.invoke('twinpulse:automation-status'),
  runBasicChecks: () => ipcRenderer.invoke('twinpulse:automation-run'),
  openCheckReport: () => ipcRenderer.invoke('twinpulse:automation-open'),
  onExitRequested: callback => {
    if (typeof callback !== 'function') throw new TypeError('callback required');
    const handler = () => callback();
    ipcRenderer.on('twinpulse:exit-requested', handler);
    ipcRenderer.send('twinpulse:listener-ready');
    return () => ipcRenderer.removeListener('twinpulse:exit-requested', handler);
  },
  reportExitResult: result => ipcRenderer.send('twinpulse:exit-result', {
    requested: result?.requested === true,
    ...(typeof result?.code === 'string' && /^[a-z0-9_]{1,80}$/.test(result.code) ? {code: result.code} : {}),
  }),
}));
