// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { TwinPulseApi } from "./api";
import { NativeScanReview, displayPoint, type NativeScanState } from "./NativeScanReview";

function state(): NativeScanState {
  return { workspace_revision: "rev1", notice: "Historical native evidence", mode: "saved_native_evidence_only",
    active_project_changed: false, motion_authorized: false, demo_ready: false, source_bytes_verified: false,
    world_tf: null, robot_heading: null, handedness_verified: false, physical_validation: "NOT_RUN",
    bundle: { digest: "digest", frame_count: 2, sample_count: 8,
      source: { kind: "synthetic_test_fixture", raw_sha256: "a".repeat(64), nodes_sha256: "b".repeat(64),
        observation_start_utc: "2026-09-27T03:13:54Z", observation_end_utc: "2026-09-27T03:14:05Z", timestamp_basis: "host_observation_window_not_beam_time" },
      photos: [{ role: "top_view", sha256: "c".repeat(64), media_type: "image/jpeg", same_position_user_declared: false, window_direction: "up" }],
      display_hypotheses: [{ id: "mirror1", rotation_deg: 90, mirror_native_y: true }] },
    frame: { index: 1, samples: 4, invalid_returns: 3,
      points: [{ angle_deg: 0, distance_m: 1, quality: 100, node_index: 8, source_byte_cursor: 123, x_m: 1, y_m: 0 }] } };
}

