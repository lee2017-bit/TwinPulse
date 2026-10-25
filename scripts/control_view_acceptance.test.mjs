// SPDX-License-Identifier: Apache-2.0
// Synthetic DOM equivalence only. Not installed UI or physical evidence.
import test from 'node:test';
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
import {currentControlView,checkControlView} from './control_view_acceptance.mjs';

const baseline=process.env.TWINPULSE_CONTROL_VIEW_BASELINE
 ?await import(pathToFileURL(process.env.TWINPULSE_CONTROL_VIEW_BASELINE).href):null;
const box=(x,y,width,height)=>({x,y,width,height,left:x,top:y,right:x+width,bottom:y+height,
 toJSON(){const {toJSON,...value}=this;return value;}});
function fixture(change='valid'){
 const counts={styles:0,rects:0,hits:0},all=[];
 const el=(name,rect,parent=null)=>{
  const v={name,rect,parentElement:parent,dataset:{},textContent:name,attrs:{},
   style:{display:'block',visibility:'visible',opacity:'1',overflowX:'visible',overflowY:'visible'},
   getBoundingClientRect(){counts.rects++;return this.rect;},getAttribute(key){return this.attrs[key]??null;},
   contains(value){return value===this;},closest(selector){return selector==='.robot-anchor-layer'?layer:slot;}};
  all.push(v);return v;
 };
 const root=el('root',box(0,0,1600,900)),slot=el('slot',box(100,100,800,300),root);
 const layer=el('layer',box(100,100,800,300),slot),canvas=el('canvas',box(100,100,800,300),slot);
 canvas.dataset={frameId:'3',capturedAt:String(1000000-400),live:'true',sceneRevision:'scene',stageEpoch:'stage'};
 const dock=el('dock',box(100,450,800,400),root);dock.attrs['aria-label']='Control Alpha';
 const stop=el('Stop',box(850,460,40,30),dock),pad=el('pad',box(120,520,200,120),dock);
 const directions=[0,1,2,3].map(i=>el('direction'+i,box(130+i*40,550,30,30),pad));
 const badge=el('badge',box(415,222,50,14),layer);badge.attrs['aria-label']='Select Alpha in Twin';
 badge.dataset={screenBounds:'[0.4,0.3,0.45,0.4]',robotId:'alpha'};
 let badges=[badge],origin=[];
 const blockers={};
 dock.querySelector=s=>s==='.robot-fleet-pad'?pad:null;
 dock.querySelectorAll=s=>s==='button'?[stop,...directions]:s==='.robot-fleet-pad button'?directions:[];
 const document={querySelector:s=>s==='.twin-frame-slot canvas'?canvas:null,
  querySelectorAll:s=>s==='.robot-fleet-drawer'?[dock]:s==='.robot-anchor-badge'?badges:
   s==='.robot-frame-origin-dot'?origin:s==='.robot-anchor-layer'?[layer]:[],
  elementFromPoint(x,y){counts.hits++;if(blockers.stop&&x>stop.rect.left+25&&y>stop.rect.top+18)return root;
   return [stop,...directions].find(e=>x>=e.rect.left&&x<=e.rect.right&&y>=e.rect.top&&y<=e.rect.bottom)??root;}};
 if(change==='clipped-pad'){pad.style.overflowX='hidden';pad.rect=box(120,520,30,120);}
 if(change==='hidden-ancestor')root.style.visibility='hidden';
 if(change==='occluded-stop')blockers.stop=true;
 if(change==='detached-label')badge.rect=box(430,240,50,14);
 if(change==='overlapping-label')badge.rect=box(415,205,50,14);
 if(change==='origin-circle')origin=[{}];
 if(change==='missing-badge')badges=[];
 if(change==='missing-direction')directions.pop();
 if(change==='overlapping-dock')dock.rect=box(100,300,800,400);
 if(change==='offscreen-stop')stop.rect=box(1590,460,40,30);
 if(change==='not-live')canvas.dataset.live='false';
 if(change==='999.999')canvas.dataset.capturedAt=String(1000000-999.999);
 if(change==='1000')canvas.dataset.capturedAt=String(1000000-1000);
 if(change==='future')canvas.dataset.capturedAt=String(1000000+1);
 return {counts,all,root,canvas,document};
}
async function measured(fn,fixture){
 const oldNow=Date.now,keys=['document','getComputedStyle','innerWidth','innerHeight','devicePixelRatio'];
 const old=keys.map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)]);
 try{
  Date.now=()=>1000000;
  Object.assign(globalThis,{document:fixture.document,getComputedStyle:e=>{fixture.counts.styles++;return e.style;},
   innerWidth:1600,innerHeight:900,devicePixelRatio:1});
  return await fn({evaluate:async(f,name)=>f(name)},'Alpha');
 }finally{Date.now=oldNow;for(const [key,descriptor] of old){if(descriptor)Object.defineProperty(globalThis,key,descriptor);else delete globalThis[key];}}
}
const cases=['valid','clipped-pad','hidden-ancestor','occluded-stop','detached-label','overlapping-label',
 'origin-circle','missing-badge','missing-direction','overlapping-dock','offscreen-stop','not-live','999.999','1000','future'];
for(const scenario of cases)test('unchanged predicates: '+scenario,async()=>{
 const f=fixture(scenario),value=await measured(currentControlView,f);
 if(['valid','999.999'].includes(scenario))assert.doesNotThrow(()=>checkControlView(value));
 else assert.throws(()=>checkControlView(value));
 assert.equal(value.at,value.measurement.frame_snapshot_at);
 assert.equal(value.frame_age_ms,value.at-value.captured_at_ms);
 assert.ok(value.measurement.duration_ms>=0);
 assert.equal(value.measurement.ended_at,1000000);
});
test('no cache survives a measurement call',async()=>{
 const f=fixture(),first=await measured(currentControlView,f);
 assert.doesNotThrow(()=>checkControlView(first));
 f.root.style.visibility='hidden';
 const second=await measured(currentControlView,f);
 assert.throws(()=>checkControlView(second));
});
test('exact old/new frozen-clock outputs; fewer repeated reads, same hit tests',{skip:!baseline},async()=>{
 for(const scenario of cases){
  const before=fixture(scenario),after=fixture(scenario);
  const a=await measured(baseline.currentControlView,before),b=await measured(currentControlView,after);
  const {measurement,...actual}=b;
  assert.deepEqual(actual,a,scenario);
  assert.equal(after.counts.hits,before.counts.hits,scenario);
  assert.ok(after.counts.styles<=before.counts.styles,scenario);
  assert.ok(after.counts.rects<before.counts.rects,scenario);
 }
});
