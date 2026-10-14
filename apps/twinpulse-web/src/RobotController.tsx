// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { useEffect, useRef, useState } from 'react';
import type { TwinPulseApi } from './api';
import { PhysicalRobotController } from './PhysicalRobotController';
import { driveDirection, driveKeyBlocked } from './driveKeys';

export interface ManualControllerState {
  mode: 'PC_REHEARSAL_ONLY'; physical_motion_authorized: false; physical_lidar_authorized: false;
  physical_blockers: string[]; session_id: string | null; owned: boolean; armed: boolean;
  sequence: number; linear_m_s: number; angular_rad_s: number;
  pose: { x_m: number; y_m: number; yaw_rad: number };
  lidar_running: boolean; lidar_remaining_s: number; reason: string;
}
const reasons: Record<string, string> = { NOT_STARTED: 'Rehearsal awaiting start', ARMED_REHEARSAL: 'Rehearsal controls ready',
  HELD_INPUT: 'Simulated motion while held', OPERATOR_STOP: 'Simulated output stopped', INPUT_EXPIRED: 'Input expired — stop and re-arm required',
  STALE_INPUT: 'Delayed input rejected — stop and re-arm required', SESSION_EXPIRED: '60-second session ended',
  LIDAR_REHEARSAL: 'Simulated lidar running', LIDAR_TIME_LIMIT: '8-second simulated lidar ended', CONSOLE_CLOSED: 'Console closed' };

