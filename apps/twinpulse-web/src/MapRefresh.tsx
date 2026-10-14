// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { useState } from "react";

export interface MapPreview {
  revision: string; added_occupied_cells: number; freed_cells: number;
  free_cells: number; unknown_cells: number; occupied_cells: number;
  start_xy_m: number[]; goal_xy_m: number[]; map_revision: string; notice: string;
}

export function MapRefresh({ available, proposal, applied, busy, preview, apply }: {
  available: boolean; proposal: MapPreview | null; applied: MapPreview | null;
  busy: boolean; preview: () => void; apply: (revision: string) => void;
}) {
  const [reviewed, setReviewed] = useState(false);
  if (!available && !proposal && !applied) return null;
  return <section aria-label="Conservative map review">
    <h3>Conservative map and mission review</h3>
    <p>Keep the imported grid and add old/new static box footprints as occupied. No cells become free. This is not SLAM, a full rebuild or verified free space.</p>
    {available && <button disabled={busy} onClick={() => { setReviewed(false); preview(); }}>Preview conservative map overlay</button>}
    {proposal && <>
      <p>Proposed map {proposal.map_revision.slice(0, 12)}: {proposal.added_occupied_cells} added occupied cells,
        {" "}{proposal.unknown_cells} unknown, {proposal.free_cells} inherited free cells; {proposal.freed_cells} freed.</p>
      <p>Rebind the same start [{proposal.start_xy_m.join(", ")}] and goal [{proposal.goal_xy_m.join(", ")}] m to this scene and map for offline comparison.</p>
      <label><input type="checkbox" checked={reviewed} disabled={busy} onChange={e => setReviewed(e.target.checked)} />I reviewed this map overlay and these endpoints for offline comparison only.</label>
      <button disabled={busy || !reviewed} onClick={() => { setReviewed(false); apply(proposal.revision); }}>Use reviewed map in scratch draft</button>
    </>}
    {applied && <p>Conservative overlay applied — unverified. Old obstacle areas remain blocked. A new comparison is required; no motion approval.</p>}
  </section>;
}
