// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { TwinPulseApi } from './api';
import { ScanReview, type ScanReviewState } from './ScanReview';

function state(): ScanReviewState {
  const scene = { revision: 'scene', objects: [{ id: 'box', kind: 'box', dynamic: false, collision: true,
    transform: { position_m: [1, 1, 1], rotation_rpy_deg: [0, 0, 0] }, shape: { type: 'box', dimensions_m: [1, 1, 2] } }] };
  return { workspace_revision: 'workspace', mode: 'isolated_offline_review', active_project_changed: false,
    motion_authorized: false, demo_ready: false, physical_validation: 'NOT_RUN', notice: 'Offline only',
    scene, before_scene: scene, scan: { provenance: 'synthetic', scene_revision: 'scene', valid_beams: 2, invalid_beams: 0,
      points: [{ frame_index: 0, beam_index: 0, x_m: 1.2, y_m: 1.1 }] },
    proposal: null, edit_revision: null, map_present: false, mission_present: false };
}

describe('offline scan review', () => {
  it('restores only explicitly selected archive using the current revision', async () => {
    const api = { scanReview: vi.fn().mockResolvedValue(state()), importScanArchive: vi.fn().mockResolvedValue(state()) };
    render(<ScanReview api={api as unknown as TwinPulseApi} />);
    expect(api.importScanArchive).not.toHaveBeenCalled();
    const file = new File(['{}'], 'archive.json'); Object.defineProperty(file, 'text', { value: async () => '{}' });
    fireEvent.change(screen.getByLabelText('Restore offline archive (JSON)'), { target: { files: [file] } });
    await waitFor(() => expect(api.importScanArchive).toHaveBeenCalledWith('workspace', '{}'));
    expect(screen.getByText(/Pending proposals, comparisons and approvals are not restored/)).toBeTruthy();
  });
  it('rejects oversized archive locally and shows stale import failure', async () => {
    const api = { scanReview: vi.fn().mockResolvedValue(state()), importScanArchive: vi.fn().mockRejectedValue(new Error('workspace changed')) };
    render(<ScanReview api={api as unknown as TwinPulseApi} />);
    fireEvent.change(screen.getByLabelText('Restore offline archive (JSON)'), { target: { files: [new File(['x'.repeat(10 * 1024 * 1024 + 1)], 'large.json')] } });
    await waitFor(() => expect(screen.getByText('Archive exceeds 10 MiB.')).toBeTruthy());
    expect(api.scanReview).not.toHaveBeenCalled(); expect(api.importScanArchive).not.toHaveBeenCalled();
    const file = new File(['{}'], 'archive.json'); Object.defineProperty(file, 'text', { value: async () => '{}' });
    fireEvent.change(screen.getByLabelText('Restore offline archive (JSON)'), { target: { files: [file] } });
    await waitFor(() => expect(screen.getByText('workspace changed')).toBeTruthy());
  });
  it('never loads or connects automatically', () => {
    const api = { scanReview: vi.fn() };
    render(<ScanReview api={api as unknown as TwinPulseApi} />);
    expect(api.scanReview).not.toHaveBeenCalled();
    expect(screen.getByText(/No active project or Isaac changes/)).toBeTruthy();
  });
  it('labels synthetic evidence and draws a bounded overlay', async () => {
    const api = { scanReview: vi.fn().mockResolvedValue(state()) };
    render(<ScanReview api={api as unknown as TwinPulseApi} />);
    fireEvent.click(screen.getByText('Refresh offline review'));
    await waitFor(() => expect(screen.getByText('SYNTHETIC — unverified saved evidence')).toBeTruthy());
    expect(screen.getByRole('img', { name: 'Offline scan and scratch draft overlay' })).toBeTruthy();
    expect((screen.getByText('Apply to scratch draft only') as HTMLButtonElement).disabled).toBe(true);
  });
  it('requires explicit review and sends the exact proposal revision', async () => {
    const proposed = { ...state(), proposal: { revision: 'proposal', object_id: 'box', delta_xy_m: [.2, .1], max_residual_m: 0, pairs: [] } };
    const api = { scanReview: vi.fn().mockResolvedValue(proposed), applyScanCorrection: vi.fn().mockResolvedValue(state()) };
    render(<ScanReview api={api as unknown as TwinPulseApi} />);
    fireEvent.click(screen.getByText('Refresh offline review'));
    await waitFor(() => expect(screen.getByText(/Proposed box/)).toBeTruthy());
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByText('Apply to scratch draft only'));
    await waitFor(() => expect(api.applyScanCorrection).toHaveBeenCalledWith('workspace', 'proposal'));
  });
  it('editing pairs hides the old proposal and disables apply', async () => {
    const proposed = { ...state(), proposal: { revision: 'proposal', object_id: 'box', delta_xy_m: [.2, .1], max_residual_m: 0, pairs: [] } };
    const api = { scanReview: vi.fn().mockResolvedValue(proposed) };
    render(<ScanReview api={api as unknown as TwinPulseApi} />);
    fireEvent.click(screen.getByText('Refresh offline review'));
    await waitFor(() => expect(screen.getByText(/Proposed box/)).toBeTruthy());
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.change(screen.getByLabelText('Landmark pairs (JSON)'), { target: { value: '[1]' } });
    expect(screen.queryByText(/Proposed box/)).toBeNull();
    expect((screen.getByText('Apply to scratch draft only') as HTMLButtonElement).disabled).toBe(true);
  });
  it('invalid pair JSON never reaches the API', async () => {
    const api = { scanReview: vi.fn().mockResolvedValue(state()), proposeScanCorrection: vi.fn() };
    render(<ScanReview api={api as unknown as TwinPulseApi} />);
    fireEvent.click(screen.getByText('Refresh offline review'));
    await waitFor(() => expect(screen.getByLabelText('Landmark pairs (JSON)')).toBeTruthy());
    fireEvent.change(screen.getByLabelText('Landmark pairs (JSON)'), { target: { value: '{' } });
    fireEvent.click(screen.getByText('Preview XY correction'));
    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
    expect(api.proposeScanCorrection).not.toHaveBeenCalled();
  });
  it('rejects oversized files before sending any data', async () => {
    const api = { importScanBundle: vi.fn() };
    render(<ScanReview api={api as unknown as TwinPulseApi} />);
    fireEvent.change(screen.getByLabelText('Import scan bundle (JSON)'), { target: { files: [new File(['x'.repeat(5 * 1024 * 1024 + 1)], 'large.json')] } });
    await waitFor(() => expect(screen.getByText('Bundle exceeds 5 MiB.')).toBeTruthy());
    expect(api.importScanBundle).not.toHaveBeenCalled();
  });
});
