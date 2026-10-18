// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {useEffect,useRef,useState} from 'react';
import type {TwinPulseApi} from './api';
import type {ProductState} from './types';
import type {InspectionDisplay} from './conversation-types';

/** One historical display request, never Run, robot work or automatic retry. */
export function ChatInspectionBuild({api,display,product,report}:{api:TwinPulseApi;
  display:InspectionDisplay;product:ProductState|null;report:(text:string)=>void}){
  const consumed=useRef(false),alive=useRef(true),lease=useRef<string|null>(null);
  const [phase,setPhase]=useState('Waiting for Isaac · saved survey, not current robot position…');
  useEffect(()=>{alive.current=true;let renewing=false;
    const timer=setInterval(()=>{if(!lease.current||renewing)return;renewing=true;
      void api.renewLease(lease.current).catch(()=>{lease.current=null;}).finally(()=>{renewing=false;});},750);
    return()=>{alive.current=false;clearInterval(timer);lease.current=null;};},[api]);
  useEffect(()=>{
    if(!product?.engine_connected||consumed.current)return;
    consumed.current=true;
    const execute=async()=>{
      if(!display.ready||!display.scene_revision)throw new Error(display.code);
      const revision=display.scene_revision,request=crypto.randomUUID();
      const wait=()=>new Promise(resolve=>setTimeout(resolve,150));
      const open=()=>{if(!alive.current)throw new Error('Saved survey display closed; no retry.');};
      setPhase('Displaying the checked room revision and historical scan · no movement…');
      lease.current=(await api.acquireLease()).control_lease_id;open();
      let state=await api.productState();open();
      const untilReady=Date.now()+6000;
      while(!state.engine_readiness?.current_inspection_visual_v1?.ready&&Date.now()<untilReady){
        await wait();open();state=await api.productState();}
      if(!state.engine_readiness?.current_inspection_visual_v1?.ready)
        throw new Error('Isaac does not currently support this saved-survey display. No retry or movement.');
      // Always compose the overlay, even when unchanged geometry already matches.
      let op;
      try{op=await api.chatInspectionDisplay(display.descriptor,request);}
      catch(error){throw new Error(`Saved survey display delivery unconfirmed: ${String(error)}. Check operations; do not resend automatically.`);}
      const until=Date.now()+45000;let complete=false;
      while(Date.now()<until){open();state=await api.productState();
        if(state.engine_session_id!==op.engine_session_id||state.stage_epoch!==op.stage_epoch)
          throw new Error('Isaac identity changed during survey display; no retry.');
        const current=state.operations.find(item=>item.command_id===op.command_id);
        if(current?.status==='succeeded'){complete=true;break;}
        if(current&&!['accepted','running'].includes(current.status))throw new Error(current.receipt?.message??current.status);
        await wait();}
      if(!complete)throw new Error('Saved survey display receipt unconfirmed after 45 seconds; no retry.');
      const snapshotUntil=Date.now()+6000;
      while(Date.now()<snapshotUntil){open();state=await api.productState();
        if(state.engine_session_id!==op.engine_session_id||state.stage_epoch!==op.stage_epoch)
          throw new Error('Isaac identity changed after display receipt; no retry.');
        if(state.snapshot?.safety_state)throw new Error(state.snapshot.safety_reason??'Isaac safety condition.');
        if(state.engine_connected&&state.snapshot?.applied_revision===revision&&
          ['built','paused','completed'].includes(state.snapshot.runtime_state)){
          setPhase('Survey room displayed · historical scan and pose candidate, not current navigation permission.');return;}
        await wait();}
      throw new Error('Survey room snapshot not observed; no movement or automatic retry.');
    };
    void execute().catch(error=>{if(alive.current){setPhase('Survey display failed · no automatic retry.');report(String(error));}})
      .finally(()=>{lease.current=null;});
  },[api,display,product?.engine_connected,report]);
  return <section className="chat-tool-progress" aria-label="Saved survey display"><strong>Survey room · Isaac</strong><p role="status">{phase}</p></section>;
}
