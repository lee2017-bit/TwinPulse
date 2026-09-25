import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { StrictMode } from "react";
import { describe, expect, it, vi } from "vitest";
import { App } from "./App";
import type { ProductState, WorkflowState } from "./types";
import type { TwinPulseApi } from "./api";

const draft = {
  artifact_id: "fixed_warehouse_v1", revision: "r".repeat(64), scene_id: "warehouse",
  input_revision: "i".repeat(64), plan_sha256: "p".repeat(64), request_id: "request-1",
  provider_name: "TwinPulse Mock", model_id: "twinpulse-explicit-fixture",
  robot_profile_id: "agv", task_id: "route", object_count: 1, tool_count: 3,
  objects: [{ id: "floor", kind: "floor", position_m: [0, 0, 0], shape: "box", dimensions_m: [8, 6, .1], provenance: "fixture" }],
  source: "fixture", approximate: true,
};

const workflow = (phase = "empty"): WorkflowState => ({
  schema_version: "1.1", mode: "explicit_fixture",
  provider: { configured: false, connected: false, label: "fixture" }, phase,
  generation_id: null, input: null, draft: phase === "draft_ready" ? draft : null,
  acknowledged_revision: null, build_allowed: false, error: null,
});

const product = (connected = true): ProductState => ({
  project_id: "default", engine_connected: connected, engine_session_id: connected ? "engine" : null,
  stage_epoch: connected ? "stage" : null, lease_owned: false, control_lease_id: null,
  snapshot: connected ? {
    schema_version: "1.1", engine_session_id: "engine", stage_epoch: "stage", project_id: "default",
    applied_revision: null, run_id: null, sequence: 1, runtime_state: "idle", safety_state: null,
    safety_reason: null, permitted_commands: ["get_state", "focus_scene"], capabilities: ["simulation"],
    sim_time_s: 0, sampled_at_utc: null, frame_id: "world", position_m: null, yaw_rad: null,
    roll_rad: null, pitch_rad: null, linear_speed_mps: null, distance_to_goal_m: null,
    cross_track_error_m: null, telemetry_available: false,
  } : null,
  operations: [], artifacts: [{ artifact_id: draft.artifact_id, revision: draft.revision }],
});

function mockApi(initialWorkflow = workflow(), initialProduct = product()) {
  let current = initialWorkflow;
  return {
    bootstrap: vi.fn(async () => undefined),
    workflow: vi.fn(async () => current),
    productState: vi.fn(async () => initialProduct),
    runtimeState: vi.fn(async () => ({
      schema_version: "1.0", status: "ready", phase: "ready", message: "Authenticated Isaac stage is ready",
      started_at_utc: null, updated_at_utc: null,
      backend: { owned: true, state: "running", pid: 1 },
      engine: { owned: true, state: "running", pid: 2 }, browser: { launched: true },
    })),
    providerSettings: vi.fn(async () => ({
      schema_version: "3.0", base_url: "https://api.openai.com/v1/", model_id: "gpt-test",
      reasoning_effort: "low", adapter_kind: "openai_responses", provider_profile: "openai",
      endpoint_path: "responses", credential_ref: "TwinPulse/OpenAIResponsesAPI",
      observer_model_id: "", fallback_observer_model_id: "",
      capabilities: { supports_images: true, supports_structured_output: true, max_images: 1, accepted_mime_types: ["image/png", "image/jpeg", "image/webp"] },
      settings_saved: true, capability_checked: true, credential_configured: true, live_request_succeeded: false,
    })),
    saveProviderSettings: vi.fn(async (body: { base_url: string; model_id: string; reasoning_effort: string; api_key: string; credential_reapproval: boolean; provider_profile: string }) => ({
      schema_version: "3.0" as const, base_url: body.base_url, model_id: body.model_id,
      reasoning_effort: body.reasoning_effort as "low" | "medium" | "high",
      adapter_kind: "openai_responses", provider_profile: "openai", endpoint_path: "responses",
      credential_ref: "TwinPulse/OpenAIResponsesAPI",
      observer_model_id: "", fallback_observer_model_id: "",
      capabilities: { supports_images: true, supports_structured_output: true, max_images: 1, accepted_mime_types: ["image/png", "image/jpeg", "image/webp"] },
      settings_saved: true, capability_checked: true, credential_configured: true, live_request_succeeded: false,
    })),
    selectInput: vi.fn(async () => workflow("input_ready")),
    generate: vi.fn(async () => { current = workflow("draft_ready"); return current; }),
    cancelGeneration: vi.fn(async () => current),
    acknowledge: vi.fn(async () => { current = { ...current, acknowledged_revision: draft.revision, build_allowed: true }; return current; }),
    acquireLease: vi.fn(async () => ({ control_lease_id: "lease", ttl_s: 3 })),
    renewLease: vi.fn(async () => ({ control_lease_id: "lease", ttl_s: 3 })),
    command: vi.fn(async () => ({ command_id: "command", status: "accepted" })),
  } as unknown as TwinPulseApi;
}

