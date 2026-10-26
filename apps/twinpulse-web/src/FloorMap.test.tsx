// SPDX-License-Identifier: Apache-2.0
import {describe,expect,it,vi} from 'vitest';
import {fireEvent,render,screen} from '@testing-library/react';
import {FloorMap} from './FloorMap';

const floor={status:'AVAILABLE' as const,scene_revision:'rev',bounds:[0,0,4,2],free_cells:[[0.5,0.5]],cell_m:.1,obstacles:[[1,1,2,2]],robots:[]};

describe('FloorMap',()=>{
  it('turns a click into floor coordinates and a drag into a heading',()=>{
    const onChange=vi.fn();
    render(<FloorMap floor={floor} onChange={onChange}/>);
    const svg=screen.getByRole('img');
    svg.getBoundingClientRect=()=>({left:0,top:0,width:400,height:200,right:400,bottom:200,x:0,y:0,toJSON(){}} as DOMRect);
    (svg as unknown as {setPointerCapture:()=>void}).setPointerCapture=()=>{};
    fireEvent.pointerDown(svg,{clientX:100,clientY:150,pointerId:1});   // world (1.0, 0.5)
    fireEvent.pointerMove(svg,{clientX:200,clientY:150,pointerId:1});   // drag +x: heading 0
    fireEvent.pointerUp(svg,{pointerId:1});
    expect(onChange).toHaveBeenCalledWith(1,0.5,0);
  });
  it('reports picked stops when used for route editing',()=>{
    const onPick=vi.fn();
    render(<FloorMap floor={floor} onPick={onPick}/>);
    const svg=screen.getByRole('img');
    svg.getBoundingClientRect=()=>({left:0,top:0,width:400,height:200,right:400,bottom:200,x:0,y:0,toJSON(){}} as DOMRect);
    fireEvent.pointerDown(svg,{clientX:300,clientY:50,pointerId:2});
    expect(onPick).toHaveBeenCalledWith(3,1.5);
  });
  it('says when the floor is unavailable',()=>{
    render(<FloorMap floor={{...floor,status:'UNAVAILABLE',bounds:null}}/>);
    expect(screen.getByRole('status').textContent).toContain('unavailable');
  });
});

describe('FloorMap LiDAR layer',()=>{
  it('draws stop points, drive points and LiDAR-move markers from the session layer as display only',()=>{
    const layer={scene_revision:'rev',stop_points:[[1,1],[1.1,1]],drive_points:[[2,1]],routes:2,revision:3,label:'DECLARED_START_PLUS_ODOMETRY_DISPLAY_ONLY_NOT_REGISTERED',
      moved:[{object_id:'Added_1',label:'Fan base',position_xy_m:[3,1],distance_m:.3,basis:'lidar_estimate_unverified'}]};
    const {container}=render(<FloorMap floor={{...floor,lidar_layer:layer}}/>);
    expect(container.querySelectorAll('rect[fill="#33e6ff"]')).toHaveLength(2);
    expect(container.querySelectorAll('rect[fill="#bfb34d"]')).toHaveLength(1);
    expect(screen.getByText('Fan base · LiDAR estimate')).toBeTruthy();
    expect(screen.getByText(/LiDAR layer: 2 routes \(declared start \+ odometry, display only\)/)).toBeTruthy();
  });
  it('draws nothing extra without a layer',()=>{
    const {container}=render(<FloorMap floor={floor}/>);
    expect(container.querySelectorAll('rect[fill="#33e6ff"]')).toHaveLength(0);
  });
});
