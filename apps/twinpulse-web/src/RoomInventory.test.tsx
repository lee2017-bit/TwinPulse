// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {render,screen} from '@testing-library/react';
import {describe,it,expect} from 'vitest';
import {RoomInventory} from './RoomInventory';
import type {PhotoRoomInventory,RoomInventoryState} from './types';

describe('room inventory evidence boundaries',()=>{
  const photo={items:[{id:'cables',kind:'cable_bundle',label:'Loose floor cables',visibility:'visible',required_for_route:true,placement_status:'unplaced'}],
    missing_route_items:['cables'],route_inventory_complete:false} as PhotoRoomInventory;
  it('keeps unplaced hazards visible instead of implying free space',()=>{
    render(<RoomInventory photo={photo}/>);
    expect(screen.getByText(/1 photo hazards still need placement/)).toBeTruthy();
    expect(screen.getByText('Loose floor cables')).toBeTruthy();
    expect(screen.getByText(/Unplaced · do not assume clear space/)).toBeTruthy();
    expect(screen.getByText(/Last observation: unknown/)).toBeTruthy();
  });
  it('distinguishes synthetic keepouts, collision and saved observations',()=>{
    const inventory={items:[{id:'cables',kind:'cable_bundle',label:'Loose floor cables',risk:'entanglement',basis:'user',
      last_observation_utc:null,placement_status:'represented',geometry:[{id:'cables_keepout',position_m:[1,2,.175],
      dimensions_m:[.6,.5,.35],yaw_deg:90,collision:true,synthetic_keepout:true}]}]} as RoomInventoryState;
    render(<RoomInventory inventory={inventory}/>);
    expect(screen.getByText('entanglement · represented')).toBeTruthy();
    expect(screen.getByText(/Keepout: position 1.00, 2.00, 0.17/)).toBeTruthy();
    expect(screen.getByText(/Saved proposal, not a live scan/)).toBeTruthy();
  });
});
