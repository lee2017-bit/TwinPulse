// SPDX-License-Identifier: Apache-2.0
// Supplementary recorder unit tests only; no App, model, Isaac or robot calls.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {checkedSpacePreview,checkedSpaceApply,spaceCommitObservation,COMMITTED_CAPTION} from './roomplan_edit_observation.mjs';
const initial='a'.repeat(64),moved='b'.repeat(64),undone='c'.repeat(64),source='d'.repeat(64),digest='e'.repeat(64);
function fixture(mode='change'){
 const parent=mode==='change'?initial:moved,result=mode==='change'?moved:undone,id=mode==='change'?'move-operation':'undo-operation';
 const original={status:200,request:{action:mode==='change'?'model_review':'undo_preview',expected_scene_revision:parent},
  body:{project_id:'project',source_sha256:source,scene_revision:parent,preview:{parent_revision:parent,result_revision:result,preview_digest:digest,
   operation:{operation_id:id,mode,parent_revision:parent,result_revision:result}}}};
 const expected=checkedSpacePreview(original,{mode,parent,project:'project',source,previousOperation:mode==='undo'?'move-operation':null});
 const apply={method:'POST',path:'/v1/product/scene-edit/apply',status:202,request:{schema_version:'scene-edit-apply-2.0',environment_preview_id:id,preview_digest:digest},
  body:{operation_id:id,state:'STAGED',parent_revision:parent,result_revision:result,preview_digest:digest,error:null}};
 const commit={method:'GET',path:'/v1/product/scene-edit/transaction',status:200,body:{operation_id:id,state:'COMMITTED',parent_revision:parent,result_revision:result,
  engine_acknowledged:true,durable_committed:true,current_frame:true,error:null}};
 const environment={method:'GET',path:'/v1/product/environment',status:200,body:{project_id:'project',source_sha256:source,status:'imported',scene_revision:result}};
 const ui={caption:COMMITTED_CAPTION,undo_enabled:true,preview_visible:false,frame:{live:true,scene_revision:result,stage_epoch:'stage',frame_id:42,frame_age_ms:50}};
 return {expected,original,rows:[apply,commit,environment],ui};
}
test('each explicit Apply and Undo requires its own original transaction and current UI',()=>{
 for(const mode of ['change','undo']){const f=fixture(mode);assert.equal(spaceCommitObservation(f.expected,f.rows,f.ui).committed.body.operation_id,f.expected.operation_id);}
});
test('previous COMMITTED caption and old operation GET cannot complete staged Undo',()=>{
 const f=fixture('undo');f.rows=[f.rows[0],fixture().rows[1],{method:'GET',path:'/v1/product/scene-edit/transaction',status:200,body:null},f.rows[2]];
 assert.equal(spaceCommitObservation(f.expected,f.rows,f.ui),null);
});
for(const kind of ['missing_post','null_post','wrong_post_id','wrong_post_digest','null_commit','no_ack','not_saved','old_frame','wrong_parent','wrong_result','old_environment','wrong_project','wrong_source','locked_ui','preview_remains','old_caption','stale_canvas','old_canvas','duplicate_post','commit_before_post'])
 test('reject recorder false completion: '+kind,()=>{
  const f=fixture('undo'),[apply,commit,environment]=f.rows;
  if(kind==='missing_post')f.rows.shift();
  if(kind==='null_post')apply.body=null;
  if(kind==='wrong_post_id')apply.body.operation_id='move-operation';
  if(kind==='wrong_post_digest')apply.request.preview_digest='0'.repeat(64);
  if(kind==='null_commit')commit.body=null;
  if(kind==='no_ack')commit.body.engine_acknowledged=false;
  if(kind==='not_saved')commit.body.durable_committed=false;
  if(kind==='old_frame')commit.body.current_frame=false;
  if(kind==='wrong_parent')commit.body.parent_revision=initial;
  if(kind==='wrong_result')commit.body.result_revision=moved;
  if(kind==='old_environment')environment.body.scene_revision=moved;
  if(kind==='wrong_project')environment.body.project_id='other';
  if(kind==='wrong_source')environment.body.source_sha256='0'.repeat(64);
  if(kind==='locked_ui')f.ui.undo_enabled=false;
  if(kind==='preview_remains')f.ui.preview_visible=true;
  if(kind==='old_caption')f.ui.caption='Edit BUILDING';
  if(kind==='stale_canvas')f.ui.frame.frame_age_ms=1000;
  if(kind==='old_canvas')f.ui.frame.scene_revision=moved;
  if(kind==='duplicate_post')f.rows.push(structuredClone(apply));
  if(kind==='commit_before_post')f.rows=[commit,apply,environment];
  let result;try{result=spaceCommitObservation(f.expected,f.rows,f.ui);}catch{result=null;}
  assert.equal(result,null);
 });
test('a reused operation identity or old Undo parent fails preview admission',()=>{
 const f=fixture('undo');
 assert.throws(()=>checkedSpacePreview(f.original,{mode:'undo',parent:initial,project:'project',source}));
 assert.throws(()=>checkedSpacePreview(f.original,{mode:'undo',parent:moved,project:'project',source,previousOperation:'undo-operation'}));
});
test('null unrelated observations preserve records and do not certify an Apply',()=>{
 const f=fixture(),before=structuredClone(f);f.rows.splice(1,0,{method:'GET',path:'/v1/product/scene-edit/transaction',status:200,body:null});
 assert.ok(spaceCommitObservation(f.expected,f.rows,f.ui));assert.deepEqual(f.rows[0],before.rows[0]);
 assert.throws(()=>checkedSpaceApply(f.expected,{...f.rows[0],body:null}));
});
