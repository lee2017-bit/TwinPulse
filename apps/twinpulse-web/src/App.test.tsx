// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { StrictMode } from "react";
import { describe, expect, it, vi } from "vitest";
import { App as ChatApp, LegacyApp as App } from "./App";
import type { ProductState, WorkflowState } from "./types";
import type { TwinPulseApi } from "./api";
import type { Operation } from "./engine-contracts";
import type {ViewportState} from './viewport-types';

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
    runtimeDiagnostics: vi.fn(async () => ({
      schema_version: "runtime-diagnostics-1.0", runtime: {
        status: "error", phase: "isaac_import", retry_remaining: 3,
        started_at_utc: null, updated_at_utc: null,
        backend: { owned: true, state: "running" }, engine: { owned: true, state: "exited" },
        browser: { launched: true },
      },
      engine_startup: { phase: "isaac_import", error_type: "ImportError", detail: "Local owner-only result" },
      engine_runtime_profile: null, profile: { app_python: "3.12.0", platform: "win32" },
      export_policy: "allowlisted_metadata_only_no_raw_logs_paths_secrets_or_user_images",
    })),
    retryLauncher: vi.fn(async () => ({ status: "requested", new_session_required: true })),
    cancelStartup: vi.fn(async () => ({ status: "requested", new_session_required: true })),
    shutdownRuntime: vi.fn(async () => ({status:"requested",new_session_required:true})),
    switchProject: vi.fn(async (project_id: string) => ({ status: "requested", project_id, new_session_required: true })),
    projects: vi.fn(async () => ({ schema_version: "project-catalog-1.0", active_project_id: initialProduct.project_id, preserved_bedroom_available: true,
      switch_requires_restart: true, saved_approval_restored: false, truncated: false,
      projects: [{ project_id: initialProduct.project_id, kind: "default", status: "review_required", active: true }] })),
    createProject: vi.fn(async (project_id: string) => ({ created_project_id: project_id,
      catalog: { schema_version: "project-catalog-1.0", active_project_id: initialProduct.project_id, preserved_bedroom_available: true,
        switch_requires_restart: true, saved_approval_restored: false, truncated: false,
        projects: [{ project_id: initialProduct.project_id, kind: "default", status: "review_required", active: true },
          { project_id, kind: "named_room", status: "empty", active: false }] } })),
    createBedroomProject: vi.fn(async (project_id: string) => ({ created_project_id: project_id,
      source: "preserved_bedroom_photo", build_allowed: false, physical_authority: false,
      catalog: { schema_version: "project-catalog-1.0", active_project_id: initialProduct.project_id, preserved_bedroom_available: true,
        switch_requires_restart: true, saved_approval_restored: false, truncated: false,
        projects: [{ project_id: initialProduct.project_id, kind: "default", status: "review_required", active: true },
          { project_id, kind: "named_room", status: "review_required", active: false }] } })),
    createManualRoomProject: vi.fn(async (value: { project_id: string }) => ({
      created_project_id: value.project_id, photo_interpreted: false, burger_visual_included: false,
      physical_authority: false,
      catalog: { schema_version: "project-catalog-1.0", active_project_id: initialProduct.project_id,
        preserved_bedroom_available: true, burger_visual_available: true,
        switch_requires_restart: true, saved_approval_restored: false, truncated: false,
        projects: [{ project_id: initialProduct.project_id, kind: "default", status: "review_required", active: true },
          { project_id: value.project_id, kind: "named_room", status: "review_required", active: false }] },
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
    continueRoomRecipe: vi.fn(async () => { current = { ...current, phase: "draft_ready", error: null }; return current; }),
    resumeSavedScene: vi.fn(async () => { current = { ...current, phase: "draft_ready", error: null }; return current; }),
    generate: vi.fn(async () => { current = workflow("draft_ready"); return current; }),
    cancelGeneration: vi.fn(async () => current),
    acknowledge: vi.fn(async () => { current = { ...current, acknowledged_revision: draft.revision, build_allowed: true }; return current; }),
    acquireLease: vi.fn(async () => ({ control_lease_id: "lease", ttl_s: 3 })),
    renewLease: vi.fn(async () => ({ control_lease_id: "lease", ttl_s: 3 })),
    command: vi.fn(async () => ({ command_id: "command", status: "accepted" })),
  } as unknown as TwinPulseApi;
}

// Contract-only supervisor/API fixtures; these do not stop a real process.
function exitApi(available=true){
  const api=mockApi(workflow(),product(false)),runtime=api.runtimeState;
  api.runtimeState=vi.fn(async()=>({...await runtime(),shutdown_available:available,shutdown_requested:false}));
  api.conversation=vi.fn(async()=>({schema_version:'conversation-1.0' as const,session_id:'exit-chat',project_id:'default',revision:0,cursor:0,
    mode:null,robot_id:null,physical_authority:false as const,restore_error:null,messages:[{message_id:'history',role:'user' as const,content:'Retained conversation',
      status:'completed',created_at:'now',attachments:[],operation_id:null}],cards:[],events:[],generation:null,accepted_request_ids:[]}));
  api.providerKeys=vi.fn(async()=>({schema_version:'1.0' as const,network_called:false,note:'Read-only settings fixture',entries:[]}));
  return api;
}

describe('TwinPulse exit contract UI',()=>{
  it('routes native close through normal authenticated exit and unregisters its callback',async()=>{
    const api=exitApi();let requestClose!:()=>void;const unsubscribe=vi.fn(),reportExitResult=vi.fn();
    window.twinpulseDesktop={versions:vi.fn().mockResolvedValue({}),onExitRequested:callback=>{requestClose=callback;return unsubscribe;},reportExitResult};
    try{
      const {unmount}=render(<ChatApp api={api}/>);await waitFor(()=>expect(screen.getByRole('button',{name:'Exit TwinPulse'})).toHaveProperty('disabled',false));
      await act(async()=>requestClose());await screen.findByRole('status',{name:'TwinPulse shutdown'});
      expect(api.shutdownRuntime).toHaveBeenCalledOnce();expect(reportExitResult).toHaveBeenCalledWith({requested:true});expect(api.command).not.toHaveBeenCalled();
      unmount();expect(unsubscribe).toHaveBeenCalledOnce();
    }finally{delete window.twinpulseDesktop;}
  });
  it('submits one native close despite a stale unavailable hint, using server admission',async()=>{
    const api=exitApi(false);let requestClose!:()=>void;const reportExitResult=vi.fn();
    window.twinpulseDesktop={versions:vi.fn().mockResolvedValue({}),onExitRequested:callback=>{requestClose=callback;return vi.fn();},reportExitResult};
    try{const {unmount}=render(<ChatApp api={api}/>);await screen.findByText('Retained conversation');
      expect(screen.getByRole('button',{name:'Exit TwinPulse'})).toHaveProperty('disabled',true);
      await act(async()=>requestClose());await screen.findByRole('status',{name:'TwinPulse shutdown'});
      expect(reportExitResult).toHaveBeenCalledWith({requested:true});expect(api.shutdownRuntime).toHaveBeenCalledOnce();unmount();
    }finally{delete window.twinpulseDesktop;}
  });
  it('retains the window on authoritative busy rejection after an unavailable native hint',async()=>{
    const api=exitApi(false);let requestClose!:()=>void;const reportExitResult=vi.fn();
    vi.mocked(api.shutdownRuntime).mockRejectedValue(new Error('A robot operation remains active'));
    window.twinpulseDesktop={versions:vi.fn().mockResolvedValue({}),onExitRequested:callback=>{requestClose=callback;return vi.fn();},reportExitResult};
    try{const {unmount}=render(<ChatApp api={api}/>);await screen.findByText('Retained conversation');await act(async()=>requestClose());
      expect((await screen.findByRole('alert')).textContent).toContain('A robot operation remains active');
      expect(reportExitResult).toHaveBeenCalledWith({requested:false,code:'shutdown_unconfirmed'});
      expect(api.shutdownRuntime).toHaveBeenCalledOnce();expect(screen.queryByRole('status',{name:'TwinPulse shutdown'})).toBeNull();
      expect(screen.getAllByText('Retained conversation').length).toBeGreaterThan(0);unmount();
    }finally{delete window.twinpulseDesktop;}
  });
  it('does not duplicate or certify an unresolved native close',async()=>{
    const api=exitApi(false);let requestClose!:()=>void,reject!:(reason:Error)=>void;const reportExitResult=vi.fn();
    vi.mocked(api.shutdownRuntime).mockImplementation(()=>new Promise((_resolve,fail)=>{reject=fail;}));
    window.twinpulseDesktop={versions:vi.fn().mockResolvedValue({}),onExitRequested:callback=>{requestClose=callback;return vi.fn();},reportExitResult};
    try{const {unmount}=render(<ChatApp api={api}/>);await screen.findByText('Retained conversation');
      await act(async()=>{requestClose();requestClose();});expect(api.shutdownRuntime).toHaveBeenCalledOnce();
      expect(reportExitResult).not.toHaveBeenCalledWith({requested:true});await act(async()=>reject(new Error('ACK lost')));
      expect((await screen.findByRole('alert')).textContent).toContain('ACK lost');
      expect(screen.queryByRole('status',{name:'TwinPulse shutdown'})).toBeNull();expect(api.shutdownRuntime).toHaveBeenCalledOnce();unmount();
    }finally{delete window.twinpulseDesktop;}
  });
  it('sends one explicit exit and keeps its guidance after the backend disconnects',async()=>{
    const api=exitApi();let finish!:(value:{status:'requested';new_session_required:true})=>void;
    vi.mocked(api.shutdownRuntime).mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
    render(<ChatApp api={api}/>);
    const button=await screen.findByRole('button',{name:'Exit TwinPulse'});
    await waitFor(()=>expect(button).toHaveProperty('disabled',false));
    expect(button.closest('header')).toHaveProperty('className','chat-appbar');
    expect(screen.getByText(/Browser close only closes this screen/)).toBeTruthy();
    expect(api.shutdownRuntime).not.toHaveBeenCalled();fireEvent.click(button);fireEvent.click(button);
    expect(button).toHaveProperty('disabled',true);expect(api.shutdownRuntime).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/waiting for acknowledgement/)).toBeTruthy();
    vi.mocked(api.runtimeState).mockRejectedValue(new Error('Backend disconnected'));
    await act(async()=>{finish({status:'requested',new_session_required:true});});
    const notice=await screen.findByRole('status',{name:'TwinPulse shutdown'});
    expect(notice.textContent).toContain('shutting down its owned Isaac and backend normally');
    expect(notice.textContent).toContain('You can close this browser window');
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve,550));});
    expect(screen.getByRole('status',{name:'TwinPulse shutdown'})).toBe(notice);
    expect(screen.queryByRole('alert')).toBeNull();expect(api.shutdownRuntime).toHaveBeenCalledTimes(1);expect(api.command).not.toHaveBeenCalled();
  });
  it('shows request failure without repeating the shutdown POST',async()=>{
    const api=exitApi();vi.mocked(api.shutdownRuntime).mockRejectedValue(new Error('Shutdown unavailable'));
    render(<ChatApp api={api}/>);const button=await screen.findByRole('button',{name:'Exit TwinPulse'});
    await waitFor(()=>expect(button).toHaveProperty('disabled',false));fireEvent.click(button);
    expect((await screen.findByRole('alert')).textContent).toContain('Exit was not confirmed: Shutdown unavailable. No automatic retry.');
    expect(screen.queryByRole('status',{name:'TwinPulse shutdown'})).toBeNull();
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve,550));});
    expect(api.shutdownRuntime).toHaveBeenCalledTimes(1);expect(api.command).not.toHaveBeenCalled();
  });
  it('suspends the real viewport before POST and emits no late observation when its image fails during Exit',async()=>{
    const api=exitApi();let rejectImage!:(error:Error)=>void,finishExit!:(value:{status:'requested';new_session_required:true})=>void;
    const frame:ViewportState={state:'live',fps:6,age_ms:0,detail:'Current Isaac frame',physical_authority:false,camera_pending:false,camera_result:null,
      frame:{frame_id:1,captured_at_ms:Date.now(),applied_revision:'scene',engine_session_id:'engine',stage_epoch:'stage',camera_sequence:0,width:960,height:640,sha256:'a'.repeat(64),url:'unused'}};
    api.viewportState=vi.fn(async()=>frame);api.viewportImage=vi.fn(()=>new Promise<Blob>((_resolve,reject)=>{rejectImage=reject;}));
    api.viewportObservation=vi.fn(async()=>({execution_id:null,physical_authority:false as const}));
    vi.mocked(api.shutdownRuntime).mockImplementation(()=>{
      expect(screen.queryByRole('complementary',{name:'Digital Twin'})).toBeNull();
      expect(screen.getByRole('status',{name:'TwinPulse exit pending'})).toBeTruthy();
      return new Promise(resolve=>{finishExit=resolve;});
    });
    const {unmount}=render(<ChatApp api={api}/>);
    await waitFor(()=>expect(api.viewportImage).toHaveBeenCalledOnce());
    await waitFor(()=>expect(screen.getByRole('button',{name:'Exit TwinPulse'})).toHaveProperty('disabled',false));
    fireEvent.click(screen.getByRole('button',{name:'Exit TwinPulse'}));
    const reads={chat:vi.mocked(api.conversation).mock.calls.length,product:vi.mocked(api.productState).mock.calls.length,
      workflow:vi.mocked(api.workflow).mock.calls.length,viewport:vi.mocked(api.viewportState).mock.calls.length};
    await act(async()=>{rejectImage(new Error('Frame delivery ended during shutdown'));await new Promise(resolve=>setTimeout(resolve,800));});
    expect(api.viewportObservation).not.toHaveBeenCalled();expect(api.conversation).toHaveBeenCalledTimes(reads.chat);
    expect(api.productState).toHaveBeenCalledTimes(reads.product);expect(api.workflow).toHaveBeenCalledTimes(reads.workflow);expect(api.viewportState).toHaveBeenCalledTimes(reads.viewport);
    expect(api.shutdownRuntime).toHaveBeenCalledOnce();
    await act(async()=>{finishExit({status:'requested',new_session_required:true});});
    expect(screen.getByRole('status',{name:'TwinPulse shutdown'})).toBeTruthy();unmount();
  });
  it('restores the same unsent text, attached photo and polling after a rejected Exit',async()=>{
    const api=exitApi();let rejectExit!:(error:Error)=>void;
    vi.mocked(api.shutdownRuntime).mockImplementation(()=>new Promise((_resolve,reject)=>{rejectExit=reject;}));
    render(<ChatApp api={api}/>);await screen.findByText('Retained conversation');
    const composer=screen.getByRole('textbox',{name:'Message TwinPulse'});
    fireEvent.change(composer,{target:{value:'Keep this unsent room description'}});
    fireEvent.drop(composer.closest('form')!,{dataTransfer:{files:[new File(['photo'],'room.jpg',{type:'image/jpeg'})]}});
    const image=screen.getByAltText('Attached image preview');
    await waitFor(()=>expect(screen.getByRole('button',{name:'Exit TwinPulse'})).toHaveProperty('disabled',false));
    fireEvent.click(screen.getByRole('button',{name:'Exit TwinPulse'}));
    expect(screen.queryByRole('textbox',{name:'Message TwinPulse'})).toBeNull();
    const reads=vi.mocked(api.conversation).mock.calls.length;
    await act(async()=>{rejectExit(new Error('Shutdown rejected by current owner'));});
    expect(screen.getByRole('textbox',{name:'Message TwinPulse'})).toBe(composer);
    expect(composer).toHaveProperty('value','Keep this unsent room description');expect(screen.getByAltText('Attached image preview')).toBe(image);
    expect(screen.getByRole('alert').textContent).toContain('Shutdown rejected by current owner');
    await waitFor(()=>expect(vi.mocked(api.conversation).mock.calls.length).toBeGreaterThan(reads));
    expect(api.shutdownRuntime).toHaveBeenCalledOnce();expect(api.command).not.toHaveBeenCalled();
  });
  it('leaves history and settings readable with an unready engine and unavailable shutdown',async()=>{
    const api=exitApi(false),runtime=api.runtimeState;
    api.runtimeState=vi.fn(async()=>({...await runtime(),status:'starting',phase:'engine_start'}));
    render(<ChatApp api={api}/>);await screen.findByText('Retained conversation');
    expect(screen.getByRole('button',{name:'Exit TwinPulse'})).toHaveProperty('disabled',true);
    fireEvent.click(screen.getByRole('button',{name:'API keys'}));
    await waitFor(()=>expect(api.providerKeys).toHaveBeenCalledTimes(1));
    expect(api.shutdownRuntime).not.toHaveBeenCalled();expect(api.command).not.toHaveBeenCalled();
  });
  it('honors a shutdown already requested in another app window without submitting a new request',async()=>{
    const api=exitApi(),runtime=api.runtimeState;
    api.runtimeState=vi.fn(async()=>({...await runtime(),shutdown_requested:true,shutdown_available:false}));
    render(<ChatApp api={api}/>);await screen.findByRole('status',{name:'TwinPulse shutdown'});
    expect(api.shutdownRuntime).not.toHaveBeenCalled();expect(api.command).not.toHaveBeenCalled();
  });
});

