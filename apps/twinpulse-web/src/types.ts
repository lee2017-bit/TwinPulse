import type { Operation, SimulationSnapshot } from "./engine-contracts";

export interface DraftObject {
  id: string;
  kind: string;
  position_m: number[];
  shape: string;
  dimensions_m: number[];
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

export interface WorkflowState {
  schema_version: "1.1";
  mode: "live_provider" | "explicit_fixture";
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
  acknowledged_revision: string | null;
  build_allowed: boolean;
  error: null | { code: string; message: string };
}

export interface ProductState {
  project_id: string;
  engine_connected: boolean;
  engine_session_id: string | null;
  stage_epoch: string | null;
  lease_owned: boolean;
  control_lease_id: string | null;
  snapshot: SimulationSnapshot | null;
  operations: Operation[];
  artifacts: { artifact_id: string; revision: string }[];
}

export interface SupervisorComponent {
  owned: boolean;
  state: string;
  pid?: number;
  exit_code?: number;
}

export interface SupervisorState {
  schema_version: "1.0";
  status: string;
  phase: string;
  message: string;
  started_at_utc: string | null;
  updated_at_utc: string | null;
  backend: SupervisorComponent;
  engine: SupervisorComponent;
  browser: { launched: boolean };
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
