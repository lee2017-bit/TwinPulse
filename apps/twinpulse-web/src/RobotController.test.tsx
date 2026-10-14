// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { TwinPulseApi } from './api';
import { RobotController, type ManualControllerState } from './RobotController';

function fixture() {
  const state: ManualControllerState = { mode: 'PC_REHEARSAL_ONLY', physical_motion_authorized: false,
    physical_lidar_authorized: false, physical_blockers: ['PHYSICAL_STOP_NOT_QUALIFIED'],
    session_id: 'memory-only', owned: true, armed: true, sequence: 0, linear_m_s: 0, angular_rad_s: 0,
    pose: { x_m: 0, y_m: 0, yaw_rad: 0 }, lidar_running: false, lidar_remaining_s: 0, reason: 'ARMED_REHEARSAL' };
  return { beginController: vi.fn().mockResolvedValue(state), controllerState: vi.fn().mockResolvedValue(state),
    controllerInput: vi.fn().mockImplementation(async (_session, sequence, action) => ({ ...state, sequence,
      armed: action !== 'stop_all', reason: action === 'stop_all' ? 'OPERATOR_STOP' : 'HELD_INPUT' })) };
}
async function ready(api: ReturnType<typeof fixture>) {
  render(<RobotController api={api as unknown as TwinPulseApi} />);
  fireEvent.click(screen.getByText('PC rehearsal'));
  fireEvent.click(screen.getByRole('checkbox'));
  fireEvent.click(screen.getByText('Prepare rehearsal controls'));
  await waitFor(() => expect((screen.getByText('↑ Forward') as HTMLButtonElement).disabled).toBe(false));
}
describe('manual console', () => {
  it('locks named-project physical controls while leaving PC rehearsal available', () => {
    const api = fixture();
    render(<RobotController api={api as unknown as TwinPulseApi} physicalProjectAllowed={false} />);
    expect(screen.getByText(/Project-bound saved history can be reviewed/)).toBeTruthy();
    expect((screen.getByText('3. Connect manual control') as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByText('PC rehearsal'));
    expect((screen.getByText('Prepare rehearsal controls') as HTMLButtonElement).disabled).toBe(true);
  });
  it('defaults to locked physical controls without automatic activation', () => {
    const api = fixture(); render(<RobotController api={api as unknown as TwinPulseApi} />);
    expect(screen.getByText(/Physical control locked/)).toBeTruthy();
    expect((screen.getByText('↑ Forward') as HTMLButtonElement).disabled).toBe(true);
    expect(api.beginController).not.toHaveBeenCalled(); expect(api.controllerInput).not.toHaveBeenCalled();
  });
  it('keyboard release stops and Escape latches all outputs', async () => {
    const api = fixture(); await ready(api);
    const panel = screen.getByRole('region', { name: 'Virtual controller' });
    fireEvent.keyDown(panel, { key: 'w' });
    await waitFor(() => expect(api.controllerInput).toHaveBeenCalledWith('memory-only', 1, 'forward'));
    fireEvent.keyUp(panel, { key: 'w' });
    await waitFor(() => expect(api.controllerInput).toHaveBeenCalledWith('memory-only', 2, 'stop'));
    fireEvent.keyDown(panel, { key: 'Escape' });
    await waitFor(() => expect(api.controllerInput).toHaveBeenCalledWith('memory-only', 3, 'stop_all'));
  });
  it('focus loss sends stop and requires fresh rehearsal enable', async () => {
    const api = fixture(); await ready(api);
    fireEvent(window, new Event('blur'));
    await waitFor(() => expect(api.controllerInput).toHaveBeenCalledWith('memory-only', 1, 'stop_all'));
    await waitFor(() => expect((screen.getByText('↑ Forward') as HTMLButtonElement).disabled).toBe(true));
  });
  it('unmount closes only the mock session', async () => {
    const api = fixture(); const view = render(<RobotController api={api as unknown as TwinPulseApi} />);
    fireEvent.click(screen.getByText('PC rehearsal')); fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByText('Prepare rehearsal controls'));
    await waitFor(() => expect((screen.getByText('↑ Forward') as HTMLButtonElement).disabled).toBe(false));
    view.unmount();
    expect(api.controllerInput).toHaveBeenCalledWith('memory-only', 1, 'close');
  });
  it('ignores a late input response belonging to an older session', async () => {
    const api = fixture(); await ready(api);
    const oldState = await api.beginController();
    let finish!: (state: ManualControllerState) => void;
    api.controllerInput.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    const panel = screen.getByRole('region', { name: 'Virtual controller' });
    fireEvent.keyDown(panel, { key: 'w' });
    fireEvent.keyDown(panel, { key: 'Escape' });
    await waitFor(() => expect((screen.getByText('↑ Forward') as HTMLButtonElement).disabled).toBe(true));
    api.beginController.mockResolvedValue({ ...oldState, session_id: 'new-session' });
    fireEvent.click(screen.getByRole('checkbox')); fireEvent.click(screen.getByText('Prepare rehearsal controls'));
    await waitFor(() => expect((screen.getByText('↑ Forward') as HTMLButtonElement).disabled).toBe(false));
    finish({ ...oldState, sequence: 1, linear_m_s: .03 });
    await waitFor(() => expect(screen.getByText(/Synthetic velocity: 0.00 m\/s/)).toBeTruthy());
    fireEvent.keyDown(panel, { key: 'Escape' });
    await waitFor(() => expect(api.controllerInput).toHaveBeenLastCalledWith('new-session', 1, 'stop_all'));
  });
});
