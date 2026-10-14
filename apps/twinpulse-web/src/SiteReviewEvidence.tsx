// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import type { SiteReviewProvenance } from "./types";

const basisLabel: Record<SiteReviewProvenance["calls"][number]["basis"], string> = {
  visual: "Recorded visual claim",
  user: "User input",
  inferred: "Inference",
  trusted_measurement: "Recorded measurement evidence — field verification separate",
  unprovided: "No per-call evidence recorded",
};

export function SiteReviewEvidence({ evidence }: { evidence: SiteReviewProvenance }) {
  const local = evidence.source_class === "local_recipe";
  return <div className="panel site-review-evidence" role="region" aria-label="Scene source and validation scope">
    <h3>Scene provenance</h3>
    <p>{local ? "A local room recipe was imported. TwinPulse did not analyze the photo or call a model during this import. How the recipe was originally authored is separate."
      : "This is a saved provider or test plan. The displayed provider name alone does not prove that a model was called in this session or that the photo content is accurate."}</p>
    <p className="fine">Source plan {evidence.source_plan_sha256.slice(0, 12)} · source input {evidence.input_revision.slice(0, 12)} · local edits {evidence.local_edit_count}</p>
    <p className="fine">Real-room coordinate alignment: not verified · physics/physical validation: not run</p>
    <details>
      <summary>Review per-tool-call evidence ({evidence.calls.length})</summary>
      <ul>
        {evidence.calls.map((call) => <li key={call.call_id}>
          <code>{call.tool}</code> · {call.origin === "user_local_edit" ? "User edit in this project" : "Source plan"} · {basisLabel[call.basis]}
          {call.observation_ids.length > 0 && <> · observation IDs {call.observation_ids.join(", ")}</>}
        </li>)}
      </ul>
      <p className="fine">These records describe provenance. An observation ID or description alone does not prove measurement accuracy or collision safety.</p>
    </details>
  </div>;
}
