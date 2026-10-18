# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Supplementary manager adapter contracts. No actual Electron is simulated as PASS."""
import io
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
ROOT=Path(__file__).resolve().parents[2]
for name in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
from twinpulse_app.desktop_ui_host import DesktopUiHost,PROTOCOL,desktop_ui_test_arguments
from twinpulse_app.process_manager import TwinPulseProcessManager

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

if __name__=='__main__':unittest.main()
