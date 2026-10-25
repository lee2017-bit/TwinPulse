// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
export interface GenerationAttempt {
  attempt_id?:string; stage?:string; model_id?:string; status?:string;
  role?:'initial'|'repair'|'final_review'; repair?:boolean;
  validation?:string; validation_code?:string; error_type?:string; elapsed_s?:number;
  patch_shape?:string;patch_effect?:string;candidate_validation?:string;
}

export interface ChatMessage {
  message_id: string; role: 'user' | 'assistant'; content: string; status: string;
  reply_to?: string | null;
  attachments: { name: string; media_type: string; preview_url?: string }[]; created_at: string; operation_id: string | null;
}
export interface QuestionCard {
  message_id: string;
  reply_to?: string | null;
  created_at?: string;
  id: string; kind: string; question: string; state: string; selected_choice_id: string | null;
  expected_session_revision: number; operation_id: string | null;
  choices: { id: string; label: string; enabled: boolean; disabled_reason: string | null }[];
  generation_approval?: GenerationApprovalPreview;
  scene_feedback?: boolean;
  route_preview?: {bounds:number[];free_cells:number[][];cell_m:number;start:number[];waypoints:number[][];polyline:number[][];basis:string;scope:string;keepouts?:number[][]};
}
export interface GenerationApprovalPreview {
  schema_version:'ordinary-generation-preview-1.0';input_sha256:string;input_revision:string;preview_sha256:string;
  image_count:number;purpose:string;render_review_approved?:boolean;pricing_valid_until:string;default_limit_usd:string;
  planned_requests?:number;scene_edit_context_sha256?:string;
  worst_single_reserve_usd:string;minimum_initial_reserve_usd:string;
  checkpoint_id:string|null;prior_requests:number;prior_active_s:number;
  prior_cost?:{estimated_usage_usd:string;reserved_unknown_usd:string;history_complete?:boolean;invoice_verified:false}|null;
  policy:{per_call_timeout_s:number;total_timeout_s:number;max_requests:number;max_repairs:number;stalled_repairs:number};
  models:{stage:string;model_id:string;origin:string;max_output_tokens:number;thinking_mode:string;
    full_context_reserve_usd:string;price_source:string;price_verified_at:string}[];
}
export interface SceneContractDiagnostic {
  issues:{code:string;path?:string;target_ids?:string[];actual_m?:number;violation_m?:number;
    actual_count?:number;maximum?:number;structural_metadata_count?:number;
    geometry_values_m?:{height_m?:number;support_top_m?:number;bottom_m?:number};
    expected_bounds_m?:{min_m?:number;max_m?:number;max_top_m?:number;max_height_m?:number;min_bottom_m?:number}}[];
  issue_count:number;issues_truncated:boolean;blocked_checks:string[];physical_authority:false;category_validation?:'TYPED_OBSERVATION'|'UNVERIFIED_LEGACY_OBSERVATION';
  checks?:GeometryCheck[];checks_complete?:boolean;checks_truncated?:boolean;
}
export interface GeometryCheck {check_id:string;status:'passed'|'partial'|'failed'|'blocked'|'not_run'|'error';blocked_by:string[];candidate_revision?:string}
export interface RepairDecision {decision:string;progressed?:boolean;regressed?:boolean;stage_complete?:boolean;branch_abandoned?:boolean;advanced_checks?:string[];repair_kind?:'geometry'|'quality'}
export interface RepairScope {schema_version:'geometry-scope-1.0'|'geometry-scope-1.1';accepted:{id:string;anchor_id:string;reason_code:'packing_neighbor'|'support_alternative'}[];physical_authority:false}
export interface InstanceGrounding {status:'count_preserved'|'count_partially_unverified'|'legacy_count_unverified';effective_object_count:number;expanded_groups:number;unresolved_counts:number;individual_pose_verified:false}
export interface InventoryWorkProgress {schema_version:'inventory-work-progress-1.0';observed_instances:number;inventory_count:number;parameterized_count:number;pending_count:number;parameter_batch_size:number;inventory_planned:boolean;parameters_complete:boolean;checkpoint_saved:boolean;observation_saved?:boolean;draft_saved?:boolean;automatic_resume:false;physical_authority:false}
export interface GenerationPreview {schema_version:'generation-preview-1.0';state:'building'|'ready'|'blocked';candidate_revision:string|null;scene_revision:string|null;rendered_count:number;pending_count:number;inventory_count:number;pending_objects?:{id:string;reason_code:string;blocked_by?:string[]}[];preview_only:true;physical_authority:false;error_code?:string|null}
export interface GenerationActivity {schema_version:'generation-activity-1.0';stage:string;phase:'waiting_model'|'validating'|'building'|'awaiting_frame'|'ready'|'blocked';batch_index?:number;batch_total?:number;affected_ids?:string[];reason_codes?:string[]}
export interface RetentionRevalidation {validation:'passed'|'failed';gate:'exact_plan_and_support_witness';same_plan:boolean;same_witness:boolean;physical_authority:false}
export interface GenerationQualityReview {status?:string;candidate_revision?:string;plan_sha256?:string;
  relative_layout?:{status:'needs_revision'|'uncertain'|'consistent_materialized_anchors';
    anchor_ids?:string[];reviewed_anchor_ids?:string[];contradicted_anchor_ids?:string[];
    uncertain_anchor_ids?:string[];deferred_object_ids?:string[];metric_scale:'estimated_not_measured';
    sensor_alignment:'not_run';physical_authority:false}}
