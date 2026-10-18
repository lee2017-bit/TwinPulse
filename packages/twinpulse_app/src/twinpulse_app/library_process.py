# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Owned finite external processes / reviewed MCP stdio, no arbitrary shell."""
import base64
import json
import os
from pathlib import Path
from queue import Queue,Empty
import subprocess
from threading import Thread
import time
from .runtime_paths import resource_root,script_command,child_environment,external_dll_search


def csv_mcp_adapter(raw,inputs,folder,token):return call_csv_mcp(raw,inputs,folder,token)


def run_finite(command,folder,token,*,timeout=60,external=True):
    out=Path(folder)/'stdout.log';err=Path(folder)/'stderr.log'
    from .process_manager import _WindowsJob
    owned=_WindowsJob('library-tool') if os.name=='nt' else None
    with out.open('xb') as stdout,err.open('xb') as stderr,external_dll_search():
        process=subprocess.Popen(command,cwd=folder,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,
            shell=False,env=child_environment(os.environ,external=external),creationflags=0x08000000 if os.name=='nt' else 0)
    started=time.monotonic()
    try:
        if owned:owned.assign(process)
        while process.poll() is None:
            if token.is_cancelled:raise ValueError('LIBRARY_CANCELLED')
            if time.monotonic()-started>timeout:raise ValueError('LIBRARY_TOOL_TIMEOUT')
            if any(p.stat().st_size>2*1024*1024 for p in (out,err)):raise ValueError('LIBRARY_TOOL_LOG_LIMIT')
            time.sleep(.05)
        if process.returncode:raise ValueError('LIBRARY_TOOL_FAILED: '+err.read_text(encoding='utf-8',errors='replace')[-800:])
        return dict(exit_code=process.returncode,elapsed_s=round(time.monotonic()-started,3))
    finally:
        if owned:owned.close()
        if process.poll() is None:
            process.terminate()
            try:process.wait(3)
            except subprocess.TimeoutExpired:process.kill();process.wait(3)


def call_csv_mcp(raw,inputs,folder,token,*,probe=False,timeout=20):
    command=script_command(resource_root(),'library-tool')+['--mcp']
    with (Path(folder)/'mcp-stderr.log').open('xb') as err:
        process=subprocess.Popen(command,cwd=folder,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=err,
            shell=False,env=child_environment(os.environ),creationflags=0x08000000 if os.name=='nt' else 0)
    received=Queue(maxsize=32);history=[];started=time.monotonic()
    def read():
        try:
            for line in iter(lambda:process.stdout.readline(2*1024*1024+1),b''):
                if len(line)>2*1024*1024:received.put(ValueError('MCP_RESPONSE_BYTE_LIMIT'));return
                received.put(json.loads(line))
        except Exception as error:received.put(error)
        finally:received.put(None)
    Thread(target=read,name='TwinPulseLibraryMcpReader',daemon=True).start()
    def send(method,params,identity=None):
        row=dict(jsonrpc='2.0',method=method,params=params)
        if identity is not None:row['id']=identity
        process.stdin.write((json.dumps(row,separators=(',',':'))+'\n').encode());process.stdin.flush()
        if identity is None:return None
        while True:
            if token.is_cancelled:raise ValueError('LIBRARY_CANCELLED')
            if time.monotonic()-started>timeout:raise ValueError('MCP_TIMEOUT')
            try:response=received.get(timeout=.1)
            except Empty:continue
            if isinstance(response,Exception):raise response
            if response is None:raise ValueError('MCP_CONNECTION_CLOSED')
            if response.get('jsonrpc')!='2.0' or response.get('id')!=identity:raise ValueError('MCP_RESPONSE_IDENTITY_INVALID')
            if 'error' in response:raise ValueError('MCP_TOOL_ERROR: '+str(response['error'])[:250])
            history.append(dict(method=method,response_id=identity));return response['result']
    try:
        hello=send('initialize',dict(protocolVersion='2025-11-25',capabilities={},clientInfo=dict(name='TwinPulse',version='1.0')),1)
        if hello.get('protocolVersion')!='2025-11-25' or 'tools' not in hello.get('capabilities',{}):
            raise ValueError('MCP_CAPABILITY_MISMATCH')
        send('notifications/initialized',{})
        catalog=send('tools/list',{},2)
        if not any(t.get('name')=='csv.summary' for t in catalog.get('tools',[])):raise ValueError('MCP_TOOL_NOT_FOUND')
        if probe:return dict(server=hello['serverInfo'],tools=catalog['tools'])
        result=send('tools/call',dict(name='csv.summary',arguments={**inputs,'bytes_base64':base64.b64encode(raw).decode()}),3)
        if result.get('isError') or not isinstance(result.get('structuredContent'),dict):raise ValueError('MCP_RESULT_INVALID')
        output=result['structuredContent']
        if output.get('schema_version')!='csv-summary-1.0' or output.get('physical_authority') is not False:
            raise ValueError('MCP_RESULT_CONTRACT_INVALID')
        return {**output,'transport':'MCP_stdio','protocol_version':'2025-11-25','server':hello['serverInfo']}
    finally:
        try:process.stdin.close()
        except OSError:pass
        try:process.wait(3)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:process.wait(3)
            except subprocess.TimeoutExpired:process.kill();process.wait(3)
        process.stdout.close()
        Path(folder,'mcp-session.json').write_text(json.dumps(dict(events=history,exit_code=process.returncode,
            elapsed_s=round(time.monotonic()-started,3))),encoding='utf-8')