export function RobotController({ api, backendReady=true, physicalProjectAllowed=true }:
  { api: TwinPulseApi; backendReady?:boolean; physicalProjectAllowed?:boolean }) {
  const [mode, setMode] = useState<'physical' | 'rehearsal'>('physical');
  const [confirmed, setConfirmed] = useState(false);
  const [state, setState] = useState<ManualControllerState | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [held, setHeld] = useState<string | null>(null);
  const live = useRef<ManualControllerState | null>(null);
  const sequence = useRef(0);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const down = useRef<string | null>(null);
  const mounted = useRef(true);
  const panel = useRef<HTMLElement>(null);
  const enabled = mode === 'rehearsal' && Boolean(state?.owned && state?.armed) && !busy && !error;
  useEffect(() => { if (enabled) panel.current?.focus({ preventScroll: true }); }, [enabled]);
  function apply(next: ManualControllerState, newSession = false) {
    if (!mounted.current) return;
    if (!newSession && next.session_id !== live.current?.session_id) return;
    if (!newSession && next.sequence < (live.current?.sequence ?? 0)) return;
    live.current = next; setState(next);
  }
  function clearHold() {
    down.current = null;
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
    if (mounted.current) setHeld(null);
  }
  async function send(action: string) {
    const current = live.current;
    if (!current?.session_id) return;
    const nextSequence = ++sequence.current;
    try { apply(await api.controllerInput(current.session_id, nextSequence, action)); }
    catch {
      if (current.session_id !== live.current?.session_id || nextSequence < sequence.current) return;
      clearHold();
      if (mounted.current) setError('Rehearsal connection is unverified. Input transmission stopped. Server input expiry stops simulated output, not a physical robot.');
    }
  }
  function stop(all = false) { clearHold(); void send(all ? 'stop_all' : 'stop'); }
  function press(direction: string) {
    if (!enabled || down.current) return;
    down.current = direction; setHeld(direction);
    void send(direction);
    timer.current = setInterval(() => { if (down.current) void send(down.current); }, 100);
  }
  async function start() {
    if (!confirmed || busy) return;
    clearHold(); setBusy(true); setError('');
    try {
      const next = await api.beginController();
      sequence.current = next.sequence; apply(next, true); setConfirmed(false);
    } catch { setError('Could not start the rehearsal session. No automatic retry.'); }
    finally { setBusy(false); }
  }
  useEffect(() => {
    mounted.current = true;
    const blur = () => stop(true);
    const hidden = () => { if (document.visibilityState !== 'visible') stop(true); };
    window.addEventListener('blur', blur); window.addEventListener('pagehide', blur);
    document.addEventListener('visibilitychange', hidden);
    return () => {
      mounted.current = false; clearHold();
      const current = live.current;
      if (current?.session_id) void api.controllerInput(current.session_id, ++sequence.current, 'close').catch(() => {});
      window.removeEventListener('blur', blur); window.removeEventListener('pagehide', blur);
      document.removeEventListener('visibilitychange', hidden);
    };
  }, [api]);
  useEffect(() => {
    if (!state?.armed) { clearHold(); return; }
    let pending = false, disposed = false;
    const id = setInterval(async () => {
      if (pending) return;
      pending = true;
      try { const next = await api.controllerState(); if (!disposed) apply(next); }
      catch { if (!disposed) { stop(true); setError('Could not read rehearsal status. Controls stopped.'); } }
      finally { pending = false; }
    }, 150);
    return () => { disposed = true; clearInterval(id); };
  }, [api, state?.armed, state?.session_id]);
  return <section ref={panel} className="robot-report manual-controller" aria-label="Virtual controller" tabIndex={0}
    onBlur={event => { if (enabled && !event.currentTarget.contains(event.relatedTarget as Node | null)) stop(true); }}
    onKeyDown={event => {
      if (mode !== 'rehearsal') return;
      if (event.key === 'Escape') { event.preventDefault(); stop(true); return; }
      if (driveKeyBlocked(event)) return;
      const action = driveDirection(event);
      if (action && enabled) { event.preventDefault(); if (!event.repeat) press(action); }
    }} onKeyUp={event => { const action = driveDirection(event); if (mode === 'rehearsal' && action && down.current === action) { event.preventDefault(); stop(); } }}>
    <h2>Virtual controller</h2>
    <div className="native-controls">
      <button aria-pressed={mode === 'physical'} onClick={() => { stop(true); setMode('physical'); setConfirmed(false); }}>Physical control</button>
      <button aria-pressed={mode === 'rehearsal'} onClick={() => { stop(true); setMode('rehearsal'); setConfirmed(false); }}>PC rehearsal</button>
    </div>
    {mode === 'physical' ? <>{!physicalProjectAllowed &&
      <p role="status" className="native-warning">Physical control is locked for this project. Project-bound saved history can be reviewed, but it never enables robot motion. Only PC rehearsal is available.</p>}
      <PhysicalRobotController api={api} backendReady={backendReady && physicalProjectAllowed} historyReady={backendReady}/></> : <>
      <p className="native-warning">PC rehearsal does not connect to the robot, ROS, serial, or Isaac. Pose, velocity, and lidar below are synthetic.</p>
      <label><input type="checkbox" checked={confirmed} disabled={busy || Boolean(state?.armed)}
        onChange={event => setConfirmed(event.target.checked)} /> I understand that PC rehearsal sends no commands to the physical robot.</label>
      <button disabled={!confirmed || busy || Boolean(state?.armed)} onClick={() => void start()}>Prepare rehearsal controls</button>
    <div className="controller-pad">
      {([['forward', '↑ Forward'], ['left', '↶ Turn left'], ['right', '↷ Turn right'], ['backward', '↓ Backward']] as const).map(([action, label]) =>
        <button key={action} className={`controller-${action}`} disabled={!enabled} aria-pressed={held === action}
          onPointerDown={event => { if (event.button !== 0) return; event.preventDefault(); event.currentTarget.setPointerCapture?.(event.pointerId); press(action); }}
          onPointerUp={() => { if (down.current === action) stop(); }}
          onPointerCancel={() => stop(true)} onLostPointerCapture={() => { if (down.current === action) stop(); }}
          onContextMenu={event => event.preventDefault()}>{label}</button>)}
      <button className="controller-stop" onClick={() => stop(true)}>Stop rehearsal · Esc</button>
    </div>
    <p>Hold to move · W/S or ↑/↓ drives forward/backward · A/D or ←/→ rotates in place (not sideways translation).
      Simulated input expires within 350 ms; each hold lasts at most 2 seconds and a session lasts 60 seconds. Window blur or touch cancel stops the rehearsal. These are not physical robot stop guarantees.</p>
    <div className="native-controls">
      <button disabled={!enabled || Boolean(state?.lidar_running)} onClick={() => void send('lidar_start')}>Start lidar · 8-second simulation</button>
      <button disabled={mode !== 'rehearsal' || !state?.session_id} onClick={() => void send('lidar_stop')}>Stop simulated lidar</button>
    </div>
    {mode === 'rehearsal' && state && <div className="native-quality" aria-label="Simulated output">
      <p role="status">{reasons[state.reason] ?? 'Rehearsal status needs review'}</p>
      <p>Synthetic velocity: {state.linear_m_s.toFixed(2)} m/s · {state.angular_rad_s.toFixed(2)} rad/s</p>
      <p>Synthetic pose: X {state.pose.x_m.toFixed(3)} m · Y {state.pose.y_m.toFixed(3)} m · heading {(state.pose.yaw_rad * 180 / Math.PI).toFixed(1)}°</p>
      <p>Synthetic lidar: {state.lidar_running ? `running (${state.lidar_remaining_s.toFixed(1)}s remaining)` : 'stopped'}</p>
    </div>}
    {error && <p role="alert">{error}</p>}
    <p>Stopping the rehearsal is not a physical emergency stop. Physical connection requires separate on-site validation after stop verification and control integration.</p>
    </>}
  </section>;
}
