// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { RouteComparison, type ComparisonResult } from './RouteComparison';

const conditions = { revision: 'a'.repeat(64), map_revision: 'b'.repeat(64), profile_digest: 'c'.repeat(64),
  start_xy_m: [-2, 0], goal_xy_m: [2, 0], inflation_m: .411, clearance_m: .05 };
const route = { route_id: 'baseline', provenance: 'synthetic', points_xy_m: [[-2, 0], [2, 0]], length_m: 8,
  internal_turn_angle_rad: 3.14, grid_check: { status: 'CLEAR_IN_SUPPLIED_GRID', reason: 'geometry_only' } };
const result: ComparisonResult = { baseline: route, candidate: { ...route, route_id: 'candidate', length_m: 4.828 },
  comparable: true, shorter_route_id: 'candidate', candidate_length_reduction_percent: 39.64466 };

describe('offline route comparison', () => {
  it('disables comparison when map or registered profile is unavailable', () => {
    render(<RouteComparison conditions={null} result={null} reason="No current map" busy={false} compare={vi.fn()} />);
    expect(screen.getByText('Comparison unavailable: No current map')).toBeTruthy();
    expect(screen.queryByText('Compare supplied routes')).toBeNull();
  });
  it('shows exact conditions and sends supplied JSON only on request', () => {
    const compare = vi.fn();
    render(<RouteComparison conditions={conditions} result={null} reason={null} busy={false} compare={compare} />);
    expect(compare).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('Baseline XY points (JSON)'), { target: { value: '[[-2,0],[2,0]]' } });
    fireEvent.change(screen.getByLabelText('Candidate XY points (JSON)'), { target: { value: '[[-2,0],[0,1],[2,0]]' } });
    fireEvent.click(screen.getByText('Compare supplied routes'));
    expect(compare).toHaveBeenCalledWith('[[-2,0],[2,0]]', '[[-2,0],[0,1],[2,0]]');
    expect(screen.getByText(/Same start/).textContent).toContain('[-2, 0]');
  });
  it('labels length-only result and hides it when inputs change', () => {
    render(<RouteComparison conditions={conditions} result={result} reason={null} busy={false} compare={vi.fn()} />);
    expect(screen.getByText(/candidate length reduction 39.64%/)).toBeTruthy();
    expect(screen.getByText(/No physical time or collision improvement measured/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Candidate XY points (JSON)'), { target: { value: '[] ' } });
    expect(screen.queryByText(/candidate length reduction 39.64%/)).toBeNull();
    expect(screen.getByText(/export still contains the previous evaluated points/)).toBeTruthy();
  });
  it('does not show an improvement or winner for a blocked route', () => {
    render(<RouteComparison conditions={conditions} result={{ ...result, comparable: false, shorter_route_id: null,
      candidate_length_reduction_percent: null }} reason={null} busy={false} compare={vi.fn()} />);
    expect(screen.getByText(/Not comparable: no shorter-route winner/)).toBeTruthy();
    expect(screen.queryByText(/candidate length reduction/)).toBeNull();
  });
  it('prevents duplicate requests while processing', () => {
    render(<RouteComparison conditions={conditions} result={null} reason={null} busy={true} compare={vi.fn()} />);
    expect((screen.getByText('Compare supplied routes') as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByLabelText('Baseline XY points (JSON)') as HTMLTextAreaElement).disabled).toBe(true);
  });
});
