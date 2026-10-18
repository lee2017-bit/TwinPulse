// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { TwinPulseApi } from './api';
import { RobotReadiness, type RobotReadinessState } from './RobotReadiness';

const empty: RobotReadinessState = {
  schema_version: 'robot-readiness-app-1.0', status: 'NOT_STARTED', job_id: null,
  motion_authorized: false, demo_ready: false, result: null, report_path: null,
};
function fixture() {
  return {
    robotReadiness: vi.fn().mockResolvedValue(empty),
    startRobotReadiness: vi.fn().mockResolvedValue({ ...empty, status: 'RUNNING', job_id: 'a'.repeat(32) }),
    clearUncertainRobotReadiness: vi.fn().mockResolvedValue({ ...empty, status: 'CLEARED_AFTER_OPERATOR_OFF' }),
  };
}
describe('no-motion App collection', () => {
  it('mount and refresh never start a robot operation; explicit approval starts once', async () => {
    const api = fixture(); render(<RobotReadiness api={api as unknown as TwinPulseApi} available />);
    await waitFor(() => expect(api.robotReadiness).toHaveBeenCalledTimes(1));
    expect(api.startRobotReadiness).not.toHaveBeenCalled();
    const button = screen.getByRole('button', { name: 'Collect stationary evidence once' }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: 'Refresh saved result' }));
    await waitFor(() => expect(api.robotReadiness).toHaveBeenCalledTimes(2));
    expect(api.startRobotReadiness).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('checkbox', { name: /I approve this one no-motion/ }));
    fireEvent.click(button); fireEvent.click(button);
    await waitFor(() => expect(api.startRobotReadiness).toHaveBeenCalledTimes(1));
  });

  it('saved evidence gaps display after reopen without starting a new collection', async () => {
    const api = fixture(); api.robotReadiness.mockResolvedValue({ ...empty, status: 'COMPLETED_WITH_GAPS',
      job_id: 'a'.repeat(32), project_id: 'default',
      app_context: { app_scene_revision: 'b'.repeat(64), app_robot_profile_id: 'burger3', capture_status: 'CAPTURED' },
      report_path: 'local/report.json', result: { status: 'EVIDENCE_GAPS', demo_ready: false,
        motion_authorized: false, steps: { stationary_collection: { status: 'STATIONARY_CHECK_PASS' } },
        evidence: { odom: { status: 'REJECTED' }, scan: { status: 'NOT_RECEIVED' },
          tf: { status: 'NOT_RECEIVED' }, room_alignment: 'NOT_VERIFIED' } } });
    render(<RobotReadiness api={api as unknown as TwinPulseApi} available />);
    expect(await screen.findByText(/Odom: REJECTED/)).toBeTruthy();
    expect(screen.getByText(/Room alignment: NOT_VERIFIED/)).toBeTruthy();
    expect(screen.getByText(/Collection ID:/)).toBeTruthy();
    expect(screen.getByText(/Profile: burger3/)).toBeTruthy();
    expect(api.startRobotReadiness).not.toHaveBeenCalled();
  });

  it('uncertain remote state blocks collection until separate physical-OFF confirmation', async () => {
    const api = fixture(); api.robotReadiness.mockResolvedValue({ ...empty, status: 'REMOTE_STATE_UNKNOWN' });
    render(<RobotReadiness api={api as unknown as TwinPulseApi} available />);
    await screen.findByRole('alert');
    fireEvent.click(screen.getByRole('checkbox', { name: /I approve this one no-motion/ }));
    expect((screen.getByRole('button', { name: 'Collect stationary evidence once' }) as HTMLButtonElement).disabled).toBe(true);
    const clear = screen.getByRole('button', { name: 'Record robot OFF and clear uncertain job' }) as HTMLButtonElement;
    expect(clear.disabled).toBe(true);
    fireEvent.click(screen.getByRole('checkbox', { name: /physically powered the robot off/ }));
    fireEvent.click(clear);
    await waitFor(() => expect(api.clearUncertainRobotReadiness).toHaveBeenCalledTimes(1));
    expect(api.startRobotReadiness).not.toHaveBeenCalled();
  });

  it('ambiguous start response performs only a status read, never a second start', async () => {
    const api = fixture(); api.startRobotReadiness.mockRejectedValue(new Error('response lost'));
    render(<RobotReadiness api={api as unknown as TwinPulseApi} available />);
    await waitFor(() => expect(api.robotReadiness).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole('checkbox', { name: /I approve this one no-motion/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Collect stationary evidence once' }));
    await screen.findByRole('alert');
    expect(api.startRobotReadiness).toHaveBeenCalledTimes(1);
    expect(api.robotReadiness).toHaveBeenCalledTimes(2);
  });

  it('unavailable saved status keeps collection locked even after the operator clicks approval', async () => {
    const api = fixture(); api.robotReadiness.mockRejectedValue(new Error('unavailable'));
    render(<RobotReadiness api={api as unknown as TwinPulseApi} available />);
    await screen.findByRole('alert');
    const approval = screen.getByRole('checkbox', { name: /I approve this one no-motion/ }) as HTMLInputElement;
    const start = screen.getByRole('button', { name: 'Collect stationary evidence once' }) as HTMLButtonElement;
    expect(approval.disabled).toBe(true);
    expect(start.disabled).toBe(true);
    fireEvent.click(approval); fireEvent.click(start);
    expect(api.startRobotReadiness).not.toHaveBeenCalled();
  });
});
