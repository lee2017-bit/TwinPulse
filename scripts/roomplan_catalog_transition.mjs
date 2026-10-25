// SPDX-License-Identifier: Apache-2.0
// Read-only classification of a guarded catalog transition, never a blanket 409 exemption.
import {spaceCommitObservation,COMMITTED_CAPTION} from './roomplan_edit_observation.mjs';
const hash=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const timed=r=>Number.isFinite(r?.native_start_ms)&&Number.isFinite(r?.native_timing?.responseEnd)&&r.native_timing.responseEnd>=0;
export function catalogTransition(result,rejected){
 if(!['edit','ai-edit'].includes(result.phase)||rejected.path!=='/v1/product/scene-edit/obstacle-feedback'||rejected.method!=='GET'||rejected.status!==409||rejected.body?.error?.code!=='obstacle_metadata_not_ready'||!timed(rejected))return null;
 const rows=result.responses??[],end=r=>r.native_start_ms+r.native_timing.responseEnd;
 for(const tx of result.edit_transactions??[]){
  const expected=tx.expected,ui=tx.catalog_ui;
  if(!expected||!ui||![tx.started_at_ms,tx.confirmed_at_ms,ui.at].every(Number.isFinite)||tx.started_at_ms<0||tx.started_at_ms>rejected.native_start_ms||tx.confirmed_at_ms<ui.at||ui.at<end(rejected)||ui.alert_count!==0||ui.context_controls_enabled!==true||ui.project_id!==expected.project_id||ui.scene_revision!==expected.result_revision||tx.ui?.caption!==COMMITTED_CAPTION)continue;
  let checked;try{checked=spaceCommitObservation(expected,rows,tx.ui);}catch{continue;}if(!checked)continue;
  const recovered=rows.find(r=>r.path===rejected.path&&r.method==='GET'&&r.status===200&&timed(r)&&r.native_start_ms>=end(rejected)&&end(r)<=ui.at&&r.body?.context?.project_id===expected.project_id&&r.body.context.current_scene_revision===expected.result_revision&&hash(r.body.context.current_state_sha256)&&hash(r.body.context.input_revision)&&r.body.context.physical_authority===false);
  if(!recovered)continue;
  const c=recovered.body.context;
  // Independent GETs may overlap on the wire. Bind the completed matching
  // response, not an invented ordering of server-internal publication work.
  const published=rows.find(r=>r.path==='/v1/product/workflow'&&r.method==='GET'&&r.status===200&&timed(r)&&end(r)>=end(rejected)&&end(r)<=recovered.native_start_ms&&r.body?.site_draft?.revision===c.current_scene_revision&&r.body.site_draft.scene_state_sha256===c.current_state_sha256&&r.body.site_draft.input_revision===c.input_revision);
  if(!published||rows.some(r=>r.method==='POST'&&r.path.startsWith('/v1/product/')&&(!timed(r)||r.native_start_ms>rejected.native_start_ms&&r.native_start_ms<=ui.at)))continue;
  return {classification:'READ_ONLY_CATALOG_TRANSITION_RECOVERED_BEFORE_NEXT_MUTATION',raw_http_status:409,error_code:rejected.body.error.code,operation_id:expected.operation_id,project_id:expected.project_id,scene_revision:c.current_scene_revision,state_sha256:c.current_state_sha256,rejected_native_start_ms:rejected.native_start_ms,recovered_native_start_ms:recovered.native_start_ms,ui_observed_at_ms:ui.at};
 }
 return null;
}
