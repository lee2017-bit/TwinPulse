// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {afterEach,expect,it,vi} from 'vitest';
import {TwinPulseApi} from './api';
afterEach(()=>{vi.unstubAllGlobals();sessionStorage.clear();});
it('loads the authenticated thumbnail using the selected context header',async()=>{
  const calls=vi.fn(async(path:string,_init?:RequestInit)=>path==='/v1/product/session'?
    new Response(JSON.stringify({csrf_token:'csrf',context_id:'ctx-a',project_id:'a'}),
      {headers:{'Content-Type':'application/json','X-TwinPulse-Context':'ctx-a'}}):
    new Response(new Uint8Array([1,2,3]),{headers:{'Content-Type':'image/png','X-TwinPulse-Context':'ctx-a'}}));
  vi.stubGlobal('fetch',calls);const api=new TwinPulseApi();await api.bootstrap();
  const image=await api.conversationImage('/v1/product/conversation/image/message-1');
  expect(image.type).toBe('image/png');expect(image.size).toBe(3);
  expect(calls.mock.calls[1][1]).toMatchObject({credentials:'same-origin',cache:'no-store',headers:{'X-TwinPulse-Context':'ctx-a'}});
});
it('does not fetch an external URL or query-bearing thumbnail',async()=>{
  const calls=vi.fn();vi.stubGlobal('fetch',calls);const api=new TwinPulseApi();
  for(const path of ['https://example.com/photo.png','/v1/product/conversation/image/id?token=secret'])
    await expect(api.conversationImage(path)).rejects.toMatchObject({code:'conversation_image_invalid'});
  expect(calls).not.toHaveBeenCalled();
});
it('rejects an unexpected response MIME instead of displaying arbitrary content',async()=>{
  vi.stubGlobal('fetch',vi.fn(async()=>new Response('not a PNG',{headers:{'Content-Type':'text/html'}})));
  await expect(new TwinPulseApi().conversationImage('/v1/product/conversation/image/id')).rejects.toMatchObject({code:'conversation_image_invalid'});
});
