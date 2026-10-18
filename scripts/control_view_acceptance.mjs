// SPDX-License-Identifier: Apache-2.0
// Read-only DOM measurements in the real installed BrowserWindow, no API writes.
export async function currentControlView(page,name){
 return page.evaluate(name=>{
  const canvas=document.querySelector('.twin-frame-slot canvas'),dock=[...document.querySelectorAll('.robot-fleet-drawer')].find(e=>e.getAttribute('aria-label')==='Control '+name);
  if(!canvas||!dock)throw Error('Actual viewport/controller missing');
  const c=canvas.getBoundingClientRect(),d=dock.getBoundingClientRect();
  const intersection=Math.max(0,Math.min(c.right,d.right)-Math.max(c.left,d.left))*Math.max(0,Math.min(c.bottom,d.bottom)-Math.max(c.top,d.top));
  const stop=[...dock.querySelectorAll('button')].find(e=>e.textContent.trim()==='Stop'),pad=dock.querySelector('.robot-fleet-pad');
  const shown=e=>{if(!e)return false;const r=e.getBoundingClientRect();
   if(r.width<=0||r.height<=0||r.top<0||r.left<0||r.bottom>innerHeight+1||r.right>innerWidth+1)return false;
   for(let parent=e;parent;parent=parent.parentElement){const style=getComputedStyle(parent);if(style.display==='none'||style.visibility!=='visible'||Number(style.opacity)===0)return false;
    const box=parent.getBoundingClientRect();if(['hidden','clip','auto','scroll'].includes(style.overflowX)&&(r.left<box.left-1||r.right>box.right+1))return false;
    if(['hidden','clip','auto','scroll'].includes(style.overflowY)&&(r.top<box.top-1||r.bottom>box.bottom+1))return false;
   }return true;
  };
  const hit=e=>{if(!shown(e))return false;const r=e.getBoundingClientRect();return [[.5,.5],[.2,.2],[.8,.2],[.2,.8],[.8,.8]].every(([x,y])=>e.contains(document.elementFromPoint(r.left+r.width*x,r.top+r.height*y)));};
  const directions=[...dock.querySelectorAll('.robot-fleet-pad button')];
  const badge=[...document.querySelectorAll('.robot-anchor-badge')].find(e=>e.getAttribute('aria-label')==='Select '+name+' in Twin');
  const bounds=badge?.dataset.screenBounds?JSON.parse(badge.dataset.screenBounds):null;
  const labels=[...document.querySelectorAll('.robot-anchor-badge')],layer=badge?.closest('.robot-anchor-layer')?.getBoundingClientRect();
  let badgeBodyOverlap=0;
  if(layer)for(const label of labels)for(const other of labels){const b=JSON.parse(other.dataset.screenBounds??'null');
   if(!b||b.length!==4||b[2]<=b[0]||b[3]<=b[1])continue;const plate=label.getBoundingClientRect();
   badgeBodyOverlap+=Math.max(0,Math.min(plate.right,layer.left+b[2]*layer.width)-Math.max(plate.left,layer.left+b[0]*layer.width))*
    Math.max(0,Math.min(plate.bottom,layer.top+b[3]*layer.height)-Math.max(plate.top,layer.top+b[1]*layer.height));}
  return {at:Date.now(),frame_id:Number(canvas.dataset.frameId),captured_at_ms:Number(canvas.dataset.capturedAt),
   frame_age_ms:Date.now()-Number(canvas.dataset.capturedAt),live:canvas.dataset.live==='true',scene_revision:canvas.dataset.sceneRevision,
   stage_epoch:canvas.dataset.stageEpoch,canvas_visible:shown(canvas),canvas:{x:c.x,y:c.y,width:c.width,height:c.height},
   dock:{x:d.x,y:d.y,width:d.width,height:d.height},intersection_px2:intersection,stop_visible:hit(stop),pad_visible:shown(pad)&&directions.length===4&&directions.every(hit),
   robot_badge_visible:shown(badge),robot_bounds:bounds,badge_body_overlap_px2:badgeBodyOverlap,window:{width:innerWidth,height:innerHeight,devicePixelRatio}};
 },name);
}
export function checkControlView(value,{fresh=true,robot=true}={}){
 if(!value.canvas_visible||value.canvas.height<150||!value.stop_visible||!value.pad_visible||value.intersection_px2>0)throw Error('Control obscures/clips viewport or Stop/pad: '+JSON.stringify(value));
 if(fresh&&(!value.live||!Number.isFinite(value.frame_id)||!Number.isFinite(value.frame_age_ms)||value.frame_age_ms<0||value.frame_age_ms>=1000))throw Error('Motion display is not current: '+JSON.stringify(value));
 if(robot&&(!value.robot_badge_visible||!value.robot_bounds||value.robot_bounds.length!==4||value.robot_bounds.some(n=>!Number.isFinite(n)||n<0||n>1)||value.robot_bounds[2]<=value.robot_bounds[0]||value.robot_bounds[3]<=value.robot_bounds[1]))throw Error('Selected rendered robot not visible: '+JSON.stringify(value));
 if(robot&&value.badge_body_overlap_px2>0)throw Error('Name plate overlaps a projected robot envelope: '+JSON.stringify(value));
}
export async function visibleMotion(page,name,condition,{duration=0,timeout=15000,onSample=()=>{}}={}){
 const began=Date.now();let first=null,last=null,count=0;
 while(true){
  const value=await currentControlView(page,name);checkControlView(value);onSample(value);count++;
  if(!first)first=value;last=value;
  if((duration?Date.now()-began>=duration:condition()))break;
  if(Date.now()-began>timeout)throw Error('Visible motion did not finish in its original timeout');
  await new Promise(resolve=>setTimeout(resolve,200));
 }
 if(!Number.isFinite(last.frame_id)||!Number.isFinite(first.frame_id)||last.frame_id<=first.frame_id)throw Error('No decoded-frame advancement during motion');
 return {first,last,samples:count,duration_ms:Date.now()-began};
}
