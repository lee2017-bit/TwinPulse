// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { useEffect, useRef, useState } from 'react';
import { TwinPulseApi } from './api';
import { RobotDiagnostics } from './RobotDiagnostics';
import { PhysicalRobotController } from './PhysicalRobotController';
import type { RobotDiagnosticsState } from './RobotDiagnostics';

const consoleApi = new TwinPulseApi();

/** Bootstrap the dedicated console without waiting for Isaac or product workflow state. */
export function RobotConsoleEntry({ api = consoleApi }: { api?: TwinPulseApi }) {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState('');
  const bootstrap = useRef<Promise<void> | null>(null);
  function connectLocalApp() {
    if (!bootstrap.current) bootstrap.current = api.bootstrap();
    void bootstrap.current.then(() => { setReady(true); setError(''); }).catch((reason: unknown) => {
      setReady(false);
      setError(reason instanceof Error ? reason.message : 'Local console session could not open.');
    });
  }
  useEffect(() => { connectLocalApp(); }, [api]);
  return ready ? <RobotQuickConsole api={api} /> : <main className="robot-quick-shell">
    <h1>Robot console</h1>
    {error ? <><p role="alert">Local console unavailable: {error}</p>
      <button onClick={() => { bootstrap.current = null; connectLocalApp(); }}>Retry local console</button></> :
      <p role="status">Opening local console…</p>}
  </main>;
}

/** Dedicated robot-console launcher view: observation is automatic, motion is not. */
export function RobotQuickConsole({ api }: { api: TwinPulseApi }) {
  const [observed, setObserved] = useState<RobotDiagnosticsState['record']>(null);
  const [localReleaseId, setLocalReleaseId] = useState<string | null>(null);
  return <main className="robot-quick-shell" aria-label="Robot quick console">
    <header className="robot-quick-header">
      <span className="robot-quick-kicker">TWINPULSE / ROBOT CONSOLE</span>
      <h1>Robot control</h1>
      <p>Connection status checks automatically. Motion never starts automatically.</p>
    </header>
    <RobotDiagnostics api={api} compact autoConnect onObservation={(record, release) => { setObserved(record); setLocalReleaseId(release); }} />
    {observed ? <section className="robot-quick-control" aria-label="Manual drive after read-only check">
      <h2>Manual drive</h2>
      <PhysicalRobotController api={api} backendReady historyReady compact observedRobot={observed} localReleaseId={localReleaseId} />
    </section> : <p className="robot-quick-wait" role="status">
      Manual controls appear after a fresh status observation. A connection failure never unlocks movement.
    </p>}
  </main>;
}
