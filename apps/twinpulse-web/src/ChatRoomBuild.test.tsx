// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {describe,it,expect,vi} from 'vitest';
import {ChatRoomBuild} from './ChatRoomBuild';
import {ChatWorkspace} from './ChatWorkspace';
import type {TwinPulseApi} from './api';
import type {ProductState} from './types';
const build={operation_id:'generation',scene_revision:'scene',artifact_id:'artifact'};
function fixture(){
  const snapshot={applied_revision:'scene',runtime_state:'built',safety_state:null,capabilities:[]};
  const ready={engine_connected:true,lease_owned:true,snapshot,operations:[{command_id:'build',status:'succeeded'}],
    engine_readiness:{site_scene_build_v2:{ready:true}}} as unknown as ProductState;
  const api={acquireLease:vi.fn().mockResolvedValue({control_lease_id:'lease'}),acknowledge:vi.fn().mockResolvedValue({}),
    renewLease:vi.fn().mockResolvedValue({}),productState:vi.fn().mockResolvedValue(ready),
    command:vi.fn().mockResolvedValue({command_id:'build'}),simulationRun:vi.fn(),chatRobotStop:vi.fn()};
  return {api,ready};
}
describe('Fresh REAL room display, never motion',()=>{
  it('waits for the actual room snapshot after one Build; rerenders never resend',async()=>{
    const {api,ready}=fixture();
    api.productState.mockResolvedValueOnce({...ready,snapshot:{...ready.snapshot,applied_revision:'old'}});
    const report=vi.fn();const view=render(<ChatRoomBuild api={api as unknown as TwinPulseApi} build={build} product={ready} report={report}/>);
    await screen.findByText(/Current room displayed in Isaac/);
    view.rerender(<ChatRoomBuild api={api as unknown as TwinPulseApi} build={{...build}} product={{...ready}} report={report}/>);
    expect(api.command).toHaveBeenCalledTimes(1);
    expect(api.command).toHaveBeenCalledWith('build_site_scene','scene','artifact');
    expect(api.simulationRun).not.toHaveBeenCalled();expect(api.chatRobotStop).not.toHaveBeenCalled();expect(report).not.toHaveBeenCalled();
  });
  it('unknown Build delivery reports failure without retransmission or Run',async()=>{
    const {api,ready}=fixture();api.productState.mockResolvedValue({...ready,snapshot:null});
    api.command.mockRejectedValue(new Error('delivery_unknown · check saved Build'));
    const report=vi.fn();const view=render(<ChatRoomBuild api={api as unknown as TwinPulseApi} build={build} product={ready} report={report}/>);
    await screen.findByText(/Room display needs attention/);
    view.rerender(<ChatRoomBuild api={api as unknown as TwinPulseApi} build={build} product={{...ready}} report={report}/>);
    expect(api.command).toHaveBeenCalledTimes(1);expect(report).toHaveBeenCalledWith(expect.stringContaining('delivery_unknown'));
    expect(api.simulationRun).not.toHaveBeenCalled();
  });
  it('does not acquire control while Isaac is unavailable',async()=>{
    const {api,ready}=fixture();render(<ChatRoomBuild api={api as unknown as TwinPulseApi} build={build} product={{...ready,engine_connected:false}} report={vi.fn()}/>);
    expect(screen.getByText(/Waiting for Isaac/)).toBeTruthy();expect(api.acquireLease).not.toHaveBeenCalled();
  });
  it('restored REAL history exposes room display before any inspection action and never arms Build',async()=>{
    const {api,ready}=fixture();const state={schema_version:'conversation-1.0',session_id:'chat',project_id:'default',revision:1,cursor:1,mode:'REAL',robot_id:'turtlebot3_burger',
      physical_authority:false,messages:[],cards:[],events:[],accepted_request_ids:[],restore_error:null,room_build:build,
      generation:{operation_id:'generation',state:'completed',can_cancel:false,summary:'Ready',last_progress_at:'now'},
      inspection:{state:'NOT_STARTED',owned:false,busy:false,motion_authorized:false,demo_ready:false,readiness:{ready:false,code:'CURRENT_TWIN_BUILD_REQUIRED'}}};
    const workspace={...api,bootstrap:vi.fn().mockResolvedValue({}),conversation:vi.fn().mockResolvedValue(state),
      runtimeState:vi.fn().mockResolvedValue({status:'ready'}),workflow:vi.fn().mockResolvedValue({phase:'draft_ready',site_draft:{revision:'scene',artifact_id:'artifact'}}),
      conversationAction:vi.fn().mockResolvedValue(state)};
    render(<ChatWorkspace api={workspace as unknown as TwinPulseApi} advanced={()=>{}}/>);
    const display=await screen.findByRole('button',{name:'Display current room in Isaac · no robot command'});
    expect(screen.queryByRole('button',{name:'Refresh inspection readiness · no robot command'})).toBeNull();
    expect(workspace.acquireLease).not.toHaveBeenCalled();expect(workspace.conversationAction).not.toHaveBeenCalled();
    expect(workspace.command).not.toHaveBeenCalled();expect(workspace.chatRobotStop).not.toHaveBeenCalled();
    fireEvent.click(display);
    await screen.findByText(/Current room displayed in Isaac/);
    expect(workspace.acquireLease).toHaveBeenCalledTimes(1);expect(workspace.simulationRun).not.toHaveBeenCalled();
    expect(screen.queryByRole('button',{name:'Refresh inspection readiness · no robot command'})).toBeNull();
  });
  it('offers read-only inspection readiness only after the current room is applied and robot is linked',async()=>{
    const {api}=fixture();
    const state={schema_version:'conversation-1.0',session_id:'chat',project_id:'default',revision:1,cursor:1,mode:'REAL',robot_id:'turtlebot3_burger',
      physical_authority:false,messages:[],cards:[],events:[],accepted_request_ids:[],restore_error:null,
      robot_preparation:{state:'LINKED',stage:'COMPLETE',busy:false},
      inspection:{state:'NOT_STARTED',owned:false,busy:false,motion_authorized:false,demo_ready:false,readiness:{ready:false,code:'NOT_CHECKED'}}};
    const workspace={...api,bootstrap:vi.fn().mockResolvedValue({}),conversation:vi.fn().mockResolvedValue(state),
      runtimeState:vi.fn().mockResolvedValue({status:'ready'}),workflow:vi.fn().mockResolvedValue({phase:'draft_ready',site_draft:{revision:'scene',artifact_id:'artifact'}}),
      conversationAction:vi.fn().mockResolvedValue(state)};
    render(<ChatWorkspace api={workspace as unknown as TwinPulseApi} advanced={()=>{}}/>);
    fireEvent.click(await screen.findByRole('button',{name:'Refresh inspection readiness · no robot command'}));
    await waitFor(()=>expect(workspace.conversationAction).toHaveBeenCalledWith({action:'inspection_check',request_id:expect.any(String)}));
    expect(workspace.command).not.toHaveBeenCalled();expect(workspace.chatRobotStop).not.toHaveBeenCalled();
  });
});