export interface ConversationState {
  schema_version: 'conversation-1.0'; session_id: string; project_id: string; context_id?: string; revision: number; cursor: number;
  mode: 'SIM' | 'REAL' | null; robot_id: string | null; physical_authority: false;
  restore_error: {code: string; message: string} | null;
  restored_session?: boolean;
  budgeted_generation_available?:boolean;
  generation_settling?:{operation_id:string;generation_id:string}|null;
  scene_feedback?:{operation_id:string;origin_message_id?:string;state:string;error:string|null;clarification_count:number;approval_id?:string;execution_id?:string;request_id?:string;
    progress?:{stage?:string;status?:string;elapsed_s?:number;budget?:{requests?:number;max_requests?:number;repairs?:number;max_repairs?:number;stop_reason?:string;cost?:{estimated_usage_usd:string;reserved_unknown_usd:string}}}}|null;
  scene_edit_preview?:import('./types').SceneEditPreview|null;
  scene_edit_transaction?:import('./types').SceneEditTransaction|null;
  scene_sensor_review?:SceneSensorResult|null;
  queued_edit?: {text:string; state:'pending';origin_message_id?:string} | null;
  simulation_review?: SimulationReview|null;
  robot_preparation?: RobotPreparation|null;
  inspection?: InspectionState|null;
  navigation?: CurrentGoalState|null;
  room_build?: {operation_id:string;scene_revision:string;artifact_id:string}|null;
  inspection_display?: InspectionDisplay|null;
  messages: ChatMessage[]; cards: QuestionCard[]; accepted_request_ids: string[];
  events: { event_id: string; sequence: number; type: string; timestamp: string }[];
  generation: { operation_id: string; generation_id?:string; origin_message_id?:string; request_id?:string; state: string; summary: string; can_cancel: boolean;
    progress?:{stage?:string;model_id?:string;status?:string;elapsed_s?:number;repair_count?:number;max_repairs?:number;sequence?:number;repair_no_progress?:boolean;scene_contract?:SceneContractDiagnostic;
      quality_review?:GenerationQualityReview;repair_decision?:RepairDecision;scope_decision?:RepairScope;geometry_checks?:{checks:GeometryCheck[];checks_complete:boolean};stage_acceptance?:Record<string,string>;instance_grounding?:InstanceGrounding;inventory_progress?:InventoryWorkProgress;generation_preview?:GenerationPreview;generation_activity?:GenerationActivity;retention_revalidation?:RetentionRevalidation;
      budget?:{requests?:number;max_requests?:number;repairs?:number;max_repairs?:number;elapsed_s?:number;remaining_s?:number;stop_reason?:string;financial_scope?:string;
        cost?:{currency:'USD';limit_usd:string;estimated_usage_usd:string;reserved_unknown_usd:string;invoice_verified:false};
        cumulative_requests?:number;cumulative_active_s?:number;
        cumulative_cost?:{currency:'USD';estimated_usage_usd:string;reserved_unknown_usd:string;history_complete:boolean;invoice_verified:false}};
      attempts?:GenerationAttempt[];attempts_total?:number;attempts_truncated?:boolean};
    started_at: string; last_progress_at: string; error: { code: string; message: string;diagnostics?:{stage?:string;model_id?:string;max_tokens?:number;elapsed_s?:number;timeout_s?:number;finish_reason?:string;repair_no_progress?:boolean;scene_contract?:SceneContractDiagnostic;attempts?:GenerationAttempt[];attempts_total?:number;attempts_truncated?:boolean;
      quality_review?:GenerationQualityReview;repair_decision?:RepairDecision;scope_decision?:RepairScope;geometry_checks?:{checks:GeometryCheck[];checks_complete:boolean};stage_acceptance?:Record<string,string>;instance_grounding?:InstanceGrounding;inventory_progress?:InventoryWorkProgress;generation_preview?:GenerationPreview;generation_activity?:GenerationActivity;retention_revalidation?:RetentionRevalidation} } | null } | null;
}
export interface CurrentGoalState {
  task_loop?:{task_id:string;state:string;leg:number;destination:string;completed_legs:number;
    a:number[];b:number[];worker_active:boolean;error:string|null;error_stage:string|null;cleanup_error:string|null;
    resources:{voltage_v:number;estimated_percent:number;capacity_measured:false;historical:true}|null;
    motion_authorized:false;physical_demo_ready:false}|null;
  demonstration?:{state:string;stage:string;elapsed_s:number;error:string|null;cleanup_error:string|null;
    review_id:string;simulation_id:string;receipt_current:boolean;handoff_ready:boolean;robot_review_parked?:boolean;physical_authority:false}|null;
  review:{scene_revision:string;plan:{schema:'current-goal-preview-1.0'|'current-goal-preview-2.0';mode:'REAL_CANDIDATE';
    plan_id:string;start:number[];goal:number[];route:number[][];yaw_rad:number;physical_authority:false}|null;
    target:{id:string;label:string}|null;choices:{id:string;label:string}[];
    drawing:{bounds:number[];boxes:number[][];discs:number[][]}}|null;
  error:string|null;current_pose_available:false;motion_authorized:false;physical_demo_ready:false;
  job:{job_id:string;state:string;elapsed_s:number;error?:string|null;cleanup_error?:string|null;report_error?:string|null;
    native_cleanup_errors?:{stage:string;code:string;error_type:string}[];
    telemetry_status?:string;telemetry_age_s?:number|null;worker_active?:boolean;
    telemetry?:{battery:{voltage_v:number;estimated_percent:number;measured_capacity:false}|null;
      next_waypoint:{index:number;count:number;xy_room:number[]}|null;motor_load:'UNSUPPORTED'}|null}|null;
}
export interface InspectionDisplay {
  ready:boolean;code:string;scene_revision:string|null;current_pose_available:false;motion_authorized:false;
  descriptor:{kind:'current_inspection_visual_v1';mission_id:string;manifest_sha256:string};
}
export interface InspectionState {
  state:string;owned:boolean;busy:boolean;job_id?:string;elapsed_s?:number;
  readiness?:{ready:boolean;binding:string|null;code:string;room_revision:string|null;scene_revision:string|null;photo_policy?:'align_only'|'correct_walls'};
  photo_correction?:{status:string;applied_revision:string;effective_revision:string;goal_revalidation:string;isaac_geometry_status:string}|null;
  diagnostics?:{stage:string;view_count:number;alignment_status:string;reason:string}|null;
  error?:string|null;error_stage?:string|null;cleanup_error?:string|null;report_error?:string|null;
  report_status?:string;report_revision?:string|null;alignment_candidate?:boolean;current_pose_available?:boolean;
  summary?:{state:string;elapsed_s:number;battery_status:string;next_action:string;error:string|null};
  motion_authorized:false;demo_ready:false;
}
export type ConversationAction =
  | {action:'sensor_review';request_id:string;map_id:string;expected_map_revision:string;expected_scene_revision:string;expected_state_sha256:string}
  | {action:'sensor_import';request_id:string;mission_id:string;expected_report_revision:string;expected_scene_revision:string;expected_state_sha256:string}
  | { action: 'message'; request_id: string; text: string; mode: 'new' | 'add' | 'change';
      attachment: { name: string; media_type: string; content_base64: string } | null }
  | { action: 'answer'; request_id: string; card_id: string; choice_id: string; expected_session_revision: number; expires_at_ms?:number;limit_usd?:string }
  | { action: 'cancel'; request_id: string; operation_id: string }
  | { action:'generation_retry'; request_id:string; operation_id:string };
