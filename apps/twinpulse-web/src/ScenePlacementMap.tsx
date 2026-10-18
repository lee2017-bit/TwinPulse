// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {useEffect,useRef,useState,type CSSProperties} from 'react';
import type {SiteDraftSummary} from './types';

/** Controlled edit input, not a save, route validator or robot controller. */
export function ScenePlacementMap({site,label,identity,position,dimensions,yaw,disabled,lockedReason,onChange}:{
  site:SiteDraftSummary;label:string;identity:string;position:[number,number];dimensions:[number,number];yaw:number;
  disabled:boolean;lockedReason?:string;onChange:(position:[number,number],yaw:number)=>void;
}){
  const floor=site.objects.find(item=>item.kind==='floor');
  const map=useRef<HTMLDivElement>(null);
  const pointer=useRef<number|null>(null);
  const grabOffset=useRef<[number,number]>([0,0]);
  const [hover,setHover]=useState<[number,number]|null>(null);
  useEffect(()=>{pointer.current=null;setHover(null);},[identity,site.revision,disabled,lockedReason]);
  if(!floor||floor.dimensions_m[0]<=0||floor.dimensions_m[1]<=0)return <p role="alert">Floor geometry is unavailable. Use coordinates and the server preview.</p>;
  const [fw,fh]=floor.dimensions_m;const [fx,fy]=floor.position_m;
  const locked=disabled||!!lockedReason;
  const at=(xy:number[],size:number[],angle:number):CSSProperties=>{
    const a=angle*Math.PI/180;
    return {left:`${50+(xy[0]-fx)/fw*100}%`,top:`${50-(xy[1]-fy)/fh*100}%`,
      width:`${(Math.abs(Math.cos(a))*size[0]+Math.abs(Math.sin(a))*size[1])/fw*100}%`,
      height:`${(Math.abs(Math.sin(a))*size[0]+Math.abs(Math.cos(a))*size[1])/fh*100}%`};
  };
  const fromPointer=(clientX:number,clientY:number):[number,number]|null=>{
    const rect=map.current?.getBoundingClientRect();
    if(!rect||!rect.width||!rect.height||clientX<rect.left||clientX>rect.right||clientY<rect.top||clientY>rect.bottom)return null;
    return [Math.round((fx+(clientX-rect.left)/rect.width*fw-fw/2)*100)/100,
      Math.round((fy+fh/2-(clientY-rect.top)/rect.height*fh)*100)/100];
  };
  const displayed=hover??position;
  const dragPosition=(clientX:number,clientY:number):[number,number]|null=>{
    const point=fromPointer(clientX,clientY);
    return point ? [Math.round((point[0]+grabOffset.current[0])*100)/100,
      Math.round((point[1]+grabOffset.current[1])*100)/100]:null;
  };
  return <section className="scene-placement" aria-label="Selected object placement">
    <h4>{label} · placement preview</h4>
    <p>Drag the highlighted footprint; release to update X/Y. Rotate here or enter an exact yaw below. Nothing is saved or moved in 3D until Preview and Save.</p>
    {lockedReason&&<p role="note">{lockedReason}</p>}
    <div ref={map} className="scene-placement-map" role="group" aria-label="Selected object floor map"
      style={{aspectRatio:`${fw} / ${fh}`}}>
      <span className="room-map-back">+Y · back</span>
      {site.objects.filter(item=>item.kind!=='floor'&&item.id!==identity&&!item.id.startsWith(identity+'_')).map(item=>
        <span key={item.id} className="scene-map-existing" style={at(item.position_m,item.dimensions_m,item.rotation_rpy_deg?.[2]??0)} title={item.id}/>)}
      <button type="button" aria-label="Drag selected object" disabled={locked} className="scene-map-selected"
        style={at(displayed,dimensions,yaw)}
        onPointerDown={e=>{if(locked||e.button!==0||pointer.current!==null)return;e.preventDefault();
          const point=fromPointer(e.clientX,e.clientY);if(!point)return;
          grabOffset.current=[position[0]-point[0],position[1]-point[1]];
          pointer.current=e.pointerId;e.currentTarget.setPointerCapture?.(e.pointerId);}}
        onPointerMove={e=>{if(pointer.current!==e.pointerId||locked)return;setHover(dragPosition(e.clientX,e.clientY));}}
        onPointerUp={e=>{if(pointer.current!==e.pointerId)return;const next=dragPosition(e.clientX,e.clientY);
          pointer.current=null;setHover(null);if(next&&!locked&&(next[0]!==position[0]||next[1]!==position[1]))onChange(next,yaw);}}
        onPointerCancel={()=>{pointer.current=null;setHover(null);}}
        onLostPointerCapture={()=>{pointer.current=null;setHover(null);}}
        onKeyDown={e=>{
          const deltas:Record<string,[number,number]>={ArrowLeft:[-.05,0],ArrowRight:[.05,0],ArrowUp:[0,.05],ArrowDown:[0,-.05]};
          const delta=deltas[e.key];if(!delta||locked)return;e.preventDefault();
          onChange([Math.round((position[0]+delta[0])*100)/100,Math.round((position[1]+delta[1])*100)/100],yaw);
        }}>{label}</button>
      <span className="room-map-front">-Y · front</span>
    </div>
    <p role="status">Draft X {displayed[0].toFixed(2)} m · Y {displayed[1].toFixed(2)} m · yaw {yaw.toFixed(1)}°. Estimated top view, not sensed free space.</p>
    <button type="button" disabled={locked} onClick={()=>onChange(position,((yaw+90+180)%360+360)%360-180)}>Rotate selected object 90°</button>
    <small>Keyboard arrows move 5 cm. Server preview checks bounds and declared attachments; this map does not prove collision-free or physical placement.</small>
  </section>;
}
