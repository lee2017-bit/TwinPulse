// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { useEffect, useRef, useState } from "react";
import type { TwinPulseApi } from "./api";

export interface NativePhotoBinding {
  role: "room" | "top_view"; sha256: string; media_type: "image/jpeg";
  same_position_user_declared: boolean; window_direction: "up" | "unspecified";
}
export interface NativeHypothesis { id: string; rotation_deg: number; mirror_native_y: boolean }
export interface NativeQuality {
  assessment: "DESCRIPTIVE_ONLY"; frame_count: number; sample_count: number; excluded_count: number;
  excluded_percent: number; min_usable_per_frame: number; max_usable_per_frame: number;
  worst_return_gap_deg: number; never_observed_angle_bins: number; clearance: "UNKNOWN";
  stationarity_verified: false; range_accuracy_verified: false; motion_authorized: false;
  angle_groups: { native_angle_start_deg: number; native_angle_end_deg: number; frames_with_returns: number;
    frames_total: number; median_of_frame_medians_m: number | null; p10_frame_median_m: number | null;
    p90_frame_median_m: number | null; median_absolute_deviation_m: number | null }[];
}
export interface NativeScanState {
  workspace_revision: string; notice: string; mode: "saved_native_evidence_only";
  active_project_changed: false; motion_authorized: false; demo_ready: false;
  source_bytes_verified: false; world_tf: null; robot_heading: null; handedness_verified: false;
  physical_validation: "NOT_RUN";
  analysis?: NativeQuality | null;
  registration?: null | { proposal_digest: string; frame_index: number; notice: string;
    reference_kind: string; reference_sha256: string; scene_revision: string;
    fit_status: "UNIQUE_CANDIDATE" | "AMBIGUOUS" | "NO_FIT";
    candidate_native_y_sign: number | null; world_alignment_verified: false;
    candidates: { native_y_sign: number; fit_pass: boolean; max_residual_m: number | null;
      rms_residual_m: number | null; rigid_transform: null | { x_m: number; y_m: number; yaw_rad: number } }[] };
  bundle: null | { digest: string; frame_count: number; sample_count: number;
    source: { kind: "saved_sensor_recording" | "synthetic_test_fixture"; raw_sha256: string; nodes_sha256: string;
      observation_start_utc: string; observation_end_utc: string; timestamp_basis: string };
    photos: NativePhotoBinding[]; display_hypotheses: NativeHypothesis[] };
  frame: null | { index: number; samples: number; invalid_returns: number;
    points: { angle_deg: number; distance_m: number; quality: number; node_index: number; source_byte_cursor: number; x_m: number; y_m: number }[] };
}

export function displayPoint(x: number, y: number, candidate?: NativeHypothesis): [number, number] {
  if (!candidate) return [x, y];
  const a = candidate.rotation_deg * Math.PI / 180;
  const reflectedY = candidate.mirror_native_y ? -y : y;
  return [Math.cos(a) * x - Math.sin(a) * reflectedY, Math.sin(a) * x + Math.cos(a) * reflectedY];
}

