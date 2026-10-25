// SPDX-License-Identifier: Apache-2.0
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
export async function reserveDevelopmentCall(file,kind,context){
 const config=JSON.parse(await fs.readFile(file,'utf8'));
 if(config.schema!=='twinpulse-explicit-development-call-allowance-1.0'||config.additional_max_requests!==50||config.automatic_retries!==false||config.not_authorized?.unattended_physical_connection_or_motion!==true||!['text','photo'].includes(kind))throw Error('Development allowance mismatch');
 const folder=path.join(path.dirname(file),config.claim_directory);await fs.mkdir(folder,{recursive:true});
 for(let i=1;i<=config.additional_max_requests;i++){
  const claim={index:i,kind,context,at:Date.now(),authorization_sha256:createHash('sha256').update(await fs.readFile(file)).digest('hex'),status:'RESERVED_BEFORE_UI_SUBMISSION_UNKNOWN_COUNTS_AS_USED'};
  try{await fs.writeFile(path.join(folder,String(i).padStart(3,'0')+'.json'),JSON.stringify(claim,null,2),{flag:'wx'});return claim;}catch(e){if(e.code!=='EEXIST')throw e;}
 }
 throw Error('Approved development calls exhausted');
}
