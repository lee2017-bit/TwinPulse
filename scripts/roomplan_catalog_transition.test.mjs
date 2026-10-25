// SPDX-License-Identifier: Apache-2.0
import {test} from 'node:test';import assert from 'node:assert/strict';
import {classifyRoomplanResponses as gate} from './roomplan_response_gate.mjs';
import {COMMITTED_CAPTION} from './roomplan_edit_observation.mjs';
const s=n=>String(n).repeat(64),row=(path,method,status,start,body,request)=>({path,method,status,native_start_ms:start,native_timing:{responseEnd:1},at:start+1,body,...(request?{request}:{})});
function fixture(){
 const expected={mode:'change',operation_id:'edit-a',parent_revision:s(1),result_revision:s(2),preview_digest:s(3),project_id:'project-a',source_sha256:s(4)};
 const apply=row('/v1/product/scene-edit/apply','POST',202,90,{...expected,state:'BUILDING'}, {schema_version:'scene-edit-apply-2.0',environment_preview_id:'edit-a',preview_digest:s(3)});
 const committed=row('/v1/product/scene-edit/transaction','GET',200,100,{...expected,state:'COMMITTED',engine_acknowledged:true,durable_committed:true,current_frame:true});
 const rejected=row('/v1/product/scene-edit/obstacle-feedback','GET',409,110,{error:{code:'obstacle_metadata_not_ready'}});
 const published=row('/v1/product/workflow','GET',200,120,{site_draft:{revision:s(2),scene_state_sha256:s(5),input_revision:s(6)}});
 const recovered=row(rejected.path,'GET',200,123,{context:{project_id:'project-a',current_scene_revision:s(2),current_state_sha256:s(5),input_revision:s(6),physical_authority:false}});
 const environment=row('/v1/product/environment','GET',200,125,{status:'imported',project_id:'project-a',source_sha256:s(4),scene_revision:s(2)});
 return {phase:'edit',responses:[apply,committed,rejected,published,recovered,environment],edit_transactions:[{started_at_ms:80,confirmed_at_ms:130,expected,
  ui:{caption:COMMITTED_CAPTION,undo_enabled:true,preview_visible:false,frame:{live:true,scene_revision:s(2),stage_epoch:'stage',frame_id:1,frame_age_ms:1}},
  catalog_ui:{at:130,project_id:'project-a',scene_revision:s(2),context_controls_enabled:true,alert_count:0}}]};
}
test('classifies only exact read-only transition with committed scene, published digest and clean UI binding before any next mutation',()=>{const out=gate(fixture());assert.equal(out.status,'PASS');assert.equal(out.expected_catalog_transitions.length,1);});
test('independent read requests may overlap while the completed exact metadata response precedes catalog recovery',()=>{const f=fixture();f.responses[3].native_start_ms=105;f.responses[3].native_timing.responseEnd=16;assert.equal(gate(f).status,'PASS');});
for(const kind of ['wrong-phase','post','wrong-code','no-ui','disabled-ui','alert','no-recovery','wrong-project','wrong-revision','wrong-state','wrong-input','no-published','bad-native-time','overlapping-mutation','bad-commit','wrong-frame','missing-start','nan-confirmed','missing-ui-time','nan-ui-time','missing-both-inputs','old-published','mutation-before-dom','project-switch-before-dom','dom-after-confirmed','recovery-before-rejection'])test('reject catalog transition '+kind,()=>{
 const f=fixture(),r=f.responses,tx=f.edit_transactions[0];
 if(kind==='wrong-phase')f.phase='sim';if(kind==='post')r[2].method='POST';if(kind==='wrong-code')r[2].body.error.code='other';
 if(kind==='no-ui')delete tx.catalog_ui;if(kind==='disabled-ui')tx.catalog_ui.context_controls_enabled=false;if(kind==='alert')tx.catalog_ui.alert_count=1;
 if(kind==='no-recovery')r.splice(4,1);if(kind==='wrong-project')r[4].body.context.project_id='other';if(kind==='wrong-revision')r[4].body.context.current_scene_revision=s(7);
 if(kind==='wrong-state')r[4].body.context.current_state_sha256=s(7);if(kind==='wrong-input')r[4].body.context.input_revision=s(7);if(kind==='no-published')r.splice(3,1);
 if(kind==='bad-native-time')r[2].native_start_ms=NaN;if(kind==='overlapping-mutation')r.push(row('/v1/product/environment/action','POST',200,115,{}));
 if(kind==='bad-commit')r[1].body.durable_committed=false;if(kind==='wrong-frame')tx.ui.frame.scene_revision=s(7);
 if(kind==='missing-start')delete tx.started_at_ms;if(kind==='nan-confirmed')tx.confirmed_at_ms=NaN;if(kind==='missing-ui-time')delete tx.catalog_ui.at;if(kind==='nan-ui-time')tx.catalog_ui.at=NaN;
 if(kind==='missing-both-inputs'){delete r[3].body.site_draft.input_revision;delete r[4].body.context.input_revision;}
 if(kind==='old-published')r[3].native_start_ms=105;if(kind==='mutation-before-dom')r.push(row('/v1/product/environment/action','POST',200,128,{}));
 if(kind==='project-switch-before-dom')r.push(row('/v1/product/conversation','POST',200,128,{}));
 if(kind==='dom-after-confirmed')tx.catalog_ui.at=131;if(kind==='recovery-before-rejection')r[4].native_start_ms=108;
 assert.equal(gate(f).status,'FAIL');
});
