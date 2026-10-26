// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {act,fireEvent,render,screen,within} from '@testing-library/react';
import {describe,expect,it,vi} from 'vitest';
import {RobotFieldTests,fieldTestCases} from './RobotFieldTests';
import {RobotFleet} from './RobotFleet';
import type {TwinPulseApi} from './api';
import type {FieldSetupConfig,RobotFieldState,RobotFleetAction,RobotFleetRobot,RobotFleetState} from './robot-fleet-types';

// Supplementary UI contract fixtures, never measured calibration or hardware PASS.
const config:FieldSetupConfig={schema:'supervised-field-test-1.0',robot_id:'test-robot',binding_sha256:'test-binding',footprint_radius_m:.13,
  sensor_x_m:.01,sensor_y_m:.02,sensor_yaw_rad:.03,angle_sign:-1,wheel_metres_per_tick:.000051,wheel_separation_m:.17,provenance:'operator_reviewed',axes_reviewed:true};
const field=():RobotFieldState=>({config,config_sha256:'fixture-config-sha',mode:'SUPERVISED_FIELD_TEST',armed:false,remaining_s:0,
  blockers:['STOP_RECEIPT_REQUIRED','NATIVE_COVERAGE_INCOMPLETE'],stop_receipt:null,tracking:null,active_trial:null,trials:[]});
const robot=():RobotFleetRobot=>({robot_id:'test-robot',label:'Fixture physical',kind:'physical',connection_state:'CONNECTED',connection_epoch:'connection-a',motion_epoch:'motion-a',
  control_state:'UNPREPARED',lidar_state:'OFF',recording_state:'RECORDING',operation_id:'operation-a',reason:null,battery:{voltage_v:null,percent:null,source:'unknown',age_ms:null},
  pose:null,telemetry_age_ms:10,telemetry_sequence:1,live_heartbeat:true,capabilities:{drive:false,lidar:false},scan:null,
  setup:{runtime_state:'UNPREPARED',blockers:[],profile:null,qualification:null,binding_sha256:'test-binding'},field:field()});
function setup(row=robot()){
  const onAction=vi.fn(),onOpenLogs=vi.fn(),props={robot:row,available:true,busy:false,onAction,onOpenLogs};
  return {...render(<RobotFieldTests {...props}/>),props,onAction,onOpenLogs};
}
const checkbox=(name:RegExp)=>screen.getByRole('checkbox',{name});
const button=(name:string)=>screen.getByRole('button',{name}) as HTMLButtonElement;
const axes=()=>fireEvent.click(checkbox(/I reviewed robot model applicability/));
const confirm=()=>fireEvent.click(checkbox(/I reviewed the selected trial scope/));
const supervise=()=>fireEvent.click(checkbox(/I am supervising, charging is unplugged/));

