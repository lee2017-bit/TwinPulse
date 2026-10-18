// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { useEffect, useRef, useState } from 'react';
import type { TwinPulseApi } from './api';
import type { RobotReportState } from './RobotReport';
import { RobotCheckDetails } from './RobotCheckDetails';

export interface RobotDiagnosticsState {
  schema_version: 'robot-diagnostics-1.0'; available: boolean; target: string;
  local_release_id?: string | null;
  motion_authorized: false; demo_ready: false; start_token: string | null;
  pc: null | { ready: boolean; checked_at_utc: string; checks: { id: string; ok: boolean }[] };
  job: null | { id: string; status: string; phase: string; started_at_utc: string;
    result_code: string | null; saved: boolean; health_status?: string; sensor_status?: string;
    diagnostic?: {code: string; exit_code: number | null} };
  record: RobotReportState['record'];
}
const names: Record<string, string> = { checker_sources: 'Check code', ssh_client: 'SSH executable',
  identity_file: 'Existing identity file', known_hosts_file: 'Existing host record', pc_file_access: 'PC file access' };
const messages: Record<string, string> = {
  SSH_CLIENT_MISSING: 'SSH executable is missing. Nothing was installed automatically.',
  SSH_CONNECTION_REFUSED: 'SSH is not accepting connections yet. The robot may still be booting. Retry when ready.',
  SSH_CONNECT_TIMEOUT: 'SSH did not respond. Check robot power and Wi-Fi, then retry.',
  SSH_NO_ROUTE: 'No network route to the robot. Check robot power and Wi-Fi, then retry.',
  SSH_AUTH_FAILED: 'SSH authentication failed. Check the existing identity; waiting for boot will not fix this.',
  SSH_HOST_KEY_REJECTED: 'SSH host identity was rejected. Verify the robot identity; do not bypass this check.',
  SSH_NAME_RESOLUTION_FAILED: 'Robot address could not be resolved. Check the configured target.',
  SSH_OR_REMOTE_SETUP_FAILED: 'Connection or remote check failed. Check power, network, and existing identity/host records. No automatic retry.',
  CONNECTION_CHECK_TIMEOUT: 'Check timed out. Current state is unknown. No automatic retry.',
  CHECK_FAILED: 'Check response could not be verified.', CHECK_OR_SAVE_FAILED: 'Check result verification or storage failed.',
  OBSERVATION_RECEIVED: 'Status collected — not motion authorization',
  OBSERVATION_NEEDS_ATTENTION: 'Status collected — some items need attention.',
};