describe("TwinPulse R5 UI", () => {
  it("keeps full-scene generation locked when a saved site scene exists", async () => {
    const saved = { ...workflow("input_ready"), saved_site_scene_protected: true };
    const api = mockApi(saved);
    render(<App api={api} />);
    await screen.findByText(/Full-scene generation is locked to protect it/);
    fireEvent.change(screen.getByPlaceholderText(/Describe/i), { target: { value: "Move the bed" } });
    expect((screen.getByRole("button", { name: "Create Draft" }) as HTMLButtonElement).disabled).toBe(true);
    expect(api.generate).not.toHaveBeenCalled();
  });
  it("offers a one-shot cancel while the owned engine is starting", async () => {
    const api = mockApi();
    vi.mocked(api.runtimeState).mockResolvedValue({
      schema_version: "1.0", status: "starting", phase: "engine_start", message: "Starting Isaac",
      started_at_utc: null, updated_at_utc: null,
      backend: { owned: true, state: "running", pid: 1 },
      engine: { owned: true, state: "running", pid: 2 }, browser: { launched: true },
    });
    render(<App api={api} />);
    fireEvent.click(await screen.findByRole("button", { name: "Cancel this startup" }));
    await screen.findByRole("button", { name: "Cancellation requested · this window will close" });
    expect(api.cancelStartup).toHaveBeenCalledTimes(1);
    expect(api.command).not.toHaveBeenCalled();
  });
  it("offers a one-shot fresh launch after owned engine startup failure", async () => {
    const api = mockApi();
    vi.mocked(api.runtimeState).mockResolvedValue({
      schema_version: "1.0", status: "error", phase: "engine_start_failed", message: "engine exited",
      retry_remaining: 3,
      started_at_utc: null, updated_at_utc: null,
      backend: { owned: true, state: "running", pid: 1 },
      engine: { owned: true, state: "exited", exit_code: 7 }, browser: { launched: true },
    });
    render(<App api={api} />);
    await screen.findByText(/Isaac import failed before a scene started/);
    expect(screen.getByText("Isaac startup failed · read-only diagnostics")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("New local project"), { target: { value: "room_three" } });
    fireEvent.change(screen.getByLabelText("Instructions (optional)"), { target: { value: "A test site" } });
    expect((screen.getByRole("button", { name: "Create empty project" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Create Draft" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "AI settings" }));
    expect((screen.getByRole("button", { name: "Save settings" }) as HTMLButtonElement).disabled).toBe(true);
    const retry = await screen.findByRole("button", { name: "Retry startup after stopping this launch" });
    fireEvent.click(retry);
    await screen.findByRole("button", { name: "Retry requested · wait for the new app window" });
    expect(api.retryLauncher).toHaveBeenCalledTimes(1);
    expect(api.createProject).not.toHaveBeenCalled();
    expect(api.generate).not.toHaveBeenCalled();
    expect(api.command).not.toHaveBeenCalled();
  });
  it("creates an empty local project without switching or granting run authority", async () => {
    const api = mockApi();
    render(<App api={api} />);
    const input = await screen.findByLabelText("New local project");
    fireEvent.change(input, { target: { value: "room_three" } });
    fireEvent.click(screen.getByRole("button", { name: "Create empty project" }));
    await screen.findByText("room_three · empty");
    expect(screen.getByText(/Created room_three\. Current project remains default/)).toBeTruthy();
    expect(api.createProject).toHaveBeenCalledWith("room_three");
    expect(api.command).not.toHaveBeenCalled();
    expect(api.continueRoomRecipe).not.toHaveBeenCalled();
  });
  it("copies the reviewed bedroom to a separate project without engine authority", async () => {
    const api = mockApi();
    render(<App api={api} />);
    fireEvent.change(await screen.findByLabelText("New local project"), { target: { value: "my_room" } });
    fireEvent.change(screen.getByLabelText("Project source"), { target: { value: "preserved_bedroom" } });
    fireEvent.click(screen.getByRole("button", { name: "Create bedroom project" }));
    await screen.findByText("my_room · review_required");
    expect(api.createBedroomProject).toHaveBeenCalledWith("my_room", expect.stringMatching(/^[0-9a-f-]{36}$/));
    expect(api.command).not.toHaveBeenCalled();
    expect(api.acknowledge).not.toHaveBeenCalled();
  });
  it("creates a separate photo room from only user-entered dimensions without provider or Build", async () => {
    const api = mockApi();
    render(<App api={api} />);
    fireEvent.change(await screen.findByLabelText("New local project"), { target: { value: "second_room" } });
    fireEvent.change(screen.getByLabelText("Project source"), { target: { value: "manual_photo" } });
    const image = new File([new Uint8Array([137, 80, 78, 71])], "room.png", { type: "image/png" });
    Object.defineProperty(image, "arrayBuffer", { value: async () => new Uint8Array([137, 80, 78, 71]).buffer });
    fireEvent.change(screen.getByLabelText("Room photo"), { target: { files: [image] } });
    fireEvent.change(screen.getByLabelText("Width (m)"), { target: { value: "3.2" } });
    fireEvent.click(screen.getByRole("button", { name: "Create photo room" }));
    await screen.findByText("second_room · review_required");
    expect(api.createManualRoomProject).toHaveBeenCalledWith(expect.objectContaining({
      project_id: "second_room", width_m: 3.2, length_m: 4, wall_height_m: 2.4,
      include_burger_visual: false, media_type: "image/png",
    }));
    expect(api.generate).not.toHaveBeenCalled();
    expect(api.command).not.toHaveBeenCalled();
    expect(api.acknowledge).not.toHaveBeenCalled();
  });
  it("passes explicit local furniture selections into a new room without photo inference", async () => {
    const api = mockApi();
    render(<App api={api} />);
    // Use the existing accessible project section; unrelated diagnostic panels
    // are not part of this form's label/role lookup or acceptance criteria.
    const projects = within(await screen.findByRole('region', { name: 'Local projects' }));
    fireEvent.change(projects.getByLabelText("New local project"), { target: { value: "furnished_room" } });
    fireEvent.change(projects.getByLabelText("Project source"), { target: { value: "manual_photo" } });
    const image = new File([new Uint8Array([137, 80, 78, 71])], "room.png", { type: "image/png" });
    Object.defineProperty(image, "arrayBuffer", { value: async () => new Uint8Array([137, 80, 78, 71]).buffer });
    fireEvent.change(projects.getByLabelText("Room photo"), { target: { files: [image] } });
    fireEvent.click(projects.getByRole("button", { name: "Add furniture preset" }));
    fireEvent.change(projects.getByLabelText("Type"), { target: { value: "desk" } });
    fireEvent.change(projects.getByLabelText("X (m)"), { target: { value: "0.6" } });
    fireEvent.change(projects.getByLabelText("Y (m)"), { target: { value: "0.7" } });
    fireEvent.change(projects.getByLabelText("Yaw (°)"), { target: { value: "90" } });
    fireEvent.click(projects.getByRole("button", { name: "Create photo room" }));
    await projects.findByText("furnished_room · review_required");
    expect(api.createManualRoomProject).toHaveBeenCalledWith(expect.objectContaining({
      project_id: "furnished_room", furniture: [{ kind: "desk", center_m: [0.6, 0.7], yaw_deg: 90 }],
    }));
    expect(api.generate).not.toHaveBeenCalled();
    expect(api.command).not.toHaveBeenCalled();
  });
  it("does not offer the private bedroom copy in a generic release lacking those assets", async () => {
    const api = mockApi();
    vi.mocked(api.projects).mockResolvedValue({
      schema_version: "project-catalog-1.0", active_project_id: "default", preserved_bedroom_available: false,
      switch_requires_restart: true, saved_approval_restored: false, truncated: false,
      projects: [{ project_id: "default", kind: "default", status: "empty", active: true }],
    });
    render(<App api={api} />);
    await screen.findByText(/generic offline release never bundles them automatically/);
    const option = screen.getByRole("option", { name: /Copy reviewed bedroom photo/ }) as HTMLOptionElement;
    expect(option.disabled).toBe(true);
    expect(api.createBedroomProject).not.toHaveBeenCalled();
  });
  it("requests a new whole-process session for a selected saved project", async () => {
    const api = mockApi();
    vi.mocked(api.projects).mockResolvedValue({
      schema_version: "project-catalog-1.0", active_project_id: "default", preserved_bedroom_available: true,
      switch_requires_restart: true, saved_approval_restored: false, truncated: false,
      projects: [
        { project_id: "default", kind: "default", status: "empty", active: true },
        { project_id: "room_two", kind: "named_room", status: "review_required", active: false },
      ],
    });
    render(<App api={api} />);
    await screen.findByText("room_two · review_required");
    fireEvent.click(screen.getByRole("button", { name: "Open room_two in a new session" }));
    await screen.findByText(/Opening room_two\. This page will disconnect/);
    expect(api.switchProject).toHaveBeenCalledWith("room_two");
    expect(api.command).not.toHaveBeenCalled();
    expect(api.continueRoomRecipe).not.toHaveBeenCalled();
  });
  it("continues a saved local room only after an explicit click without Build or Run", async () => {
    const siteDraft = {
      schema_version: "2.0" as const, artifact_id: null, revision: "s".repeat(64),
      input_revision: "i".repeat(64), plan_sha256: "p".repeat(64), request_id: "room-request",
      provider_name: "local-room-recipe", model_id: "no-provider-call", scene_id: "room_one",
      summary: "Approximate local room", source: "photo", tool_count: 1, object_count: 1,
      robot_profile_id: null, mission_id: null, navigation_map_ready: false,
      review_required: true as const, build_allowed: false, run_allowed: false as const,
      objects: draft.objects,
    };
    const saved = { ...workflow("restore_review_required"), draft: null, site_draft: siteDraft,
      error: { code: "restore_review_required", message: "Review stored draft" } };
    const state = product(false); state.project_id = "room_one";
    const api = mockApi(saved, state);
    render(<App api={api} />);
    await screen.findByRole("button", { name: "Open saved scene for review" });
    expect(api.resumeSavedScene).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Open saved scene for review" }));
    await waitFor(() => expect(api.resumeSavedScene).toHaveBeenCalledWith("room_one", siteDraft.revision, siteDraft.input_revision));
    await screen.findByText("Review site geometry");
    expect((screen.getByRole("button", { name: "Build scene geometry in Isaac" }) as HTMLButtonElement).disabled).toBe(true);
    expect(api.command).not.toHaveBeenCalled();
  });
  it("opens a general saved v2 scene through the public review action", async () => {
    const siteDraft = {
      schema_version: "2.0" as const, artifact_id: null, revision: "s".repeat(64),
      input_revision: "i".repeat(64), plan_sha256: "p".repeat(64), request_id: "original-request",
      provider_name: "fixture-provider", model_id: "old-model", scene_id: "saved_site",
      summary: "Saved site", source: "manual", tool_count: 1, object_count: 1,
      robot_profile_id: null, mission_id: null, navigation_map_ready: false,
      review_required: true as const, build_allowed: false, run_allowed: false as const,
      objects: draft.objects,
    };
    const saved = { ...workflow("restore_review_required"), draft: null, site_draft: siteDraft };
    const api = mockApi(saved);
    render(<App api={api} />);
    const reopen = await screen.findByRole("button", { name: "Open saved scene for review" });
    fireEvent.click(reopen);
    await waitFor(() => expect(api.resumeSavedScene).toHaveBeenCalledWith(
      "default", siteDraft.revision, siteDraft.input_revision));
    expect(api.generate).not.toHaveBeenCalled();
    expect(api.acknowledge).not.toHaveBeenCalled();
    expect(api.command).not.toHaveBeenCalled();
  });
  it.each([
    { connected: true, staleIdentity: false, allowed: true },
    { connected: false, staleIdentity: false, allowed: false },
    { connected: true, staleIdentity: true, allowed: false },
  ])("standalone scene review requires a matching connected snapshot ($connected/$staleIdentity)", async ({ connected, staleIdentity, allowed }) => {
    const saved = { ...workflow("restore_review_required"), draft: null, site_draft: {
      schema_version: "2.0" as const, artifact_id: null, revision: "s".repeat(64),
      input_revision: "i".repeat(64), plan_sha256: "p".repeat(64), request_id: "room-request",
      provider_name: "local-room-recipe", model_id: "no-provider-call", scene_id: "room_one",
      summary: "Approximate local room", source: "photo", tool_count: 1, object_count: 1,
      robot_profile_id: null, mission_id: null, navigation_map_ready: false,
      review_required: true as const, build_allowed: false, run_allowed: false as const,
      objects: draft.objects,
    } };
    const state = product(connected);
    if (staleIdentity) state.snapshot = { ...state.snapshot!, engine_session_id: "old-engine" };
    const api = mockApi(saved, state);
    vi.mocked(api.runtimeState).mockResolvedValue({
      schema_version: "1.0", status: "unmanaged", phase: "standalone",
      message: "Started without the TwinPulse process manager",
      started_at_utc: null, updated_at_utc: null,
      backend: { owned: false, state: "running" }, engine: { owned: false, state: "unknown" },
      browser: { launched: false },
    });
    render(<App api={api} />);
    const button = await screen.findByRole("button", { name: "Open saved scene for review" }) as HTMLButtonElement;
    await waitFor(() => expect(button.disabled).toBe(!allowed));
    expect(api.resumeSavedScene).not.toHaveBeenCalled();
    expect(api.command).not.toHaveBeenCalled();
  });
  it.each(["old_success", "old_failure"])("ignores reordered %s after a newer state read", async mode => {
    const ready = { ...workflow("draft_ready"), acknowledged_revision: draft.revision, build_allowed: true };
    const api = mockApi(ready,product());
    render(<App api={api} />);
    await screen.findByText("Backend ready");
    fireEvent.click(screen.getByRole("button", { name: "Review Twin" }));
    const build = screen.getByRole("button", { name: "Build in Isaac Sim" }) as HTMLButtonElement;
    let resolve!: (value: ProductState) => void, reject!: (reason: Error) => void;
    const delayed = new Promise<ProductState>((yes,no) => { resolve=yes; reject=no; });
    vi.mocked(api.productState).mockImplementationOnce(() => delayed);
    if (mode === "old_success") vi.mocked(api.productState).mockRejectedValue(new Error("new read failed"));
    await waitFor(() => expect(api.productState).toHaveBeenCalledTimes(3), {timeout:2000});
    await waitFor(() => expect(build.disabled).toBe(mode === "old_success"));
    await act(async () => { if(mode === "old_success") resolve(product()); else reject(new Error("old read failed")); });
    expect(build.disabled).toBe(mode === "old_success");
    expect(api.command).not.toHaveBeenCalled();
  });

  it("clears cached engine authority after a failed state read and recovers without a command", async () => {
    const ready = { ...workflow("draft_ready"), acknowledged_revision: draft.revision, build_allowed: true };
    const api = mockApi(ready, product());
    render(<App api={api} />);
    await screen.findByText("Backend ready");
    fireEvent.click(screen.getByRole("button", { name: "Review Twin" }));
    const build = screen.getByRole("button", { name: "Build in Isaac Sim" }) as HTMLButtonElement;
    expect(build.disabled).toBe(false);
    vi.mocked(api.productState).mockRejectedValue(new Error("Synthetic connection loss"));
    await waitFor(() => expect(build.disabled).toBe(true), { timeout: 2000 });
    expect(screen.getByText("Isaac disconnected")).toBeTruthy();
    vi.mocked(api.productState).mockResolvedValue(product());
    await waitFor(() => expect(build.disabled).toBe(false), { timeout: 2000 });
    expect(api.command).not.toHaveBeenCalled();
    expect(api.acquireLease).not.toHaveBeenCalled();
  });

  it("does not renew an expired lease identifier returned with lease_owned false", async () => {
    const state = product(); state.control_lease_id = "expired"; state.lease_owned = false;
    const api = mockApi(workflow(),state);
    render(<App api={api} />);
    await screen.findByText("Backend ready");
    await new Promise(resolve => setTimeout(resolve, 1300));
    expect(api.renewLease).not.toHaveBeenCalled();
  });

  it.each(["success", "rejected", "disconnected", "unsupported"])("v2 explicit scene control: %s never builds or acknowledges implicitly", async (mode) => {
    const siteDraft = {
      schema_version: "2.0" as const, artifact_id: "site-artifact", revision: "s".repeat(64),
      input_revision: "i".repeat(64), plan_sha256: "p".repeat(64), request_id: "site-request",
      provider_name: "fake", model_id: "fake", scene_id: "site", summary: "Synthetic site",
      source: "fixture", tool_count: 1, object_count: 1, robot_profile_id: null, mission_id: null,
      navigation_map_ready: false, review_required: true as const, build_allowed: false,
      run_allowed: false as const, objects: draft.objects,
    };
    const currentProduct = product(mode !== "disconnected");
    if (currentProduct.snapshot && mode !== "unsupported") currentProduct.snapshot.capabilities = ["site_scene_build_v2"];
    const api = mockApi({ ...workflow("draft_ready"), draft: null, site_draft: siteDraft }, currentProduct);
    if (mode === "rejected") vi.mocked(api.acquireLease).mockRejectedValue(new Error("Control is owned by another session"));
    render(<App api={api} />);
    await screen.findByText("Backend ready");
    fireEvent.click(screen.getByRole("button", { name: "Review Twin" }));
    const control = screen.getByRole("button", { name: "Acquire scene control" }) as HTMLButtonElement;
    expect(api.acquireLease).not.toHaveBeenCalled();
    expect(control.disabled).toBe(mode === "disconnected" || mode === "unsupported");
    fireEvent.click(control);
    if (mode === "success" || mode === "rejected") await waitFor(() => expect(api.acquireLease).toHaveBeenCalledTimes(1));
    else expect(api.acquireLease).not.toHaveBeenCalled();
    if (mode === "rejected") await screen.findByText("The request failed. Check the status and try again.");
    expect((screen.getByRole("button", { name: "Build scene geometry in Isaac" }) as HTMLButtonElement).disabled).toBe(true);
    expect(api.acknowledge).not.toHaveBeenCalled();
    expect(api.command).not.toHaveBeenCalled();
  });

  it("distinguishes backend, engine, and persisted credential status", async () => {
    render(<StrictMode><App api={mockApi(workflow(), product(false))} /></StrictMode>);
    await waitFor(() => expect(screen.getByText("Backend ready")).toBeTruthy());
    expect(screen.getByText("Isaac disconnected")).toBeTruthy();
    expect(screen.getByText("API key saved")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "AI settings" }));
    expect(screen.getByText(/Live request not tested or not successful/)).toBeTruthy();
  });

  it("creates a deterministic draft and requires acknowledgement", async () => {
    const api = mockApi();
    render(<App api={api} />);
    await waitFor(() => screen.getByText("Backend ready"));
    const create = screen.getByRole("button", { name: "Create Draft" }) as HTMLButtonElement;
    expect(create.disabled).toBe(true);
    expect((screen.getByLabelText("Instructions (optional)") as HTMLTextAreaElement).value).toBe("");
    fireEvent.change(screen.getByLabelText("Instructions (optional)"), { target: { value: "A small test site" } });
    fireEvent.click(create);
    await waitFor(() => screen.getByText("Review the draft"));
    expect(api.selectInput).toHaveBeenCalledWith(expect.objectContaining({ prompt: "A small test site" }));
    const build = screen.getByRole("button", { name: "Build in Isaac Sim" }) as HTMLButtonElement;
    expect(build.disabled).toBe(true);
    fireEvent.click(screen.getByRole("checkbox", { name: "I reviewed the limits of this draft version." }));
    await waitFor(() => expect(build.disabled).toBe(false));
  });

  it("sends a selected photo with blank instructions and preserves its Korean filename", async () => {
    const api = mockApi();
    const photo = new File([new Uint8Array([1, 2, 3])], "현장 사진.png", { type: "image/png" });
    Object.defineProperty(photo, "arrayBuffer", { value: async () => new Uint8Array([1, 2, 3]).buffer });
    render(<App api={api} />);
    await waitFor(() => screen.getByText("Backend ready"));
    fireEvent.change(screen.getByLabelText("Choose photo or drawing"), { target: { files: [photo] } });
    fireEvent.click(screen.getByRole("button", { name: "Create Draft" }));
    await waitFor(() => expect(api.selectInput).toHaveBeenCalledWith(expect.objectContaining({
      prompt: "", name: "현장 사진.png", media_type: "image/png", content_base64: "AQID",
    })));
  });

  it("keeps Korean instructions as user data", async () => {
    const api = mockApi();
    render(<App api={api} />);
    await waitFor(() => screen.getByText("Backend ready"));
    fireEvent.change(screen.getByLabelText("Instructions (optional)"), { target: { value: "현장 통로를 넓혀줘" } });
    fireEvent.click(screen.getByRole("button", { name: "Create Draft" }));
    await waitFor(() => expect(api.selectInput).toHaveBeenCalledWith(expect.objectContaining({ prompt: "현장 통로를 넓혀줘" })));
  });

  it("keeps AI generation disabled in offline simulation mode", async () => {
    const api = mockApi({ ...workflow(), mode: "simulation_offline" });
    render(<App api={api} />);
    await waitFor(() => screen.getByText("Offline simulation · AI generation unavailable"));
    fireEvent.change(screen.getByLabelText("Instructions (optional)"), { target: { value: "A test site" } });
    expect((screen.getByRole("button", { name: "Create Draft" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.queryByRole("button", { name: "AI settings" })).toBeNull();
  });

  it("uses stable error codes for recovery text without showing a raw server message", async () => {
    const failed = { ...workflow(), error: { code: "input_reselection_required", message: "Internal server detail" } };
    render(<App api={mockApi(failed)} />);
    expect(await screen.findByText("Provider settings changed. Select the input again before generating.")).toBeTruthy();
    expect(screen.queryByText("Internal server detail")).toBeNull();
  });

  it("shows safety state separately from ordinary runtime state", async () => {
    const unsafe = product();
    unsafe.snapshot = { ...unsafe.snapshot!, safety_state: "off_route", safety_reason: "Reset required" };
    render(<App api={mockApi(workflow("draft_ready"), unsafe)} />);
    await waitFor(() => screen.getByText("Safety stop · off_route"));
    fireEvent.click(screen.getByRole("button", { name: "Simulate" }));
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
    await waitFor(() => screen.getByText("Isaac disconnected"));
    fireEvent.click(screen.getByRole("button", { name: "Simulate" }));
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
    expect(await screen.findByText("API key saved")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "AI settings" }));
    expect(screen.getByText("Key stored in Windows Credential Manager")).toBeTruthy();
    const key = screen.getByLabelText("API key") as HTMLInputElement;
    expect(key.type).toBe("password");
    fireEvent.change(key, { target: { value: "sk-ui-secret" } });
    fireEvent.click(screen.getByRole("button", { name: "Save settings" }));
    await waitFor(() => expect(api.saveProviderSettings).toHaveBeenCalledWith(expect.objectContaining({ api_key: "sk-ui-secret" })));
    expect(screen.queryByDisplayValue("sk-ui-secret")).toBeNull();
  });

  it("keeps Build on review until a matching receipt and scene snapshot confirm success", async () => {
    const ready = { ...workflow("draft_ready"), acknowledged_revision: draft.revision, build_allowed: true };
    const state = product();
    const accepted: Operation = {
      command_id: "build-1", command_type: "build_scene", project_id: "default",
      engine_session_id: "engine", stage_epoch: "stage", expected_applied_revision: draft.revision,
      status: "accepted", receipt: null,
    };
    const api = mockApi(ready, state);
    api.command = vi.fn(async () => { state.operations = [accepted]; return accepted; }) as TwinPulseApi["command"];
    render(<App api={api} />);
    await screen.findByText("Backend ready");
    fireEvent.click(screen.getByRole("button", { name: "Review Twin" }));
    fireEvent.click(screen.getByRole("button", { name: "Build in Isaac Sim" }));
    await screen.findByText("build_scene · Accepted · waiting for Isaac Sim");
    expect(screen.queryByText("Simulation controls")).toBeNull();
    expect((screen.getByRole("button", { name: "Build in Isaac Sim" }) as HTMLButtonElement).disabled).toBe(true);

    state.operations = [{ ...accepted, status: "running" }];
    await screen.findByText("build_scene · Running in Isaac Sim");
    expect(screen.queryByText("Simulation controls")).toBeNull();

    const receipt = {
      schema_version: "1.1" as const, command_id: "build-1", command_type: "build_scene" as const,
      project_id: "default", engine_session_id: "engine", stage_epoch: "stage",
      status: "succeeded" as const, message: "built", error_code: null,
      applied_revision: draft.revision, build_fingerprint: "f".repeat(64),
    };
    state.operations = [{ ...accepted, status: "succeeded", receipt }];
    await screen.findByText("build_scene · Engine reported success · waiting for matching scene state");
    expect(screen.queryByText("Simulation controls")).toBeNull();

    state.snapshot = { ...state.snapshot!, applied_revision: draft.revision, permitted_commands: ["get_state", "run"] };
    expect(await screen.findByText("Simulation controls")).toBeTruthy();
    expect(screen.getByText(/Current draft built/)).toBeTruthy();
  });

  it("keeps a failed Build on review and identifies an older scene without claiming the new draft was built", async () => {
    const ready = { ...workflow("draft_ready"), acknowledged_revision: draft.revision, build_allowed: true };
    const state = product();
    state.snapshot = { ...state.snapshot!, applied_revision: "old-revision" };
    state.operations = [{
      command_id: "build-failed", command_type: "build_scene", project_id: "default",
      engine_session_id: "engine", stage_epoch: "stage", expected_applied_revision: draft.revision,
      status: "failed", receipt: {
        schema_version: "1.1", command_id: "build-failed", command_type: "build_scene", project_id: "default",
        engine_session_id: "engine", stage_epoch: "stage", status: "failed", message: "secret backend detail",
        error_code: "build_rejected", applied_revision: null, build_fingerprint: null,
      },
    }];
    render(<App api={mockApi(ready, state)} />);
    await screen.findByText("Backend ready");
    expect(screen.getByText(/Previous scene remains/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Review Twin" }));
    expect(screen.getByText("build_scene · Did not complete · review details")).toBeTruthy();
    fireEvent.click(screen.getByText("Details"));
    expect(screen.getByText(/build_rejected/)).toBeTruthy();
    expect(screen.queryByText("secret backend detail")).toBeNull();
    expect(screen.queryByText("Simulation controls")).toBeNull();
  });

  it("marks a disconnected or replaced engine scene unconfirmed and disables controls", async () => {
    const state = product();
    state.snapshot = { ...state.snapshot!, applied_revision: draft.revision, permitted_commands: ["run", "pause", "reset"], telemetry_available: true, distance_to_goal_m: 5 };
    state.stage_epoch = "new-stage";
    render(<App api={mockApi(workflow("draft_ready"), state)} />);
    await screen.findByText("Backend ready");
    expect(screen.getByText("Scene not confirmed · Isaac disconnected or changed")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Simulate" }));
    expect((screen.getByRole("button", { name: /Run/ }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: /Pause/ }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: /Reset/ }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("Status illustration · not the live 3D view")).toBeTruthy();
    expect(screen.getAllByText("Not measured").length).toBeGreaterThan(0);
    expect(screen.queryByText("5.00 m")).toBeNull();
  });

  it("does not silently retry an unknown Build or run an old draft after input changes", async () => {
    const ready = { ...workflow("draft_ready"), input: { revision: "new-input", input_kind: "photo", prompt_length: 0, image_name: "site.png", media_type: "image/png", image_sha256: "i", width: 1, height: 1, sidecar_name: null, sidecar_sha256: null, measurement_count: 0 }, build_allowed: false };
    const state = product();
    state.snapshot = { ...state.snapshot!, applied_revision: draft.revision, permitted_commands: ["run", "pause", "reset"] };
    state.operations = [{
      command_id: "unknown-build", command_type: "build_scene", project_id: "default",
      engine_session_id: "engine", stage_epoch: "stage", expected_applied_revision: draft.revision,
      status: "unknown", receipt: null,
    }];
    render(<App api={mockApi(ready, state)} />);
    await screen.findByText("Input changed · create and review a new draft");
    fireEvent.click(screen.getByRole("button", { name: "Review Twin" }));
    expect(screen.getByText("build_scene · Result unknown · check Isaac Sim before trying again")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Build in Isaac Sim" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Simulate" }));
    expect((screen.getByRole("button", { name: /Run/ }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("shows a v2 scene draft with Build gated until capability and acknowledgement", async () => {
    const siteDraft = {
      schema_version: "2.0" as const, artifact_id: "site-artifact", revision: "s".repeat(64), input_revision: "i".repeat(64),
      plan_sha256: "p".repeat(64), request_id: "site-request", provider_name: "fake",
      model_id: "fake-model", scene_id: "site_demo", summary: "A site proposal",
      source: "photo", tool_count: 1, object_count: 1, robot_profile_id: null,
      mission_id: null, navigation_map_ready: false, review_required: true as const,
      build_allowed: false, run_allowed: false as const, objects: draft.objects,
    };
    const state = { ...workflow("draft_ready"), draft: null, site_draft: siteDraft };
    const api = mockApi(state);
    render(<App api={api} />);
    await screen.findByText("Backend ready");
    fireEvent.click(screen.getByRole("button", { name: "Review Twin" }));
    expect(screen.getByText("Review site geometry")).toBeTruthy();
    expect(screen.getAllByText("Not proposed").length).toBeGreaterThan(0);
    expect((screen.getByRole("button", { name: "Build scene geometry in Isaac" }) as HTMLButtonElement).disabled).toBe(true);
    expect(api.acknowledge).not.toHaveBeenCalled();
    expect(api.command).not.toHaveBeenCalled();
  });

  it("sends only the explicit v2 site build command when capability is present", async () => {
    const revision = "s".repeat(64);
    const siteDraft = {
      schema_version: "2.0" as const, artifact_id: "site-artifact", revision,
      input_revision: "i".repeat(64), plan_sha256: "p".repeat(64),
      request_id: "site-request", provider_name: "fake", model_id: "fake-model",
      scene_id: "site_demo", summary: "A site proposal", source: "photo",
      tool_count: 1, object_count: 1, robot_profile_id: null, mission_id: null,
      navigation_map_ready: false, review_required: true as const,
      build_allowed: true, run_allowed: false as const, objects: draft.objects,
    };
    const currentProduct = product();
    currentProduct.snapshot!.capabilities = ["simulation", "site_scene_build_v2"];
    currentProduct.snapshot!.permitted_commands = ["build_site_scene", "get_state"];
    const api = mockApi({ ...workflow("draft_ready"), draft: null, site_draft: siteDraft,
      acknowledged_revision: revision, build_allowed: true }, currentProduct);
    render(<App api={api} />);
    await screen.findByText("Backend ready");
    fireEvent.click(screen.getByRole("button", { name: "Review Twin" }));
    fireEvent.click(screen.getByRole("button", { name: "Build scene geometry in Isaac" }));
    await waitFor(() => expect(api.command).toHaveBeenCalledWith("build_site_scene", revision, "site-artifact"));
    expect(api.command).not.toHaveBeenCalledWith("run", expect.anything());
  });
});
