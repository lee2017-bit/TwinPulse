# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Electron window adapter for the existing Python process-manager authority.

The manager owns backend/Isaac. Window reconnect never restarts a generation.
Only authenticated product shutdown can ask the manager to finish its session.
"""
from datetime import datetime, timezone
import json
import hmac
import os
from pathlib import Path
import re
import subprocess
import secrets
import socket
import sys
from threading import Event, RLock, Thread

PROTOCOL = 'desktop-engine-1.0'


def desktop_ui_test_arguments(environment):
    """Explicit per-launch renderer testing; never enabled by normal startup.

    The local debugger can control this window, so it must not be persisted in
    user settings or advertised on a network interface. No Node inspector or
    renderer security preference is changed.
    """
    value = environment.get('TWINPULSE_UI_TEST_CDP_PORT')
    if value is None:
        return []
    if not re.fullmatch(r'[0-9]{4,5}', value) or not 1024 <= int(value) <= 65535:
        raise ValueError('DESKTOP_UI_TEST_PORT_INVALID')
    return ['--remote-debugging-address=127.0.0.1', '--remote-debugging-port=' + value]


class DesktopUiHost:
    def __init__(self, root, state_dir, *, popen=subprocess.Popen):
        self.root, self.state_dir = Path(root), Path(state_dir)
        self.popen = popen
        self.lock = RLock()
        self.child = None
        self.manager = None
        self.stderr_path = None
        self.protocol_alive = False
        self.initialized = Event()
        self.writer = None
        self.listener = None

    def _command(self):
        if getattr(sys, 'frozen', False):
            executable = Path(sys.executable).parent / 'desktop' / 'TwinPulseDesktop.exe'
            command = [str(executable)]
        else:
            app = self.root / 'apps/twinpulse-desktop'
            executable = app / 'node_modules/electron/dist/electron.exe'
            command = [str(executable), str(app)]
        if not executable.is_file():
            raise ValueError('DESKTOP_HOST_NOT_BUILT')
        return command + desktop_ui_test_arguments(os.environ) + ['--twinpulse-state', str(self.state_dir.resolve())]

    def _send(self, row, *, child=None):
        with self.lock:
            child = child or self.child
            if child is None or child is not self.child or child.poll() is not None or self.writer is None:
                return False
            try:
                self.writer.write((json.dumps({'version': PROTOCOL, **row}, ensure_ascii=False) + '\n').encode('utf-8'))
                self.writer.flush()
                return True
            except (OSError, ValueError):
                return False

    def _event(self, name, payload):
        return self._send({'event': name, 'payload': payload})

    def open(self, manager, ui_url):
        from urllib.parse import urlsplit
        parsed = urlsplit(ui_url)
        if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or not parsed.port:
            raise ValueError('DESKTOP_HOST_URL_INVALID')
        with self.lock:
            if self.child is not None and self.child.poll() is None:
                if not self.protocol_alive:
                    from .process_manager import ProcessManagerError
                    raise ProcessManagerError('desktop_protocol_disconnected',
                        'Desktop window connection was lost. Close that window, then use Start again. Active work was not restarted.')
                self._event('focus', {'launch_id': manager._launch_id})
                return
            self.manager = manager
            from .release_contract import atomic_json
            arguments=desktop_ui_test_arguments(os.environ)
            atomic_json(manager.launch_dir/'desktop-automation.json',{
                'schema':'desktop-automation-1.0','enabled':bool(arguments),
                'port':int(os.environ['TWINPULSE_UI_TEST_CDP_PORT']) if arguments else None})
            self.base_url = f'http://127.0.0.1:{parsed.port}'
            command = self._command()
            environment = dict(os.environ)
            environment.pop('ELECTRON_RUN_AS_NODE', None)
            environment.pop('TWINPULSE_UI_TEST_CDP_PORT', None)
            environment['TWINPULSE_UI_HOST'] = 'electron'
            environment['ELECTRON_NO_ATTACH_CONSOLE'] = '1'
            # GUI Electron on Windows may detach/close inherited stdio. Use
            # the same narrow framed protocol over a private authenticated
            # loopback transport; the ordinary App URL is unchanged.
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.bind(('127.0.0.1', 0)); listener.listen(4); listener.settimeout(2)
            secret = secrets.token_urlsafe(32)
            environment['TWINPULSE_HOST_PORT'] = str(listener.getsockname()[1])
            environment['TWINPULSE_HOST_SECRET'] = secret
            self.listener = listener
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            try:
                child = self.popen(command, cwd=str(self.root), env=environment,
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                    shell=False, creationflags=creationflags)
            except BaseException:
                listener.close()
                raise
            self.child = child
            self.protocol_alive = False
            self.writer = None
            self.initialized.clear()
            self.stderr_path = manager.launch_dir / 'desktop-host.log'
            Thread(target=self._accept_host, args=(listener,secret,child), daemon=True, name='TwinPulseDesktopProtocol').start()
            Thread(target=self._read_errors, args=(child,), daemon=True, name='TwinPulseDesktopErrors').start()
        # Reader needs self.lock to send the response. Never wait under it.
        if not self.initialized.wait(timeout=10) or child.poll() is not None:
            listener.close()
            from .process_manager import ProcessManagerError
            raise ProcessManagerError('desktop_handshake_failed',
                'Desktop host did not confirm its current protocol session. See desktop-host.log.')
        self._load_application()
        status = __import__('twinpulse_app.process_manager', fromlist=['_read_json'])._read_json(manager.supervisor_status_file) or {}
        manager._write_status(str(status.get('status', 'starting')), str(status.get('phase', 'backend_ready')),
            str(status.get('message', 'Opening TwinPulse desktop')), browser_launched=True)

    def _load_application(self):
        bootstrap = self.manager._issue_product_bootstrap(self.base_url)
        self._event('ui-ready', {'url': self.base_url + '/#bootstrap=' + bootstrap,
            'launch_id': self.manager._launch_id})

    def _accept_host(self, listener, secret, child):
        try:
            for _ in range(4):
                try:
                    connection, _address = listener.accept()
                except socket.timeout:
                    if child.poll() is not None: return
                    continue
                connection.settimeout(2)
                stream = connection.makefile('rwb', buffering=0)
                try:
                    line = stream.readline(4097)
                    auth = json.loads(line)
                    valid = (len(line) <= 4096 and isinstance(auth,dict)
                        and set(auth) == {'version','auth_nonce'} and auth['version'] == PROTOCOL
                        and isinstance(auth['auth_nonce'],str) and hmac.compare_digest(auth['auth_nonce'],secret))
                except (ValueError, TypeError, OSError):
                    valid = False
                if not valid:
                    stream.close(); connection.close(); continue
                with self.lock:
                    if self.child is not child:
                        stream.close(); connection.close(); return
                    self.writer = stream; self.protocol_alive = True
                connection.settimeout(None)
                listener.close()
                try:
                    self._read_requests(child, stream)
                finally:
                    connection.close()
                return
        except OSError:
            pass
        finally:
            listener.close()

    def _read_requests(self, child, stream=None):
        stream = stream or child.stdout
        try:
            while stream is not None:
                line = stream.readline(65538)
                if not line:
                    break
                if len(line) > 65536 or not line.endswith(b'\n'):
                    break
                try:
                    row = json.loads(line)
                    if (not isinstance(row, dict) or set(row) != {'version', 'id', 'method', 'params'}
                            or row['version'] != PROTOCOL or not isinstance(row['id'], str)
                            or re.fullmatch('[a-f0-9-]{36}', row['id']) is None
                            or not isinstance(row['params'], dict)):
                        break
                    method = row['method']
                    if method in ('initialize', 'versions'):
                        result = dict(protocol=PROTOCOL, engine_python=sys.version.split()[0],
                            app_version='0.1.0', release_id=os.environ.get('TWINPULSE_RELEASE_ID', 'development'),
                            launch_id=self.manager._launch_id)
                    elif method == 'focus':
                        if row['params'].get('reload') is True:
                            self._load_application()
                        result = {'available': True}
                    elif method == 'request-exit':
                        # Renderer invokes the existing authenticated shutdown
                        # API. This pipe never publishes a shutdown file.
                        result = {'accepted': False, 'code': 'USE_AUTHENTICATED_APP_SHUTDOWN'}
                    else:
                        self._send({'id': row['id'], 'error': {'code': 'METHOD_REJECTED'}}, child=child)
                        continue
                    sent = self._send({'id': row['id'], 'result': result}, child=child)
                    if method == 'initialize' and sent and self.child is child and self.protocol_alive:
                        self.initialized.set()
                except (ValueError, TypeError, KeyError):
                    break
        except OSError:
            pass
        finally:
            with self.lock:
                if self.child is child:
                    self.protocol_alive = False
                    self.writer = None
            # The disconnected UI may close itself, but EOF never asks the
            # manager to stop active inference/Isaac work.
            try:
                stream.close()
                if getattr(child,'stdin',None) is not None: child.stdin.close()
            except (OSError, ValueError, AttributeError):
                pass
        # A crashed window has no authority to kill active work. The existing
        # manager stays available; the next Start can open a fresh window.

    def _read_errors(self, child):
        path = self.stderr_path
        if path is None:
            return
        try:
            with path.open('a', encoding='utf-8') as stream:
                count = 0
                while child.stderr is not None:
                    line = child.stderr.readline(8193)
                    if not line:
                        break
                    if count >= 262144:
                        continue  # Keep draining: a full pipe can block Chromium.
                    text = line.decode('utf-8', errors='replace')
                    text = re.sub(r'(#bootstrap=)[A-Za-z0-9_-]+', r'\1[REDACTED]', text)
                    stream.write(text); stream.flush(); count += len(line)
        except OSError:
            pass

    def close_after_stop(self, manager):
        from .process_manager import _read_json
        state = _read_json(manager.supervisor_status_file) or {}
        receipt = _read_json(manager.launch_dir / 'cleanup-receipt.json') or {}
        cleaned = (receipt.get('schema_version') == 'launcher-cleanup-1.0'
            and receipt.get('launch_id') == manager._launch_id
            and receipt.get('owner_pid') == manager._owner_pid
            and receipt.get('owned_processes_stopped') is True)
        if state.get('status') != 'stopped' and not cleaned:
            self._event('diagnostic', {'code': 'ENGINE_STOP_UNCONFIRMED'})
            return
        self._event('stopped', {'launch_id': manager._launch_id, 'stopped_at_utc': datetime.now(timezone.utc).isoformat()})
        child = self.child
        if child is not None:
            try:
                child.wait(timeout=8)
            except subprocess.TimeoutExpired:
                # Keep evidence, never kill a foreign or hung process here.
                return
