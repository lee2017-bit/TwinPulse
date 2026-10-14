// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { useState } from "react";

export interface RouteConditions {
  revision: string; map_revision: string; profile_digest: string;
  start_xy_m: number[]; goal_xy_m: number[]; inflation_m: number; clearance_m: number;
}
interface RouteResult {
  route_id: string; provenance: string; points_xy_m: number[][]; length_m: number;
  internal_turn_angle_rad: number; grid_check: { status: string; reason: string };
}
export interface ComparisonResult {
  baseline: RouteResult; candidate: RouteResult; comparable: boolean; shorter_route_id: string | null;
  candidate_length_reduction_percent: number | null;
}

export function RouteComparison({ conditions, result, reason, busy, compare }: {
  conditions: RouteConditions | null; result: ComparisonResult | null;
  reason: string | null; busy: boolean; compare: (baseline: string, candidate: string) => void;
}) {
  const [baseline, setBaseline] = useState("[]"), [candidate, setCandidate] = useState("[]");
  const [dirty, setDirty] = useState(false);
  return <section aria-label="Offline route comparison">
    <h3>Same-condition route comparison</h3>
    <p>Two manually supplied polylines, not generated or optimized routes. Geometry only; no timing, controller, Isaac or physical validation.</p>
    {!conditions ? <p>Comparison unavailable: {reason ?? "Matching map, mission and registered profile required."}</p> : <>
      <p>Same start [{conditions.start_xy_m.join(", ")}] and goal [{conditions.goal_xy_m.join(", ")}] m.
        Footprint + clearance: {conditions.inflation_m.toFixed(3)} m; fixed clearance {conditions.clearance_m.toFixed(2)} m.</p>
      <p>Map {conditions.map_revision.slice(0, 12)} · Profile {conditions.profile_digest.slice(0, 12)} · Conditions {conditions.revision.slice(0, 12)}</p>
      <label>Baseline XY points (JSON)<textarea rows={3} value={baseline} disabled={busy}
        onChange={e => { setBaseline(e.target.value); setDirty(true); }} /></label>
      <label>Candidate XY points (JSON)<textarea rows={3} value={candidate} disabled={busy}
        onChange={e => { setCandidate(e.target.value); setDirty(true); }} /></label>
      <p>Each route: 2–128 points [[x, y], …], metres. Include the exact mission start and goal. Unknown cells and the outside of the supplied map are not free space.</p>
      <button disabled={busy} onClick={() => { setDirty(false); compare(baseline, candidate); }}>Compare supplied routes</button>
    </>}
    {result && !dirty && <>
      <p>Saved comparison — unverified inputs. No execution authority.</p>
      {[result.baseline, result.candidate].map(route => <div key={route.route_id}>
        <h4>{route.route_id} · {route.provenance}</h4>
        <p>Length {route.length_m.toFixed(3)} m · Internal turns {route.internal_turn_angle_rad.toFixed(3)} rad</p>
        <p>{route.grid_check.status}: {route.grid_check.reason}</p>
        <p>Evaluated points: {JSON.stringify(route.points_xy_m)}</p>
      </div>)}
      <p>{result.comparable
        ? `Shorter geometric route: ${result.shorter_route_id}; candidate length reduction ${result.candidate_length_reduction_percent!.toFixed(2)}%.`
        : "Not comparable: no shorter-route winner or improvement claim."}</p>
      <p>Supplied grid only. Conservative footprint checks may reject feasible corner paths. No physical time or collision improvement measured.</p>
    </>}
    {result && dirty && <p>Inputs changed. Compare again to replace the saved result; export still contains the previous evaluated points.</p>}
  </section>;
}
