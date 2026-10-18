// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {describe,it,expect,vi} from 'vitest';
import {ChatRobotStatus} from './ChatRobotStatus';
import type {RobotPreparation} from './conversation-types';
import type {TwinPulseApi} from './api';

const state=(phase='CHECKING'):RobotPreparation=>({state:phase,stage:'READ_ONLY_CONNECTION',code:null,
  attempt_id:'attempt',binding:'binding',owned:true,available:true,transport:'OFFLINE_TEST_TRANSPORT',
  physical_authority:false,demo_ready:false,job_id:null,record:null,trial:null});
describe('Chat robot preparation',()=>{
  it('offers explicit stationary collection and transfer-only resume with separate sensor failures',()=>{
    const collect=vi.fn(),transfer=vi.fn();
    const current:RobotPreparation={...state('COLLECTION_RESULT'),collection:{status:'COMPLETED_WITH_GAPS',job_id:'job',owned:true,
      result_code:'EVIDENCE_GAPS',reason:null,steps:[{id:'stationary_collection',status:'EVIDENCE_EXPORT_INCOMPLETE',reason:null}],
      sources:[{id:'odom',status:'REJECTED',reason:'FRAME_ID',fault_counts:{FRAME_ID:3}},{id:'scan',status:'NOT_RECEIVED',reason:'NO_PUBLISHER',fault_counts:{}}],
      raw_export:{status:'INCOMPLETE'},recovery:{status:'NOT_STARTED',transfer_only:true as const},resume_available:true,
      motion_authorized:false as const,alignment_verified:false as const,demo_ready:false as const}};
    render(<ChatRobotStatus state={current} api={{} as TwinPulseApi} report={()=>{}} collect={collect} transfer={transfer}/>);
    expect(collect).not.toHaveBeenCalled();expect(transfer).not.toHaveBeenCalled();
    expect(screen.getByText('odom: REJECTED · FRAME_ID')).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'Resume saved raw transfer only'}));
    expect(transfer).toHaveBeenCalledWith('stationary','job');
    fireEvent.click(screen.getByRole('button',{name:'Approve source transfer and collect once'}));
    expect(collect).toHaveBeenCalledTimes(1);
  });
  it('locks collection during unknown remote state or active transfer',()=>{
    const collection={status:'REMOTE_STATE_UNKNOWN',job_id:'job',owned:true,result_code:'TimeoutError',reason:null,
      steps:[],sources:[],raw_export:null,recovery:null,resume_available:false,
      motion_authorized:false as const,alignment_verified:false as const,demo_ready:false as const};
    const view=render(<ChatRobotStatus state={{...state('COLLECTION_RESULT'),collection}} api={{} as TwinPulseApi} report={()=>{}} collect={()=>{}}/>);
    expect(screen.getByRole('button',{name:'Approve source transfer and collect once'})).toHaveProperty('disabled',true);
    view.rerender(<ChatRobotStatus state={{...state('COLLECTION_RESULT'),collection:{...collection,status:'COMPLETED_WITH_GAPS',recovery:{status:'TRANSFERRING',transfer_only:true}}}} api={{} as TwinPulseApi} report={()=>{}} collect={()=>{}}/>);
    expect(screen.getByRole('button',{name:'Approve source transfer and collect once'})).toHaveProperty('disabled',true);
  });
  it('renders checking and bounded qualification distinctly without auto Stop or transport',()=>{
    const api={chatRobotStop:vi.fn()};const view=render(<ChatRobotStatus state={state()} api={api as unknown as TwinPulseApi} report={()=>{}}/>);
    expect(screen.getByText(/Booting may take 2–3 minutes/)).toBeTruthy();
    view.rerender(<ChatRobotStatus state={state('QUALIFYING')} api={api as unknown as TwinPulseApi} report={()=>{}}/>);
    expect(screen.getByText(/One bounded forward-and-stop trial/)).toBeTruthy();
    expect(api.chatRobotStop).not.toHaveBeenCalled();
  });
  it('Force STOP is independent of pending ordinary Stop and reports delivery failure',async()=>{
    let finish:(v:{state:string})=>void=()=>{};
    const api={chatRobotStop:vi.fn((force:boolean)=>force?Promise.reject(new Error('Stop delivery unknown')):
      new Promise<{state:string}>(resolve=>{finish=resolve;}))};const report=vi.fn();
    render(<ChatRobotStatus state={state('QUALIFYING')} api={api as unknown as TwinPulseApi} report={report}/>);
    fireEvent.click(screen.getByRole('button',{name:'Stop after current command'}));
    expect(screen.getByRole('button',{name:'Force STOP'})).toHaveProperty('disabled',false);
    fireEvent.click(screen.getByRole('button',{name:'Force STOP'}));
    await waitFor(()=>expect(report).toHaveBeenCalledWith('Stop delivery unknown'));
    await act(async()=>finish({state:'STOPPING'}));
    expect(api.chatRobotStop.mock.calls).toEqual([[false],[true]]);
  });
  it('disables stop with no active owned worker, retains cleanup cause and snapshot labeling',()=>{
    const current={...state('BLOCKED'),cleanup_error:'MOTOR_OFF_READ_FAILED',record:{boot_id:'boot',release_id:'release',observed_at_utc:'now',age_seconds:1,
      battery:{estimated_percent:71.1,voltage_v:11.78,capacity_measured:false as const}}};
    render(<ChatRobotStatus state={current} api={{} as TwinPulseApi} report={()=>{}}/>);
    expect(screen.getByRole('button',{name:'Force STOP'})).toHaveProperty('disabled',true);
    expect(screen.getByRole('alert').textContent).toContain('MOTOR_OFF_READ_FAILED');
    expect(screen.getByText(/71.1% estimated/)).toBeTruthy();
    expect(screen.getByText(/Offline test transport/)).toBeTruthy();
  });
});