function NativePhoto({ binding }: { binding: NativePhotoBinding }) {
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  const [checking, setChecking] = useState(false);
  const generation = useRef(0);
  const ownedUrl = useRef("");
  useEffect(() => () => { generation.current++; if (ownedUrl.current) URL.revokeObjectURL(ownedUrl.current); }, []);
  async function attach(file?: File) {
    if (!file) return;
    const request = ++generation.current;
    setChecking(true); setError(""); setUrl("");
    if (ownedUrl.current) URL.revokeObjectURL(ownedUrl.current);
    ownedUrl.current = "";
    try {
      if (file.size > 10 * 1024 * 1024) throw new Error("Photo exceeds 10 MiB.");
      const bytes = await file.arrayBuffer();
      const signature = new Uint8Array(bytes);
      if (signature[0] !== 255 || signature[1] !== 216 || signature[2] !== 255) throw new Error("Original JPEG required.");
      const hash = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)), b => b.toString(16).padStart(2, "0")).join("");
      if (hash !== binding.sha256) throw new Error("Photo hash mismatch. Select the original bound photo.");
      if (generation.current !== request) return;
      ownedUrl.current = URL.createObjectURL(new Blob([bytes], { type: "image/jpeg" }));
      setUrl(ownedUrl.current);
    } catch (e) { if (generation.current === request) setError(e instanceof Error ? e.message : "Photo could not be verified."); }
    finally { if (generation.current === request) setChecking(false); }
  }
  return <figure className="native-photo">
    <figcaption>{binding.role === "room" ? "Room photo" : "Top-view photo"}</figcaption>
    <label>Attach {binding.role} original JPEG (local only)
      <input type="file" accept="image/jpeg" disabled={checking} onChange={e => { void attach(e.target.files?.[0]); e.target.value = ""; }} />
    </label>
    {checking && <p>Checking original photo bytes…</p>}
    {error && <p role="alert">{error}</p>}
    {url && <><p>SHA-256 matched · local photo only</p><img src={url} alt={`${binding.role} hash-matched source photo`}
      onError={() => { setUrl(""); setError("JPEG could not be decoded."); }}
      onLoad={e => { if (e.currentTarget.naturalWidth * e.currentTarget.naturalHeight > 40000000) { setUrl(""); setError("Photo exceeds 40 megapixels."); } }} /></>}
    <p>{binding.same_position_user_declared ? "Same scan position: user declaration, not calibrated registration." : "Context photo; scan-position equivalence not asserted."}
      {binding.window_direction === "up" && " Photo-up = window (user declaration). Not robot-forward."}</p>
  </figure>;
}

