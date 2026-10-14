// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {act,render,screen,waitFor} from '@testing-library/react';
import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {AuthenticatedConversationImage} from './AuthenticatedConversationImage';
import type {TwinPulseApi} from './api';

const photo=()=>new Blob(['png'],{type:'image/png'});
function harness(){return {context:'first-context',conversationImage:vi.fn(async()=>photo())};}
describe('Authenticated conversation photos',()=>{
  let decode=vi.fn(async()=>{}),sequence=0;
  beforeEach(()=>{
    sequence=0;decode=vi.fn(async()=>{});
    vi.spyOn(URL,'createObjectURL').mockImplementation(()=>`blob:photo-${++sequence}`);
    vi.spyOn(URL,'revokeObjectURL').mockImplementation(()=>{});
    vi.stubGlobal('Image',class {src='';naturalWidth=800;naturalHeight=600;decode(){return decode();}});
  });
  afterEach(()=>vi.unstubAllGlobals());
  it('loads through the contextual API, checks decoded pixels and preserves the same photo across polling rerenders',async()=>{
    const api=harness(),url='/v1/product/conversation/image/source';
    const component=render(<AuthenticatedConversationImage api={api as unknown as TwinPulseApi} url={url} alt="Source photo"/>);
    expect(screen.getByRole('status').textContent).toContain('Loading photo');expect(screen.queryByRole('img')).toBeNull();
    const image=await screen.findByRole('img',{name:'Source photo'});
    expect(api.conversationImage).toHaveBeenCalledWith(url);expect(image.getAttribute('src')).toBe('blob:photo-1');
    expect(image.getAttribute('data-decoded-width')).toBe('800');expect(decode).toHaveBeenCalledOnce();
    component.rerender(<AuthenticatedConversationImage api={api as unknown as TwinPulseApi} url={url} alt="Source photo"/>);
    expect(screen.getByRole('img',{name:'Source photo'})).toBe(image);expect(api.conversationImage).toHaveBeenCalledOnce();
    expect(URL.revokeObjectURL).not.toHaveBeenCalled();component.unmount();expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:photo-1');
  });
  it('rejects a late response for a different photo without creating or displaying its blob URL',async()=>{
    const api=harness();let finish!:(blob:Blob)=>void;
    api.conversationImage.mockImplementationOnce(()=>new Promise<Blob>(resolve=>{finish=resolve;}));
    const component=render(<AuthenticatedConversationImage api={api as unknown as TwinPulseApi} url="/old" alt="Source photo"/>);
    component.rerender(<AuthenticatedConversationImage api={api as unknown as TwinPulseApi} url="/new" alt="Source photo"/>);
    const image=await screen.findByRole('img',{name:'Source photo'});
    await act(async()=>{finish(photo());});
    expect(screen.getByRole('img',{name:'Source photo'})).toBe(image);expect(URL.createObjectURL).toHaveBeenCalledOnce();component.unmount();
  });
  it('revokes a pending decode on context switch and ignores its late completion',async()=>{
    const api=harness();let finish!:()=>void;
    decode.mockImplementationOnce(()=>new Promise<void>(resolve=>{finish=resolve;}));
    const component=render(<AuthenticatedConversationImage api={api as unknown as TwinPulseApi} url="/photo" alt="Source photo"/>);
    await waitFor(()=>expect(decode).toHaveBeenCalledOnce());api.context='new-context';
    component.rerender(<AuthenticatedConversationImage api={api as unknown as TwinPulseApi} url="/photo" alt="Source photo"/>);
    const image=await screen.findByRole('img',{name:'Source photo'});expect(image.getAttribute('src')).toBe('blob:photo-2');
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:photo-1');
    await act(async()=>{finish();});expect(image.getAttribute('src')).toBe('blob:photo-2');
    expect(api.conversationImage).toHaveBeenCalledTimes(2);component.unmount();expect(URL.revokeObjectURL).toHaveBeenCalledTimes(2);
  });
  it('rejects a response if the API context changed before React observed the switch',async()=>{
    const api=harness();let finish!:(blob:Blob)=>void;
    api.conversationImage.mockImplementationOnce(()=>new Promise<Blob>(resolve=>{finish=resolve;}));
    const component=render(<AuthenticatedConversationImage api={api as unknown as TwinPulseApi} url="/photo" alt="Source photo"/>);
    api.context='new-context';await act(async()=>{finish(photo());});
    expect(URL.createObjectURL).not.toHaveBeenCalled();expect(screen.queryByRole('img')).toBeNull();component.unmount();
  });
  it.each(['request','decode','empty-pixels','invalid-type'])('shows a clear error and releases resources after %s failure',async failure=>{
    const api=harness();if(failure==='request')api.conversationImage.mockRejectedValue(new Error('Not accessible'));
    if(failure==='decode')decode.mockRejectedValue(new Error('Invalid image'));
    if(failure==='empty-pixels')vi.stubGlobal('Image',class {src='';naturalWidth=0;naturalHeight=0;decode(){return decode();}});
    if(failure==='invalid-type')api.conversationImage.mockResolvedValue(new Blob(['html'],{type:'text/html'}));
    const component=render(<AuthenticatedConversationImage api={api as unknown as TwinPulseApi} url="/photo" alt="Source photo"/>);
    expect((await screen.findByRole('alert')).textContent).toContain('Photo unavailable');expect(screen.queryByRole('img')).toBeNull();
    if(failure==='decode'||failure==='empty-pixels')expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:photo-1');
    else expect(URL.createObjectURL).not.toHaveBeenCalled();component.unmount();
  });
});