describe("saved native scan review", () => {
  it("displays a reference fit as a proposal, never verified TF or a motion action", async () => {
    const value = state();
    value.registration = { proposal_digest: "p".repeat(64), frame_index: 1, notice: "No TF or navigation approval.",
      reference_kind: "synthetic_test_fixture", reference_sha256: "r".repeat(64), scene_revision: "s".repeat(64),
      fit_status: "UNIQUE_CANDIDATE", candidate_native_y_sign: -1, world_alignment_verified: false,
      candidates: [{ native_y_sign: -1, fit_pass: true, max_residual_m: .001, rms_residual_m: .001,
        rigid_transform: { x_m: 2, y_m: -1, yaw_rad: .4 } }] };
    const api = { nativeScan: vi.fn().mockResolvedValue(state()), proposeNativeRegistration: vi.fn().mockResolvedValue(value) };
    render(<NativeScanReview api={api as unknown as TwinPulseApi} />);
    fireEvent.click(screen.getByText("Refresh native evidence"));
    const input = await screen.findByLabelText("Import coordinate reference JSON");
    const file = new File(["{}"], "reference.json", { type: "application/json" });
    Object.defineProperty(file, "text", { value: async () => "{}" });
    fireEvent.change(input, { target: { files: [file] } });
    await waitFor(() => expect(api.proposeNativeRegistration).toHaveBeenCalledWith("rev1", 1, "{}"));
    expect(await screen.findByText("Reference fit: UNIQUE_CANDIDATE")).toBeTruthy();
    expect(screen.getByText(/SYNTHETIC reference/)).toBeTruthy();
    expect(screen.getByText(/No proposal is applied/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /run|drive|apply/i })).toBeNull();
  });
  it("3D export binds selected frame and revision, rejects failure without discarding data", async () => {
    const api = { nativeScan: vi.fn().mockResolvedValue(state()), exportNative3D: vi.fn().mockRejectedValue(new Error("stale evidence")) };
    render(<NativeScanReview api={api as unknown as TwinPulseApi} />);
    expect((screen.getByText("Export selected frame to 3D (USD)") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByText("Refresh native evidence"));
    await screen.findByText("SYNTHETIC native fixture");
    fireEvent.change(screen.getByLabelText("Display orientation (not calibration)"), { target: { value: "mirror1" } });
    fireEvent.click(screen.getByText("Export selected frame to 3D (USD)"));
    await waitFor(() => expect(api.exportNative3D).toHaveBeenCalledWith("rev1", 1));
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "stale evidence");
    expect(screen.getByText(/Frame 2: 4 samples/)).toBeTruthy();
    expect(screen.getByText(/3D export uses native axes only/)).toBeTruthy();
  });
  it("does not connect, fetch or import automatically", () => {
    const api = { nativeScan: vi.fn() };
    render(<NativeScanReview api={api as unknown as TwinPulseApi} />);
    expect(api.nativeScan).not.toHaveBeenCalled();
    expect(screen.getByText(/No robot connection, active project edits or drive controls/)).toBeTruthy();
    expect((screen.getByText("Export preserved native bundle") as HTMLButtonElement).disabled).toBe(true);
  });
  it("labels synthetic data, missing returns and photo direction without heading claims", async () => {
    const api = { nativeScan: vi.fn().mockResolvedValue(state()) };
    render(<NativeScanReview api={api as unknown as TwinPulseApi} />);
    fireEvent.click(screen.getByText("Refresh native evidence"));
    await waitFor(() => expect(screen.getByText("SYNTHETIC native fixture")).toBeTruthy());
    expect(screen.getByRole("img", { name: "Saved native scan points, not a navigation map" })).toBeTruthy();
    expect(screen.getByText(/Photo-up = window.*Not robot-forward/)).toBeTruthy();
    expect(screen.getByText(/4 samples · 1 usable · 3 excluded/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /run|drive|apply/i })).toBeNull();
  });
  it("keeps display reflection client-only and defaults to native", async () => {
    const api = { nativeScan: vi.fn().mockResolvedValue(state()), nativeScanFrame: vi.fn() };
    render(<NativeScanReview api={api as unknown as TwinPulseApi} />);
    fireEvent.click(screen.getByText("Refresh native evidence"));
    const select = await screen.findByLabelText("Display orientation (not calibration)") as HTMLSelectElement;
    expect(select.value).toBe("native");
    fireEvent.change(select, { target: { value: "mirror1" } });
    expect(screen.getByText(/DISPLAY HYPOTHESIS ONLY/)).toBeTruthy();
    expect(api.nativeScanFrame).not.toHaveBeenCalled();
    expect(displayPoint(1, 2)).toEqual([1, 2]);
    const reflected = displayPoint(1, 2, { id: "mirror1", rotation_deg: 90, mirror_native_y: true });
    expect(reflected[0]).toBeCloseTo(2); expect(reflected[1]).toBeCloseTo(1);
  });
  it("sends exact revision for frame selection and retains old data on stale rejection", async () => {
    const api = { nativeScan: vi.fn().mockResolvedValue(state()), nativeScanFrame: vi.fn().mockRejectedValue(new Error("native evidence changed")) };
    render(<NativeScanReview api={api as unknown as TwinPulseApi} />);
    fireEvent.click(screen.getByText("Refresh native evidence"));
    await screen.findByText("SYNTHETIC native fixture");
    fireEvent.click(screen.getByText("Previous saved frame"));
    await waitFor(() => expect(api.nativeScanFrame).toHaveBeenCalledWith("rev1", 0));
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "native evidence changed");
    expect(screen.getByText(/Frame 2: 4 samples/)).toBeTruthy();
  });
  it("rejects oversize JSON before transport", async () => {
    const api = { importNativeScan: vi.fn() };
    render(<NativeScanReview api={api as unknown as TwinPulseApi} />);
    const file = new File(["{}"], "native.json", { type: "application/json" });
    Object.defineProperty(file, "size", { value: 9 * 1024 * 1024 });
    fireEvent.change(screen.getByLabelText("Import native scan bundle (JSON)"), { target: { files: [file] } });
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "Native bundle exceeds 8 MiB.");
    expect(api.importNativeScan).not.toHaveBeenCalled();
  });
  it("rejects a non-JPEG local attachment before hashing or showing it", async () => {
    const api = { nativeScan: vi.fn().mockResolvedValue(state()) };
    render(<NativeScanReview api={api as unknown as TwinPulseApi} />);
    fireEvent.click(screen.getByText("Refresh native evidence"));
    const input = await screen.findByLabelText("Attach top_view original JPEG (local only)");
    const file = new File(["bad"], "bad.jpg", { type: "image/jpeg" });
    Object.defineProperty(file, "arrayBuffer", { value: async () => new Uint8Array([1, 2, 3]).buffer });
    fireEvent.change(input, { target: { files: [file] } });
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "Original JPEG required.");
    expect(screen.queryByAltText("top_view hash-matched source photo")).toBeNull();
  });
  it("shows descriptive coverage with unknown clearance and no invented missing range", async () => {
    const value = state();
    value.analysis = { assessment: "DESCRIPTIVE_ONLY", frame_count: 2, sample_count: 8, excluded_count: 6,
      excluded_percent: 75, min_usable_per_frame: 1, max_usable_per_frame: 1, worst_return_gap_deg: 360,
      never_observed_angle_bins: 71, clearance: "UNKNOWN", stationarity_verified: false, range_accuracy_verified: false,
      motion_authorized: false, angle_groups: [{ native_angle_start_deg: 5, native_angle_end_deg: 10, frames_with_returns: 0,
        frames_total: 2, median_of_frame_medians_m: null, p10_frame_median_m: null, p90_frame_median_m: null, median_absolute_deviation_m: null }] };
    const api = { nativeScan: vi.fn().mockResolvedValue(value) };
    render(<NativeScanReview api={api as unknown as TwinPulseApi} />);
    fireEvent.click(screen.getByText("Refresh native evidence"));
    expect(await screen.findByText(/Clearance: UNKNOWN/)).toBeTruthy();
    expect(screen.getByText(/75.00%/)).toBeTruthy();
    expect(screen.getAllByText("UNKNOWN")).toHaveLength(2);
  });
});
