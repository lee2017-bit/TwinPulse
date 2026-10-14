// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {describe,it,expect,vi} from 'vitest';
import type {TwinPulseApi} from './api';
import {SceneSensorFeedback} from './SceneSensorFeedback';
import {ActionCard} from './ChatWorkspace';
import type {SceneSensorContext,QuestionCard,SceneSensorResult} from './conversation-types';

const context:SceneSensorContext={schema_version:'scene-sensor-context-1.0',project_id:'default',input_revision:'1'.repeat(64),
  source_sha256:'2'.repeat(64),current_scene_revision:'3'.repeat(64),current_state_sha256:'4'.repeat(64),physical_authority:false};
const map={map_id:'a'.repeat(32),revision:'5'.repeat(64),keyframes:11};
function api(){return {automaticMaps:vi.fn().mockResolvedValue({maps:[map]}),sceneSensorContext:vi.fn().mockResolvedValue(context)} as unknown as TwinPulseApi;}

describe('Current Twin saved sensor feedback',()=>{
  it('completed survey requires explicit import and exact report/current identities, then selects the normal map without auto review',async()=>{
    const review=vi.fn();const gateway=api();const mission='b'.repeat(32);
    gateway.sceneSensorSurveys=vi.fn().mockResolvedValue({surveys:[{mission_id:mission,report_revision:'6'.repeat(64),source_job_id:mission,
      status:'READY',reason:'Completed synthetic lifecycle',provenance:'SYNTHETIC_TRANSPORT'}],physical_authority:false});
    const shown=render(<SceneSensorFeedback api={gateway} revision={context.current_scene_revision} stateSha={context.current_state_sha256} enabled review={review}/>);
    await screen.findByRole('option',{name:new RegExp(mission)});expect(review).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('Completed survey'),{target:{value:mission}});
    fireEvent.click(screen.getByRole('button',{name:'Import saved survey'}));
    expect(review).toHaveBeenCalledWith(expect.objectContaining({action:'sensor_import',mission_id:mission,expected_report_revision:'6'.repeat(64),
      expected_scene_revision:context.current_scene_revision,expected_state_sha256:context.current_state_sha256}));
    const imported:SceneSensorResult={status:'imported',policy:'import_only',context,physical_authority:false,map_id:map.map_id,map_revision:map.revision,
      evidence:{map_id:map.map_id,map_revision:map.revision,source_job_id:mission,provenance:'SYNTHETIC_TRANSPORT'}};
    shown.rerender(<SceneSensorFeedback api={gateway} revision={context.current_scene_revision} stateSha={context.current_state_sha256} enabled result={imported} review={review}/>);
    await waitFor(()=>expect((screen.getByLabelText('Saved sensor map') as HTMLSelectElement).value).toBe(map.map_id));
    expect(review).toHaveBeenCalledTimes(1);
    expect((screen.getByRole('button',{name:'Import saved survey'}) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole('button',{name:'Review saved sensor feedback'}) as HTMLButtonElement).disabled).toBe(false);
    expect(screen.getByText(/Historical map registered/)).toBeTruthy();
  });
  it('HELD or stale completed survey cannot import or dispatch a command',async()=>{
    const review=vi.fn();const gateway=api();const mission='b'.repeat(32);
    gateway.sceneSensorSurveys=vi.fn().mockResolvedValue({surveys:[{mission_id:mission,report_revision:null,source_job_id:mission,
      status:'HELD',reason:'SCENE_SENSOR_SURVEY_TERMINAL_BINDING_MISSING',provenance:'UNAVAILABLE'}],physical_authority:false});
    render(<SceneSensorFeedback api={gateway} revision={context.current_scene_revision} stateSha={context.current_state_sha256} enabled review={review}/>);
    await screen.findByRole('option',{name:new RegExp(mission)});fireEvent.change(screen.getByLabelText('Completed survey'),{target:{value:mission}});
    expect(screen.getByText(/TERMINAL_BINDING_MISSING/)).toBeTruthy();
    expect((screen.getByRole('button',{name:'Import saved survey'}) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole('button',{name:'Import saved survey'}));expect(review).not.toHaveBeenCalled();
  });
  it('opening only reads metadata; explicit selection sends exact map/state bindings',async()=>{
    const review=vi.fn();render(<SceneSensorFeedback api={api()} revision={context.current_scene_revision} stateSha={context.current_state_sha256} enabled result={null} review={review}/>);
    await screen.findByText(/11 views/);expect(review).not.toHaveBeenCalled();
    expect((screen.getByRole('button',{name:'Review saved sensor feedback'}) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText('Saved sensor map'),{target:{value:map.map_id}});
    fireEvent.click(screen.getByRole('button',{name:'Review saved sensor feedback'}));
    expect(review).toHaveBeenCalledWith(expect.objectContaining({action:'sensor_review',map_id:map.map_id,expected_map_revision:map.revision,
      expected_scene_revision:context.current_scene_revision,expected_state_sha256:context.current_state_sha256}));
  });
  it('busy and stale state cannot submit or auto-retry a selection',async()=>{
    const review=vi.fn();const gateway=api();const shown=render(<SceneSensorFeedback api={gateway} revision={context.current_scene_revision} stateSha={context.current_state_sha256} enabled={false} review={review}/>);
    await screen.findByText(/11 views/);expect((screen.getByLabelText('Saved sensor map') as HTMLSelectElement).disabled).toBe(true);
    shown.rerender(<SceneSensorFeedback api={gateway} revision={context.current_scene_revision} stateSha={'0'.repeat(64)} enabled review={review}/>);
    await waitFor(()=>expect(gateway.sceneSensorContext).toHaveBeenCalledTimes(2));
    fireEvent.change(screen.getByLabelText('Saved sensor map'),{target:{value:map.map_id}});
    expect((screen.getByRole('button',{name:'Review saved sensor feedback'}) as HTMLButtonElement).disabled).toBe(true);
    expect(review).not.toHaveBeenCalled();
  });
  it('HELD and pose-only retain unverified provenance and no execution claim',async()=>{
    const review=vi.fn();render(<SceneSensorFeedback api={api()} revision={context.current_scene_revision} stateSha={context.current_state_sha256} enabled review={review}
      result={{status:'POSE_CANDIDATE',policy:'align_only',context,physical_authority:false,evidence:{map_id:map.map_id,map_revision:map.revision,source_job_id:'b'.repeat(32),provenance:'SYNTHETIC_TRANSPORT'}}}/>);
    expect(screen.getByText(/Explicit synthetic typed sensor fixture/)).toBeTruthy();
    expect(screen.getByText(/Pose only: geometry, history and Build unchanged/)).toBeTruthy();
    expect(screen.getByText(/No measured floor pose/)).toBeTruthy();expect(review).not.toHaveBeenCalled();
  });
  it('uses the existing one-policy question and does not select a wall policy automatically',()=>{
    const act=vi.fn();const card:QuestionCard={message_id:'m',id:'q',kind:'scene_sensor_policy',question:'How should this saved sensor evidence be reviewed?',state:'waiting',selected_choice_id:null,expected_session_revision:1,operation_id:null,
      choices:[{id:'align_only',label:'Pose only · no geometry change',enabled:true,disabled_reason:null},
      {id:'correct_walls',label:'Review bounded wall changes',enabled:true,disabled_reason:null},{id:'cancel',label:'Cancel sensor review',enabled:true,disabled_reason:null}]};
    render(<ActionCard card={card} busy={false} act={act}/>);
    expect((screen.getByRole('button',{name:'Continue'}) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByLabelText('Review bounded wall changes'));fireEvent.click(screen.getByRole('button',{name:'Continue'}));
    expect(act).toHaveBeenCalledWith(card,'correct_walls');expect(act).toHaveBeenCalledTimes(1);
  });
});
