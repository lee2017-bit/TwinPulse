// SPDX-License-Identifier: Apache-2.0
// Filesystem-only supplementary ceiling test. No App, network or actual call.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {reservePhotoSubmission} from './photo_call_allowance.mjs';
test('ten durable reservations, unknown remains spent, eleventh blocked',async()=>{
 const folder=await fs.mkdtemp(path.join(os.tmpdir(),'tp-photo-allowance-'));
 const photo=path.join(folder,'fixture.bin'),config=path.join(folder,'allowance.json');const raw=Buffer.from('supplementary-no-image-or-network');await fs.writeFile(photo,raw);
 await fs.writeFile(config,JSON.stringify({schema_version:'photo-call-allowance-1.0',max_calls:10,allowed_photo_sha256:[createHash('sha256').update(raw).digest('hex')]}));
 for(let i=1;i<=10;i++)assert.equal((await reservePhotoSubmission(config,photo,{fixture:true})).index,i);
 await assert.rejects(reservePhotoSubmission(config,photo,{}),/exhausted/);
 assert.equal((await fs.readdir(path.join(folder,'call-claims'))).length,10);
 await fs.writeFile(photo,'changed');await assert.rejects(reservePhotoSubmission(config,photo,{}),/scope mismatch/);
});
