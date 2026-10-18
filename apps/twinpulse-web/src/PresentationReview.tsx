// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { useEffect, useState } from "react";
import type { PresentationState, WorkflowState } from "./types";
import { TwinPulseApi } from "./api";

const views: { value: PresentationState["view"]; label: string }[] = [
  { value: "auto", label: "Auto fit" }, { value: "front", label: "Front" },
  { value: "back", label: "Back" }, { value: "left", label: "Left" },
  { value: "right", label: "Right" }, { value: "top", label: "Top" },
];
const lights: { value: PresentationState["lighting"]; label: string }[] = [
  { value: "balanced", label: "Balanced" }, { value: "soft", label: "Soft" },
  { value: "bright", label: "Bright" },
];

export function PresentationReview({ api, presentation, disabled, onSaved }: {
  api: TwinPulseApi;
  presentation: PresentationState;
  disabled: boolean;
  onSaved: (workflow: WorkflowState) => void;
}) {
  const [view, setView] = useState(presentation.view);
  const [lighting, setLighting] = useState(presentation.lighting);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setView(presentation.view);
    setLighting(presentation.lighting);
    setError(null);
  }, [presentation.source_scene_revision, presentation.view, presentation.lighting]);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const next = await api.savePresentation(presentation.source_scene_revision, view, lighting);
      onSaved(next);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save the view settings.");
    } finally {
      setSaving(false);
    }
  }

  const changed = view !== presentation.view || lighting !== presentation.lighting;
  return <div className="panel presentation-review">
    <h3>3D view settings</h3>
    <p>Choose camera and lighting without changing the saved room geometry. These settings apply on the next Isaac Build, not immediately to the open scene.</p>
    <div className="presentation-fields">
      <label>Camera direction
        <select aria-label="Camera direction" value={view} disabled={disabled || saving} onChange={(event) => setView(event.target.value as PresentationState["view"])}>
          {views.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
        </select>
      </label>
      <label>Lighting
        <select aria-label="Lighting" value={lighting} disabled={disabled || saving} onChange={(event) => setLighting(event.target.value as PresentationState["lighting"])}>
          {lights.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
        </select>
      </label>
      <button type="button" disabled={disabled || saving || !changed} onClick={() => void save()}>{saving ? "Saving…" : "Save view settings"}</button>
    </div>
    <p className="fine" role="status">{presentation.saved ? "Saved to this project" : "Default settings"} · This does not verify the photo orientation or robot coordinate frame.</p>
    {error && <p role="alert" className="error">{error}</p>}
  </div>;
}
