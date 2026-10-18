// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { useEffect, useState } from 'react';
import type { SupervisorState } from './types';

export function IsaacConnectionStatus({runtime, connected, apiConnected, inspect}: {
  runtime:SupervisorState|null; connected:boolean; apiConnected:boolean; inspect:()=>void;
}) {
  const [now,setNow]=useState(Date.now());
  useEffect(()=>{const timer=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(timer);},[]);
  const failed=runtime?.status==='error';
  const starting=runtime?.status==='starting';
  const stopped=['stopped','cancelled','canceled'].includes(runtime?.status??'');
  const state=failed?'error':starting?'starting':stopped?'stopped':apiConnected&&connected?'connected':'waiting';
  const started=Date.parse(runtime?.started_at_utc??'');
  const elapsed=Number.isFinite(started)?Math.max(0,Math.floor((now-started)/1000)):null;
  const duration=elapsed===null?'':` · ${Math.floor(elapsed/60)}:${String(elapsed%60).padStart(2,'0')}`;
  const label=state==='connected'?'Isaac connected':state==='error'?'Isaac startup failed':
    state==='starting'?`Isaac starting${duration}`:state==='stopped'?'Isaac stopped':
    !apiConnected?'Connecting to App':'Connecting to Isaac';
  return <button type="button" className={`isaac-connection-status ${state}`} onClick={inspect}
    aria-label={`Isaac connection status: ${label}`} title={runtime?.message??'Current connection observation. Scene display and motion readiness are checked separately.'}>
    <span className="connection-dot" aria-hidden="true"/><span role="status" aria-live="polite">{label}</span>
  </button>;
}