export type RobotCheckAction = {action:'robot_check';request_id:string}
  | {action:'inspection_check';request_id:string}
  | {action:'robot_collect';request_id:string;expires_at_ms:number;confirmed_source_transfer:true}
  | {action:'robot_transfer';request_id:string;expires_at_ms:number;kind:'stationary'|'qualification';job_id:string};
export type ResumeSceneAction = { action:'resume'; request_id:string; expected_scene_revision:string; expected_input_revision:string };
export interface SceneSensorContext {
  schema_version:'scene-sensor-context-1.0';project_id:string;input_revision:string;source_sha256:string;
  current_scene_revision:string;current_state_sha256:string;physical_authority:false;
}
export interface SceneSensorResult {
  status:'HELD'|'POSE_CANDIDATE'|'preview'|'cancelled'|'imported';policy:string;reason?:string;
  map_id?:string;map_revision?:string;duplicate?:boolean;survey_import_sha256?:string;
  context:SceneSensorContext;evidence?:{map_id:string;map_revision:string;source_job_id:string;
    provenance:'SYNTHETIC_TRANSPORT'|'RECORDED_REAL_TRANSPORT';[key:string]:string};
  alignment_status?:string;geometry_status?:string;room_from_map?:number[]|null;
  diagnostics?:{schema_version:'scene-sensor-diagnostics-1.0';view_count:number;view_span_m:number;
    source_pose_truth:false;physical_authority:false;scope:string;furniture_correspondence:string;
    [key:string]:unknown};
  proposals?:{id:string;translation_xy_m:number[];normal_delta_m:number}[];physical_authority:false;
}
export interface SceneSensorSurvey {
  mission_id:string;report_revision:string|null;source_job_id:string;status:'READY'|'HELD';reason:string;
  provenance:'SYNTHETIC_TRANSPORT'|'RECORDED_REAL_TRANSPORT'|'UNAVAILABLE';
}
export interface RobotPreparation {
  state:string;stage:string;code:string|null;attempt_id:string|null;owned:boolean;available:boolean;
  binding:string|null;transport:'ACTUAL_ROBOT'|'OFFLINE_TEST_TRANSPORT';physical_authority:false;demo_ready:false;
  job_id:string|null;record:{boot_id:string;release_id:string;observed_at_utc:string;age_seconds:number;
    battery:{estimated_percent:number;capacity_measured:false;voltage_v:number}|null}|null;
  trial:{status:string;job_id:string;cleanup_confirmed?:boolean}|null;
  cleanup_error?:string|null;missing?:string[];error_type?:string;
  active_control?:{owned:boolean;busy:boolean;state:string|null;mode:string|null;cleanup_confirmed:boolean};
  collection?:{status:string;job_id:string|null;owned:boolean;result_code:string|null;reason:string|null;
    steps:{id:string;status:string;reason:string|null}[];sources:{id:string;status:string;reason:string|null;fault_counts:Record<string,number>}[];
    raw_export:{status:string}|null;recovery:{status:string;reason?:string|null;transfer_only:true}|null;
    resume_available:boolean;motion_authorized:false;alignment_verified:false;demo_ready:false}|null;
  evidence?:{session_log_complete?:boolean|null;evidence_export?:string|null;evidence_export_error?:string|null;
    session_storage?:{saved:number;accepted:number;error:string|null}|null;report_saved?:boolean|null;
    evidence_recovery?:{status:string;transfer_only:true;reason?:string|null}|null}|null;
}
import type {SimulationPlan} from './SimulationRunCard';
export interface SimulationReview {
  origin_message_id?:string;
  request_id:string; text:string; scene_revision:string; start_source:string;
  plan:SimulationPlan|null; target:{id:string;label:string;object_ids:string[];bounds:number[]}|null;
  choices:{id:string;label:string;object_ids:string[];bounds:number[]}[];
  drawing:{bounds:number[];boxes:number[][];discs:number[][]};
}
