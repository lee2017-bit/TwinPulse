// SPDX-License-Identifier: Apache-2.0
import {useRef, useState} from 'react';
import type {FloorMapState} from './robot-fleet-types';

/** Click to place (X, Y); drag from the click point to set the heading. Display scale only: the
 * result is an operator estimate, never a measured or localized pose. */
export function FloorMap({floor,value,onChange,height=220,picks=[],onPick}:{floor:FloorMapState|null;value?:[number,number,number];
  onChange?:(x:number,y:number,yaw:number)=>void;height?:number;picks?:number[][];onPick?:(x:number,y:number)=>void}){
  const svg=useRef<SVGSVGElement>(null);const [drag,setDrag]=useState<{x:number;y:number;yaw:number}|null>(null);
  if(!floor||floor.status!=='AVAILABLE'||!floor.bounds)return <p role="status">Floor map unavailable · show the Twin first.</p>;
  const [x0,y0,x1,y1]=floor.bounds,w=Math.max(x1-x0,1),h=Math.max(y1-y0,1),c=floor.cell_m;
  const X=(x:number)=>x-x0,Y=(y:number)=>y1-y;
  const world=(event:{clientX:number;clientY:number})=>{const node=svg.current!;const box=node.getBoundingClientRect();
    const px=(event.clientX-box.left)/box.width*w,py=(event.clientY-box.top)/box.height*h;return [x0+px,y1-py] as [number,number];};
  const current=drag??(value?{x:value[0],y:value[1],yaw:value[2]}:null);
  return <div className="floor-map">
    <svg ref={svg} role="img" aria-label="Floor map · click to place, drag to aim · display scale, not localization" viewBox={`0 0 ${w} ${h}`}
      style={{width:'100%',maxHeight:height,background:'#20262e',borderRadius:6,touchAction:'none',cursor:onChange||onPick?'crosshair':'default'}}
      onPointerDown={event=>{if(!onChange&&!onPick)return;const [x,y]=world(event);
        if(onPick&&!onChange){onPick(Math.round(x*100)/100,Math.round(y*100)/100);return;}
        setDrag({x,y,yaw:value?.[2]??0});(event.currentTarget as Element).setPointerCapture(event.pointerId);}}
      onPointerMove={event=>{if(!drag)return;const [x,y]=world(event);const d=Math.hypot(x-drag.x,y-drag.y);
        if(d>0.08)setDrag({...drag,yaw:Math.atan2(y-drag.y,x-drag.x)});}}
      onPointerUp={()=>{if(!drag)return;onChange?.(Math.round(drag.x*1000)/1000,Math.round(drag.y*1000)/1000,Math.round(drag.yaw*1000)/1000);setDrag(null);}}>
      {floor.free_cells.map(([x,y],i)=><rect key={i} x={X(x)-c/2} y={Y(y)-c/2} width={c} height={c} fill="#3b4652"/>)}
      {floor.obstacles.map(([a,b,d,e],i)=><rect key={'o'+i} x={X(a)} y={Y(e)} width={d-a} height={e-b} fill="#6b4a3a" opacity={0.8}/>)}
      {floor.sim_obstacles?.map(o=><g key={o.id}><rect x={X(o.position_m[0])-o.size_m[0]/2} y={Y(o.position_m[1])-o.size_m[1]/2} width={o.size_m[0]} height={o.size_m[1]} fill="#8c1d18" opacity={0.75} stroke="#ff6b5e" strokeWidth={0.03} strokeDasharray="0.08 0.05"/>
        <text x={X(o.position_m[0])+o.size_m[0]/2+0.05} y={Y(o.position_m[1])+0.06} fontSize={0.16} fill="#ffb3ad">{o.label.slice(0,16)} · SIM only</text></g>)}
      {floor.lidar_layer?.drive_points.map(([x,y],i)=><rect key={'d'+i} x={X(x)-0.02} y={Y(y)-0.02} width={0.04} height={0.04} fill="#bfb34d" opacity={0.55}/>)}
      {floor.lidar_layer?.stop_points.map(([x,y],i)=><rect key={'s'+i} x={X(x)-0.025} y={Y(y)-0.025} width={0.05} height={0.05} fill="#33e6ff" opacity={0.85}/>)}
      {floor.lidar_layer?.moved.map(m=><g key={'m'+m.object_id}><circle cx={X(m.position_xy_m[0])} cy={Y(m.position_xy_m[1])} r={0.22} fill="none" stroke="#c060ff" strokeWidth={0.05}/>
        <text x={X(m.position_xy_m[0])+0.26} y={Y(m.position_xy_m[1])+0.06} fontSize={0.16} fill="#e0c0ff">{m.label.slice(0,16)} · LiDAR estimate</text></g>)}
      {floor.robots.filter(r=>r.position_m&&r.position_m.length>=2).map(r=><g key={r.robot_id}>
        <circle cx={X(r.position_m![0])} cy={Y(r.position_m![1])} r={0.1} fill={r.kind==='physical'?'#f2b84b':'#5fd3a6'} opacity={0.7}/>
        <text x={X(r.position_m![0])+0.12} y={Y(r.position_m![1])-0.1} fontSize={0.18} fill="#c8d0d8">{r.label.slice(0,14)}</text></g>)}
      {picks.map(([x,y],i)=><g key={'p'+i}><circle cx={X(x)} cy={Y(y)} r={0.11} fill="#f2b84b"/><text x={X(x)+0.14} y={Y(y)-0.1} fontSize={0.24} fill="#ffffff">{i+1}</text></g>)}
      {current&&<g><circle cx={X(current.x)} cy={Y(current.y)} r={0.12} fill="#3fa9f5"/>
        <line x1={X(current.x)} y1={Y(current.y)} x2={X(current.x+0.35*Math.cos(current.yaw))} y2={Y(current.y+0.35*Math.sin(current.yaw))} stroke="#3fa9f5" strokeWidth={0.06}/></g>}
    </svg>
    <small>{onChange?'Click to place the robot, drag to set its heading · ':''}{onPick?'Click to add a route stop · ':''}operator estimate, not localized{floor.lidar_layer&&(floor.lidar_layer.stop_points.length>0||floor.lidar_layer.drive_points.length>0)?` · LiDAR layer: ${floor.lidar_layer.routes} route${floor.lidar_layer.routes===1?'':'s'} (declared start + odometry, display only)`:''}</small>
  </div>;
}
