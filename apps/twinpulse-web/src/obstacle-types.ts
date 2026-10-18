// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse

export interface ObstacleObservation {
  id:string;sha256:string;provenance:string;received_at_utc:string;execution_id:string;
  scan_count:number;scan_height_m:number;sensor_pose_m:number[];points:number[][];
  cells:[number,number,string][];occupied_count:number;free_count:number;unknown_count:number;
  association:'unassigned';
  cell_size_m?:number;cell_coordinates?:'room_metres_cell_centres';reviewed_scan_index?:number;coordinate_basis?:string;alignment_verified?:false;
}

export interface ObstacleFeedbackState {
  schema_version:'obstacle-feedback-1.0';
  context:{current_scene_revision:string;current_state_sha256:string;project_id:string};
  observations:ObstacleObservation[];targets:{id:string;label:string;center_m:number[]}[];
  physical_authority:false;
}

export interface ObstacleCorrectionPreview {
  status:'preview'|'HELD';reason:string;execution_id:string;
  observation_id:string;observation_sha256:string;translation_xy_m?:number[];
  fit?:Record<string,unknown>|null;operation?:Record<string,unknown>;preview_digest?:string;
  sensor_binding?:Record<string,unknown>;apply_version:'scene-edit-apply-2.0';
}
