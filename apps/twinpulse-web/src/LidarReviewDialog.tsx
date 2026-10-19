// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {createPortal} from 'react-dom';
import {useEffect,useRef} from 'react';
import type {TwinPulseApi} from './api';
import type {RobotFleetRobot} from './robot-fleet-types';
import {LidarPointView} from './LidarPointView';
import {NativeScanReview} from './NativeScanReview';

export function LidarReviewDialog({api,robot,onClose,onStopAll}:{api:TwinPulseApi;robot:RobotFleetRobot;onClose:()=>void;onStopAll:()=>void}){
 const panel=useRef<HTMLDivElement>(null);
 useEffect(()=>{const previous=document.activeElement;panel.current?.focus();return()=>{if(previous instanceof HTMLElement&&previous.isConnected)previous.focus();};},[]);
 return createPortal(<div className="key-settings-backdrop"><div ref={panel} tabIndex={-1} className="key-settings-panel lidar-review-panel" role="dialog" aria-modal="true" aria-labelledby="lidar-review-title" onKeyDown={event=>{
  if(event.key==='Escape'){event.preventDefault();event.stopPropagation();onClose();}
  if(event.key==='Tab'){
   const nodes=[...event.currentTarget.querySelectorAll<HTMLElement>('button:not([disabled]),input:not([disabled]),select:not([disabled]),summary')].filter(n=>n.getClientRects().length);
   const first=nodes[0],last=nodes.at(-1);
   if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}
   else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
  }
 }}>
  <header><h2 id="lidar-review-title">LiDAR sensor review</h2><button type="button" className="robot-fleet-stop" onClick={onStopAll}>Stop all</button><button type="button" onClick={onClose}>Close sensor review</button></header>
  <p>Sensor-local inspection, not world localization. Held manual input is released when opening. Close this review to return to Twin controls.</p>
  {robot.scan&&<details><summary>Current sensor returns · {robot.label}</summary>
   <LidarPointView points={robot.scan.points} source={robot.scan.source} height={robot.scan.height_m}/>
   <p>{robot.kind==='physical'?`PC receipt age ${robot.scan_receipt?.age_ms?.toFixed(0)??'unknown'} ms; acquisition timing remains separate. No synchronized world transform is assumed.`:'SIM surface geometry; nominal model mounting, not an optical or calibrated physical sensor.'}</p>
  </details>}
  <NativeScanReview api={api}/>
 </div></div>,document.body);
}
