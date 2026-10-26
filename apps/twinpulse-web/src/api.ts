// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import type { CommandType, Operation } from "./engine-contracts";
import type {ProviderKeyList} from './ApiKeySettings';
import type {RobotRegistryState} from './RobotRegistry';
import type { ProductState, ProjectCatalogState, ProviderSettingsState, RuntimeDiagnostics, SceneEditContext, SceneEditPreview, SceneEditProposal, SceneEditProposalResult, SupervisorState, WorkflowState } from "./types";
import type { RobotReportState } from "./RobotReport";
import type { ScanReviewState } from "./ScanReview";
import type { NativeScanState } from "./NativeScanReview";
import type { RobotDiagnosticsState } from "./RobotDiagnostics";
import type { RobotReadinessState } from "./RobotReadiness";
import type { ManualControllerState } from './RobotController';
import type { PhysicalState } from './PhysicalRobotController';
import {CONTROL_INPUT_TTL_MS} from './robot-control-timing';
import type { SessionList, SessionReview } from './SessionHistory';

const CSRF_KEY = "twinpulse.csrf";

export type ProjectSwitchResult = {status:'switched';project_id:string;context_id:string;new_session_required:false}
  | {status:'requested';project_id:string;context_id?:string;new_session_required:boolean};
interface ProductContext {context_id:string;project_id:string;csrf_token:string;
  project_switch?:{pending?:boolean;switch_id?:string;from_context_id?:string;target_context_id?:string;project_id?:string;new_stage_epoch?:string}|null}

export class ApiError extends Error {
  constructor(public readonly code: string, message: string) {
    super(message);
  }
}

async function parseResponse<T>(response: Response): Promise<T> {
  const body = await response.json() as { error?: { code?: string; message?: string } } & T;
  if (!response.ok) {
    throw new ApiError(body.error?.code ?? "request_failed", body.error?.message ?? "The request failed.");
  }
  return body;
}

