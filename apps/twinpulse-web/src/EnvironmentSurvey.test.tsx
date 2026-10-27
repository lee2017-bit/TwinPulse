// SPDX-License-Identifier: Apache-2.0
import {render,screen,waitFor,fireEvent,cleanup} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
import {EnvironmentSurvey,type SurveyState} from './EnvironmentSurvey';
import type {TwinPulseApi} from './api';
import type {EnvironmentPhotoCandidate,EnvironmentPhotoProposal} from './environment-types';
afterEach(cleanup);
const snapshot=(reviewRevision='current'):SurveyState=>({context:{scene_revision:'current'},references:[],collections:[],job:{job_id:'job',status:'GEOMETRIC_REVIEW',reason:null},review_digest:'digest',visible:false,registration_active:false,
  review:{context:{scene_revision:reviewRevision},status:'GEOMETRIC_REVIEW',source:'TASK',view_count:3,maximum_view_baseline_m:.4,physical_authority:false,
    obstacle_candidates:[{candidate_id:'Residual_a',position_xy_m:[1,1],observed_extent_xy_m:[.3,.3],uncertainty_m:.1,return_count:40,view_indices:[0,1,2],view_baseline_m:.4}]}});
const apiFor=(value:SurveyState)=>({context:'owner',environmentSurvey:vi.fn(async()=>value),environmentSurveyAction:vi.fn(async()=>value),robotFleet:vi.fn(async()=>({robots:[]}))}) as unknown as TwinPulseApi;
it('Current metadata does not make a previous-revision review actionable',async()=>{
 const api=apiFor(snapshot('previous'));
 render(<EnvironmentSurvey api={api} revision="current" onPreview={vi.fn()} onInvalidate={vi.fn()}/>);
 await screen.findByText('Survey: GEOMETRIC_REVIEW');
 expect(screen.getByRole('button',{name:'Show survey'}).matches(':disabled')).toBe(true);
 expect(screen.getByRole('button',{name:'Preview missing obstacle'}).matches(':disabled')).toBe(true);
});
it('Changes to a reviewed obstacle draft invalidate the old common preview',async()=>{
 const api=apiFor(snapshot()),invalidate=vi.fn();
 render(<EnvironmentSurvey api={api} revision="current" onPreview={vi.fn()} onInvalidate={invalidate}/>);
 await screen.findByText('Survey: GEOMETRIC_REVIEW');
 await waitFor(()=>expect(screen.getByLabelText('Survey obstacle height').matches(':disabled')).toBe(false));
 const before=invalidate.mock.calls.length;fireEvent.change(screen.getByLabelText('Survey obstacle height'),{target:{value:'0.8'}});
 await waitFor(()=>expect(invalidate.mock.calls.length).toBeGreaterThan(before));
 expect(api.environmentSurveyAction).not.toHaveBeenCalled();
});
it('Photo association lists only addable candidates and maps furniture to an unknown box',async()=>{
 const row=(id:string,kind:string,label:string,overlay_kind:string|null):EnvironmentPhotoCandidate=>({id,kind,label,overlay_kind,addable:overlay_kind!==null,possible_duplicates:[],
  confidence:.8,bbox:[.1,.1,.5,.5],description:'Seen in the photo.',dimensions_m:[.35,.3,.4],dimensions_basis:'catalog_estimate',duplicate_check_required:true});
 const photo:EnvironmentPhotoProposal={status:'ready',error:null,job_id:'photo-job',candidates:[row('Candidate_1','basket','Basket','basket'),
  row('Candidate_2','sofa','Couch','unknown'),row('Candidate_3','window_blind','Blind',null)]};
 render(<EnvironmentSurvey api={apiFor(snapshot())} revision="current" photo={photo} onPreview={vi.fn()} onInvalidate={vi.fn()}/>);
 await screen.findByText('Survey: GEOMETRIC_REVIEW');
 const select=screen.getByLabelText('Survey photo association');
 expect([...select.querySelectorAll('option')].map(o=>o.textContent)).toEqual(['No photo class · manual review','Basket · basket','Couch · sofa']);
 fireEvent.change(select,{target:{value:'Candidate_2'}});
 expect(screen.getByLabelText('Survey obstacle kind')).toHaveProperty('value','unknown');expect(screen.getByLabelText('Survey obstacle label')).toHaveProperty('value','Couch');
 fireEvent.change(select,{target:{value:'Candidate_1'}});expect(screen.getByLabelText('Survey obstacle kind')).toHaveProperty('value','basket');
});
