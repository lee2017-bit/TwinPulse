// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {EventEmitter} from 'node:events';
import {mkdtempSync,mkdirSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
import fs from 'node:fs';
import {createSelfTestHost} from './automation.cjs';

test('explicit mode, current window, fixed runner and owned lifecycle',()=>{
  const root=mkdtempSync(path.join(tmpdir(),'tp-self-test-'));let calls=[],child;
  const utilityProcess={fork:(...args)=>{calls.push(args);child=new EventEmitter();child.kill=()=>child.emit('exit',1);return child;}};
  const options={utilityProcess,shell:{openPath:()=>{}},directory:root,stateDirectory:root,endpoint:'',appUrl:()=> 'http://127.0.0.1:8765',launch:()=> 'a'.repeat(32)};
  try{
    const normal=createSelfTestHost(options);assert.equal(normal.status().enabled,false);assert.throws(()=>normal.run(),/MODE_REQUIRED/);assert.equal(calls.length,0);
    const host=createSelfTestHost({...options,endpoint:'http://127.0.0.1:19222'});
    const status=host.run();assert.equal(status.state,'running');assert.throws(()=>host.run(),/ALREADY_RUNNING/);
    assert.equal(calls[0][0],path.join(root,'self-test-runner.cjs'));assert.equal(calls[0][1][3],'a'.repeat(32));assert.deepEqual(calls[0][2].execArgv,[]);
    assert.equal(calls[0][2].env.NODE_OPTIONS,undefined);assert.equal(calls[0][2].env.TWINPULSE_HOST_SECRET,undefined);
    const reportFolder=path.join(root,'self-tests',status.run_id);mkdirSync(reportFolder,{recursive:true});writeFileSync(path.join(reportFolder,'report.html'),'local');
    child.emit('exit',0);assert.equal(host.status().state,'completed');assert.equal(host.status().report_available,true);host.close();
    const busy=createSelfTestHost({...options,endpoint:'http://127.0.0.1:19222',available:()=>false});assert.throws(()=>busy.run(),/APP_BUSY/);
  }finally{rmSync(root,{recursive:true,force:true});}
});

test('timeout retains worker ownership until actual exit and storage failure cannot prevent close',t=>{
  const root=mkdtempSync(path.join(tmpdir(),'tp-self-test-timeout-'));let child,killed=0;
  const options={utilityProcess:{fork:()=>{child=new EventEmitter();child.kill=()=>{killed++;return true;};return child;}},shell:{},directory:root,stateDirectory:root,endpoint:'http://127.0.0.1:19222',appUrl:()=> 'http://127.0.0.1:8765'};
  t.mock.timers.enable({apis:['setTimeout']});
  try{
    const host=createSelfTestHost(options);host.run();t.mock.timers.tick(90001);
    assert.equal(killed,1);assert.throws(()=>host.run(),/ALREADY_RUNNING/);child.emit('exit',1);
    host.run();t.mock.method(fs,'writeFileSync',()=>{throw Error('ENOSPC');});host.close();
    assert.equal(killed,2);assert.equal(host.status().state,'interrupted');assert.equal(host.status().storage_error,true);assert.throws(()=>host.run(),/HOST_CLOSED/);
  }finally{t.mock.restoreAll();t.mock.timers.reset();rmSync(root,{recursive:true,force:true});}
});
