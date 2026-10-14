// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { useEffect, useRef, useState } from 'react';

export function joystickDirection(x:number,y:number):string|null {
  if(!Number.isFinite(x)||!Number.isFinite(y)||Math.hypot(x,y)<.22)return null;
  return Math.abs(y)>=Math.abs(x)?y<0?'forward':'backward':x<0?'left':'right';
}

// Cardinal, fixed-speed intent only; diagonals never inject an unreviewed Twist.
export function DriveJoystick({disabled,onDirection,onRelease,disabledMessage='Control locked'}: {
  disabled:boolean;onDirection:(direction:string)=>void;onRelease:()=>void;disabledMessage?:string;
}) {
  const [offset,setOffset]=useState({x:0,y:0});
  const pointer=useRef<number|null>(null),direction=useRef<string|null>(null);
  const surface=useRef<HTMLButtonElement>(null);
  function release(){
    const wasActive=pointer.current!==null||direction.current!==null;
    pointer.current=null;direction.current=null;setOffset({x:0,y:0});
    if(wasActive)onRelease();
  }
  useEffect(()=>{if(disabled)release();},[disabled]); // Parent revokes control on fault/close.
  function move(clientX:number,clientY:number){
    const rect=surface.current?.getBoundingClientRect();if(!rect||!rect.width||!rect.height)return;
    let x=(clientX-rect.left-rect.width/2)/(rect.width*.35);
    let y=(clientY-rect.top-rect.height/2)/(rect.height*.35);
    const size=Math.hypot(x,y);if(size>1){x/=size;y/=size;}
    setOffset({x,y});const next=joystickDirection(x,y);
    if(next===direction.current)return;
    direction.current=next;
    if(next)onDirection(next);else onRelease();
  }
  return <div className="joystick-control">
    <button ref={surface} type="button" className="drive-joystick" aria-label="Drive joystick"
      aria-disabled={disabled} disabled={disabled}
      onPointerDown={e=>{if(disabled||e.button!==0||pointer.current!==null)return;
        e.preventDefault();pointer.current=e.pointerId;e.currentTarget.setPointerCapture?.(e.pointerId);move(e.clientX,e.clientY);}}
      onPointerMove={e=>{if(pointer.current===e.pointerId&&!disabled){e.preventDefault();move(e.clientX,e.clientY);}}}
      onPointerUp={e=>{if(pointer.current===e.pointerId)release();}}
      onPointerCancel={release} onLostPointerCapture={release} onContextMenu={e=>e.preventDefault()}>
      <span className="joystick-axis vertical"/><span className="joystick-axis horizontal"/>
      <span className="joystick-label north">Forward</span><span className="joystick-label south">Backward</span>
      <span className="joystick-label west">↶</span><span className="joystick-label east">↷</span>
      <span className="joystick-knob" style={{transform:`translate(${offset.x*62}px,${offset.y*62}px)`}}>●</span>
    </button>
    <p className="joystick-readout">{disabled?disabledMessage:direction.current?
      ({forward:'Forward',backward:'Backward',left:'Turn left',right:'Turn right'} as Record<string,string>)[direction.current]:
      'Drag to move · release to stop'}</p>
  </div>;
}