export function RobotDiagnostics({ api, compact = false, autoConnect = false, onObservation }: {
  api: TwinPulseApi; compact?: boolean; autoConnect?: boolean;
  onObservation?: (record: RobotDiagnosticsState['record'] | null, localReleaseId: string | null) => void;
}) {
  const [state, setState] = useState<RobotDiagnosticsState | null>(null);
  const [busy, setBusy] = useState(false);
  const [needsRefresh, setNeedsRefresh] = useState(false);
  const [phase, setPhase] = useState('');
  const [error, setError] = useState('');
  const [elapsed, setElapsed] = useState(0);
  const [observedJob, setObservedJob] = useState<string | null>(null);
  const serial = useRef(0);
  const inFlight = useRef(false);
  const autoAttempted = useRef(false);
  const running = state?.job?.status === 'RUNNING';
  const record = state?.record;
  async function perform(kind: 'prepare' | 'read' | 'refresh') {
    if (inFlight.current || running || (kind === 'read' && needsRefresh)) return;
    inFlight.current = true;
    const current = ++serial.current;
    setBusy(true); setError('');
    if (kind === 'read') {
      setObservedJob(null);
      setElapsed(0); setPhase('Checking PC files and connection tools');
      setState(previous => previous ? { ...previous, record: null, job: null, start_token: null } : null);
    }
    try {
      let next;
      if (kind === 'read') {
        next = await api.robotPreflight();
        if (current !== serial.current) return;
        setState({ ...next, record: null, job: null });
        if (!next.pc?.ready || !next.start_token) {
          setError('PC prerequisites are missing; no connection was made. Review the items below.');
          return;
        }
        setPhase('Requesting read-only connection');
        next = await api.startRobotCheck(next.start_token);
        if (current === serial.current) setObservedJob(next.job?.id ?? null);
      } else next = kind === 'prepare' ? await api.robotPreflight() : await api.robotDiagnostics();
      if (current === serial.current) { setState(next); if (kind === 'refresh') setNeedsRefresh(false); }
    } catch {
      if (current === serial.current) {
        setNeedsRefresh(true);
        setState(previous => previous ? { ...previous, start_token: null, record: null } : null);
        setError('App status check failed. Refresh results to determine progress. The command will not be resent automatically.');
      }
    } finally { inFlight.current = false; if (current === serial.current) { setBusy(false); setPhase(''); } }
  }
  useEffect(() => () => { serial.current++; }, []);
  useEffect(() => {
    if (!autoConnect || autoAttempted.current) return;
    // Defer until after StrictMode's effect cleanup so a development remount
    // cannot cancel the one read-only attempt before its POST.
    const timer = window.setTimeout(() => {
      if (autoAttempted.current) return;
      autoAttempted.current = true;
      void perform('read');
    }, 0);
    return () => window.clearTimeout(timer);
  // One bounded attempt per mounted console; refresh/retry is always explicit.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoConnect]);
  useEffect(() => {
    if (!running) return;
    let pending = false, disposed = false;
    const timer = setInterval(async () => {
      setElapsed(Math.max(0, Math.floor((Date.now() - Date.parse(state!.job!.started_at_utc)) / 1000)));
      if (pending) return;
      pending = true;
      const current = ++serial.current;
      try {
        const next = await api.robotDiagnostics();
        if (!disposed && current === serial.current) { setState(next); setError(''); }
      } catch {
        if (!disposed) setError('Progress status was not received. Do not restart the check; wait for the result query.');
      } finally { pending = false; }
    }, 1000);
    return () => { disposed = true; clearInterval(timer); };
  }, [api, running, state?.job?.id]);
  const currentObservation = Boolean(observedJob && state?.job?.id === observedJob &&
    state.job.status === 'COMPLETED' && state.record &&
    ['OBSERVATION_RECEIVED', 'OBSERVATION_NEEDS_ATTENTION'].includes(state.job.result_code ?? ''));
  useEffect(() => { onObservation?.(currentObservation ? record ?? null : null, state?.local_release_id ?? null); }, [currentObservation, record, state?.local_release_id, onObservation]);
  if (compact) {
    const resultCode = state?.job?.result_code;
    const diagnostic = state?.job?.diagnostic;
    const waiting = ['SSH_CONNECTION_REFUSED','SSH_CONNECT_TIMEOUT','SSH_NO_ROUTE'].includes(diagnostic?.code ?? '');
    const status = !autoConnect ? 'Loading local console…' : busy || running ?
      'Checking robot status…' : currentObservation ?
      resultCode === 'OBSERVATION_NEEDS_ATTENTION' ? 'Connected — review robot status' : 'Connected — status received' :
      waiting ? 'Waiting for robot SSH — retry when ready' : error || resultCode ? 'Connection needs attention' : 'Preparing read-only check…';
    return <section className="robot-quick-status" aria-label="Robot connection status">
      <div className="robot-quick-status-line"><div>
        <span className="robot-quick-kicker">01 / READ-ONLY STATUS</span>
        <h2 role="status">{status}</h2>
        <p>{currentObservation ? `Snapshot ${state?.record?.observed_at_utc ?? 'time unknown'} · ${state?.record?.battery ? `${state.record.battery.voltage_v.toFixed(2)} V` : 'battery unverified'}` :
          running ? `Board and existing sensors · ${elapsed}s / 120s maximum` :
          'No motor, sensor start, deployment or driving command is sent by this check.'}</p>
      </div><div className="robot-quick-buttons">
        <button disabled={!autoConnect || busy || running || needsRefresh}
          onClick={() => void perform('read')}>{currentObservation ? 'Check again' : 'Retry connection'}</button>
        <button disabled={busy || running} onClick={() => void perform('refresh')}>Refresh result</button>
      </div></div>
      {(busy || running || waiting) && <p role="status">After power-on, this robot usually needs 2–3 minutes before SSH is ready. This is an estimate, not a live boot measurement. No movement starts automatically.</p>}
      {error && <p role="alert" className="robot-quick-error">{error}</p>}
      {resultCode && !currentObservation && <p role="alert" className="robot-quick-error">
        {messages[diagnostic?.code ?? resultCode] ?? messages[resultCode] ?? resultCode}</p>}
      {needsRefresh && <p>Start response is uncertain. Refresh the saved result before retrying; no command is automatically resent.</p>}
      {currentObservation && <p className="robot-quick-boundary">Observed now: board {record?.board_status ?? 'unknown'} · motor idle {record?.idle_at_observation === true ? 'yes' : 'unverified'}. Movement remains locked until this boot and release pass the separate stop test.</p>}
      {state?.pc && !state.pc.ready && <p role="alert">PC prerequisites failed: {state.pc.checks.filter(item => !item.ok).map(item => names[item.id] ?? item.id).join(', ')}.</p>}
      <details><summary>Technical details and saved observations</summary>
        <p>Target: {state?.target ?? 'twinpulse@192.168.35.139'} · PC checked: {state?.pc?.checked_at_utc ?? 'not checked'}</p>
        {state?.pc && <ul>{state.pc.checks.map(item => <li key={item.id}>{names[item.id] ?? item.id}: {item.ok ? 'Verified' : 'Missing'}</li>)}</ul>}
        {state?.job && <p>Job {state.job.id} · {state.job.status} · {resultCode ?? 'pending'} · saved {state.job.saved ? 'yes' : 'no'}</p>}
        {diagnostic && <p>Error: {diagnostic.code} · SSH exit {diagnostic.exit_code ?? 'unavailable'}</p>}
        {record && <><p>Boot {record.boot_id} · Release {record.release_id ?? 'unknown'} · Board {record.board_status}</p>
          <RobotCheckDetails record={record} healthStatus={state?.job?.health_status} sensorStatus={state?.job?.sensor_status} /></>}
      </details>
    </section>;
  }
  return <section className="robot-report robot-console" aria-label="Robot readiness and checks">
    <h2>Robot readiness and checks</h2>
    <p>One connection click checks PC prerequisites and collects status. Opening this screen does not connect.</p>
    <p>Target: twinpulse@192.168.35.139 · no automatic install, deployment, sensor start, or motor command</p>
    <div className="native-controls">
      <button disabled={busy || running || needsRefresh} onClick={() => void perform('read')}>Connect robot and run bundled check</button>
      <button disabled={busy || running} onClick={() => void perform('refresh')}>Refresh results</button>
    </div>
    <p>PC tools and existing identity → connection → board, battery, deployment, and existing sensor observations. No install, stop test, or movement.</p>
    <details><summary>Check PC only, without robot (optional)</summary>
      <p>Use only for an advance check while charging. A separate click is not required before connection.</p>
      <button disabled={busy || running || needsRefresh} onClick={() => void perform('prepare')}>Check PC only</button>
    </details>
    {state?.pc && <><p>PC checked at: {state.pc.checked_at_utc}</p><ul>{state.pc.checks.map(item =>
      <li key={item.id}>{names[item.id] ?? item.id}: {item.ok ? 'Verified' : 'Missing — action required'}</li>)}</ul>
      <p>Key contents are not read. File presence does not guarantee remote access; host identity is checked again on connection.</p></>}
    {busy && <p role="status">{phase || 'Checking results'}…</p>}
    {running && <p role="status">Collecting connection, board, deployment, and existing sensor status · {elapsed}s / remote check limit 120s · no movement</p>}
    {error && <p role="alert">{error}</p>}
    {state?.job?.result_code && <p role="status">{messages[state.job.result_code] ?? 'Status needs review'} · {state.job.saved ? 'Result saved' : 'Storage unverified'}</p>}
    {state?.job?.sensor_status && <p>Existing sensor reception: {state.job.sensor_status} · No reception is expected if the driver is off.</p>}
    {record ? <div className="native-quality"><h3>This check's observations — not a continuous live connection</h3>
      <p>Observed at: {record.observed_at_utc}</p>
      <p>Board: {record.board_status} · Motor disabled and idle observation: {record.idle_at_observation === null ? 'Unverified' : record.idle_at_observation ? 'Verified' : 'Needs review'}</p>
      <p>{record.battery ? `${record.battery.voltage_v.toFixed(2)} V · voltage-based estimate ${record.battery.estimated_percent.toFixed(1)}%` : 'Battery unverified'}</p>
      <p>This is not a measured state of charge. The charging threshold is an estimated 20%; board protection takes priority.</p>
      {record.battery?.charge_requested_at_observation && <p>Charging threshold reached.</p>}
      {record.battery?.near_protection_at_observation && <p>Near the board's voltage protection threshold. Do not drive.</p>}
      <p>Boot ID: {record.boot_id}<br />Deployment release: {record.release_id ?? 'Unverified'}</p>
      <RobotCheckDetails record={record} healthStatus={state?.job?.health_status} sensorStatus={state?.job?.sensor_status} />
    </div> : <p>Current battery and motor state are unverified. Do not treat a saved report as current data.</p>}
    <p className="native-warning">This check only observes. Stop verification must be checked separately for the current boot and deployment in the control panel; this result does not authorize movement. Measured coordinate alignment and physical autonomous mission integration are incomplete.</p>
  </section>;
}
