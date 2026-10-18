// SPDX-License-Identifier: Apache-2.0
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,describe,it,expect,vi} from 'vitest';
import {DesktopTesting} from './DesktopTesting';
afterEach(()=>{cleanup();delete window.twinpulseDesktop;});
function setup(enabled=false){const host={versions:vi.fn(),onExitRequested:vi.fn(),reportExitResult:vi.fn(),
  automationStatus:vi.fn().mockResolvedValue({enabled,state:'idle',run_id:null,report_available:false,scope:'basic'}),
  runBasicChecks:vi.fn().mockResolvedValue({state:'running'}),openCheckReport:vi.fn()};window.twinpulseDesktop=host;render(<DesktopTesting/>);return host;}
describe('desktop testing UI supplementary',()=>{
  it('normal launch explains optional entry but cannot run checks',async()=>{const host=setup();await waitFor(()=>expect(host.automationStatus).toHaveBeenCalled());
    fireEvent.click(screen.getByRole('button',{name:'Tests'}));await screen.findByText(/Normal mode: no automation port/);
    expect(screen.getByRole('button',{name:'Run basic checks'})).toHaveProperty('disabled',true);expect(host.runBasicChecks).not.toHaveBeenCalled();});
  it('explicit test mode has a banner and starts only on click, closing the dialog first',async()=>{const host=setup(true);await screen.findByText(/TEST MODE/);
    expect(host.runBasicChecks).not.toHaveBeenCalled();fireEvent.click(screen.getByRole('button',{name:'Tests'}));
    fireEvent.click(screen.getByRole('button',{name:'Run basic checks'}));await waitFor(()=>expect(host.runBasicChecks).toHaveBeenCalledOnce());
    expect(screen.queryByRole('dialog')).toBeNull();});
});
