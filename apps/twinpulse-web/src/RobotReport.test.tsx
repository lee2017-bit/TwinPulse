// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { RobotReport, type RobotReportState } from './RobotReport';
import type { TwinPulseApi } from './api';

function state(): RobotReportState {
  return { schema_version: 'robot-report-review-1.0', session_id: 'test', connection: 'NOT_CONNECTED',
    motion_authorized: false, demo_ready: false, notice: 'Saved only', blockers: [],
    record: { boot_id: 'boot', release_id: null, report_sha256: 'digest',
      observed_at_utc: '2026-09-26T15:00:00Z', age_seconds: 3600, board_status: 'OBSERVED',
      idle_at_observation: true, battery: { voltage_v: 11.21, estimated_percent: 39.4,
        observed_at_utc: '2026-09-26T15:00:00Z', charge_requested_at_observation: false,
        near_protection_at_observation: false } } };
}

describe('recorded robot diagnostics', () => {
  it('does not automatically connect or load on render', () => {
    const api = { robotReport: vi.fn(), importRobotReport: vi.fn() };
    render(<RobotReport api={api as unknown as TwinPulseApi} />);
    expect(api.robotReport).not.toHaveBeenCalled();
    expect(screen.getByText(/Current battery and robot state are unknown/)).toBeTruthy();
  });
  it('shows historical battery, not live readiness', async () => {
    const api = { robotReport: vi.fn().mockResolvedValue(state()) };
    render(<RobotReport api={api as unknown as TwinPulseApi} />);
    fireEvent.click(screen.getByText('Refresh saved report'));
    await waitFor(() => expect(screen.getByText(/11.21 V · estimated 39.4% at observation/)).toBeTruthy());
    expect(screen.getByText('Historical measurement — not live')).toBeTruthy();
    expect(screen.getByText(/Physical movement unavailable/)).toBeTruthy();
    expect(screen.queryByRole('button', { name: /Run robot/ })).toBeNull();
  });
  it('rejects oversized files without a request', async () => {
    const api = { importRobotReport: vi.fn() };
    render(<RobotReport api={api as unknown as TwinPulseApi} />);
    const file = new File(['x'.repeat(262145)], 'large.json');
    fireEvent.change(screen.getByLabelText('Import robot report (JSON)'), { target: { files: [file] } });
    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
    expect(api.importRobotReport).not.toHaveBeenCalled();
  });
});
