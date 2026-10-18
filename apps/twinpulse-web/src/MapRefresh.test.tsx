// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MapRefresh, type MapPreview } from './MapRefresh';

const proposal: MapPreview = { revision: 'proposal', map_revision: 'map', added_occupied_cells: 12,
  freed_cells: 0, free_cells: 1500, unknown_cells: 2, occupied_cells: 98, start_xy_m: [-2,0], goal_xy_m: [2,0], notice: 'Offline' };
describe('conservative map review', () => {
  it('requires explicit review and sends the exact proposal', () => {
    const apply = vi.fn();
    render(<MapRefresh available proposal={proposal} applied={null} busy={false} preview={vi.fn()} apply={apply} />);
    const button = screen.getByText('Use reviewed map in scratch draft') as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    fireEvent.click(screen.getByRole('checkbox')); fireEvent.click(button);
    expect(apply).toHaveBeenCalledWith('proposal');
    expect(button.disabled).toBe(true);
  });
  it('marks inherited free cells and never describes SLAM or physical approval', () => {
    render(<MapRefresh available proposal={proposal} applied={null} busy={false} preview={vi.fn()} apply={vi.fn()} />);
    expect(screen.getByText(/1500 inherited free cells; 0 freed/)).toBeTruthy();
    expect(screen.getByText(/This is not SLAM/)).toBeTruthy();
  });
  it('unavailable stage is absent and applied stage never offers automatic reapply', () => {
    const { rerender } = render(<MapRefresh available={false} proposal={null} applied={null} busy={false} preview={vi.fn()} apply={vi.fn()} />);
    expect(screen.queryByRole('region')).toBeNull();
    rerender(<MapRefresh available={false} proposal={null} applied={proposal} busy={false} preview={vi.fn()} apply={vi.fn()} />);
    expect(screen.getByText(/Old obstacle areas remain blocked/)).toBeTruthy();
    expect(screen.queryByRole('button')).toBeNull();
  });
});
