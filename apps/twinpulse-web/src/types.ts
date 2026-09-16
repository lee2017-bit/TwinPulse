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
  schema_version: "1.0";
  mode: "deterministic_fixture";
  provider: { configured: boolean; connected: boolean; label: string };
  phase: string;
  generation_id: string | null;
  input: null | {
    revision: string;
    input_kind: string;
    prompt_length: number;
    image_name: string | null;
    media_type: string | null;
    width: number | null;
    height: number | null;
    sidecar_name: string | null;
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
