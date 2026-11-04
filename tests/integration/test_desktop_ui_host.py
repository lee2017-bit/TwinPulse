# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Supplementary manager adapter contracts. No actual Electron is simulated as PASS."""
import io
import json
import os
from pathlib import Path
import socket
import sys
from tempfile import TemporaryDirectory
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
for name in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
from twinpulse_app.desktop_ui_host import DesktopUiHost,HANDSHAKE_TIMEOUT_S,PROTOCOL,desktop_ui_test_arguments
from twinpulse_app.process_manager import ProcessManagerError,TwinPulseProcessManager

class Connection:
    def __init__(self,nonce):self.stream=io.BytesIO((json.dumps(dict(version=PROTOCOL,auth_nonce=nonce))+'\n').encode());self.closed=False
    def settimeout(self,value):pass
    def makefile(self,*args,**kwargs):return self.stream
    def close(self):self.closed=True

class AdapterTests(unittest.TestCase):
    def test_desktop_debugging_is_off_without_explicit_test_environment(self):
        self.assertEqual(desktop_ui_test_arguments({}), [])
    def test_desktop_debugging_rejects_arbitrary_switches_and_invalid_ports(self):
        for value in ('', '0', '80', '65536', '9222 --no-sandbox', '0.0.0.0:9222', '-1'):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError,'UI_TEST_PORT_INVALID'):
                desktop_ui_test_arguments({'TWINPULSE_UI_TEST_CDP_PORT':value})
    def test_desktop_debugging_pins_loopback_without_node_or_security_switches(self):
        self.assertEqual(desktop_ui_test_arguments({'TWINPULSE_UI_TEST_CDP_PORT':'19222'}),
            ['--remote-debugging-address=127.0.0.1','--remote-debugging-port=19222'])
    def setUp(self):
        self.temp=TemporaryDirectory(dir=ROOT/'artifacts/test-tmp');self.addCleanup(self.temp.cleanup)
        self.host=DesktopUiHost(ROOT,Path(self.temp.name))
        self.host.manager=SimpleNamespace(_launch_id='launch')
    def child(self,raw):
        return SimpleNamespace(stdout=io.BytesIO(raw),stdin=io.BytesIO(),poll=lambda:None)
    def test_invalid_url_cannot_spawn(self):
        self.host.popen=lambda *a,**k:self.fail('must not spawn')
        for url in ('https://example.com/','http://localhost:8765/'):
            with self.assertRaisesRegex(ValueError,'URL_INVALID'):self.host.open(self.host.manager,url)
    def test_shutdown_request_pipe_has_no_authority(self):
        row=dict(version=PROTOCOL,id='0'*8+'-'+'0'*4+'-'+'0'*4+'-'+'0'*4+'-'+'0'*12,
            method='request-exit',params={})
        child=self.child((json.dumps(row)+'\n').encode());response=[]
        self.host._send=lambda value,**k:response.append(value)
        self.host._read_requests(child)
        self.assertEqual(response[0]['result'],dict(accepted=False,code='USE_AUTHENTICATED_APP_SHUTDOWN'))
    def test_eof_marks_channel_unusable_and_closes_only_its_pipe(self):
        child=self.child(b'');self.host.child=child;self.host.protocol_alive=True
        self.host._read_requests(child)
        self.assertFalse(self.host.protocol_alive);self.assertTrue(child.stdin.closed)
    def test_stderr_drain_continues_after_storage_cap(self):
        data=b'x'*300000+b'END\n';child=SimpleNamespace(stderr=io.BytesIO(data))
        self.host.stderr_path=Path(self.temp.name)/'desktop.log';self.host._read_errors(child)
        self.assertEqual(child.stderr.tell(),len(data));self.assertLess(self.host.stderr_path.stat().st_size,271000)
    def test_live_channel_reopen_does_not_spawn_or_restart_backend(self):
        self.host.child=self.child(b'');self.host.protocol_alive=True;events=[]
        self.host._event=lambda name,payload:events.append(name)
        self.host.popen=lambda *a,**k:self.fail('duplicate child')
        self.host.open(self.host.manager,'http://127.0.0.1:8765/')
        self.assertEqual(events,['focus'])
    def test_bad_transport_nonce_cannot_reach_protocol_or_bootstrap(self):
        child=self.child(b'');self.host.child=child;seen=[]
        self.host._read_requests=lambda current,stream:seen.append(current)
        class Connection:
            def __init__(self,nonce):self.stream=io.BytesIO((json.dumps(dict(version=PROTOCOL,auth_nonce=nonce))+'\n').encode());self.closed=False
            def settimeout(self,value):pass
            def makefile(self,*args,**kwargs):return self.stream
            def close(self):self.closed=True
        bad,good=Connection('wrong'),Connection('exact-nonce')
        class Listener:
            def __init__(self):self.rows=iter((bad,good))
            def accept(self):return next(self.rows),('127.0.0.1',1)
            def close(self):pass
        self.host._accept_host(Listener(),'exact-nonce',child)
        self.assertTrue(bad.closed);self.assertTrue(bad.stream.closed);self.assertEqual(seen,[child])
    def test_failed_child_wait_retains_ownership_for_recheck(self):
        class Process:
            def poll(self):return None
            def wait(self,**kw):raise OSError('wait failed')
        process=Process();owner=SimpleNamespace(_owned={'engine':process},_jobs={})
        with self.assertRaises(OSError):TwinPulseProcessManager._stop_owned(owner,'engine',graceful_s=0)
        self.assertIs(owner._owned['engine'],process)

class HostAvailabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(dir=ROOT/'artifacts/test-tmp');self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.launch=self.base/'launch'
        self.manager=SimpleNamespace(_launch_id='launch',_owner_pid=os.getpid(),launch_dir=self.launch,
            supervisor_status_file=self.launch/'supervisor-status.json')
        environment=patch.dict(os.environ);environment.start();self.addCleanup(environment.stop)
        os.environ.pop('TWINPULSE_UI_TEST_CDP_PORT',None)
    def host(self,built,**kwargs):
        host=DesktopUiHost(self.base/'repo',self.base/'state',**kwargs)
        if built:host._executable().parent.mkdir(parents=True,exist_ok=True);host._executable().write_bytes(b'fixture')
        return host
    def test_available_reports_only_whether_the_source_host_exists(self):
        host=self.host(False)
        self.assertEqual(host._executable(),self.base/'repo/apps/twinpulse-desktop/node_modules/electron/dist/electron.exe')
        self.assertFalse(host.available())
        host._executable().parent.mkdir(parents=True);host._executable().write_bytes(b'fixture')
        self.assertTrue(host.available())
        self.assertEqual(host._command(),[str(host._executable()),str(self.base/'repo/apps/twinpulse-desktop'),
            '--twinpulse-state',str((self.base/'state').resolve())])
    def test_frozen_host_is_the_bundled_desktop_exe(self):
        package=self.base/'package'
        with patch.object(sys,'frozen',True,create=True),patch.object(sys,'executable',str(package/'TwinPulse.exe')):
            host=self.host(False)
            self.assertEqual(host._executable(),package/'desktop'/'TwinPulseDesktop.exe');self.assertFalse(host.available())
            host._executable().parent.mkdir(parents=True);host._executable().write_bytes(b'fixture')
            self.assertTrue(host.available())
            self.assertEqual(host._command(),[str(package/'desktop'/'TwinPulseDesktop.exe'),'--twinpulse-state',str((self.base/'state').resolve())])
    def test_available_does_not_hide_invalid_test_switches(self):
        host=self.host(True);os.environ['TWINPULSE_UI_TEST_CDP_PORT']='80'
        self.assertTrue(host.available())
        with self.assertRaisesRegex(ValueError,'UI_TEST_PORT_INVALID'):host._command()
    def test_missing_host_is_typed_and_leaves_no_half_state(self):
        host=self.host(False,popen=lambda *a,**k:self.fail('must not spawn'))
        with self.assertRaises(ProcessManagerError) as caught:host.open(self.manager,'http://127.0.0.1:8765/')
        self.assertEqual(caught.exception.code,'desktop_host_not_built')
        self.assertIn('DESKTOP_HOST_NOT_BUILT',str(caught.exception))
        self.assertFalse((self.launch/'desktop-automation.json').exists())
        self.assertIsNone(host.manager);self.assertIsNone(host.child);self.assertIsNone(host.listener)
        host.close_after_stop(self.manager)
        self.launch.mkdir();self.manager.supervisor_status_file.write_text(json.dumps({'status':'stopped'}),encoding='utf-8')
        host.close_after_stop(self.manager)
    def test_slow_first_start_is_accepted_and_a_silent_host_fails_at_the_window(self):
        # Fake clock: a first start that confirms after 40 s still opens (the old
        # single 10 s wait refused it); one that never confirms fails at the window.
        for ready_at,expected in ((40.,'opened'),(float('inf'),'desktop_handshake_failed')):
            with self.subTest(ready_at=ready_at):
                now=[0.];statuses=[]
                class Initialized:
                    def wait(self,timeout):
                        now[0]+=timeout
                        if now[0]>300:raise AssertionError('handshake wait has no deadline')
                        return now[0]>=ready_at
                    def is_set(self):return now[0]>=ready_at
                    def clear(self):pass
                host=self.host(True,popen=lambda *a,**k:SimpleNamespace(poll=lambda:None));host.initialized=Initialized()
                host._accept_host=host._read_errors=lambda *a:None
                self.manager._issue_product_bootstrap=lambda url:'ticket';self.manager._write_status=lambda *a,**k:statuses.append(k)
                with patch('twinpulse_app.desktop_ui_host.time',SimpleNamespace(monotonic=lambda:now[0])):
                    try:host.open(self.manager,'http://127.0.0.1:8765/');outcome='opened'
                    except ProcessManagerError as error:outcome=error.code
                    finally:host.listener is None or host.listener.close()
                self.assertEqual(outcome,expected)
                if expected=='opened':self.assertEqual(statuses,[{'browser_launched':True}])
                else:self.assertTrue(HANDSHAKE_TIMEOUT_S<=now[0]<HANDSHAKE_TIMEOUT_S+1,now[0])
    def test_slow_host_can_connect_after_more_than_four_accept_timeouts(self):
        child=SimpleNamespace(poll=lambda:None);host=self.host(False);host.child=child;seen=[]
        host._read_requests=lambda current,stream:seen.append(current)
        class Listener:
            calls=0
            def accept(self):
                self.calls+=1
                if self.calls<=6:raise socket.timeout()
                return Connection('exact-nonce'),('127.0.0.1',1)
            def close(self):pass
        host._accept_host(Listener(),'exact-nonce',child)
        self.assertEqual(seen,[child])
    def test_accept_stops_when_the_host_exits(self):
        calls=[];host=self.host(False);child=SimpleNamespace(poll=lambda:1);host.child=child
        def accept():
            calls.append(1)
            if len(calls)>1:raise AssertionError('still listening after the host exited')
            raise socket.timeout()
        host._read_requests=lambda current,stream:self.fail('no connection')
        host._accept_host(SimpleNamespace(accept=accept,close=lambda:None),'exact-nonce',child)
        self.assertEqual(calls,[1])
    def test_exited_host_ends_the_handshake_wait_early(self):
        child=SimpleNamespace(poll=lambda:1,stdout=None,stdin=None,stderr=None)
        host=self.host(True,popen=lambda *a,**k:child);started=time.monotonic()
        with self.assertRaises(ProcessManagerError) as caught:host.open(self.manager,'http://127.0.0.1:8765/')
        self.assertEqual(caught.exception.code,'desktop_handshake_failed')
        self.assertLess(time.monotonic()-started,10)

if __name__=='__main__':unittest.main()
