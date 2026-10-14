// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { useState } from "react";
import type { TwinPulseApi } from "./api";

export interface RobotReportState {
  schema_version: "robot-report-review-1.0";
  session_id: string;
  connection: "NOT_CONNECTED";
  motion_authorized: false;
  demo_ready: false;
  notice: string;
  blockers: string[];
  record: null | {
    boot_id: string; release_id: string | null; report_sha256: string;
    observed_at_utc: string; age_seconds: number; board_status: string;
    idle_at_observation: boolean | null;
    guard_artifact_verified_at_observation?: boolean;
    idle_failure_reasons?: string[];
    board_observation?: null | { observed_at_utc: string; torque_enabled: boolean;
      wheel_velocity_raw: [number, number]; command_bytes_zero: boolean; port_restored: boolean };
    battery: null | { voltage_v: number; estimated_percent: number; observed_at_utc: string;
      charge_requested_at_observation: boolean; near_protection_at_observation: boolean };
  };
}

export function RobotReport({ api }: { api: TwinPulseApi }) {
  const [state, setState] = useState<RobotReportState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function importFile(file: File | undefined) {
    if (!file) return;
    setBusy(true); setError(null);
    try {
      if (file.size > 256 * 1024) throw new Error("Report exceeds 256 KiB.");
      setState(await api.importRobotReport(JSON.parse(await file.text())));
    } catch {
      setError("Report could not be imported. Use a read-only robot-health-1.0 report with UTC timestamps and boot ID.");
    } finally { setBusy(false); }
  }
  async function refresh() {
    setBusy(true); setError(null);
    try { setState(await api.robotReport()); }
    catch { setError("Saved report unavailable. Reopen TwinPulse if the app session expired."); }
    finally { setBusy(false); }
  }
  const record = state?.record;
  return <details className="robot-report">
    <summary>Robot status · Saved diagnostics</summary>
    <p>Not connected · Physical movement unavailable</p>
    <p>Review a saved report without contacting the robot. Importing a report does not approve motion or make the demo ready.</p>
    <label>Import robot report (JSON)<input aria-label="Import robot report (JSON)" type="file" accept=".json,application/json"
      disabled={busy} onChange={(event) => { void importFile(event.target.files?.[0]); event.target.value = ""; }} /></label>
    <button disabled={busy} onClick={() => void refresh()}>Refresh saved report</button>
    {busy && <p role="status">Reading saved diagnostics…</p>}
    {error && <p role="alert">{error}</p>}
    {!record && <p>No saved robot report loaded. Current battery and robot state are unknown.</p>}
    {record && <>
      <h3>Historical measurement — not live</h3>
      <p>Observed: {record.observed_at_utc} · {record.age_seconds}s old when retrieved</p>
      <p>Board: {record.board_status} · Idle at observation: {record.idle_at_observation === null ? "Unknown" : record.idle_at_observation ? "Yes" : "No"}</p>
      <p>{record.battery ? `${record.battery.voltage_v.toFixed(2)} V · estimated ${record.battery.estimated_percent.toFixed(1)}% at observation` : "Battery measurement unavailable"}</p>
      <p>Voltage estimate, not measured capacity. Charge target: estimated 20%; board protection may activate earlier.</p>
      {record.battery?.charge_requested_at_observation && <p>Charging was requested at observation.</p>}
      {record.battery?.near_protection_at_observation && <p>Voltage was near the board protection range.</p>}
      <p>Boot: {record.boot_id}<br />Release: {record.release_id ?? "Not recorded"}</p>
      <p>Imported file is unverified evidence. A new live check is required after power-on.</p>
    </>}
    <p>Still required: deployment and stationary check; stopping qualification; LiDAR/coordinates; scan-to-twin and route comparison.</p>
  </details>;
}