describe('supervised field tests (supplementary UI contract only)',()=>{
  it('separates collection window, strict ring quality, archive integrity and power-on test entry',()=>{
    const row=robot();row.field!.native_observation={frame_sequence:11,stream_id:'stream',raw_sha256:'a'.repeat(64),raw_ring_complete:false,
      unknown_bytes:11,receipt_age_s:.11,policy:'SUPERVISED_LAST_COMPLETE_ORIGINAL_AGE_AND_NEWER_STOP_VETO_V1',directional_clearance:'CHECKED_PER_OUTPUT_NOT_BY_THIS_STATUS'};
    row.field!.trials=[{trial_id:'observed-window',case:'stationary',status:'INCONCLUSIVE',reason:'NATIVE_COLLECTION_CONTAINS_INVALID_FRAMES',started_s:1,
      result:{collection_complete:true,strict_ring_quality:'INCOMPLETE_RINGS',raw_archive_integrity:'PENDING_NATIVE_FINAL_MANIFEST',motion_authority:'NOT_GRANTED_BY_COLLECTION'}}];
    const {onAction}=setup(row);
    expect(screen.getByRole('region',{name:'Power-on test sequence'})).toBeTruthy();
    expect(screen.getByText(/Bootstrap stop does not require a prior stop receipt/)).toBeTruthy();
    expect(screen.getByText(/incomplete — original warning retained.*unknown 11 bytes/)).toBeTruthy();
    expect(screen.getByText(/Collection window complete · strict ring quality INCOMPLETE_RINGS/)).toBeTruthy();
    expect(screen.getByText(/Verify raw archive integrity separately in the final sensor manifest/)).toBeTruthy();
    expect(onAction).not.toHaveBeenCalled();
  });
  it('shows current input timing and confirmed output readback, never legacy constants or an unconfirmed registered output',()=>{
    const row=robot();row.timing_values={input_ttl_ms:350} as RobotFleetRobot['timing_values'];
    const view=setup(row);
    expect(screen.getByLabelText('Current field timing').textContent).toBe('Input expiry 350 ms · applied output timeout not confirmed ms.');
    row.output_timing={output_timeout_ms:450} as RobotFleetRobot['output_timing'];
    view.rerender(<RobotFieldTests {...view.props} robot={{...row}}/>);
    expect(screen.getByLabelText('Current field timing').textContent).toBe('Input expiry 350 ms · applied output timeout 450 ms.');
    expect(screen.queryByText(/Input expiry 250 ms/)).toBeNull();
  });
  it('saves editable reference setup offline only after explicit axes/model review, with fixed identities and no arm/connect',()=>{
    const off={...robot(),connection_state:'DISCONNECTED' as const,connection_epoch:null,live_heartbeat:false,field:undefined};
    const {onAction}=setup(off);
    expect(screen.getByText(/Editable Burger reference values, not measurements/)).toBeTruthy();
    expect((screen.getByLabelText('Wheel metres per tick') as HTMLInputElement).value).toBe(String(2*Math.PI*.033/4096));
    expect(button('Save supervised setup').disabled).toBe(true);expect(onAction).not.toHaveBeenCalled();
    axes();fireEvent.change(screen.getByLabelText('Sensor X (m)'),{target:{value:'.04'}});
    expect((checkbox(/I reviewed robot model applicability/) as HTMLInputElement).checked).toBe(false);
    axes();fireEvent.submit(screen.getByRole('form',{name:'Supervised field setup'}));
    expect(onAction).toHaveBeenCalledExactlyOnceWith('field_setup',{config:{schema:'supervised-field-test-1.0',robot_id:'test-robot',binding_sha256:'test-binding',
      footprint_radius_m:.12,sensor_x_m:.04,sensor_y_m:0,sensor_yaw_rad:0,angle_sign:1,wheel_metres_per_tick:2*Math.PI*.033/4096,wheel_separation_m:.16,provenance:'reference',axes_reviewed:true}});
    expect((checkbox(/I reviewed robot model applicability/) as HTMLInputElement).checked).toBe(false);
    expect(button('Arm supervised field session').disabled).toBe(true);
  });
  it('restores saved data without checking axes or supervision, automatic POST, or fabricated measured provenance',()=>{
    const {onAction}=setup();
    expect((screen.getByLabelText('Sensor yaw (rad)') as HTMLInputElement).value).toBe('0.03');
    expect((screen.getByLabelText('Setup provenance') as HTMLSelectElement).value).toBe('operator_reviewed');
    expect((checkbox(/I reviewed robot model applicability/) as HTMLInputElement).checked).toBe(false);
    expect((checkbox(/I am supervising, charging is unplugged/) as HTMLInputElement).checked).toBe(false);
    expect(onAction).not.toHaveBeenCalled();
  });
  it('reflects offline saved-config updates even without a digest and never overwrites unsaved edits on identical polling',()=>{
    const row=robot();delete (row.field as Partial<RobotFieldState>).config_sha256;
    const {props,rerender,onAction}=setup(row);
    fireEvent.change(screen.getByLabelText('Sensor X (m)'),{target:{value:'.05'}});axes();
    rerender(<RobotFieldTests {...props} robot={{...row,field:{...row.field!,config:{...config}}}}/>);
    expect((screen.getByLabelText('Sensor X (m)') as HTMLInputElement).value).toBe('.05');
    expect((checkbox(/I reviewed robot model applicability/) as HTMLInputElement).checked).toBe(true);
    rerender(<RobotFieldTests {...props} robot={{...row,field:{...row.field!,config:{...config,sensor_x_m:.06}}}}/>);
    expect((screen.getByLabelText('Sensor X (m)') as HTMLInputElement).value).toBe('0.06');
    expect((checkbox(/I reviewed robot model applicability/) as HTMLInputElement).checked).toBe(false);
    expect(onAction).not.toHaveBeenCalled();
  });
  it.each([
    ['Outer footprint radius (m)','0.079'],['Sensor X (m)','0.61'],['Sensor Y (m)','-0.61'],['Sensor yaw (rad)','3.15'],
    ['Wheel metres per tick','0'],['Wheel separation (m)','0.801'],['Wheel metres per tick',''],['Wheel separation (m)','1e309'],
  ])('rejects missing/nonfinite/out-of-range %s (%s) without any action', (label,value)=>{
    const {onAction}=setup();fireEvent.change(screen.getByLabelText(label),{target:{value}});axes();
    // Direct submit additionally exercises validation independent of browser validation.
    fireEvent.submit(screen.getByRole('form',{name:'Supervised field setup'}));
    expect(screen.getByRole('alert').textContent).toContain('must be finite and within');expect(onAction).not.toHaveBeenCalled();
  });
  it.each(['busy','unavailable','missing-binding'] as const)('does not save while %s',condition=>{
    const row=robot();if(condition==='missing-binding'){row.setup=undefined;row.field=undefined;}
    const {props,rerender,onAction}=setup(row);
    rerender(<RobotFieldTests {...props} busy={condition==='busy'} available={condition!=='unavailable'}/>);
    axes();fireEvent.submit(screen.getByRole('form',{name:'Supervised field setup'}));
    expect(button('Save supervised setup').disabled).toBe(true);expect(onAction).not.toHaveBeenCalled();
  });
  it('arms exactly once after explicit supervision and consumes consent; reconnect and config changes require a fresh review',()=>{
    const {props,rerender,onAction}=setup();expect(button('Arm supervised field session').disabled).toBe(true);
    supervise();fireEvent.click(button('Arm supervised field session'));
    expect(onAction).toHaveBeenCalledExactlyOnceWith('field_arm',{confirmed:true});
    expect(button('Arm supervised field session').disabled).toBe(true);
    supervise();confirm();rerender(<RobotFieldTests {...props} robot={{...props.robot,connection_epoch:'connection-b'}}/>);
    expect((checkbox(/I am supervising, charging is unplugged/) as HTMLInputElement).checked).toBe(false);
    expect((checkbox(/I reviewed the selected trial scope/) as HTMLInputElement).checked).toBe(false);
    supervise();rerender(<RobotFieldTests {...props} robot={{...props.robot,field:{...field(),config_sha256:'changed'}}}/>);
    expect(button('Arm supervised field session').disabled).toBe(true);
  });
  it('revokes local pending consent on Stop authority/motion changes without automatically re-arming',()=>{
    const row=robot();row.field!.armed=true;row.field!.remaining_s=600;
    const {props,rerender,onAction}=setup(row);supervise();confirm();
    rerender(<RobotFieldTests {...props} robot={{...row,motion_epoch:'stop-epoch',field:{...row.field!,armed:false,remaining_s:0}}}/>);
    expect((checkbox(/I am supervising, charging is unplugged/) as HTMLInputElement).checked).toBe(false);
    expect((checkbox(/I reviewed the selected trial scope/) as HTMLInputElement).checked).toBe(false);
    expect(screen.getByText(/Supervision not armed · remaining 0 s/)).toBeTruthy();expect(onAction).not.toHaveBeenCalled();
  });
  it.each(fieldTestCases)('requests exactly the bounded $id contract, even without protected drive capability, never chains/retries',test=>{
    const {onAction}=setup();expect(button(`Run ${test.label}`).disabled).toBe(true);
    confirm();fireEvent.click(button(`Run ${test.label}`));
    expect(onAction).toHaveBeenCalledExactlyOnceWith('field_test',{case:test.id,confirmed:true});
    expect(button(`Run ${test.label}`).disabled).toBe(true);
  });
  it('shows the complete 11-case list and concrete prerequisites while offline, retaining setup but disabling live actions',()=>{
    const row=robot();row.live_heartbeat=false;row.connection_state='DISCONNECTED';const {onAction}=setup(row);
    const list=screen.getByRole('list',{name:'Available field test cases'});
    expect(within(list).getAllByRole('button')).toHaveLength(11);confirm();supervise();
    expect(within(list).getAllByRole('button').every(item=>(item as HTMLButtonElement).disabled)).toBe(true);
    expect(screen.getByText('STOP_RECEIPT_REQUIRED')).toBeTruthy();expect(screen.getByText('NATIVE_COVERAGE_INCOMPLETE')).toBeTruthy();
    expect(screen.getByText(/fresh authenticated heartbeat/)).toBeTruthy();expect(button('Arm supervised field session').disabled).toBe(true);
    expect(screen.getByText(/not a real Wi-Fi\/network outage test/)).toBeTruthy();expect(onAction).not.toHaveBeenCalled();
  });
  it('keeps a running trial visible and rejects concurrent test/arm clicks without affecting the global Stop path',()=>{
    const row=robot();row.field!.active_trial={trial_id:'trial-running',case:'forward',status:'RUNNING',reason:'collecting',started_s:1};
    const {onAction}=setup(row);confirm();supervise();
    expect(button('Run Forward').disabled).toBe(true);expect(button('Arm supervised field session').disabled).toBe(true);
    expect(screen.getByText(/Active trial trial-running.*RUNNING/)).toBeTruthy();expect(onAction).not.toHaveBeenCalled();
  });
  it('shows scope-limited PASS, UNKNOWN tracking and unqualified beam/clearance/body evidence without manufacturing a safety claim',()=>{
    const row=robot();row.field!.trials=[{trial_id:'trial-a',case:'stationary',status:'PASS',reason:'fixture zero-motion collection',started_s:1,ended_s:2,result:{scope:'zero-motion only'}}];
    setup(row);expect(screen.getByText('stationary · PASS')).toBeTruthy();
    expect(screen.getByText(/PASS applies only to the recorded trial scope/)).toBeTruthy();
    expect(screen.getByText(/UNKNOWN · accuracy UNQUALIFIED/)).toBeTruthy();expect(screen.getByText(/Unknown beam acquisition time remains unqualified/)).toBeTruthy();
    expect(screen.getByText(/Wheel stall is not independent chassis\/slip proof/)).toBeTruthy();
    expect(screen.getByText(/not an industrial safety guarantee/)).toBeTruthy();expect(screen.getByText(/Receipt threshold is not physical stopping distance/)).toBeTruthy();
  });
  it.each(['stopped','not_stopped','moved','not_moved','inconclusive'])('binds human %s review to an actual trial and omits unmeasured clearance',observed=>{
    const row=robot();row.field!.trials=[{trial_id:'trial-a',case:'proximity',status:'INCONCLUSIVE',reason:'needs observation',started_s:1}];
    const {onAction}=setup(row);expect(button('Save trial observation').disabled).toBe(true);
    fireEvent.change(screen.getByLabelText('Actual trial to review'),{target:{value:'trial-a'}});
    fireEvent.change(screen.getByLabelText('Human observation'),{target:{value:observed}});
    fireEvent.submit(screen.getByRole('form',{name:'Review actual field trial'}));
    expect(onAction).toHaveBeenCalledExactlyOnceWith('field_review',{trial_id:'trial-a',observed});
  });
  it('preserves measured outer-body clearance as operator input and refuses invalid clearance',()=>{
    const row=robot();row.field!.trials=[{trial_id:'trial-a',case:'proximity',status:'INCONCLUSIVE',reason:null,started_s:1}];
    const {onAction}=setup(row);fireEvent.change(screen.getByLabelText('Actual trial to review'),{target:{value:'trial-a'}});
    fireEvent.change(screen.getByLabelText('Human observation'),{target:{value:'stopped'}});
    fireEvent.change(screen.getByLabelText('Measured outer-body clearance (m, optional)'),{target:{value:'-1'}});
    fireEvent.submit(screen.getByRole('form',{name:'Review actual field trial'}));expect(onAction).not.toHaveBeenCalled();
    expect(screen.getByRole('alert').textContent).toContain('finite nonnegative');
    fireEvent.change(screen.getByLabelText('Measured outer-body clearance (m, optional)'),{target:{value:'.11'}});
    fireEvent.submit(screen.getByRole('form',{name:'Review actual field trial'}));
    expect(onAction).toHaveBeenCalledExactlyOnceWith('field_review',{trial_id:'trial-a',observed:'stopped',clearance_m:.11});
  });
  it('does not review an old trial removed from current server state or synthesize a trial ID',()=>{
    const row=robot();row.field!.trials=[{trial_id:'trial-a',case:'stationary',status:'PASS',reason:null,started_s:1}];
    const {onAction,props,rerender}=setup(row);fireEvent.change(screen.getByLabelText('Actual trial to review'),{target:{value:'trial-a'}});
    fireEvent.change(screen.getByLabelText('Human observation'),{target:{value:'stopped'}});
    rerender(<RobotFieldTests {...props} robot={{...row,field:field()}}/>);
    fireEvent.submit(screen.getByRole('form',{name:'Review actual field trial'}));expect(onAction).not.toHaveBeenCalled();
  });
  it('opens the actual operation log and labels field members as streamed raw_source, never invented download URLs',()=>{
    const {onOpenLogs}=setup();fireEvent.click(button('Open field operation logs'));expect(onOpenLogs).toHaveBeenCalledOnce();
    expect(screen.getByText(/field-config.json, field-trials.json, field-stop.json, field-tracking.json/).textContent).toContain('not separate file-download URLs');
  });
});