describe("TwinPulse R5 UI", () => {
  it("distinguishes backend, engine, and persisted credential status", async () => {
    render(<StrictMode><App api={mockApi(workflow(), product(false))} /></StrictMode>);
    await waitFor(() => expect(screen.getByText("Backend ready")).toBeTruthy());
    expect(screen.getByText("Isaac 연결 안 됨")).toBeTruthy();
    expect(screen.getByText("LLM 키 저장됨")).toBeTruthy();
  });

  it("creates a deterministic draft and requires acknowledgement", async () => {
    const api = mockApi();
    render(<App api={api} />);
    await waitFor(() => screen.getByText("Backend ready"));
    fireEvent.click(screen.getByRole("button", { name: "검증 초안 생성" }));
    await waitFor(() => screen.getByText("장면 초안 검토"));
    const build = screen.getByRole("button", { name: "Isaac에 3D 적용" }) as HTMLButtonElement;
    expect(build.disabled).toBe(true);
    fireEvent.click(screen.getByRole("checkbox"));
    await waitFor(() => expect(build.disabled).toBe(false));
  });

  it("shows safety state separately from ordinary runtime state", async () => {
    const unsafe = product();
    unsafe.snapshot = { ...unsafe.snapshot!, safety_state: "off_route", safety_reason: "Reset required" };
    render(<App api={mockApi(workflow("draft_ready"), unsafe)} />);
    await waitFor(() => screen.getByText("안전 정지 · off_route"));
    fireEvent.click(screen.getByRole("button", { name: /시뮬레이션/ }));
    expect(await screen.findByText("Reset required")).toBeTruthy();
  });

  it("blocks Run when the heartbeat is stale even if the last snapshot allowed it", async () => {
    const stale = product();
    stale.engine_connected = false;
    stale.snapshot = {
      ...stale.snapshot!, applied_revision: draft.revision,
      permitted_commands: ["get_state", "focus_scene", "run"],
    };
    render(<App api={mockApi(workflow("draft_ready"), stale)} />);
    await waitFor(() => screen.getByText("Isaac 연결 안 됨"));
    fireEvent.click(screen.getByRole("button", { name: /시뮬레이션/ }));
    expect((await screen.findByRole("button", { name: /Run/ }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("shows a finite launcher failure in the product UI", async () => {
    const api = mockApi();
    api.runtimeState = vi.fn(async () => ({
      schema_version: "1.0" as const, status: "error", phase: "engine_exited", message: "engine exited with code 7",
      started_at_utc: null, updated_at_utc: null,
      backend: { owned: true, state: "running" }, engine: { owned: true, state: "exited", exit_code: 7 },
      browser: { launched: true },
    }));
    render(<App api={api} />);
    expect(await screen.findByText("engine exited with code 7")).toBeTruthy();
  });

  it("shows persisted credential state without exposing the saved key", async () => {
    const api = mockApi();
    render(<App api={api} />);
    expect(await screen.findByText("LLM 키 저장됨")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "LLM 설정" }));
    expect(screen.getByText("Windows 자격 증명에 저장됨")).toBeTruthy();
    const key = screen.getByLabelText("API Key") as HTMLInputElement;
    expect(key.type).toBe("password");
    fireEvent.change(key, { target: { value: "sk-ui-secret" } });
    fireEvent.click(screen.getByRole("button", { name: "안전하게 저장" }));
    await waitFor(() => expect(api.saveProviderSettings).toHaveBeenCalledWith(expect.objectContaining({ api_key: "sk-ui-secret" })));
    expect(screen.queryByDisplayValue("sk-ui-secret")).toBeNull();
  });
});
