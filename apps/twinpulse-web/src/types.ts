// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import type { Operation, SimulationSnapshot } from "./engine-contracts";

export interface DraftObject {
  id: string;
  kind: string;
  position_m: number[];
  shape: string;
  dimensions_m: number[];
  rotation_rpy_deg?: number[];
  provenance: string;
}

export interface DraftSummary {
  artifact_id: string;
  revision: string;
  input_revision: string | null;
  plan_sha256: string;
  request_id: string;
  provider_name: string;
  model_id: string;
  scene_id: string;
  robot_profile_id: string;
  task_id: string;
  object_count: number;
  tool_count: number;
  objects: DraftObject[];
  source: string;
  approximate: boolean;
}

export interface ProgressiveTwinSummary {
  schema_version: 'progressive-twin-1.0' | 'progressive-twin-1.1'; policy_version: string;
  plan_sha256: string; current: boolean; inventory_count: number; materialized_count: number;
  axes: {draft_ready: string; sim_task_pass: string; real_task_ready: string; visual_review: string};
  unresolved: {id: string; parent_id: string | null; code: string; reason: string; status: 'deferred' | 'removed'; impact: string;hazard?:'rigid'|'entanglement'|'unknown';bounds_z_m?:number[]}[];
  physical_authority: false;
}

export interface SiteDraftSummary {
  draft_refinement?: {schema_version:'draft-refinement-1.0'|'draft-refinement-1.1';acceptance:'GEOMETRY_VALID_REFINEMENT_INCOMPLETE'|'MATERIALIZED_SUBSET_VALID_REFINEMENT_INCOMPLETE';progressive_sha256?:string;
    candidate_revision:string;plan_sha256:string;sha256:string;stop_reason:string;current:boolean;
    assessment_state:'needs_revision'|'recheck_required';physical_authority:false;
    quality_review:{status:'needs_revision';issues:{code:string;target_ids:string[];related_ids:string[];violation_m?:number}[]}} | null;
  progressive_twin?: ProgressiveTwinSummary | null;
  placement_contract?: {schema_version: 'photo-placement-contract-1.0' | 'photo-placement-contract-1.1'; relations: {
    id: string; relation: 'floor' | 'surface' | 'drape' | 'wall' | 'ceiling';
    parent_id: string | null; part: string | null; anchor: string; elevation_m: number | null;
  }[]} | null;
  room_inventory?: RoomInventoryState;
  photo_inventory?: PhotoRoomInventory | null;
  derived_review_revision?: string | null;
  scene_edit_revision?: string | null;
  scene_edit_count?: number;
  scene_state_sha256?: string;
  editable_calls?: { call_id: string; tool: string; arguments: Record<string, unknown> }[];
  original_scene_revision?: string;
  geometry_provenance?: string;
  review_provenance?: SiteReviewProvenance;
  schema_version: "2.0";
  artifact_id: string | null;
  revision: string;
  input_revision: string;
  plan_sha256: string;
  request_id: string;
  provider_name: string;
  model_id: string;
  scene_id: string;
  summary: string;
  source: string;
  tool_count: number;
  object_count: number;
  robot_profile_id: string | null;
  mission_id: string | null;
  navigation_map_ready: boolean;
  review_required: true;
  build_allowed: boolean;
  run_allowed: false;
  objects: DraftObject[];
}

export interface SiteReviewProvenance {
  schema_version: "site-review-provenance-1.0";
  source_class: "local_recipe" | "saved_provider_or_fixture_plan";
  provider_name: string;
  model_id: string;
  input_kind: string;
  input_revision: string;
  source_plan_sha256: string;
  original_scene_revision: string;
  current_scene_revision: string;
  local_edit_count: number;
  photo_interpretation_evidence: "local_import_not_performed" | "not_verified_by_saved_plan";
  world_alignment: "NOT_VERIFIED";
  physical_validation: "NOT_RUN";
  calls: { call_id: string; tool: string; origin: "original_plan" | "user_local_edit";
    basis: "visual" | "user" | "inferred" | "trusted_measurement" | "unprovided";
    observation_ids: string[] }[];
}

