// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {useEffect,useRef,useState} from 'react';
import type {TwinPulseApi} from './api';
import type {ProductState} from './types';

/** Render a fresh, acknowledged REAL room. Never starts Run or robot work.
 * This component is deliberately not armed by restored conversation history. */
export function ChatRoomBuild({api,build,product,report}:{api:TwinPulseApi;
  build:{operation_id:string;scene_revision:string;artifact_id:string};product:ProductState|null;report:(text:string)=>void}){
  const consumed=useRef(false);
  const alive=useRef(true);
  const lease=useRef<string|null>(null);
  const [phase,setPhase]=useState('Waiting for Isaac to display this room…');
  useEffect(()=>{alive.current=true;let renewing=false;
    const timer=setInterval(()=>{if(!lease.current||renewing)return;renewing=true;
      void api.renewLease(lease.current).catch(()=>{lease.current=null;}).finally(()=>{renewing=false;});},750);
    return()=>{alive.current=false;clearInterval(timer);lease.current=null;};
  },[api]);
  useEffect(()=>{
    if(!product?.engine_connected||consumed.current)return;
    consumed.current=true;
    const execute=async()=>{
      const revision=build.scene_revision;
      const wait=()=>new Promise(resolve=>setTimeout(resolve,150));
      const assertOpen=()=>{if(!alive.current)throw new Error('Room view closed; no automatic retry.');};
      assertOpen();setPhase('Preparing the current room in Isaac · no robot movement…');
      const acquired=await api.acquireLease();lease.current=acquired.control_lease_id;
      assertOpen();await api.acknowledge(revision);
      let state=await api.productState();assertOpen();
      if(state.snapshot?.applied_revision!==revision){
        const readyUntil=Date.now()+6000;
        while(!state.engine_readiness?.site_scene_build_v2?.ready&&Date.now()<readyUntil){
          await wait();assertOpen();state=await api.productState();}
        if(!state.engine_readiness?.site_scene_build_v2?.ready)throw new Error('Isaac Build readiness unavailable. No robot work started.');
        assertOpen();
        // Send at most one Build. Unknown delivery is reported, never resent.
        const op=await api.command('build_site_scene',revision,build.artifact_id);
        const until=Date.now()+45000;let complete=false;
        while(Date.now()<until){
          assertOpen();state=await api.productState();
          const current=state.operations.find(item=>item.command_id===op.command_id);
          if(current?.status==='succeeded'){complete=true;break;}
          if(current&&!['accepted','running'].includes(current.status))throw new Error(current.receipt?.message??current.status);
          await wait();
        }
        if(!complete)throw new Error('Room Build receipt unconfirmed after 45 seconds. Check the saved operation; no retry.');
      }
      const until=Date.now()+6000;
      while(Date.now()<until){
        assertOpen();state=await api.productState();
        if(state.snapshot?.safety_state)throw new Error(state.snapshot.safety_reason??'Isaac safety condition blocks this room.');
        if(state.engine_connected&&state.snapshot?.applied_revision===revision&&
          ['built','paused','completed'].includes(state.snapshot.runtime_state)){
          setPhase('Current room displayed in Isaac. Robot inspection is a separate confirmation.');return;}
        await wait();
      }
      throw new Error('Current room snapshot not observed. Inspection stays locked; no robot work started.');
    };
    void execute().catch(error=>{if(alive.current){setPhase('Room display needs attention · no automatic retry.');report(String(error));}})
      .finally(()=>{lease.current=null;});
  },[api,build,product?.engine_connected,report]);
  return <section className="chat-tool-progress" aria-label="Current REAL room display"><strong>Current room · Isaac</strong><p role="status">{phase}</p></section>;
}
