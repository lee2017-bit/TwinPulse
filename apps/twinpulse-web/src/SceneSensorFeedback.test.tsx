// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {describe,it,expect,vi} from 'vitest';
import type {TwinPulseApi} from './api';
import {SceneSensorFeedback} from './SceneSensorFeedback';
import {ActionCard} from './ChatWorkspace';
import type {SceneSensorContext,QuestionCard,SceneSensorResult,SceneSensorSurvey} from './conversation-types';

const context:SceneSensorContext={schema_version:'scene-sensor-context-1.0',project_id:'default',input_revision:'1'.repeat(64),
  source_sha256:'2'.repeat(64),current_scene_revision:'3'.repeat(64),current_state_sha256:'4'.repeat(64),physical_authority:false};
const map={map_id:'a'.repeat(32),revision:'5'.repeat(64),keyframes:11};
function api(){return {context:'sensor-a',automaticMaps:vi.fn().mockResolvedValue({maps:[map]}),
  sceneSensorSurveys:vi.fn().mockResolvedValue({surveys:[],physical_authority:false}),sceneSensorContext:vi.fn().mockResolvedValue(context)} as unknown as TwinPulseApi;}

describe('Current Twin saved sensor feedback',()=>{
  it('keeps legacy wall feedback read-only while transport is stale without replaying catalogs on recovery',async()=>{
    const gateway=api(),review=vi.fn();const component=(fresh:boolean)=><SceneSensorFeedback api={gateway} revision={context.current_scene_revision} stateSha={context.current_state_sha256} enabled fresh={fresh} review={review}/>;
    const view=render(component(true));await waitFor(()=>expect(gateway.sceneSensorContext).toHaveBeenCalledOnce());
    fireEvent.change(screen.getByLabelText('Saved sensor map'),{target:{value:map.map_id}});
    const button=screen.getByRole('button',{name:'Review saved sensor feedback'});expect(button).toHaveProperty('disabled',false);
    view.rerender(component(false));expect(button).toHaveProperty('disabled',true);fireEvent.click(button);expect(review).not.toHaveBeenCalled();
    view.rerender(component(true));expect(button).toHaveProperty('disabled',false);expect(gateway.sceneSensorContext).toHaveBeenCalledOnce();
    fireEvent.click(button);expect(review).toHaveBeenCalledOnce();
  });
  it('embeds independent local obstacle feedback above saved-map policies without starting a scan or model',async()=>{
    const gateway=api(),review=vi.fn();gateway.automaticMaps=vi.fn().mockResolvedValue({maps:[]});
    Object.assign(gateway,{obstacleFeedbackState:vi.fn().mockResolvedValue({schema_version:'obstacle-feedback-1.0',
      context:{project_id:'default',current_scene_revision:context.current_scene_revision,current_state_sha256:context.current_state_sha256},
      observations:[],targets:[],physical_authority:false}),sceneEditTransaction:vi.fn().mockResolvedValue(null),importObstacleObservation:vi.fn()});
    render(<SceneSensorFeedback api={gateway} revision={context.current_scene_revision} stateSha={context.current_state_sha256} enabled review={review}/>);
    expect(await screen.findByText(/No saved obstacle observation/)).toBeTruthy();
    expect(screen.getByRole('region',{name:'Obstacle observation feedback'})).toBeTruthy();
    expect(screen.getByRole('button',{name:'Import obstacle observation · local only'})).toHaveProperty('disabled',true);
    await screen.findByRole('status',{name:'Sensor preparation next steps'});
    expect(gateway.sceneSensorContext).not.toHaveBeenCalled();expect(review).not.toHaveBeenCalled();
  });
  it.each(['map','survey'])('requests one strict context only after both catalogs succeed with a saved %s',async kind=>{
    const gateway=api(),review=vi.fn();let finishCatalog!:(value:{surveys:SceneSensorSurvey[];physical_authority:false})=>void;
    let finishContext!:(value:SceneSensorContext)=>void;
    const mission='b'.repeat(32),survey:SceneSensorSurvey={mission_id:mission,report_revision:'6'.repeat(64),source_job_id:mission,
      status:'READY',reason:'Saved completed survey',provenance:'RECORDED_REAL_TRANSPORT'};
    gateway.automaticMaps=vi.fn().mockResolvedValue({maps:kind==='map'?[map]:[]});
    gateway.sceneSensorSurveys=vi.fn(()=>new Promise<{surveys:SceneSensorSurvey[];physical_authority:false}>(resolve=>{finishCatalog=resolve;}));
    gateway.sceneSensorContext=vi.fn(()=>new Promise<SceneSensorContext>(resolve=>{finishContext=resolve;}));
    render(<SceneSensorFeedback api={gateway} revision={context.current_scene_revision} stateSha={context.current_state_sha256} enabled review={review}/>);
    await act(async()=>{await Promise.resolve();});expect(gateway.sceneSensorContext).not.toHaveBeenCalled();
    expect(screen.queryByRole('status',{name:'Sensor preparation next steps'})).toBeNull();
    await act(async()=>finishCatalog({surveys:kind==='survey'?[survey]:[],physical_authority:false}));
    expect(gateway.sceneSensorContext).toHaveBeenCalledTimes(1);
    fireEvent.change(screen.getByLabelText(kind==='map'?'Saved sensor map':'Completed survey'),{target:{value:kind==='map'?map.map_id:mission}});
    const button=screen.getByRole('button',{name:kind==='map'?'Review saved sensor feedback':'Import saved survey'});
    expect(button).toHaveProperty('disabled',true);expect(review).not.toHaveBeenCalled();
    await act(async()=>finishContext(context));expect(button).toHaveProperty('disabled',false);
    expect(gateway.sceneSensorContext).toHaveBeenCalledTimes(1);expect(review).not.toHaveBeenCalled();
  });
  it.each(['maps','surveys','missing-surveys','invalid-maps'])('does not turn a failed or unavailable %s catalog into empty evidence or request strict context',async failure=>{
    const gateway=api(),review=vi.fn();gateway.automaticMaps=vi.fn().mockResolvedValue({maps:[]});
    if(failure==='maps')gateway.automaticMaps=vi.fn().mockRejectedValue(new Error('Saved maps read failed'));
    if(failure==='surveys')gateway.sceneSensorSurveys=vi.fn().mockRejectedValue(new Error('Saved surveys read failed'));
    if(failure==='missing-surveys')gateway.sceneSensorSurveys=undefined as never;
    if(failure==='invalid-maps')gateway.automaticMaps=vi.fn().mockResolvedValue({maps:null});
    render(<SceneSensorFeedback api={gateway} revision={context.current_scene_revision} stateSha={context.current_state_sha256} enabled review={review}/>);
    await screen.findByRole('alert');expect(gateway.sceneSensorContext).not.toHaveBeenCalled();
    expect(screen.queryByRole('status',{name:'Sensor preparation next steps'})).toBeNull();
    expect(screen.getByRole('button',{name:'Review saved sensor feedback'})).toHaveProperty('disabled',true);
    expect(screen.getByRole('button',{name:'Import saved survey'})).toHaveProperty('disabled',true);expect(review).not.toHaveBeenCalled();
  });
  it('preserves a strict-context failure as an error with saved evidence present',async()=>{
    const gateway=api(),review=vi.fn();gateway.sceneSensorContext=vi.fn().mockRejectedValue(new Error('Strict scene replay failed'));
    render(<SceneSensorFeedback api={gateway} revision={context.current_scene_revision} stateSha={context.current_state_sha256} enabled review={review}/>);
    expect((await screen.findByRole('alert')).textContent).toBe('Strict scene replay failed');
    fireEvent.change(screen.getByLabelText('Saved sensor map'),{target:{value:map.map_id}});
    expect(screen.getByRole('button',{name:'Review saved sensor feedback'})).toHaveProperty('disabled',true);
    expect(screen.queryByRole('status',{name:'Sensor preparation next steps'})).toBeNull();
    expect(gateway.sceneSensorContext).toHaveBeenCalledTimes(1);expect(review).not.toHaveBeenCalled();
  });
  it('does not start strict context after pending catalogs finish on a disabled panel',async()=>{
    const gateway=api(),review=vi.fn();let finish!:(value:Awaited<ReturnType<TwinPulseApi['automaticMaps']>>)=>void;
    gateway.automaticMaps=vi.fn(()=>new Promise<Awaited<ReturnType<TwinPulseApi['automaticMaps']>>>(resolve=>{finish=resolve;}));
    const shown=render(<SceneSensorFeedback api={gateway} revision={context.current_scene_revision} stateSha={context.current_state_sha256} enabled review={review}/>);
    shown.rerender(<SceneSensorFeedback api={gateway} revision={context.current_scene_revision} stateSha={context.current_state_sha256} enabled={false} review={review}/>);
    await act(async()=>finish({maps:[map as never]}));
    expect(gateway.sceneSensorContext).not.toHaveBeenCalled();expect(screen.queryByText(/11 views/)).toBeNull();
    expect(screen.queryByRole('status',{name:'Sensor preparation next steps'})).toBeNull();expect(review).not.toHaveBeenCalled();
  });
  it.each(['revision','state-sha','api-context','disabled'])('does not publish a late strict context across %s change',async change=>{
    const gateway=api(),review=vi.fn();let first!:(value:SceneSensorContext)=>void,second!:(value:SceneSensorContext)=>void;
    gateway.sceneSensorContext=vi.fn().mockImplementationOnce(()=>new Promise(resolve=>{first=resolve;}))
      .mockImplementationOnce(()=>new Promise(resolve=>{second=resolve;}));
    const shown=render(<SceneSensorFeedback api={gateway} revision={context.current_scene_revision} stateSha={context.current_state_sha256} enabled review={review}/>);
    await waitFor(()=>expect(gateway.sceneSensorContext).toHaveBeenCalledTimes(1));
    const revision=change==='revision'?'7'.repeat(64):context.current_scene_revision;
    const sha=change==='state-sha'?'8'.repeat(64):context.current_state_sha256;
    if(change==='api-context')(gateway as unknown as {context:string}).context='sensor-b';
    shown.rerender(<SceneSensorFeedback api={gateway} revision={revision} stateSha={sha} enabled={change!=='disabled'} review={review}/>);
    await act(async()=>{await Promise.resolve();});
    if(change!=='disabled')await waitFor(()=>expect(gateway.sceneSensorContext).toHaveBeenCalledTimes(2));
    await act(async()=>first(context));
    fireEvent.change(screen.getByLabelText('Saved sensor map'),{target:{value:map.map_id}});
    expect(screen.getByRole('button',{name:'Review saved sensor feedback'})).toHaveProperty('disabled',true);
    expect(review).not.toHaveBeenCalled();
    if(change!=='disabled'){
      await act(async()=>second({...context,current_scene_revision:revision,current_state_sha256:sha}));
      expect(screen.getByRole('button',{name:'Review saved sensor feedback'})).toHaveProperty('disabled',false);
    }else expect(gateway.sceneSensorContext).toHaveBeenCalledTimes(1);
  });
  it('empty evidence explains stationary health versus multi-view fit without starting anything',async()=>{
    const gateway=api(),review=vi.fn();gateway.automaticMaps=vi.fn().mockResolvedValue({maps:[]});
    render(<SceneSensorFeedback api={gateway} revision={context.current_scene_revision} stateSha={context.current_state_sha256} enabled review={review}/>);
    await screen.findByRole('status',{name:'Sensor preparation next steps'});
    expect(screen.getByText(/stationary scan alone cannot/)).toBeTruthy();expect(review).not.toHaveBeenCalled();
    expect((screen.getByRole('button',{name:'Review saved sensor feedback'}) as HTMLButtonElement).disabled).toBe(true);
    expect(gateway.automaticMaps).toHaveBeenCalledTimes(1);expect(gateway.sceneSensorSurveys).toHaveBeenCalledTimes(1);
    expect(gateway.sceneSensorContext).not.toHaveBeenCalled();
  });
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
    expect(gateway.sceneSensorContext).not.toHaveBeenCalled();expect(gateway.automaticMaps).not.toHaveBeenCalled();
    expect((screen.getByLabelText('Saved sensor map') as HTMLSelectElement).disabled).toBe(true);
    shown.rerender(<SceneSensorFeedback api={gateway} revision={context.current_scene_revision} stateSha={'0'.repeat(64)} enabled review={review}/>);
    await waitFor(()=>expect(gateway.sceneSensorContext).toHaveBeenCalledTimes(1));
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
