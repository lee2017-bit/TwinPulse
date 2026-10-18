// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
export interface ModelComparisonResult {
  revision:string;status:string;evaluated_keyframes:number;scan_height_m_nominal:number;
  outline:{segments:number[][][]};
  best_diagnostic_hypothesis:null|{weighted_capped_mean_error_m:number;supported_frames:number;evaluated_frames:number;frames:{frame:number;supports_same_transform:boolean;capped_mean_outline_error_m:number}[]};
  sensor_sections:{object_id:string;intersects_nominal_scan_plane:boolean;review_priority:string}[];
  overlays:{frame:number;points:number[][];sensor_pose:number[]}[];
  nearest_surface_diagnostics:{object_id:string;nearest_returns:number;beyond_15cm_returns:number}[];
  geometry_changed:false;alignment_verified:false;motion_authorized:false;physical_demo_ready:false;
}

export function ModelComparison({value}:{value:ModelComparisonResult}){
  const points=value.overlays.flatMap(k=>k.points),segments=value.outline.segments;
  const xy=[...points,...segments.flat()],xs=xy.map(p=>p[0]),ys=xy.map(p=>p[1]);
  const x=Math.min(...xs)-.2,y=Math.min(...ys)-.2,w=Math.max(1,Math.max(...xs)-x+.2),h=Math.max(1,Math.max(...ys)-y+.2);
  const best=value.best_diagnostic_hypothesis;
  return <section aria-label="Photo model comparison">
    <h4>Photo 3D vs recorded scans</h4>
    <p role="status">{value.status.replaceAll('_',' ')} · {best?.supported_frames??0}/{value.evaluated_keyframes} frames support the same transform</p>
    <p>This diagnostic transform is not a robot position. The photo room is unchanged; scans, odom and nominal mounting may each contribute to disagreement.</p>
    {best&&<p>Capped mean outline residual: {(best.weighted_capped_mean_error_m*1000).toFixed(0)} mm — not position accuracy.</p>}
    <svg role="img" aria-label="Unchanged photo model outline and multiframe diagnostic scan overlay"
      viewBox={`${x*100} ${-(y+h)*100} ${w*100} ${h*100}`} style={{width:'100%',maxWidth:640,aspectRatio:`${w}/${h}`,background:'#101923'}}>
      {points.map((p,i)=><circle key={i} cx={p[0]*100} cy={-p[1]*100} r="1.4" fill="#dca461" opacity=".55"/>)}
      {segments.map((s,i)=><line key={i} x1={s[0][0]*100} y1={-s[0][1]*100} x2={s[1][0]*100} y2={-s[1][1]*100} stroke="#59ead9" strokeWidth="2"/>)}
    </svg>
    <p>Cyan: authored box cross-section · amber: up to 16 recorded scans under one diagnostic transform. No geometry correction or free-space inference.</p>
    <details><summary>Sensor cross-section and disagreement details</summary>
      <p>Nominal scan height {(value.scan_height_m_nominal*1000).toFixed(0)} mm. Furniture legs, gaps and cloth are not measured by the box model.</p>
      <ul>{value.sensor_sections.map(s=><li key={s.object_id}>{s.object_id}: {s.intersects_nominal_scan_plane?'intersects scan plane':'above/below scan plane'} · {s.review_priority.replaceAll('_',' ')}</li>)}</ul>
      <p>Nearest model surface is not object recognition. Returns more than 15 cm away:</p>
      <ul>{value.nearest_surface_diagnostics.filter(s=>s.nearest_returns>0).map(s=><li key={s.object_id}>{s.object_id}: {s.beyond_15cm_returns}/{s.nearest_returns}</li>)}</ul>
      <p>Bounded seed search; missing returns, exterior observations, timing errors and odom drift are not resolved. No physical mission is unlocked.</p>
    </details>
  </section>;
}
