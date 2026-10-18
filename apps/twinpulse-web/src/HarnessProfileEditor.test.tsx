// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {HarnessProfileEditor,type HarnessProfile} from './HarnessProfileEditor';
import type {TwinPulseApi} from './api';
afterEach(cleanup);
const reference={id:'planner-default',revision:1,sha256:'a'.repeat(64)};
const profile:HarnessProfile={schema_version:'harness-profile-1.0',id:reference.id,revision:1,provider:'nebius',model_id:'nemotron',role:'planner',baseline_sha256:'b'.repeat(64),instructions:{planning:'Keep scene identities',repair:'Preserve hazards'},compatibility:'unverified'};
describe('harness profile supplementary UI contracts',()=>{
  it('selects explicit legacy instructions for old checkpoint recovery without an API call',()=>{
    const onSaved=vi.fn(),api={updateProviderKeys:vi.fn()};
    render(<HarnessProfileEditor api={api as unknown as TwinPulseApi} stage="planner" choice={{key_id:'key',model_id:'nemotron'}} disabled={false} onBusy={vi.fn()} onSaved={onSaved}/>);
    fireEvent.click(screen.getByText('Planning and repair harness profile'));
    fireEvent.change(screen.getByLabelText('Instruction family'),{target:{value:'legacy'}});
    expect(onSaved).toHaveBeenCalledWith(null);expect(api.updateProviderKeys).not.toHaveBeenCalled();
    expect(screen.getByText(/checkpoint compatibility is still checked/)).toBeTruthy();
  });
  it('loads only explicitly, saves immutable edits with base reference, and selects separately from routing apply',async()=>{
    const saved={...reference,revision:2,sha256:'c'.repeat(64)},onSaved=vi.fn();
    const api={updateProviderKeys:vi.fn().mockResolvedValueOnce({harness_editor:{stage:'planner',key_id:'key',model_id:'nemotron',profile,reference,available:[reference]}})
      .mockResolvedValueOnce({harness_saved:{stage:'planner',reference:saved,profile:{...profile,revision:2}}})};
    render(<HarnessProfileEditor api={api as unknown as TwinPulseApi} stage="planner" choice={{key_id:'key',model_id:'nemotron',harness_profile:reference}} disabled={false} onBusy={vi.fn()} onSaved={onSaved}/>);
    expect(api.updateProviderKeys).not.toHaveBeenCalled();fireEvent.click(screen.getByText('Planning and repair harness profile'));
    fireEvent.click(screen.getByRole('button',{name:'Load profile'}));await screen.findByText(/Compatibility unverified/);
    expect(api.updateProviderKeys).toHaveBeenCalledWith({action:'harness_profile',operation:'draft',stage:'planner',key_id:'key',model_id:'nemotron',reference});
    fireEvent.click(screen.getByRole('button',{name:'Duplicate profile'}));fireEvent.change(screen.getByLabelText('planner repair'),{target:{value:'Retain unresolved supports'}});
    fireEvent.click(screen.getByRole('button',{name:'Save new snapshot'}));
    await waitFor(()=>expect(onSaved).toHaveBeenCalledWith(saved));
    expect(api.updateProviderKeys).toHaveBeenLastCalledWith({action:'harness_profile',operation:'save',stage:'planner',key_id:'key',model_id:'nemotron',base_reference:reference,id:'planner-default-copy',instructions:{planning:'Keep scene identities',repair:'Retain unresolved supports'}});
    expect(screen.getByText(/Snapshot saved. Save model routing/)).toBeTruthy();
    expect(api.updateProviderKeys.mock.calls.every(([body])=>body.action==='harness_profile')).toBe(true);
  });
});
