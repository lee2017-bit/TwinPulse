// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { useEffect, useRef, useState } from 'react';
import type { TwinPulseApi } from './api';
import {DeviceLogStorage} from './DeviceLogStorage';

export interface RobotReadinessState {
  schema_version: 'robot-readiness-app-1.0'; status: string;
  motion_authorized: false; demo_ready: false; job_id: string | null;
  project_id?: string; current_operation_active?:boolean;record_scope?:string; app_context?: { app_scene_revision: string | null;
    app_robot_profile_id: string | null; capture_status: 'CAPTURED' | 'UNAVAILABLE' } | null;
  started_at_utc?: string; finished_at_utc?: string;
  twin_collection_binding?:{schema_version:string;status:string;context_sha256:string|null;
    historical_reference_only:true;alignment_verified:false;physical_authority:false};
  report_path: string | null; exit_code?: number;
  result: null | { status: string; reason?: string; demo_ready: false; motion_authorized: false;
    boot_id?: string; release_id?: string;
    steps?: Record<string, { status: string; reason?: string | null }>;
    evidence?: { odom?: { status: string; reason?: string }; scan?: { status: string; reason?: string };
      tf?: { status: string }; room_alignment?: string } };
}

export function RobotReadiness({ api, available }: { api: TwinPulseApi; available: boolean }) {
  const [state, setState] = useState<RobotReadinessState | null>(null);
  const [statusAvailable, setStatusAvailable] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [robotOff, setRobotOff] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const mounted = useRef(true);
  const inFlight = useRef(false);
  async function refresh() {
    if (!available || inFlight.current) return;
    inFlight.current = true;
    try { const next = await api.robotReadiness(); if (mounted.current) { setState(next); setStatusAvailable(true); setError(''); } }
    catch { if (mounted.current) { setStatusAvailable(false); setError('Readiness status is unavailable. Do not repeat the collection; refresh the saved result.'); } }
    finally { inFlight.current = false; }
  }
  useEffect(() => {
    mounted.current = true;
    void refresh();
    return () => { mounted.current = false; };
  // Initial GET has no connection or side effect.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [available, api]);
  useEffect(() => {
    if (state?.status !== 'RUNNING') return;
    const timer = setInterval(() => { void refresh(); }, 1500);
    return () => clearInterval(timer);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state?.status, available, api]);
  async function start() {
    if (!available || !statusAvailable || !confirmed || busy || state?.status === 'RUNNING' ||
        state?.status === 'REMOTE_STATE_UNKNOWN' || state?.status === 'LOCAL_RECORD_UNREADABLE') return;
    setBusy(true); setError(''); setConfirmed(false);
    const requestId = crypto.randomUUID().replaceAll('-', '');
    try { setState(await api.startRobotReadiness(requestId)); setStatusAvailable(true); }
    catch {
      setStatusAvailable(false);
      setError('Start response was not confirmed. Do not click again; refresh the saved state first.');
      try { setState(await api.robotReadiness()); setStatusAvailable(true); } catch { /* Keep the error; no automatic action. */ }
    } finally { setBusy(false); }
  }
  async function clearUnknown() {
    if (!robotOff || busy) return;
    setBusy(true); setRobotOff(false); setError('');
    try { setState(await api.clearUncertainRobotReadiness()); }
    catch { setError('Could not record robot-OFF confirmation. Collection remains locked.'); }
    finally { setBusy(false); }
  }
  if (!available) return null;
  const uncertain = state?.status === 'REMOTE_STATE_UNKNOWN' || state?.status === 'LOCAL_RECORD_UNREADABLE';
  const running = state?.status === 'RUNNING';
  return <section className="robot-report robot-console" aria-label="No-motion evidence collection">
    <h2>No-motion evidence collection</h2>
    <DeviceLogStorage api={api}/>
    {state?.current_operation_active===false&&<p>No collection is currently running. The result below is a saved record; it does not prevent creating a chat or editing a SIM Twin.</p>}
    <p>One explicit request runs PC preflight, transfers the reviewed project source, confirms idle,
      collects bounded stationary odom/scan/TF, and saves raw files and a diagnosis. It does not
      start the LiDAR driver, enable motors, drive, calibrate the room, or unlock a demo.</p>
    <p>Opening this panel or refreshing never connects to the robot. The robot must be powered on
      and stationary for collection; the action may deploy reviewed source. No automatic retry.</p>
    <label><input type="checkbox" checked={confirmed} disabled={!statusAvailable || busy || running || uncertain}
      onChange={event => setConfirmed(event.target.checked)} /> I approve this one no-motion source transfer and stationary collection.</label>
    <div className="native-controls">
      <button disabled={!statusAvailable || !confirmed || busy || running || uncertain} onClick={() => void start()}>Collect stationary evidence once</button>
      <button disabled={busy} onClick={() => void refresh()}>Refresh saved result</button>
    </div>
    {running && <p role="status">Collection running. Do not restart or open another robot operation. A disconnect is not proof of safe cleanup.</p>}
    {uncertain && <div role="alert"><p>The saved collection did not confirm the robot's final state. Physical operations need a fresh check or an explicit robot-OFF confirmation.</p>
      <label><input type="checkbox" checked={robotOff} onChange={event => setRobotOff(event.target.checked)} />
        I have physically powered the robot off.</label>
      <button disabled={!robotOff || busy} onClick={() => void clearUnknown()}>Record robot OFF and clear uncertain job</button>
    </div>}
    {error && <div role="alert">{error}<button onClick={() => setError('')}>Dismiss</button></div>}
    {state?.result && <div className="native-quality"><h3>Saved collection result: {state.result.status}</h3>
      <p>Collection ID: <code>{state.job_id ?? 'NOT_RECORDED'}</code> · Project: {state.project_id ?? 'LEGACY_UNATTRIBUTED'}</p>
      {state.twin_collection_binding&&<p>Historical Twin collection reference: {state.twin_collection_binding.status} · {state.twin_collection_binding.context_sha256??'UNBOUND'}. This is not current-scene correspondence, room alignment or motion permission.</p>}
      <p>App scene at collection start: {state.app_context?.app_scene_revision ?? 'NOT_RECORDED'} ·
        Profile: {state.app_context?.app_robot_profile_id ?? 'NOT_RECORDED'} ·
        Context: {state.app_context?.capture_status ?? 'LEGACY_UNKNOWN'}</p>
      <p>Robot boot: {state.result.boot_id ?? 'NOT_RECORDED'} · Release: {state.result.release_id ?? 'NOT_RECORDED'}</p>
      <p>This is one collection record tied to the App project reference; it is not a room-to-odom transform or a linked drive mission.</p>
      {state.result.reason && <p>{state.result.reason}</p>}
      {state.result.steps && <ul>{Object.entries(state.result.steps).map(([name, step]) =>
        <li key={name}>{name}: {step.status}{step.reason ? ` — ${step.reason}` : ''}</li>)}</ul>}
      {state.result.evidence && <p>Odom: {state.result.evidence.odom?.status ?? 'NOT_RECORDED'} ·
        Scan: {state.result.evidence.scan?.status ?? 'NOT_RECORDED'} ·
        TF: {state.result.evidence.tf?.status ?? 'NOT_RECORDED'} ·
        Room alignment: {state.result.evidence.room_alignment ?? 'NOT_VERIFIED'}</p>}
      {state.report_path && <p>Local raw/report bundle: <code>{state.report_path}</code></p>}
    </div>}
    <p className="native-warning">This result is evidence collection only. Missing or rejected ROS data remains a gap;
      physical stop, coordinate calibration and autonomous mission are not approved by this panel.</p>
  </section>;
}
