// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {describe,it,expect,vi} from 'vitest';
import {DeviceLogStorage} from './DeviceLogStorage';
import type {TwinPulseApi} from './api';
describe('Connection diagnostic retention',()=>{
  it('only archives after the explicit button and keeps the selected valid period',async()=>{
    const archive=vi.fn().mockResolvedValue({archived_count:2});
    render(<DeviceLogStorage api={{deviceDiagnosticRetention:archive} as unknown as TwinPulseApi}/>);
    expect(archive).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('Connection log storage'));
    fireEvent.change(screen.getByLabelText('Connection log retention days'),{target:{value:'7'}});
    fireEvent.click(screen.getByRole('button',{name:'Archive older connection logs'}));
    await waitFor(()=>expect(archive).toHaveBeenCalledWith(7));
    expect(await screen.findByText('Archived 2 finished logs. Current device state is unchanged.')).toBeTruthy();
  });
  it('does not automatically repeat an uncertain archive result',async()=>{
    const archive=vi.fn().mockRejectedValue(new Error('response lost'));
    render(<DeviceLogStorage api={{deviceDiagnosticRetention:archive} as unknown as TwinPulseApi}/>);
    fireEvent.click(screen.getByText('Connection log storage'));
    fireEvent.click(screen.getByRole('button',{name:'Archive older connection logs'}));
    await screen.findByText(/archive is unavailable/);
    expect(archive).toHaveBeenCalledOnce();
  });
});
