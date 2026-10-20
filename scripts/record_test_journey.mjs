// SPDX-License-Identifier: Apache-2.0
// Passive same-BrowserWindow recorder. The separate visible UI driver owns actions.
import{attachPoweredSession}from'./robot_powered_ui_session.mjs';
import fs from'node:fs/promises';
import path from'node:path';
const[out,resultFile]=process.argv.slice(2);if(!out||!resultFile)throw Error('New output and actual test result required');
const s=await attachPoweredSession(out);let terminal=null;const began=Date.now();
try{
 while(Date.now()-began<20*60*1000){
  try{const r=JSON.parse(await fs.readFile(resultFile,'utf8'));if(r.status!=='IN_PROGRESS'&&r.status){terminal={status:r.status,project:r.project,operation_id:r.operation_id};break;}}catch{}
  await new Promise(r=>setTimeout(r,300));
 }
 await s.finishVideo();
 await fs.writeFile(path.join(out,'recording-result.json'),JSON.stringify({identity:s.identity,terminal,
  status:terminal?'RECORDED_ACTUAL_JOURNEY':'RECORDER_TIMEOUT',source:'Passive sampled renderer only, not App acceptance or native input',
  expected_close_stop_errors:s.errors.filter(e=>e.recorder_stop)},null,2),{flag:'wx'});
}finally{await s.browser.close();}
