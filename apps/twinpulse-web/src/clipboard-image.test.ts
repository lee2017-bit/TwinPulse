// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {describe,it,expect,vi} from 'vitest';
import {clipboardImage} from './clipboard-image';
const data=(files:File[]=[],items:object[]=[],html='')=>({files,items,getData:()=>html}) as unknown as DataTransfer;
describe('Clipboard image bytes without network or OS clipboard reads',()=>{
  it('reads FileList and items-only representations without requiring a second copy',()=>{
    const image=new File(['pixels'],'clipboard.png',{type:'image/png'});
    expect(clipboardImage(data([image])).image).toBe(image);
    expect(clipboardImage(data([],[{kind:'file',type:'image/png',getAsFile:()=>image}])).image).toBe(image);
    expect(clipboardImage(data([image],[{kind:'file',type:'image/png',getAsFile:()=>image}])).image).toBe(image);
  });
  it('normalizes a MIME-less copied image filename but never relabels a known non-image MIME',()=>{
    const image=new File(['pixels'],'Copied.JPG');
    expect(clipboardImage(data([image])).image?.type).toBe('image/jpeg');
    expect(clipboardImage(data([new File(['not an image'],'wrong.png',{type:'text/plain'})])).image).toBeUndefined();
  });
  it('accepts embedded image bytes without evaluating or loading HTML',()=>{
    const result=clipboardImage(data([],[],`<div><img src="data:image/png;base64,cGl4ZWxz" onerror="alert(1)"></div>`));
    expect(result.image?.type).toBe('image/png');expect(result.image?.size).toBe(6);
  });
  it('does not fetch a remote/private image URL, blob URL or plain text',()=>{
    const fetcher=vi.spyOn(globalThis,'fetch');
    for(const url of ['https://example.org/room.jpg','http://127.0.0.1/private','blob:other-document']){
      const result=clipboardImage(data([],[],`<img src="${url}">`));
      expect(result.image).toBeUndefined();expect(result.message).toContain('not image bytes');
    }
    expect(clipboardImage(data([],[],'<b>Text only</b>'))).toEqual({});expect(fetcher).not.toHaveBeenCalled();fetcher.mockRestore();
  });
  it('rejects multiple image files or HTML images instead of silently discarding one',()=>{
    const image=new File(['pixels'],'clipboard.png',{type:'image/png'});
    expect(clipboardImage(data([image,image])).message).toContain('one image');
    expect(clipboardImage(data([],[],`<img src="data:image/png;base64,YQ=="><img src="data:image/png;base64,Yg==">`)).message).toContain('one image');
  });
  it('does not allocate unbounded inline clipboard images',()=>{
    expect(clipboardImage(data([],[],'x'.repeat(14*1024*1024+1))).message).toContain('too large');
  });
});
