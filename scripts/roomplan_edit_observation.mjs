// SPDX-License-Identifier: Apache-2.0
// Pure recorder checks of original responses and the current UI. No API calls.
const sha=value=>typeof value==='string'&&/^[a-f0-9]{64}$/.test(value);
const object=value=>value&&typeof value==='object'&&!Array.isArray(value)?value:{};
export const COMMITTED_CAPTION='Edit COMMITTED · Engine ACK confirmed · Saved yes · Current frame confirmed';

export function checkedSpacePreview(original,{mode,parent,project,source,previousOperation=null}){
 const body=object(original.body),preview=object(body.preview),operation=object(preview.operation),request=object(original.request);
 if(original.status!==200||!['model_review','move_preview','undo_preview'].includes(request.action)||
    request.expected_scene_revision!==parent||body.project_id!==project||body.source_sha256!==source||body.scene_revision!==parent||
    operation.mode!==mode||typeof operation.operation_id!=='string'||!operation.operation_id||operation.operation_id===previousOperation||
    preview.parent_revision!==parent||operation.parent_revision!==parent||!sha(preview.result_revision)||preview.result_revision===parent||
    operation.result_revision!==preview.result_revision||!sha(preview.preview_digest)||
    (mode==='undo'&&request.action!=='undo_preview')||(mode==='change'&&request.action==='undo_preview'))
  throw Error('Original space preview does not match the expected operation and parent revision.');
 return {mode,operation_id:operation.operation_id,parent_revision:parent,result_revision:preview.result_revision,
  preview_digest:preview.preview_digest,project_id:project,source_sha256:source};
}

export function checkedSpaceApply(expected,original){
 const request=object(original.request),body=object(original.body);
 if(![200,202].includes(original.status)||request.schema_version!=='scene-edit-apply-2.0'||
    request.environment_preview_id!==expected.operation_id||request.preview_digest!==expected.preview_digest||
    body.operation_id!==expected.operation_id||body.parent_revision!==expected.parent_revision||body.result_revision!==expected.result_revision||
    body.preview_digest!==expected.preview_digest||body.error||
    !['STAGED','PREPARED','BUILDING','ENGINE_ACKNOWLEDGED','COMMITTED'].includes(body.state))
  throw Error('Original Apply response does not match this reviewed space operation.');
 return original;
}

export function spaceCommitObservation(expected,rows,ui){
 const records=rows.filter(value=>value&&typeof value==='object');
 const applies=records.filter(r=>r.method==='POST'&&r.path==='/v1/product/scene-edit/apply'&&
  object(r.request).environment_preview_id===expected.operation_id);
 if(!applies.length)return null;
 if(applies.length!==1)throw Error('Duplicate Apply observed; no automatic Apply retry is accepted.');
 checkedSpaceApply(expected,applies[0]);
 const start=records.indexOf(applies[0]);
 const matching=records.slice(start+1).filter(r=>r.method==='GET'&&r.path==='/v1/product/scene-edit/transaction'&&
  r.status===200&&object(r.body).operation_id===expected.operation_id);
 for(const row of matching){
  const body=row.body;
  if(body.parent_revision!==expected.parent_revision||body.result_revision!==expected.result_revision)
   throw Error('Observed transaction changed the expected space revision chain.');
  if(body.error||['ROLLED_BACK','CANCELLED_BEFORE_DISPATCH','ENGINE_STATE_UNKNOWN'].includes(body.state))
   throw Error('Observed space transaction did not commit: '+body.state);
 }
 const committed=matching.find(r=>r.body.state==='COMMITTED'&&r.body.engine_acknowledged===true&&
  r.body.durable_committed===true&&r.body.current_frame===true);
 if(!committed)return null;
 const environment=records.slice(records.indexOf(committed)+1).find(r=>r.method==='GET'&&r.path==='/v1/product/environment'&&r.status===200&&
  object(r.body).status==='imported'&&r.body.project_id===expected.project_id&&r.body.source_sha256===expected.source_sha256&&
  r.body.scene_revision===expected.result_revision);
 if(!environment)return null;
 const frame=object(ui.frame);
 if(ui.caption!==COMMITTED_CAPTION||ui.undo_enabled!==true||ui.preview_visible!==false||
    frame.live!==true||frame.scene_revision!==expected.result_revision||!frame.stage_epoch||
    !Number.isFinite(frame.frame_id)||frame.frame_id<=0||!Number.isFinite(frame.frame_age_ms)||frame.frame_age_ms<0||frame.frame_age_ms>=1000)return null;
 return {expected,apply:applies[0],committed,environment,ui};
}
