// SPDX-License-Identifier: Apache-2.0
// Mocked parent/child boundary only; actual frame geometry belongs to UI acceptance.
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import {expect,it,vi} from 'vitest';
import {ChatWorkspace} from './ChatWorkspace';
import type {TwinPulseApi} from './api';

vi.mock('./TwinViewport',async importOriginal=>({...await importOriginal<typeof import('./TwinViewport')>(),
  TwinViewport:({robotFleet,onRobotSelect}:any)=><div data-testid="frame-names">
  {robotFleet?.robots.map((r:any)=><button key={r.robot_id} onClick={()=>onRobotSelect(r.robot_id)}>{r.label}</button>)}</div>}));
vi.mock('./RobotFleet',()=>({RobotFleet:({available}:any)=><div data-testid="control-admission">{available?'ready':'unavailable'}</div>}));

it('keeps current-project names during a fleet-read gap without granting focus or carrying names across context',async()=>{
  const state={schema_version:'conversation-1.0',session_id:'chat-1',project_id:'project',revision:0,cursor:0,
    mode:'SIM',robot_id:null,physical_authority:false,restore_error:null,messages:[],cards:[],events:[],generation:null,accepted_request_ids:[]};
  const fleet={revision:1,robots:[{robot_id:'a',label:'Alpha',kind:'sim'}],focused_robot_id:'a'};
  let calls=0;
  const api={context:'context-a',bootstrap:vi.fn(async()=>{}),conversation:vi.fn(async()=>state),runtimeState:vi.fn(async()=>({status:'ready'})),
    productState:vi.fn(async()=>({engine_connected:true})),workflow:vi.fn(async()=>({phase:'empty',provider:{configured:false,label:'Provider'}})),
    robotFleet:vi.fn(()=>++calls===1?Promise.resolve(fleet):new Promise(()=>{})),robotFleetAction:vi.fn()};
  const component=render(<ChatWorkspace api={api as unknown as TwinPulseApi} advanced={()=>{}}/>);
  await waitFor(()=>expect(screen.getByTestId('control-admission').textContent).toBe('ready'));
  await waitFor(()=>expect(screen.getByTestId('control-admission').textContent).toBe('unavailable'),{timeout:2200});
  fireEvent.click(screen.getByRole('button',{name:'Alpha'}));
  expect(screen.getByTestId('frame-names').textContent).toContain('Alpha');expect(api.robotFleetAction).not.toHaveBeenCalled();
  const changed={...api,context:'context-b'};
  component.rerender(<ChatWorkspace api={changed as unknown as TwinPulseApi} advanced={()=>{}}/>);
  await waitFor(()=>expect(screen.getByTestId('frame-names').textContent).not.toContain('Alpha'));
  component.unmount();
});
