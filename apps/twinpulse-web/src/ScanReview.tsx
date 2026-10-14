// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { useState } from "react";
import type { TwinPulseApi } from "./api";
import { RouteComparison, type RouteConditions, type ComparisonResult } from "./RouteComparison";
import { MapRefresh, type MapPreview } from "./MapRefresh";
import { DerivedReview } from "./DerivedReview";
import type { WorkflowState } from "./types";

interface SceneObject {
  id: string; kind: string; dynamic: boolean; collision: boolean;
  transform: { position_m: number[]; rotation_rpy_deg: number[] };
  shape: { type: string; dimensions_m: number[] };
}
interface Scene { revision: string; objects: SceneObject[] }
export interface ScanReviewState {
  workspace_revision: string; mode: "isolated_offline_review";
  active_project_changed: false; motion_authorized: false; demo_ready: false;
  physical_validation: "NOT_RUN"; notice: string;
  scene: Scene | null; before_scene: Scene | null;
  scan: null | { provenance: string; scene_revision: string; valid_beams: number; invalid_beams: number;
    points: { frame_index: number; beam_index: number; x_m: number; y_m: number }[] };
  proposal: null | { revision: string; object_id: string; delta_xy_m: number[]; max_residual_m: number; pairs: unknown[] };
  edit_revision: string | null; map_present: boolean; mission_present: boolean;
  route_conditions?: RouteConditions | null; route_comparison?: ComparisonResult | null; route_unavailable_reason?: string | null;
  map_refresh_available?: boolean; map_proposal?: MapPreview | null; map_overlay?: MapPreview | null;
  archive_action_count?: number;
}

function ScanOverlay({ state }: { state: ScanReviewState }) {
  if (!state.scene || !state.scan) return null;
  const objects = [...(state.before_scene?.objects ?? []), ...state.scene.objects];
  const coordinates = objects.flatMap(o => {
    const [x, y] = o.transform.position_m;
    const radius = Math.hypot(...o.shape.dimensions_m.slice(0, 2)) / 2;
    return [[x - radius, y - radius], [x + radius, y + radius]];
  }).concat(state.scan.points.map(p => [p.x_m, p.y_m]));
  if (!coordinates.length) coordinates.push([0, 0], [1, 1]);
  const minX = Math.min(...coordinates.map(p => p[0])) - .2;
  const maxX = Math.max(...coordinates.map(p => p[0])) + .2;
  const minY = Math.min(...coordinates.map(p => p[1])) - .2;
  const maxY = Math.max(...coordinates.map(p => p[1])) + .2;
  const width = Math.max(1, maxX - minX), height = Math.max(1, maxY - minY);
  const mark = (o: SceneObject, before: boolean) => {
    const [x, y] = o.transform.position_m, [dx, dy] = o.shape.dimensions_m;
    if (o.shape.type !== "box") return null;
    return <rect key={`${before}-${o.id}`} x={-dx / 2} y={-dy / 2} width={dx} height={dy}
      transform={`translate(${x} ${-y}) rotate(${-o.transform.rotation_rpy_deg[2]})`}
      fill={before ? "none" : o.kind === "floor" ? "#eef2f5" : "#79a7df55"}
      stroke={before ? "#71717a" : "#2563a4"} strokeWidth={width / 700}
      strokeDasharray={before ? `${width / 100} ${width / 100}` : undefined}>
      <title>{o.id} · {before ? "Imported" : "Scratch draft"}</title></rect>;
  };
  return <>
    <svg role="img" aria-label="Offline scan and scratch draft overlay" className="scan-overlay"
      viewBox={`${minX} ${-maxY} ${width} ${height}`}>
      {state.scene.objects.map(o => mark(o, false))}
      {state.before_scene?.objects.map(o => mark(o, true))}
      {state.scan.points.map(p => <circle key={`${p.frame_index}-${p.beam_index}`} cx={p.x_m} cy={-p.y_m}
        r={width / 450} fill="#c2410c"><title>Frame {p.frame_index}, beam {p.beam_index}: {p.x_m.toFixed(3)}, {p.y_m.toFixed(3)} m</title></circle>)}
    </svg>
    <p>Top view · metres · +X right, +Y up. Dashed: imported boxes; blue: scratch boxes; orange: sampled returns. Cylinders are not drawn.</p>
  </>;
}