export function NativeScanReview({ api }: { api: TwinPulseApi }) {
  const [state, setState] = useState<NativeScanState | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [hypothesis, setHypothesis] = useState("native");
  async function action(work: () => Promise<NativeScanState>, reset = false) {
    setBusy(true); setError("");
    try { setState(await work()); if (reset) setHypothesis("native"); }
    catch (e) { setError(e instanceof Error ? e.message : "Native evidence request failed."); }
    finally { setBusy(false); }
  }
  async function importFile(file?: File) {
    if (!file) return;
    if (file.size > 8 * 1024 * 1024) { setError("Native bundle exceeds 8 MiB."); return; }
    await action(async () => api.importNativeScan(await file.text()), true);
  }
  async function download() {
    setBusy(true); setError("");
    try {
      const exported = await api.exportNativeScan();
      const url = URL.createObjectURL(new Blob([JSON.stringify(exported)], { type: "application/json" }));
      const link = document.createElement("a"); link.href = url; link.download = "native-scan-bundle.json"; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) { setError(e instanceof Error ? e.message : "Export failed."); }
    finally { setBusy(false); }
  }
  async function download3D() {
    if (!state?.frame || !state.bundle) return;
    setBusy(true); setError("");
    try {
      const result = await api.exportNative3D(state.workspace_revision, state.frame.index);
      const bytes = new TextEncoder().encode(result.usda);
      const digest = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)), b => b.toString(16).padStart(2, "0")).join("");
      if (digest !== result.sha256) throw new Error("3D evidence download hash mismatch.");
      const url = URL.createObjectURL(new Blob([bytes], { type: "text/plain" }));
      const link = document.createElement("a"); link.href = url; link.download = result.filename; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) { setError(e instanceof Error ? e.message : "3D export failed."); }
    finally { setBusy(false); }
  }
  async function importReference(file?: File) {
    if (!file || !state?.frame) return;
    if (file.size > 65536) { setError("Reference JSON exceeds 64 KiB."); return; }
    await action(async () => api.proposeNativeRegistration(state.workspace_revision, state.frame!.index, await file.text()));
  }
  const bundle = state?.bundle, frame = state?.frame;
  const candidate = bundle?.display_hypotheses.find(c => c.id === hypothesis);
  const points = frame?.points.map(p => ({ ...p, xy: displayPoint(p.x_m, p.y_m, candidate) })) ?? [];
  const extent = Math.max(1, Math.ceil(Math.max(0, ...points.map(p => Math.max(Math.abs(p.xy[0]), Math.abs(p.xy[1]))))));
  const scale = 250 / extent;
  return <details className="robot-report scan-review native-review">
    <summary>Native scan · Saved photo review</summary>
    <p>Stored evidence only · No robot connection, active project edits or drive controls. Restart clears this review.</p>
    <label>Import native scan bundle (JSON)<input type="file" accept="application/json,.json" disabled={busy}
      onChange={e => { void importFile(e.target.files?.[0]); e.target.value = ""; }} /></label>
    <button disabled={busy} onClick={() => void action(() => api.nativeScan(), true)}>Refresh native evidence</button>
    <button disabled={busy || !bundle} onClick={() => void download()}>Export preserved native bundle</button>
    <button disabled={busy || !frame} onClick={() => void download3D()}>Export selected frame to 3D (USD)</button>
    {busy && <p role="status">Loading saved evidence…</p>}
    {error && <p role="alert">{error}</p>}
    {state && <p className="native-warning">{state.notice}</p>}
    {bundle && frame && <>
      <h3>{bundle.source.kind === "synthetic_test_fixture" ? "SYNTHETIC native fixture" : "Saved sensor recording — imported provenance"}</h3>
      <p>{bundle.source.observation_start_utc} → {bundle.source.observation_end_utc} · host observation window, not individual beam timing.</p>
      <p>{bundle.frame_count} complete frames · {bundle.sample_count} original samples. Raw-file hashes are retained but not independently verified by this App.</p>
      {state.analysis && <details className="native-quality"><summary>Across-frame statistics (not clearance)</summary>
        <p>{state.analysis.excluded_count} / {state.analysis.sample_count} returns excluded ({state.analysis.excluded_percent.toFixed(2)}%).
          Usable returns per frame: {state.analysis.min_usable_per_frame}–{state.analysis.max_usable_per_frame}.
          Widest gap between usable directions: {state.analysis.worst_return_gap_deg.toFixed(2)}°.</p>
        <p className="native-warning">Clearance: UNKNOWN. These 5° groups describe recorded returns only; no rays are resampled.
          Across-frame variation includes object edges and scene changes, not calibrated accuracy or proof the robot was stationary.</p>
        <div className="native-quality-table"><table><thead><tr><th>Native angle</th><th>Frames observed</th><th>Median range</th><th>P10–P90</th></tr></thead>
          <tbody>{state.analysis.angle_groups.map(group => <tr key={group.native_angle_start_deg}>
            <td>{group.native_angle_start_deg}–{group.native_angle_end_deg}°</td><td>{group.frames_with_returns} / {group.frames_total}</td>
            <td>{group.median_of_frame_medians_m === null ? "UNKNOWN" : `${group.median_of_frame_medians_m.toFixed(3)} m`}</td>
            <td>{group.p10_frame_median_m === null || group.p90_frame_median_m === null ? "UNKNOWN" : `${group.p10_frame_median_m.toFixed(3)}–${group.p90_frame_median_m.toFixed(3)} m`}</td>
          </tr>)}</tbody></table></div>
      </details>}
      <div className="native-controls">
        <button disabled={busy || frame.index === 0} onClick={() => void action(() => api.nativeScanFrame(state.workspace_revision, frame.index - 1))}>Previous saved frame</button>
        <label>Saved frame<select disabled={busy} value={frame.index} onChange={e => void action(() => api.nativeScanFrame(state.workspace_revision, Number(e.target.value)))}>
          {Array.from({ length: bundle.frame_count }, (_, index) => <option key={index} value={index}>{index + 1} / {bundle.frame_count}</option>)}
        </select></label>
        <button disabled={busy || frame.index === bundle.frame_count - 1} onClick={() => void action(() => api.nativeScanFrame(state.workspace_revision, frame.index + 1))}>Next saved frame</button>
      </div>
      <div className="native-grid">
        <section><label>Display orientation (not calibration)<select disabled={busy} value={hypothesis} onChange={e => setHypothesis(e.target.value)}>
          <option value="native">Native measured angles</option>
          {bundle.display_hypotheses.map(c => <option key={c.id} value={c.id}>{c.id}: {c.rotation_deg.toFixed(1)}°{c.mirror_native_y ? " + reflection" : ""} · unverified</option>)}
        </select></label>
        <p className="native-warning">{candidate ? "DISPLAY HYPOTHESIS ONLY. Reflection is not a rigid TF. Furniture identity is unverified." : "Native angle zero is not confirmed robot-forward. Handedness and world TF are unverified."}</p>
        <svg className="native-overlay" viewBox="0 0 600 640" role="img" aria-label="Saved native scan points, not a navigation map">
          <rect width="600" height="640" fill="#101b2d" />
          {[1, 2, 3, 4].map(i => <circle key={i} cx="300" cy="300" r={i * 62.5} stroke="#334155" fill="none" />)}
          <path d="M50 300H550 M300 50V550" stroke="#64748b" />
          {points.map(p => <circle key={p.node_index} cx={300 + p.xy[0] * scale} cy={300 - p.xy[1] * scale} r="2.2" fill="#5eead4">
            <title>sample {p.node_index}: {p.angle_deg}°, {p.distance_m} m, quality {p.quality}</title></circle>)}
          <circle cx="300" cy="300" r="5" fill="#fb923c" />
          <g fill="#e2e8f0" fontSize="14"><text x="22" y="25">LiDAR origin · {candidate ? "unverified display axes" : "sensor-native axes"}</text>
            <text x="22" y="588">Outer ring: {extent} m · no interpolation or fabricated returns</text>
            <text x="22" y="613">Missing returns are UNKNOWN, not clear floor.</text></g>
        </svg>
        <p>Frame {frame.index + 1}: {frame.samples} samples · {points.length} usable · {frame.invalid_returns} excluded returns.</p>
        <p>No acquisition-time playback, room scale estimate or geometry approval.</p></section>
        <section key={bundle.digest}>{bundle.photos.map(binding => <NativePhoto key={binding.sha256} binding={binding} />)}</section>
      </div>
      <p>3D export uses native axes only, never the display hypothesis. Open the USD as a separate evidence stage.
        z=0 is the sensor drawing plane, not the floor. No furniture heights, colliders or world alignment are inferred.</p>
      <details className="native-registration"><summary>Coordinate correspondence review (optional, not calibration)</summary>
        <p>Needs 3–16 original sample IDs and independent metric reference points in a named site revision.
          This is not required to inspect scans. Do not substitute guesses from the photo or screen rotation.</p>
        <label>Import coordinate reference JSON<input type="file" accept="application/json,.json" disabled={busy}
          onChange={e => { void importReference(e.target.files?.[0]); e.target.value = ""; }} /></label>
        {!state.registration && <p>No reference proposal for this frame. World alignment: UNVERIFIED.</p>}
        {state.registration && <>
          <h4>Reference fit: {state.registration.fit_status}</h4>
          <p>{state.registration.reference_kind === "synthetic_test_fixture" ? "SYNTHETIC reference — math test only." : "Operator-supplied references — source bytes and physical correspondence unverified."}</p>
          <p className="native-warning">{state.registration.notice}</p>
          <ul>{state.registration.candidates.map(candidate => <li key={candidate.native_y_sign}>
            Native Y sign {candidate.native_y_sign}: {candidate.fit_pass ? "fits draft threshold" : "does not fit"};
            max residual {candidate.max_residual_m === null ? "UNKNOWN" : `${candidate.max_residual_m.toFixed(4)} m`}.
            {candidate.rigid_transform && ` Proper rotation ${(candidate.rigid_transform.yaw_rad * 180 / Math.PI).toFixed(2)}°, translation (${candidate.rigid_transform.x_m.toFixed(3)}, ${candidate.rigid_transform.y_m.toFixed(3)}) m.`}
          </li>)}</ul>
          <p>Proposal digest: <code>{state.registration.proposal_digest}</code></p>
          <p>No proposal is applied to the 3D export, active Twin, TF or robot.</p>
        </>}
      </details>
      <details><summary>Source identities and limits</summary><p>Raw SHA-256: <code>{bundle.source.raw_sha256}</code></p>
        <p>Decoded nodes SHA-256: <code>{bundle.source.nodes_sha256}</code></p>
        <p>Bundle digest: <code>{bundle.digest}</code></p>
        <p>Photo hashes verify selected bytes against imported metadata, not scene alignment or authorship. Physical validation: NOT_RUN. Demo readiness: false.</p></details>
    </>}
  </details>;
}
