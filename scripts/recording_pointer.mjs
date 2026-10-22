// SPDX-License-Identifier: Apache-2.0
// Recording-only presentation. Never dispatch input, prevent default or touch App state.
import {randomUUID} from 'node:crypto';
export function mountRecordingPointer(owner) {
 const key='__twinpulseRecordingPointerV1';
 if(window[key]){if(window[key].owner===owner)return {installed:true,existing:true};throw Error('RECORDING_POINTER_ALREADY_ACTIVE');}
 const host=document.createElement('div');host.dataset.tpRecordingPointer='1';
 host.setAttribute('aria-hidden','true');
 host.style.cssText='all:initial;position:fixed;left:0;top:0;width:64px;height:64px;z-index:2147483647;pointer-events:none!important;visibility:hidden;overflow:visible;contain:layout style;';
 const shadow=host.attachShadow({mode:'open'});
 shadow.innerHTML='<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64" style="pointer-events:none"><circle cx="24" cy="24" r="13" fill="#fbbf24" fill-opacity=".18" stroke="#fbbf24" stroke-opacity=".6"/><circle data-press-ring cx="24" cy="24" r="17" fill="none" stroke="#f59e0b" stroke-width="3" opacity="0"/><path transform="translate(22 22)" d="M2 2 L2 24 L8 19 L13 30 L19 27 L14 17 L23 17 Z" fill="white" stroke="#152536" stroke-width="2" stroke-linejoin="round"/></svg>';
 const ring=shadow.querySelector('[data-press-ring]');
 let timer=null,pulse=null,moves=0,presses=0,last=null;
 const removers=[];
 const listen=(target,name,fn)=>{target.addEventListener(name,fn,{capture:true,passive:true});removers.push(()=>target.removeEventListener(name,fn,true));};
 const accept=e=>e.isTrusted&&(!e.pointerType||e.pointerType==='mouse');
 const position=e=>{last={x:e.clientX,y:e.clientY};host.style.transform=`translate(${e.clientX-24}px,${e.clientY-24}px)`;host.style.visibility='visible';};
 const hide=()=>{host.style.visibility='hidden';host.dataset.down='false';pulse?.cancel();ring.setAttribute('opacity','0');clearTimeout(timer);};
 listen(document,'pointermove',e=>{if(accept(e)){moves++;position(e);}});
 listen(document,'pointerdown',e=>{if(!accept(e))return;position(e);presses++;host.dataset.down='true';
  pulse?.cancel();ring.setAttribute('opacity','1');clearTimeout(timer);
  pulse=ring.animate([{opacity:1},{opacity:.25}],{duration:900});
  // A recent-press annotation, not a claim that the button is still held.
  // 900ms also survives the recorder's 450ms sampling without changing its clock.
  timer=setTimeout(()=>ring.setAttribute('opacity','0'),900);
 });
 listen(document,'pointerup',e=>{if(accept(e)){position(e);host.dataset.down='false';}});
 listen(document,'pointercancel',hide);
 listen(document,'pointerout',e=>{if(e.relatedTarget===null)hide();});
 listen(window,'blur',hide);listen(window,'resize',hide);
 document.documentElement.append(host);
 window[key]={owner,snapshot:()=>({moves,presses,last}),remove:()=>{const value={moves,presses,last};
  clearTimeout(timer);pulse?.cancel();for(const remove of removers)remove();host.remove();delete window[key];return value;}};
 return {installed:true};
}

export async function installRecordingPointer(page) {
 const owner=randomUUID();
 const receipt={schema:'recording-pointer-1.0',enabled:true,native_os_cursor:false,
  source:'Actual trusted renderer mouse pointer events; recording-only DOM annotation, not product-state injection',
  appearance:'White/dark-outline arrow, faint amber halo, 900ms recent-press ring',
  affects_input:false,reconstructs_old_recordings:false,documents:0,errors:[]};
 let pending=Promise.resolve(),finished=false;
 const mount=async()=>{if(finished||page.isClosed())return;const result=await page.evaluate(mountRecordingPointer,owner);if(!result.existing)receipt.documents++;};
 await mount();
 const onDocument=()=>{pending=pending.then(mount).catch(()=>receipt.errors.push('POINTER_DOCUMENT_INSTALL_FAILED'));};
 page.on('domcontentloaded',onDocument);
 return async()=>{
  finished=true;page.off('domcontentloaded',onDocument);await pending;
  if(page.isClosed())receipt.cleanup='DOCUMENT_CLOSED';
  else try{receipt.observed_at_stop=await page.evaluate(id=>{const value=window.__twinpulseRecordingPointerV1;
    if(value?.owner!==id)throw Error('POINTER_OWNERSHIP_CHANGED');return value.remove();},owner);receipt.cleanup='REMOVED';}
   catch{receipt.cleanup='UNCONFIRMED_DOCUMENT_UNAVAILABLE';receipt.errors.push('POINTER_CLEANUP_UNCONFIRMED');}
  receipt.status=receipt.errors.length?'PARTIAL':'ANNOTATION_INSTALLED';return receipt;
 };
}
