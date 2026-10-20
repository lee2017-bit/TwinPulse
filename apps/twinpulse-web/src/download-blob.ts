// SPDX-License-Identifier: Apache-2.0
// Keep Blob data alive until the asynchronous browser download consumes it.
// No filesystem, network or navigation policy is relaxed.
export function downloadBlob(blob:Blob,filename:string){
  const url=URL.createObjectURL(blob),link=document.createElement('a');
  link.href=url;link.download=filename;link.hidden=true;
  document.body.append(link);
  try{link.click();}finally{
    setTimeout(()=>{link.remove();URL.revokeObjectURL(url);},60000);
  }
}
