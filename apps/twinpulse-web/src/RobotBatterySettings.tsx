// SPDX-License-Identifier: Apache-2.0
import {useEffect,useState} from 'react';

export type BatteryDisplayConfig={schema_version:'robot-battery-display-1.0';mode:'voltage_only'|'robotis_opencr'|'custom';
  label:string;source:string;points:{voltage_v:number;percent:number}[]};
export type BatteryPresets=Partial<Record<'voltage_only'|'robotis_opencr',BatteryDisplayConfig>>;
const voltageOnly:BatteryDisplayConfig={schema_version:'robot-battery-display-1.0',mode:'voltage_only',label:'',source:'',points:[]};
type Draft={mode:BatteryDisplayConfig['mode'];label:string;source:string;points:{v:string;p:string}[]};
const draftOf=(c:BatteryDisplayConfig):Draft=>({mode:c.mode,label:c.label,source:c.source,points:c.points.map(p=>({v:String(p.voltage_v),p:String(p.percent)}))});

export function batteryDraftConfig(draft:Draft,presets:BatteryPresets):BatteryDisplayConfig|null{
  if(draft.mode!=='custom')return presets[draft.mode]??(draft.mode==='voltage_only'?voltageOnly:null);
  const points=draft.points.map(p=>({voltage_v:p.v.trim()?Number(p.v):NaN,percent:p.p.trim()?Number(p.p):NaN}));
  if(points.length<2||points.length>32||draft.label.length>120||draft.source.length>500||/[\x00-\x1f]/.test(draft.label+draft.source)
    ||points[0].percent!==0||points.at(-1)?.percent!==100||points.some((p,i)=>!Number.isFinite(p.voltage_v)||p.voltage_v<=0||p.voltage_v>1000
      ||!Number.isFinite(p.percent)||p.percent<0||p.percent>100||i>0&&(p.voltage_v<=points[i-1].voltage_v||p.percent<=points[i-1].percent)))return null;
  return {...voltageOnly,mode:'custom',label:draft.label,source:draft.source,points};
}
export function batteryPreview(voltage:number,config:BatteryDisplayConfig){
  if(!Number.isFinite(voltage)||voltage<=0||voltage>1000||config.mode==='voltage_only')return null;
  const ps=config.points;if(config.mode==='robotis_opencr'&&(voltage<3.5||voltage>13))return null;
  if(voltage<=ps[0].voltage_v)return 0;if(voltage>=ps[ps.length-1].voltage_v)return 100;
  for(let i=1;i<ps.length;i++)if(voltage<=ps[i].voltage_v){const a=ps[i-1],b=ps[i];return Math.round((a.percent+(voltage-a.voltage_v)/(b.voltage_v-a.voltage_v)*(b.percent-a.percent))*10)/10;}
  return null;
}

