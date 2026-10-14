// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { DerivedReview } from './DerivedReview';
import type { TwinPulseApi } from './api';
import type { WorkflowState } from './types';

const workflow = { phase: 'draft_ready', input: { revision: 'input' }, site_draft: {
  input_revision: 'input', revision: 'current', original_scene_revision: 'original',
} } as WorkflowState;
describe('explicit derived scene selection', () => {
  it('does not adopt automatically and sends displayed identities after explicit choice', async () => {
    const api = { adoptDerivedReview: vi.fn().mockResolvedValue(workflow) }, onWorkflow = vi.fn();
    render(<DerivedReview api={api as unknown as TwinPulseApi} workflow={workflow} workspaceRevision="workspace"
      hasEdits disabled={false} onWorkflow={onWorkflow} />);
    const button = screen.getByText('Select scratch edits as scene draft') as HTMLButtonElement;
    expect(button.disabled).toBe(true); expect(api.adoptDerivedReview).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('checkbox')); fireEvent.click(button);
    await waitFor(() => expect(api.adoptDerivedReview).toHaveBeenCalledWith('input', 'original', 'workspace'));
    expect(onWorkflow).toHaveBeenCalledWith(workflow);
  });
  it('explicit restore works without scratch edits but adoption does not', async () => {
    const api = { restoreDerivedReview: vi.fn().mockResolvedValue(workflow) };
    render(<DerivedReview api={api as unknown as TwinPulseApi} workflow={workflow} hasEdits={false}
      disabled={false} onWorkflow={vi.fn()} />);
    fireEvent.click(screen.getByRole('checkbox'));
    expect((screen.getByText('Select scratch edits as scene draft') as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByText('Restore saved derived scene for review'));
    await waitFor(() => expect(api.restoreDerivedReview).toHaveBeenCalledWith('input', 'original'));
  });
  it('refreshes cleared server acknowledgement after failure', async () => {
    const api = { adoptDerivedReview: vi.fn().mockRejectedValue(new Error('stale review')), workflow: vi.fn().mockResolvedValue(workflow) };
    const onWorkflow = vi.fn();
    render(<DerivedReview api={api as unknown as TwinPulseApi} workflow={workflow} workspaceRevision="workspace"
      hasEdits disabled={false} onWorkflow={onWorkflow} />);
    fireEvent.click(screen.getByRole('checkbox')); fireEvent.click(screen.getByText('Select scratch edits as scene draft'));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toBe('stale review'));
    await waitFor(() => expect(onWorkflow).toHaveBeenCalledWith(workflow));
    expect((screen.getByRole('checkbox') as HTMLInputElement).checked).toBe(false);
  });
  it('disables selection when the current input does not match the original draft', () => {
    render(<DerivedReview api={{} as TwinPulseApi} workflow={{ ...workflow, input: null }} workspaceRevision="workspace"
      hasEdits disabled={false} onWorkflow={vi.fn()} />);
    expect((screen.getByRole('checkbox') as HTMLInputElement).disabled).toBe(true);
  });
});