export class TwinPulseApi {
  private environmentImageAdmission:Promise<void>|null=null;
  private async waitForEnvironmentImages():Promise<void>{
    const context=this.contextId;
    await this.environmentImageAdmission;
    if(context!==this.contextId)throw this.contextChanged();
  }
  environment():Promise<import('./environment-types').EnvironmentState>{return this.readState('/v1/product/environment');}
  alignment():Promise<import('./EnvironmentAlignment').AlignmentState>{return this.readState('/v1/product/environment/alignment');}
  environmentSurvey():Promise<import('./EnvironmentSurvey').SurveyState>{return this.readState('/v1/product/environment/survey');}
  environmentSurveyAction(body:import('./EnvironmentSurvey').SurveyAction):Promise<import('./EnvironmentSurvey').SurveyState>{return this.boundedProjectAction('/v1/product/environment/survey',body);}
  alignmentAction(body:import('./EnvironmentAlignment').AlignmentAction):Promise<import('./EnvironmentAlignment').AlignmentState>{return this.boundedProjectAction('/v1/product/environment/alignment',body);}
  environmentAction(body:import('./environment-types').EnvironmentAction):Promise<import('./environment-types').EnvironmentState>{
    if(body.action==='inspect')return this.boundedProjectAction('/v1/product/environment/action',body);
    return this.environmentTransaction(()=>this.boundedProjectAction('/v1/product/environment/action',body));
  }
  private async environmentTransaction<T>(work:()=>Promise<T>):Promise<T>{
    // Explicit environment changes drain observations before their validation
    // lock, rather than timing out polls behind deterministic compile/save.
    // No new motion, lease, timeout extension or automatic mutation retry.
    if(this.projectReadBarrier)throw new ApiError('project_switch_busy','A project transaction is already being observed.');
    const context=this.contextId;
    let release!:()=>void;
    this.projectReadBarrier=new Promise<void>(resolve=>{release=resolve;});
    this.environmentImageAdmission=this.projectReadBarrier;
    try{
      await Promise.allSettled([...this.stateReads.values(),...this.imageReads,...this.leaseActions]);
      if(context!==this.contextId)throw this.contextChanged();
      return await work();
    }finally{this.environmentImageAdmission=null;this.projectReadBarrier=null;release();}
  }
  robotFleet():Promise<import('./robot-fleet-types').RobotFleetState>{return this.readState('/v1/product/robot-fleet');}
  robotFleetFloor():Promise<import('./robot-fleet-types').FloorMapState>{return this.readState('/v1/product/robot-fleet/floor');}
  robotFleetAction(body:import('./robot-fleet-types').RobotFleetAction):Promise<import('./robot-fleet-types').RobotFleetState>{
    // Each hold has a short deadline and must never wait behind a prior hold.
    if(body.action==='drive')return this.fleetDrive(body);
    return this.boundedProjectAction('/v1/product/robot-fleet',body);
  }
  private async fleetDrive(body:Extract<import('./robot-fleet-types').RobotFleetAction,{action:'drive'}>):Promise<import('./robot-fleet-types').RobotFleetState>{
    // Per-robot policy is pinned at connection on the server. This transport
    // ceiling does not grant a new lifetime or override that policy.
    const remaining=Math.min(1000,body.payload.expires_at_ms-Date.now());
    if(!Number.isFinite(remaining)||remaining<=0)throw new ApiError('fleet_input_expired','Held input expired before delivery.');
    const controller=new AbortController();let timer:ReturnType<typeof setTimeout>|undefined;
    try{return await Promise.race([this.request<import('./robot-fleet-types').RobotFleetState>('/v1/product/robot-fleet',body,controller.signal,false),
      new Promise<never>((_,reject)=>{timer=setTimeout(()=>{controller.abort();reject(new ApiError('fleet_input_expired','Held input delivery expired. Movement paused; release and press again.'));},remaining);})]);
    }finally{if(timer!==undefined)clearTimeout(timer);}
  }
  robotFleetOperation(id:string):Promise<import('./robot-fleet-types').RobotFleetOperation>{
    return this.readState(`/v1/product/robot-fleet/operations/${encodeURIComponent(id)}`);
  }
  robotMotionReview(id:string):Promise<import('./RobotMotionReview').MotionReviewState>{
    return this.readState(`/v1/product/robot-fleet/operations/${encodeURIComponent(id)}/motion-review`);
  }
  robotMotionReviewAction(id:string,body:{action:'start';request_id:string}|{action:'cancel';request_id:string;job_id:string}):Promise<import('./RobotMotionReview').MotionReviewState>{
    return this.boundedProjectAction(`/v1/product/robot-fleet/operations/${encodeURIComponent(id)}/motion-review`,body);
  }
  async robotFleetEvidence(id:string,file:string):Promise<Blob>{
    if(!/^[a-zA-Z0-9_-]{1,100}$/.test(id)||!/^(?:events-[0-9]{5}\.jsonl|receipt\.json|ssh-stderr\.log)$/.test(file))
      throw new ApiError('fleet_evidence_invalid','Select an original runtime evidence filename from this operation.');
    const context=this.contextId,controller=new AbortController();let timer:ReturnType<typeof setTimeout>|undefined;
    try{return await Promise.race([(async()=>{
      const response=await this.imageRequest(`/v1/product/robot-fleet/operations/${encodeURIComponent(id)}/evidence/${encodeURIComponent(file)}`,controller.signal);
      if(!response.ok)await parseResponse<never>(response);
      const bytes=await response.arrayBuffer();
      if(context!==this.contextId||!this.responseMatches(response,context))throw this.contextChanged();
      if(bytes.byteLength>32*1024*1024)throw new ApiError('fleet_evidence_invalid','Runtime evidence exceeds the bounded download size.');
      return new Blob([bytes],{type:response.headers.get('Content-Type')??'application/octet-stream'});
    })(),new Promise<never>((_,reject)=>{timer=setTimeout(()=>{
      controller.abort();reject(new ApiError('fleet_evidence_unavailable','Runtime evidence download exceeded 15 seconds.'));
    },15000);})]);}finally{if(timer!==undefined)clearTimeout(timer);}
  }
  libraryWorkspace():Promise<import('./library-workspace-types').LibraryWorkspaceState>{return this.readState('/v1/product/library-workspace');}
  libraryWorkspaceAction(body:import('./library-workspace-types').LibraryWorkspaceAction):Promise<import('./library-workspace-types').LibraryWorkspaceState>{
    return this.boundedProjectAction('/v1/product/library-workspace',body);
  }
  deviceDiagnosticRetention(days?:number):Promise<{days:number;eligible_count:number;eligible_bytes:number;archived_count:number;recoverable:boolean}> {
    return days===undefined?this.readState('/v1/product/robot/diagnostic-retention'):this.request('/v1/product/robot/diagnostic-retention',{days});
  }
  executionList(options: {query?:string;status?:string;cursor?:string|null;limit?:number} = {}): Promise<import('./ExecutionDiagnostics').ExecutionList> {
    const params=new URLSearchParams();
    if(options.query)params.set('q',options.query);
    if(options.status)params.set('status',options.status);
    if(options.cursor)params.set('cursor',options.cursor);
    if(options.limit!==undefined)params.set('limit',String(options.limit));
    return this.readState(`/v1/product/diagnostics${params.size?'?'+params.toString():''}`);
  }
  executionDiagnostics(id: string): Promise<import('./ExecutionDiagnostics').ExecutionDetail> {
    return this.readState(`/v1/product/diagnostics/${encodeURIComponent(id)}`);
  }
  executionGraph(id: string): Promise<import('./ExecutionDiagnostics').ExecutionGraph> {
    return this.readState(`/v1/product/diagnostics/${encodeURIComponent(id)}/graph`);
  }
  exportExecutionDiagnostics(id: string): Promise<{diagnostics: import('./ExecutionDiagnostics').ExecutionDetail; export_sha256: string}> {
    return this.readState(`/v1/product/diagnostics/${encodeURIComponent(id)}/export`);
  }
  simulationPlan(scene_revision:string,start:number[],goal:number[],yaw_rad:number):Promise<import('./SimulationRunCard').SimulationPlan>{
    return this.request('/v1/product/simulation/plan',{scene_revision,start,goal,yaw_rad});
  }
  async simulationRun(simulation_id:string,revision:string,request_id:string):Promise<Operation>{
    const controller=new AbortController();let timer:ReturnType<typeof setTimeout>|undefined;
    try{return await Promise.race([
      this.request<Operation>('/v1/product/commands',{client_request_id:request_id,command_type:'run',
        expected_applied_revision:revision,simulation_id},controller.signal),
      new Promise<never>((_,reject)=>{timer=setTimeout(()=>{
        reject(new ApiError('delivery_unknown','Run response exceeded 15 seconds. Check its saved result; no automatic retry.'));
        controller.abort();
      },15000);}),
    ]);}finally{if(timer!==undefined)clearTimeout(timer);}
  }
  simulationOutcome(requestId:string):Promise<Operation>{
    return this.readState(`/v1/product/simulation/request/${encodeURIComponent(requestId)}`);
  }
  viewportState():Promise<import('./viewport-types').ViewportState>{return this.readState('/v1/product/viewport');}
  async conversationImage(path:string):Promise<Blob>{
    if(!/^\/v1\/product\/conversation\/image\/[a-zA-Z0-9_-]{1,100}$/.test(path))
      throw new ApiError('conversation_image_invalid','Invalid source image identity.');
    if(this.environmentImageAdmission)await this.waitForEnvironmentImages();
    const context=this.contextId;
    const controller=new AbortController();let timer:ReturnType<typeof setTimeout>|undefined;
    try{return await Promise.race([(async()=>{
      const response=await this.imageRequest(path,controller.signal);
      if(!response.ok)throw new ApiError('conversation_image_unavailable',`Source image HTTP ${response.status}.`);
      if(response.headers.get('Content-Type')!=='image/png')throw new ApiError('conversation_image_invalid','Source image type is invalid.');
      const bytes=await response.arrayBuffer();
      if(context!==this.contextId||!this.responseMatches(response,context))throw this.contextChanged();
      if(!bytes.byteLength||bytes.byteLength>2*1024*1024)throw new ApiError('conversation_image_invalid','Source image size is invalid.');
      return new Blob([bytes],{type:'image/png'});
    })(),new Promise<never>((_,reject)=>{timer=setTimeout(()=>{
      reject(new ApiError('conversation_image_unavailable','Source image delivery exceeded 2 seconds.'));controller.abort();
    },2000);})]);}finally{if(timer!==undefined)clearTimeout(timer);}
  }
  async viewportPreviewImage(sha:string):Promise<Blob>{
    if(!/^[a-f0-9]{64}$/.test(sha))throw new ApiError('viewport_image_invalid','Invalid preview identity.');
    if(this.environmentImageAdmission)await this.waitForEnvironmentImages();
    const controller=new AbortController();let timer:ReturnType<typeof setTimeout>|undefined;
    try{return await Promise.race([(async()=>{
      const response=await this.imageRequest(`/v1/product/viewport/preview/${sha}`,controller.signal);
      if(!response.ok){
        if(response.status===409){
          const problem=await response.json().catch(()=>null);
          if(problem?.error?.code==='viewport_preview_expired')
            throw new ApiError('viewport_preview_expired','Preview replaced; waiting for the next metadata receipt.');
        }
        throw new ApiError('viewport_http_error',`Viewer preview HTTP ${response.status}.`);
      }
      if(response.headers.get('Content-Type')!=='image/jpeg')throw new ApiError('viewport_image_invalid','Viewer returned an invalid preview.');
      const bytes=await response.arrayBuffer();
      if(!this.responseMatches(response,this.contextId))throw this.contextChanged();
      if(!bytes.byteLength||bytes.byteLength>180000)throw new ApiError('viewport_image_invalid','Viewer preview size is invalid.');
      return new Blob([bytes],{type:'image/jpeg'});
    })(),new Promise<never>((_,reject)=>{timer=setTimeout(()=>{
      reject(new ApiError('viewport_http_error','Viewer preview delivery exceeded 2 seconds.'));controller.abort();
    },2000);})]);}finally{if(timer!==undefined)clearTimeout(timer);}
  }
  async viewportObservation(body:{frame_id:number;engine_session_id:string;stage_epoch:string;applied_revision:string;error_code:string;timings?:import('./viewport-types').ViewportTimings}):Promise<{execution_id:string|null;physical_authority:false;disposition?:'recorded'|'discarded';reason?:'scene_superseded'}> {
    const controller=new AbortController();let timer:ReturnType<typeof setTimeout>|undefined;
    try{return await Promise.race([
      this.request<{execution_id:string|null;physical_authority:false;disposition?:'recorded'|'discarded';reason?:'scene_superseded'}>('/v1/product/viewport/observation',body,controller.signal),
      new Promise<never>((_,reject)=>{timer=setTimeout(()=>{
        reject(new ApiError('viewport_observation_unknown','Display diagnostic delivery exceeded 3 seconds. Its saved result may still exist; no automatic retry.'));
        controller.abort();
      },3000);}),
    ]);}finally{if(timer!==undefined)clearTimeout(timer);}
  }
  async viewportImage(frameId:number):Promise<Blob>{
    if(this.environmentImageAdmission)await this.waitForEnvironmentImages();
    const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),2000);
    try{
      const response=await this.imageRequest(`/v1/product/viewport/frame/${frameId}`,controller.signal);
      if(!response.ok)throw new ApiError(response.status===409?'viewport_frame_expired':'viewport_http_error',
        response.status===409?'Frame replaced; waiting for the next current frame.':`Viewer image HTTP ${response.status}.`);
      if(response.headers.get('Content-Type')!=='image/jpeg')throw new ApiError('viewport_image_invalid','Viewer returned an invalid image.');
      // Do not register each streamed frame as a downloaded Blob attached
      // to the browser's network-inspector history. Consume the bytes, then
      // create only the short-lived decode Blob owned by the viewer.
      const bytes=await response.arrayBuffer();
      if(!this.responseMatches(response,this.contextId))throw this.contextChanged();
      return new Blob([bytes],{type:'image/jpeg'});
    }finally{clearTimeout(timer);}
  }
  async viewportImageFrame():Promise<{state:import('./viewport-types').ViewportState;image:Blob|null}>{
    // Explicit adoption queues unsent observation only. The unchanged 2s
    // transfer/decode budget starts after admission; frame clocks stay original.
    if(this.environmentImageAdmission)await this.waitForEnvironmentImages();
    const controller=new AbortController();let timer:ReturnType<typeof setTimeout>|undefined;
    try{return await Promise.race([(async()=>{
      const response=await this.imageRequest('/v1/product/viewport/current',controller.signal);
      if(response.status!==200&&response.status!==204)throw new ApiError('viewport_http_error',`Viewer image HTTP ${response.status}.`);
      const header=response.headers.get('X-TwinPulse-Viewport');
      const invalid=()=>new ApiError('viewport_image_invalid','Viewer image receipt is missing or invalid.');
      if(!header||header.length>8192||response.headers.get('Content-Type')!=='image/jpeg')throw invalid();
      let state:import('./viewport-types').ViewportState;try{state=JSON.parse(header);}catch{throw invalid();}
      if(!state||!['waiting','live','degraded','stale'].includes(state.state)||state.physical_authority!==false||
        !Number.isFinite(state.fps)||state.fps<0||typeof state.camera_pending!=='boolean'||
        (state.camera_result!==null&&(!state.camera_result||!['completed','failed'].includes(state.camera_result.state)||
          ![state.camera_result.request_id,state.camera_result.code].every(value=>typeof value==='string'&&value.length<=80))))throw invalid();
      const frame=state.frame;
      if(response.status===204){
        if(frame!==null||['live','degraded'].includes(state.state))throw invalid();
        // Complete even a bodyless fetch. The installed Electron Chromium
        // otherwise reports an unconsumed 204 stream as ERR_ABORTED. Keep the
        // original 2-second bound and recheck context after the awaited drain.
        const empty=await response.arrayBuffer();
        if(!this.responseMatches(response,this.contextId))throw this.contextChanged();
        if(empty.byteLength!==0)throw invalid();
        return {state,image:null};
      }
      if(!frame||!['live','degraded'].includes(state.state)||!Number.isSafeInteger(frame.frame_id)||frame.frame_id<0||
        !Number.isFinite(frame.captured_at_ms)||!Number.isInteger(frame.width)||!Number.isInteger(frame.height)||
        frame.width<64||frame.width>1280||frame.height<64||frame.height>960||
        !Number.isSafeInteger(frame.camera_sequence)||frame.camera_sequence<0||
        ![frame.engine_session_id,frame.stage_epoch,frame.applied_revision].every(value=>typeof value==='string'&&value.length>0&&value.length<=160)||
        typeof frame.sha256!=='string'||!(/^[a-f0-9]{64}$/).test(frame.sha256)||frame.url!==`/v1/product/viewport/frame/${frame.frame_id}`)throw invalid();
      const bytes=await response.arrayBuffer();
      if(!this.responseMatches(response,this.contextId))throw this.contextChanged();
      if(!bytes.byteLength||bytes.byteLength>180000)throw invalid();
      return {state,image:new Blob([bytes],{type:'image/jpeg'})};
    })(),new Promise<never>((_,reject)=>{timer=setTimeout(()=>{
      reject(new ApiError('viewport_http_error','Viewer image delivery exceeded 2 seconds.'));controller.abort();
    },2000);})]);}finally{if(timer!==undefined)clearTimeout(timer);}
  }
  async viewportCamera(body:{request_id:string;frame_id:number;action:string}):Promise<import('./viewport-types').ViewportState>{
    const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),3000);
    try{return await this.request('/v1/product/viewport/camera',body,controller.signal);}
    finally{clearTimeout(timer);}
  }
  conversation(): Promise<import('./conversation-types').ConversationState> {
    return this.readState('/v1/product/conversation');
  }
  async conversationAction(body: import('./conversation-types').ConversationAction | import('./conversation-types').ResumeSceneAction | import('./conversation-types').RobotCheckAction): Promise<import('./conversation-types').ConversationState> {
    if(body.action==='resume')return this.environmentTransaction(()=>this.sendConversationAction(body));
    return this.sendConversationAction(body);
  }
  private async sendConversationAction(body:Parameters<TwinPulseApi['conversationAction']>[0]):Promise<import('./conversation-types').ConversationState>{
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      return await Promise.race([
        this.request<import('./conversation-types').ConversationState>('/v1/product/conversation', body, controller.signal),
        new Promise<never>((_, reject) => { timer = setTimeout(() => {
          reject(new ApiError('delivery_unknown', 'Chat action response exceeded 15 seconds. Query its saved result; do not repeat it.'));
          controller.abort();
        }, 15000); }),
      ]);
    } finally { if (timer !== undefined) clearTimeout(timer); }
  }
  private async boundedProjectAction<T>(path: string, body: object): Promise<T> {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    try { return await Promise.race([this.request<T>(path, body, controller.signal), new Promise<never>((_, reject) => {
      timer = setTimeout(() => { reject(new ApiError('delivery_unknown', 'Project response exceeded 15 seconds. Check the saved outcome; no automatic retry.')); controller.abort(); }, 15000);
    })]); } finally { if (timer !== undefined) clearTimeout(timer); }
  }
  automaticComparisonState():Promise<import('./AutomaticComparison').ComparisonState>{return this.request('/v1/product/automatic-demo/comparison');}
  automaticComparisonStart(start:number[],goal:number[]):Promise<import('./AutomaticComparison').ComparisonState>{
    return this.request('/v1/product/automatic-demo/comparison-start',{start,goal});}
  automaticComparisonStop(job_id:string):Promise<import('./AutomaticComparison').ComparisonState>{
    return this.request('/v1/product/automatic-demo/comparison-stop',{job_id});}
  automaticState():Promise<import('./AutomaticDemo').AutomaticState>{return this.request('/v1/product/automatic-demo');}
  automaticMissionState():Promise<import('./AutomaticMission').MissionState>{return this.request('/v1/product/automatic-demo/mission');}
  automaticMissionPreview(job_id:string,revision:string,request_id:string):Promise<Operation>{
    return this.request('/v1/product/automatic-demo/mission-preview3d',{job_id,revision,request_id});}
  automaticMissionReadiness(map_id:string|null):Promise<{room_revision:string;photo_status:string;adapter_available:boolean;current_pose_available:boolean;photo_correction_available?:boolean;next_action:string}>{
    return this.request('/v1/product/automatic-demo/mission-readiness',{map_id});}
  automaticMissionStart(map_id:string|null,goal:{mode:string;xy:number[];room_revision:string;duration_s:number},photo_policy?:'correct_walls'):Promise<import('./AutomaticMission').MissionState>{
    return this.request('/v1/product/automatic-demo/mission-start',{map_id,goal,...(photo_policy?{photo_policy}:{})});}
  automaticMissionStop(job_id:string,force:boolean):Promise<import('./AutomaticMission').MissionState>{
    return this.request('/v1/product/automatic-demo/mission-stop',{job_id,force});}
  automaticMaps():Promise<{maps:import('./AutomaticDemo').SavedMap[]}>{return this.readState('/v1/product/automatic-demo/maps');}
  sceneSensorContext():Promise<import('./conversation-types').SceneSensorContext>{return this.readState('/v1/product/scene-edit/sensor-context');}
  sceneSensorSurveys():Promise<{surveys:import('./conversation-types').SceneSensorSurvey[];physical_authority:false}>{return this.readState('/v1/product/scene-edit/sensor-surveys');}
  obstacleFeedbackState():Promise<import('./obstacle-types').ObstacleFeedbackState>{return this.readState('/v1/product/scene-edit/obstacle-feedback');}
  importObstacleObservation(observation:Record<string,unknown>,expected_scene_revision:string,expected_state_sha256:string,sensor_pose_m:number[],scan_height_m:number):Promise<import('./obstacle-types').ObstacleFeedbackState>{
    return this.boundedProjectAction('/v1/product/scene-edit/obstacle-feedback',{action:'import',observation,expected_scene_revision,expected_state_sha256,sensor_pose_m,scan_height_m});}
  previewObstacleCorrection(observation_id:string,observation_sha256:string,expected_scene_revision:string,expected_state_sha256:string,target_id:string,translation_xy_m:number[]|null):Promise<import('./obstacle-types').ObstacleCorrectionPreview>{
    return this.boundedProjectAction('/v1/product/scene-edit/obstacle-feedback',{action:'preview',observation_id,observation_sha256,expected_scene_revision,expected_state_sha256,target_id,translation_xy_m});}
  applyObstacleCorrection(preview:import('./obstacle-types').ObstacleCorrectionPreview):Promise<import('./types').SceneEditTransaction>{
    return this.boundedProjectAction('/v1/product/scene-edit/apply',{schema_version:'scene-edit-apply-2.0',obstacle_preview_id:preview.execution_id,preview_digest:preview.preview_digest});}
  startSceneEditTransaction(preview:SceneEditPreview):Promise<import('./types').SceneEditTransaction>{
    return this.boundedProjectAction('/v1/product/scene-edit/apply',{schema_version:'scene-edit-apply-2.0',operation:preview.operation,preview_digest:preview.preview_digest});}
  robotObservation(job_id:string):Promise<Record<string,unknown>>{return this.readState('/v1/product/robot/observations/'+encodeURIComponent(job_id));}
  robotObservationExport(job_id:string):Promise<{schema_version:'robot-observation-export-1.0';job_id:string;export_sha256:string;file_sha256:string;json_text:string}>{
    return this.readState('/v1/product/robot/observations/'+encodeURIComponent(job_id)+'/export');
  }
  automaticStart(job_id:string,reference_map_id:string|null,photo_policy:import('./AutomaticDemo').PhotoPolicy='disabled',replay_mode?:'recorded_1x'):Promise<import('./AutomaticDemo').AutomaticState>{
    return this.request('/v1/product/automatic-demo/start',{job_id,reference_map_id,photo_policy,...(replay_mode?{replay_mode}:{})});
  }
  automaticControl(job_id:string,action:string,sequence:number|null=null):Promise<import('./AutomaticDemo').AutomaticState>{
    return this.request('/v1/product/automatic-demo/control',{job_id,action,sequence});
  }
  automaticRollbackPhoto(job_id:string,revision:string):Promise<import('./AutomaticDemo').AutomaticState>{
    return this.request('/v1/product/automatic-demo/rollback-photo',{job_id,revision});
  }
  automaticReopen(map_id:string):Promise<{map:import('./AutomaticDemo').MapData;photo_alignment?:import('./AutomaticDemo').PhotoAlignment|null}>{
    return this.request('/v1/product/automatic-demo/reopen',{map_id});
  }
  private async photoLinkRequest<T>(path:string,body:object):Promise<T>{
    const controller=new AbortController();let timer:ReturnType<typeof setTimeout>|undefined;
    try{return await Promise.race([this.request<T>(`/v1/product/room-localization/${path}`,body,controller.signal),
      new Promise<never>((_,reject)=>{timer=setTimeout(()=>{reject(new ApiError('photo_link_timeout',
        'Coordinate link request timed out. No robot action or room edit was sent; no automatic retry.'));controller.abort();},45_000);})]);
    }finally{if(timer!==undefined)clearTimeout(timer);}
  }
  photoLinkContext(revision:string,sensor_revision:string):Promise<import('./SensorPhotoLink').PhotoLinkContext>{
    return this.photoLinkRequest('photo-link-context',{revision,sensor_revision});
  }
  linkSensorPhoto(revision:string,sensor_revision:string,context_revision:string,pairs:import('./SensorPhotoLink').LinkPair[]):Promise<import('./SensorPhotoLink').PhotoLinkResult>{
    return this.photoLinkRequest('photo-link',{revision,sensor_revision,context_revision,pairs});
  }
  photoLinkGoal(revision:string,link_revision:string,goal:number[]):Promise<{query_odom_goal_candidate_m:number[]}>{
    return this.photoLinkRequest('photo-link-goal',{revision,link_revision,goal});
  }
  async locateSensorMap(job_id:string,observation_revision:string,query_job_id:string,frame:number):Promise<import('./SensorMapLocalization').SensorMapResult> {
    const controller=new AbortController();let timer:ReturnType<typeof setTimeout>|undefined;
    try{return await Promise.race([
      this.request<import('./SensorMapLocalization').SensorMapResult>('/v1/product/room-localization/sensor-map',{job_id,observation_revision,query_job_id,frame},controller.signal),
      new Promise<never>((_,reject)=>{timer=setTimeout(()=>{
        reject(new ApiError('sensor_map_timeout','Sensor-map search timed out. No robot action or room change was sent. The diagnostic may still finish; no automatic retry.'));controller.abort();
      },45_000);}),
    ]);}finally{if(timer!==undefined)clearTimeout(timer);}
  }
  async compareObservationModel(job_id:string,revision:string,observation_revision:string):Promise<import('./ModelComparison').ModelComparisonResult> {
    const controller=new AbortController();let timer:ReturnType<typeof setTimeout>|undefined;
    try{return await Promise.race([
      this.request<import('./ModelComparison').ModelComparisonResult>('/v1/product/room-localization/compare-model',{job_id,revision,observation_revision},controller.signal),
      new Promise<never>((_,reject)=>{timer=setTimeout(()=>{
        reject(new ApiError('model_comparison_timeout','Model comparison timed out. The diagnostic may still finish; no geometry changed and no automatic retry.'));controller.abort();
      },45_000);}),
    ]);}finally{if(timer!==undefined)clearTimeout(timer);}
  }
  async sessionObservationMap(job_id:string):Promise<import('./ObservationMap').ObservationMapResult> {
    const controller=new AbortController();let timer:ReturnType<typeof setTimeout>|undefined;
    try{return await Promise.race([
      this.request<import('./ObservationMap').ObservationMapResult>('/v1/product/room-localization/observation-map',{job_id},controller.signal),
      new Promise<never>((_,reject)=>{timer=setTimeout(()=>{
        reject(new ApiError('observation_map_timeout','Observation map request timed out. No robot action was sent. The saved diagnostic may still finish; no automatic retry.'));
        controller.abort();
      },45_000);}),
    ]);}finally{if(timer!==undefined)clearTimeout(timer);}
  }
  roomLocalization(job_id:string,frame:number,revision:string):Promise<import('./RoomLocalization').LocalizationResult> {
    return this.request('/v1/product/room-localization/review',{job_id,frame,revision});
  }
  invalidateRoomLocalization():Promise<unknown> {return this.request('/v1/product/room-localization/invalidate',{});}
  previewLocalizedRoom(revision:string,result_revision:string,request_id:string):Promise<import('./engine-contracts').Operation> {
    return this.request('/v1/product/room-localization/preview3d',{revision,result_revision,request_id});
  }
  localizedRoomGoal(revision:string,result_revision:string,epoch:number,goal:number[]):Promise<{odom_goal_candidate_m:number[];scope:string;mission_request:null}> {
    return this.request('/v1/product/room-localization/goal',{revision,result_revision,epoch,goal});
  }
  geometryEvidence():Promise<import('./BedroomGoalReview').GeometryEvidence> {
    return this.request('/v1/product/bedroom/geometry-evidence',{});
  }
  bedroomGoal(revision:string,evidence_revision:string,goal:number[],reference:unknown):Promise<import('./BedroomGoalReview').GoalPreview> {
    return this.request('/v1/product/bedroom/goal-preview',{revision,evidence_revision,goal,reference});
  }
  prepareBedroom(): Promise<import("./BedroomTwin").BedroomReviewState> {
    return this.request("/v1/product/bedroom/prepare", {});
  }
  rehearseBedroom(revision:string,scenario:string):Promise<import("./BedroomTwin").BedroomMissionResult> {
    return this.request('/v1/product/bedroom/rehearse',{revision,scenario,acknowledged:true});
  }
  offlineBedroomAcceptance(revision:string):Promise<import('./BedroomTwin').BedroomOfflineAcceptance> {
    return this.request('/v1/product/bedroom/offline-acceptance',{revision,acknowledged:true});
  }
  exportBedroomOfflineAcceptance(revision:string,acceptance_revision:string):Promise<{acceptance_revision:string;json_text:string;sha256:string}> {
    return this.request('/v1/product/bedroom/offline-acceptance-export',{revision,acknowledged:true,acceptance_revision});
  }
  importBedroomOfflineAcceptance(revision:string,bundle_text:string):Promise<import('./BedroomTwin').BedroomOfflineAcceptance> {
    return this.request('/v1/product/bedroom/offline-acceptance-import',{revision,acknowledged:true,bundle_text});
  }
  exportBedroomRehearsal(revision:string,scenario:string,record_revision:string):Promise<{record_revision:string;json_text:string;sha256:string}> {
    return this.request('/v1/product/bedroom/rehearse-export',{revision,scenario,acknowledged:true,record_revision});
  }
  buildBedroom(revision: string, acknowledged: boolean, request_id: string): Promise<import("./engine-contracts").Operation> {
    return this.request("/v1/product/bedroom/build", { revision, acknowledged, request_id });
  }
  replayBedroom(revision:string, replay:{scenario:string;revision:string;frame:number}, request_id:string):Promise<import('./engine-contracts').Operation> {
    return this.request('/v1/product/bedroom/replay',{revision,replay,acknowledged:true,request_id});
  }
  compareBedroom(revision:string):Promise<import('./BedroomTwin').BedroomComparison> {
    return this.request('/v1/product/bedroom/compare',{revision,acknowledged:true});
  }
  exportBedroomComparison(revision:string,comparison_revision:string):Promise<{comparison_revision:string;json_text:string;sha256:string}> {
    return this.request('/v1/product/bedroom/compare-export',{revision,acknowledged:true,comparison_revision});
  }
  private csrf = sessionStorage.getItem(CSRF_KEY) ?? "";
  private contextId = '';
  private contextRecovery:Promise<ProductContext>|null=null;
  get context(): string { return this.contextId; }
  private bootstrapPending: Promise<void> | null = null;
  private readonly stateReads = new Map<string, Promise<unknown>>();
  private readonly imageReads = new Set<Promise<Response>>();
  private readonly leaseActions = new Set<Promise<unknown>>();
  private projectReadBarrier: Promise<void> | null = null;

  // Only idempotent status reads. Never time out/retry a mutation implicitly.
  private readState<T>(path: string): Promise<T> {
    // A switch first drains old-context reads. New polls (including App runtime
    // observation) wait here and start only after its outcome is resolved.
    if(this.projectReadBarrier)return this.projectReadBarrier.then(()=>this.readState<T>(path));
    const key = `${this.contextId}:${path}`;
    const existing = this.stateReads.get(key);
    if (existing) return existing as Promise<T>;
    const controller = new AbortController();
    // A cold paged catalog reads bounded labels for multiple projects, not the
    // currently selected state. Its own deadline does not relax frame/status
    // freshness or any mutation/receipt guard.
    // Explicit historical operation export can contain MB of immutable scans.
    // It is not a heartbeat/status sample; retain the 3s freshness deadline for
    // live fleet/viewport reads and never retry a command on this account.
    const operationRecord = /^\/v1\/product\/robot-fleet\/operations\/[A-Za-z0-9_-]+$/.test(path);
    const readTimeoutMs = operationRecord ? 20000 : path === '/v1/product/projects' ? 6000 : 3000;
    let timer: ReturnType<typeof setTimeout>;
    const deadline = new Promise<never>((_, reject) => {
      timer = setTimeout(() => {
        reject(new ApiError(operationRecord ? 'operation_record_timeout' : 'state_read_timeout', `Local ${operationRecord ? 'operation record' : path === '/v1/product/projects' ? 'project list' : 'state'} read exceeded ${readTimeoutMs / 1000} seconds.`));
        controller.abort();
      }, readTimeoutMs);
    });
    const pending = Promise.race([this.request<T>(path, undefined, controller.signal), deadline])
      .finally(() => {
        clearTimeout(timer);
        if (this.stateReads.get(key) === pending) this.stateReads.delete(key);
      });
    this.stateReads.set(key, pending);
    return pending;
  }

  private saveCsrf(value: string): void {
    this.csrf = value;
    sessionStorage.setItem(CSRF_KEY, value);
  }

  private clearCsrf(): void {
    this.csrf = "";
    sessionStorage.removeItem(CSRF_KEY);
  }

  private reopenRequired(): ApiError {
    return new ApiError(
      "session_reopen_required",
      "Your session expired. Reopen TwinPulse from the launcher's secure link.",
    );
  }

  async bootstrap(): Promise<void> {
    if (!this.bootstrapPending) {
      this.bootstrapPending = this.bootstrapOnce().finally(() => { this.bootstrapPending = null; });
    }
    return this.bootstrapPending;
  }

  private async bootstrapOnce(): Promise<void> {
    const fragment = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    const secret = fragment.get("bootstrap");
    if (!secret) {
      try {
        const recovered = await parseResponse<{ csrf_token: string; context_id?: string }>(await fetch(
          "/v1/product/session",
          { method: "GET", credentials: "same-origin" },
        ));
        this.saveCsrf(recovered.csrf_token);
        this.contextId = recovered.context_id ?? '';
        return;
      } catch (error) {
        this.clearCsrf();
        if (error instanceof ApiError && error.code === "session_rejected") {
          throw this.reopenRequired();
        }
        throw error;
      }
    }
    // Keep only the non-secret console mode so refresh stays in this view.
    // The one-use bootstrap secret must disappear before the request awaits.
    const modeFragment = fragment.get("robot-console") === "1" ? "#robot-console=1" : "";
    history.replaceState(null, "", `${window.location.pathname}${window.location.search}${modeFragment}`);
    try {
      const result = await parseResponse<{ csrf_token: string; context_id?: string }>(await fetch("/v1/bootstrap", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role: "product", secret }),
      }));
      this.saveCsrf(result.csrf_token);
      this.contextId = result.context_id ?? '';
    } catch (error) {
      this.clearCsrf();
      throw error;
    }
  }

  private contextChanged(): ApiError {
    return new ApiError('context_changed', 'The selected chat changed. Refreshing its current state.');
  }

  private responseMatches(response: Response, context: string): boolean {
    const received = response.headers?.get('X-TwinPulse-Context');
    return context === this.contextId && (!context || received === context);
  }

  private validContext(value:unknown):value is string {
    return typeof value==='string'&&/^[a-zA-Z0-9_-]{1,128}$/.test(value);
  }

  // Recovery observes the authenticated session; it never repeats a switch or
  // another mutation. Only a body/header pair from this endpoint can adopt a
  // context after a lost switch acknowledgement.
  async projectContext():Promise<ProductContext> {
    if(this.contextRecovery)return this.contextRecovery;
    const context=this.contextId;
    const controller=new AbortController();let timer:ReturnType<typeof setTimeout>|undefined;
    const observed=Promise.race([(async()=>{
      const response=await fetch('/v1/product/session',{method:'GET',credentials:'same-origin',signal:controller.signal,cache:'no-store'});
      const value=await parseResponse<ProductContext>(response);
      if(!this.validContext(value.context_id)||response.headers?.get('X-TwinPulse-Context')!==value.context_id||typeof value.project_id!=='string')throw this.contextChanged();
      if(context!==this.contextId)throw this.contextChanged();
      this.contextId=value.context_id;this.saveCsrf(value.csrf_token);this.stateReads.clear();return value;
    })(),new Promise<never>((_,reject)=>{timer=setTimeout(()=>{controller.abort();reject(new ApiError('state_read_timeout','Selected chat observation exceeded 3 seconds.'));},3000);})])
      .finally(()=>{if(timer!==undefined)clearTimeout(timer);if(this.contextRecovery===observed)this.contextRecovery=null;});
    this.contextRecovery=observed;return observed;
  }

  private async pendingProject(project:string):Promise<ProjectSwitchResult> {
    const deadline=Date.now()+15000;
    while(Date.now()<deadline){
      const observed=await this.projectContext();
      if(observed.project_id===project&&(!observed.project_switch||observed.project_switch.pending===false))
        return {status:'switched',project_id:project,context_id:observed.context_id,new_session_required:false};
      await new Promise(resolve=>setTimeout(resolve,500));
    }
    throw new ApiError('delivery_unknown','Project switch acknowledgement is pending. Check its saved outcome; the switch was not repeated.');
  }

  private imageRequest(path: string, signal: AbortSignal, retry = true): Promise<Response> {
    if(retry&&this.projectReadBarrier)return this.projectReadBarrier.then(()=>this.imageRequest(path,signal,retry));
    if(signal.aborted)return Promise.reject(signal.reason??new DOMException('Image read aborted','AbortError'));
    const context = this.contextId;
    let abort!:()=>void;
    const cancelled=new Promise<never>((_,reject)=>{abort=()=>reject(signal.reason??new DOMException('Image read aborted','AbortError'));signal.addEventListener('abort',abort,{once:true});});
    const pending=(async()=>{
      const response = await Promise.race([fetch(path, {credentials:'same-origin',signal,cache:'no-store',
        headers:context?{'X-TwinPulse-Context':context}:undefined}),cancelled]);
      if (!this.responseMatches(response, context)) {
        if (retry && !signal.aborted) return this.imageRequest(path,signal,false);
        throw this.contextChanged();
      }
      return response;
    })().finally(()=>{signal.removeEventListener('abort',abort);this.imageReads.delete(pending);});
    this.imageReads.add(pending);return pending;
  }

  private async request<T>(path: string, body?: object, signal?: AbortSignal, retry = true): Promise<T> {
    const context = this.contextId;
    const switching = path === '/v1/product/projects/switch';
    const response = await fetch(path, {
      method: body === undefined ? "GET" : "POST",
      credentials: "same-origin",
      headers: {
        ...(body === undefined ? {'X-TwinPulse-Read-ID':crypto.randomUUID()} : {}),
        ...(context ? {'X-TwinPulse-Context': context} : {}),
        ...(body === undefined ? {} : {
        "Content-Type": "application/json",
        "X-TwinPulse-CSRF": this.csrf,
        }),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
    try {
      const received=response.headers?.get('X-TwinPulse-Context');
      if(response.status===409&&context===this.contextId&&this.validContext(received)&&received!==context){
        const problem=await response.json() as {error?:{code?:string}};
        if(problem.error?.code==='project_context_changed'||problem.error?.code==='context_changed'){
          await this.projectContext();
          if(body===undefined&&retry&&!signal?.aborted)return this.request<T>(path,undefined,signal,false);
        }
        throw this.contextChanged();
      }
      if (!switching && !this.responseMatches(response,context)) {
        if (body === undefined && retry && !signal?.aborted) return this.request<T>(path,undefined,signal,false);
        throw this.contextChanged();
      }
      const value = await parseResponse<T>(response);
      if (switching && context === this.contextId) {
        const selected = value as ProjectSwitchResult;
        if (selected.status === 'switched' && selected.context_id) {
          if (response.headers?.get('X-TwinPulse-Context') !== selected.context_id) throw this.contextChanged();
          this.contextId = selected.context_id;
          this.stateReads.clear();
          return value;
        }
      }
      if (!this.responseMatches(response, context)) {
        if (body === undefined && retry && !signal?.aborted) return this.request<T>(path, undefined, signal, false);
        throw this.contextChanged();
      }
      return value;
    } catch (error) {
      // Old responses, including an old 401, must not invalidate the selected session.
      if (context !== this.contextId) {
        if (body === undefined && retry && !signal?.aborted) return this.request<T>(path, undefined, signal, false);
        throw this.contextChanged();
      }
      if (response.status === 401) {
        this.clearCsrf();
        throw this.reopenRequired();
      }
      if (response.status === 403 && error instanceof ApiError && error.code === 'csrf_rejected'
          && body !== undefined && retry && !signal?.aborted) {
        // Another legitimate App window may have exchanged its ticket at the
        // same time and updated the shared HttpOnly cookie. This exact server
        // rejection occurs before action dispatch, so it is safe to refresh
        // authentication and retry ONCE, only in the unchanged project.
        // Unknown outcomes, other 403s and stale project writes never retry.
        await this.projectContext();
        if (context !== this.contextId) throw this.contextChanged();
        return this.request<T>(path, body, signal, false);
      }
      throw error;
    }
  }

  workflow(): Promise<WorkflowState> { return this.readState("/v1/product/workflow"); }
  modelLibrary(): Promise<{library_version:string;models:import('./model-library-types').LibraryModel[];physical_authority:false}> {
    return this.readState('/v1/product/model-library');
  }
  projects(): Promise<ProjectCatalogState> { return this.readState("/v1/product/projects"); }
  async switchProject(project_id: string): Promise<ProjectSwitchResult> {
    if(this.projectReadBarrier)throw new ApiError('project_switch_busy','A project switch is already being observed.');
    let release!:()=>void;
    const barrier=new Promise<void>(resolve=>{release=resolve;});
    this.projectReadBarrier=barrier;
    try {
      await Promise.allSettled([...this.stateReads.values(),...this.imageReads,...this.leaseActions]);
      try {
        const result=await this.boundedProjectAction<ProjectSwitchResult>("/v1/product/projects/switch", { project_id });
        return result.status==='requested'&&result.new_session_required===false?await this.pendingProject(project_id):result;
      } catch(error){
        if(error instanceof ApiError&&!['delivery_unknown','context_changed'].includes(error.code))throw error;
        // The command may already have reached Isaac. Observe, never resubmit.
        return await this.pendingProject(project_id);
      }
    } finally {this.projectReadBarrier=null;release();}
  }
  retryLauncher(): Promise<{ status: "requested"; new_session_required: true }> {
    return this.request("/v1/product/runtime/retry", {});
  }
  cancelStartup(): Promise<{ status: "requested"; new_session_required: true }> {
    return this.request("/v1/product/runtime/cancel", {});
  }
  shutdownRuntime(): Promise<{ status: "requested"; new_session_required: true }> {
    return this.request("/v1/product/runtime/shutdown", {});
  }
  createProject(project_id: string): Promise<{ created_project_id: string; catalog: ProjectCatalogState }> {
    return this.boundedProjectAction("/v1/product/projects/create", { project_id });
  }
  createManualRoomProject(value: {
    project_id: string; request_id: string; prompt: string; media_type: string;
    photo_base64: string; width_m: number; length_m: number; wall_height_m: number;
    include_burger_visual: boolean;
    furniture?: { kind: string; center_m: [number, number]; yaw_deg: number }[];
  }): Promise<{ created_project_id: string; catalog: ProjectCatalogState;
    photo_interpreted: false; burger_visual_included: boolean; physical_authority: false }> {
    return this.request("/v1/product/projects/create-manual-room", value);
  }
  createBedroomProject(project_id: string, request_id?: string): Promise<{ created_project_id: string; catalog: ProjectCatalogState;
    source: "preserved_bedroom_photo"; build_allowed: false; physical_authority: false }> {
    return this.request("/v1/product/projects/create-bedroom", request_id ? { project_id, request_id } : { project_id });
  }
  recoverBedroomProject(project_id: string, request_id: string, recovery_fingerprint: string):
    Promise<{ created_project_id: string; catalog: ProjectCatalogState }> {
    return this.request("/v1/product/projects/recover-bedroom",
      { project_id, request_id, recovery_fingerprint });
  }
  continueRoomRecipe(): Promise<WorkflowState> { return this.request("/v1/product/project/continue-room", {}); }
  resumeSavedScene(project_id: string, expected_scene_revision: string,
                   expected_input_revision: string): Promise<WorkflowState> {
    return this.environmentTransaction(()=>this.boundedProjectAction("/v1/product/project/resume-scene",
      { project_id, expected_scene_revision, expected_input_revision }));
  }
  previewSceneEdit(operation_id: string, mode: "add" | "add_many" | "change" | "undo",
                   target_call_id: string | null, tool_call: Record<string, unknown> | null): Promise<SceneEditPreview> {
    return this.request("/v1/product/scene-edit/preview", { operation_id, mode, target_call_id, tool_call });
  }
  sceneEditContext(request_text: string, selected_call_id: string | null): Promise<SceneEditContext> {
    return this.request("/v1/product/scene-edit/context", { request_text, selected_call_id });
  }
  previewSceneEditProposal(operation_id: string, request_text: string, selected_call_id: string | null,
                           expected_revision: string, proposal: SceneEditProposal): Promise<SceneEditProposalResult> {
    return this.request("/v1/product/scene-edit/proposal-preview",
      { operation_id, request_text, selected_call_id, expected_revision, proposal });
  }
  applySceneEdit(operation: Record<string, unknown>, preview_digest: string): Promise<WorkflowState> {
    return this.request("/v1/product/scene-edit/apply", { operation, preview_digest });
  }
  applyEnvironmentEdit(operation:Record<string,unknown>,preview_digest:string):Promise<import('./types').SceneEditTransaction>{
    return this.environmentTransaction(()=>this.boundedProjectAction('/v1/product/scene-edit/apply',{
      schema_version:'scene-edit-apply-2.0',environment_preview_id:operation.operation_id,preview_digest,
    }));
  }
  applyLibraryPlacement(preview_id:string,preview_digest:string):Promise<import('./types').SceneEditTransaction>{
    return this.boundedProjectAction('/v1/product/scene-edit/apply',{
      schema_version:'scene-edit-apply-2.0',library_placement_id:preview_id,preview_digest,
    });
  }
  sceneEditTransaction():Promise<import('./types').SceneEditTransaction|null>{
    return this.request('/v1/product/scene-edit/transaction');
  }
  recoverSceneEdit():Promise<import('./types').SceneEditTransaction>{
    return this.request('/v1/product/scene-edit/apply',{schema_version:'scene-edit-apply-2.0',action:'recover'});
  }
  reattachSavedSource(project_id: string, expected_scene_revision: string,
                      expected_input_revision: string, name: string | null,
                      media_type: string | null, content_base64: string | null): Promise<WorkflowState> {
    return this.request("/v1/product/project/reattach-source",
      { project_id, expected_scene_revision, expected_input_revision, name, media_type, content_base64 });
  }
  adoptDerivedReview(input_revision: string, source_revision: string, workspace_revision: string): Promise<WorkflowState> {
    return this.request("/v1/product/derived-review/adopt", { input_revision, source_revision, workspace_revision });
  }
  restoreDerivedReview(input_revision: string, source_revision: string): Promise<WorkflowState> {
    return this.request("/v1/product/derived-review/restore", { input_revision, source_revision });
  }
  robotReport(): Promise<RobotReportState> { return this.request("/v1/product/robot/report"); }
  robotDiagnostics(): Promise<RobotDiagnosticsState> { return this.readState("/v1/product/robot/diagnostics"); }
  robotReadiness(): Promise<RobotReadinessState> { return this.readState('/v1/product/robot/readiness'); }
  startRobotReadiness(request_id:string):Promise<RobotReadinessState>{
    return this.request('/v1/product/robot/readiness/start',{
      request_id,confirmed_no_motion_deployment:true,expires_at_ms:Date.now()+1500});
  }
  clearUncertainRobotReadiness():Promise<RobotReadinessState>{
    return this.request('/v1/product/robot/readiness/clear-uncertain',{
      confirmed_powered_off:true,expires_at_ms:Date.now()+1500});
  }
  controllerState(): Promise<ManualControllerState> { return this.readState('/v1/product/robot/controller'); }
  physicalState(): Promise<PhysicalState> { return this.readState('/v1/product/robot/physical'); }
  physicalResumeEvidence(job_id:string,request_id:string):Promise<{status:string;job_id:string|null;
    transfer_only:true;receipt?:string|null;reason?:string|null}>{
    return this.request('/v1/product/robot/physical/evidence/resume',{job_id,request_id});
  }
  physicalReviewEvidence(job_id:string):Promise<import('./SessionHistory').SavedEvidenceReview>{
    return this.readState('/v1/product/robot/physical/evidence/review/'+encodeURIComponent(job_id));
  }
  physicalSessions(): Promise<SessionList> { return this.readState('/v1/product/sessions'); }
  physicalSession(job:string): Promise<SessionReview> { return this.readState('/v1/product/sessions/'+encodeURIComponent(job)); }
  private async physicalRequest(body:object,suffix:string,timeoutMs=1500): Promise<PhysicalState> {
    const controller=new AbortController();let timer:ReturnType<typeof setTimeout>|undefined;
    try {return await Promise.race([this.request<PhysicalState>('/v1/product/robot/physical/'+suffix,body,controller.signal,suffix!=='input'),
      new Promise<never>((_,reject)=>{timer=setTimeout(()=>{controller.abort();reject(new ApiError('physical_delivery_unknown','Physical input delivery is unverified. No automatic replay.'));},timeoutMs);})]);}
    finally {if(timer!==undefined)clearTimeout(timer);}
  }
  async chatRobotStop(force:boolean):Promise<{state:string;stop_confirmed?:boolean}>{
    const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),1500);
    try{return await this.request('/v1/product/conversation/robot/stop',{force},controller.signal);}
    finally{clearTimeout(timer);}
  }
  async chatTaskPresence():Promise<{owned:boolean;active:boolean}>{
    const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),700);
    try{return await this.request('/v1/product/conversation/robot/task-presence',undefined,controller.signal);}
    finally{clearTimeout(timer);}
  }
  async chatInspectionDisplay(descriptor:import('./conversation-types').InspectionDisplay['descriptor'],request_id:string):Promise<Operation>{
    const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),15000);
    try{return await this.request('/v1/product/conversation/inspection/display',{descriptor,request_id},controller.signal);}
    finally{clearTimeout(timer);}
  }
  physicalStart(mode:string,request_id:string):Promise<PhysicalState>{
    return this.physicalRequest({mode,request_id,confirmed:true,expires_at_ms:Date.now()+1500},'start');
  }
  physicalMission(scope:{frame_id:'odom';waypoints:number[][];duration_s:number},request_id:string):Promise<PhysicalState>{
    return this.physicalRequest({scope,request_id,confirmed:true,expires_at_ms:Date.now()+1500},'mission');
  }
  physicalInput(job_id:string,sequence:number,action:string):Promise<PhysicalState>{
    return this.physicalRequest({job_id,sequence,action,expires_at_ms:Date.now()+CONTROL_INPUT_TTL_MS},'input',
      ['forward','backward','left','right','watch'].includes(action)?CONTROL_INPUT_TTL_MS:1500);
  }
  private async controllerRequest(body: object, suffix: string): Promise<ManualControllerState> {
    const abort = new AbortController();
    const timeout = setTimeout(() => abort.abort(), 1000);
    try { return await this.request('/v1/product/robot/controller/' + suffix, body, abort.signal); }
    finally { clearTimeout(timeout); }
  }
  beginController(): Promise<ManualControllerState> {
    return this.controllerRequest({ mode: 'rehearsal', confirmed: true }, 'session');
  }
  controllerInput(session_id: string, sequence: number, action: string): Promise<ManualControllerState> {
    return this.controllerRequest({ session_id, sequence, action, expires_at_ms: Date.now() + CONTROL_INPUT_TTL_MS }, 'input');
  }
  robotPreflight(): Promise<RobotDiagnosticsState> { return this.request("/v1/product/robot/preflight", {}); }
  startRobotCheck(start_token: string): Promise<RobotDiagnosticsState> {
    return this.request("/v1/product/robot/check", { start_token, confirmed_read_only: true });
  }
  scanReview(): Promise<ScanReviewState> { return this.request("/v1/product/scan-review"); }
  nativeScan(): Promise<NativeScanState> { return this.request("/v1/product/native-scan"); }
  importNativeScan(bundle_text: string): Promise<NativeScanState> { return this.request("/v1/product/native-scan/import", { bundle_text }); }
  nativeScanFrame(workspace_revision: string, frame_index: number): Promise<NativeScanState> { return this.request("/v1/product/native-scan/frame", { workspace_revision, frame_index }); }
  exportNativeScan(): Promise<unknown> { return this.request("/v1/product/native-scan/export"); }
  exportNative3D(workspace_revision: string, frame_index: number): Promise<{ filename: string; usda: string; sha256: string }> {
    return this.request("/v1/product/native-scan/3d-export", { workspace_revision, frame_index });
  }
  proposeNativeRegistration(workspace_revision: string, frame_index: number, reference_text: string): Promise<NativeScanState> {
    return this.request("/v1/product/native-scan/registration", { workspace_revision, frame_index, reference_text });
  }
  importScanBundle(bundle_text: string): Promise<ScanReviewState> { return this.request("/v1/product/scan-review/import", { bundle_text }); }
  proposeScanCorrection(workspace_revision: string, object_id: string, pairs: unknown): Promise<ScanReviewState> {
    return this.request("/v1/product/scan-review/propose", { workspace_revision, object_id, pairs });
  }
  applyScanCorrection(workspace_revision: string, proposal_revision: string): Promise<ScanReviewState> {
    return this.request("/v1/product/scan-review/apply", { workspace_revision, proposal_revision });
  }
  undoScanCorrection(workspace_revision: string, edit_revision: string): Promise<ScanReviewState> {
    return this.request("/v1/product/scan-review/undo", { workspace_revision, edit_revision });
  }
  exportScanReview(): Promise<Record<string, unknown>> { return this.request("/v1/product/scan-review/export"); }
  exportScanArchive(workspace_revision: string): Promise<{ filename: string; archive_text: string; sha256: string }> {
    return this.request("/v1/product/scan-review/archive-export", { workspace_revision });
  }
  importScanArchive(workspace_revision: string, archive_text: string): Promise<ScanReviewState> {
    return this.request("/v1/product/scan-review/archive-import", { workspace_revision, archive_text });
  }
  proposeMapOverlay(workspace_revision: string): Promise<ScanReviewState> {
    return this.request("/v1/product/scan-review/map-propose", { workspace_revision });
  }
  applyMapOverlay(workspace_revision: string, proposal_revision: string): Promise<ScanReviewState> {
    return this.request("/v1/product/scan-review/map-apply", { workspace_revision, proposal_revision });
  }
  compareOfflineRoutes(workspace_revision: string, conditions_revision: string, baseline: unknown, candidate: unknown): Promise<ScanReviewState> {
    return this.request("/v1/product/scan-review/compare", { workspace_revision, conditions_revision, baseline, candidate });
  }
  importRobotReport(report: unknown): Promise<RobotReportState> {
    return this.request("/v1/product/robot/report", { report });
  }
  productState(): Promise<ProductState> { return this.readState("/v1/product/state"); }
  runtimeState(): Promise<SupervisorState> { return this.readState("/v1/product/runtime"); }
  runtimeDiagnostics(): Promise<RuntimeDiagnostics> { return this.readState("/v1/product/runtime/diagnostics"); }
  providerSettings(): Promise<ProviderSettingsState> {
    return this.request("/v1/product/provider-settings");
  }
  providerKeys(): Promise<ProviderKeyList> { return this.request('/v1/product/provider-keys'); }
  updateProviderKeys(body: object): Promise<ProviderKeyList> { return this.request('/v1/product/provider-keys', body); }
  robotRegistry(): Promise<RobotRegistryState> { return this.readState('/v1/product/robots'); }
  updateRobotRegistry(body:object):Promise<RobotRegistryState> { return this.request('/v1/product/robots',body); }
  saveProviderSettings(body: {
    base_url: string; model_id: string; reasoning_effort: string; api_key: string;
    credential_reapproval: boolean; provider_profile: string;
  }): Promise<ProviderSettingsState> {
    return this.request("/v1/product/provider-settings", body);
  }
  selectInput(body: object): Promise<WorkflowState> { return this.request("/v1/product/input", body); }
  generate(): Promise<WorkflowState> { return this.request("/v1/product/generation", {}); }
  cancelGeneration(): Promise<WorkflowState> { return this.request("/v1/product/generation/cancel", {}); }
  acknowledge(revision: string): Promise<WorkflowState> {
    return this.request("/v1/product/draft/acknowledge", { revision });
  }
  savePresentation(sourceSceneRevision: string, view: string, lighting: string): Promise<WorkflowState> {
    return this.request("/v1/product/presentation", {
      expected_source_scene_revision: sourceSceneRevision,
      presentation: { schema_version: 1, view, lighting },
    });
  }
  acquireLease(): Promise<{ control_lease_id: string; ttl_s: number }> {
    return this.leaseAction('/v1/product/lease',{});
  }
  renewLease(controlLeaseId: string): Promise<{ control_lease_id: string; ttl_s: number }> {
    return this.leaseAction('/v1/product/lease/renew',{control_lease_id:controlLeaseId});
  }
  private leaseAction(path:string,body:object):Promise<{control_lease_id:string;ttl_s:number}> {
    // A lease is a context-bound mutation, never a deferred read. In particular,
    // do not replay an old owner's queued timer in the newly selected project.
    if(this.projectReadBarrier)return Promise.reject(new ApiError('lease_context_transition','Control lease request was not sent while the selected conversation is changing.'));
    const controller=new AbortController();let timer:ReturnType<typeof setTimeout>;
    const pending=Promise.race([
      this.request<{control_lease_id:string;ttl_s:number}>(path,body,controller.signal,false),
      new Promise<never>((_,reject)=>{timer=setTimeout(()=>{
        reject(new ApiError('delivery_unknown','Control lease response exceeded 3 seconds. Its outcome is unknown; no automatic retry.'));
        controller.abort();
      },3000);}),
    ]).finally(()=>{clearTimeout(timer);this.leaseActions.delete(pending);});
    this.leaseActions.add(pending);return pending;
  }
  command(
    commandType: CommandType,
    expectedAppliedRevision: string | null,
    artifactId?: string,
    simulationId?: string,
  ): Promise<Operation> {
    return this.request("/v1/product/commands", {
      client_request_id: crypto.randomUUID(),
      command_type: commandType,
      expected_applied_revision: expectedAppliedRevision,
      ...(artifactId ? { artifact_id: artifactId } : {}),
      ...(simulationId ? { simulation_id: simulationId } : {}),
    });
  }
}

export async function fileToBase64(file: File): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += 32_768) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 32_768));
  }
  return btoa(binary);
}
