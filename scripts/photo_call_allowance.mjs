// SPDX-License-Identifier: Apache-2.0
// Conservative durable ceiling for this operator's approved UI submissions.
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
export async function reservePhotoSubmission(allowanceFile,photoFile,context){
 const config=JSON.parse(await fs.readFile(allowanceFile,'utf8'));
 const digest=createHash('sha256').update(await fs.readFile(photoFile)).digest('hex');
 if(config.schema_version!=='photo-call-allowance-1.0'||config.max_calls!==10||!config.allowed_photo_sha256.includes(digest))throw Error('Photo allowance scope mismatch');
 const folder=path.join(path.dirname(allowanceFile),'call-claims');await fs.mkdir(folder,{recursive:true});
 for(let i=1;i<=config.max_calls;i++){
  const claim={index:i,photo_sha256:digest,context,at:Date.now(),status:'RESERVED_BEFORE_UI_SUBMISSION_UNKNOWN_COUNTS_AS_SPENT'};
  try{await fs.writeFile(path.join(folder,String(i).padStart(2,'0')+'.json'),JSON.stringify(claim,null,2),{flag:'wx'});return claim;}
  catch(e){if(e.code!=='EEXIST')throw e;}
 }
 throw Error('Photo allowance exhausted; no UI submission');
}
