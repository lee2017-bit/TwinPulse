// SPDX-License-Identifier: Apache-2.0
// Independent recorder survives the interactive control tool disconnecting.
import fs from 'node:fs/promises';
import path from 'node:path';
import {attachPoweredSession} from './robot_powered_ui_session.mjs';
const output=process.argv[2];if(!output)throw Error('New output directory required');
const session=await attachPoweredSession(output);
console.log(JSON.stringify({recording:true,output,identity:session.identity}));
let stopped=false;
while(!stopped){
  await new Promise(r=>setTimeout(r,1000));
  try{await fs.access(path.join(output,'finish-recording.request'));stopped=true;}catch{}
  if(session.page.isClosed())stopped=true;
  await session.save();
}
console.log(JSON.stringify({video:await session.finishVideo()}));
await session.browser.close();
