// SPDX-License-Identifier: Apache-2.0
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {RobotTimingSettings,type TimingSettings,type TimingFields} from './RobotTimingSettings';
afterEach(cleanup);
const fields:TimingFields=Object.fromEntries(Object.entries({input_ttl_ms:350,odom_interval_ms:300,sensor_source_ms:200,sensor_receipt_ms:200,
  guard_receipt_ms:200,wheel_interval_ms:200,output_timeout_ms:400,operator_presence_ms:500,native_receipt_ms:350,tracking_result_ms:600,
  icp_compute_ms:80,ros_service_ms:500,input_renewal_ms:100,input_window_ms:50}).map(([k,v])=>[k,{minimum_ms:20,maximum_ms:2000,preset_ms:v,label:k}]));
const settings:TimingSettings={profile:{schema_version:'robot-timing-profile-1.0',robot_id:'a'.repeat(32),binding_sha256:'b'.repeat(64),mode:'unmeasured',
  values:Object.fromEntries(Object.entries(fields).map(([k,v])=>[k,v.preset_ms])),adaptive:false,qualification:'ENGINEERING_ONLY_NOT_BRAKING_OR_DRIVING_QUALIFICATION',evidence:null},
  profile_sha256:'c'.repeat(64),apply_policy:'NEXT_EXPLICIT_CONNECTION_ONLY',last_measurement_origin:null,measurement:null,recommendation:null};
