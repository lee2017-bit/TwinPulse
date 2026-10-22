// SPDX-License-Identifier: Apache-2.0
// Passive same-renderer-turn observation; no product state or clock mutation.
export function checkScanDisplay(sample){
 if(!sample?.present||!sample.visible)throw Error('Current scan overlay absent at the atomic observation');
 if(sample.frame_live!==true||sample.preview_only!==false)throw Error('Scan overlay has no current frame receipt');
 if(!Number.isFinite(sample.captured_at_ms)||!Number.isFinite(sample.observed_at_ms)||
    sample.age_ms!==sample.observed_at_ms-sample.captured_at_ms||sample.age_ms<0||sample.age_ms>=700)
  throw Error('Stale scan displayed as current: '+JSON.stringify(sample));
 if(!Number.isInteger(sample.frame_id)||sample.frame_id<=0||!Number.isFinite(sample.frame_captured_at_ms)||
    sample.observed_at_ms-sample.frame_captured_at_ms<0||sample.observed_at_ms-sample.frame_captured_at_ms>=1000||
    ['robot_id','stage_epoch','scene_revision','connection_epoch','motion_epoch'].some(key=>typeof sample[key]!=='string'||!sample[key]))
  throw Error('Scan observation is missing frame or robot identity');
 return sample;
}
export function checkScanObservation(sample,window){
 if(!window||window.timeout_ms!==5000||window.deadline_ms-window.started_at_ms!==5000||
    !Number.isFinite(sample?.observed_at_ms)||!Number.isFinite(sample?.requested_at_ms)||!Number.isFinite(sample?.received_at_ms)||
    sample.requested_at_ms<window.started_at_ms||sample.observed_at_ms<sample.requested_at_ms||
    sample.received_at_ms<sample.observed_at_ms||sample.received_at_ms>window.deadline_ms)
  throw Error('Scan observation outside original visibility deadline');
 // Even absence may only wait on a current frame, not a preview or lost canvas.
 if(sample.frame_live!==true||sample.preview_only!==false||!Number.isInteger(sample.frame_id)||sample.frame_id<=0||
    !Number.isFinite(sample.frame_captured_at_ms)||sample.observed_at_ms-sample.frame_captured_at_ms<0||
    sample.observed_at_ms-sample.frame_captured_at_ms>=1000||!sample.stage_epoch||!sample.scene_revision)
  throw Error('Scan observation has no current frame');
 if(sample.present===false&&sample.visible===false&&sample.captured_at_ms===null&&sample.age_ms===null)return false;
 checkScanDisplay(sample);
 if(['robot_id','connection_epoch','motion_epoch'].some(key=>sample[key]!==window.expected?.[key]))throw Error('Scan epoch differs from selected robot');
 if(!Number.isInteger(sample.rays_count)||sample.rays_count<1||sample.rays_count>12||
    !Number.isInteger(sample.points_count)||sample.points_count<1||sample.points_count>90)throw Error('Unbounded or missing displayed scan geometry');
 return true;
}
export async function waitForScanDisplay(page,window,{record,sleep=()=>new Promise(resolve=>setTimeout(resolve,50)),clock=Date.now}){
 for(let count=0;count<128;count++){
  const requested=clock(),remaining=window.deadline_ms-requested;
  if(remaining<=0)throw Error('Scan observation visibility deadline exhausted');
  let timer;
  let sample;
  try{sample=await Promise.race([observeScanDisplay(page),new Promise((_,reject)=>{
   timer=setTimeout(()=>reject(Error('Scan observation visibility deadline exceeded')),remaining);
  })]);}finally{clearTimeout(timer);}
  sample={...sample,requested_at_ms:requested,received_at_ms:clock()};record(sample);
  if(checkScanObservation(sample,window))return sample;
  await sleep();
 }
 throw Error('Bounded scan visibility observation exhausted without a current scan');
}
export function observeScanDisplay(page){
 return page.evaluate(()=>{
  const overlay=document.querySelector('.robot-lidar-overlay'),canvas=document.querySelector('.twin-frame-slot canvas');
  const now=Date.now(),stamp=overlay?Number(overlay.getAttribute('data-scan-captured-at')):null;
  const rect=overlay?.getBoundingClientRect(),style=overlay?getComputedStyle(overlay):null;
  return {present:!!overlay,visible:!!rect&&rect.width>0&&rect.height>0&&style?.visibility==='visible'&&style?.display!=='none',
   observed_at_ms:now,captured_at_ms:stamp,age_ms:stamp===null?null:now-stamp,
   robot_id:overlay?.getAttribute('data-robot-id')??null,frame_id:canvas?Number(canvas.getAttribute('data-frame-id')):null,
   frame_captured_at_ms:canvas?Number(canvas.getAttribute('data-captured-at')):null,
   frame_live:canvas?.getAttribute('data-live')==='true',
   preview_only:canvas?.getAttribute('data-preview-only')==='false'?false:canvas?.getAttribute('data-preview-only')==='true'?true:null,
   stage_epoch:canvas?.getAttribute('data-stage-epoch')??null,scene_revision:canvas?.getAttribute('data-scene-revision')??null,
   connection_epoch:overlay?.getAttribute('data-connection-epoch')??null,motion_epoch:overlay?.getAttribute('data-motion-epoch')??null,
   rays_count:overlay?.querySelectorAll('line').length??0,points_count:overlay?.querySelectorAll('circle').length??0};
 });
}
