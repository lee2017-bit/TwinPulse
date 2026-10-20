// SPDX-License-Identifier: Apache-2.0
// Preserve exact owned fault evidence before a later launch rotates it.
import fs from 'node:fs/promises';
import path from 'node:path';
import{createHash}from'node:crypto';
const [out,launch,project,operation,kit]=process.argv.slice(2);
if(!out||![launch,project,operation].every(v=>/^[A-Za-z0-9_-]+$/.test(v??''))||!kit)throw Error('Output, exact launch/project/operation and matching Kit log required');
await fs.mkdir(out,{recursive:false});
const runtime=path.join(process.env.LOCALAPPDATA,'TwinPulse/runtime');
const sources=['supervisor-status.json','engine-status.json','engine.log','backend.log','desktop-host.log'].map(v=>path.join(runtime,'launches',launch,v));
sources.push(path.join(runtime,'projects',project,'robot-operations',operation+'.json'),path.join(runtime,'projects',project,'robot-operations',operation+'.events.jsonl'),kit);
const receipt={launch,project,operation,at:new Date().toISOString(),files:[]};
for(const [i,source] of sources.entries()){
 const target=String(i).padStart(2,'0')+'-'+path.basename(source),row={source,target};
 try{const before=await fs.stat(source);await fs.copyFile(source,path.join(out,target),fs.constants.COPYFILE_EXCL);const bytes=await fs.readFile(path.join(out,target)),after=await fs.stat(source);
 row.bytes=bytes.length;row.sha256=createHash('sha256').update(bytes).digest('hex');row.stable=before.size===after.size&&before.mtimeMs===after.mtimeMs;}
 catch(e){row.error=e.code??String(e);}receipt.files.push(row);
}
await fs.writeFile(path.join(out,'receipt.json'),JSON.stringify(receipt,null,2),{flag:'wx'});console.log(JSON.stringify(receipt));