export interface SceneEditPreview {
  apply_version?: 'scene-edit-apply-2.0';
  inventory_changes?: {id:string;before:Record<string,unknown>|null;after:Record<string,unknown>|null}[];
  parent_state_sha256?: string;
  result_state_sha256?: string;
  operation: Record<string, unknown>;
  preview_digest: string;
  source_revision: string;
  parent_revision: string;
  result_revision: string;
  affected_before: Record<string, { position_m: number[]; dimensions_m: number[]; kind: string }>;
  affected_after: Record<string, { position_m: number[]; dimensions_m: number[]; kind: string }>;
  preserved_object_count: number;
  review_required: true;
  physical_validation: "NOT_RUN";
}

export interface SceneEditTransaction {
  origin_message_id?:string;
  operation_id:string;state:string;execution_id?:string|null;
  current_frame:boolean;durable_committed:boolean;error:string|null;
    engine_acknowledged?:boolean;
    compensation_acknowledged?:boolean;displayed_revision?:string;
  command_id:string|null;result_revision?:string;before_revision?:string;
  recovery_available?:boolean;historical?:boolean;
}

export interface SceneEditContext {
  schema_version: "scene-edit-context-1.0" | "scene-edit-context-1.1";
  placement_contract?: SiteDraftSummary['placement_contract'];
  project_id: string;
  source_scene_revision: string;
  current_scene_revision: string;
  request_text: string;
  selected_call_id: string | null;
  furniture_calls: { call_id: string; tool: "place_furniture"; arguments: Record<string, unknown> }[];
  scene_objects: { id: string; kind: string; position_m: number[]; dimensions_m: number[] }[];
  boundary: string;
  context_sha256: string;
}

export interface SceneEditProposal {
  schema_version: "scene-edit-proposal-1.0";
  context_sha256: string;
  mode: "add_furniture" | "change_furniture" | "clarify";
  explanation: string;
  target_call_id: string | null;
  tool_call: Record<string, unknown> | null;
}

export interface SceneEditProposalResult {
  status: "preview" | "clarify";
  explanation: string;
  context_sha256: string;
  preview: SceneEditPreview | null;
}

export interface WorkflowState {
  scene_edit_transaction?: SceneEditTransaction | null;
  execution_id?: string | null;
  photo_inventory?: PhotoRoomInventory | null;
  schema_version: "1.1" | "1.2";
  mode: "live_provider" | "explicit_fixture" | "replay" | "simulation_offline";
  provider: { configured: boolean; connected: boolean; label: string };
  phase: string;
  generation_id: string | null;
  input: null | {
    revision: string;
    input_kind: string;
    prompt_length: number;
    image_name: string | null;
    media_type: string | null;
    image_sha256: string | null;
    width: number | null;
    height: number | null;
    sidecar_name: string | null;
    sidecar_sha256: string | null;
    measurement_count: number;
  };
  draft: DraftSummary | null;
  site_draft?: SiteDraftSummary | null;
  presentation?: PresentationState | null;
  saved_site_scene_protected?: boolean;
  saved_input?: null | { input_kind: string; image_name: string | null; media_type: string | null };
  acknowledged_revision: string | null;
  build_allowed: boolean;
  error: null | { code: string; message: string };
}

export interface RoomInventoryItem {
  id: string; label: string; kind: string;
  risk: 'collision' | 'entanglement' | 'unknown' | 'visual_only';
  basis: string; observation_ids: string[];
  last_observation_utc: string | null;
  placement_status: 'represented' | 'missing';
  geometry: {id: string; position_m: number[]; dimensions_m: number[]; yaw_deg: number;
    collision: boolean; synthetic_keepout: boolean}[];
}
export interface RoomInventoryState {
  schema_version: 'room-inventory-1.0'; scene_revision: string; source: string;
  source_ref: string | null; live_observation: false; physical_validation: 'NOT_RUN';
  items: RoomInventoryItem[];
}
export interface PhotoRoomInventory {
  schema_version: 'photo-room-inventory-1.0'; image_sha256: string;
  source: string; capture_time_utc: null; live_observation: false;
  geometry_status: 'UNMEASURED'; physical_validation: 'NOT_RUN';
  route_inventory_complete: boolean; missing_route_items: string[];
  items: {id: string; label: string; kind: string; visibility: string;
    required_for_route: boolean; placement_status: 'represented' | 'unplaced';
    last_observation_utc: string | null; geometry: RoomInventoryItem['geometry']}[];
}

