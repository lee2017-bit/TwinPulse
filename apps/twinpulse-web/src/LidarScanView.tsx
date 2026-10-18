// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { useEffect, useState } from 'react';

export interface ScanPreview {
  schema:'lidar-display-1.0';frame_id:string;source_stamp_ns:number;sample_s:number;receipt_s:number;
  angle_min_rad:number;angle_increment_rad:number;range_min_m:number;range_max_m:number;
  ranges_m:(number|null)[];display_only:true;alignment_verified:false;
  receipt_age_s:number;source_age_at_emit_s:number;transport_delay_measured:false;
}
export function scanPoints(scan:ScanPreview|null,radius:number):{x:number;y:number}[]{
  if(!scan||scan.schema!=='lidar-display-1.0'||scan.display_only!==true||scan.alignment_verified!==false||
    !Array.isArray(scan.ranges_m)||scan.ranges_m.length>720||
    ![scan.angle_min_rad,scan.angle_increment_rad,scan.range_min_m,scan.range_max_m,radius].every(Number.isFinite)||radius<=0)return [];
  return scan.ranges_m.flatMap((r,i)=>{
    if(r===null||!Number.isFinite(r)||r<scan.range_min_m||r>scan.range_max_m||r>radius)return [];
    const angle=scan.angle_min_rad+i*scan.angle_increment_rad;
    // Sensor +X upwards, +Y leftwards. No unverified robot/room TF applied.
    return [{x:250-Math.sin(angle)*r/radius*215,y:250-Math.cos(angle)*r/radius*215}];
  });
}
export function LidarScanView({scan,active,pending}:{scan:ScanPreview|null;active:boolean;pending:boolean}){
  const [radius,setRadius]=useState(4),[elapsed,setElapsed]=useState(0);
  useEffect(()=>{setElapsed(0);const start=performance.now();
    const timer=window.setInterval(()=>setElapsed((performance.now()-start)/1000),250);
    return()=>window.clearInterval(timer);
  },[scan]);
  const stale=!scan||!Number.isFinite(scan.receipt_age_s)||!Number.isFinite(scan.source_age_at_emit_s)||
    scan.receipt_age_s+elapsed>=1.5||scan.source_age_at_emit_s>=1.5;
  const points=scanPoints(scan,radius);
  const status=pending?'Preparing scan…':!active?scan?'Stopped · last scan':'No scan yet':stale?
    scan?'Stale scan · reception interrupted':'Waiting for /scan…':'Receiving /scan';
  return <div className={`lidar-scan-view${stale||!active?' scan-is-stale':''}`}>
    <div className="scan-view-toolbar"><span role="status">{status}</span>
      <label>View radius <select value={radius} onChange={e=>setRadius(Number(e.target.value))}>
        {[2,4,8].map(v=><option key={v} value={v}>{v} m</option>)}</select></label></div>
    <svg viewBox="0 0 500 500" role="img" aria-label="LiDAR scan in sensor coordinates">
      {[1,2,3,4].map(i=><g key={i}><circle cx="250" cy="250" r={215*i/4} className="scan-ring"/>
        <text x="257" y={250-215*i/4+15}>{radius*i/4} m</text></g>)}
      <path d="M250 25V475 M25 250H475" className="scan-axis"/>
      <text x="265" y="30">Sensor +X</text><text x="25" y="242">+Y</text>
      <g className="scan-points">{points.map((p,i)=><circle key={i} cx={p.x} cy={p.y} r="2.2"/>)}</g>
      <circle cx="250" cy="250" r="9" className="scan-origin"/><path d="M250 230l-5 9h10Z" className="scan-origin"/>
      {!scan&&<text className="scan-empty" x="250" y="315" textAnchor="middle">Start LiDAR to see measured distance points</text>}
    </svg>
    <p className="scan-caption">{scan?`${points.length} visible returns · ${scan.frame_id}`:'No sensor data'} · sensor-local view, not a mapped room.
      Missing returns are unknown, not clear space. Transport delay is unmeasured.</p>
  </div>;
}
