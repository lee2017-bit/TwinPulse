// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { Activity, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {flushSync} from 'react-dom';
import type { CommandType, Operation } from "./engine-contracts";
import { ApiError, fileToBase64, TwinPulseApi } from "./api";
import { en, errorMessage } from "./i18n/en";
import { RobotReport } from "./RobotReport";
import { RobotDiagnostics } from "./RobotDiagnostics";
import { RobotReadiness } from "./RobotReadiness";
import { RobotController } from "./RobotController";
import { ScanReview } from "./ScanReview";
import { NativeScanReview } from "./NativeScanReview";
import { BedroomTwin } from "./BedroomTwin";
import { AutomaticDemo } from './AutomaticDemo';
import { SceneEditReview } from "./SceneEditReview";
import { PresentationReview } from "./PresentationReview";
import { SiteReviewEvidence } from "./SiteReviewEvidence";
import { ChatWorkspace } from './ChatWorkspace';
import { DesktopTesting } from './DesktopTesting';
import type { ProductState, ProjectCatalogState, ProviderSettingsState, RuntimeDiagnostics, SupervisorState, WorkflowState } from "./types";

type Screen = "build" | "review" | "simulate";
type ManualFurniture = { kind: string; x: string; y: string; yaw: string };
const FURNITURE_KINDS = ["bed", "wardrobe", "desk", "chair", "sofa", "dining_table", "storage"] as const;

// Keep the transport identity stable across React renders. Creating this in a
// default parameter would tear down the polling effect after the first state
// update and leave accepted engine operations looking permanently pending.
const DEFAULT_API = new TwinPulseApi();

const EMPTY_PRODUCT: ProductState = {
  project_id: "default",
  engine_connected: false,
  engine_session_id: null,
  stage_epoch: null,
  lease_owned: false,
  control_lease_id: null,
  snapshot: null,
  operations: [],
  artifacts: [],
};

const EMPTY_SUPERVISOR: SupervisorState = {
  schema_version: "1.0", status: "unknown", phase: "starting", message: "Launcher status pending",
  started_at_utc: null, updated_at_utc: null,
  backend: { owned: false, state: "unknown" }, engine: { owned: false, state: "unknown" },
  browser: { launched: false },
};

function messageOf(error: unknown): string {
  if (error instanceof ApiError) return `${errorMessage(error.code)} (${error.code})`;
  return en.unknownError;
}

function compact(value: string | null | undefined): string {
  return value ? `${value.slice(0, 8)}…${value.slice(-4)}` : "—";
}

const NEBIUS_PROFILE = "nebius_token_factory";
const NEBIUS_SITE_PROFILE = "nebius_site_v2";
const isNebiusProfile = (profile: string) => profile === NEBIUS_PROFILE || profile === NEBIUS_SITE_PROFILE;
const NEBIUS_BASE_URL = "https://api.tokenfactory.nebius.com/v1/";
const NEBIUS_PLANNER = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B";

export function App({ api = DEFAULT_API }: { api?: TwinPulseApi }) {
  const [advanced, setAdvanced] = useState(false);
  const [exit,setExit]=useState<{api:TwinPulseApi;phase:'idle'|'pending'|'requested';available:boolean;error:string|null}>({api,phase:'idle',available:false,error:null});
  const owner=useRef(api);owner.current=api;
  const inFlight=useRef(false),requested=useRef(false);
  const state=exit.api===api?exit:{api,phase:'idle' as const,available:false,error:null};
  useEffect(()=>{
    let closed=false,timer:ReturnType<typeof setTimeout>|undefined;
    inFlight.current=false;requested.current=false;setExit({api,phase:'idle',available:false,error:null});
    const poll=async()=>{
      if(closed||requested.current)return;
      try{
        const next=await api.runtimeState();if(closed)return;
        if(next.shutdown_requested===true)requested.current=true;
        setExit(current=>current.api===api?{...current,available:next.shutdown_available===true&&!requested.current,
          phase:requested.current?'requested':current.phase}:current);
      }catch{if(!closed)setExit(current=>current.api===api?{...current,available:false}:current);}
      finally{if(!closed&&!requested.current)timer=setTimeout(()=>void poll(),500);}
    };
    void api.bootstrap().then(()=>{if(!closed)void poll();}).catch(()=>{/* Existing workspace shows the session diagnosis. */});
    return()=>{closed=true;clearTimeout(timer);};
  },[api]);
  const shutdown=async()=>{
    if(requested.current){window.twinpulseDesktop?.reportExitResult({requested:true});return;}
    if(inFlight.current||!state.available){window.twinpulseDesktop?.reportExitResult({requested:false,code:inFlight.current?'shutdown_pending':'shutdown_unavailable'});return;}
    // Stop child effects before the shutdown POST can close their backend.
    // Activity retains unsent text/files if a rejected exit must reopen them.
    inFlight.current=true;flushSync(()=>setExit(current=>({...current,phase:'pending',error:null})));
    try{
      const result=await api.shutdownRuntime();if(owner.current!==api)return;
      if(result.status!=='requested'||result.new_session_required!==true)throw new Error('Exit acknowledgement is invalid');
      requested.current=true;setExit({api,phase:'requested',available:false,error:null});
      window.twinpulseDesktop?.reportExitResult({requested:true});
    }catch(caught){if(owner.current===api&&!requested.current)setExit(current=>({...current,phase:'idle',available:false,
      error:`Exit was not confirmed: ${caught instanceof Error?caught.message:'request failed'}. No automatic retry.`}));
      window.twinpulseDesktop?.reportExitResult({requested:false,code:caught instanceof ApiError&&/^[a-z0-9_]+$/.test(caught.code)?caught.code:'shutdown_unconfirmed'});}
    finally{if(owner.current===api)inFlight.current=false;}
  };
  const desktopShutdown=useRef(shutdown);desktopShutdown.current=shutdown;
  useEffect(()=>window.twinpulseDesktop?.onExitRequested(()=>void desktopShutdown.current()),[]);
  const runtimeExit=<span><DesktopTesting/><button type="button" disabled={!state.available||state.phase!=='idle'} onClick={()=>void shutdown()}
    title="Available when owned runtime work is idle. Exit stops TwinPulse's owned Isaac and backend normally.">Exit TwinPulse</button>
    <small>{window.twinpulseDesktop?' Closing this app requests the same normal runtime shutdown.':' Browser close only closes this screen; Exit stops owned Isaac/backend normally.'}</small>
    {state.error&&<span role="alert"> {state.error}</span>}</span>;
  if(state.phase==='requested')return <div className="chat-workspace"><section className="chat-home" role="status" aria-label="TwinPulse shutdown">
    <h1>Exit requested</h1><p>TwinPulse is shutting down its owned Isaac and backend normally.</p>
    <p>{window.twinpulseDesktop?'The app will close after owned runtime shutdown is confirmed.':'You can close this browser window. Open TwinPulse again to reconnect.'}</p><button disabled>Exit TwinPulse</button>
  </section></div>;
  return <>{state.phase==='pending'&&<div className="chat-workspace"><section className="chat-home" role="status" aria-label="TwinPulse exit pending">
    <h1>Exiting TwinPulse</h1><p>Exit requested · waiting for acknowledgement.</p><p>Screen updates are paused while the exit request is checked.</p><button disabled>Exit TwinPulse</button>
  </section></div>}
    <Activity mode={state.phase==='pending'?'hidden':'visible'}>{advanced ? <><button className="chat-return" onClick={() => setAdvanced(false)}>← Return to chat</button><LegacyApp api={api} runtimeExit={runtimeExit}/></>
      : <ChatWorkspace api={api} advanced={() => setAdvanced(true)} runtimeExit={runtimeExit}/>}</Activity></>;
}

