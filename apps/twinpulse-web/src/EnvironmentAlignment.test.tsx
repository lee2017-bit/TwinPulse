// SPDX-License-Identifier: Apache-2.0
import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {describe,it,expect,vi} from 'vitest';
import type {TwinPulseApi} from './api';
import {EnvironmentAlignment,type AlignmentState,type AlignmentAction} from './EnvironmentAlignment';
const empty:AlignmentState={context:{scene_revision:'revision'},references:[{id:'wall',label:'Wall1',length_m:4,ends_m:[[0,0],[4,0]]}],job:null,review:null,review_digest:null,visible:false,physical_authority:false,world_registration_verified:false};
function api(state=empty){return {context:'context',alignment:vi.fn(async()=>state),robotFleet:vi.fn(async()=>({robots:[{robot_id:'sim',label:'SIM robot',kind:'sim'}]})),alignmentAction:vi.fn(async(_body:AlignmentAction)=>state)};}
describe('separate scan alignment review',()=>{
  it('does not fill a measured length or a pose from the source geometry',async()=>{
    const client=api();render(<EnvironmentAlignment api={client as unknown as TwinPulseApi} revision="revision"/>);
    await screen.findByRole('option',{name:/Wall1/});
    fireEvent.change(screen.getByLabelText('Alignment reference wall'),{target:{value:'wall'}});
    expect((screen.getByLabelText('Alignment reference length') as HTMLInputElement).value).toBe('');
    expect((screen.getByLabelText('Alignment X (m)') as HTMLInputElement).value).toBe('');
    expect((screen.getByRole('button',{name:'Show aligned scan'}) as HTMLButtonElement).disabled).toBe(true);expect(client.alignmentAction).not.toHaveBeenCalled();
  });
  it('submits explicit initial pose/reference and does not call a fleet mutation',async()=>{
    const client=api();render(<EnvironmentAlignment api={client as unknown as TwinPulseApi} revision="revision"/>);
    await screen.findByRole('option',{name:/Wall1/});await screen.findByRole('option',{name:/SIM robot/});
    for(const [label,value] of [['Alignment robot','sim'],['Alignment reference wall','wall'],['Alignment X (m)','1.2'],['Alignment Y (m)','1.1'],['Alignment reference length','4'],['Alignment reference basis','SIM_ONLY']])
      fireEvent.change(screen.getByLabelText(label),{target:{value}});
    fireEvent.click(screen.getByRole('button',{name:'Check alignment'}));
    await waitFor(()=>expect(client.alignmentAction).toHaveBeenCalledOnce());
    expect(client.alignmentAction.mock.calls[0]![0]).toMatchObject({action:'check',expected_scene_revision:'revision',initial_pose:[1.2,1.1,0],reference_length_m:4,reference_basis:'SIM_ONLY',robot_id:'sim'});
  });
  it('keeps scale mismatch and held result out of Show',async()=>{
    const held={...empty,job:{job_id:'job',status:'HELD',reason:'SCALE_MISMATCH'},review_digest:'digest',review:{status:'HELD',source:'SAVED',reference:{status:'SCALE_MISMATCH',ratio:1.1,basis:'OPERATOR_REFERENCE'},match:{body_pose:[1,1,0],validation:{mean_error_m:.03,inlier_fraction:.9,normal_diversity:.4}},temporal_validation:[],physical_authority:false}} as AlignmentState;
    render(<EnvironmentAlignment api={api(held) as unknown as TwinPulseApi} revision="revision"/>);
    await screen.findByText(/Alignment: HELD/);expect((screen.getByRole('button',{name:'Show aligned scan'}) as HTMLButtonElement).disabled).toBe(true);
  });
});
