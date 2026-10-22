// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {act,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {TwinPulseApi} from './api';
import {RobotFleet} from './RobotFleet';
import {TwinViewport,layoutRobotBadges,pickRobotAnchor,type RobotBadgePlacement} from './TwinViewport';
import type {ViewportState} from './viewport-types';
import {fleetBatteryLabel,fleetBatteryPolicyMessage,fleetRobotFresh,type RobotTwinContext,type RobotFleetAction,type RobotFleetOperation,type RobotFleetRobot,type RobotFleetState} from './robot-fleet-types';

const robot=(id='a'):RobotFleetRobot=>({robot_id:id,label:`Robot ${id}`,kind:'sim',connection_state:'CONNECTED',connection_epoch:`connection-${id}`,motion_epoch:`motion-${id}`,
  control_state:'READY',lidar_state:'STREAMING',recording_state:'RECORDING',operation_id:`operation-${id}`,reason:null,
  battery:{voltage_v:12,percent:80,source:'simulated',age_ms:50},pose:null,telemetry_age_ms:50,telemetry_sequence:1,capabilities:{drive:true,lidar:true},scan:null});
const fleet=(robots=[robot(),robot('b')]):RobotFleetState=>({schema_version:'robot-fleet-1.0',revision:2,focused_robot_id:'a',robots,last_command:null,
  capabilities:{sim:true,physical:false},policy:{linear_m_s:.05,angular_rad_s:.3,input_expiry_ms:250}});
function setup(state=fleet(),custom?:(body:RobotFleetAction)=>Promise<RobotFleetState>){
  const action=vi.fn(custom??(async()=>state));
  const operation=vi.fn(async(_id:string):Promise<RobotFleetOperation>=>({schema_version:'robot-operation-1.0',operation_id:'operation-a',robot_id:'a',project_id:'project',events:[{kind:'stop',reason:'release'}],manifest:{complete:false}}));
  const api={context:'context',robotFleetAction:action,robotFleetOperation:operation} as unknown as TwinPulseApi;
  const props={api,state,selectedId:'a',onChange:vi.fn(),onSelect:vi.fn(),available:true};
  return {action,operation,props,...render(<RobotFleet {...props}/>)};
}
afterEach(()=>{vi.useRealTimers();vi.unstubAllGlobals();});