export function LegacyApp({ api = DEFAULT_API, runtimeExit }: { api?: TwinPulseApi; runtimeExit?:ReactNode }) {
  const [screen, setScreen] = useState<Screen>("build");
  const [workflow, setWorkflow] = useState<WorkflowState | null>(null);
  const [product, setProduct] = useState<ProductState>(EMPTY_PRODUCT);
  const [projectCatalog, setProjectCatalog] = useState<ProjectCatalogState | null>(null);
  const [newProjectId, setNewProjectId] = useState("");
  const [projectSource, setProjectSource] = useState<"empty" | "preserved_bedroom" | "manual_photo">("empty");
  const [manualRoomPhoto, setManualRoomPhoto] = useState<File | null>(null);
  const [manualRoomWidth, setManualRoomWidth] = useState("3.0");
  const [manualRoomLength, setManualRoomLength] = useState("4.0");
  const [manualRoomHeight, setManualRoomHeight] = useState("2.4");
  const [manualRoomNote, setManualRoomNote] = useState("Room dimensions entered by user; photo retained but not interpreted");
  const [manualRoomBurger, setManualRoomBurger] = useState(false);
  const [manualFurniture, setManualFurniture] = useState<ManualFurniture[]>([]);
  const [createdProjectId, setCreatedProjectId] = useState<string | null>(null);
  const [switchRequested, setSwitchRequested] = useState<string | null>(null);
  const [creatingProject, setCreatingProject] = useState(false);
  const [supervisor, setSupervisor] = useState<SupervisorState>(EMPTY_SUPERVISOR);
  const [runtimeDiagnosis, setRuntimeDiagnosis] = useState<RuntimeDiagnostics | null>(null);
  const [retryRequested, setRetryRequested] = useState(false);
  const [cancelRequested, setCancelRequested] = useState(false);
  const [providerSettings, setProviderSettings] = useState<ProviderSettingsState | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [baseUrl, setBaseUrl] = useState("https://api.openai.com/v1/");
  const [modelId, setModelId] = useState("gpt-5.6-luna");
  const [reasoningEffort, setReasoningEffort] = useState("low");
  const [providerProfile, setProviderProfile] = useState("openai");
  const [apiKey, setApiKey] = useState("");
  const [credentialReapproval, setCredentialReapproval] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [inputKind, setInputKind] = useState("auto");
  const [file, setFile] = useState<File | null>(null);
  const [sidecar, setSidecar] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [savedSourceMissing, setSavedSourceMissing] = useState(false);
  const [leaseId, setLeaseId] = useState<string | null>(null);
  const [submittedBuild, setSubmittedBuild] = useState<Operation | null>(null);
  const refreshStarted = useRef(0);
  const refreshApplied = useRef(0);
  const bedroomCreateAttempt = useRef<{ projectId: string; requestId: string } | null>(null);
  const manualCreateAttempt = useRef<{ projectId: string; photo: File; dimensions: string;
    note: string; burger: boolean; furniture: string; requestId: string } | null>(null);

  const refresh = async () => {
    const requestNumber = ++refreshStarted.current;
    let nextWorkflow: WorkflowState, nextProduct: ProductState, nextSupervisor: SupervisorState;
    try {
      [nextWorkflow, nextProduct, nextSupervisor] = await Promise.all([
        api.workflow(), api.productState(), api.runtimeState(),
      ]);
    } catch (caught) {
      if (requestNumber >= refreshApplied.current) {
        refreshApplied.current = requestNumber;
        // Keep draft/history for review, not cached engine/control authority.
        setProduct(previous => ({ ...previous, engine_connected: false,
          lease_owned: false, control_lease_id: null, snapshot: null, engine_readiness: undefined }));
        setLeaseId(null);
      }
      throw caught;
    }
    if (requestNumber < refreshApplied.current) return;
    refreshApplied.current = requestNumber;
    setWorkflow(nextWorkflow);
    setProduct(nextProduct);
    setSupervisor(nextSupervisor);
    setLeaseId(nextProduct.lease_owned ? nextProduct.control_lease_id : null);
  };

  const applyProviderSettings = (next: ProviderSettingsState) => {
    setProviderSettings(next);
    setBaseUrl(next.base_url);
    setModelId(next.model_id);
    setReasoningEffort(next.reasoning_effort);
    setProviderProfile(next.provider_profile);
  };

  useEffect(() => {
    let active = true;
    const boot = async () => {
      try {
        await api.bootstrap();
        if (active) {
          const settings = await api.providerSettings();
          applyProviderSettings(settings);
          await refresh();
          if (active) await api.projects().then(setProjectCatalog).catch(() => setProjectCatalog(null));
        }
      } catch (caught) {
        if (active) setError(messageOf(caught));
      }
    };
    void boot();
    const timer = window.setInterval(() => {
      if (active) void refresh().catch((caught) => setError(messageOf(caught)));
    }, 500);
    return () => { active = false; window.clearInterval(timer); };
  }, [api]);

  useEffect(() => {
    if (!leaseId) return;
    const timer = window.setInterval(() => {
      void api.renewLease(leaseId).catch((caught) => {
        setLeaseId(null);
        setError(messageOf(caught));
      });
    }, 1_000);
    return () => window.clearInterval(timer);
  }, [api, leaseId]);

  useEffect(() => {
    if (supervisor.status !== "error") { setRuntimeDiagnosis(null); return; }
    let active = true;
    void api.runtimeDiagnostics().then((result) => {
      if (active) setRuntimeDiagnosis(result);
    }).catch(() => { if (active) setRuntimeDiagnosis(null); });
    return () => { active = false; };
  }, [api, supervisor.status, supervisor.phase]);

  useEffect(() => {
    if (!file) { setPreview(null); return; }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const draft = workflow?.draft ?? null;
  const siteDraft = workflow?.site_draft ?? null;
  const activeRevision = siteDraft?.revision ?? draft?.revision;
  const snapshot = product.snapshot;
  const latestOperation = product.operations.at(-1) ?? null;
  const stageCurrent = Boolean(product.engine_connected && snapshot &&
    snapshot.engine_session_id === product.engine_session_id && snapshot.stage_epoch === product.stage_epoch);
  const sceneRevision = stageCurrent ? snapshot?.applied_revision : null;
  const applied = Boolean(draft && sceneRevision === draft.revision);
  const siteApplied = Boolean(siteDraft && sceneRevision === siteDraft.revision);
  const inputChanged = Boolean(workflow?.input && draft && workflow.input.revision !== draft.input_revision);
  const buildOperation = product.operations.find((item) => item.command_id === submittedBuild?.command_id) ?? submittedBuild ??
    [...product.operations].reverse().find((item) => ["build_scene", "build_site_scene"].includes(item.command_type) && item.expected_applied_revision === activeRevision) ?? null;
  const buildPending = Boolean(buildOperation && ["accepted", "running"].includes(buildOperation.status) &&
    buildOperation.expected_applied_revision === activeRevision);
  const buildConfirmed = Boolean(buildOperation?.status === "succeeded" && buildOperation.receipt?.status === "succeeded" &&
    buildOperation.receipt.applied_revision === activeRevision && buildOperation.receipt.engine_session_id === product.engine_session_id &&
    buildOperation.receipt.stage_epoch === product.stage_epoch && stageCurrent && sceneRevision === activeRevision);
  const permitted = new Set(snapshot?.permitted_commands ?? []);
  const telemetryStale = !stageCurrent || !snapshot?.telemetry_available;
  const liveTelemetry = telemetryStale ? null : snapshot;
  const isOffline = workflow?.mode === "simulation_offline";
  const generationMode = isOffline ? en.offlineMode : workflow?.mode === "explicit_fixture" ? en.fixtureMode : en.configuredProvider;

  const stageLabel = useMemo(() => {
    if (!product.engine_connected) return en.isaacDisconnected;
    if (!stageCurrent) return en.stageUnconfirmed;
    if (snapshot?.safety_state) return `${en.safetyStop} · ${snapshot.safety_state}`;
    return `Isaac ${snapshot?.runtime_state ?? en.isaacConnecting}`;
  }, [product.engine_connected, snapshot, stageCurrent]);

  useEffect(() => {
    if (draft && submittedBuild && buildOperation?.command_id === submittedBuild.command_id && buildConfirmed && !inputChanged) {
      setScreen("simulate");
      setSubmittedBuild(null);
    }
  }, [draft, submittedBuild, buildOperation, buildConfirmed, inputChanged]);

  const generate = async () => {
    setBusy("generate");
    setError(null);
    try {
      const encoded = file ? await fileToBase64(file) : null;
      const sidecarEncoded = sidecar ? await fileToBase64(sidecar) : null;
      await api.selectInput({
        name: file?.name ?? null,
        input_kind: inputKind,
        prompt,
        media_type: file?.type || null,
        content_base64: encoded,
        sidecar_name: sidecar?.name ?? null,
        sidecar_content_base64: sidecarEncoded,
      });
      let next = await api.generate();
      setWorkflow(next);
      while (next.phase === "generating") {
        await new Promise((resolve) => window.setTimeout(resolve, 120));
        next = await api.workflow();
        setWorkflow(next);
      }
      if (next.phase === "draft_ready") setScreen("review");
    } catch (caught) {
      setError(messageOf(caught));
    } finally {
      setBusy(null);
    }
  };

  const cancelGeneration = async () => {
    try { setWorkflow(await api.cancelGeneration()); }
    catch (caught) { setError(messageOf(caught)); }
  };

  const continueSavedScene = async () => {
    const saved = siteDraft ?? draft;
    if (!saved?.input_revision) return;
    setBusy("resume-scene");
    setError(null);
    setSavedSourceMissing(false);
    try {
      const restored = await api.resumeSavedScene(product.project_id,
        siteDraft?.original_scene_revision ?? saved.revision, saved.input_revision);
      setWorkflow(restored);
      setScreen("review");
    } catch (caught) {
      if (caught instanceof ApiError && caught.code === "saved_input_missing") setSavedSourceMissing(true);
      setError(messageOf(caught));
    }
    finally { setBusy(null); }
  };

  const reattachSavedSource = async () => {
    const saved = siteDraft ?? draft;
    if (!saved?.input_revision || (workflow?.saved_input?.image_name && !file)) return;
    setBusy("reattach-source");
    setError(null);
    try {
      const restored = await api.reattachSavedSource(product.project_id,
        siteDraft?.original_scene_revision ?? saved.revision,
        saved.input_revision, file?.name ?? null, file?.type || null,
        file ? await fileToBase64(file) : null);
      setSavedSourceMissing(false);
      setWorkflow(restored);
      setScreen("review");
    } catch (caught) { setError(messageOf(caught)); }
    finally { setBusy(null); }
  };

  const acknowledge = async () => {
    const revision = siteDraft?.revision ?? draft?.revision;
    if (!revision) return;
    setBusy("acknowledge");
    setError(null);
    try { setWorkflow(await api.acknowledge(revision)); }
    catch (caught) { setError(messageOf(caught)); }
    finally { setBusy(null); }
  };

  const ensureLease = async () => {
    if (leaseId) return leaseId;
    const lease = await api.acquireLease();
    setLeaseId(lease.control_lease_id);
    return lease.control_lease_id;
  };

  // V2 build eligibility includes the engine's lease-dependent permissions.
  // Acquire separately: a disabled Build button cannot acquire its own lease.
  const requestSceneControl = async () => {
    setBusy("scene_control");
    setError(null);
    try {
      const lease = await api.acquireLease();
      setLeaseId(lease.control_lease_id);
      await refresh();
    } catch (caught) { setError(messageOf(caught)); }
    finally { setBusy(null); }
  };

  const command = async (type: CommandType) => {
    setBusy(type);
    setError(null);
    try {
      await ensureLease();
      if (type === "build_scene") {
        if (!draft) throw new ApiError("draft_missing", en.noValidatedDraft);
        const accepted = await api.command(type, draft.revision, draft.artifact_id);
        setSubmittedBuild(accepted);
      } else if (type === "build_site_scene") {
        if (!siteDraft?.artifact_id) throw new ApiError("site_draft_missing", "Select a reviewed site scene first.");
        const accepted = await api.command(type, siteDraft.revision, siteDraft.artifact_id);
        setSubmittedBuild(accepted);
      } else {
        await api.command(type, snapshot?.applied_revision ?? draft?.revision ?? null);
      }
      await refresh();
    } catch (caught) {
      setError(messageOf(caught));
    } finally {
      setBusy(null);
    }
  };

  const saveSettings = async () => {
    setBusy("settings");
    setError(null);
    try {
      const next = await api.saveProviderSettings({
        base_url: baseUrl,
        model_id: modelId,
        reasoning_effort: reasoningEffort,
        api_key: apiKey,
        credential_reapproval: credentialReapproval,
        provider_profile: providerProfile,
      });
      setApiKey("");
      setCredentialReapproval(false);
      applyProviderSettings(next);
      setShowSettings(false);
    } catch (caught) {
      setError(messageOf(caught));
    } finally {
      setBusy(null);
    }
  };

  // Standalone local bridge rehearsals have no launcher status file. They may
  // review scenes only after a current connected engine snapshot exists; an
  // owned launcher in starting/error state never uses this fallback.
  const sceneControlsReady = supervisor.status === "ready" ||
    (supervisor.status === "unmanaged" && product.engine_connected && product.snapshot !== null &&
      product.snapshot.engine_session_id === product.engine_session_id &&
      product.snapshot.stage_epoch === product.stage_epoch);


  return (
    <div className="shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label={en.home}>
          <span className="brand-mark">TP</span>
          <span><strong>TwinPulse</strong><small>{en.brandTagline}</small></span>
        </a>
        <div className="status-strip" aria-label={en.connectionStatus}>
          <Status tone={workflow ? "ok" : "wait"} label={workflow ? en.backendReady : en.backendConnecting} />
          <Status tone={product.engine_connected ? "ok" : "bad"} label={stageLabel} />
          <Status tone={isOffline ? "warn" : providerSettings?.credential_configured ? "ok" : "warn"} label={isOffline ? en.offlineStatus : providerSettings?.credential_configured ? en.keySaved : en.keyMissing} />
          {!isOffline && <button className="settings-button" onClick={() => setShowSettings((value) => !value)}>{en.settings}</button>}
          {runtimeExit}
        </div>
      </header>

      <nav className="step-nav" aria-label={en.workflowSteps}>
        <Step active={screen === "build"} done={Boolean(draft || siteDraft)} number="01" label={en.addPhoto} onClick={() => setScreen("build")} />
        <Step active={screen === "review"} done={Boolean(workflow?.build_allowed)} number="02" label={en.reviewTwin} onClick={() => setScreen("review")} />
        <Step active={screen === "simulate"} done={applied} number="03" label={en.simulate} onClick={() => setScreen("simulate")} />
      </nav>

      <main id="top">
        <AutomaticDemo api={api} available={!!workflow} projectId={product.project_id} />
        <BedroomTwin api={api} product={product} refresh={refresh} backendReady={!!workflow} />
        <RobotDiagnostics api={api} />
        <RobotReadiness api={api} available={Boolean(workflow) && product.project_id === 'default'} />
        <RobotController api={api} backendReady={!!workflow && supervisor.status === "ready"} physicalProjectAllowed={product.project_id === "default"} />
        <RobotReport api={api} />
        <ScanReview api={api} workflow={workflow} productBusy={Boolean(busy) || !sceneControlsReady} onWorkflow={next => { setWorkflow(next); setScreen("review"); }} />
        <NativeScanReview api={api} />
        <section className="hero">
          <div>
            <p className="eyebrow">LOCAL / AUTHENTICATED / ISAAC 6.0.1</p>
            <h1>{en.heroFirst}<br /><span>{en.heroSecond}</span></h1>
          </div>
          <div className="truth-card">
            <span>{en.currentState}</span>
            <strong>{supervisor.status === "error" ? "Isaac startup failed · read-only diagnostics" :
              supervisor.status === "starting" ? "Isaac starting · scene controls locked" :
              siteApplied ? "Site geometry built · Run unavailable" : inputChanged ? en.inputNeedsDraft : applied ? en.sceneBuilt : buildPending ? en.buildPending : (draft || siteDraft) ? en.draftNotBuilt : en.waitingForInput}</strong>
            <small>{en.stateEvidence}</small>
          </div>
        </section>

        <section className="state-grid" aria-label={en.stateBreakdown}>
          <Metric label={en.currentInput} value={workflow?.input ? `${workflow.input.input_kind} · ${compact(workflow.input.revision)}` : en.none} />
          <Metric label={en.currentDraft} value={siteDraft ? `Site draft · ${compact(siteDraft.revision)}` : draft ? `${inputChanged ? en.draftOutdated : en.draftReady} · ${compact(draft.revision)}` : en.none} />
          <Metric label={en.isaacScene} value={sceneRevision ? `${(applied || siteApplied) ? en.currentDraftApplied : en.previousScene} · ${compact(sceneRevision)}` : stageCurrent ? en.noScene : en.sceneUnconfirmed} />
          <Metric label={en.currentRun} value={stageCurrent && sceneRevision ? snapshot?.runtime_state ?? en.notMeasured : en.runUnconfirmed} />
        </section>

        {projectCatalog && <section className="panel project-panel" aria-label="Local projects">
          <div className="section-heading"><div><p className="panel-index">LOCAL / PROJECTS</p><h2>Project · {projectCatalog.active_project_id}</h2></div>
            <button onClick={() => void api.projects().then(setProjectCatalog).catch((caught) => setError(messageOf(caught)))}>Refresh projects</button></div>
          <p className="fine">Saved drafts can be reviewed after reopening. Approval, engine lease, and robot readiness are never restored.</p>
          <ul className="project-list">{projectCatalog.projects.map(item => <li key={item.project_id}>
            {item.project_id} · {item.status}{item.active ? " · current" : ""}
            {!item.active && ["empty", "review_required"].includes(item.status) && <button type="button"
              disabled={switchRequested !== null || supervisor.status !== "ready"}
              onClick={() => void api.switchProject(item.project_id).then(() => setSwitchRequested(item.project_id)).catch((caught) => setError(messageOf(caught)))}>
              Open {item.project_id} in a new session
            </button>}
            {!item.active && item.recovery_fingerprint && ["recovery_required", "import_required"].includes(item.status) &&
              <button type="button" disabled={creatingProject || supervisor.status !== "ready" || !projectCatalog.preserved_bedroom_available}
                onClick={() => {
                  if (!item.recovery_fingerprint) return;
                  const attempt = bedroomCreateAttempt.current?.projectId === item.project_id
                    ? bedroomCreateAttempt.current : { projectId: item.project_id, requestId: crypto.randomUUID() };
                  bedroomCreateAttempt.current = attempt;
                  setCreatingProject(true);
                  setError(null);
                  void api.recoverBedroomProject(item.project_id, attempt.requestId, item.recovery_fingerprint)
                    .then((result) => { bedroomCreateAttempt.current = null; setProjectCatalog(result.catalog); setCreatedProjectId(result.created_project_id); })
                    .catch((caught) => setError(messageOf(caught)))
                    .finally(() => setCreatingProject(false));
                }}>Preserve incomplete original and recreate {item.project_id}</button>}
          </li>)}</ul>
          <form className="project-create" onSubmit={(event) => {
            event.preventDefault();
            if (supervisor.status !== "ready" || !/^[a-z0-9][a-z0-9_-]{0,63}$/.test(newProjectId) || newProjectId === "default" || creatingProject) return;
            setCreatingProject(true);
            setError(null);
            void (async () => {
              if (projectSource === "empty") return api.createProject(newProjectId);
              if (projectSource === "preserved_bedroom") {
                if (bedroomCreateAttempt.current?.projectId !== newProjectId) {
                  bedroomCreateAttempt.current = { projectId: newProjectId, requestId: crypto.randomUUID() };
                }
                return api.createBedroomProject(newProjectId, bedroomCreateAttempt.current.requestId);
              }
              if (!manualRoomPhoto || manualRoomPhoto.size > 10 * 1024 * 1024 ||
                  !["image/jpeg", "image/png", "image/webp"].includes(manualRoomPhoto.type)) {
                throw new Error("Choose a PNG, JPEG or WebP room photo under 10 MB.");
              }
              const width = Number(manualRoomWidth), length = Number(manualRoomLength), height = Number(manualRoomHeight);
              if (!Number.isFinite(width) || !Number.isFinite(length) || !Number.isFinite(height) ||
                  width < 1 || width > 12 || length < 1 || length > 12 || height < 1.8 || height > 4 ||
                  !manualRoomNote.trim() || manualRoomNote.length > 500) {
                throw new Error("Enter width/length 1–12 m, wall height 1.8–4 m, and a short note.");
              }
              const dimensions = `${width}:${length}:${height}`;
              const furniture = manualFurniture.map((item) => ({
                kind: item.kind, center_m: [Number(item.x), Number(item.y)] as [number, number],
                yaw_deg: Number(item.yaw),
              }));
              if (manualFurniture.some((item) => !item.x.trim() || !item.y.trim() || !item.yaw.trim()) ||
                  furniture.some((item) => !FURNITURE_KINDS.includes(item.kind as typeof FURNITURE_KINDS[number]) ||
                  !item.center_m.every(Number.isFinite) || !Number.isFinite(item.yaw_deg) || Math.abs(item.yaw_deg) > 180)) {
                throw new Error("Choose a furniture preset and finite X/Y/yaw values (yaw −180° to 180°).");
              }
              const furnitureKey = JSON.stringify(furniture);
              const previous = manualCreateAttempt.current;
              if (!previous || previous.projectId !== newProjectId || previous.photo !== manualRoomPhoto ||
                  previous.dimensions !== dimensions || previous.note !== manualRoomNote ||
                  previous.burger !== manualRoomBurger || previous.furniture !== furnitureKey) {
                manualCreateAttempt.current = { projectId: newProjectId, photo: manualRoomPhoto, dimensions,
                  note: manualRoomNote, burger: manualRoomBurger, furniture: furnitureKey, requestId: crypto.randomUUID() };
              }
              return api.createManualRoomProject({
                project_id: newProjectId, request_id: manualCreateAttempt.current!.requestId,
                prompt: manualRoomNote, media_type: manualRoomPhoto.type,
                photo_base64: await fileToBase64(manualRoomPhoto), width_m: width, length_m: length,
                wall_height_m: height, include_burger_visual: manualRoomBurger,
                ...(furniture.length ? { furniture } : {}),
              });
            })().then((result) => {
              bedroomCreateAttempt.current = null;
              manualCreateAttempt.current = null;
              setProjectCatalog(result.catalog);
              setCreatedProjectId(result.created_project_id);
              setNewProjectId("");
            }).catch((caught) => setError(caught instanceof Error ? caught.message : messageOf(caught)))
              .finally(() => setCreatingProject(false));
          }}>
            <label htmlFor="new-project-id">New local project</label>
            <input id="new-project-id" value={newProjectId} onChange={(event) => setNewProjectId(event.target.value)}
              maxLength={64} autoComplete="off" spellCheck={false} placeholder="room_name" />
            <label htmlFor="project-source">Project source</label>
            <select id="project-source" value={projectSource} onChange={(event) => setProjectSource(event.target.value as "empty" | "preserved_bedroom" | "manual_photo")}>
              <option value="empty">Empty project</option>
              <option value="preserved_bedroom" disabled={!projectCatalog.preserved_bedroom_available}>Copy reviewed bedroom photo, approximate room and Burger visual</option>
              <option value="manual_photo">My photo + dimensions I enter</option>
            </select>
            {projectSource === "manual_photo" && <div className="manual-room-fields">
              <label htmlFor="manual-room-photo">Room photo</label>
              <input id="manual-room-photo" type="file" accept="image/png,image/jpeg,image/webp"
                onChange={(event) => setManualRoomPhoto(event.target.files?.[0] ?? null)} />
              <label htmlFor="manual-room-width">Width (m)</label>
              <input id="manual-room-width" type="number" min="1" max="12" step="0.01" value={manualRoomWidth}
                onChange={(event) => setManualRoomWidth(event.target.value)} />
              <label htmlFor="manual-room-length">Length (m)</label>
              <input id="manual-room-length" type="number" min="1" max="12" step="0.01" value={manualRoomLength}
                onChange={(event) => setManualRoomLength(event.target.value)} />
              <label htmlFor="manual-room-height">Wall height (m)</label>
              <input id="manual-room-height" type="number" min="1.8" max="4" step="0.01" value={manualRoomHeight}
                onChange={(event) => setManualRoomHeight(event.target.value)} />
              <label htmlFor="manual-room-note">Source note</label>
              <input id="manual-room-note" value={manualRoomNote} maxLength={500}
                onChange={(event) => setManualRoomNote(event.target.value)} />
              <label className="manual-room-check"><input type="checkbox" checked={manualRoomBurger}
                disabled={!projectCatalog.burger_visual_available}
                onChange={(event) => setManualRoomBurger(event.target.checked)} />Include pinned Burger visual</label>
              <div className="manual-room-furniture">
                <p>Furniture presets (optional; up to 3). Origin is room centre; +Y points toward the closed back wall. Positions and rotations are your choices, not measurements from the photo.</p>
                {manualFurniture.map((item, index) => <fieldset key={index}>
                  <legend>Furniture {index + 1}</legend>
                  <label htmlFor={`furniture-kind-${index}`}>Type</label>
                  <select id={`furniture-kind-${index}`} value={item.kind} onChange={(event) => setManualFurniture((previous) => previous.map((entry, i) => i === index ? { ...entry, kind: event.target.value } : entry))}>
                    {FURNITURE_KINDS.map((kind) => <option key={kind} value={kind}>{kind.replace("_", " ")}</option>)}
                  </select>
                  {(["x", "y", "yaw"] as const).map((field) => <label key={field} htmlFor={`furniture-${field}-${index}`}>
                    {field === "yaw" ? "Yaw (°)" : `${field.toUpperCase()} (m)`}
                    <input id={`furniture-${field}-${index}`} type="number" step="0.01" value={item[field]}
                      onChange={(event) => setManualFurniture((previous) => previous.map((entry, i) => i === index ? { ...entry, [field]: event.target.value } : entry))} />
                  </label>)}
                  <button type="button" onClick={() => setManualFurniture((previous) => previous.filter((_, i) => i !== index))}>Remove furniture {index + 1}</button>
                </fieldset>)}
                <button type="button" disabled={manualFurniture.length >= 3} onClick={() => setManualFurniture((previous) => [...previous, { kind: "bed", x: "0", y: "0", yaw: "0" }])}>Add furniture preset</button>
              </div>
              <p className="fine">The photo is retained locally, not interpreted. The 3D rectangle uses only your entered dimensions; its front wall is open for viewing. Burger is visual-only, not a physical pose or motion permission.</p>
            </div>}
            <button type="submit" disabled={supervisor.status !== "ready" || creatingProject || (projectSource === "preserved_bedroom" && !projectCatalog.preserved_bedroom_available) || (projectSource === "manual_photo" && !manualRoomPhoto) || newProjectId === "default" || !/^[a-z0-9][a-z0-9_-]{0,63}$/.test(newProjectId)}>
              {creatingProject ? "Creating…" : projectSource === "empty" ? "Create empty project" : projectSource === "manual_photo" ? "Create photo room" : bedroomCreateAttempt.current?.projectId === newProjectId ? "Retry bedroom creation" : "Create bedroom project"}
            </button>
          </form>
          {createdProjectId && <p className="fine" role="status">Created {createdProjectId}. Current project remains {projectCatalog.active_project_id}; choose Open to close this session and load the new project.</p>}
          {switchRequested && <p className="fine" role="status">Opening {switchRequested}. This page will disconnect; use the new authenticated window. Saved draft data remains, but Build approval and engine control do not carry over.</p>}
          {projectSource === "preserved_bedroom" && <p className="fine">Copies only the already reviewed local room photo, approximate geometry and pinned Burger display asset. No measured scale, robot pose, Build approval or physical authority is transferred. The new project must be reopened and reviewed.</p>}
          {projectSource === "manual_photo" && !projectCatalog.burger_visual_available && <p className="fine">Pinned Burger files are unavailable in this installation; this room can still be saved and reviewed without the visual model.</p>}
          {!projectCatalog.preserved_bedroom_available && <p className="fine">This installation does not contain the private reviewed bedroom photo and Burger asset. The generic offline release never bundles them automatically; use an existing saved project or create an empty one.</p>}
          {projectCatalog.truncated && <p className="fine">Project inventory is truncated; use an explicit project ID to open a project not shown here.</p>}
          <p className="fine">Open stops the current owned backend and Isaac engine, then starts both under the selected saved project with a new authenticated window. An active generation, scene command, or physical-console job blocks switching. If the new start fails, your saved project files remain available.</p>
        </section>}

        {error && <div className="error-banner" role="alert"><strong>{en.reviewRequired}</strong><span>{error}</span><button onClick={() => setError(null)}>{en.close}</button></div>}
        {workflow?.error && <div className="error-banner" role="alert"><strong>{workflow.error.code}</strong><span>{errorMessage(workflow.error.code)}</span></div>}
        {supervisor.status === "error" && <div className="error-banner" role="alert"><strong>{en.launcherError} · {supervisor.phase}</strong><span>{supervisor.message}</span>
          {runtimeDiagnosis?.engine_startup?.phase === "isaac_import" && <span>Isaac import failed before a scene started. The saved diagnostic summary identifies the observed package origins; review it and the local owner-only engine log before changing the Isaac installation.</span>}
          {runtimeDiagnosis?.engine_startup?.phase === "simulation_app_init" && <span>Isaac imported, but SimulationApp initialization failed. Review the local graphics/Kit startup log and saved diagnostic summary; no scene command was sent.</span>}
          {!runtimeDiagnosis?.engine_startup && <span>Startup did not finish. Save the safe summary and inspect the local owner-only engine log before retrying; this screen does not prove a package cause.</span>}
          <button onClick={() => void api.runtimeDiagnostics().then((bundle) => {
            const url = URL.createObjectURL(new Blob([JSON.stringify(bundle, null, 2)], { type: "application/json" }));
            const link = document.createElement("a");
            link.href = url;
            link.download = "twinpulse-runtime-diagnostics.json";
            link.click();
            window.setTimeout(() => URL.revokeObjectURL(url), 0);
          }).catch((caught) => setError(messageOf(caught)))}>Save safe diagnostic summary</button>
          <button disabled={retryRequested || (supervisor.retry_remaining ?? 0) < 1} onClick={() => void api.retryLauncher().then(() => setRetryRequested(true)).catch((caught) => setError(messageOf(caught)))}>
            {retryRequested ? "Retry requested · wait for the new app window" : "Retry startup after stopping this launch"}
          </button><span>{(supervisor.retry_remaining ?? 0) < 1 ? "Retry limit reached. Save diagnostics and restart the launcher after reviewing the cause." : "Retry starts a new authenticated session. This page will disconnect; use the new window. No project approval or robot readiness is restored."}</span>
        </div>}
        {supervisor.status === "starting" && <div className="runtime-banner"><strong>{en.launcherStarting} · {supervisor.phase}</strong><span>{supervisor.message}</span>
          <button disabled={cancelRequested} onClick={() => void api.cancelStartup().then(() => setCancelRequested(true)).catch((caught) => setError(messageOf(caught)))}>
            {cancelRequested ? "Cancellation requested · this window will close" : "Cancel this startup"}
          </button></div>}

        {showSettings && !isOffline && <section className="panel settings-panel" aria-labelledby="settings-title">
          <div className="section-heading"><div><p className="panel-index">LOCAL / SECURE SETTINGS</p><h2 id="settings-title">{en.settings}</h2></div><Status tone={providerSettings?.credential_configured ? "ok" : "warn"} label={providerSettings?.credential_configured ? en.keyStoredInWindows : en.keyNotStored} /></div>
          <p className="muted">{en.keyStorage}</p>
          {providerSettings && <p className="fine">Profile: {providerSettings.provider_profile} · Adapter: {providerSettings.adapter_kind} · Capabilities {providerSettings.capability_checked ? en.capabilitiesChecked : en.capabilitiesUnchecked} · Live request {providerSettings.live_request_succeeded ? en.liveRequestSucceeded : en.liveRequestNotTested}</p>}
          <div className="settings-grid">
            <label>{en.providerPreset}<select value={providerProfile} onChange={(event) => {
              const profile = event.target.value;
              setProviderProfile(profile);
              if (isNebiusProfile(profile)) {
                setBaseUrl(NEBIUS_BASE_URL); setModelId(NEBIUS_PLANNER); setReasoningEffort("low");
              } else {
                setBaseUrl("https://api.openai.com/v1/"); setModelId("gpt-5.6-luna"); setReasoningEffort("low");
              }
            }}><option value="openai">OpenAI Responses</option><option value={NEBIUS_PROFILE}>Nebius · legacy route (v1)</option><option value={NEBIUS_SITE_PROFILE}>Nebius · site scene proposal (v2)</option></select></label>
            <label>Base URL<input value={baseUrl} disabled={isNebiusProfile(providerProfile)} onChange={(event) => setBaseUrl(event.target.value)} autoComplete="off" /></label>
            <label>{en.plannerModel}<input value={modelId} disabled={isNebiusProfile(providerProfile)} onChange={(event) => setModelId(event.target.value)} autoComplete="off" /></label>
            <label>{en.reasoning}<select value={reasoningEffort} disabled={isNebiusProfile(providerProfile)} onChange={(event) => setReasoningEffort(event.target.value)}><option value="low">low</option><option value="medium">medium</option><option value="high">high</option></select></label>
            <label>{en.apiKey}<input type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder={providerSettings?.credential_configured ? en.keepKey : en.enterKey} autoComplete="new-password" /></label>
          </div>
          {isNebiusProfile(providerProfile) && <p className="fine">Observer: google/gemma-3-27b-it · Planner: {NEBIUS_PLANNER} · {en.manualFallback}: openbmb/MiniCPM-V-4_5 · {en.noAutomaticRetry}</p>}
          {providerProfile === NEBIUS_SITE_PROFILE && <p className="fine">Site plan 2.0 requests scene geometry without requiring a robot or mission. Build is scene-only; Run stays unavailable. Switching profiles requires key re-entry.</p>}
          <label className="credential-reapproval"><input type="checkbox" checked={credentialReapproval} onChange={(event) => setCredentialReapproval(event.target.checked)} /> {en.reapproveKey}</label>
          <div className="action-row end"><button onClick={() => { setApiKey(""); setCredentialReapproval(false); setShowSettings(false); }}>{en.cancel}</button><button className="primary settings-save" disabled={busy === "settings" || supervisor.status !== "ready"} onClick={() => void saveSettings()}>{busy === "settings" ? en.saving : en.saveSettings}</button></div>
          <p className="fine">{en.settingsConsequence}</p>
        </section>}

        {screen === "build" && (
          <section className="workspace two-column" aria-labelledby="build-title">
            <div className="panel form-panel">
              <p className="panel-index">01 / DESCRIBE</p>
              <h2 id="build-title">{en.addInput}</h2>
              <p className="muted">{en.imagePrimary}</p>
              {workflow?.phase === "restore_review_required" && (siteDraft ?? draft) &&
                <div className="warning-card" role="status"><div><strong>Saved scene · {product.project_id}</strong><p>Source: {(siteDraft ?? draft)?.provider_name} · Original input revision: {compact((siteDraft ?? draft)?.input_revision ?? "")}.</p><p>Original input and scene are validated again. This opens review only; it does not call a provider, Build, move a robot, or restore approval. If the immutable original is missing, reattachment is required.</p></div><button disabled={Boolean(busy) || !sceneControlsReady || !(siteDraft ?? draft)?.input_revision} onClick={() => void continueSavedScene()}>Open saved scene for review</button></div>}
              {savedSourceMissing && workflow?.phase === "restore_review_required" && <div className="warning-card" role="status">
                <strong>Original archive missing</strong>
                <p>{workflow.saved_input?.image_name ? `Choose the identical original ${workflow.saved_input.image_name} below; its name, type, and bytes must match.` : "This saved scene is text-only; restore its verified manifest without an image."}</p>
                <button disabled={Boolean(busy) || !sceneControlsReady || Boolean(workflow.saved_input?.image_name && !file)} onClick={() => void reattachSavedSource()}>Reattach identical source and open review</button>
              </div>}
              <label>{en.inputKind}
                <select value={inputKind} onChange={(event) => setInputKind(event.target.value)}>
                  <option value="auto">{en.autoDetect}</option><option value="photo">{en.photo}</option><option value="drawing">{en.drawing}</option>
                </select>
              </label>
              <label>{en.instructions}
                <textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder={en.instructionsPlaceholder} rows={5} maxLength={8000} />
              </label>
              <div className="upload-row">
                <label className="upload-button">{en.chooseImage}<input type="file" accept="image/png,image/jpeg,image/webp" onChange={(event) => { const selected = event.target.files?.[0] ?? null; setFile(selected); if (!selected) setSidecar(null); }} /></label>
                {file && <button className="text-button" onClick={() => { setFile(null); setSidecar(null); }}>{en.remove}</button>}
              </div>
              <p className="fine">{en.imageLimits}</p>
              {providerSettings && isNebiusProfile(providerSettings.provider_profile) && !file && <p className="fine">{en.nebiusNeedsImage}</p>}
              <div className="upload-row">
                <label className="upload-button secondary">{en.sidecar}<input type="file" accept="application/json,.json" disabled={!file} onChange={(event) => setSidecar(event.target.files?.[0] ?? null)} /></label>
                {sidecar && <button className="text-button" onClick={() => setSidecar(null)}>{en.remove}</button>}
              </div>
              <p className="fine">{en.sidecarHelp}</p>
              <div className="action-row">
                <button className="primary" disabled={!sceneControlsReady || isOffline || workflow?.saved_site_scene_protected || Boolean(busy) || (!prompt.trim() && !file) || Boolean(providerSettings && isNebiusProfile(providerSettings.provider_profile) && !file)} onClick={() => void generate()}>{busy === "generate" ? en.creatingDraft : en.createDraft}</button>
                <button disabled={workflow?.phase !== "generating"} onClick={() => void cancelGeneration()}>{en.cancel}</button>
              </div>
              {isOffline && <p className="fine">{en.offlineHelp}</p>}
              {workflow?.saved_site_scene_protected && <p className="fine" role="status">This project already contains a saved site scene. Full-scene generation is locked to protect it. Create and open a new project for a new environment, or return to Review to use the existing Add/Change/Undo preview and save flow.</p>}
            </div>
            <div className="panel preview-panel">
              <p className="panel-index">REFERENCE</p>
              {preview ? <img src={preview} alt={en.selectedReference} /> : <div className="empty-preview"><span>+</span><strong>{en.noReference}</strong><small>{en.textOnly}</small></div>}
              <dl className="meta-list">
                <div><dt>{en.file}</dt><dd>{file?.name ?? en.none}</dd></div>
                <div><dt>{en.classification}</dt><dd>{inputKind}</dd></div>
                <div><dt>{en.measurements}</dt><dd>{sidecar?.name ?? en.none}</dd></div>
                <div><dt>{en.generationMode}</dt><dd>{generationMode}</dd></div>
              </dl>
            </div>
          </section>
        )}

        {screen === "review" && (
          <section className="workspace" aria-labelledby="review-title">
            <div className="section-heading"><div><p className="panel-index">02 / REVIEW</p><h2 id="review-title">{en.draftReview}</h2></div><span className="revision">REV {compact(siteDraft?.revision ?? draft?.revision)}</span></div>
            {siteDraft ? <>
              <div className="summary-grid">
                <Metric label={en.allowedTools} value={`${siteDraft.tool_count}`} /><Metric label={en.sceneObjects} value={`${siteDraft.object_count}`} />
                <Metric label={en.robot} value={siteDraft.robot_profile_id ?? "Not proposed"} /><Metric label={en.source} value={siteDraft.source} />
              </div>
              <div className="operation-line"><span>{en.generationRecord} · Site plan 2.0</span><strong>{siteDraft.model_id} · PLAN {compact(siteDraft.plan_sha256)}</strong><small>{siteDraft.provider_name} · input {compact(siteDraft.input_revision)}</small></div>
              {siteDraft.review_provenance && <SiteReviewEvidence evidence={siteDraft.review_provenance} />}
              <div className="panel"><h3>{siteDraft.scene_id}</h3><p>{siteDraft.summary}</p><p>Mission: {siteDraft.mission_id ?? "Not proposed"} · Navigation map: {siteDraft.navigation_map_ready ? "Available for review" : "Not available"}</p></div>
              {siteDraft.derived_review_revision && <p role="status">Offline-derived geometry · alignment unverified · original retained ({compact(siteDraft.original_scene_revision)}). New scene acknowledgement is required; no Run.</p>}
              <div className="panel table-wrap"><table><thead><tr><th>ID</th><th>{en.kind}</th><th>{en.position}</th><th>{en.size}</th><th>{en.source}</th></tr></thead><tbody>{siteDraft.objects.map((item) => <tr key={item.id}><td><code>{item.id}</code></td><td>{item.kind}</td><td>{item.position_m.map((value) => value.toFixed(2)).join(" / ")}</td><td>{item.dimensions_m.map((value) => value.toFixed(2)).join(" × ")}</td><td><span className="source-tag">{item.provenance}</span></td></tr>)}</tbody></table></div>
              {workflow?.phase === "draft_ready" && <SceneEditReview api={api} site={siteDraft}
                onNewEnvironment={() => setScreen("build")}
                onApplied={(next) => { setWorkflow(next); setSubmittedBuild(null); }} />}
              {workflow?.phase === "draft_ready" && workflow.presentation &&
                <PresentationReview api={api} presentation={workflow.presentation} disabled={Boolean(busy)}
                  onSaved={(next) => { setWorkflow(next); setSubmittedBuild(null); }} />}
              <div className="warning-card" role="status"><div><strong>Review site geometry</strong><p>Build transfers only the reviewed scene geometry to Isaac. A robot, mission and Run are not inferred or enabled. Build requires a connected v2-capable Isaac engine and acknowledgement of this input.</p></div><label className="ack"><input type="checkbox" checked={workflow?.acknowledged_revision === siteDraft.revision} disabled={workflow?.acknowledged_revision === siteDraft.revision || Boolean(busy) || !siteDraft.artifact_id} onChange={() => void acknowledge()} /> {en.acknowledge}</label></div>
              {!product.lease_owned && <div className="action-row"><button disabled={!stageCurrent || !snapshot?.capabilities.includes("site_scene_build_v2") || Boolean(busy)} onClick={() => void requestSceneControl()}>Acquire scene control</button><p className="fine">Requests control of this Isaac session only. It does not build a scene or start motion. Review acknowledgement is still required.</p></div>}
              <div className="action-row end"><button onClick={() => setScreen("build")}>{en.editInput}</button><button className="primary" disabled={!siteDraft.build_allowed || !stageCurrent || !permitted.has("build_site_scene") || buildPending || Boolean(busy)} onClick={() => void command("build_site_scene")}>{busy === "build_site_scene" ? en.building : "Build scene geometry in Isaac"}</button></div>
              {buildOperation && <CommandResult operation={buildOperation} confirmed={buildConfirmed} />}
              {buildConfirmed && <p className="fine">Scene geometry built. Navigation remains unavailable until robot, map and mission validation.</p>}
            </> : !draft ? <Empty title={en.noDraft} body={en.noDraftHelp} /> : <>
              <div className="summary-grid">
                <Metric label={en.allowedTools} value={`${draft.tool_count}`} /><Metric label={en.sceneObjects} value={`${draft.object_count}`} /><Metric label={en.robot} value="2WD + caster" /><Metric label={en.source} value={draft.source} />
              </div>
              <div className="operation-line"><span>{en.generationRecord}</span><strong>{draft.model_id} · PLAN {compact(draft.plan_sha256)}</strong><small>{draft.provider_name} · request {compact(draft.request_id)} · input {compact(draft.input_revision)}</small></div>
              <div className="panel table-wrap"><table><thead><tr><th>ID</th><th>{en.kind}</th><th>{en.position}</th><th>{en.size}</th><th>{en.source}</th></tr></thead><tbody>{draft.objects.map((item) => <tr key={item.id}><td><code>{item.id}</code></td><td>{item.kind}</td><td>{item.position_m.map((value) => value.toFixed(2)).join(" / ")}</td><td>{item.dimensions_m.map((value) => value.toFixed(2)).join(" × ")}</td><td><span className="source-tag">{item.provenance}</span></td></tr>)}</tbody></table></div>
              <div className="warning-card"><div><strong>{en.approximateTitle}</strong><p>{en.approximateWarning}</p></div><label className="ack"><input type="checkbox" checked={workflow?.acknowledged_revision === draft.revision} disabled={workflow?.acknowledged_revision === draft.revision || Boolean(busy)} onChange={() => void acknowledge()} /> {en.acknowledge}</label></div>
              <div className="action-row end"><button onClick={() => setScreen("build")}>{en.editInput}</button><button className="primary" disabled={!workflow?.build_allowed || !stageCurrent || buildPending || Boolean(busy)} onClick={() => void command("build_scene")}>{busy === "build_scene" ? en.building : en.buildInIsaac}</button></div>
              {buildOperation && <CommandResult operation={buildOperation} confirmed={buildConfirmed} />}
            </>}
          </section>
        )}

        {screen === "simulate" && (
          <section className="workspace" aria-labelledby="simulate-title">
            <div className="section-heading"><div><p className="panel-index">03 / SIMULATE</p><h2 id="simulate-title">{en.simulationControls}</h2></div><Status tone={applied ? "ok" : "warn"} label={applied ? en.revisionMatched : sceneRevision ? en.previousScene : stageCurrent ? en.geometryNotApplied : en.sceneUnconfirmed} /></div>
            <div className="sim-grid">
              <div className="panel stage-card"><div className="stage-visual" role="img" aria-label={en.statusIllustration}><strong className="illustration-label">{en.statusIllustration}</strong><div className="aisle" /><div className="rack left" /><div className="rack right" /><div className="agv" /></div><div className="stage-caption"><span>{en.separate3d}</span><strong>{stageCurrent ? snapshot?.runtime_state : en.waitingForConnection}</strong><small>Stage {compact(product.stage_epoch)}</small></div></div>
              <div className="panel telemetry"><h3>{en.liveStatus}</h3><Metric label={en.distanceToGoal} value={liveTelemetry?.distance_to_goal_m == null ? en.notMeasured : `${liveTelemetry.distance_to_goal_m.toFixed(2)} m`} /><Metric label={en.crossTrackError} value={liveTelemetry?.cross_track_error_m == null ? en.notMeasured : `${liveTelemetry.cross_track_error_m.toFixed(3)} m`} /><Metric label={en.simulationTime} value={liveTelemetry?.sim_time_s == null ? en.notMeasured : `${liveTelemetry.sim_time_s.toFixed(1)} s`} /><p className={telemetryStale ? "stale" : "fresh"}>{telemetryStale ? en.telemetryStale : `Sequence ${snapshot?.sequence}`}</p></div>
            </div>
            {stageCurrent && snapshot?.safety_state && <div className="safety-banner" role="alert"><strong>{en.safetyStop} · {snapshot.safety_state}</strong><span>{snapshot.safety_reason ?? en.safetyReset}</span></div>}
            <div className="control-bar">
              <button className="run" disabled={!stageCurrent || !applied || inputChanged || !permitted.has("run") || Boolean(busy)} onClick={() => void command("run")}>▶ Run</button>
              <button disabled={!stageCurrent || !applied || inputChanged || !permitted.has("pause") || Boolean(busy)} onClick={() => void command("pause")}>Ⅱ Pause</button>
              <button disabled={!stageCurrent || !applied || inputChanged || !permitted.has("reset") || Boolean(busy)} onClick={() => void command("reset")}>↺ Reset</button>
              <button disabled={!stageCurrent || Boolean(busy)} onClick={() => void command("focus_scene")}>{en.show3dView}</button>
            </div>
            {latestOperation ? <CommandResult operation={latestOperation} confirmed={latestOperation.command_type !== "build_scene" || (latestOperation.command_id === buildOperation?.command_id && buildConfirmed)} /> : <div className="operation-line"><span>{en.recentCommand}</span><strong>{en.noCommand}</strong></div>}
          </section>
        )}
      </main>

      <footer><span>{en.localApp}</span><span>Launcher: {supervisor.status} · Generation: {workflow?.provider.connected ? "validated provider response" : generationMode}</span></footer>
    </div>
  );
}

function Status({ tone, label }: { tone: "ok" | "wait" | "warn" | "bad"; label: string }) {
  return <span className={`status ${tone}`}><i />{label}</span>;
}

function Step({ active, done, number, label, onClick }: { active: boolean; done: boolean; number: string; label: string; onClick: () => void }) {
  return <button className={active ? "active" : done ? "done" : ""} aria-label={label} onClick={onClick}><span aria-hidden="true">{done ? "✓" : number}</span>{label}</button>;
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong></div>;
}

function Empty({ title, body }: { title: string; body: string }) {
  return <div className="panel empty"><strong>{title}</strong><p>{body}</p></div>;
}

function CommandResult({ operation, confirmed }: { operation: Operation; confirmed: boolean }) {
  const status = operation.status;
  const result = status === "accepted" ? en.commandAccepted : status === "running" ? en.commandRunning :
    status === "succeeded" ? confirmed ? en.commandSucceeded : en.receiptAwaitingScene :
    status === "unknown" ? en.commandUnknown : en.commandFailed;
  return <div className="command-result" role="status"><strong>{operation.command_type} · {result}</strong><details><summary>{en.details}</summary><p>{en.commandStatus}: {status} · ID {compact(operation.command_id)}{operation.receipt?.error_code ? ` · ${en.errorCode}: ${operation.receipt.error_code}` : ""}</p></details></div>;
}
