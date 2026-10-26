// SPDX-License-Identifier: Apache-2.0
import {describe,expect,it,vi} from 'vitest';
import {fireEvent,render,screen} from '@testing-library/react';
import {DeclaredRouteCard} from './DeclaredRouteCard';
import type {DeclaredRouteState} from './robot-fleet-types';

const route=(over:Partial<DeclaredRouteState>={}):DeclaredRouteState=>({plan_id:'p',robot_id:'r',kind:'sim',state:'RUNNING',reason:null,reached:1,reached_stops:[0],skipped_stops:[],
  total_stops:4,completed_steps:7,planned_steps:15,current_step:'forward 73.4cm',recoveries:0,started_at:1000,finished_at:null,revision:3,label:'X',scene_current:true,
  start:[.6,.6,0],waypoints:[[1.5,.6],[2.5,1.2],[2.5,2.2],[1,2.2]],polyline:[[1.5,.6],[2.5,1.2]],pose:[1.2,.6,0],trace:[[.6,.6],[1.2,.6]],keepouts:null,candidates:0,...over});

describe('DeclaredRouteCard',()=>{
  it('shows stop progress, the honest move count and sends Stop all through the fleet',async()=>{
    const api={robotFleetAction:vi.fn().mockResolvedValue({revision:2})} as never;
    const onChange=vi.fn();
    render(<DeclaredRouteCard route={route()} api={api} onChange={onChange} available report={()=>{}}/>);
    expect(screen.getByText('Route running · stop 1 of 4')).toBeTruthy();
    expect(screen.getByText(/7 moves done · about 15 planned; odometry re-aims can add more · now: forward 73.4cm/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'Stop route'}));
    await vi.waitFor(()=>expect(onChange).toHaveBeenCalledWith({revision:2}));
    expect((api as {robotFleetAction:ReturnType<typeof vi.fn>}).robotFleetAction.mock.calls[0][0].action).toBe('stop_all');
  });
  it('reports skipped stops and the finish reason, and can be dismissed',()=>{
    render(<DeclaredRouteCard route={route({state:'COMPLETED',reached_stops:[0,2,3],skipped_stops:[1],completed_steps:21,finished_at:1300,reason:'ALL_STOPS_AND_RETURN_COMPLETED',candidates:2})}
      api={{} as never} onChange={()=>{}} available report={()=>{}}/>);
    expect(screen.getByText('Route completed · 3 of 4 stops (skipped 2)')).toBeTruthy();
    expect(screen.getByText(/2 LiDAR objects not in the Twin/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'Dismiss'}));
    expect(screen.queryByText(/Route completed/)).toBeNull();
  });
  it('renders nothing for another scene revision or without a route',()=>{
    const {container}=render(<DeclaredRouteCard route={route({scene_current:false})} api={{} as never} onChange={()=>{}} available report={()=>{}}/>);
    expect(container.textContent).toBe('');
  });
});
