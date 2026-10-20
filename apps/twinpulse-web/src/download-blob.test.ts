// SPDX-License-Identifier: Apache-2.0
import {afterEach,expect,it,vi} from 'vitest';
import {downloadBlob} from './download-blob';
afterEach(()=>{vi.useRealTimers();vi.unstubAllGlobals();vi.restoreAllMocks();document.querySelectorAll('a[download]').forEach(x=>x.remove());});
it('keeps large exports and their attached anchor alive through asynchronous transfer',()=>{
  vi.useFakeTimers();const revoke=vi.fn();vi.stubGlobal('URL',{createObjectURL:()=> 'blob:local-export',revokeObjectURL:revoke});
  const click=vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{});
  downloadBlob(new Blob(['x'.repeat(4*1024*1024)]),'robot-operation.json');
  expect(click).toHaveBeenCalledOnce();expect(document.querySelector('a[download]')).toBeTruthy();
  vi.advanceTimersByTime(59999);expect(revoke).not.toHaveBeenCalled();
  vi.advanceTimersByTime(1);expect(revoke).toHaveBeenCalledWith('blob:local-export');expect(document.querySelector('a[download]')).toBeNull();
});
