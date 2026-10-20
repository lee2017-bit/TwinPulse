// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {useEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import './api-key-settings.css';
type Status={enabled:boolean;state:string;run_id:string|null;report_available:boolean;endpoint?:string;scope:string};
export function DesktopTesting(){
  const host=window.twinpulseDesktop;
  const [status,setStatus]=useState<Status|null>(null),[open,setOpen]=useState(false),[error,setError]=useState('');
  const panel=useRef<HTMLDivElement>(null);
  useEffect(()=>{
    if(!host?.automationStatus)return;
    let closed=false,timer:ReturnType<typeof setTimeout>;
    const poll=async()=>{try{const next=await host.automationStatus!();if(!closed)setStatus(next);}catch{if(!closed)setError('Test status unavailable. No test was started.');}
      if(!closed)timer=setTimeout(()=>void poll(),1000);};
    void poll();return()=>{closed=true;clearTimeout(timer);};
  },[host]);
  useEffect(()=>{if(open)panel.current?.focus();},[open]);
  if(!host?.automationStatus)return null;
  return <span className="desktop-tests"><button type="button" onClick={()=>setOpen(true)}>Tests</button>
    {status?.enabled&&<span role="status" className="desktop-test-badge" title="Local automation is enabled for this launch. Open Tests for scope and details.">TEST MODE · {status.state}</span>}
    {open&&createPortal(<div className="key-settings-backdrop"><div ref={panel} tabIndex={-1} className="key-settings-panel" role="dialog" aria-modal="true" aria-label="Automation tests"
      onKeyDown={event=>{if(event.key==='Escape')setOpen(false);}}>
      <header><h2>Automation tests</h2><button onClick={()=>setOpen(false)}>Close tests</button></header>
      <p>{status?.enabled?'Local Playwright control is enabled for this launch only. Other programs on this PC may control this app while the debugging port is open.':'Normal mode: no automation port is opened by this launch.'}</p>
      {!status?.enabled&&<p>Exit TwinPulse normally, then run <strong>Start-TwinPulse-Test.cmd</strong> beside the installed Start entry. Test and normal mode cannot replace a running session. Exit test mode before returning to normal startup.</p>}
      <p>Basic checks click Robots, type into Library search and open the Twin pane. No paid generation, discovery, SSH or robot movement. Keep the app idle and do not use its controls during the check.</p>
      <p>Results and screenshots stay on this PC. Screenshots can include your conversation and local device details. Review them before sharing; nothing is uploaded automatically.</p>
      <p>Check status: {status?.state??'loading'}{status?.run_id?` · ${status.run_id}`:''}</p>
      {error&&<p role="alert">{error}</p>}
      <button disabled={!status?.enabled||['starting','running'].includes(status.state)} onClick={()=>{setError('');setStatus(previous=>previous?{...previous,state:'starting',run_id:null,report_available:false}:previous);setOpen(false);void host.runBasicChecks?.().then(()=>host.automationStatus!()).then(next=>setStatus(next)).catch(()=>{setError('Basic checks could not start. Review the current app and test mode.');setStatus(previous=>previous?{...previous,state:'failed'}:previous);setOpen(true);});}}>Run basic checks</button>
      <button disabled={!status?.report_available} onClick={()=>void host.openCheckReport?.().catch(()=>setError('The local report could not be opened.'))}>Open check report</button>
      <p>Full SIM generation/edit/Undo/save, OS clipboard/dialogs and physical robot qualification are separate tests. A basic PASS does not certify these.</p>
    </div></div>,document.body)}
  </span>;
}
