// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { RobotCheckDetails } from './RobotCheckDetails';
import type { RobotReportState } from './RobotReport';

function record(): NonNullable<RobotReportState['record']> {
  return { boot_id: 'boot', release_id: 'release', report_sha256: 'hash', age_seconds: 0,
    observed_at_utc: '2026-09-27T11:36:40Z', board_status: 'OBSERVED', idle_at_observation: true,
    guard_artifact_verified_at_observation: true, battery: null,
    board_observation: { observed_at_utc: '2026-09-27T11:36:40Z', torque_enabled: false,
      wheel_velocity_raw: [0, 0], command_bytes_zero: true, port_restored: true } };
}

describe('robot explanation without operator interpretation', () => {
  it('explains torque-only failure without claiming movement or repair', () => {
    const value = record(); value.board_observation!.torque_enabled = true;
    render(<RobotCheckDetails record={value} healthStatus="NEEDS_ATTENTION" sensorStatus="NO_SENSOR_DATA" />);
    expect(screen.getByText(/Motor torque is enabled/)).toBeTruthy();
    expect(screen.getByText(/does not by itself mean the wheels moved/)).toBeTruthy();
    expect(screen.getByText(/Motor OFF and status confirmation in the control panel/)).toBeTruthy();
    expect(screen.getByText(/this result alone does not indicate a fault/)).toBeTruthy();
  });
  it('does not invent a cause from legacy aggregate false', () => {
    const value = record(); delete value.board_observation; value.idle_at_observation = false;
    render(<RobotCheckDetails record={value} />);
    expect(screen.getByText(/no individual torque, velocity, or port values/)).toBeTruthy();
    expect(screen.queryByText(/Motor torque is enabled/)).toBeNull();
  });
  it('distinguishes simultaneous speed, command and restore failures', () => {
    const value = record(); Object.assign(value.board_observation!, { wheel_velocity_raw: [4, -2], command_bytes_zero: false, port_restored: false });
    render(<RobotCheckDetails record={value} />);
    expect(screen.getByText(/left 4, right -2/)).toBeTruthy();
    expect(screen.getByText(/Wheel velocity or command is nonzero/)).toBeTruthy();
    expect(screen.getByText(/Port restoration was not verified/)).toBeTruthy();
    expect(screen.queryByText(/Board and deployment conditions passed this read-only snapshot/)).toBeNull();
  });
  it('only qualifies the observation, never full readiness', () => {
    render(<RobotCheckDetails record={record()} healthStatus="IDLE_SNAPSHOT_OK" sensorStatus="SENSOR_MESSAGES_RECEIVED" />);
    expect(screen.getByText(/No need to repeat it/)).toBeTruthy();
    expect(screen.getByText(/does not verify coordinate alignment or obstacle safety/)).toBeTruthy();
    expect(screen.getByText(/Pending development and validation/)).toBeTruthy();
  });
  it('missing board and protection condition remain actionable unknown', () => {
    const value = record(); value.board_observation = null; value.board_status = 'BUSY';
    value.battery = { voltage_v: 11, estimated_percent: 27.8, observed_at_utc: value.observed_at_utc,
      charge_requested_at_observation: false, near_protection_at_observation: true };
    render(<RobotCheckDetails record={value} />);
    expect(screen.getByText(/No board details \(BUSY\)/)).toBeTruthy();
    expect(screen.getByText(/Repeating a check cannot resolve low voltage/)).toBeTruthy();
  });
});
