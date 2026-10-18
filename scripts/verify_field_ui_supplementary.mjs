// SPDX-License-Identifier: Apache-2.0
import {spawnSync} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
const root=process.cwd(),out=path.join(root,'outputs/robot-app-field-tests-20261018');
const start=Date.now();
const result=spawnSync(process.execPath,['node_modules/vitest/vitest.mjs','run','src/RobotFieldTests.test.tsx','src/RobotFleet.test.tsx','--maxWorkers=1','--no-file-parallelism'],
 {cwd:path.join(root,'apps/twinpulse-web'),encoding:'utf8',timeout:120000,windowsHide:true});
const log=(result.stdout??'')+(result.stderr??'');fs.writeFileSync(path.join(out,'ui-supplementary-final.log'),log);
const report={classification:'SUPPLEMENTARY_NOT_INSTALLED_OR_HARDWARE_ACCEPTANCE',status:result.status===0?'PASS':'FAIL',exit_code:result.status,
 elapsed_ms:Date.now()-start,log:'ui-supplementary-final.log',sha256:createHash('sha256').update(log).digest('hex')};
fs.writeFileSync(path.join(out,'ui-supplementary-attempt.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
if(result.status!==0)process.exitCode=1;
