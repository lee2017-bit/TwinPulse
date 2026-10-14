// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { TwinPulseApi } from './api';
import { RobotConsoleEntry } from './RobotQuickConsole';
import type { RobotDiagnosticsState } from './RobotDiagnostics';

function check(status: 'COMPLETED' | 'FAILED', code: string): RobotDiagnosticsState {
  return {
    schema_version: 'robot-diagnostics-1.0', available: true, target: 'test-robot',
    motion_authorized: false, demo_ready: false, start_token: null,
    pc: { ready: true, checked_at_utc: '2026-10-03T00:00:00Z', checks: [] },
    job: { id: 'fresh-check', status, phase: 'done', started_at_utc: '2026-10-03T00:00:00Z',
      result_code: code, saved: true },
    record: status === 'COMPLETED' ? {
      boot_id: 'test-boot', release_id: 'test-release', report_sha256: 'test',
      observed_at_utc: '2026-10-03T00:00:00Z', age_seconds: 0, board_status: 'OBSERVED',
      idle_at_observation: true, guard_artifact_verified_at_observation: true,
      board_observation: { observed_at_utc: '2026-10-03T00:00:00Z', torque_enabled: false,
        wheel_velocity_raw: [0, 0], command_bytes_zero: true, port_restored: true },
      battery: null,
    } : null,
  };
}

function fixture() {
  const preflight: RobotDiagnosticsState = {
    ...check('FAILED', 'PENDING'), job: null, record: null, start_token: 'one-use',
  };
  return {
    bootstrap: vi.fn().mockResolvedValue(undefined),
    robotPreflight: vi.fn().mockResolvedValue(preflight),
    startRobotCheck: vi.fn().mockResolvedValue(check('COMPLETED', 'OBSERVATION_RECEIVED')),
    robotDiagnostics: vi.fn().mockResolvedValue(check('COMPLETED', 'OBSERVATION_RECEIVED')),
    physicalState: vi.fn().mockResolvedValue({ state: 'NOT_STARTED', busy: false }),
    physicalStart: vi.fn(), physicalInput: vi.fn(),
  };
}

describe('dedicated one-click robot console', () => {
  it('bootstraps locally and runs only one automatic read-only check, without Isaac or motor calls', async () => {
    const api = fixture();
    render(<RobotConsoleEntry api={api as unknown as TwinPulseApi} />);
    await waitFor(() => expect(api.startRobotCheck).toHaveBeenCalledTimes(1));
    expect(api.robotPreflight).toHaveBeenCalledTimes(1);
    expect(api.startRobotCheck).toHaveBeenCalledWith('one-use');
    await screen.findByRole('region', { name: 'Physical controller' });
    expect((screen.getByRole('button', { name: '↑ Forward' }) as HTMLButtonElement).disabled).toBe(true);
    expect(api.physicalStart).not.toHaveBeenCalled();
    expect(api.physicalInput).not.toHaveBeenCalled();
  });

  it('shows the failure reason and never unlocks controls until an explicit retry succeeds', async () => {
    const api = fixture();
    api.startRobotCheck.mockResolvedValueOnce(check('FAILED', 'SSH_OR_REMOTE_SETUP_FAILED'));
    render(<RobotConsoleEntry api={api as unknown as TwinPulseApi} />);
    await screen.findByText(/Connection or remote check failed/);
    expect(screen.queryByRole('region', { name: 'Physical controller' })).toBeNull();
    expect(api.startRobotCheck).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: 'Retry connection' }));
    await waitFor(() => expect(api.startRobotCheck).toHaveBeenCalledTimes(2));
    await screen.findByRole('region', { name: 'Physical controller' });
    expect(api.physicalStart).not.toHaveBeenCalled();
  });

  it('reports local authentication failure and does not access the robot', async () => {
    const api = fixture();
    api.bootstrap.mockRejectedValueOnce(new Error('Session expired'));
    render(<RobotConsoleEntry api={api as unknown as TwinPulseApi} />);
    await screen.findByRole('alert');
    expect(api.robotPreflight).not.toHaveBeenCalled();
    expect(api.startRobotCheck).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Retry local console' }));
    await waitFor(() => expect(api.startRobotCheck).toHaveBeenCalledTimes(1));
  });
});
