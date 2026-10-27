// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
import {useEffect,useState} from 'react';
import type {EnvironmentObstacle,EnvironmentState,EnvironmentCandidateRef} from './environment-types';

const presets:Record<string,[number,number,number]>={floor_fan:[.4,.4,1.1],basket:[.35,.3,.4],bag:[.3,.25,.35],box:[.3,.3,.3],
  clothing_pile:[.35,.25,.15],cable_bundle:[.3,.2,.04],power_adapter:[.12,.08,.05],power_strip:[.3,.08,.05],small_equipment:[.3,.3,.3],unknown:[.3,.3,.3]};
// Why a candidate has no suggested spot beside the object the photo model named (local placement, never a model coordinate).
const unplaced:Record<string,string>={NO_ANCHOR:'the photo model named no neighbouring scanned or added object',ANCHOR_NOT_FOUND:'the named neighbour is not in the current scene',
  ANCHOR_AMBIGUOUS:'several objects share the named neighbour',NO_FREE_FLOOR_NEAR_ANCHOR:'no free floor beside the named neighbour',
  COVERING_NOT_SUGGESTED:'coverings are placed by hand',ALREADY_ADDED:'already added'};
export function EnvironmentObstacles({state,disabled,preview,remove,invalidate,analyze,cancelPhoto,addAll,batch}:{state:EnvironmentState;disabled:boolean;
  preview:(obstacle:EnvironmentObstacle,photo:File|null,candidate?:EnvironmentCandidateRef,replaceId?:string)=>void;remove:(id:string)=>void;invalidate:()=>void;
  analyze:(photo:File)=>void;cancelPhoto:(id:string)=>void;addAll?:(ids:string[])=>void;batch?:{running:boolean;status:string|null}}){
  const [kind,setKind]=useState('basket'),[label,setLabel]=useState('Basket'),[xy,setXY]=useState(['0','0']);
  const [size,setSize]=useState(['.35','.3','.4']),[yaw,setYaw]=useState('0'),[margin,setMargin]=useState('.2'),[autoMargin,setAutoMargin]=useState(false);
  const [photo,setPhoto]=useState<File|null>(null),[url,setURL]=useState('');
  const [consent,setConsent]=useState(false),[candidate,setCandidate]=useState<EnvironmentCandidateRef|undefined>(),[duplicate,setDuplicate]=useState(false),[photoSHA,setPhotoSHA]=useState('');
  const [batchReviewed,setBatchReviewed]=useState(false);
  const [replaceId,setReplaceId]=useState('');const unknownBoxes=state.objects.filter(o=>o.id.startsWith('Added_'));  // added estimates only (LiDAR outline, manual, photo), never scanned meshes
  const proposal=state.photo_proposal;
  const reviewed=proposal?.job_id===candidate?.job_id?proposal?.candidates.find(c=>c.id===candidate?.candidate_id):undefined;
  // Leaving a review restores the default uncertainty when a furniture Review set .05 and the user did not type a value.
  const endReview=()=>{setCandidate(undefined);if(autoMargin){setMargin('.2');setAutoMargin(false);}};
  useEffect(()=>{let active=true;setPhotoSHA('');if(photo&&crypto.subtle&&typeof photo.arrayBuffer==='function'){
    void photo.arrayBuffer().then(bytes=>crypto.subtle.digest('SHA-256',bytes)).then(hash=>{if(active)setPhotoSHA(Array.from(new Uint8Array(hash),b=>b.toString(16).padStart(2,'0')).join(''));}).catch(()=>{});
  }return()=>{active=false;};},[photo]);
  useEffect(()=>{if(!photo||typeof URL.createObjectURL!=='function'){setURL('');return;}
    const next=URL.createObjectURL(photo);setURL(next);return()=>URL.revokeObjectURL(next);},[photo]);
  const numeric=[...xy,...size,yaw,margin],valid=numeric.every(v=>v.trim()&&Number.isFinite(Number(v)))&&size.every(v=>Number(v)>0&&Number(v)<=3)&&Number(margin)>=.05&&Number(margin)<=1&&Math.abs(Number(yaw))<=180;
  const added=state.objects.filter(o=>o.added);
  const triangles=state.floor_triangles_xy??[],points=triangles.flat();
  const bounds=points.length?[Math.min(...points.map(p=>p[0])),Math.min(...points.map(p=>p[1])),Math.max(...points.map(p=>p[0])),Math.max(...points.map(p=>p[1]))]:null;
  const extent=bounds?Math.max(bounds[2]-bounds[0],bounds[3]-bounds[1])+.4:1;
  return <details className="environment-obstacles"><summary>Added obstacles · {added.length}</summary>
    <p>Keep the scanned room. Add missing objects (furniture or floor props) as estimated boxes from the photo-room catalog.</p>
    <small>Photo recognition is optional. Placement and size are estimates, not automatic photo-to-room alignment. These edits do not grant physical driving authority.</small>
    {proposal?.status==='running'&&<p role="status">Analyzing one photo · no automatic retry or Apply. {proposal.model_id??'Configured photo observer'}</p>}
    {proposal?.error&&<p role="alert">Photo analysis: {proposal.error}</p>}
    {proposal?.status==='running'&&proposal.job_id&&<button type="button" onClick={()=>cancelPhoto(proposal.job_id!)}>Cancel photo analysis</button>}
    <fieldset disabled={disabled}><legend>New obstacle</legend>
      {bounds&&<><small>Click to place the center · top view, scene axes. Gray: imported bounds. Amber: added estimates.</small>
        <svg aria-label="Obstacle placement map" role="img" viewBox={`${bounds[0]-.2} ${-bounds[3]-.2} ${extent} ${extent}`}
          style={{display:'block',width:'100%',maxWidth:300,aspectRatio:'1',background:'#e5edf1',cursor:disabled?'default':'crosshair'}}
          onClick={e=>{if(disabled)return;const matrix=e.currentTarget.getScreenCTM();if(!matrix)return;
            const p=new DOMPoint(e.clientX,e.clientY).matrixTransform(matrix.inverse());setXY([p.x.toFixed(3),(-p.y).toFixed(3)]);invalidate();}}>
          {triangles.map((t,i)=><polygon key={i} points={t.map(([x,y])=>`${x},${-y}`).join(' ')} fill="#fff"/>)}
          {state.objects.filter(o=>o.category!=='floor'&&o.dimensions_m).map(o=>{const [x,y]=o.position_m,[w,d]=o.dimensions_m!;
            return <rect key={o.id} x={x-w/2} y={-y-d/2} width={w} height={d} fill={o.added?'#d58d35':'#6e7a83'} opacity=".65"><title>{o.label} · bounds</title></rect>;})}
          {proposal?.status==='ready'&&proposal.candidates.map(c=>c.suggested&&<polygon key={'suggested-'+c.id} points={c.suggested.envelope_xy.map(([x,y])=>`${x},${-y}`).join(' ')}
            fill="none" stroke="#c94f15" strokeWidth={extent*.006} strokeDasharray={`${extent*.02} ${extent*.012}`}><title>{c.id} · suggested next to {c.suggested.anchor} · estimate</title></polygon>)}
          {Number.isFinite(Number(xy[0]))&&Number.isFinite(Number(xy[1]))&&<circle cx={Number(xy[0])} cy={-Number(xy[1])} r={extent*.015} fill="#c94f15"/>}
        </svg></>}
      <label className="library-field">Reference photo (optional)<input aria-label="Obstacle reference photo" type="file" accept=".jpg,.jpeg,.png,.webp" onChange={e=>{setPhoto(e.target.files?.[0]??null);setConsent(false);endReview();setDuplicate(false);invalidate();e.target.value='';}}/></label>
      {photo&&<p>{photo.name} · stored locally on Preview or Analyze <button type="button" onClick={()=>{setPhoto(null);setConsent(false);endReview();invalidate();}}>Remove reference</button></p>}
      {url&&<div style={{position:'relative',display:'table',maxWidth:'100%'}}><img src={url} alt="Local obstacle reference" style={{display:'block',maxWidth:'100%',maxHeight:240,objectFit:'contain'}}/>
        {proposal?.status==='ready'&&proposal.photo?.sha256===photoSHA&&proposal.candidates.map(c=><span key={c.id} style={{position:'absolute',pointerEvents:'none',boxSizing:'border-box',left:`${c.bbox[0]*100}%`,top:`${c.bbox[1]*100}%`,width:`${(c.bbox[2]-c.bbox[0])*100}%`,height:`${(c.bbox[3]-c.bbox[1])*100}%`,border:'2px solid #eea22c',color:'#fff',fontSize:11,textShadow:'0 1px 2px #000'}}>{c.id}</span>)}</div>}
      <label className="library-field"><span><input aria-label="Allow photo analysis" type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/> Send this photo and scanned object names/types to the configured observer · one call, no automatic retry.</span></label>
      <button type="button" disabled={!photo||!consent||!/\.(jpe?g|png)$/i.test(photo.name)} onClick={()=>{if(photo){setConsent(false);endReview();invalidate();analyze(photo);}}}>Analyze photo</button>
      <small>Only this photo and the names/types of scanned objects and added estimates are sent. No USD geometry, robot logs or room coordinates. WebP stays local; use JPEG/PNG for analysis.</small>
      {proposal?.status==='ready'&&<section aria-label="Photo obstacle candidates">
        <strong>Photo candidates · {proposal.candidates.length}</strong><p>{proposal.explanation}</p>
        <small>{proposal.photo?.source_name} · {proposal.model_id}. Recognition confidence is not metric accuracy. Check duplicates; a suggested center beside the named neighbour is an estimate, otherwise place it explicitly.</small>
        {proposal.candidates.map(c=><div key={c.id} style={{marginBlock:8,borderBottom:'1px solid #ddd',overflowWrap:'anywhere'}}>
          <strong>{c.label}</strong> · {c.kind.replaceAll('_',' ')} · recognition {Math.round(c.confidence*100)}%<small>{c.description}</small>
          {c.possible_duplicates.length>0&&<small> Possible duplicate of: {c.possible_duplicates.join(', ')}</small>}
          {!c.addable&&<small> Recognised only: not added to an imported space.</small>}
          {c.suggested?<small> Suggested: next to {c.suggested.anchor} · {c.suggested.gap_m.toFixed(2)} m gap · estimate</small>:
            c.addable&&c.suggestion_reason&&unplaced[c.suggestion_reason]&&<small> No suggested spot: {unplaced[c.suggestion_reason]}. Place the center on the map.</small>}
          {c.addable&&c.overlay_kind!==c.kind&&<small> Added as a labelled box (unknown kind, catalog size). Against a wall: keep the center at least half the depth + 0.15 m away.</small>}
          {/* Furniture becomes an unknown box, which already adds a 0.10 m keepout, so its uncertainty starts at the minimum; other kinds keep the current value. */}
          <button type="button" disabled={!c.addable} onClick={()=>{setCandidate({job_id:proposal.job_id!,candidate_id:c.id});setKind(c.overlay_kind!);setLabel(c.label);setSize(c.dimensions_m.map(String));
            const s=c.suggested,furniture=c.overlay_kind==='unknown'&&c.kind!=='unknown';
            // A suggestion pre-fills the exact numbers the server checked beside the anchor; without one the center stays manual.
            if(s){setXY([String(s.position_m[0]),String(s.position_m[1])]);setYaw(String(s.yaw_deg));setMargin(String(s.uncertainty_m));setAutoMargin(true);}
            else{setXY(['','']);setYaw('0');if(furniture||autoMargin)setMargin(furniture?'.05':'.2');setAutoMargin(furniture);}
            setDuplicate(false);invalidate();}}>Review {c.id}</button>
        </div>)}
        {(()=>{const ready=proposal.candidates.filter(c=>c.batch_addable&&c.suggested),n=ready.length;return n>0&&addAll&&<div>
          <label><input aria-label="Suggested objects duplicate reviewed" type="checkbox" checked={batchReviewed} onChange={e=>setBatchReviewed(e.target.checked)}/> I checked that {n===1?'this suggested object is':`these ${n} suggested objects are`} not already represented.</label>
          <button type="button" disabled={!batchReviewed||!!batch?.running} onClick={()=>{setBatchReviewed(false);endReview();setDuplicate(false);invalidate();addAll(ready.map(c=>c.id));}}>Add {n} suggested object{n===1?'':'s'}</button>
          <small>Each one goes through its own preview and Apply in order (Engine ACK, Undo available); the first refusal stops the rest. Positions are estimates.</small></div>;})()}
        {batch?.status&&<p role="status">{batch.status}</p>}
      </section>}
      {candidate&&<><p role="status">Reviewing {candidate.candidate_id} · {reviewed?.suggested?`Placed next to ${reviewed.suggested.anchor} from the photo (estimate) · click the map or edit X/Y to adjust; the robot LiDAR refines it.`:'set the center on the map.'} Catalog size is an estimate.</p>
        {unknownBoxes.length>0&&reviewed&&reviewed.overlay_kind===reviewed.kind&&<label>Replace an added estimate box with this photo object <select aria-label="Replace LiDAR unknown box" value={replaceId} onChange={e=>{const id=e.target.value;setReplaceId(id);
          // The Twin edit contract allows one object per edit, so a replacement is two edits: the box is
          // removed first (preview + Apply), then this photo object is placed at the box's position.
          const box=unknownBoxes.find(o=>o.id===id);if(box?.position_m){setXY([box.position_m[0].toFixed(3),box.position_m[1].toFixed(3)]);setDuplicate(true);remove(id);}invalidate();}}>
          <option value="">Keep as a new object</option>{unknownBoxes.map(o=><option key={o.id} value={o.id}>{o.label}</option>)}</select>
          <small> Two Twin edits: Apply the removal, then Preview obstacle and Apply the photo object at the same spot.</small></label>}
        <label><input aria-label="Candidate duplicate reviewed" type="checkbox" checked={duplicate} onChange={e=>{setDuplicate(e.target.checked);invalidate();}}/> I checked that this object is not already represented.</label>
        <button type="button" onClick={()=>{endReview();setDuplicate(false);invalidate();}}>Use manual entry</button></>}
      <label className="library-field">Type<select aria-label="Obstacle type" value={kind} onChange={e=>{const k=e.target.value;setKind(k);setLabel(k.replaceAll('_',' '));setSize(presets[k].map(String));endReview();setDuplicate(false);invalidate();}}>
        {Object.keys(presets).map(k=><option key={k} value={k}>{k.replaceAll('_',' ')}</option>)}</select></label>
      <label className="library-field">Name<input aria-label="Obstacle name" maxLength={120} value={label} onChange={e=>{setLabel(e.target.value);invalidate();}}/></label>
      <div className="library-position">{['X','Y'].map((axis,i)=><label key={axis}>Center {axis} (m)<input aria-label={`Obstacle ${axis}`} type="number" step="any" value={xy[i]} onChange={e=>{setXY(v=>v.map((n,j)=>j===i?e.target.value:n));invalidate();}}/></label>)}</div>
      <div className="library-position">{['width','depth','height'].map((axis,i)=><label key={axis}>{axis} (m)<input aria-label={`Obstacle ${axis}`} type="number" min="0.01" max="3" step="any" value={size[i]} onChange={e=>{setSize(v=>v.map((n,j)=>j===i?e.target.value:n));invalidate();}}/></label>)}</div>
      <div className="library-position"><label>Yaw (deg)<input aria-label="Obstacle yaw" type="number" min="-180" max="180" value={yaw} onChange={e=>{setYaw(e.target.value);invalidate();}}/></label>
        <label>Uncertainty (m)<input aria-label="Obstacle uncertainty" type="number" min=".05" max="1" step=".05" value={margin} onChange={e=>{setMargin(e.target.value);setAutoMargin(false);invalidate();}}/></label></div>
      <small>Scene X/Y coordinates; bottom on the floor. Catalog sizes are editable estimates. The whole uncertainty footprint must fit the scanned floor. A hidden keepout blocks SIM paths; LiDAR uses visible shapes only.</small>
      <button type="button" disabled={!valid||!label.trim()||!!candidate&&!duplicate} onClick={()=>preview({kind,label:label.trim(),position_xy_m:xy.map(Number) as [number,number],dimensions_m:size.map(Number) as [number,number,number],yaw_deg:Number(yaw),uncertainty_m:Number(margin)},photo,candidate,undefined)}>Preview obstacle</button>
    </fieldset>
    {added.length>0&&<ul style={{paddingInlineStart:20,overflowWrap:'anywhere'}}>{added.map(o=><li key={o.id}>
      {o.label} · {o.category} · {o.evidence?.basis==='photo_estimate'?'photo estimate':o.evidence?.basis==='lidar_estimate'?'LiDAR estimate':'manual estimate'} · not aligned
      <small>Center: {o.position_m.map(v=>v.toFixed(2)).join(', ')} m · uncertainty ±{o.uncertainty_m} m · {o.risk}</small>
      {o.evidence?.source_name&&<small>Reference: {o.evidence.source_name} · SHA {o.evidence.sha256}</small>}
      <button type="button" disabled={disabled} onClick={()=>remove(o.id)}>Remove {o.label} · preview</button>
    </li>)}</ul>}
  </details>;
}
