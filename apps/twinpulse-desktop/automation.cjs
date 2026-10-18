// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
const path=require('node:path');
const fs=require('node:fs');
const {randomUUID}=require('node:crypto');

function createSelfTestHost({utilityProcess,shell,directory,stateDirectory,endpoint,appUrl,launch=()=>'',available=()=>true}){
  const enabled=/^http:\/\/127\.0\.0\.1:\d{4,5}$/.test(endpoint);
  let state='idle',runId=null,folder=null,child=null,timer=null,storageError=false,closed=false;
  const write=(name,data,append=false)=>{try{(append?fs.appendFileSync:fs.writeFileSync)(path.join(folder,name),data);return true;}
    catch{storageError=true;return false;}};
  const status=()=>({enabled,state,run_id:runId,report_available:!!folder&&fs.existsSync(path.join(folder,'report.html')),
    ...(enabled?{endpoint}:{}),storage_error:storageError,scope:'Basic UI checks only; no paid generation or robot connection.'});
  const finish=(code,ticket)=>{if(runId!==ticket)return;clearTimeout(timer);timer=null;child=null;
    if(state==='running')state=code===0&&!storageError&&fs.existsSync(path.join(folder,'report.html'))?'completed':'failed';
    if(state==='failed'&&!fs.existsSync(path.join(folder,'report.html'))){
      if(!fs.existsSync(path.join(folder,'host-outcome.json')))write('host-outcome.json',JSON.stringify({status:'FAIL',code:'BASIC_CHECK_RUNNER_FAILED',run_id:ticket}));
      write('report.html','<!doctype html><meta charset="utf-8"><h1>Basic checks: FAIL</h1><p>The owned UI-check worker did not complete. No generation or robot check is claimed. Review the local runner.stderr.log.</p>');}};
  return {
    status,
    run(){
      if(closed)throw Error('AUTOMATION_TEST_HOST_CLOSED');
      if(!enabled)throw Error('AUTOMATION_TEST_MODE_REQUIRED');
      if(!available())throw Error('AUTOMATION_TEST_APP_BUSY');
      if(child||state==='running')throw Error('AUTOMATION_TEST_ALREADY_RUNNING');
      const origin=new URL(appUrl());
      if(origin.protocol!=='http:'||origin.hostname!=='127.0.0.1'||!origin.port)throw Error('AUTOMATION_TEST_APP_UNAVAILABLE');
      runId=randomUUID();folder=path.join(stateDirectory,'self-tests',runId);fs.mkdirSync(folder,{recursive:true});
      const ticket=runId;
      state='running';storageError=false;
      try{
        const environment={...process.env};
        for(const key of Object.keys(environment))if(/^(NODE_|ELECTRON_RUN_AS_NODE|TWINPULSE_HOST_)/.test(key))delete environment[key];
        child=utilityProcess.fork(path.join(directory,'self-test-runner.cjs'),[endpoint,origin.origin,folder,launch()],
          {serviceName:'TwinPulse basic checks',stdio:'pipe',env:environment,execArgv:[]});
        let stderrBytes=0;
        child.stderr?.on('data',data=>{if(stderrBytes>=32768)return;
          const safe=String(data).replace(/#bootstrap=[A-Za-z0-9_-]+/g,'#bootstrap=[REDACTED]').slice(0,32768-stderrBytes);
          stderrBytes+=Buffer.byteLength(safe);write('runner.stderr.log',safe,true);});
        child.once('exit',code=>finish(code,ticket));
        timer=setTimeout(()=>{if(ticket!==runId)return;state='failed';
          write('host-outcome.json',JSON.stringify({status:'FAIL',code:'BASIC_CHECK_TIMEOUT',run_id:ticket}));
          try{child?.kill();}catch{/* Retain ownership: no second runner before exit. */}},90000);
      }catch{state='failed';child=null;throw Error('AUTOMATION_TEST_START_FAILED');}
      return status();
    },
    open(){if(!folder||!fs.existsSync(path.join(folder,'report.html')))throw Error('AUTOMATION_TEST_REPORT_UNAVAILABLE');
      return shell.openPath(path.join(folder,'report.html'));},
    close(){closed=true;clearTimeout(timer);timer=null;const running=child;if(state==='running'){
      state='interrupted';write('host-outcome.json',JSON.stringify({status:'NOT_RUN',code:'BASIC_CHECK_INTERRUPTED',run_id:runId}));
    }try{running?.kill();}catch{/* Closing the owning app cannot be blocked by worker cleanup. */}},
  };
}
module.exports={createSelfTestHost};