export function RobotBatterySettings({config,presets={},busy,onSave}:{config?:BatteryDisplayConfig;presets?:BatteryPresets;busy:boolean;onSave:(c:BatteryDisplayConfig)=>Promise<boolean>}){
  const saved=config??voltageOnly,key=JSON.stringify(saved);
  const [draft,setDraft]=useState(()=>draftOf(saved)),[dirty,setDirty]=useState(false),[voltage,setVoltage]=useState('');
  useEffect(()=>{if(!dirty)setDraft(draftOf(saved));},[key,dirty]);
  const update=(next:Draft)=>{setDraft(next);setDirty(true);};
  const value=batteryDraftConfig(draft,presets),preview=value&&voltage.trim()?batteryPreview(Number(voltage),value):null;
  return <details className="robot-battery-settings"><summary>Battery display settings · {saved.mode==='voltage_only'?'Voltage only':saved.mode==='robotis_opencr'?'ROBOTIS reference':'Custom table'}</summary>
    <p>Display settings for this robot. Voltage-derived percentages are not measured capacity and do not change driving protection or firmware limits. Charging and load can affect the estimate.</p>
    <fieldset disabled={busy}><label>Battery display mode<select value={draft.mode} onChange={e=>{
      const mode=e.target.value as Draft['mode'];
      update(mode==='custom'?{mode,label:'',source:'',points:draft.points.length?draft.points:[{v:'',p:'0'},{v:'',p:'100'}]}:draftOf(presets[mode]??voltageOnly));
    }}><option value="voltage_only">Voltage only · no conversion reference</option>
      <option value="robotis_opencr" disabled={!presets.robotis_opencr}>ROBOTIS OpenCR reference · 10.5V=0%, 12.3V=100%</option>
      <option value="custom">Custom voltage / percentage table</option></select></label>
    {draft.mode!=='voltage_only'&&<><p>{draft.mode==='robotis_opencr'?'Reference conversion from public manufacturer code · not a guarantee of installed firmware or actual capacity':'Operator-entered estimate · not manufacturer verified'}</p>
      {draft.mode==='custom'&&<><label>Reference table name<input maxLength={120} value={draft.label} onChange={e=>update({...draft,label:e.target.value})}/></label>
        <label>Reference source / notes<input maxLength={500} value={draft.source} onChange={e=>update({...draft,source:e.target.value})}/></label></>}
      <div className="battery-table-wrap"><table aria-label="Voltage percentage table"><thead><tr><th>Voltage (V)</th><th>Remaining (%)</th>{draft.mode==='custom'&&<th>Row</th>}</tr></thead>
        <tbody>{draft.points.map((p,i)=><tr key={i}><td><input aria-label={`Voltage ${i+1}`} type="number" step="any" readOnly={draft.mode!=='custom'} value={p.v} onChange={e=>update({...draft,points:draft.points.map((row,j)=>j===i?{...row,v:e.target.value}:row)})}/></td>
          <td><input aria-label={`Percentage ${i+1}`} type="number" step="any" readOnly={draft.mode!=='custom'} value={p.p} onChange={e=>update({...draft,points:draft.points.map((row,j)=>j===i?{...row,p:e.target.value}:row)})}/></td>
          {draft.mode==='custom'&&<td><button disabled={draft.points.length<=2} onClick={()=>update({...draft,points:draft.points.filter((_,j)=>i!==j)})} aria-label={`Remove table row ${i+1}`}>−</button></td>}</tr>)}</tbody></table></div>
      {draft.mode==='custom'&&<button disabled={draft.points.length>=32} onClick={()=>{
        const a=draft.points[draft.points.length-2],b=draft.points[draft.points.length-1];
        const between=value?{v:String((Number(a.v)+Number(b.v))/2),p:String((Number(a.p)+Number(b.p))/2)}:{v:'',p:''};
        update({...draft,points:[...draft.points.slice(0,-1),between,b]});
      }}>Add table row</button>}
      {draft.mode==='robotis_opencr'&&<small className="battery-source">Source: {saved.mode==='robotis_opencr'?saved.source:presets.robotis_opencr?.source}</small>}
    </>}
    {!value&&<p role="alert">Enter increasing voltage and percentage values. Use 2–32 rows, starting at 0% and ending at 100%.</p>}
    <label>Preview voltage (not a current measurement)<input type="number" step="any" value={voltage} onChange={e=>setVoltage(e.target.value)}/></label>
    <p aria-label="Battery conversion preview">{preview===null?'No percentage conversion · voltage only':`Input ${voltage} V → approximately ${preview}% (voltage estimate) · not a current measurement`}</p>
    {dirty&&<p>Unsaved changes</p>}
    <button disabled={!value||!dirty} onClick={async()=>{if(value&&await onSave(value))setDirty(false);}}>Save battery display</button>
    <button disabled={!dirty} onClick={()=>{setDraft(draftOf(saved));setDirty(false);}}>Cancel changes</button></fieldset>
  </details>;
}
