// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {fireEvent,render,screen} from '@testing-library/react';
import {expect,it,vi} from 'vitest';
import {ScenePlacementMap} from './ScenePlacementMap';
import type {SiteDraftSummary} from './types';

const site={revision:'a'.repeat(64),objects:[{id:'floor',kind:'floor',position_m:[1,2,0],dimensions_m:[4,6,.1],shape:'box',provenance:'fixture'}]} as SiteDraftSummary;
const props={site,label:'Loose cables',identity:'cables',position:[0,0] as [number,number],dimensions:[.4,.3] as [number,number],yaw:0,disabled:false};
function pointer(target:HTMLElement,type:string,x:number,y:number,id=1){
  const event=new MouseEvent(type,{bubbles:true,clientX:x,clientY:y,button:0});
  Object.defineProperty(event,'pointerId',{value:id});fireEvent(target,event);
}
function mapRect(){
  const map=screen.getByRole('group',{name:'Selected object floor map'});
  vi.spyOn(map,'getBoundingClientRect').mockReturnValue({left:10,top:20,right:410,bottom:620,width:400,height:600,x:10,y:20,toJSON:()=>({})});
}
it('commits a pointer drag only on release in shifted floor metres, not while moving',()=>{
  const onChange=vi.fn();render(<ScenePlacementMap {...props} onChange={onChange}/>);mapRect();
  const marker=screen.getByRole('button',{name:'Drag selected object'});
  pointer(marker,'pointerdown',110,520);pointer(marker,'pointermove',310,220);
  expect(onChange).not.toHaveBeenCalled();expect(screen.getByRole('status').textContent).toContain('X 2.00');
  pointer(marker,'pointerup',310,220);expect(onChange).toHaveBeenCalledExactlyOnceWith([2,3],0);
});
it('retains the grabbed point offset and does not jump on a click without movement',()=>{
  const onChange=vi.fn();render(<ScenePlacementMap {...props} onChange={onChange}/>);mapRect();
  const marker=screen.getByRole('button',{name:'Drag selected object'});
  pointer(marker,'pointerdown',120,510);pointer(marker,'pointerup',120,510);
  expect(onChange).not.toHaveBeenCalled();
  pointer(marker,'pointerdown',120,510);pointer(marker,'pointermove',140,490);pointer(marker,'pointerup',140,490);
  expect(onChange).toHaveBeenCalledExactlyOnceWith([.2,.2],0);
});
it('rejects outside drop, pointer mismatch and cancellation without mutating inputs',()=>{
  const onChange=vi.fn();render(<ScenePlacementMap {...props} onChange={onChange}/>);mapRect();
  const marker=screen.getByRole('button',{name:'Drag selected object'});
  pointer(marker,'pointerdown',100,100);pointer(marker,'pointerup',310,220,2);
  expect(onChange).not.toHaveBeenCalled();pointer(marker,'pointerup',500,220);
  pointer(marker,'pointerdown',100,100);pointer(marker,'pointercancel',310,220);pointer(marker,'pointerup',310,220);
  expect(onChange).not.toHaveBeenCalled();expect(props.position).toEqual([0,0]);
});
it('rotates and supports keyboard position input without a save or API action',()=>{
  const onChange=vi.fn();render(<ScenePlacementMap {...props} yaw={180} onChange={onChange}/>);
  fireEvent.click(screen.getByRole('button',{name:'Rotate selected object 90°'}));
  expect(onChange).toHaveBeenLastCalledWith([0,0],-90);
  fireEvent.keyDown(screen.getByRole('button',{name:'Drag selected object'}),{key:'ArrowUp'});
  expect(onChange).toHaveBeenLastCalledWith([0,.05],180);
});
it('locks independent attachment dragging and busy operations with an exact reason',()=>{
  const onChange=vi.fn();const {rerender}=render(<ScenePlacementMap {...props} lockedReason="Move parent desk instead" onChange={onChange}/>);
  expect(screen.getByRole('note').textContent).toContain('parent desk');
  expect((screen.getByRole('button',{name:'Drag selected object'}) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole('button',{name:'Rotate selected object 90°'}));expect(onChange).not.toHaveBeenCalled();
  rerender(<ScenePlacementMap {...props} disabled onChange={onChange}/>);
  expect((screen.getByRole('button',{name:'Rotate selected object 90°'}) as HTMLButtonElement).disabled).toBe(true);
});
it('reports missing floor rather than inventing a draggable map',()=>{
  render(<ScenePlacementMap {...props} site={{...site,objects:[]}} onChange={vi.fn()}/>);
  expect(screen.getByRole('alert').textContent).toContain('Floor geometry is unavailable');
  expect(screen.queryByRole('button',{name:'Drag selected object'})).toBeNull();
});
