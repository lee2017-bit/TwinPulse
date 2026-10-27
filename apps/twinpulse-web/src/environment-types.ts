// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import type {Operation} from './engine-contracts';
import type {SceneEditPreview,WorkflowState} from './types';

export interface EnvironmentProposal {
  job_id:string;request_id:string;status:'running'|'ready'|'failed'|'cancelled';
  source_revision:string;model_id:string|null;error:string|null;preview?:SceneEditPreview;
  suggestion?:{translation_m:[number,number,0];explanation:string};
}
export interface EnvironmentState {
  project_id:string;
  status:'empty'|'inspecting'|'ready'|'imported'|'failed';
  job_id:string|null;error:string|null;source_name:string|null;source_sha256:string|null;
  units_basis:string|null;
  floor_triangles_xy?:[number,number][][];
  objects:{id:string;category:string;label:string;position_m:[number,number,number];dimensions_m?:[number,number,number];
    added?:boolean;uncertainty_m?:number;risk?:string;evidence?:{basis:string;source_name:string|null;sha256:string|null;alignment_verified:false}}[];
  scene_revision:string|null;
  metadata_basis?:'current_review_not_disk_validation'|null;
  workflow?:WorkflowState;operation?:Operation;preview?:SceneEditPreview;
  proposal?:EnvironmentProposal;
  photo_proposal?:EnvironmentPhotoProposal|null;
}
// A local placement beside the scanned/added object the photo model named ('near'); never a model coordinate or an alignment.
export interface EnvironmentPhotoPlacement {position_m:[number,number,number];yaw_deg:number;dimensions_m:[number,number,number];uncertainty_m:number;
  anchor:string;gap_m:number;side:string;basis:'photo_near_anchor';alignment_verified:false;envelope_xy:[number,number][]}
export interface EnvironmentPhotoCandidate {id:string;kind:string;label:string;confidence:number;bbox:[number,number,number,number];description:string;dimensions_m:[number,number,number];dimensions_basis:'catalog_estimate';
  overlay_kind:string|null;addable:boolean;possible_duplicates:string[];duplicate_check_required:true;
  near?:string|null;suggested?:EnvironmentPhotoPlacement|null;suggestion_reason?:string|null;batch_addable?:boolean}
export interface EnvironmentPhotoProposal {job_id?:string;request_id?:string;status:'running'|'ready'|'failed'|'cancelled';error:string|null;
  model_id?:string|null;photo?:{source_name:string;sha256:string};source_revision?:string;response_sha256?:string|null;
  explanation?:string|null;candidates:EnvironmentPhotoCandidate[]}
export interface EnvironmentCandidateRef {job_id:string;candidate_id:string}
export interface EnvironmentObstacle {kind:string;label:string;position_xy_m:[number,number];dimensions_m:[number,number,number];yaw_deg:number;uncertainty_m:number}
export type EnvironmentAction =
  | {action:'inspect';request_id:string;attachment:{name:string;bytes_base64:string};units:'m'|'cm'|'mm'|null}
  | {action:'adopt';request_id:string;job_id:string}
  | {action:'build';request_id:string}
  | {action:'move_preview';request_id:string;object_id:string;translation_m:[number,number,0];expected_scene_revision:string}
  | {action:'model_move_preview';request_id:string;object_id:string;text:string;expected_scene_revision:string}
  | {action:'model_cancel';request_id:string;job_id:string}
  | {action:'model_review';request_id:string;job_id:string;expected_scene_revision:string}
  | {action:'photo_analyze';request_id:string;photo:{name:string;bytes_base64:string};consent:true;expected_scene_revision:string}
  | {action:'photo_cancel';request_id:string;job_id:string}
  | {action:'photo_candidate_preview';request_id:string;obstacle:EnvironmentObstacle;candidate_ref:EnvironmentCandidateRef;duplicate_reviewed:true;expected_scene_revision:string;replace_object_id?:string}
  | {action:'add_overlay_preview';request_id:string;obstacle:EnvironmentObstacle;photo:{name:string;bytes_base64:string}|null;expected_scene_revision:string}
  | {action:'remove_overlay_preview';request_id:string;object_id:string;expected_scene_revision:string}
  | {action:'undo_preview';request_id:string;expected_scene_revision:string};

export function isEnvironmentSource(file:Pick<File,'name'>):boolean{return /\.(?:usd|usda|usdc)$/i.test(file.name);}
