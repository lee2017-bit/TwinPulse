// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// Supplementary framing checks, not Electron/LLM/Isaac acceptance.
import test from 'node:test';
import assert from 'node:assert/strict';
import {EventEmitter} from 'node:events';
import {PassThrough,Writable} from 'node:stream';
import {EngineChannel,PROTOCOL_VERSION,checkedAppUrl,allowAppNavigation} from './protocol.mjs';
function setup(options){const child=new EventEmitter(),sent=[];
  child.stdout=new PassThrough(); child.stdin=new Writable({write(data,_encoding,done){sent.push(JSON.parse(data));done();}});
  return {child,sent,channel:new EngineChannel(child,options)};}
function receive(channel,value){channel.receive(Buffer.from(JSON.stringify({version:PROTOCOL_VERSION,...value})+'\n'));}
test('exact owned origin, no remote/file/credential/query destination',()=>{
  assert.equal(checkedAppUrl('http://127.0.0.1:8765/').port,'8765');
  for(const url of ['https://remote.example/','file:///c:/x','http://localhost:8765/',
    'http://u:p@127.0.0.1:8765/','http://127.0.0.1:8765/?token=x','http://127.0.0.1:8765/path'])
    assert.throws(()=>checkedAppUrl(url));
  assert.equal(allowAppNavigation('http://127.0.0.1:8766/','http://127.0.0.1:8765/'),false);
});
test('fragmented UTF8 is decoded after a whole line',()=>{const {channel}=setup();let result;
  channel.on('progress',v=>result=v);const b=Buffer.from(JSON.stringify({version:PROTOCOL_VERSION,event:'progress',payload:'바닥 만드는 중'})+'\n');
  for(const byte of b)channel.receive(Buffer.from([byte]));assert.equal(result,'바닥 만드는 중');channel.disconnect('DONE');});
test('out of order responses keep exact request ID',async()=>{const {channel,sent}=setup();
  const a=channel.request('versions'),b=channel.request('focus');
  receive(channel,{id:sent[1].id,result:2});receive(channel,{id:sent[0].id,result:1});
  assert.deepEqual(await Promise.all([a,b]),[1,2]);channel.disconnect('DONE');});
test('timeout does not resend or accept late output as new response',async()=>{const {channel,sent}=setup({timeoutMs:5});
  await assert.rejects(channel.request('focus'),/TIMEOUT/);receive(channel,{id:sent[0].id,result:true});
  assert.equal(sent.length,1);assert.equal(channel.pending.size,0);assert.equal(channel.closed,false);channel.disconnect('DONE');});
test('EOF rejects pending without killing manager or another process',async()=>{const {channel,child}=setup();
  const p=assert.rejects(channel.request('initialize'),/STDOUT_EOF/);child.stdout.emit('end');await p;assert.equal(channel.closed,true);});
test('unknown method and circular payload never dispatch',async()=>{const {channel,sent}=setup();const circular={};circular.self=circular;
  await assert.rejects(channel.request('execute-shell'),/METHOD_REJECTED/);await assert.rejects(channel.request('focus',circular),/PARAMS_INVALID/);
  assert.equal(sent.length,0);channel.disconnect('DONE');});
test('version/oversized/malformed/unknown event terminate channel',()=>{
  for(const raw of ['{}\n','bad\n','x'.repeat(65537),JSON.stringify({version:PROTOCOL_VERSION,event:'error'})+'\n']){
    const {channel}=setup();channel.receive(Buffer.from(raw));assert.equal(channel.closed,true);}});
test('foreign bootstrap never opens application',()=>{const {channel}=setup();let ready=false;
  channel.on('ui-ready',()=>ready=true);receive(channel,{event:'ui-ready',payload:{url:'https://example.com/'}});
  assert.equal(ready,false);assert.equal(channel.closed,true);});
test('response has exactly one typed result/error',async()=>{
  for(const fields of [{},{result:null,error:{code:'FAIL'}},{error:{message:'raw'}},{result:'ok',event:'stopped'}]){
    const {channel,sent}=setup();const p=assert.rejects(channel.request('versions'),/RESPONSE_INVALID/);
    receive(channel,{id:sent[0].id,...fields});await p;assert.equal(channel.closed,true);}});
test('write failure clears request and timer',async()=>{const {channel,child}=setup();child.stdin.write=()=>{throw Error('pipe');};
  await assert.rejects(channel.request('focus'),/WRITE_FAILED/);assert.equal(channel.pending.size,0);channel.disconnect('DONE');});
