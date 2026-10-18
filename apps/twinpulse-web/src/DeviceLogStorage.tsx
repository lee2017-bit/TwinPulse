// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {useState} from 'react';
import type {TwinPulseApi} from './api';

export function DeviceLogStorage({api}:{api:TwinPulseApi}) {
  const [days,setDays]=useState(30);
  const [busy,setBusy]=useState(false);
  const [notice,setNotice]=useState<string|null>(null);
  if(typeof api.deviceDiagnosticRetention!=='function')return null;
  return <details className="device-log-storage"><summary>Connection log storage</summary>
    <p>Archive finished connection logs older than the selected period, or above 512 MiB. Files remain in local retired-diagnostics for recovery. Projects, photos, sensor records and current device state are kept.</p>
    <label>Keep connection logs for days <input aria-label="Connection log retention days" type="number" min={1} max={365} value={days} onChange={event=>setDays(Number(event.target.value))}/></label>
    <button disabled={busy||!Number.isInteger(days)||days<1||days>365} onClick={()=>{
      setBusy(true);void api.deviceDiagnosticRetention(days)
        .then(value=>setNotice(`Archived ${value.archived_count} finished logs. Current device state is unchanged.`))
        .catch(()=>setNotice('Connection log archive is unavailable while an operation is active or storage cannot be accessed.'))
        .finally(()=>setBusy(false));
    }}>Archive older connection logs</button>
    {notice&&<p role="status">{notice}</p>}
  </details>;
}
