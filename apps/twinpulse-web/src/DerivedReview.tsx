// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { useState } from "react";
import type { TwinPulseApi } from "./api";
import type { WorkflowState } from "./types";

export function DerivedReview({ api, workflow, workspaceRevision, hasEdits, disabled, onWorkflow }: {
  api: TwinPulseApi; workflow: WorkflowState; workspaceRevision?: string; hasEdits: boolean;
  disabled: boolean; onWorkflow: (state: WorkflowState) => void;
}) {
  const [reviewed, setReviewed] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const draft = workflow.site_draft;
  const eligible = workflow.phase === "draft_ready" && draft && workflow.input?.revision === draft.input_revision;
  async function select(restore: boolean) {
    if (!eligible || !draft || !reviewed) return;
    setBusy(true); setError(""); setReviewed(false);
    try {
      const source = draft.original_scene_revision ?? draft.revision;
      const next = restore ? await api.restoreDerivedReview(draft.input_revision, source)
        : await api.adoptDerivedReview(draft.input_revision, source, workspaceRevision!);
      onWorkflow(next);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Derived review selection failed.");
      // A failed server-side adoption clears acknowledgement; refresh the card too.
      try { onWorkflow(await api.workflow()); } catch { /* existing App polling handles disconnect */ }
    } finally { setBusy(false); }
  }
  return <section role="region" aria-label="Derived scene selection">
    <h3>Select an offline-derived scene</h3>
    <p>The original generated draft is retained. This selects a separate, unverified geometry review; it does not build in Isaac, establish a real-world coordinate frame, or enable Run. Review the new scene card again before Build.</p>
    {!eligible && <p>Select the matching original site-plan input before adopting a review.</p>}
    <label><input type="checkbox" checked={reviewed} disabled={!eligible || disabled || busy}
      onChange={e => setReviewed(e.target.checked)} />I want to select a separate unverified scene and review it again before Build.</label>
    <button disabled={!eligible || disabled || busy || !reviewed || !workspaceRevision || !hasEdits}
      onClick={() => void select(false)}>Select scratch edits as scene draft</button>
    <button disabled={!eligible || disabled || busy || !reviewed}
      onClick={() => void select(true)}>Restore saved derived scene for review</button>
    {error && <p role="alert">{error}</p>}
  </section>;
}
