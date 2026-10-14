// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { IsaacConnectionStatus } from './IsaacConnectionStatus';
describe('always visible Isaac connection status',()=>{
  it('reports startup rather than a missing connection failure',()=>{
    render(<IsaacConnectionStatus runtime={{status:'starting',started_at_utc:new Date().toISOString(),message:'Starting Isaac'} as never} connected={false} apiConnected={true} inspect={()=>{}}/>);
    expect(screen.getByRole('status').textContent).toContain('Isaac starting');
  });
  it('never equates launcher ready with an observed Isaac connection',()=>{
    render(<IsaacConnectionStatus runtime={{status:'ready'} as never} connected={false} apiConnected={true} inspect={()=>{}}/>);
    expect(screen.getByRole('status').textContent).toBe('Connecting to Isaac');
  });
  it('reports failure even if an older engine observation was connected',()=>{
    render(<IsaacConnectionStatus runtime={{status:'error'} as never} connected={true} apiConnected={true} inspect={()=>{}}/>);
    expect(screen.getByRole('status').textContent).toBe('Isaac startup failed');
  });
  it('does not claim current connection after local API reception is lost',()=>{
    render(<IsaacConnectionStatus runtime={{status:'ready'} as never} connected={true} apiConnected={false} inspect={()=>{}}/>);
    expect(screen.getByRole('status').textContent).toBe('Connecting to App');
  });
});
