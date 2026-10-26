// SPDX-License-Identifier: Apache-2.0
import {render,screen} from '@testing-library/react';
import {describe,expect,it} from 'vitest';
import {RoutePreview} from './ChatWorkspace';

describe('RoutePreview',()=>{
  it('draws the start, numbered stops and path as a labelled model plan',()=>{
    render(<RoutePreview preview={{bounds:[0,0,3,2],free_cells:[[0.55,0.55],[0.65,0.55]],cell_m:.1,start:[.5,.5,0],
      waypoints:[[2,1.5],[2.5,.5]],polyline:[[2,1.5],[2.5,.5],[.5,.5]],basis:'sim_engine_pose',scope:'DECLARED_START_MODEL_PLAN_NOT_LOCALIZED'}}/>);
    const map=screen.getByRole('img',{name:/model plan, not localization/});
    expect(map.querySelectorAll('circle').length).toBe(3);
    expect(map.querySelector('polyline')?.getAttribute('points')).toBe('0.5,1.5 2,0.5 2.5,1.5 0.5,1.5');
    expect(screen.getByText('Start')).toBeTruthy();
  });
});
