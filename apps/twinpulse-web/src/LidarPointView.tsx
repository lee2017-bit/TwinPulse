// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {useState} from 'react';

// Shared actual-return renderer for SIM, native live and saved native scans.
// Coordinates stay sensor-local. This component never invents a world TF.
export function LidarPointView({points,source,historical=false,height}:{points:[number,number][];source:string;historical?:boolean;height?:number}){
 const [rays,setRays]=useState(false);
 const valid=points.slice(0,8192).filter(p=>p.length===2&&p.every(Number.isFinite));
 const radius=Math.max(2,...valid.map(p=>Math.hypot(...p)));
 const sample=Math.max(1,Math.ceil(valid.length/720));const shown=valid.filter((_,i)=>i%sample===0);
 return <div className="lidar-point-view">
  <label><input type="checkbox" checked={rays} onChange={e=>setRays(e.target.checked)}/>Sparse sensor rays</label>
  <svg className="robot-fleet-scan" viewBox={`${-radius} ${-radius} ${radius*2} ${radius*2}`} aria-label={`LiDAR scan · ${source}`} role="img">
   <circle r={radius*.018} fill="currentColor"/>
   {rays&&shown.filter((_,i)=>i%Math.max(1,Math.ceil(shown.length/24))===0).map(([x,y],i)=><line key={`r${i}`} x1="0" y1="0" x2={x} y2={-y} stroke="#07aeb4" strokeWidth={radius*.003} opacity=".2"/>)}
   {shown.map(([x,y],i)=><circle key={i} cx={x} cy={-y} r={radius*.006} fill="#07aeb4"/>)}
  </svg>
  <small>{historical?'Recorded scan · not live':'Sensor-local returns'} · {valid.length} hits · {source}
   {typeof height==='number'&&Number.isFinite(height)?` · mounting height ${(height*100).toFixed(1)} cm (model)`:''} · no world alignment or position correction.
   Missing returns are unknown, not clear space.</small>
 </div>;
}
