// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { useEffect, useRef, useState } from "react";
import type { SceneEditPreview, SiteDraftSummary, WorkflowState } from "./types";
import { ApiError, TwinPulseApi } from "./api";
import { FURNITURE_KINDS, interpretFurnitureIntent, type FurnitureKind } from "./furnitureIntent";
import { FurniturePlacementBoard, type StagedFurniture } from "./FurniturePlacementBoard";
import { fakeFurnitureProposal } from "./fakeFurnitureProposal";
import { OperationFeedback } from "./OperationFeedback";
import type { LibraryModel } from './model-library-types';
import {ScenePlacementMap} from './ScenePlacementMap';

type Mode = "new" | "add_box" | "change_box" | "add_furniture" | "change_furniture" | "add_room_item" | "change_room_item" | "undo";
const ROOM_KINDS = ['office_chair','floor_fan','clothes_rack','door_leaf','bag','box','basket',
  'clothing_pile','hanging_clothes','bedding_overhang','cable_bundle','power_adapter','power_strip',
  'small_equipment','monitor','tabletop_item','window_blind','ceiling_light','unknown'];

function freshId(): string {
  return `edit_${crypto.randomUUID().replaceAll("-", "")}`;
}

function numeric(value: string): number | null {
  if (value.trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/** Legacy furniture has no requested dimensions. Derive its local footprint
 * from the saved geometry, rather than displaying an invented half-metre box. */
function savedFootprint(site: SiteDraftSummary, identity: string, angle: number): [number, number] | null {
  const points: [number,number][]=[];
  const yaw=angle*Math.PI/180;
  for(const item of site.objects.filter(o=>o.id===identity||o.id.startsWith(`${identity}_`))){
    const a=(item.rotation_rpy_deg?.[2]??angle)*Math.PI/180;
    for(const dx of [-item.dimensions_m[0]/2,item.dimensions_m[0]/2])
      for(const dy of [-item.dimensions_m[1]/2,item.dimensions_m[1]/2]){
        const x=item.position_m[0]+Math.cos(a)*dx-Math.sin(a)*dy;
        const y=item.position_m[1]+Math.sin(a)*dx+Math.cos(a)*dy;
        points.push([Math.cos(yaw)*x+Math.sin(yaw)*y,-Math.sin(yaw)*x+Math.cos(yaw)*y]);
      }
  }
  if(!points.length)return null;
  const xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);
  return [Math.max(...xs)-Math.min(...xs),Math.max(...ys)-Math.min(...ys)];
}

export function SceneEditReview({ api, site, onApplied, onNewEnvironment }: {
  api: TwinPulseApi;
  site: SiteDraftSummary;
  onApplied: (workflow: WorkflowState) => void;
  onNewEnvironment?: () => void;
}) {
  const boxCalls = (site.editable_calls ?? []).filter((call) => call.tool === "create_box_obstacle");
  const furnitureCalls = (site.editable_calls ?? []).filter((call) => call.tool === "place_furniture");
  const roomCalls = (site.editable_calls ?? []).filter((call) => call.tool === 'place_room_item');
  const [roomKind,setRoomKind] = useState('unknown');
  const [roomLabel,setRoomLabel] = useState('Unknown room obstacle');
  const [z,setZ] = useState('0.35');
  const [mode, setMode] = useState<Mode>("add_box");
  const [target, setTarget] = useState("");
  const [objectId, setObjectId] = useState("");
  const [x, setX] = useState("0");
  const [y, setY] = useState("0");
  const [length, setLength] = useState("0.8");
  const [width, setWidth] = useState("0.5");
  const [height, setHeight] = useState("0.7");
  const [yaw, setYaw] = useState("0");
  const [furnitureKind, setFurnitureKind] = useState<FurnitureKind>("bed");
  const [library,setLibrary] = useState<LibraryModel[]>([]);
  const [adjustable,setAdjustable] = useState(false);
  const [variant,setVariant] = useState('standard');
  const [finish,setFinish] = useState('natural');
  const [furnitureRequest, setFurnitureRequest] = useState("");
  const [furnitureExplanation, setFurnitureExplanation] = useState<string | null>(null);
  const [staged, setStaged] = useState<StagedFurniture[]>([]);
  const [preview, setPreview] = useState<SceneEditPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [busyLabel, setBusyLabel] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const currentRevision = useRef(site.revision);
  currentRevision.current = site.revision;

  useEffect(() => { setPreview(null); setFurnitureExplanation(null); setTarget(""); setStaged([]); setError(null); }, [site.revision]);

  const invalidate = () => { setPreview(null); setError(null); };
  const showError = (caught: unknown, fallback: string) => setError(caught instanceof ApiError
    ? `${caught.message} (${caught.code})`
    : caught instanceof TypeError && /Failed to fetch|NetworkError/i.test(caught.message)
      ? "Cannot connect to the App server. Check the connection and refresh the current saved scene before retrying."
      : caught instanceof Error ? caught.message : fallback);
  useEffect(() => {
    let alive=true;
    if (typeof api.modelLibrary === 'function') void api.modelLibrary().then(result=>{
      if(alive)setLibrary(result.models);
    }).catch(caught=>{if(alive)showError(caught,'Model library is unavailable.');});
    return ()=>{alive=false;};
  },[api]);
  const model=library.find(item=>item.kind===furnitureKind&&item.tool==='place_furniture');
  const selectAdjustable=(enabled:boolean,kind: FurnitureKind=furnitureKind)=>{
    setAdjustable(enabled);setVariant('standard');setFinish('natural');invalidate();
    const entry=library.find(item=>item.kind===kind&&item.tool==='place_furniture');
    if(enabled&&entry?.dimensions_m.default){
      setLength(String(entry.dimensions_m.default[0]));setWidth(String(entry.dimensions_m.default[1]));setHeight(String(entry.dimensions_m.default[2]));
    }
  };
  const selectTarget = (id: string) => {
    setTarget(id);
    invalidate();
    const call = [...boxCalls, ...furnitureCalls, ...roomCalls].find((item) => item.call_id === id);
    if (!call) return;
    const args = call.arguments;
    const center = args.center_m;
    const dimensions = args.dimensions_m;
    if (call.tool === "place_furniture" && FURNITURE_KINDS.includes(args.kind as FurnitureKind)) {
      setFurnitureKind(args.kind as FurnitureKind);
      setAdjustable(args.catalog_version==='furniture-parametric-1.0');
      setVariant(String(args.variant??'standard'));setFinish(String(args.finish??'natural'));
    }
    setObjectId(String(args.id ?? ""));
    if (call.tool === 'place_room_item') {
      setRoomKind(String(args.kind)); setRoomLabel(String(args.label));
      const position = args.position_m as number[];
      setX(String(position[0]));setY(String(position[1]));setZ(String(position[2]));
    }
    if (Array.isArray(center) && center.length === 2) {
      setX(String(center[0])); setY(String(center[1]));
    }
    if (Array.isArray(dimensions) && dimensions.length === 3) {
      setLength(String(dimensions[0])); setWidth(String(dimensions[1])); setHeight(String(dimensions[2]));
    }
    setYaw(String(args.yaw_deg ?? 0));
  };

  const interpretRequest = () => {
    invalidate();
    const intent = interpretFurnitureIntent(furnitureRequest, furnitureCalls, target);
    setFurnitureExplanation(intent.explanation);
    if (intent.status === "staging") {
      setStaged(intent.kinds.map((kind) => ({
        id: `furn_${crypto.randomUUID().slice(0, 8)}_${kind}`, kind, x: null, y: null, yawDeg: 0,
      })));
      return;
    }
    if (intent.status !== "proposal") return;
    setStaged([]);
    setMode(intent.mode);
    setFurnitureKind(intent.kind);
    if (intent.mode === "add_furniture") {
      setTarget("");
      setObjectId(`furn_${crypto.randomUUID().slice(0, 8)}_${intent.kind}`);
      setX(intent.x === null ? "" : String(intent.x));
      setY(intent.y === null ? "" : String(intent.y));
      setYaw("0");
    } else if (intent.targetCallId) {
      selectTarget(intent.targetCallId);
      if (intent.x !== null) setX(String(intent.x));
      if (intent.y !== null) setY(String(intent.y));
    }
  };

  const previewFakeProposal = async () => {
    if (busy) return;
    const requestText = furnitureRequest.trim();
    const selectedCallId = target || null;
    const revision = site.revision;
    setPreview(null); setError(null); setFurnitureExplanation(null);
    setBusy(true); setBusyLabel("Checking the saved scene edit context…");
    try {
      const context = await api.sceneEditContext(requestText, selectedCallId);
      if (context.current_scene_revision !== revision || currentRevision.current !== revision) {
        throw new Error("The scene has changed. Refresh the saved scene before submitting the request again.");
      }
      const proposal = fakeFurnitureProposal(context);
      setBusyLabel("Validating the offline simulated response and previewing the change…");
      const result = await api.previewSceneEditProposal(freshId(), requestText, selectedCallId,
        revision, proposal);
      if (currentRevision.current !== revision) {
        throw new Error("The scene changed during the preview. Refresh it and try again.");
      }
      setFurnitureExplanation(result.explanation);
      if (result.status === "clarify" && proposal.mode === "clarify") return;
      if (result.status !== "preview" || proposal.mode === "clarify" || !result.preview || !proposal.tool_call) {
        throw new Error("The proposal result is not a valid preview. Refresh the saved scene before retrying.");
      }
      const args = proposal.tool_call.arguments as Record<string, unknown>;
      const center = args.center_m as number[];
      setStaged([]);
      setMode(proposal.mode);
      setObjectId(String(args.id));
      setFurnitureKind(args.kind as FurnitureKind);
      setAdjustable(args.catalog_version==='furniture-parametric-1.0');
      setVariant(String(args.variant??'standard'));setFinish(String(args.finish??'natural'));
      if(Array.isArray(args.dimensions_m)) {
        setLength(String(args.dimensions_m[0]));setWidth(String(args.dimensions_m[1]));setHeight(String(args.dimensions_m[2]));
      }
      setX(String(center[0])); setY(String(center[1])); setYaw(String(args.yaw_deg));
      setTarget(proposal.mode === "change_furniture" ? selectedCallId ?? "" : "");
      setPreview(result.preview);
    } catch (caught) {
      setPreview(null);
      showError(caught, "Could not validate the simulated edit proposal. Refresh the saved scene.");
    } finally { setBusy(false); setBusyLabel(null); }
  };

  const previewEdit = async () => {
    if (mode === "new") return;
    setError(null);
    setBusy(true);
    setBusyLabel("Validating and previewing the change…");
    try {
      let toolCall: Record<string, unknown> | null = null;
      const isFurniture = mode === "add_furniture" || mode === "change_furniture";
      const isRoomItem = mode === 'add_room_item' || mode === 'change_room_item';
      const isChange = mode === "change_box" || mode === "change_furniture" || mode === 'change_room_item';
      if (mode !== "undo") {
        const values = [x, y, yaw, ...(isFurniture && !adjustable ? [] : [length, width, height])].map(numeric);
        if (!/^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(objectId) ||
            (isRoomItem && (objectId.length > 42 || numeric(z) === null || !roomLabel.trim())) ||
            (isFurniture && objectId.length > 48) || values.some((v) => v === null)) {
          throw new Error("Use an object ID starting with a letter and finite numeric dimensions/coordinates.");
        }
        const callId = isChange ? target : freshId();
        if (!callId) throw new Error("Select the exact object to change.");
        toolCall = isRoomItem
          ? {call_id:callId,tool:'place_room_item',arguments:{id:objectId,kind:roomKind,label:roomLabel,
              catalog_version:'room-items-1.0',position_m:[values[0],values[1],numeric(z)],
              dimensions_m:[values[3],values[4],values[5]],yaw_deg:values[2],
              observation_time_utc:isChange ? roomCalls.find(c=>c.call_id===target)?.arguments.observation_time_utc ?? null : null}}
          : isFurniture
          ? { call_id: callId, tool: "place_furniture", arguments: {
              id: objectId, kind: furnitureKind, catalog_version: adjustable ? 'furniture-parametric-1.0' : "furniture-blocks-1.0",
              center_m: [values[0], values[1]], yaw_deg: values[2],
              ...(adjustable ? {dimensions_m:[values[3],values[4],values[5]],variant,finish}:{}),
            } }
          : { call_id: callId, tool: "create_box_obstacle", arguments: {
              id: objectId, center_m: [values[0], values[1]],
              dimensions_m: [values[3], values[4], values[5]], yaw_deg: values[2],
            } };
      }
      setPreview(await api.previewSceneEdit(freshId(), mode === "undo" ? "undo" : isChange ? "change" : "add",
        isChange ? target : null, toolCall));
    } catch (caught) {
      setPreview(null);
      showError(caught, "Could not preview the change.");
    } finally { setBusy(false); setBusyLabel(null); }
  };

  const applyEdit = async () => {
    if (!preview || preview.parent_revision !== site.revision) return;
    setBusy(true);
    setBusyLabel("Saving the reviewed change…");
    setError(null);
    try {
      const next = await api.applySceneEdit(preview.operation, preview.preview_digest);
      setPreview(null);
      onApplied(next);
    } catch (caught) {
      setPreview(null);
      showError(caught, "Could not verify the save result. Refresh the current scene.");
    } finally { setBusy(false); setBusyLabel(null); }
  };

  const affectedIds = preview ? Array.from(new Set([
    ...Object.keys(preview.affected_before), ...Object.keys(preview.affected_after),
  ])).sort() : [];
  const describe = (value: SceneEditPreview["affected_before"][string] | undefined) => value
    ? `${value.position_m.map((part) => part.toFixed(2)).join(" / ")} m · ${value.dimensions_m.map((part) => part.toFixed(2)).join(" × ")} m`
    : "—";
  const isFurniture = mode === "add_furniture" || mode === "change_furniture";
  const isRoomItem = mode === 'add_room_item' || mode === 'change_room_item';
  const isChange = mode === "change_box" || mode === "change_furniture" || mode === 'change_room_item';
  const selectedFurniture = furnitureCalls.find((call) => call.call_id === target);
  const selectedCall = [...furnitureCalls,...roomCalls].find(call=>call.call_id===target);
  const attachedChildren = site.placement_contract?.relations.filter(
    item=>item.parent_id===selectedCall?.arguments.id) ?? [];
  const selectedRelation=site.placement_contract?.relations.find(item=>item.id===selectedCall?.arguments.id);
  const selectedSize=selectedCall?.arguments.dimensions_m;
  const legacyFootprint=selectedCall ? savedFootprint(site,String(selectedCall.arguments.id),Number(selectedCall.arguments.yaw_deg??0)):null;
  const selectedCenter = selectedFurniture?.arguments.center_m;
  const furnitureUnchanged = mode === "change_furniture" && selectedFurniture != null &&
    objectId === selectedFurniture.arguments.id && furnitureKind === selectedFurniture.arguments.kind &&
    Array.isArray(selectedCenter) && numeric(x) === selectedCenter[0] && numeric(y) === selectedCenter[1] &&
    numeric(yaw) === selectedFurniture.arguments.yaw_deg &&
    adjustable === (selectedFurniture.arguments.catalog_version==='furniture-parametric-1.0') &&
    (!adjustable || (JSON.stringify([numeric(length),numeric(width),numeric(height)])===JSON.stringify(selectedFurniture.arguments.dimensions_m) &&
      variant===selectedFurniture.arguments.variant && finish===selectedFurniture.arguments.finish));
  const furniturePositionMissing = isFurniture && (numeric(x) === null || numeric(y) === null || numeric(yaw) === null);

  return <div className="panel scene-edit-review">
    <h3>Scene edits · local review</h3>
    <p>The original is retained. Edits are saved as a separate revision; Build needs a fresh acknowledgement. This does not move a robot.</p>
    {attachedChildren.length>0&&<p role="note">This parent has {attachedChildren.length} estimated attached items: {attachedChildren.map(item=>item.id).join(', ')}.
      {' '}Moving, rotating or resizing it updates those items in the same preview. Apply and Undo include the group. A too-small support is rejected.</p>}
    <div className="furniture-intent">
      <p className="fine" aria-label="Current furniture request context">Saved scene {site.revision.slice(0, 10)} · {furnitureCalls.length} furniture items · selected {furnitureCalls.find((call) => call.call_id === target)?.arguments.id as string ?? "none"}. Only this saved scene is checked by local rules.</p>
      <label>Furniture request (offline)
        <input aria-label="Furniture request" value={furnitureRequest} disabled={busy} placeholder="Example: add sofa X=0.5 Y=-1.2 / move selected bed X=-0.8"
          onChange={(event) => { setFurnitureRequest(event.target.value); setFurnitureExplanation(null); invalidate(); }} />
      </label>
      <button disabled={busy || site.derived_review_revision != null} onClick={interpretRequest}>Interpret furniture request</button>
      <p>Local rules interpret only a short supported request. No model call, photo analysis, or automatic save.</p>
      <button type="button" disabled={busy || !furnitureRequest.trim() || site.derived_review_revision != null}
        onClick={() => void previewFakeProposal()}>Preview offline simulated proposal</button>
      <p>The server rechecks the saved scene and selected furniture before validating the simulated response. No live model call or automatic save.</p>
      {furnitureExplanation && <p role="status">{furnitureExplanation}</p>}
    </div>
    {staged.length > 0 && <FurniturePlacementBoard api={api} site={site} items={staged}
      onItemsChange={setStaged} onApplied={onApplied} />}
    {staged.length === 0 && <><div className="action-row">
      {onNewEnvironment && <label><input type="radio" name="scene-edit-mode" checked={mode === "new"} onChange={() => { setMode("new"); invalidate(); }} /> New environment</label>}
      <label><input type="radio" name="scene-edit-mode" checked={mode === "add_box"} onChange={() => { setMode("add_box"); setTarget(""); invalidate(); }} /> Add box</label>
      <label><input type="radio" name="scene-edit-mode" checked={mode === "change_box"} onChange={() => { setMode("change_box"); setTarget(""); invalidate(); }} /> Change box</label>
      <label><input type="radio" name="scene-edit-mode" checked={mode === "add_furniture"} onChange={() => { setMode("add_furniture"); setTarget(""); setFurnitureKind("bed"); setObjectId(`furn_${crypto.randomUUID().slice(0, 8)}_bed`); invalidate(); }} /> Add furniture</label>
      <label><input type="radio" name="scene-edit-mode" checked={mode === "change_furniture"} onChange={() => { setMode("change_furniture"); setTarget(""); invalidate(); }} /> Change furniture</label>
      <label><input type="radio" name="scene-edit-mode" checked={mode === 'add_room_item'} onChange={()=>{setMode('add_room_item');setTarget('');setObjectId(`item_${crypto.randomUUID().slice(0,8)}`);invalidate();}}/> Add room item / hazard</label>
      <label><input type="radio" name="scene-edit-mode" checked={mode === 'change_room_item'} onChange={()=>{setMode('change_room_item');setTarget('');invalidate();}}/> Change room item / hazard</label>
      <label><input type="radio" name="scene-edit-mode" checked={mode === "undo"} disabled={!site.scene_edit_count} onChange={() => { setMode("undo"); invalidate(); }} /> Undo last edit</label>
    </div>
    {isChange && <label>{isRoomItem ? 'Existing room item call' : isFurniture ? "Existing furniture call" : "Existing box call"} <select
      aria-label={isRoomItem ? 'Existing room item call' : isFurniture ? 'Existing furniture call' : 'Existing box call'}
      value={target} onChange={(event) => selectTarget(event.target.value)}>
      <option value="">Select one</option>{(isRoomItem ? roomCalls : isFurniture ? furnitureCalls : boxCalls).map((call) => <option value={call.call_id} key={call.call_id}>{call.arguments.id as string} · {call.call_id}</option>)}
    </select></label>}
    {mode === "new" && <div><p>Create a separate project. The current room and its history remain unchanged.</p><button onClick={onNewEnvironment}>Go to project creation</button></div>}
    {mode !== "undo" && mode !== "new" && <div className="scene-edit-fields">
      <label>Object ID<input aria-label="Object ID" value={objectId} onChange={(event) => { setObjectId(event.target.value); invalidate(); }} /></label>
      {isRoomItem && <><label>Room item type<select aria-label="Room item type" value={roomKind} onChange={e=>{setRoomKind(e.target.value);invalidate();}}>
        {ROOM_KINDS.map(kind=><option key={kind} value={kind}>{kind.replaceAll('_',' ')}</option>)}</select></label>
        <label>Item label<input aria-label="Item label" value={roomLabel} onChange={e=>{setRoomLabel(e.target.value);invalidate();}}/></label>
        <label>Center Z (m)<input aria-label="Center Z (m)" type="number" step="0.01" value={z} onChange={e=>{setZ(e.target.value);invalidate();}}/></label>
        <p>Approximate placement only. Fabric, cables and unknown items add a synthetic keepout. Use the photo inventory's exact ID to cover a listed item. No observation timestamp is invented.</p></>}
      {mode === 'add_room_item' && site.photo_inventory && <label>Photo item to place<select aria-label="Photo item to place" value="" onChange={e=>{
        const ref=site.photo_inventory?.items.find(i=>i.id===e.target.value);if(!ref)return;
        setObjectId(ref.id);setRoomKind(ref.kind);setRoomLabel(ref.label);invalidate();
      }}><option value="">Select an unplaced photo item</option>{site.photo_inventory.items.filter(i=>
        i.placement_status!=='represented'&&ROOM_KINDS.includes(i.kind)).map(i=><option key={i.id} value={i.id}>{i.label}</option>)}</select></label>}
      {isFurniture && <label>Furniture type<select aria-label="Furniture type" value={furnitureKind} onChange={(event) => {
        const next = event.target.value as FurnitureKind;
        setObjectId((previous) => previous.endsWith(`_${furnitureKind}`) ? `${previous.slice(0, -furnitureKind.length)}${next}` : previous);
        setFurnitureKind(next); invalidate();
        if(adjustable)selectAdjustable(true,next);
      }}>{FURNITURE_KINDS.map((kind) => <option key={kind} value={kind}>{kind.replace("_", " ")}</option>)}</select></label>}
      {isFurniture && <><label><input aria-label="Adjustable library model" type="checkbox" checked={adjustable}
        disabled={!model || (isChange&&selectedFurniture?.arguments.catalog_version==='furniture-parametric-1.0')}
        onChange={e=>selectAdjustable(e.target.checked)}/>Adjustable library model</label>
        {adjustable&&model&&<><p>{model.model_id} · {model.environments.join(' / ')} · width X / depth Y / height Z, metres. Dimensions are estimates unless measured.</p>
          <label>Model variant<select aria-label="Model variant" value={variant} onChange={e=>{setVariant(e.target.value);invalidate();}}>
            {model.variants?.map(value=><option key={value}>{value}</option>)}</select></label>
          <label>Model finish<select aria-label="Model finish" value={finish} onChange={e=>{setFinish(e.target.value);invalidate();}}>
            {model.finishes?.map(value=><option key={value}>{value}</option>)}</select></label></>}
      </>}
      {([ ["X (m)", x, setX], ["Y (m)", y, setY],
          ...(!isFurniture || adjustable ? [[adjustable&&isFurniture ? 'Width X (m)' : "Length (m)", length, setLength], [adjustable&&isFurniture ? 'Depth Y (m)' : "Width (m)", width, setWidth],
              ["Height (m)", height, setHeight]] as const : []), ["Yaw (°)", yaw, setYaw] ] as const).map(([label, value, setter]) =>
        <label key={label}>{label}<input aria-label={label} type="number" step="0.01" value={value}
          onChange={(event) => { setter(event.target.value); invalidate(); }} /></label>)}
    </div>}
    {isChange&&selectedCall&&(Array.isArray(selectedSize)||legacyFootprint)&&numeric(x)!==null&&numeric(y)!==null&&numeric(yaw)!==null&&
      <ScenePlacementMap site={site} label={String(selectedCall.arguments.label??selectedCall.arguments.kind)}
        identity={String(selectedCall.arguments.id)} position={[numeric(x)!,numeric(y)!]}
        dimensions={isFurniture&&adjustable||isRoomItem ? [numeric(length)??.1,numeric(width)??.1] :
          Array.isArray(selectedSize) ? [Number(selectedSize[0]),Number(selectedSize[1])] : legacyFootprint!}
        yaw={numeric(yaw)!} disabled={busy||site.derived_review_revision!=null}
        lockedReason={selectedRelation&&selectedRelation.relation!=='floor' ?
          `Attached by ${selectedRelation.relation}. Move or rotate parent ${selectedRelation.parent_id} instead; independent dragging would detach it.`:undefined}
        onChange={(position,angle)=>{setX(String(position[0]));setY(String(position[1]));setYaw(String(angle));invalidate();}}/>}
    {mode !== "new" && <div className="action-row">
      <button disabled={busy || site.derived_review_revision != null || (isChange && !target) ||
        furniturePositionMissing || furnitureUnchanged} onClick={() => void previewEdit()}>Preview change</button>
      <button className="primary" disabled={busy || !preview || preview.parent_revision !== site.revision} onClick={() => void applyEdit()}>Save reviewed change</button>
    </div>}
    {preview && <div role="status"><p>Preview {preview.result_revision.slice(0, 10)} · {preview.preserved_object_count} existing objects unchanged. Physical validation: not run.</p>
      <div className="table-wrap"><table><thead><tr><th>Object</th><th>Before · position / size</th><th>After · position / size</th></tr></thead><tbody>
        {affectedIds.map((id) => <tr key={id}><td>{id}</td><td>{describe(preview.affected_before[id])}</td><td>{describe(preview.affected_after[id])}</td></tr>)}
      </tbody></table></div>
    </div>}
    </>}
    <OperationFeedback busyLabel={busyLabel} error={error} onDismiss={() => setError(null)} />
    {site.scene_edit_count ? <p>Saved edits: {site.scene_edit_count} · original revision {site.original_scene_revision?.slice(0, 10)} · current {site.revision.slice(0, 10)}</p> : null}
  </div>;
}
