// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { TwinPulseApi } from './api';
import { RobotDiagnostics, type RobotDiagnosticsState } from './RobotDiagnostics';

function ready(): RobotDiagnosticsState {
  return { schema_version: 'robot-diagnostics-1.0', available: true, target: 'fixed',
    motion_authorized: false, demo_ready: false, pc: { ready: true, checked_at_utc: 'now', checks: [] },
    start_token: 'one-use', job: null, record: null };
}
function apiFixture() {
  return { robotPreflight: vi.fn().mockResolvedValue(ready()),
    startRobotCheck: vi.fn().mockResolvedValue({ ...ready(), start_token: null }),
    robotDiagnostics: vi.fn().mockResolvedValue({ ...ready(), start_token: null }) };
}
const run = () => screen.getByRole('button', { name: 'Connect robot and run bundled check' }) as HTMLButtonElement;
describe('integrated read-only connection', () => {
  it('distinguishes boot/network waiting from authentication failure in the quick console', async () => {
    const api=apiFixture();
    api.startRobotCheck.mockResolvedValue({...ready(),start_token:null,job:{id:'a',status:'FAILED',
      phase:'FINISHED',started_at_utc:'now',result_code:'SSH_OR_REMOTE_SETUP_FAILED',saved:true,
      diagnostic:{code:'SSH_CONNECTION_REFUSED',exit_code:255}}});
    render(<RobotDiagnostics api={api as unknown as TwinPulseApi} compact autoConnect/>);
    await screen.findByText('Waiting for robot SSH — retry when ready');
    expect(screen.getByText(/usually needs 2–3 minutes/)).toBeTruthy();
    api.startRobotCheck.mockResolvedValue({...ready(),start_token:null,job:{id:'b',status:'FAILED',
      phase:'FINISHED',started_at_utc:'now',result_code:'SSH_OR_REMOTE_SETUP_FAILED',saved:true,
      diagnostic:{code:'SSH_AUTH_FAILED',exit_code:255}}});
    fireEvent.click(screen.getByRole('button',{name:'Retry connection'}));
    await screen.findByText(/waiting for boot will not fix this/);
    expect(screen.queryByText('Waiting for robot SSH — retry when ready')).toBeNull();
  });
  it('does nothing on mount; one click prepares then connects without a separate checkbox', async () => {
    const api = apiFixture(); render(<RobotDiagnostics api={api as unknown as TwinPulseApi} />);
    expect(api.robotPreflight).not.toHaveBeenCalled(); expect(api.startRobotCheck).not.toHaveBeenCalled();
    expect(screen.queryByRole('checkbox')).toBeNull(); expect(run().disabled).toBe(false);
    fireEvent.click(run());
    await waitFor(() => expect(api.startRobotCheck).toHaveBeenCalledWith('one-use'));
    expect(api.robotPreflight).toHaveBeenCalledTimes(1); expect(api.startRobotCheck).toHaveBeenCalledTimes(1);
    expect(api.robotPreflight.mock.invocationCallOrder[0]).toBeLessThan(api.startRobotCheck.mock.invocationCallOrder[0]);
  });
  it('PC-only option never connects; next connection obtains a fresh token', async () => {
    const api = apiFixture(); render(<RobotDiagnostics api={api as unknown as TwinPulseApi} />);
    fireEvent.click(screen.getByText('Check PC only'));
    await waitFor(() => expect(screen.getByText(/PC checked at/)).toBeTruthy());
    expect(api.startRobotCheck).not.toHaveBeenCalled();
    api.robotPreflight.mockResolvedValueOnce({ ...ready(), start_token: 'new-token' });
    fireEvent.click(run());
    await waitFor(() => expect(api.startRobotCheck).toHaveBeenCalledWith('new-token'));
  });
  it('missing PC dependencies stop before transport', async () => {
    const api = apiFixture(); api.robotPreflight.mockResolvedValue({ ...ready(), pc: { ready: false, checked_at_utc: 'now', checks: [{ id: 'ssh_client', ok: false }] }, start_token: null });
    render(<RobotDiagnostics api={api as unknown as TwinPulseApi} />); fireEvent.click(run());
    await screen.findByRole('alert'); expect(api.startRobotCheck).not.toHaveBeenCalled();
    expect(screen.getByText(/SSH executable: Missing/)).toBeTruthy();
  });
  it('ambiguous response requires read-only refresh, never retries automatically', async () => {
    const api = apiFixture(); api.startRobotCheck.mockRejectedValue(new Error('lost'));
    render(<RobotDiagnostics api={api as unknown as TwinPulseApi} />); fireEvent.click(run());
    await screen.findByRole('alert'); expect(run().disabled).toBe(true);
    expect(api.startRobotCheck).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByText('Refresh results'));
    await waitFor(() => expect(run().disabled).toBe(false));
    expect(api.startRobotCheck).toHaveBeenCalledTimes(1);
  });
  it('double click while preparing cannot create two jobs', async () => {
    let resolve!: (value: RobotDiagnosticsState) => void;
    const api = apiFixture(); api.robotPreflight.mockReturnValue(new Promise(r => { resolve = r; }));
    render(<RobotDiagnostics api={api as unknown as TwinPulseApi} />);
    fireEvent.click(run()); fireEvent.click(run());
    expect(api.robotPreflight).toHaveBeenCalledTimes(1); resolve(ready());
    await waitFor(() => expect(api.startRobotCheck).toHaveBeenCalledTimes(1));
  });
  it('navigation during PC preparation cannot initiate a later connection', async () => {
    let resolve!: (value: RobotDiagnosticsState) => void;
    const api = apiFixture(); api.robotPreflight.mockReturnValue(new Promise(r => { resolve = r; }));
    const view = render(<RobotDiagnostics api={api as unknown as TwinPulseApi} />);
    fireEvent.click(run()); view.unmount(); resolve(ready());
    await Promise.resolve(); expect(api.startRobotCheck).not.toHaveBeenCalled();
  });
});
