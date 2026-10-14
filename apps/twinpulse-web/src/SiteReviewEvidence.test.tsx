// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SiteReviewEvidence } from "./SiteReviewEvidence";
import type { SiteReviewProvenance } from "./types";

describe("SiteReviewEvidence", () => {
  it("labels a local recipe and user edit without claiming photo or physical validation", () => {
    const evidence: SiteReviewProvenance = {
      schema_version: "site-review-provenance-1.0", source_class: "local_recipe",
      provider_name: "local-room-recipe", model_id: "no-provider-call", input_kind: "photo",
      input_revision: "a".repeat(64), source_plan_sha256: "b".repeat(64),
      original_scene_revision: "c".repeat(64), current_scene_revision: "d".repeat(64),
      local_edit_count: 1, photo_interpretation_evidence: "local_import_not_performed", world_alignment: "NOT_VERIFIED",
      physical_validation: "NOT_RUN", calls: [
        { call_id: "chair", tool: "place_furniture", origin: "user_local_edit",
          basis: "user", observation_ids: [] },
      ],
    };
    render(<SiteReviewEvidence evidence={evidence} />);
    expect(screen.getByText(/TwinPulse did not analyze the photo or call a model during this import/)).toBeTruthy();
    expect(screen.getByText(/Real-room coordinate alignment: not verified/)).toBeTruthy();
    expect(screen.getByText(/physics\/physical validation: not run/)).toBeTruthy();
  });
});