describe('robot fleet controls (supplementary UI tests)',()=>{
  it('shows one short preparation phase while retaining the original reason in help',()=>{
    const r={...robot(),kind:'physical' as const,reason:'OLD_STOP_REASON',setup:{runtime_state:'PREPARING',blockers:['BUILDING_OUTPUT_GUARD'],profile:null,qualification:null,maintenance_phase:'BUILDING_OUTPUT_GUARD'}};
    setup(fleet([r]));
    expect(screen.getByText('Building output guard…')).toBeTruthy();
    expect(screen.queryByText('OLD_STOP_REASON')).toBeNull();
    expect(screen.getByText('Building output guard…').getAttribute('title')).toContain('OLD_STOP_REASON');
  });
  it('distinguishes local dispatch from real arrival and shows a later main-chat receipt',async()=>{
    const state=fleet();const {props,rerender,action}=setup(state);
    fireEvent.change(screen.getByLabelText('Robot command'),{target:{value:'Go to the nearest bed'}});
    fireEvent.click(screen.getByRole('button',{name:'Send command'}));
    await waitFor(()=>expect(screen.getByLabelText('Robot command progress').textContent).toContain('ACCEPTED'));
    expect((screen.getByLabelText('Robot command') as HTMLInputElement).value).toBe('');
    expect(screen.getByLabelText('Robot command').getAttribute('placeholder')).toBe('Type a new command…');
    expect(screen.getByLabelText('Robot command progress').textContent).toContain('Go to the nearest bed');
    expect(screen.getByLabelText('Robot command progress').textContent).not.toContain('ARRIVED');
    const id=action.mock.calls.find(([b])=>b.action==='command')![0].request_id;
    const current=fleet([{...robot(),command:{request_id:id,text:'Go to the nearest bed',kind:'navigate',state:'ARRIVED',target_label:'bed bed1'}}]);
    rerender(<RobotFleet {...props} state={current}/>);
    expect(screen.getByLabelText('Robot command progress').textContent).toContain('ARRIVED');
    const next=fleet([{...robot(),command:{request_id:'main-chat-new',text:'Go to the nearest chair',kind:'navigate',state:'PLANNING',target_kind:'chair'}}]);
    rerender(<RobotFleet {...props} state={next}/>);
    expect(screen.getByLabelText('Robot command progress').getAttribute('title')).toContain('main-chat-new');
    expect(screen.getByText('main-chat-new',{selector:'code'})).toBeTruthy();
    expect(screen.getByLabelText('Robot command progress').textContent).toContain('PLANNING');
  });
  it('keeps the draft until ACK and preserves it on a rejected command',async()=>{
    let reject!:(error:Error)=>void;
    setup(fleet(),()=>new Promise((_,no)=>{reject=no;}));
    const input=screen.getByLabelText('Robot command') as HTMLInputElement;
    fireEvent.change(input,{target:{value:'Go to the nearest bed'}});
    fireEvent.submit(input.closest('form')!);
    expect(input.value).toBe('Go to the nearest bed');
    expect(screen.getByLabelText('Robot command progress').textContent).toContain('SENDING');
    await act(async()=>{reject(new Error('Destination unavailable'));});
    expect(input.value).toBe('Go to the nearest bed');
    expect(screen.getByLabelText('Robot command progress').textContent).toContain('FAILED');
  });
  it.each(['Go to the nearest chair','Go to the nearest bed'])('does not erase a newer draft on late ACK: %s',async value=>{
    let resolve!:(next:RobotFleetState)=>void;
    setup(fleet(),()=>new Promise(yes=>{resolve=yes;}));
    const input=screen.getByLabelText('Robot command') as HTMLInputElement;
    fireEvent.change(input,{target:{value:'Go to the nearest bed'}});
    fireEvent.submit(input.closest('form')!);
    fireEvent.change(input,{target:{value:''}});
    fireEvent.change(input,{target:{value}});
    await act(async()=>{resolve(fleet());});
    expect(input.value).toBe(value);
    expect(screen.getByLabelText('Robot command progress').textContent).toContain('ACCEPTED');
  });
  it('does not clear another selected robot draft on late ACK',async()=>{
    let resolve!:(next:RobotFleetState)=>void;
    const {props,rerender}=setup(fleet(),()=>new Promise(yes=>{resolve=yes;}));
    const input=screen.getByLabelText('Robot command') as HTMLInputElement;
    fireEvent.change(input,{target:{value:'Go to the nearest bed'}});
    fireEvent.submit(input.closest('form')!);
    rerender(<RobotFleet {...props} selectedId="b"/>);
    fireEvent.change(screen.getByLabelText('Robot command'),{target:{value:'Go to the nearest chair'}});
    await act(async()=>{resolve(fleet());});
    expect((screen.getByLabelText('Robot command') as HTMLInputElement).value).toBe('Go to the nearest chair');
  });
  it('keeps the compact primary pad and Stop before collapsed setup and opens logs explicitly',async()=>{
    const {action,container}=setup();
    const dock=screen.getByLabelText('Control Robot a'),details=container.querySelector('.robot-fleet-diagnostics')!;
    expect(details.hasAttribute('open')).toBe(false);
    expect(dock.querySelectorAll('.robot-fleet-pad')).toHaveLength(1);
    expect(dock.querySelector('.robot-fleet-control-primary')!.compareDocumentPosition(details)&Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(within(dock).getByRole('button',{name:'Stop'})).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'Operation logs'}));
    await screen.findByRole('button',{name:'Download operation JSON'});
    expect(details.hasAttribute('open')).toBe(true);
    expect(action).not.toHaveBeenCalled();
  });
  it('releases one hold on a dock layout change without remounting or replaying it',async()=>{
    vi.useFakeTimers();const {action,props,rerender,container}=setup();
    const pad=screen.getByRole('group',{name:'Hold to drive'});
    fireEvent.change(screen.getByLabelText('Robot command'),{target:{value:'turn left 90 degrees'}});
    fireEvent.keyDown(pad,{key:'ArrowUp'});
    expect(action.mock.calls.filter(([body])=>body.action==='drive')).toHaveLength(1);
    rerender(<RobotFleet {...props} layoutVersion="control-view:33"/>);
    expect(action.mock.calls.filter(([body])=>body.action==='stop')).toHaveLength(1);
    expect(screen.getByRole('group',{name:'Hold to drive'})).toBe(pad);
    expect(container.querySelectorAll('.robot-fleet-pad')).toHaveLength(1);
    expect((screen.getByLabelText('Robot command') as HTMLInputElement).value).toBe('turn left 90 degrees');
    await act(async()=>{await vi.advanceTimersByTimeAsync(600);});
    expect(action.mock.calls.filter(([body])=>body.action==='drive')).toHaveLength(1);
    expect(action.mock.calls.some(([body])=>body.action==='disconnect')).toBe(false);
    fireEvent.keyDown(pad,{key:'ArrowRight'});
    expect(action.mock.calls.filter(([body])=>body.action==='drive')).toHaveLength(2);
  });
  it('stops on a window resize and waits for a new user gesture after resizing',async()=>{
    vi.useFakeTimers();const {action}=setup();
    fireEvent.keyDown(screen.getByRole('group',{name:'Hold to drive'}),{key:'ArrowLeft'});
    fireEvent.resize(window);
    expect(action.mock.calls.at(-1)?.[0].action).toBe('stop');
    await act(async()=>{await vi.advanceTimersByTimeAsync(500);});
    expect(action.mock.calls.filter(([body])=>body.action==='drive')).toHaveLength(1);
    expect(action.mock.calls.some(([body])=>body.action==='connect'||body.action==='disconnect')).toBe(false);
  });
  it('keeps Stop independent while logs are pending and diagnostics are expanded',async()=>{
    const {action,operation}=setup();operation.mockImplementationOnce(()=>new Promise(()=>{}));
    fireEvent.click(screen.getByRole('button',{name:'Operation logs'}));
    fireEvent.click(screen.getByRole('button',{name:'Stop'}));
    expect(action.mock.calls.at(-1)?.[0]).toMatchObject({action:'stop',robot_id:'a'});
    expect((screen.getByRole('button',{name:'Stop'}) as HTMLButtonElement).disabled).toBe(false);
  });
  it('does not imply that a physical paused controller awaits or has an Isaac stop receipt',()=>{
    const physical:RobotFleetRobot={...robot(),kind:'physical',live_heartbeat:true,
      control_state:'PAUSED',applied_motion_epoch:'motion-a'};
    setup(fleet([physical]));
    expect(screen.getByText('Physical movement paused · current motor stop/readback is not established by an Isaac engine ACK.')).toBeTruthy();
    expect(screen.queryByText('Engine stop confirmed')).toBeNull();
    expect(screen.queryByText('Stop requested · waiting for engine confirmation')).toBeNull();
  });
  it('shows source-header age separately from a fresh sensor callback',()=>{
    const physical:RobotFleetRobot={...robot(),kind:'physical',live_heartbeat:true,
      telemetry_diagnostic:{reason:'SENSOR_SOURCE_AGE',source_age_s:.223906317,
        sensor_receipt_age_s:.000876351,guard_receipt_age_s:.020916754}};
    setup(fleet([physical]));
    const row=screen.getByText('ROS receipt diagnosis').parentElement;
    expect(row?.textContent).toContain('SENSOR_SOURCE_AGE');
    expect(row?.textContent).toContain('source 224 ms');
    expect(row?.textContent).toContain('sensor 1 ms');
    expect(row?.textContent).toContain('guard 21 ms');
  });
  it('cannot download the old snapshot while the same operation refresh is pending',async()=>{
    const {operation}=setup();
    fireEvent.click(screen.getByRole('button',{name:'Operation logs'}));
    const button=await screen.findByRole('button',{name:'Download operation JSON'});
    await waitFor(()=>expect((button as HTMLButtonElement).disabled).toBe(false));
    let finish!:(value:RobotFleetOperation)=>void;
    operation.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}));
    fireEvent.click(screen.getByRole('button',{name:'Operation logs'}));
    expect((button as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText('Refreshing operation log; download waits for the response.')).toBeTruthy();
    await act(async()=>finish({schema_version:'robot-operation-1.0',operation_id:'operation-a',robot_id:'a',project_id:'project',
      events:[{kind:'stop_all_request',request_id:'actual-new-stop'}],manifest:{complete:false}}));
    await waitFor(()=>expect((button as HTMLButtonElement).disabled).toBe(false));
    expect(screen.getByLabelText('Recent operation events').textContent).toContain('stop_all_request');
  });
  it('keeps cold trial failure IDs visible without restoring current qualification',async()=>{
    const {operation}=setup();operation.mockResolvedValue({schema_version:'robot-operation-1.0',operation_id:'operation-a',robot_id:'a',project_id:'project',
      events:[{kind:'heartbeat',data:{field:{trials:[{trial_id:'a'.repeat(32),case:'stationary',status:'INCONCLUSIVE',reason:'FIELD_NATIVE_RECEIPT_STALE_OR_BACKLOG',frames:0,context:{operation_id:'operation-a'}},
        {trial_id:'b'.repeat(32),case:'forward',status:'PASS',context:{operation_id:'other'}}]}}}],manifest:{historical:true,worker_sources:null}});
    fireEvent.click(screen.getByRole('button',{name:'Operation logs'}));
    const summary=await screen.findByLabelText('Operation summary');
    await waitFor(()=>expect(summary.textContent).toContain('Historical trial '+'a'.repeat(32)));
    expect(summary.textContent).toContain('INCONCLUSIVE · FIELD_NATIVE_RECEIPT_STALE_OR_BACKLOG · frames 0 · not current qualification');
    expect(summary.textContent).not.toContain('Historical trial '+'b'.repeat(32));
    expect(summary.textContent).toContain('Unknown · not recorded');
  });
  it('pins the original failed check above bounded recent observations and later clean cleanup',async()=>{
    const fault={reason:'TELEMETRY_STALE',telemetry:{reason:'GUARD_RECEIPT_STALE',checked_monotonic_s:4.9,guard_receipt_age_s:.212418531}};
    const {operation}=setup();operation.mockResolvedValue({schema_version:'robot-operation-1.0',operation_id:'operation-a',robot_id:'a',project_id:'project',
      events:[{kind:'heartbeat',operation_id:'operation-a',sequence:10,robot_monotonic_s:5,data:{last_control_fault:fault}},
        ...Array.from({length:70},(_,sequence)=>({kind:'heartbeat',operation_id:'operation-a',sequence:11+sequence,data:{last_control_fault:fault,telemetry_diagnostic:{reason:null,guard_receipt_age_s:.002}}})),
        {kind:'cleanup',operation_id:'operation-a',data:{confirmed:true}},
        {kind:'heartbeat',operation_id:'another-operation',data:{last_control_fault:{reason:'WRONG_OPERATION',telemetry:{reason:'DO_NOT_SHOW'}}}}],
      manifest:{historical:true,complete:true}});
    fireEvent.click(screen.getByRole('button',{name:'Operation logs'}));
    const summary=await screen.findByLabelText('Operation summary');
    await waitFor(()=>expect(summary.textContent).toContain('original failed control reason'));
    expect(summary.textContent).toContain('GUARD_RECEIPT_STALE');
    expect(summary.textContent).toContain('212.42 ms');
    expect(screen.getByText('Fault-carrying report sequence').parentElement?.textContent).toContain('80');
    expect(screen.getByText('Original failed check robot s').parentElement?.textContent).toContain('4.9');
    expect(summary.textContent).not.toContain('DO_NOT_SHOW');
  });
  it('uses the selected custom mapping or explicit voltage-only without changing protection',()=>{
    const r={...robot(),battery:{...robot().battery,voltage_v:11.34,percent:null,estimated_percent:67,
      estimate_method:'custom_voltage_table_v1',display_mode:'custom' as const,display_label:'My table',voltage_protection:'CLEAR' as const}};
    expect(fleetBatteryLabel(r)).toContain('약 67%');expect(fleetBatteryPolicyMessage(r)).toContain('사용자 기준표 · My table');
    const voltage={...r,battery:{...r.battery,display_mode:'voltage_only' as const,percent:80}};
    expect(fleetBatteryLabel(voltage)).toBe('11.34 V · simulated');
    expect(fleetBatteryPolicyMessage({...voltage,battery:{...voltage.battery,voltage_protection:'LOW_VOLTAGE_GUARD'}})).toContain('저전압 보호');
  });
  it('separates voltage-derived47percent from20percent reserve and low-voltage protection',()=>{
    const r:RobotFleetRobot={...robot(),kind:'physical',live_heartbeat:true,battery:{voltage_v:11.34,percent:null,source:'measured',age_ms:50,
      estimated_percent:46.7,estimate_method:'robotis_opencr_voltage_10_5_to_12_3_v1',capacity_measured:false,
      reserve_state:'ABOVE_RESERVE',voltage_protection:'CLEAR'}};
    expect(fleetBatteryLabel(r)).toBe('약 47% (전압 추정) · 11.34 V · measured');
    setup(fleet([r]));expect(screen.getByLabelText('Battery estimate and protection').textContent).toContain('실측 용량이 아닙니다');
    expect(fleetBatteryPolicyMessage({...r,battery:{...r.battery,voltage_v:11.1,estimated_percent:33.3,voltage_protection:'LOW_VOLTAGE_GUARD'}})).toContain('저전압 보호');
    expect(fleetBatteryLabel({...r,battery:{...r.battery,age_ms:40000}})).toContain('stale');
    expect(fleetBatteryPolicyMessage({...r,battery:{...r.battery,voltage_protection:'UNKNOWN',reserve_state:'AT_OR_BELOW_RESERVE'}})).toContain('20% 이하');
  });
  it('renders actual physical voltage-only battery replies without inventing a percentage or crashing',()=>{
    const physical={...robot(),kind:'physical' as const,live_heartbeat:true,
      battery:{voltage_v:12.35,source:'measured',age_ms:50} as RobotFleetRobot['battery']};
    expect(fleetBatteryLabel(physical)).toBe('12.35 V · measured');
    setup(fleet([physical]));expect(screen.getAllByText(/12.35 V/).length).toBeGreaterThan(0);
    expect(fleetBatteryLabel({...physical,battery:{...physical.battery,percent:NaN,voltage_v:Infinity,age_ms:NaN}})).toBe('unavailable · measured · stale');
  });
  it('shows source and current Twin revisions separately without disabling Stop on mismatch',()=>{
    const source:RobotTwinContext={schema:'robot-twin-context-1.0',context_id:'context-sha',project_id:'chat-project',conversation_session_id:'conversation-identity',
      scene_revision:'original-twin',engine_session_id:'engine',stage_epoch:'stage',association:'TWIN_REFERENCE',
      alignment:{frame_id:'native_sensor',status:'UNALIGNED',aligned:false,anchor:null}};
    const r={...robot(),kind:'physical' as const,live_heartbeat:true,source_twin_context:source,
      current_twin_context:{...source,scene_revision:'new-twin'},twin_context_relation:'DIFFERENT_TWIN_REVISION'};
    const {action}=setup(fleet([r]));
    const linkage=screen.getByLabelText('Robot Twin record linkage');
    expect(within(linkage).getByText('original-twin')).toBeTruthy();expect(within(linkage).getByText('new-twin')).toBeTruthy();
    expect(within(linkage).getByText('conversation-identity')).toBeTruthy();expect(within(linkage).getByText('UNALIGNED')).toBeTruthy();
    expect(within(linkage).getByText(/does not certify acquisition-time scene synchronization or world alignment/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'Stop'}));
    expect(action).toHaveBeenCalledWith(expect.objectContaining({action:'stop'}));
  });
  it('does not invent a source for saved records until Operation logs are loaded',async()=>{
    const r={...robot(),operation_id:null,last_operation_id:'operation-a',connection_state:'DISCONNECTED' as const};
    setup(fleet([r]));expect(screen.getByText('OPEN_LOGS_TO_CHECK_SAVED_REFERENCE')).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'Operation logs'}));
    await screen.findAllByText('LEGACY_UNKNOWN');expect(screen.getAllByText('not recorded',{selector:'dd'}).length).toBeGreaterThan(0);
  });
  it('keeps every robot in a fixed list without aligned poses or viewport anchors',()=>{
    const {props}=setup();
    expect(screen.getByRole('button',{name:/Robot a.*SIM/})).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:/Robot b.*SIM/}));
    expect(props.onSelect).toHaveBeenCalledWith('b');
    expect(screen.getByText('Pose unaligned / unavailable',{exact:false})).toBeTruthy();
  });
  it('requires both connected and fresh telemetry; preserves source and stale battery status',()=>{
    const old=robot();old.telemetry_age_ms=1000;
    expect(fleetRobotFresh(old)).toBe(false);expect(fleetBatteryLabel(old)).toContain('simulated · stale');
    old.kind='physical';old.connection_state='DISCONNECTED';old.battery.source='measured';
    setup(fleet([old]));expect((screen.getByRole('button',{name:'Hold forward'}) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getAllByText(/measured · stale/).length).toBe(3);
  });
  it('distinguishes a requested pause from the engine-applied stop without sending new movement',()=>{
    const paused={...robot(),control_state:'PAUSED' as const,applied_motion_epoch:'previous-motion'};
    const {action,props,rerender}=setup(fleet([paused]));
    expect(screen.getByText('Stop requested · waiting for engine confirmation')).toBeTruthy();
    expect(screen.queryByText('Engine stop confirmed')).toBeNull();
    rerender(<RobotFleet {...props} state={fleet([{...paused,applied_motion_epoch:null}])}/>);
    expect(screen.getByText('Stop requested · waiting for engine confirmation')).toBeTruthy();
    rerender(<RobotFleet {...props} state={fleet([{...paused,applied_motion_epoch:paused.motion_epoch}])}/>);
    expect(screen.getByText('Engine stop confirmed')).toBeTruthy();
    expect(screen.queryByText('Stop requested · waiting for engine confirmation')).toBeNull();
    expect(action).not.toHaveBeenCalled();
  });
  it('preserves legacy status and only shows engine-stop receipts for connected paused robots',()=>{
    const paused={...robot(),control_state:'PAUSED' as const};
    const {props,rerender}=setup(fleet([paused]));
    const expectNoStopReceipt=()=>{expect(screen.queryByText('Engine stop confirmed')).toBeNull();
      expect(screen.queryByText('Stop requested · waiting for engine confirmation')).toBeNull();};
    expectNoStopReceipt();
    rerender(<RobotFleet {...props} state={fleet([{...paused,applied_motion_epoch:paused.motion_epoch,connection_state:'DISCONNECTED'}])}/>);
    expectNoStopReceipt();
    rerender(<RobotFleet {...props} state={fleet([{...paused,applied_motion_epoch:paused.motion_epoch,control_state:'READY'}])}/>);
    expectNoStopReceipt();
  });
  it('does not treat a missing desired epoch as engine confirmation or relax stale drive permissions',()=>{
    const paused={...robot(),control_state:'PAUSED' as const,motion_epoch:null,applied_motion_epoch:null,telemetry_age_ms:1000};
    setup(fleet([paused]));
    expect(screen.getByText('Stop requested · waiting for engine confirmation')).toBeTruthy();
    expect(screen.queryByText('Engine stop confirmed')).toBeNull();
    expect((screen.getByRole('button',{name:'Hold forward'}) as HTMLButtonElement).disabled).toBe(true);
  });
  it('coalesces held input to one outstanding packet and stops independently on release',async()=>{
    vi.useFakeTimers();
    const {action}=setup(fleet(),body=>body.action==='drive'?new Promise(()=>{}):Promise.resolve(fleet()));
    const pad=screen.getByRole('group',{name:'Hold to drive'});
    fireEvent.keyDown(pad,{key:'ArrowUp'});
    await act(async()=>{vi.advanceTimersByTime(210);});
    const drives=action.mock.calls.map(([body])=>body).filter(body=>body.action==='drive');
    expect(drives).toHaveLength(1);
    expect(drives.map(body=>body.payload.sequence)).toEqual([1]);
    for(const drive of drives){expect(drive.robot_id).toBe('a');expect(drive.connection_epoch).toBe('connection-a');expect(drive.motion_epoch).toBe('motion-a');}
    fireEvent.keyUp(window,{key:'ArrowUp'});
    expect(action.mock.calls.at(-1)?.[0].action).toBe('stop');
    await act(async()=>{vi.advanceTimersByTime(500);});
    expect(action.mock.calls.filter(([body])=>body.action==='drive')).toHaveLength(1);
    expect(action.mock.calls.some(([body])=>body.action==='disconnect')).toBe(false);
  });
  it('does not queue or resume held renewals after a late outstanding reply',async()=>{
    vi.useFakeTimers();let complete:()=>void=()=>{};
    const {action}=setup(fleet(),body=>body.action==='drive'?new Promise(resolve=>{complete=()=>resolve(fleet());}):Promise.resolve(fleet()));
    fireEvent.keyDown(screen.getByRole('group',{name:'Hold to drive'}),{key:'ArrowUp'});
    await act(async()=>{vi.advanceTimersByTime(310);});
    expect(action.mock.calls.map(([body])=>body.action)).toEqual(['drive','stop']);
    await act(async()=>{complete();vi.advanceTimersByTime(600);});
    expect(action.mock.calls.filter(([body])=>body.action==='drive')).toHaveLength(1);
    expect(screen.getByRole('alert').textContent).toContain('delivery expired');
  });
  it('stops on window blur, prevents delayed drive errors from reviving a gesture',async()=>{
    let rejectDrive:(error:Error)=>void=()=>{};
    const {action}=setup(fleet(),body=>body.action==='drive'?new Promise((_,reject)=>{rejectDrive=reject;}):Promise.resolve(fleet()));
    fireEvent.keyDown(screen.getByRole('group',{name:'Hold to drive'}),{key:'w'});
    fireEvent.blur(window);expect(action.mock.calls.at(-1)?.[0].action).toBe('stop');
    await act(async()=>{rejectDrive(new Error('late failure'));});
    expect(action.mock.calls.map(([body])=>body.action)).toEqual(['drive','stop']);
  });
  it('stops the previous robot on selection and never disconnects it',()=>{
    const {action,props,rerender}=setup();
    fireEvent.keyDown(screen.getByRole('group',{name:'Hold to drive'}),{key:'a'});
    fireEvent.click(screen.getByRole('button',{name:/Robot b.*SIM/}));
    expect(action.mock.calls.at(-1)?.[0]).toMatchObject({action:'stop',robot_id:'a'});
    rerender(<RobotFleet {...props} selectedId="b"/>);
    expect(screen.getByRole('region',{name:'Control Robot b'})).toBeTruthy();
    expect(action.mock.calls.some(([body])=>body.action==='disconnect')).toBe(false);
  });
  it('pauses a hold if an epoch changes or optional fleet status becomes unavailable',()=>{
    const {action,props,rerender}=setup();
    fireEvent.keyDown(screen.getByRole('group',{name:'Hold to drive'}),{key:'d'});
    const changed=fleet();changed.robots[0].motion_epoch='new-motion';
    rerender(<RobotFleet {...props} state={changed}/>);
    expect(action.mock.calls.at(-1)?.[0]).toMatchObject({action:'stop',motion_epoch:'motion-a'});
    rerender(<RobotFleet {...props} available={false}/>);
    expect((screen.getByRole('button',{name:'Hold forward'}) as HTMLButtonElement).disabled).toBe(true);
  });
  it('Stop all bypasses another pending action',()=>{
    const {action}=setup(fleet(),()=>new Promise(()=>{}));
    fireEvent.click(screen.getByRole('button',{name:'Prepare'}));
    fireEvent.click(screen.getByRole('button',{name:'Stop all'}));
    expect(action.mock.calls.map(([body])=>body.action)).toEqual(['prepare','stop_all']);
  });
  it('registers an explicitly simulated robot with finite label and position values',async()=>{
    const {action}=setup();
    fireEvent.click(screen.getByRole('button',{name:'Manage robot fleet'}));
    fireEvent.click(screen.getByText('Add SIM robot',{selector:'summary'}));
    await screen.findByLabelText('Name');
    fireEvent.change(screen.getByLabelText('Name'),{target:{value:'Second SIM'}});
    fireEvent.change(screen.getByLabelText('X (m)'),{target:{value:'1.25'}});
    fireEvent.change(screen.getByLabelText('Yaw (rad)'),{target:{value:'1.57'}});
    fireEvent.click(screen.getByRole('button',{name:'Add SIM robot'}));
    await waitFor(()=>expect(action).toHaveBeenCalled());
    expect(action.mock.calls[0][0]).toMatchObject({action:'register_sim',robot_id:null,connection_epoch:null,motion_epoch:null,payload:{label:'Second SIM',position_m:[1.25,0,1.57]}});
  });
  it('routes finite text to the selected robot and loads operation source/completeness details',async()=>{
    const {action,operation}=setup();
    fireEvent.change(screen.getByLabelText('Robot command'),{target:{value:'turn left 90 degrees'}});
    fireEvent.click(screen.getByRole('button',{name:'Send command'}));
    await waitFor(()=>expect(action.mock.calls[0][0]).toMatchObject({action:'command',robot_id:'a',payload:{text:'turn left 90 degrees'}}));
    fireEvent.click(screen.getByRole('button',{name:'Operation logs'}));
    await waitFor(()=>expect(operation).toHaveBeenCalledWith('operation-a'));
    expect(await screen.findByRole('button',{name:'Download operation JSON'})).toBeTruthy();
    expect(screen.getByLabelText('Operation summary').textContent).toContain('Completefalse');
  });
  it('unmount sends Stop while preserving the robot connection',()=>{
    const {action,unmount}=setup();
    fireEvent.keyDown(screen.getByRole('group',{name:'Hold to drive'}),{key:'s'});unmount();
    expect(action.mock.calls.map(([body])=>body.action)).toEqual(['drive','stop']);
  });
  it('keeps unsupported physical controls unavailable without substituting simulated telemetry',()=>{
    const physical=robot();physical.kind='physical';physical.battery.source='unknown';physical.battery.percent=null;physical.battery.voltage_v=null;
    setup(fleet([physical]));
    expect(screen.getByText(/Physical control unavailable in this build/)).toBeTruthy();
    expect((screen.getByRole('button',{name:'Hold forward'}) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole('button',{name:'Prepare'}) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole('button',{name:'Stop'}) as HTMLButtonElement).disabled).toBe(false);
  });
  it('stops after an event-loop gap instead of renewing an old hold on resume',async()=>{
    vi.useFakeTimers();const {action}=setup();
    fireEvent.keyDown(screen.getByRole('group',{name:'Hold to drive'}),{key:'w'});
    vi.setSystemTime(Date.now()+400);
    await act(async()=>{vi.advanceTimersByTime(100);});
    expect(action.mock.calls.map(([body])=>body.action)).toEqual(['drive','stop']);
    await act(async()=>{vi.advanceTimersByTime(500);});
    expect(action.mock.calls.map(([body])=>body.action)).toEqual(['drive','stop']);
  });
  it('closing the drawer releases movement without ending its connection',()=>{
    const {action,props,rerender}=setup();
    fireEvent.keyDown(screen.getByRole('group',{name:'Hold to drive'}),{key:'w'});
    rerender(<RobotFleet {...props} drawerOpen={false}/>);
    expect(action.mock.calls.map(([body])=>body.action)).toEqual(['drive','stop']);
    expect(screen.queryByRole('group',{name:'Hold to drive'})).toBeNull();
    expect(screen.getByRole('button',{name:/Robot a.*SIM/})).toBeTruthy();
  });
  it('requires backend focus to match the drawer before drive or finite commands, while Stop remains available',()=>{
    const mismatched=fleet();mismatched.focused_robot_id='b';
    const {action,props,rerender}=setup(mismatched);
    expect(screen.getByText(/Control focus differs from this drawer/)).toBeTruthy();
    expect((screen.getByRole('button',{name:'Hold forward'}) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.keyDown(screen.getByRole('group',{name:'Hold to drive'}),{key:'w'});
    fireEvent.change(screen.getByLabelText('Robot command'),{target:{value:'forward 10 cm'}});
    expect((screen.getByRole('button',{name:'Send command'}) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.submit(screen.getByLabelText('Robot command').closest('form')!);
    expect(action).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button',{name:'Stop'}));
    expect(action.mock.calls.at(-1)?.[0]).toMatchObject({action:'stop',robot_id:'a'});
    rerender(<RobotFleet {...props} state={fleet()}/>);
    expect((screen.getByRole('button',{name:'Hold forward'}) as HTMLButtonElement).disabled).toBe(false);
    expect(action.mock.calls.some(([body])=>body.action==='drive')).toBe(false);
  });
  it('backend focus change discards an active local hold and never resumes it automatically',()=>{
    const {action,props,rerender}=setup();
    fireEvent.keyDown(screen.getByRole('group',{name:'Hold to drive'}),{key:'w'});
    const switched=fleet();switched.focused_robot_id='b';
    rerender(<RobotFleet {...props} state={switched}/>);
    expect(action.mock.calls.map(([body])=>body.action)).toEqual(['drive','stop']);
    rerender(<RobotFleet {...props} state={fleet()}/>);
    expect(action.mock.calls.map(([body])=>body.action)).toEqual(['drive','stop']);
  });
  it('locks selection and commands while focus is pending without marking fresh connection telemetry stale',()=>{
    const {action,props,rerender}=setup();
    rerender(<RobotFleet {...props} selectionPending/>);
    expect(screen.getByText(/Selecting robot · movement paused/)).toBeTruthy();
    expect((screen.getByRole('button',{name:/Robot b.*SIM/}) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole('button',{name:/Robot b.*SIM/}));
    expect(props.onSelect).not.toHaveBeenCalled();
    expect(screen.getAllByLabelText('Fresh connected heartbeat')).toHaveLength(2);
    expect(screen.queryByText(/receipt stale/)).toBeNull();
    expect((screen.getByRole('button',{name:'Hold forward'}) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.keyDown(screen.getByRole('group',{name:'Hold to drive'}),{key:'w'});
    expect(action).not.toHaveBeenCalled();
    expect((screen.getByRole('button',{name:'Stop'}) as HTMLButtonElement).disabled).toBe(false);
  });
  it('starts with compact selectable robot chips and expands registration only on request',()=>{
    const {container}=setup();
    expect(container.querySelector('.robot-fleet.is-condensed')).toBeTruthy();
    expect(screen.getByRole('button',{name:/Robot a.*SIM/})).toBeTruthy();
    expect(screen.queryByText('Add SIM robot',{selector:'summary'})).toBeNull();
    const manage=screen.getByRole('button',{name:'Manage robot fleet'});
    expect(manage.getAttribute('aria-expanded')).toBe('false');fireEvent.click(manage);
    expect(manage.getAttribute('aria-expanded')).toBe('true');
    expect(screen.getByText('Add SIM robot',{selector:'summary'})).toBeTruthy();
    fireEvent.click(manage);expect(container.querySelector('.robot-fleet.is-condensed')).toBeTruthy();
    expect(screen.getByRole('button',{name:/Robot b.*SIM/})).toBeTruthy();
  });
  it('bounds large scan-heavy operation rendering and preserves the complete JSON download',async()=>{
    const {operation,container}=setup();
    const rawMarker='RAW_SCAN_DETAIL_SHOULD_NOT_RENDER';
    const raw:RobotFleetOperation={schema_version:'robot-operation-1.0',operation_id:'operation-a',robot_id:'a',project_id:'project',
      manifest:{complete:false,completeness:'IN_PROGRESS',source:'isaac_kinematic_sim',missing:['MISSING_FOOTER'],
        source_files:{'runtime.py':'source-pin'.repeat(1000)}},
      events:Array.from({length:331},(_,index)=>({event_sequence:index+1,kind:index%4===0?'stop_requested':index%3===0?'command_accepted':'engine_observation',
        telemetry_sequence:index+10,position_m:[index/100,1.25,.3],reason:'observed result '.repeat(200),
        parameters:{direction:'left',amount:1.57},scan:{points:Array.from({length:360},(_,point)=>[point+.12345678,-point-.23456789]),vendor_detail:rawMarker}}))};
    operation.mockResolvedValue(raw);
    fireEvent.click(screen.getByRole('button',{name:'Operation logs'}));
    const summary=await screen.findByLabelText('Operation summary');
    expect(summary.textContent).toContain('331 events · showing 50 recent summaries');
    expect(summary.querySelectorAll('ol>li')).toHaveLength(50);
    expect(summary.textContent).toContain('scan points 360');
    expect(summary.textContent!.length).toBeLessThan(16000);
    expect(container.querySelector('pre')).toBeNull();expect(summary.textContent).not.toContain(rawMarker);
    expect(summary.textContent).not.toContain('source-pin'.repeat(10));
    let downloaded:Blob|null=null;
    vi.spyOn(URL,'createObjectURL').mockImplementation(blob=>{downloaded=blob as Blob;return 'blob:operation-download';});
    vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{});
    fireEvent.click(screen.getByRole('button',{name:'Download operation JSON'}));
    const content=await new Promise<string>((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result));reader.onerror=()=>reject(reader.error);reader.readAsText(downloaded!);});
    expect(content.length).toBeGreaterThan(662000);expect(JSON.parse(content)).toEqual(raw);
  });
  it('keeps historical one-shot physical observations stale and requires explicit disconnect before reconnect',async()=>{
    const physical=robot();physical.kind='physical';physical.capabilities={drive:false,lidar:false};physical.battery.source='measured';
    const state=fleet([physical]);state.capabilities.physical=true;
    const {action,props,rerender}=setup(state);
    expect(fleetRobotFresh(physical)).toBe(false);
    expect(screen.queryByLabelText('Fresh connected heartbeat')).toBeNull();
    expect(screen.getByText(/Fresh heartbeat and measured voltage do not grant driving permission/)).toBeTruthy();
    for(const name of ['Prepare','Turn LiDAR on','Hold forward'])expect((screen.getByRole('button',{name}) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText('Robot command'),{target:{value:'forward 10 cm'}});
    expect((screen.getByRole('button',{name:'Send command'}) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.submit(screen.getByLabelText('Robot command').closest('form')!);expect(action).not.toHaveBeenCalled();
    const connected=screen.getByRole('button',{name:'Connected'});expect((connected as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(connected);expect(action).not.toHaveBeenCalled();
    const disconnected={...physical,connection_state:'DISCONNECTED' as const,connection_epoch:null};
    rerender(<RobotFleet {...props} state={{...state,robots:[disconnected]}}/>);
    fireEvent.click(screen.getByRole('button',{name:'Connect'}));await waitFor(()=>expect(action).toHaveBeenCalledTimes(1));
    expect(action.mock.calls[0][0]).toMatchObject({action:'connect',robot_id:'a'});
  });
  function livePhysical():RobotFleetRobot{
    return {...robot(),kind:'physical',live_heartbeat:true,control_state:'UNPREPARED',lidar_state:'OFF',
      battery:{voltage_v:11.8,percent:null,source:'measured',age_ms:50},capabilities:{drive:false,lidar:false,read_only_connection:true,prepare:true,qualify:true,profile:true},
      setup:{runtime_state:'CONNECTED',binding_sha256:'binding-test-only',blockers:['MEASURED_FOOTPRINT_REQUIRED','SAME_BOOT_STOP_QUALIFICATION_REQUIRED'],profile:null,qualification:null}};
  }
  function physicalState(row=livePhysical()):RobotFleetState{return {...fleet([row]),capabilities:{sim:true,physical:true}};}
  it('provides the physical measurement checklist and exports only current identities plus null measurement fields',async()=>{
    const {action}=setup(physicalState());
    const guide=screen.getByLabelText('Measured profile guide');expect(guide.hasAttribute('open')).toBe(false);
    for(const topic of ['Geometry','Sampling','Timing','Stop model','Progress','timing sidecar','wheel odometry'])expect(guide.textContent).toContain(topic);
    expect(guide.textContent).toMatch(/strict (?:server )?schema/i);
    expect(guide.textContent).toContain('not an automatic instrument or certification');
    let blob:Blob|null=null,filename='';vi.spyOn(URL,'createObjectURL').mockImplementation(value=>{blob=value as Blob;return 'blob:blank-profile';});
    vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(function(this:HTMLAnchorElement){filename=this.download;});
    fireEvent.click(screen.getByRole('button',{name:'Download blank measured-profile JSON'}));
    const text=await new Promise<string>((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result));reader.onerror=()=>reject(reader.error);reader.readAsText(blob!);});
    const template=JSON.parse(text);expect(filename).toBe('physical-profile-a-unmeasured.json');
    expect(template).toMatchObject({schema:'physical-manual-profile-1.0',robot_id:'a',binding_sha256:'binding-test-only'});
    expect(Object.keys(template)).toEqual(['schema','robot_id','binding_sha256','geometry','sampling','timing','stop_model','progress']);
    for(const [group,count] of [['geometry',6],['sampling',7],['timing',3],['stop_model',12],['progress',13]] as const){
      expect(Object.keys(template[group])).toHaveLength(count);expect(Object.values(template[group]).every(value=>value===null)).toBe(true);
    }
    expect(template.stop_model).toHaveProperty('stopping_measurement_sha256',null);
    expect(template.progress).toHaveProperty('body_progress_policy',null);expect(template.timing.provenance).toBeNull();
    expect(action).not.toHaveBeenCalled();
  });
  it('lets the App edit a blank profile but keeps null measurements from being applied or granting movement',()=>{
    const {action}=setup(physicalState());
    fireEvent.click(screen.getByRole('button',{name:'Start blank profile in App'}));
    const draft=(screen.getByLabelText('Profile JSON editor') as HTMLTextAreaElement).value;
    expect(JSON.parse(draft).robot_id).toBe('a');expect(action).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button',{name:'Review edited profile JSON'}));
    expect(screen.getByText(/Unmeasured fields.*geometry.sensor_frame/)).toBeTruthy();
    fireEvent.click(screen.getByLabelText('I reviewed the original measured values, robot identity and evidence references. These are not App-generated estimates.'));
    expect((screen.getByRole('button',{name:'Apply reviewed profile'}) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole('button',{name:'Hold forward'}) as HTMLButtonElement).disabled).toBe(true);expect(action).not.toHaveBeenCalled();
  });
  const bodyThresholds=['minimum_body_translation_m','minimum_body_rotation_rad','maximum_body_speed_m_s','maximum_body_rotation_rad_s'];
  function profileGateContract(policy:string|null){
    fireEvent.click(screen.getByRole('button',{name:'Start blank profile in App'}));
    const editor=screen.getByLabelText('Profile JSON editor') as HTMLTextAreaElement,document=JSON.parse(editor.value);
    // These deliberately invalid strings isolate the UI null gate. They are
    // not measurements or a passing strict profile; the mocked server rejects.
    for(const group of ['geometry','sampling','timing','stop_model','progress'])
      for(const key of Object.keys(document[group]))document[group][key]='UI contract fixture; not measured';
    document.progress.body_progress_policy=policy;
    for(const key of bodyThresholds)document.progress[key]=null;
    return {editor,document};
  }
  function reviewGateDocument(editor:HTMLElement,document:unknown){
    fireEvent.change(editor,{target:{value:JSON.stringify(document)}});
    fireEvent.click(screen.getByRole('button',{name:'Review edited profile JSON'}));
    fireEvent.click(screen.getByLabelText('I reviewed the original measured values, robot identity and evidence references. These are not App-generated estimates.'));
  }
  it.each(['explicitly_unverified_supervised','independent_required',null])('keeps body-only null gate scoped to explicit policy %s',policy=>{
    const {action}=setup(physicalState()),{editor,document}=profileGateContract(policy);reviewGateDocument(editor,document);
    expect((screen.getByRole('button',{name:'Apply reviewed profile'}) as HTMLButtonElement).disabled).toBe(policy!=='explicitly_unverified_supervised');
    expect((screen.getByRole('button',{name:'Hold forward'}) as HTMLButtonElement).disabled).toBe(true);
    if(policy==='explicitly_unverified_supervised')expect(screen.getByText(/Body progress UNKNOWN.*body stall\/slip is not verified/)).toBeTruthy();
    if(policy!=='explicitly_unverified_supervised')expect(screen.getByText(/Unmeasured fields.*progress.minimum_body_translation_m/)).toBeTruthy();
    expect(action).not.toHaveBeenCalled();
  });
  it.each(['geometry','sampling','timing','stop_model','progress'])('retains mandatory %s measurements in the supervised policy',group=>{
    const {action}=setup(physicalState()),{editor,document}=profileGateContract('explicitly_unverified_supervised');
    const key=group==='progress'?'minimum_wheel_progress_m':Object.keys(document[group])[0];document[group][key]=null;
    reviewGateDocument(editor,document);
    expect((screen.getByRole('button',{name:'Apply reviewed profile'}) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(new RegExp(`Unmeasured fields.*${group}\\.${key}`))).toBeTruthy();expect(action).not.toHaveBeenCalled();
  });
  it.each([null,.125,0])('preserves body threshold %s in the review payload and defers strict numeric validation to the server',async value=>{
    const {action}=setup(physicalState(),async()=>{throw new Error('PROFILE_STRICT_CONTRACT_REJECTED');});
    const {editor,document}=profileGateContract('explicitly_unverified_supervised');for(const key of bodyThresholds)document.progress[key]=value;
    reviewGateDocument(editor,document);fireEvent.click(screen.getByRole('button',{name:'Apply reviewed profile'}));
    expect((await screen.findByRole('alert')).textContent).toBe('PROFILE_STRICT_CONTRACT_REJECTED');
    expect(action.mock.calls[0][0]).toMatchObject({action:'profile',payload:{profile:document}});
    expect((screen.getByRole('button',{name:'Hold forward'}) as HTMLButtonElement).disabled).toBe(true);
  });
  it.each(['NaN','1e999'])('rejects non-finite JSON %s rather than converting it to an optional null',value=>{
    const {action}=setup(physicalState());
    fireEvent.change(screen.getByLabelText('Profile JSON editor'),{target:{value:`{"robot_id":"a","binding_sha256":"binding-test-only","progress":{"body_progress_policy":"explicitly_unverified_supervised","minimum_body_translation_m":${value}}}`}});
    fireEvent.click(screen.getByRole('button',{name:'Review edited profile JSON'}));
    expect(screen.getByRole('alert').textContent).toContain('Invalid profile JSON');expect(screen.queryByRole('button',{name:'Apply reviewed profile'})).toBeNull();expect(action).not.toHaveBeenCalled();
  });
  it('keeps edited profile robot and binding identities fixed and discards its draft on selection change',()=>{
    const {action,props,rerender}=setup(physicalState());
    const editor=screen.getByLabelText('Profile JSON editor');
    fireEvent.change(editor,{target:{value:JSON.stringify({robot_id:'other',binding_sha256:'binding-test-only'})}});
    fireEvent.click(screen.getByRole('button',{name:'Review edited profile JSON'}));
    expect(screen.getByRole('alert').textContent).toContain('PROFILE_ROBOT_MISMATCH');
    fireEvent.change(editor,{target:{value:JSON.stringify({robot_id:'a',binding_sha256:'other-binding'})}});
    fireEvent.click(screen.getByRole('button',{name:'Review edited profile JSON'}));
    expect(screen.getByRole('alert').textContent).toContain('PROFILE_BINDING_MISMATCH');
    rerender(<RobotFleet {...props} selectedId="b" state={{...physicalState(),robots:[{...livePhysical(),robot_id:'b',label:'Robot b'}]}}/>);
    expect((screen.getByLabelText('Profile JSON editor') as HTMLTextAreaElement).value).toBe('');expect(action).not.toHaveBeenCalled();
  });
  it('shows authoritative strict-profile rejection after editing without turning the review into a measurement certificate',async()=>{
    const {action}=setup(physicalState(),async()=>{throw new Error('PROFILE_MEASURED_GEOMETRY_REQUIRED');});
    fireEvent.change(screen.getByLabelText('Profile JSON editor'),{target:{value:JSON.stringify({schema:'physical-manual-profile-1.0',robot_id:'a',binding_sha256:'binding-test-only',fixture:'not real measurements'})}});
    fireEvent.click(screen.getByRole('button',{name:'Review edited profile JSON'}));
    expect(screen.getByText(/Imported App profile editor.*server validation pending/)).toBeTruthy();
    fireEvent.click(screen.getByLabelText('I reviewed the original measured values, robot identity and evidence references. These are not App-generated estimates.'));
    fireEvent.click(screen.getByRole('button',{name:'Apply reviewed profile'}));
    expect((await screen.findByRole('alert')).textContent).toBe('PROFILE_MEASURED_GEOMETRY_REQUIRED');
    expect(action.mock.calls.map(([body])=>body.action)).toEqual(['profile']);
    expect((screen.getByRole('button',{name:'Hold forward'}) as HTMLButtonElement).disabled).toBe(true);
  });
  it('places a visualization-only physical marker only after an explicit submit, even while disconnected',async()=>{
    const physical={...livePhysical(),connection_state:'DISCONNECTED' as const,connection_epoch:null,motion_epoch:null,live_heartbeat:false};
    const originalPose={position_m:[1,2,.3] as [number,number,number],frame_id:'odom',source:'wheel_odometry',aligned:false};physical.pose=originalPose;
    const {action}=setup(physicalState(physical));
    const summary=screen.getByText('Estimated Twin marker',{selector:'summary'});
    expect(summary.parentElement?.hasAttribute('open')).toBe(false);
    expect(action).not.toHaveBeenCalled();fireEvent.click(summary);expect(action).not.toHaveBeenCalled();
    expect(screen.getByText('Review the robot position and yaw in this Twin. This estimate anchors relative LiDAR tracking for display and explicitly requested destinations; it never grants driving permission or claims measured world alignment.')).toBeTruthy();
    expect((screen.getByLabelText('Marker X (m)') as HTMLInputElement).value).toBe('0');
    fireEvent.change(screen.getByLabelText('Marker X (m)'),{target:{value:'1.25'}});
    fireEvent.change(screen.getByLabelText('Marker Y (m)'),{target:{value:'-0.5'}});
    fireEvent.change(screen.getByLabelText('Marker yaw (rad)'),{target:{value:'1.57'}});
    fireEvent.click(screen.getByRole('button',{name:'Place estimated robot marker'}));
    await waitFor(()=>expect(action).toHaveBeenCalledTimes(1));
    expect(action.mock.calls[0][0]).toMatchObject({action:'set_twin_pose',robot_id:'a',connection_epoch:null,motion_epoch:null,payload:{position_m:[1.25,-.5,1.57]}});
    expect(physical.pose).toBe(originalPose);expect(physical.pose.source).toBe('wheel_odometry');expect(physical.display_pose).toBeUndefined();
    expect((screen.getByRole('button',{name:'Hold forward'}) as HTMLButtonElement).disabled).toBe(true);
    expect(action.mock.calls.some(([body])=>['connect','drive','lidar','prepare','qualify'].includes(body.action))).toBe(false);
  });
  it('rejects empty marker coordinates and unavailable fleet state, without creating a SIM marker form',async()=>{
    const {action,props,rerender}=setup(physicalState());
    fireEvent.change(screen.getByLabelText('Marker X (m)'),{target:{value:''}});
    fireEvent.submit(screen.getByLabelText('Marker X (m)').closest('form')!);
    expect(screen.getByRole('alert').textContent).toContain('Enter finite X, Y and yaw');expect(action).not.toHaveBeenCalled();
    rerender(<RobotFleet {...props} available={false}/>);
    expect((screen.getByRole('button',{name:'Place estimated robot marker'}) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.submit(screen.getByLabelText('Marker X (m)').closest('form')!);expect(action).not.toHaveBeenCalled();
    rerender(<RobotFleet {...props} state={fleet()}/>);
    expect(screen.queryByText('Estimated Twin marker',{selector:'summary'})).toBeNull();
  });
  it('shows a saved marker as an estimate and surfaces current-revision rejection without optimistic placement',async()=>{
    const physical=livePhysical();physical.display_pose={position_m:[.1,.2,.3],source:'operator_estimate_not_localized',scene_revision:'confirmed-revision',frame_id:'isaac_world',aligned:false};
    const {action}=setup(physicalState(physical),async()=>{throw new Error('Display a current confirmed Twin revision before placing the marker.');});
    expect(screen.getByText(/Static visualization estimate.*confirmed-revision.*operator_estimate_not_localized/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'Place estimated robot marker'}));
    expect(await screen.findByRole('alert')).toHaveProperty('textContent','Display a current confirmed Twin revision before placing the marker.');
    expect(action).toHaveBeenCalledTimes(1);expect(physical.display_pose.position_m).toEqual([.1,.2,.3]);
  });
  it('shows live SSH and measured battery independently of preparation, sensor and recording authority',()=>{
    const physical=livePhysical(),{props,rerender}=setup(physicalState(physical));
    expect(fleetRobotFresh(physical)).toBe(true);expect(fleetBatteryLabel(physical)).toBe('11.80 V · measured');
    expect(screen.getByLabelText('Physical connection and readiness').textContent).toContain('Fresh authenticated session');
    expect(screen.getByLabelText('Physical connection and readiness').textContent).toContain('Unknown · no cleanup receipt');
    expect(screen.getByLabelText('Physical setup blockers').textContent).toContain('MEASURED_FOOTPRINT_REQUIRED');
    expect(screen.getByLabelText('Physical setup blockers').textContent).toContain('SAME_BOOT_STOP_QUALIFICATION_REQUIRED');
    for(const name of ['Hold forward','Turn LiDAR on'])expect((screen.getByRole('button',{name}) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByLabelText('Fresh connected heartbeat')).toBeTruthy();
    expect(fleetRobotFresh({...physical,telemetry_age_ms:2499})).toBe(true);
    expect(fleetRobotFresh({...physical,telemetry_age_ms:2500})).toBe(false);
    expect(fleetRobotFresh({...physical,live_heartbeat:false})).toBe(false);
    rerender(<RobotFleet {...props} state={physicalState({...physical,battery:{...physical.battery,age_ms:1000}})}/>);
    expect(screen.getByLabelText('Fresh connected heartbeat')).toBeTruthy();
    expect(screen.getByLabelText('Physical connection and readiness').textContent).toContain('measured · stale');
  });
  it('requires new physical preparation and same-boot qualification confirmations, preserving the exact envelopes',async()=>{
    const state=physicalState(),{action,props,rerender}=setup(state);
    const prepare=screen.getByRole('button',{name:'Prepare'}),qualify=screen.getByRole('button',{name:'Run same-boot stop qualification'});
    expect((prepare as HTMLButtonElement).disabled).toBe(true);expect((qualify as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByLabelText('I am present and confirm zero-command controller preparation.'));
    fireEvent.click(prepare);await waitFor(()=>expect(action).toHaveBeenCalledTimes(1));
    expect(action.mock.calls[0][0]).toMatchObject({action:'prepare',robot_id:'a',connection_epoch:'connection-a',payload:{confirmed:true}});
    await waitFor(()=>expect((prepare as HTMLButtonElement).disabled).toBe(true));
    fireEvent.click(screen.getByLabelText('I am supervising the robot with the required clear space and confirm the stop qualification movement.'));
    fireEvent.click(qualify);await waitFor(()=>expect(action).toHaveBeenCalledTimes(2));
    expect(action.mock.calls[1][0]).toMatchObject({action:'qualify',robot_id:'a',payload:{confirmed:true}});
    fireEvent.click(screen.getByLabelText('I am present and confirm zero-command controller preparation.'));
    rerender(<RobotFleet {...props} state={physicalState({...state.robots[0],connection_epoch:'new-connection'})}/>);
    expect((screen.getByLabelText('I am present and confirm zero-command controller preparation.') as HTMLInputElement).checked).toBe(false);
    expect(action.mock.calls.some(([body])=>body.action==='drive')).toBe(false);
  });
  it('leaves status and named Stop available with no drive capability, even while another physical action is pending',async()=>{
    const {action}=setup(physicalState(),body=>body.action==='prepare'?new Promise(()=>{}):Promise.resolve(physicalState()));
    fireEvent.change(screen.getByLabelText('Robot command'),{target:{value:'battery status'}});
    fireEvent.click(screen.getByRole('button',{name:'Send command'}));
    await waitFor(()=>expect(action.mock.calls[0][0]).toMatchObject({action:'command',payload:{text:'battery status'}}));
    fireEvent.click(screen.getByLabelText('I am present and confirm zero-command controller preparation.'));
    await waitFor(()=>expect((screen.getByRole('button',{name:'Prepare'}) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole('button',{name:'Prepare'}));
    fireEvent.change(screen.getByLabelText('Robot command'),{target:{value:'Robot a stop'}});
    expect((screen.getByRole('button',{name:'Send command'}) as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(screen.getByRole('button',{name:'Send command'}));
    expect(action.mock.calls.at(-1)?.[0]).toMatchObject({action:'command',robot_id:'a',payload:{text:'Robot a stop'}});
    fireEvent.click(screen.getByRole('button',{name:'Stop'}));
    expect(action.mock.calls.at(-1)?.[0]).toMatchObject({action:'stop',robot_id:'a'});
    expect(action.mock.calls.some(([body])=>body.action==='drive')).toBe(false);
  });
  it('keeps a degraded physical session from starting a second connection until Disconnect',async()=>{
    const degraded={...livePhysical(),connection_state:'DEGRADED' as const,live_heartbeat:false};
    const {action}=setup(physicalState(degraded));
    const reconnect=screen.getByRole('button',{name:'Disconnect to reconnect'});
    expect((reconnect as HTMLButtonElement).disabled).toBe(true);fireEvent.click(reconnect);expect(action).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button',{name:'Disconnect'}));
    await waitFor(()=>expect(action.mock.calls[0][0]).toMatchObject({action:'disconnect',robot_id:'a',connection_epoch:'connection-a'}));
  });
  it('imports and reviews original profile JSON while the robot is off without inventing or sending measurements automatically',async()=>{
    const off={...livePhysical(),connection_state:'DISCONNECTED' as const,live_heartbeat:false,connection_epoch:null,telemetry_age_ms:null};
    const {action}=setup(physicalState(off));
    const document={schema:'physical-manual-profile-1.0',robot_id:'a',binding_sha256:'binding-test-only',fixture:'supplementary test only; not measured evidence'};
    fireEvent.change(screen.getByLabelText('Measured profile JSON'),{target:{files:[new File([JSON.stringify(document)],'measured-profile.json',{type:'application/json'})]}});
    expect(await screen.findByText(/Imported measured-profile.json/)).toBeTruthy();
    expect(screen.getByLabelText('Measured profile import and review').querySelector('pre')?.textContent).toBe(JSON.stringify(document,null,2));
    expect(action).not.toHaveBeenCalled();
    const apply=screen.getByRole('button',{name:'Apply reviewed profile'});expect((apply as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByLabelText('I reviewed the original measured values, robot identity and evidence references. These are not App-generated estimates.'));
    expect((apply as HTMLButtonElement).disabled).toBe(false);fireEvent.click(apply);
    await waitFor(()=>expect(action.mock.calls[0][0]).toMatchObject({action:'profile',robot_id:'a',connection_epoch:null,payload:{profile:document}}));
    expect(action.mock.calls.map(([body])=>body.action)).toEqual(['profile']);
  });
  it('rejects malformed, non-object and oversized profile imports without any runtime mutation',async()=>{
    const {action}=setup(physicalState());
    for(const content of ['{"schema":','[]']){
      fireEvent.change(screen.getByLabelText('Measured profile JSON'),{target:{files:[new File([content],'invalid.json')]}});
      expect(await screen.findByText(/Invalid profile JSON/)).toBeTruthy();
      expect(screen.queryByRole('button',{name:'Apply reviewed profile'})).toBeNull();
    }
    fireEvent.change(screen.getByLabelText('Measured profile JSON'),{target:{files:[new File(['x'.repeat(64*1024+1)],'large.json')]}});
    expect(await screen.findByText(/Profile JSON exceeds 64 KiB/)).toBeTruthy();expect(action).not.toHaveBeenCalled();
  });
  it('does not carry an imported profile or review acknowledgement into another selected robot',async()=>{
    const state=physicalState(),{props,rerender,action}=setup(state);
    fireEvent.change(screen.getByLabelText('Measured profile JSON'),{target:{files:[new File(['{"schema":"test-only"}'],'first.json')]}});
    await screen.findByText(/Imported first.json/);
    fireEvent.click(screen.getByLabelText('I reviewed the original measured values, robot identity and evidence references. These are not App-generated estimates.'));
    const other={...livePhysical(),robot_id:'b',label:'Robot b'};
    rerender(<RobotFleet {...props} selectedId="b" state={{...state,focused_robot_id:'b',robots:[...state.robots,other]}}/>);
    expect(screen.queryByText(/Imported first.json/)).toBeNull();expect(action).not.toHaveBeenCalled();
  });
  it('downloads named runtime evidence from operation receipts without treating opaque paths as URLs',async()=>{
    const h=setup(physicalState()),evidence=vi.fn(async()=>new Blob(['original runtime bytes'],{type:'application/x-ndjson'}));
    h.props.api.robotFleetEvidence=evidence;
    h.operation.mockResolvedValueOnce({schema_version:'robot-operation-1.0',operation_id:'operation-a',robot_id:'a',project_id:'project',events:[],
      manifest:{complete:false,stream:{complete:false,error:'RECEIPT_MISSING',local_receipt:'physical-live/operation-a/receipt.json',segments:[
        {path:'events-00000.jsonl',bytes:100,events:5,sha256:'a'.repeat(64)},{path:'../untrusted.jsonl',sha256:'b'.repeat(64)}]}}});
    fireEvent.click(screen.getByRole('button',{name:'Operation logs'}));
    expect(await screen.findByText(/Physical runtime evidence · 4 files/)).toBeTruthy();
    expect(screen.getByText('RECEIPT_MISSING')).toBeTruthy();
    expect((screen.getByRole('button',{name:'Download unavailable file'}) as HTMLButtonElement).disabled).toBe(true);
    vi.spyOn(URL,'createObjectURL').mockReturnValue('blob:runtime-evidence');let filename='';
    vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(function(this:HTMLAnchorElement){filename=this.download;});
    fireEvent.click(screen.getByRole('button',{name:'Download events-00000.jsonl'}));
    await waitFor(()=>expect(filename).toBe('physical-operation-a-events-00000.jsonl'));
    expect(evidence).toHaveBeenCalledWith('operation-a','events-00000.jsonl');
    expect(h.action).not.toHaveBeenCalled();
  });
  it('opens the same saved operation after cold restore without restoring connection or driving authority',async()=>{
    const cold=robot();cold.operation_id=null;cold.last_operation_id='operation-a';cold.connection_state='DISCONNECTED';
    cold.connection_epoch=null;cold.motion_epoch=null;cold.control_state='UNPREPARED';cold.telemetry_age_ms=null;
    const {operation,action}=setup(fleet([cold]));
    expect(screen.getByText(/Saved operation logs · historical/)).toBeTruthy();
    expect((screen.getByRole('button',{name:'Hold forward'}) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole('button',{name:'Operation logs'}));
    await waitFor(()=>expect(operation).toHaveBeenCalledWith('operation-a'));
    expect(await screen.findByRole('button',{name:'Download operation JSON'})).toBeTruthy();
    expect(screen.getByLabelText('Operation summary').textContent).toContain('Completefalse');
    let filename='';vi.spyOn(URL,'createObjectURL').mockReturnValue('blob:historical-operation');
    vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(function(this:HTMLAnchorElement){filename=this.download;});
    fireEvent.click(screen.getByRole('button',{name:'Download operation JSON'}));
    expect(filename).toBe('robot-operation-operation-a.json');expect(action).not.toHaveBeenCalled();
    expect((screen.getByRole('button',{name:'Hold forward'}) as HTMLButtonElement).disabled).toBe(true);
  });
});

describe('physical runtime evidence downloads (supplementary API tests)',()=>{
  const response=(body:BodyInit,context='evidence-context',status=200)=>new Response(body,{status,headers:{'Content-Type':'application/octet-stream','X-TwinPulse-Context':context}});
  it('uses the authenticated current project and preserves exact raw bytes for a whitelisted runtime file',async()=>{
    const bytes=new Uint8Array([0,13,10,255,99]);
    const request=vi.fn(async(path:string)=>path==='/v1/product/session'?
      response(JSON.stringify({csrf_token:'test-csrf',context_id:'evidence-context'})):response(bytes));
    vi.stubGlobal('fetch',request);const api=new TwinPulseApi();await api.bootstrap();
    const result=await api.robotFleetEvidence('operation-a','events-00000.jsonl');
    const content=await new Promise<ArrayBuffer>((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result as ArrayBuffer);reader.onerror=()=>reject(reader.error);reader.readAsArrayBuffer(result);});
    expect(new Uint8Array(content)).toEqual(bytes);
    expect(request).toHaveBeenCalledWith('/v1/product/robot-fleet/operations/operation-a/evidence/events-00000.jsonl',expect.objectContaining({
      credentials:'same-origin',cache:'no-store',headers:{'X-TwinPulse-Context':'evidence-context'}}));
  });
  it('rejects traversal and opaque runtime source paths before requesting a file',async()=>{
    const request=vi.fn();vi.stubGlobal('fetch',request);const api=new TwinPulseApi();
    for(const file of ['../receipt.json','physical-live/operation-a/receipt.json','https://example.invalid/receipt.json','events-00000.jsonl?token=x'])
      await expect(api.robotFleetEvidence('operation-a',file)).rejects.toMatchObject({code:'fleet_evidence_invalid'});
    await expect(api.robotFleetEvidence('../operation-a','receipt.json')).rejects.toMatchObject({code:'fleet_evidence_invalid'});
    expect(request).not.toHaveBeenCalled();
  });
  it('does not deliver a late evidence file after the active project context changes',async()=>{
    let finish!:(value:Response)=>void,sessions=0;
    const request=vi.fn(async(path:string)=>{
      if(path==='/v1/product/session'){
        const context=++sessions===1?'evidence-context':'other-context';
        return response(JSON.stringify({csrf_token:'test-csrf',context_id:context,project_id:'project'}),context);
      }
      if(sessions===1)return new Promise<Response>(resolve=>{finish=resolve;});
      return response('new-context bytes','other-context');
    });
    vi.stubGlobal('fetch',request);const api=new TwinPulseApi();await api.bootstrap();
    const download=api.robotFleetEvidence('operation-a','receipt.json');
    await api.projectContext();finish(response('old-context bytes'));
    await expect(download).rejects.toMatchObject({code:'context_changed'});
  });
  it('bounds a stalled evidence read without creating a successful download',async()=>{
    vi.useFakeTimers();const request=vi.fn(()=>new Promise<Response>(()=>{}));vi.stubGlobal('fetch',request);
    const result=new TwinPulseApi().robotFleetEvidence('operation-a','receipt.json').catch(caught=>caught);
    await vi.advanceTimersByTimeAsync(15001);
    expect(await result).toMatchObject({code:'fleet_evidence_unavailable'});
    expect(request).toHaveBeenCalledTimes(1);
  });
});

function viewportHarness(){
  const bitmap={width:800,height:800,close:vi.fn()};
  vi.stubGlobal('createImageBitmap',vi.fn(async()=>bitmap));
  vi.spyOn(HTMLCanvasElement.prototype,'getContext').mockReturnValue({clearRect:vi.fn(),drawImage:vi.fn()} as unknown as CanvasRenderingContext2D);
  const original=HTMLElement.prototype.getBoundingClientRect;
  let slotWidth=600,slotHeight=400;
  vi.spyOn(HTMLElement.prototype,'getBoundingClientRect').mockImplementation(function(this:HTMLElement){
    if(this.classList.contains('twin-frame-slot'))return {width:slotWidth,height:slotHeight,left:0,top:0,right:slotWidth,bottom:slotHeight,x:0,y:0,toJSON:()=>{}};
    return original.call(this);
  });
  let state:ViewportState={state:'live',fps:6,age_ms:10,detail:'Isaac render',physical_authority:false,camera_pending:false,camera_result:null,
    frame:{frame_id:1,captured_at_ms:Date.now(),applied_revision:'revision',engine_session_id:'engine-one',stage_epoch:'stage',camera_sequence:2,width:800,height:800,sha256:'hash',url:'unused',
      robot_anchors:[{robot_id:'a',screen_anchor_uv:[.25,.5],screen_bounds_uv:[.2,.4,.3,.5],visible:true},{robot_id:'b',screen_anchor_uv:[.5,.5],screen_bounds_uv:[.4,.4,.6,.6],visible:false}]}};
  const api={viewportState:vi.fn(async()=>state),viewportImage:vi.fn(async()=>new Blob(['image'],{type:'image/jpeg'})),viewportCamera:vi.fn()};
  return {api:api as unknown as TwinPulseApi,getState:()=>state,setState:(next:ViewportState)=>{state=next;},bitmap,setSlot:(width:number,height:number)=>{slotWidth=width;slotHeight=height;}};
}
function rectanglesOverlap(a:Pick<RobotBadgePlacement,'left'|'top'|'width'|'height'>,b:Pick<RobotBadgePlacement,'left'|'top'|'width'|'height'>){
  return a.left<b.left+b.width-.00001&&a.left+a.width>b.left+.00001&&a.top<b.top+b.height-.00001&&a.top+a.height>b.top+.00001;
}
describe('robot badge collision placement (supplementary geometry)',()=>{
  const anchor=(id:string,u:number,v:number)=>({robot_id:id,screen_anchor_uv:[u,v] as [number,number],screen_bounds_uv:[u,v,u,v] as [number,number,number,number],visible:true});
  it('does not cover either projected body envelope with either robot name plate',()=>{
    const anchors=[{...anchor('alpha',.55,.4),screen_bounds_uv:[.525,.36,.575,.44] as [number,number,number,number]},
      {...anchor('beta',.65,.43),screen_bounds_uv:[.625,.39,.675,.47] as [number,number,number,number]}];
    const placed=layoutRobotBadges(anchors,800,500);expect(placed).toHaveLength(2);
    for(const plate of placed)for(const a of anchors){const b=a.screen_bounds_uv;
      expect(rectanglesOverlap(plate,{left:b[0]*800,top:b[1]*500,width:(b[2]-b[0])*800,height:(b[3]-b[1])*500})).toBe(false);}
  });
  it('allows names to overlap rather than separating them from their robots',()=>{
    const anchors=[anchor('alpha',.6,.6),anchor('beta',.725,.6)],original=JSON.stringify(anchors);
    const placed=layoutRobotBadges(anchors,400,300);
    expect(placed).toHaveLength(2);expect(rectanglesOverlap(placed[0],placed[1])).toBe(true);
    expect(placed[0]).toMatchObject({anchorX:240,anchorY:180,width:72,height:16});
    expect(placed[1]).toMatchObject({anchorX:290,anchorY:180});expect(JSON.stringify(anchors)).toBe(original);
    expect(placed.every(row=>row.top===row.anchorY+2&&row.left+row.width/2===row.anchorX)).toBe(true);
  });
  it.each([[400,300],[280,180],[200,100]])('keeps all 16 co-located names immediately below their bodies in %dx%d',(width,height)=>{
    const placed=layoutRobotBadges(Array.from({length:16},(_,index)=>anchor(`robot-${index}`,.5,.5)),width,height);
    expect(placed).toHaveLength(16);
    for(let i=0;i<placed.length;i++){
      const badge=placed[i];expect(badge.left).toBeGreaterThanOrEqual(0);expect(badge.top).toBeGreaterThanOrEqual(0);
      expect(badge.anchorX).toBe(width*.5);expect(badge.anchorY).toBe(height*.5);
      expect(badge.left+badge.width).toBeLessThanOrEqual(width+.00001);expect(badge.top+badge.height).toBeLessThanOrEqual(height+.00001);
      expect(badge.top-badge.anchorY).toBe(2);expect(badge.left+badge.width/2).toBe(badge.anchorX);
    }
  });
  it('keeps edge labels spatially attached even when clipped and ignores list order',()=>{
    const anchors=[anchor('left',0,0),anchor('right',1,1),anchor('near-right',.98,.99)];
    for(const [width,height] of [[400,400],[220,160]]){
      const first=layoutRobotBadges(anchors,width,height),reordered=layoutRobotBadges([...anchors].reverse(),width,height);
      for(const badge of first){expect(reordered.find(item=>item.robot_id===badge.robot_id)).toEqual(badge);
        expect(badge.left+badge.width/2).toBe(badge.anchorX);expect(badge.top).toBe(badge.anchorY+2);}
    }
    expect(layoutRobotBadges(anchors,0,0)).toEqual([]);
  });
});

describe('fleet anchors bound to decoded Isaac frames (supplementary)',()=>{
  it.each([0,.25,.75])('expires the original scan at700ms independently of the100ms age interval (fraction %s)',async fraction=>{
    vi.useFakeTimers();vi.setSystemTime(10000);
    const h=viewportHarness(),stamp=Date.now()-51+fraction,current=fleet();
    h.getState().frame!.lidar_overlay={robot_id:'a',connection_epoch:'connection-a',motion_epoch:'motion-a',origin_uv:[.25,.5],points_uv:[[.2,.3]],captured_at_ms:stamp,source:'isaac_usd_aabb_rays',physical_authority:false};
    current.robots[0].scan={points:[[.1,.2]],source:'test'};
    const component=render(<TwinViewport api={h.api} robotFleet={current} onRobotSelect={vi.fn()}/>);
    await act(async()=>{await vi.advanceTimersByTimeAsync(0);});
    expect(screen.queryByLabelText('Latest frame-bound simulated LiDAR hits')).not.toBeNull();
    await act(async()=>{await vi.advanceTimersByTimeAsync(648);});
    expect(screen.queryByLabelText('Latest frame-bound simulated LiDAR hits')?.getAttribute('data-scan-captured-at')).toBe(String(stamp));
    await act(async()=>{await vi.advanceTimersByTimeAsync(fraction?2:1);});
    expect(screen.queryByLabelText('Latest frame-bound simulated LiDAR hits')).toBeNull();
    expect(screen.getByText(/awaiting current scan/)).toBeTruthy();
    expect(screen.getByRole('img',{name:'Current Isaac Digital Twin render'})).toBeTruthy();
    expect(h.api.viewportCamera).not.toHaveBeenCalled();component.unmount();
  });
  it('does not relabel an old scan as current on a render before the next age tick',async()=>{
    vi.useFakeTimers();vi.setSystemTime(10000);
    const h=viewportHarness(),current=fleet();
    h.getState().frame!.lidar_overlay={robot_id:'a',connection_epoch:'connection-a',motion_epoch:'motion-a',origin_uv:[.25,.5],points_uv:[[.2,.3]],captured_at_ms:10000,source:'isaac_usd_aabb_rays',physical_authority:false};
    current.robots[0].scan={points:[[.1,.2]],source:'test'};
    const component=render(<TwinViewport api={h.api} robotFleet={current} onRobotSelect={vi.fn()}/>);
    await act(async()=>{await vi.advanceTimersByTimeAsync(0);});
    expect(screen.queryByLabelText('Latest frame-bound simulated LiDAR hits')).not.toBeNull();
    vi.setSystemTime(10750);
    fireEvent.change(screen.getByLabelText('LiDAR visualization'),{target:{value:'rays'}});
    expect(screen.queryByLabelText('Latest frame-bound simulated LiDAR hits')).toBeNull();
    expect(h.api.viewportCamera).not.toHaveBeenCalled();component.unmount();
  });
  it('has no connection circle and clears old scan geometry/status on sensor Off and mismatched epochs',async()=>{
    const h=viewportHarness(),stamp=Date.now();
    h.getState().frame!.lidar_overlay={robot_id:'a',connection_epoch:'connection-a',motion_epoch:'motion-a',origin_uv:[.25,.5],points_uv:[[.2,.3],[.3,.4]],captured_at_ms:stamp,source:'isaac_usd_aabb_rays',physical_authority:false};
    const current=fleet();current.robots[0].scan={points:[[.1,.2]],source:'test'};
    const component=render(<TwinViewport api={h.api} robotFleet={current} onRobotSelect={vi.fn()}/>);
    await screen.findByRole('button',{name:'Select Robot a in Twin'});
    expect(document.querySelector('.robot-frame-origin-dot')).toBeNull();
    const overlay=await screen.findByLabelText('Latest frame-bound simulated LiDAR hits');
    expect(overlay.querySelectorAll('circle')).toHaveLength(2);expect(overlay.querySelectorAll('line')).toHaveLength(0);
    fireEvent.change(screen.getByLabelText('LiDAR visualization'),{target:{value:'rays'}});
    expect(overlay.querySelectorAll('line')).toHaveLength(1);
    component.rerender(<TwinViewport api={h.api} robotFleet={{...current,robots:[{...current.robots[0],lidar_state:'OFF'}]}} onRobotSelect={vi.fn()}/>);
    expect(screen.queryByLabelText('Latest frame-bound simulated LiDAR hits')).toBeNull();expect(screen.getByText('LiDAR sensor: OFF')).toBeTruthy();
    component.rerender(<TwinViewport api={h.api} robotFleet={{...current,robots:[{...current.robots[0],motion_epoch:'new-motion'}]}} onRobotSelect={vi.fn()}/>);
    expect(screen.queryByLabelText('Latest frame-bound simulated LiDAR hits')).toBeNull();
    component.rerender(<TwinViewport api={h.api} robotFleet={current} onRobotSelect={vi.fn()}/>);
    vi.spyOn(Date,'now').mockReturnValue(stamp+800);
    await waitFor(()=>expect(screen.queryByLabelText('Latest frame-bound simulated LiDAR hits')).toBeNull());
    expect(screen.getByText(/awaiting current scan/)).toBeTruthy();
  });
  it('labels an estimated physical marker and selects its original robot identity without granting live status',async()=>{
    const h=viewportHarness(),select=vi.fn(),physical:RobotFleetRobot={...robot(),kind:'physical',connection_state:'DISCONNECTED',connection_epoch:null,
      live_heartbeat:false,capabilities:{drive:false,lidar:false},pose:null,battery:{voltage_v:null,percent:null,source:'unknown',age_ms:null},
      display_pose:{position_m:[.5,.7,0],source:'operator_estimate_not_localized',scene_revision:'revision',frame_id:'isaac_world',aligned:false}};
    render(<TwinViewport api={h.api} robotFleet={fleet([physical])} onRobotSelect={select}/>);
    const badge=await screen.findByRole('button',{name:'Select Robot a in Twin'});
    expect(badge.title).toBe('Robot a');
    expect(badge.getAttribute('aria-description')).toContain('visualization only, not sensor/world alignment');
    expect(badge.textContent).toBe('Robot a');
    expect(badge.querySelector('small')).toBeNull();
    expect(badge.querySelector('.robot-anchor-status.fresh')).toBeNull();
    fireEvent.click(badge);expect(select).toHaveBeenCalledWith('a');
    expect(physical.pose).toBeNull();expect(fleetRobotFresh(physical)).toBe(false);
  });
  it('fits badge coordinates to the actual letterboxed image and ignores invisible anchors',async()=>{
    const h=viewportHarness(),select=vi.fn();
    render(<TwinViewport api={h.api} robotFleet={fleet()} onRobotSelect={select}/>);
    const badge=await screen.findByRole('button',{name:'Select Robot a in Twin'});
    expect(screen.queryByRole('button',{name:'Select Robot b in Twin'})).toBeNull();
    const layer=screen.getByLabelText('Robots in current Isaac frame');
    expect(layer.style.left).toBe('100px');expect(layer.style.width).toBe('400px');expect(layer.style.height).toBe('400px');
    expect(badge.style.left).toBe('64px');expect(badge.style.top).toBe('202px');
    expect(badge.getAttribute('data-anchor-x')).toBe('100');expect(badge.getAttribute('data-anchor-y')).toBe('200');expect(badge.style.transform).toBe('none');
    fireEvent.click(badge);expect(select).toHaveBeenCalledWith('a');
  });
  it('removes click authority while camera movement is pending and when the App is disconnected',async()=>{
    const h=viewportHarness(),select=vi.fn();
    const view=render(<TwinViewport api={h.api} robotFleet={fleet()} onRobotSelect={select}/>);
    await screen.findByRole('button',{name:'Select Robot a in Twin'});
    h.setState({...h.getState(),camera_pending:true});
    await waitFor(()=>expect(screen.queryByRole('button',{name:'Select Robot a in Twin'})).toBeNull());
    view.rerender(<TwinViewport api={h.api} robotFleet={fleet()} onRobotSelect={select} appConnected={false}/>);
    expect(screen.queryByLabelText('Robots in current Isaac frame')).toBeNull();expect(select).not.toHaveBeenCalled();
  });
  it('renders names without cards or source-anchor decorations and keeps fitted positions after resize',async()=>{
    const h=viewportHarness(),select=vi.fn(),state=h.getState();
    h.setState({...state,frame:{...state.frame!,robot_anchors:[
      {robot_id:'a',screen_anchor_uv:[.6,.6],screen_bounds_uv:[.59,.59,.61,.61],visible:true},
      {robot_id:'b',screen_anchor_uv:[.725,.6],screen_bounds_uv:[.715,.59,.735,.61],visible:true}]}});
    render(<TwinViewport api={h.api} robotFleet={fleet()} onRobotSelect={select}/>);
    const alpha=await screen.findByRole('button',{name:'Select Robot a in Twin'}),beta=screen.getByRole('button',{name:'Select Robot b in Twin'});
    const bounds=(button:HTMLElement)=>({left:parseFloat(button.style.left),top:parseFloat(button.style.top),width:parseFloat(button.style.width),height:parseFloat(button.style.height)});
    expect(rectanglesOverlap(bounds(alpha),bounds(beta))).toBe(true);
    expect(screen.getByLabelText('Robots in current Isaac frame').querySelectorAll('svg')).toHaveLength(0);
    expect(alpha.querySelector('small,em')).toBeNull();expect(alpha.textContent).toBe('Robot a');
    fireEvent.click(alpha);fireEvent.click(beta);expect(select.mock.calls).toEqual([['a'],['b']]);
    h.setSlot(320,220);fireEvent.resize(window);
    const layer=screen.getByLabelText('Robots in current Isaac frame');expect(parseFloat(layer.style.width)).toBeCloseTo(220);expect(parseFloat(layer.style.left)).toBeCloseTo(50);
    expect(rectanglesOverlap(bounds(alpha),bounds(beta))).toBe(true);
    for(const button of [alpha,beta]){const badge=bounds(button);expect(badge.left).toBeGreaterThanOrEqual(0);expect(badge.top).toBeGreaterThanOrEqual(0);
      expect(badge.left+badge.width).toBeLessThanOrEqual(220);expect(badge.top+badge.height).toBeLessThanOrEqual(220);}
  });
  it('selects the actual current projected body through the letterboxed canvas, not empty space or an expired receipt',async()=>{
    const h=viewportHarness(),select=vi.fn();render(<TwinViewport api={h.api} robotFleet={fleet()} onRobotSelect={select}/>);
    const canvas=await screen.findByRole('img',{name:'Current Isaac Digital Twin render'});
    await screen.findByRole('button',{name:'Select Robot a in Twin'});
    fireEvent.click(canvas,{clientX:200,clientY:190});expect(select.mock.calls).toEqual([['a']]);
    select.mockClear();fireEvent.click(canvas,{clientX:20,clientY:190});expect(select).not.toHaveBeenCalled();
    vi.spyOn(Date,'now').mockReturnValue(h.getState().frame!.captured_at_ms+1100);
    fireEvent.click(canvas,{clientX:200,clientY:190});expect(select).not.toHaveBeenCalled();
  });
  it('resolves overlapping body projection hints to the closest visible anchor and rejects invalid coordinates',()=>{
    const anchors=[{robot_id:'a',screen_anchor_uv:[.4,.5] as [number,number],screen_bounds_uv:[.3,.4,.6,.6] as [number,number,number,number],visible:true},
      {robot_id:'b',screen_anchor_uv:[.55,.5] as [number,number],screen_bounds_uv:[.35,.4,.65,.6] as [number,number,number,number],visible:true}];
    expect(pickRobotAnchor(anchors,.56,.5)).toBe('b');expect(pickRobotAnchor(anchors,.39,.5)).toBe('a');
    expect(pickRobotAnchor(anchors,NaN,.5)).toBeNull();expect(pickRobotAnchor(anchors,-.1,.5)).toBeNull();
    expect(pickRobotAnchor(anchors.map(a=>({...a,visible:false})),.4,.5)).toBeNull();
  });
  it('never places old-engine anchors on a new-engine receipt while its decode is pending',async()=>{
    const h=viewportHarness();render(<TwinViewport api={h.api} robotFleet={fleet()} onRobotSelect={vi.fn()}/>);
    await screen.findByRole('button',{name:'Select Robot a in Twin'});
    let finish!:(value:ImageBitmap)=>void;
    vi.mocked(createImageBitmap).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}));
    const old=h.getState();h.setState({...old,frame:{...old.frame!,engine_session_id:'engine-two',robot_anchors:[{robot_id:'b',screen_anchor_uv:[.75,.5],screen_bounds_uv:[.7,.4,.8,.5],visible:true}]}});
    await waitFor(()=>expect(createImageBitmap).toHaveBeenCalledTimes(2));
    expect(screen.queryByLabelText('Robots in current Isaac frame')).toBeNull();
    await act(async()=>{finish(h.bitmap as unknown as ImageBitmap);});
    expect(await screen.findByRole('button',{name:'Select Robot b in Twin'})).toBeTruthy();
    expect(screen.queryByRole('button',{name:'Select Robot a in Twin'})).toBeNull();
  });
});

describe('fleet HTTP delivery (mocked supplementary)',()=>{
  const response=(body:object,status=200)=>({ok:status>=200&&status<300,status,json:async()=>body,headers:new Headers({'X-TwinPulse-Context':'fleet-context'})}) as Response;
  it.each([250,350])('bounds a held delivery to its original %ims while Stop bypasses that pending request',async lifetime=>{
    vi.useFakeTimers();
    const request=vi.fn(async(path:string,init?:RequestInit)=>{
      if(path==='/v1/product/session')return response({csrf_token:'csrf',context_id:'fleet-context',project_id:'project',project_switch:null});
      if(JSON.parse(String(init?.body)).action==='drive')return new Promise<Response>(()=>{});
      return response(fleet());
    });vi.stubGlobal('fetch',request);const api=new TwinPulseApi();await api.bootstrap();
    const drive:RobotFleetAction={action:'drive',request_id:crypto.randomUUID(),robot_id:'a',connection_epoch:'c',motion_epoch:'m',payload:{direction:'forward',sequence:1,expires_at_ms:Date.now()+lifetime}};
    const pending=api.robotFleetAction(drive).catch(error=>error);
    await api.robotFleetAction({...drive,action:'stop',request_id:crypto.randomUUID(),payload:{}});
    expect(request.mock.calls.filter(([path])=>path==='/v1/product/robot-fleet')).toHaveLength(2);
    await vi.advanceTimersByTimeAsync(lifetime);
    expect(await pending).toMatchObject({code:'fleet_input_expired'});
    const driveCall=request.mock.calls.find(([path,init])=>path==='/v1/product/robot-fleet'&&JSON.parse(String(init?.body)).action==='drive');
    expect(driveCall?.[1]?.signal?.aborted).toBe(true);
    expect(request.mock.calls.filter(([path])=>path==='/v1/product/robot-fleet')).toHaveLength(2);
  });
  it('does not retry unknown finite-command delivery and URL-encodes operation identifiers',async()=>{
    const request=vi.fn(async(path:string,init?:RequestInit)=>{
      if(path==='/v1/product/session')return response({csrf_token:'csrf',context_id:'fleet-context',project_id:'project',project_switch:null});
      if(init?.method==='POST')throw new Error('Unknown delivery');
      return response({schema_version:'robot-operation-1.0',operation_id:'saved/id',robot_id:'a',project_id:'project',events:[],manifest:{}});
    });vi.stubGlobal('fetch',request);const api=new TwinPulseApi();await api.bootstrap();
    await expect(api.robotFleetAction({action:'command',request_id:crypto.randomUUID(),robot_id:'a',connection_epoch:'c',motion_epoch:'m',payload:{text:'forward 10 cm'}})).rejects.toThrow('Unknown delivery');
    expect(request.mock.calls.filter(([path])=>path==='/v1/product/robot-fleet')).toHaveLength(1);
    await api.robotFleetOperation('saved/id');expect(request.mock.calls.at(-1)?.[0]).toBe('/v1/product/robot-fleet/operations/saved%2Fid');
  });
});