describe('RobotFleet field integration (supplementary UI contract only)',()=>{
  function integration(row=robot(),reject=false){
    const state:RobotFleetState={schema_version:'robot-fleet-1.0',revision:1,focused_robot_id:row.robot_id,robots:[row],last_command:null,capabilities:{physical:true,sim:true},policy:{linear_m_s:.05,angular_rad_s:.3,input_expiry_ms:250}};
    const action=vi.fn(async(_body:RobotFleetAction)=>{if(reject)throw new Error('FIELD_STOP_RECEIPT_REQUIRED');return state;}),api={context:'context',robotFleetAction:action} as unknown as TwinPulseApi;
    return {action,...render(<RobotFleet api={api} state={state} selectedId={row.robot_id} onChange={vi.fn()} onSelect={vi.fn()}/>)};
  }
  it('uses the existing request/robot/connection/motion envelope; keeps strict JSON collapsed and the existing Stop path',async()=>{
    const {action}=integration();const advanced=screen.getByLabelText('Measured profile import and review') as HTMLDetailsElement;
    expect(advanced.open).toBe(false);supervise();await act(async()=>{fireEvent.click(button('Arm supervised field session'));});
    expect(action.mock.calls[0][0]).toMatchObject({action:'field_arm',robot_id:'test-robot',connection_epoch:'connection-a',motion_epoch:'motion-a',payload:{confirmed:true}});
    expect(action.mock.calls[0][0].request_id).toEqual(expect.any(String));
    await act(async()=>{fireEvent.click(button('Stop'));});expect(action.mock.calls.at(-1)?.[0]).toMatchObject({action:'stop',robot_id:'test-robot'});
  });
  it('shows backend per-case rejection without auto-resend or relaxing protected-drive capability',async()=>{
    const {action}=integration(robot(),true);fireEvent.click(checkbox(/I reviewed the Bootstrap stop trial scope/));await act(async()=>{fireEvent.click(button('Run Bootstrap stop'));});  // the Bootstrap trial lives in the session gate (PHYS09)
    expect(screen.getByRole('alert').textContent).toBe('FIELD_STOP_RECEIPT_REQUIRED');expect(action).toHaveBeenCalledOnce();
    expect(button('Hold forward').disabled).toBe(true);expect(button('Run Bootstrap stop').disabled).toBe(true);
  });
  it('does not offer physical field tests on a SIM robot',()=>{
    integration({...robot(),kind:'sim'});expect(screen.queryByRole('region',{name:'Supervised field tests'})).toBeNull();
  });
  it('keeps Stop outside a pending field API action and never queues another trial',async()=>{
    const row=robot(),state:RobotFleetState={schema_version:'robot-fleet-1.0',revision:1,focused_robot_id:row.robot_id,robots:[row],last_command:null,
      capabilities:{physical:true,sim:true},policy:{linear_m_s:.05,angular_rad_s:.3,input_expiry_ms:250}};
    const action=vi.fn((body:RobotFleetAction)=>body.action==='field_test'?new Promise<RobotFleetState>(()=>{}):Promise.resolve(state));
    const api={context:'context',robotFleetAction:action} as unknown as TwinPulseApi;
    render(<RobotFleet api={api} state={state} selectedId={row.robot_id} onChange={vi.fn()} onSelect={vi.fn()}/>);
    confirm();fireEvent.click(button('Run Stationary collection'));
    expect(button('Run Forward').disabled).toBe(true);
    await act(async()=>{fireEvent.click(button('Stop'));});
    expect(action.mock.calls.map(([body])=>body.action)).toEqual(['field_test','stop']);
  });
});
