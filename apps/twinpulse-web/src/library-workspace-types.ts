// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import type {LibraryModel} from './model-library-types';
import type {SceneEditPreview} from './types';

export interface LibraryAttachment {name:string;media_type:string;bytes_base64:string;role:'asset_source'|'asset_reference'|'tool_input'}
export interface LibraryAsset {
  asset_id:string;version:string;title:string;kind:'recipe'|'usd'|'cad'|'brep';source_name:string;source_sha256:string;
  dimensions_m:[number,number,number];units:'m';up_axis:'Z';origin:string;license:string;
  visual_status:string;physics_status:string;reusable:boolean;recipe_model_id?:string|null;preview_parts?:LibraryModel['preview_parts'];
}
export interface LibraryJob {
  job_id:string;project_id:string;request_id:string;purpose:'asset_create'|'asset_import'|'analysis';
  status:'queued'|'running'|'ready'|'registered'|'failed'|'cancelled'|'unknown';phase:string;message:string;
  tool_id:string;execution_id:string;input_sha256:string;created_at:string;can_cancel:boolean;can_register:boolean;
  error:string|null;asset_id?:string|null;asset_version?:string|null;result?:Record<string,unknown>|null;
}
export interface ToolInputSchema {
  type?:string;title?:string;description?:string;default?:unknown;enum?:unknown[];minimum?:number;maximum?:number;
  properties?:Record<string,ToolInputSchema>;required?:string[];items?:ToolInputSchema;
  [key:string]:unknown;
}
export interface LibraryTool {tool_id:string;title:string;input_schema:ToolInputSchema;output_kind:string}
export interface LibraryExtension {
  extension_id:string;title:string;transport:'builtin'|'cli'|'mcp';available:boolean;enabled:boolean;reason:string|null;
  version:string|null;executable_configurable:boolean;tools:LibraryTool[];
}
export interface LibraryWorkspaceState {
  schema_version:'library-workspace-1.0';project_id:string;current_scene_revision:string|null;
  assets:LibraryAsset[];jobs:LibraryJob[];extensions:LibraryExtension[];placement_preview?:LibraryPlacementPreview|null;message?:string|null;
}
export type LibraryPlacementPreview=SceneEditPreview&{preview_id:string};
export type LibraryWorkspaceAction =
  | {action:'create_recipe';request_id:string;prompt:string;reference?:LibraryAttachment}
  | {action:'import_asset';request_id:string;attachment:LibraryAttachment;source:string;license:string;source_units?:'m'|'cm'|'mm';source_up_axis?:'Y'|'Z'}
  | {action:'register_job';job_id:string;request_id:string}
  | {action:'cancel_job';job_id:string}
  | {action:'preview_placement';asset_id:string;version:string;expected_scene_revision:string;instance_id:string;position_m:[number,number,number];yaw_deg:number;request_id:string}
  | {action:'configure_extension';extension_id:string;executable:string;enabled:boolean}
  | {action:'check_extension';extension_id:string}
  | {action:'run_tool';request_id:string;tool_id:string;inputs:Record<string,unknown>;attachment?:LibraryAttachment};

export function isLibrarySource(file:Pick<File,'name'>):boolean{return /\.(?:step|stp|iges|igs|usd|usda|usdc|usdz|obj|stl|ply|gltf|glb)$/i.test(file.name);}