export function ScanReview({ api, workflow, onWorkflow, productBusy = false }: {
  api: TwinPulseApi; workflow?: WorkflowState | null; onWorkflow?: (state: WorkflowState) => void; productBusy?: boolean;
}) {
  const [state, setState] = useState<ScanReviewState | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [objectId, setObjectId] = useState(""), [pairs, setPairs] = useState("[]");
  const [dirty, setDirty] = useState(true), [reviewed, setReviewed] = useState(false);
  async function act(action: () => Promise<ScanReviewState>) {
    setBusy(true); setError(""); setReviewed(false);
    try {
      const next = await action(); setState(next); setDirty(false);
      if (next.proposal) { setObjectId(next.proposal.object_id); setPairs(JSON.stringify(next.proposal.pairs, null, 2)); }
    }
    catch (e) { setError(e instanceof Error ? e.message : "Offline review failed."); }
    finally { setBusy(false); }
  }
  async function importFile(file?: File) {
    if (!file) return;
    await act(async () => {
      if (file.size > 5 * 1024 * 1024) throw new Error("Bundle exceeds 5 MiB.");
      const result = await api.importScanBundle(await file.text());
      setObjectId(""); setPairs("[]"); return result;
    });
  }
  function changed() { setDirty(true); setReviewed(false); }
  async function importArchive(file?: File) {
    if (!file) return;
    await act(async () => {
      if (file.size > 10 * 1024 * 1024) throw new Error("Archive exceeds 10 MiB.");
      const current = state ?? await api.scanReview();
      const result = await api.importScanArchive(current.workspace_revision, await file.text());
      setObjectId(""); setPairs("[]"); return result;
    });
  }
  async function download(archive = false) {
    setBusy(true); setError("");
    try {
      let text: string;
      if (archive && state) {
        const data = await api.exportScanArchive(state.workspace_revision);
        const bytes = new TextEncoder().encode(data.archive_text);
        const digest = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)), b => b.toString(16).padStart(2, "0")).join("");
        if (digest !== data.sha256) throw new Error("Archive download hash mismatch.");
        text = data.archive_text;
      } else text = JSON.stringify(await api.exportScanReview());
      const url = URL.createObjectURL(new Blob([text], { type: "application/json" }));
      const link = document.createElement("a"); link.href = url; link.download = archive ? "offline-scan-archive.json" : "offline-scan-review.json"; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch { setError("Could not export the offline review."); }
    finally { setBusy(false); }
  }
  const selectable = state?.scene?.objects.filter(o => o.kind !== "floor" && !o.dynamic && o.collision && o.shape.type === "box") ?? [];
  const selected = objectId || selectable[0]?.id || "";
  const sourceCurrent = state?.scene?.revision === state?.scan?.scene_revision;
  return <details className="robot-report scan-review">
    <summary>Scan review · Offline scratch draft</summary>
    <p>No robot connection · No active project or Isaac changes · Not ready for physical use</p>
    <p>Import an offline-scan-bundle-1.0 JSON containing a matching site_plan and recording. Save a replay archive before restart if you want to restore the reviewed geometry later.</p>
    <label>Import scan bundle (JSON)<input aria-label="Import scan bundle (JSON)" type="file" accept=".json,application/json"
      disabled={busy} onChange={e => { void importFile(e.target.files?.[0]); e.target.value = ""; }} /></label>
    <label>Restore offline archive (JSON)<input aria-label="Restore offline archive (JSON)" type="file" accept=".json,application/json"
      disabled={busy} onChange={e => { void importArchive(e.target.files?.[0]); e.target.value = ""; }} /></label>
    <p>Archive restore recomputes each saved edit into this isolated workspace. It replaces the current scratch review only; no active Twin, Isaac or robot changes. Pending proposals, comparisons and approvals are not restored.</p>
    <button disabled={busy} onClick={() => void act(() => api.scanReview())}>Refresh offline review</button>
    {busy && <p role="status">Processing offline review…</p>}
    {error && <p role="alert">{error}</p>}
    {workflow?.site_draft && onWorkflow && <DerivedReview
      key={`${state?.workspace_revision}-${workflow.input?.revision}-${workflow.site_draft?.revision}-${workflow.phase}`}
      api={api} workflow={workflow} workspaceRevision={state?.workspace_revision}
      hasEdits={Boolean(state?.archive_action_count)} disabled={busy || productBusy} onWorkflow={onWorkflow} />}
    {state?.scene && <>
      <h3>{state.scan?.provenance.toUpperCase()} — unverified saved evidence</h3>
      <p>{state.scan?.valid_beams} valid / {state.scan?.invalid_beams} missing rays. Missing rays do not establish free space.</p>
      <ScanOverlay state={state} />
      <p>Map: {state.map_present ? state.map_overlay ? "Conservative overlay, unverified" : "Imported, unverified" : "Absent — rebuild required"} · Mission: {state.mission_present ? state.map_overlay ? "Rebound for offline comparison only" : "Imported, unverified" : "Absent — review required"}</p>
      <label>Object to review<select value={selected} disabled={busy} onChange={e => { setObjectId(e.target.value); changed(); }}>
        {selectable.map(o => <option key={o.id} value={o.id}>{o.id}</option>)}
      </select></label>
      <label>Landmark pairs (JSON)<textarea aria-label="Landmark pairs (JSON)" rows={5} value={pairs} disabled={busy}
        onChange={e => { setPairs(e.target.value); changed(); }} /></label>
      <p>Each pair: frame_index, beam_index, object_local_xy_m: [x, y]. Select 2–16 distinct points on the same static box perimeter in one snapshot. Use original beam indices, not preview positions.</p>
      <button disabled={busy || !selected || !sourceCurrent} onClick={() => void act(() => api.proposeScanCorrection(state.workspace_revision, selected, JSON.parse(pairs)))}>Preview XY correction</button>
      {!sourceCurrent && <p>Scene identity changed. Import a new matching bundle before another proposal; undo does not restore old approvals.</p>}
      {state.proposal && !dirty && <p>Proposed {state.proposal.object_id}: ΔX {state.proposal.delta_xy_m[0].toFixed(3)} m, ΔY {state.proposal.delta_xy_m[1].toFixed(3)} m. Maximum pair residual {state.proposal.max_residual_m.toFixed(4)} m. Translation consistency is not verified alignment.</p>}
      <label><input type="checkbox" checked={reviewed} disabled={busy} onChange={e => setReviewed(e.target.checked)} />I reviewed this exact scratch-draft change. It does not approve execution.</label>
      <button disabled={busy || !reviewed || dirty || !state.proposal} onClick={() => void act(() => api.applyScanCorrection(state.workspace_revision, state.proposal!.revision))}>Apply to scratch draft only</button>
      <button disabled={busy || !reviewed || !state.edit_revision} onClick={() => void act(() => api.undoScanCorrection(state.workspace_revision, state.edit_revision!))}>Undo last scratch edit</button>
      <button disabled={busy} onClick={() => void download()}>Export review record</button>
      <button disabled={busy} onClick={() => void download(true)}>Save replay archive</button>
      <p>{state.archive_action_count ?? 0} applied actions in this archive. Files are unverified evidence, not execution authority.</p>
      <p>Apply and undo clear the scratch map and mission. Export review record is for inspection only. Save replay archive is the separate restore format; neither is a runnable project.</p>
      <MapRefresh key={state.workspace_revision} available={state.map_refresh_available ?? false}
        proposal={state.map_proposal ?? null} applied={state.map_overlay ?? null} busy={busy}
        preview={() => void act(() => api.proposeMapOverlay(state.workspace_revision))}
        apply={revision => void act(() => api.applyMapOverlay(state.workspace_revision, revision))} />
      <RouteComparison key={state.route_conditions?.revision ?? "unavailable"} conditions={state.route_conditions ?? null}
        result={state.route_comparison ?? null} reason={state.route_unavailable_reason ?? null} busy={busy}
        compare={(baseline, candidate) => void act(() => api.compareOfflineRoutes(state.workspace_revision,
          state.route_conditions!.revision,
          { id: "baseline", provenance: "manual", points_xy_m: JSON.parse(baseline) },
          { id: "candidate", provenance: "manual", points_xy_m: JSON.parse(candidate) }))} />
    </>}
  </details>;
}
