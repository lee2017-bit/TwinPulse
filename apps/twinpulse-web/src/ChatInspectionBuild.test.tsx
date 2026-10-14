// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import {describe,it,expect,vi} from 'vitest';
import {ChatInspectionBuild} from './ChatInspectionBuild';
import {ChatWorkspace} from './ChatWorkspace';
import type {TwinPulseApi} from './api';
import type {ProductState} from './types';
import type {InspectionDisplay,ConversationState} from './conversation-types';
const display:InspectionDisplay={ready:true,code:'SAVED_SURVEY_DISPLAY_AVAILABLE',scene_revision:'derived',
  descriptor:{kind:'current_inspection_visual_v1',mission_id:'a'.repeat(32),manifest_sha256:'b'.repeat(64)},
  current_pose_available:false,motion_authorized:false};
function fixture(){
  const ready={engine_connected:true,engine_session_id:'engine',stage_epoch:'stage',snapshot:{applied_revision:'derived',runtime_state:'built',safety_state:null,capabilities:[]},
    operations:[{command_id:'overlay',status:'succeeded'}],engine_readiness:{current_inspection_visual_v1:{ready:true}}} as unknown as ProductState;
  const api={acquireLease:vi.fn().mockResolvedValue({control_lease_id:'lease'}),renewLease:vi.fn().mockResolvedValue({}),
    productState:vi.fn().mockResolvedValue(ready),chatInspectionDisplay:vi.fn().mockResolvedValue({command_id:'overlay',engine_session_id:'engine',stage_epoch:'stage'}),
    command:vi.fn(),simulationRun:vi.fn(),chatRobotStop:vi.fn(),conversationAction:vi.fn()};
  return {api,ready};
}
describe('Checked historical survey display',()=>{
  it('composes one overlay even if geometry already matches; never Run or robot input',async()=>{
    const {api,ready}=fixture();const report=vi.fn();
    const view=render(<ChatInspectionBuild api={api as unknown as TwinPulseApi} display={display} product={ready} report={report}/>);
    await screen.findByText(/Survey room displayed/);
    view.rerender(<ChatInspectionBuild api={api as unknown as TwinPulseApi} display={{...display}} product={{...ready}} report={report}/>);
    expect(api.chatInspectionDisplay).toHaveBeenCalledTimes(1);
    expect(api.chatInspectionDisplay).toHaveBeenCalledWith(display.descriptor,expect.any(String));
    expect(api.simulationRun).not.toHaveBeenCalled();expect(api.chatRobotStop).not.toHaveBeenCalled();expect(report).not.toHaveBeenCalled();
  });
  it('keeps receipt failure visible, never silently resends',async()=>{
    const {api,ready}=fixture();api.chatInspectionDisplay.mockRejectedValue(new Error('UNKNOWN_DELIVERY'));
    const report=vi.fn();const view=render(<ChatInspectionBuild api={api as unknown as TwinPulseApi} display={display} product={ready} report={report}/>);
    await screen.findByText(/Survey display failed/);
    view.rerender(<ChatInspectionBuild api={api as unknown as TwinPulseApi} display={display} product={{...ready}} report={report}/>);
    expect(api.chatInspectionDisplay).toHaveBeenCalledTimes(1);expect(report).toHaveBeenCalledWith(expect.stringContaining('UNKNOWN_DELIVERY'));
  });
  it('cannot acquire a lease while engine is disconnected',()=>{
    const {api,ready}=fixture();render(<ChatInspectionBuild api={api as unknown as TwinPulseApi} display={display} product={{...ready,engine_connected:false}} report={vi.fn()}/>);
    expect(api.acquireLease).not.toHaveBeenCalled();expect(screen.getByText(/Waiting for Isaac/)).toBeTruthy();
  });
  it('rejects an engine identity change even with a succeeded old receipt',async()=>{
    const {api,ready}=fixture();api.productState.mockResolvedValue({...ready,engine_session_id:'replacement'});
    const report=vi.fn();render(<ChatInspectionBuild api={api as unknown as TwinPulseApi} display={display} product={ready} report={report}/>);
    await screen.findByText(/Survey display failed/);
    expect(report).toHaveBeenCalledWith(expect.stringContaining('identity changed'));
    expect(api.chatInspectionDisplay).toHaveBeenCalledTimes(1);expect(api.simulationRun).not.toHaveBeenCalled();
  });
  for(const changed of [false,true])it(`restored history does not Build; changed source=${changed} remains explicit`,async()=>{
    const {api}=fixture();const state={schema_version:'conversation-1.0',session_id:'saved',project_id:'default',revision:3,cursor:3,
      mode:'REAL',robot_id:'turtlebot3_burger',physical_authority:false,restore_error:null,messages:[],cards:[],events:[],accepted_request_ids:[],generation:null,
      inspection_display:changed?{...display,ready:false,scene_revision:null,code:'INSPECTION_DISPLAY_CURRENT_ROOM_CHANGED'}:display} as ConversationState;
    const workspace={...api,bootstrap:vi.fn().mockResolvedValue({}),conversation:vi.fn().mockResolvedValue(state),
      runtimeState:vi.fn().mockResolvedValue({status:'ready'}),workflow:vi.fn().mockResolvedValue({phase:'empty'})};
    render(<ChatWorkspace api={workspace as unknown as TwinPulseApi} advanced={()=>{}}/>);
    const button=await screen.findByRole('button',{name:'Display saved survey room · no movement'});
    expect(workspace.acquireLease).not.toHaveBeenCalled();expect(workspace.chatInspectionDisplay).not.toHaveBeenCalled();
    fireEvent.click(button);
    if(changed){expect((button as HTMLButtonElement).disabled).toBe(true);expect(workspace.chatInspectionDisplay).not.toHaveBeenCalled();}
    else{await screen.findByText(/Survey room displayed/);await waitFor(()=>expect(workspace.chatInspectionDisplay).toHaveBeenCalledTimes(1));}
    expect(workspace.conversationAction).not.toHaveBeenCalled();expect(workspace.simulationRun).not.toHaveBeenCalled();
  });
  it('fresh acknowledged inspection completion arms one display; polling does not repeat it',async()=>{
    const {api}=fixture();let state={schema_version:'conversation-1.0',session_id:'fresh',project_id:'default',revision:1,cursor:1,
      mode:'REAL',robot_id:'turtlebot3_burger',physical_authority:false,restore_error:null,
      messages:[{message_id:'q',role:'assistant',content:'Inspect now?',status:'completed',attachments:[],created_at:'now',operation_id:null}],events:[],accepted_request_ids:[],generation:null,
      cards:[{id:'inspect',message_id:'q',kind:'robot_inspection',question:'Inspect now?',state:'waiting',selected_choice_id:null,expected_session_revision:1,
        operation_id:null,choices:[{id:'inspect',label:'Inspect now',enabled:true,disabled_reason:null}]}]} as ConversationState;
    const workspace={...api,bootstrap:vi.fn().mockResolvedValue({}),conversation:vi.fn(async()=>state),
      runtimeState:vi.fn().mockResolvedValue({status:'ready'}),workflow:vi.fn().mockResolvedValue({phase:'empty'}),
      conversationAction:vi.fn(async()=>state={...state,revision:2,cursor:2,cards:[],inspection_display:display,
        inspection:{state:'SURVEY_COMPLETE',owned:true,busy:false,job_id:display.descriptor.mission_id,motion_authorized:false,demo_ready:false}})};
    render(<ChatWorkspace api={workspace as unknown as TwinPulseApi} advanced={()=>{}}/>);
    fireEvent.click(await screen.findByRole('button',{name:'Inspect now'}));
    await screen.findByText(/Survey room displayed/);
    expect(workspace.chatInspectionDisplay).toHaveBeenCalledTimes(1);expect(workspace.simulationRun).not.toHaveBeenCalled();
  });
});
