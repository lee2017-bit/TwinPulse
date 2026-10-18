// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PresentationReview } from "./PresentationReview";
import type { TwinPulseApi } from "./api";
import type { PresentationState, WorkflowState } from "./types";

const presentation: PresentationState = {
  schema_version: 1, view: "auto", lighting: "balanced", saved: false,
  source_scene_revision: "r".repeat(64), applies_on_next_build: true,
};

describe("PresentationReview", () => {
  it("saves explicit view and lighting for the next Build", async () => {
    const next = { presentation: { ...presentation, view: "top", lighting: "soft", saved: true } } as WorkflowState;
    const savePresentation = vi.fn(async () => next);
    const onSaved = vi.fn();
    render(<PresentationReview api={{ savePresentation } as unknown as TwinPulseApi}
      presentation={presentation} disabled={false} onSaved={onSaved} />);
    expect(screen.getByText(/apply on the next Isaac Build/)).toBeTruthy();
    expect((screen.getByRole("button", { name: "Save view settings" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Camera direction"), { target: { value: "top" } });
    fireEvent.change(screen.getByLabelText("Lighting"), { target: { value: "soft" } });
    fireEvent.click(screen.getByRole("button", { name: "Save view settings" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(next));
    expect(savePresentation).toHaveBeenCalledWith(presentation.source_scene_revision, "top", "soft");
  });
});