export interface PresentationState {
  schema_version: 1;
  view: "auto" | "front" | "back" | "left" | "right" | "top";
  lighting: "balanced" | "soft" | "bright";
  saved: boolean;
  source_scene_revision: string;
  applies_on_next_build: true;
}

export interface ProductState {
  snapshot_execution_id?: string | null;
  build_view?: {command_id:string;engine_session_id:string;stage_epoch:string;applied_revision:string;
    phase?:'apply'|'frame';message?:string|null;
    status:'waiting'|'succeeded'|'failed'|'unknown';error_code:string|null;execution_id:string|null} | null;
  project_id: string;
  engine_connected: boolean;
  engine_session_id: string | null;
  stage_epoch: string | null;
  lease_owned: boolean;
  control_lease_id: string | null;
  snapshot: SimulationSnapshot | null;
  engine_readiness?: Record<string, { feature: string; ready: boolean; code: string }>;
  operations: Operation[];
  artifacts: { artifact_id: string; revision: string }[];
}

export interface ProjectCatalogState {
  schema_version: "project-catalog-1.0";
  active_project_id: string;
  preserved_bedroom_available: boolean;
  burger_visual_available?: boolean;
  switch_requires_restart: true;
  saved_approval_restored: false;
  truncated: boolean;
  projects: { project_id: string; kind: "default" | "named_room";
    status: "empty" | "review_required" | "import_required" | "recovery_required" | "source_invalid";
    active: boolean; recovery_fingerprint?: string | null;
    display_name?: string; message_count?: number; last_message_at?: string | null;
    conversation_status?: 'empty' | 'saved' | 'unavailable' }[];
}

export interface SupervisorComponent {
  owned: boolean;
  state: string;
  pid?: number;
  exit_code?: number;
}

export interface SupervisorState {
  shutdown_available?: boolean;
  shutdown_requested?: boolean;
  diagnostic_execution_id?: string | null;
  startup_checks?: { id:string; state:string; detail:string; action:string|null; sampled_at:string; attempts?:number }[];
  schema_version: "1.0";
  status: string;
  phase: string;
  message: string;
  retry_remaining?: number;
  started_at_utc: string | null;
  updated_at_utc: string | null;
  backend: SupervisorComponent;
  engine: SupervisorComponent;
  browser: { launched: boolean };
}

export interface RuntimeDiagnostics {
  schema_version: "runtime-diagnostics-1.0";
  release?: {build_id:string|null; product_version:string|null; simulation_only:boolean};
  runtime: Pick<SupervisorState, "status" | "phase" | "retry_remaining" | "started_at_utc" | "updated_at_utc" | "backend" | "engine" | "browser">;
  engine_startup: { phase: "isaac_import" | "simulation_app_init"; error_type: string; detail: string } | null;
  engine_runtime_profile: { python: string; packages: Record<string, {
    loaded: boolean; origin_class: string; origin_sha256: string | null; version: string | null;
  }> } | null;
  profile: { app_python: string; platform: string };
  export_policy: string;
}

export interface ProviderSettingsState {
  schema_version: "3.0";
  base_url: string;
  model_id: string;
  reasoning_effort: "low" | "medium" | "high";
  adapter_kind: string;
  provider_profile: string;
  endpoint_path: string;
  credential_ref: string;
  observer_model_id: string;
  fallback_observer_model_id: string;
  capabilities: {
    supports_images: boolean;
    supports_structured_output: boolean;
    max_images: number;
    accepted_mime_types: string[];
  };
  settings_saved: boolean;
  capability_checked: boolean;
  credential_configured: boolean;
  live_request_succeeded: boolean;
}