describe('per-robot timing settings (supplementary component tests)',()=>{
  it('uses compact English actions while preserving complete accessible names and local import',()=>{
    const {container}=render(<RobotTimingSettings settings={settings} fields={fields} busy={false} onSave={vi.fn()} onImport={vi.fn()} onRecalculate={vi.fn()} onApply={vi.fn()}/>);
    expect(screen.getByRole('button',{name:'Recalculate parameters'}).textContent).toBe('Recalculate');
    expect(screen.getByRole('button',{name:'Apply recommended values'}).textContent).toBe('Apply recommended');
    expect(screen.getByRole('button',{name:'Import measurements'})).toBeTruthy();
    expect((container.querySelector('.timing-help') as HTMLDetailsElement).open).toBe(false);
    expect((screen.getByLabelText('Import recorded timing measurements (local JSON, no robot connection)') as HTMLInputElement).hidden).toBe(true);
  });
  it('labels unmeasured state and does not imply a runtime change',()=>{
    render(<RobotTimingSettings settings={settings} fields={fields} busy={false} onSave={vi.fn()} onImport={vi.fn()} onRecalculate={vi.fn()} onApply={vi.fn()}/>);
    expect(screen.getByText(/No first measurement yet/).textContent).toContain('not measured defaults');
    expect(screen.getByLabelText('Runtime timing readback').textContent).toContain('not confirmed');
    expect((screen.getByRole('button',{name:'Save timing settings'}) as HTMLButtonElement).disabled).toBe(true);
  });
  it('rejects cross-budget conflicts and saves a consistent custom policy',async()=>{
    const save=vi.fn().mockResolvedValue(true);
    render(<RobotTimingSettings settings={settings} fields={fields} busy={false} onSave={save} onImport={vi.fn()} onRecalculate={vi.fn()} onApply={vi.fn()}/>);
    fireEvent.change(screen.getByLabelText('input_ttl_ms (ms)'),{target:{value:'500'}});
    expect((screen.getByRole('button',{name:'Save timing settings'}) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText('output_timeout_ms (ms)'),{target:{value:'600'}});
    fireEvent.change(screen.getByLabelText('operator_presence_ms (ms)'),{target:{value:'700'}});
    fireEvent.click(screen.getByRole('button',{name:'Save timing settings'}));
    await waitFor(()=>expect(save).toHaveBeenCalledWith(expect.objectContaining({input_ttl_ms:500,output_timeout_ms:600}),'custom'));
  });
  it('cancel restores exact saved values instead of importing a recommendation silently',()=>{
    render(<RobotTimingSettings settings={settings} fields={fields} busy={false} onSave={vi.fn()} onImport={vi.fn()} onRecalculate={vi.fn()} onApply={vi.fn()}/>);
    fireEvent.change(screen.getByLabelText('odom_interval_ms (ms)'),{target:{value:'700'}});
    fireEvent.click(screen.getByRole('button',{name:'Cancel timing changes'}));
    expect((screen.getByLabelText('odom_interval_ms (ms)') as HTMLInputElement).value).toBe('300');
  });
  it('recalculates only on click and applies only with a separate explicit click',async()=>{
    const save=vi.fn(),recalculate=vi.fn().mockResolvedValue(true),apply=vi.fn().mockResolvedValue(true);
    const measured={...settings,measurement_operation_id:'d'.repeat(32),measurement_sha256:'e'.repeat(64),measurement:{duration_s:30,metrics:{}}};
    const props={fields,busy:false,onSave:save,onImport:vi.fn(),onRecalculate:recalculate,onApply:apply};
    const view=render(<RobotTimingSettings {...props} settings={measured}/>);
    expect((screen.getByRole('button',{name:'Apply recommended values'}) as HTMLButtonElement).disabled).toBe(true);
    expect(recalculate).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button',{name:'Recalculate parameters'}));
    await waitFor(()=>expect(recalculate).toHaveBeenCalledTimes(1));
    expect(save).not.toHaveBeenCalled();expect(apply).not.toHaveBeenCalled();
    const rec={...measured,recommendation_sha256:'f'.repeat(64),recommendation_origin:'MANUAL_RECALCULATION',recommendation:{profile:{...settings.profile,values:{...settings.profile.values,output_timeout_ms:450}},capped_fields:[],coverage:'PROVISIONAL',warning:'Not physical qualification'}};
    view.rerender(<RobotTimingSettings {...props} settings={rec}/>);
    const comparison=screen.getByRole('region',{name:'Parameter recommendation'}).querySelector('table')!;
    expect(comparison.style.minWidth).toBe('0px');expect(comparison.style.tableLayout).toBe('fixed');
    expect((screen.getByLabelText('output_timeout_ms (ms)') as HTMLInputElement).value).toBe('400');
    fireEvent.click(screen.getByRole('button',{name:'Apply recommended values'}));
    await waitFor(()=>expect(apply).toHaveBeenCalledWith('f'.repeat(64)));
    view.rerender(<RobotTimingSettings {...props} settings={{...rec,measurement_operation_id:'a'.repeat(32)}}/>);
    expect(recalculate).toHaveBeenCalledTimes(1);expect(apply).toHaveBeenCalledTimes(1);
  });
  it('preserves unsaved registered edits across recalculation and blocks overwriting them',()=>{
    const rec={...settings,measurement_operation_id:'d'.repeat(32),measurement:{duration_s:30,metrics:{}},recommendation_sha256:'f'.repeat(64),
      recommendation:{profile:settings.profile,capped_fields:[],coverage:'PROVISIONAL',warning:'Not physical qualification'}};
    const props={fields,busy:false,onSave:vi.fn(),onImport:vi.fn(),onRecalculate:vi.fn(),onApply:vi.fn()};
    const view=render(<RobotTimingSettings {...props} settings={rec}/>);
    fireEvent.change(screen.getByLabelText('odom_interval_ms (ms)'),{target:{value:'325'}});
    view.rerender(<RobotTimingSettings {...props} settings={{...rec,recommendation_sha256:'e'.repeat(64)}}/>);
    expect((screen.getByLabelText('odom_interval_ms (ms)') as HTMLInputElement).value).toBe('325');
    expect((screen.getByRole('button',{name:'Apply recommended values'}) as HTMLButtonElement).disabled).toBe(true);
  });
});
