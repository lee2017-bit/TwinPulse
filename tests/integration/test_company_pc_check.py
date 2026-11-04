# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Supplementary Linux checks of the read-only company-PC check script.

No Windows, Isaac Sim or internet: Windows APIs are faked and the network check talks only to a
local fake filter on 127.0.0.1. A real PC-B run is still required.
"""
import ast
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[2]
for name in ('twinpulse_core', 'twinpulse_provider', 'twinpulse_app'):
    sys.path.insert(0, str(ROOT / 'packages' / name / 'src'))
spec = importlib.util.spec_from_file_location('twinpulse_company_pc_check', ROOT / 'scripts/twinpulse_company_pc_check.py')
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)
PUBLIC_USD = ROOT / 'assets/simulation/turtlebot3_burger/usd'
# Built at run time, like test_release_provenance, so this source never holds a key-shaped literal
# that the release provenance audit would report as credential material.
SECRET = 'sk-' + 'proj-' + 'SECRET' * 3 + '1234567890'


def write(path, data, bom=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(data) if isinstance(data, (dict, list)) else data
    data = data.encode('utf-8') if isinstance(data, str) else data
    path.write_bytes((b'\xef\xbb\xbf' if bom else b'') + data)


def manifest_entries(root, names):
    return [{'path': n, 'bytes': (root / n).stat().st_size, 'sha256': hashlib.sha256((root / n).read_bytes()).hexdigest()} for n in names]


def offline_release(store, name='tp-550821745917'):
    release = store / name
    files = {'scripts/twinpulse_launcher.py': 'print(1)\n', 'apps/twinpulse-web/dist/index.html': '<html></html>\n',
             'packages/twinpulse_provider/src/twinpulse_provider/nebius_pipeline.py': 'A = 1\n'}
    for item in check.PUBLIC_BURGER_MANIFEST:  # private-folder bytes that match neither pin set
        files['artifacts/robot-models/burger-isaac/usd/turtlebot3_burger_1/' + item] = 'usda ' + item + '\r\n'
    for item, text in files.items():
        write(release / item, text)
    write(release / 'release-manifest.json', {'schema': 'twinpulse-offline-release-1.0', 'release_id': name, 'dirty': False,
                                              'files': manifest_entries(release, sorted(files))}, bom=True)
    return release


def exe_release(store, name='20261104T010000Z-abcdef123456', version='0.1.0a1'):
    release = store / name
    write(release / 'TwinPulse.exe', b'MZ')
    for path in PUBLIC_USD.rglob('*'):
        if path.is_file():
            write(release / '_internal/resources/assets/simulation/turtlebot3_burger/usd' / path.relative_to(PUBLIC_USD), path.read_bytes())
    listed = sorted(p.relative_to(release).as_posix() for p in release.rglob('*') if p.is_file())
    write(release / 'windows-release-manifest.json', {'schema': 'twinpulse-windows-exe-1.0', 'build_id': name, 'product_version': version,
                                                      'source_manifest_sha256': 'a' * 64, 'files': manifest_entries(release, listed)})
    return release


class FakeKey:
    def __init__(self, hive, key):
        self.hive, self.key = hive, key

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def Close(self):
        pass


class FakeWinreg:
    """Registry values by (hive, key, name), for the check and for CPython's own Windows urllib code."""
    HKEY_LOCAL_MACHINE, HKEY_CURRENT_USER, KEY_READ = 'HKLM', 'HKCU', 1

    def __init__(self, values):
        self.values = values

    def OpenKey(self, hive, key, reserved=0, access=1):
        if not any(h == hive and k == key for h, k, _ in self.values):
            raise OSError('no key')
        return FakeKey(hive, key)

    def QueryValueEx(self, handle, name):
        if (handle.hive, handle.key, name) not in self.values:
            raise OSError('no value')
        return self.values[(handle.hive, handle.key, name)], 1


def windows_getproxies(winreg, environ):
    """getproxies() of CPython's own urllib.request as it is on Windows (the *_proxy environment variables
    if any is set, else the WinINET registry values), reading environ and the fake winreg."""
    with patch.dict(sys.modules, {'winreg': winreg}), patch.object(os, 'name', 'nt'):
        spec = importlib.util.spec_from_file_location('urllib_request_on_windows', urllib.request.__file__)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

    def getproxies():
        with patch.dict(sys.modules, {'winreg': winreg}), patch.dict(os.environ, environ, clear=True):
            return module.getproxies()
    return getproxies


def fake_python_bat(outputs, calls):
    """A fake subprocess.Popen for python.bat that answers per mode (PYTHONNOUSERSITE in the child environment).
    'hang' never answers until the run was ended (process.ended); an exception is raised by communicate()."""
    def popen(args, **options):
        mode = 'twinpulse' if options['env'].get('PYTHONNOUSERSITE') == '1' else 'default'
        process = SimpleNamespace(pid=4000 + len(calls), returncode=0, waits=[], ended=False)

        def communicate(timeout=None):
            process.waits.append(timeout)
            value = outputs[mode]
            if isinstance(value, BaseException):
                raise value
            if value == 'hang':
                if not process.ended:
                    raise subprocess.TimeoutExpired(args, timeout)
                return '', None
            return 'Isaac env ready\nTWINPULSE_PROBE=' + json.dumps(value) + '\n', None
        process.communicate = communicate
        calls.append((args, options, process))
        return process
    return popen


def app_burger_code(folder):
    """The code the App's own simulation_assets._inventory gives the folder (None: accepted)."""
    from twinpulse_app import simulation_assets
    try:
        simulation_assets._inventory(Path(folder))
    except ValueError as error:
        return str(error).split(':', 1)[0]
    return None


def can_symlink(folder):
    try:
        (Path(folder) / 'link-probe').symlink_to(Path(folder))
    except (OSError, NotImplementedError):
        return False
    (Path(folder) / 'link-probe').unlink()
    return True


def link_folder(link, target):
    """A folder link as IT may set one up: a symlink, or on Windows without the symlink right a junction.
    Path.resolve() follows both."""
    try:
        Path(link).symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        if os.name != 'nt':
            raise
        import _winapi
        _winapi.CreateJunction(str(target), str(link))


class FakeFilter(BaseHTTPRequestHandler):
    """A network filter that answers Python-urllib (or everyone) with an HTML block page, or drops it."""
    seen, block_all, drop_python = [], False, False

    def do_GET(self):
        agent = self.headers.get('User-Agent', '')
        FakeFilter.seen.append({'agent': agent, 'authorization': self.headers.get('Authorization'), 'path': self.path})
        if agent.startswith('Python-urllib') and FakeFilter.drop_python:
            self.close_connection = True  # closed without any HTTP response
            return
        if self.path == '/redirect':
            self.send_response(302)
            self.send_header('Location', 'http://blockpage.invalid/denied')
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        if agent.startswith('Python-urllib') or FakeFilter.block_all:
            body = '<!DOCTYPE html><html><head><meta charset="UTF-8"/><title>외부사이트 차단</title></head></html>'.encode('utf-8')
            self.send_response(503)
            self.send_header('Content-Type', 'text/html; charset=UTF-8')
        else:
            body = json.dumps({'error': {'message': "You didn't provide an API key.", 'type': 'invalid_request_error', 'code': None}}).encode()
            self.send_response(401)
            self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class TextSafetyTests(unittest.TestCase):
    def test_keys_tokens_and_long_secrets_are_redacted_but_paths_stay_readable(self):
        text = check.redact(f'key {SECRET} Authorization: Bearer abc.def-123 "api_key": "plain-value" password=hunter2 '
                            'session 9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08 '
                            'ticket Zm9vYmFyYmF6cXV4MTIzNDU2Nzg5MGFiY2RlZmdoaWprbG1ub3A= '
                            'url https://user:pw@proxy.example:8080 jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NSJ9.c2lnbmF0dXJl '
                            'login http://joe:pa@ss@intranet.example:8443/x '
                            r'D:\isaacsim\isaac-sim-standalone-6.0.1-windows-x86_64 omni.kit.pip_archive-0.0.0+f9bf0dda.wx64.cp312 외부사이트 차단')
        for secret in (SECRET, 'abc.def-123', 'plain-value', 'hunter2', '9f86d081884c7d659a2feaa0c55ad015',
                       'Zm9vYmFyYmF6cXV4', 'user:pw', 'eyJhbGciOiJIUzI1NiJ9', 'c2lnbmF0dXJl', 'joe', 'pa@ss', 'ss@'):
            self.assertNotIn(secret, text)
        for kept in (r'D:\isaacsim\isaac-sim-standalone-6.0.1-windows-x86_64', 'omni.kit.pip_archive-0.0.0+f9bf0dda.wx64.cp312',
                     'proxy.example:8080', 'http://[REDACTED]@intranet.example:8443/x', '외부사이트 차단'):
            self.assertIn(kept, text)
        self.assertEqual(check.redact('test_robot_evidence_recovery_with_long_names'), 'test_robot_evidence_recovery_with_long_names')
        long = check.short('x' * 50 + ' ' + SECRET + ' y' * 400, 120)
        self.assertLessEqual(len(long), 120)
        self.assertNotIn('SECRETSECRET', check.short(('a' * 4790) + SECRET, 300))
        # The length bound before redaction may split a key after text that redaction shrinks to a few characters.
        token = 'v1.' + 'CmQKHHN0YXRpY2tleS1' + 'lMDB4eHh4' * 8
        self.assertNotIn('CmQKHHN0', check.short('QmFzZTY0' * 595 + 'QmFzZ ' + token, 300))

    def test_proxy_settings_never_show_user_names_or_passwords(self):
        internet = r'Software\Microsoft\Windows\CurrentVersion\Internet Settings'
        winreg = FakeWinreg({('HKCU', internet, 'ProxyEnable'): 1,
                             ('HKCU', internet, 'ProxyServer'): 'http=user0042:Pw1x@a.corp.example:80;https=b.corp.example:443',
                             ('HKCU', internet, 'ProxyOverride'): '<local>;*.corp.example',
                             ('HKCU', internet, 'AutoConfigURL'): 'http://user0042:PacPw2@pac.corp.example/proxy.pac'})
        env = {'HTTPS_PROXY': 'user0042:Secr3t-Pw@proxy.corp.example:8080',  # no scheme: urllib uses it all the same
               'HTTP_PROXY': 'http://user0042:Se@cr3t@proxy.corp.example:8080',  # '@' inside the password
               'ALL_PROXY': 'socks5://user0042:pa;ss,w rd@proxy.corp.example:1080',  # separators inside the password
               'NO_PROXY': 'localhost,127.0.0.1,.corp.example'}
        used = {'https': env['HTTPS_PROXY'], 'http': env['HTTP_PROXY'], 'no': env['NO_PROXY']}
        part = check.system_section(env, winreg=winreg, getproxies=lambda: used, which=lambda name: None)
        text = '\n'.join(part['lines'])
        for secret in ('user0042', 'Secr3t', 'cr3t', 'Pw1x', 'PacPw2', 'pa;ss', 'w rd'):
            self.assertNotIn(secret, text)
        for shown in ('env HTTPS_PROXY: [credentials removed]@proxy.corp.example:8080',
                      'env HTTP_PROXY: http://[credentials removed]@proxy.corp.example:8080',
                      'env ALL_PROXY: socks5://[credentials removed]@proxy.corp.example:1080',
                      'env NO_PROXY: localhost,127.0.0.1,.corp.example',
                      'ProxyServer: http=[credentials removed]@a.corp.example:80;https=b.corp.example:443;',
                      'ProxyOverride: <local>;*.corp.example;',
                      'AutoConfigURL: http://[credentials removed]@pac.corp.example/proxy.pac',
                      'Python urllib proxy entries: http, https; bypass list: set; addresses: see the proxy settings above'):
            self.assertIn(shown, text)
        # What CPython's own urllib derives from a WinINET ProxyServer whose password holds '=' or ';': pieces of the
        # user name and password in the values and the names. The report names known entries only.
        for server, entries in (('user0042:Pa7=Ss9@proxy.corp.example:8080', 'none (direct), 1 other entry (name not shown)'),
                                ('http=user0042:Kz1;Wq2@a.corp.example:80;https=b.corp.example:443', 'http;'),
                                ('socks=user0042:Mv3;Ty4@s.corp.example:1080', 'socks;'),
                                ('https=user0042:Hn5;Rb6@b.corp.example:443', 'https;')):
            with self.subTest(server=server):
                registry = FakeWinreg({('HKCU', internet, 'ProxyEnable'): 1, ('HKCU', internet, 'ProxyServer'): server})
                derived = windows_getproxies(registry, {})
                self.assertTrue(any('user0042' in key + value for key, value in derived().items()))  # the leak this guards
                part = check.system_section({}, winreg=registry, getproxies=derived, which=lambda name: None)
                text = '\n'.join(part['lines'])
                for secret in ('user0042', 'Pa7', 'Ss9', 'Kz1', 'Wq2', 'Mv3', 'Ty4', 'Hn5', 'Rb6'):
                    self.assertNotIn(secret, text)
                self.assertIn('Python urllib proxy entries: ' + entries, text + ';')
        # A WinINET list without credentials stays as it is; one whose password holds a separator is cut as one address.
        self.assertEqual(check._proxy_text('http=a:80;https=b:443', listed=True), 'http=a:80;https=b:443')
        self.assertEqual(check._proxy_text('user0042:pa;ss@proxy:8080', listed=True), '[credentials removed]@proxy:8080')
        self.assertEqual(check._proxy_text('http=user0042:pa;ss@a:80;https=b:443', listed=True),
                         'http=[credentials removed]@a:80;https=b:443')
        # Digits before the separator look like host:port; the entry with '@' then starts no 'scheme=' entry.
        self.assertEqual(check._proxy_text('user0042:12;34@a:80', listed=True), '[credentials removed]@a:80')
        self.assertEqual(check._proxy_text('http=user0042:12 34@a:80;https=b:443', listed=True),
                         'http=[credentials removed]@a:80;https=b:443')
        self.assertEqual(check._proxy_text('http=a:80;https=user0042:Pw3@b:443', listed=True),
                         'http=a:80;https=[credentials removed]@b:443')  # a later 'scheme=' entry is its own address
        self.assertEqual(check._proxy_text('http=user0042:pa;https=ss@b:443', listed=True),  # password 'pa;https=ss'
                         'http=[credentials removed]@b:443')
        self.assertEqual(check._proxy_text(None), '(not set)')

    def test_html_title_uses_the_declared_charset_and_entities(self):
        page = '<html><head><meta charset="UTF-8"/><title> 외부사이트 &amp; 차단 </title></head></html>'.encode('utf-8')
        self.assertEqual(check.html_title(page), '외부사이트 & 차단')
        self.assertEqual(check.html_title('<title>외부사이트 차단</title>'.encode('euc-kr'), 'text/html; charset=EUC-KR'), '외부사이트 차단')
        self.assertIsNone(check.html_title(b'<html><body>no title</body></html>'))
        self.assertEqual(check.describe_body(page, 'text/html')['kind'], 'html')

    def test_json_error_facts_are_typed_and_validation_input_is_not_echoed(self):
        facts = check.describe_body(json.dumps({'error': {'message': 'bad key ' + SECRET, 'type': 'invalid_request_error',
                                                          'param': 'response_format', 'code': 400}}).encode())
        self.assertEqual((facts['kind'], facts['type'], facts['param'], facts['code']), ('json', 'invalid_request_error', 'response_format', '400'))
        self.assertNotIn(SECRET, facts['message'])
        detail = check.describe_body(json.dumps({'detail': [{'msg': 'field required', 'input': 'PROMPT_SENTINEL'}]}).encode())
        self.assertEqual(detail['message'], 'field required')
        self.assertNotIn('PROMPT_SENTINEL', json.dumps(detail))
        self.assertEqual(check.describe_body(b''), {'kind': 'none'})


class FileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_bom_json_is_parsed_and_reported(self):
        write(self.root / 'bom.json', {'release_id': 'tp-1'}, bom=True)
        write(self.root / 'plain.json', {'release_id': 'tp-2'})
        write(self.root / 'broken.json', '{"release_id": ')
        value, info = check.read_json(self.root / 'bom.json')
        self.assertEqual((value, info['bom'], info['error']), ({'release_id': 'tp-1'}, True, None))
        self.assertEqual(check.read_json(self.root / 'plain.json')[1]['bom'], False)
        value, info = check.read_json(self.root / 'broken.json')
        self.assertIsNone(value)
        self.assertIn('JSONDecodeError', info['error'])
        self.assertEqual(check.read_json(self.root / 'missing.json'), (None, {'exists': False, 'bom': False, 'bytes': 0, 'error': None}))

    def test_manifest_comparison_names_missing_changed_and_extra_files(self):
        release = self.root / 'tp-1'
        for name in ('a.py', 'b.py', 'c.py'):
            write(release / 'pkg' / name, name)
        entries = manifest_entries(release, ['pkg/a.py', 'pkg/b.py', 'pkg/c.py'])
        write(release / 'pkg/b.py', 'B.PY')  # same size, different bytes: only the hash finds it
        write(release / 'pkg/a.py', 'changed a')
        (release / 'pkg/c.py').unlink()
        for name in ('pkg/c.py.backup-20261103', 'pkg/new_patch.py', 'pkg/__pycache__/a.cpython-312.pyc', 'pkg/Thumbs.db',
                     '.venv/Scripts/python.exe', 'release-manifest.json'):
            write(release / name, 'x')
        result = check.compare_manifest(release, entries, manifest_name='release-manifest.json', kind='offline')
        self.assertEqual(result['changed'], ['pkg/a.py', 'pkg/b.py'])
        self.assertEqual(result['missing'], ['pkg/c.py'])
        self.assertEqual(result['extra'], {'other': ['pkg/new_patch.py'], 'backup': ['pkg/c.py.backup-20261103'],
                                           'bytecode': ['pkg/__pycache__/a.cpython-312.pyc'], 'os_junk': ['pkg/Thumbs.db']})
        self.assertTrue(result['venv'])
        self.assertEqual(result['unreadable'], [])
        self.assertEqual(check.compare_manifest(release, entries + [{'path': '../escape'}], manifest_name='x', kind='exe')['invalid_entries'], 1)
        # A read failure is not a hand patch: a locked file and a not-found path beyond MAX_PATH are only "unreadable".
        real_sha256 = check.sha256_file

        def locked(path):
            if path.name == 'b.py':
                raise PermissionError(13, 'Access is denied')
            return real_sha256(path)
        with patch.object(check, 'sha256_file', locked):
            result = check.compare_manifest(release, entries, manifest_name='release-manifest.json', kind='offline',
                                            max_path=len(os.path.abspath(release)) + len('/pkg/c.py') - 1)
        self.assertEqual((result['changed'], result['missing'], result['unreadable']), (['pkg/a.py'], [], ['pkg/b.py', 'pkg/c.py']))
        line = check.summary_lines([{'key': 'release_unreadable', 'release': 'tp-1', 'files': result['unreadable']}])[0]
        self.assertIn('release tp-1 파일 2개를 읽지 못함 (b.py, c.py)', line)
        self.assertIn('수동 패치로 단정하지 말 것', line)


class BurgerTests(unittest.TestCase):
    def test_pin_copies_equal_the_repository_constants(self):
        from twinpulse_app import simulation_assets
        self.assertEqual(check.PUBLIC_BURGER_MANIFEST, simulation_assets.PUBLIC_BURGER_MANIFEST)
        self.assertEqual(check.BURGER_MANIFEST, simulation_assets.BURGER_MANIFEST)
        self.assertEqual(check.BURGER_FOLDERS[0], simulation_assets.PUBLIC_ASSET_RELATIVE)

    def test_metadata_names_and_isaac_folders_equal_the_app_copies(self):
        from twinpulse_app import windows_package
        integrity = runpy.run_path(str(ROOT / 'scripts/twinpulse_bootstrap_integrity.py'))
        entry = runpy.run_path(str(ROOT / 'scripts/twinpulse_desktop_entry.py'))  # not run as __main__: nothing starts
        self.assertEqual(check.OS_JUNK, windows_package.OS_JUNK)
        self.assertEqual(check.OS_JUNK, integrity['OS_JUNK'])
        self.assertEqual(check.ISAAC_CANDIDATES, entry['ISAAC_CANDIDATES'])

    def test_reviewed_isaac_version_is_the_build_the_app_calls_reviewed(self):
        from twinpulse_app.startup_checks import file_checklist
        with tempfile.TemporaryDirectory() as temp:
            write(Path(temp) / 'isaac/VERSION', check.REVIEWED_ISAAC_VERSION)
            rows = file_checklist({}, state_dir=Path(temp), isaac_python=Path(temp) / 'isaac/python.bat')
        row = next(row for row in rows if row['id'] == 'isaac_version')
        self.assertEqual(row['state'], 'ready')
        self.assertIn('Matches the reviewed local runtime.', row['detail'])
        from twinpulse_app import startup_checks
        self.assertEqual(check.REVIEWED_ISAAC_VERSION, startup_checks.REVIEWED_ISAAC_VERSION)

    def test_public_copy_matches_and_a_changed_file_is_named(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            shutil.copytree(PUBLIC_USD, root / check.BURGER_FOLDERS[0])
            result = check.burger_check(root)
            self.assertEqual((result['used'], result['folders'][0]['overall']), (check.BURGER_FOLDERS[0], 'public'))
            (root / check.BURGER_FOLDERS[0] / 'payloads/base.usda').write_bytes(b'#usda 1.0\r\n')
            write(root / check.BURGER_FOLDERS[1] / 'turtlebot3_burger.usda', 'private copy')
            result = check.burger_check(root)
            entry = result['folders'][0]
            self.assertEqual((result['used'], entry['overall'], entry['files']['payloads/base.usda']),
                             (check.BURGER_FOLDERS[0], 'mismatch', 'neither'))
            self.assertEqual(sum(state == 'public' for state in entry['files'].values()), 8)
            self.assertEqual(len(result['folders']), 2)  # the fallback folder is reported but not used

    def test_original_mixed_missing_and_closure_classification(self):
        self.assertEqual(check.classify_burger(dict(check.BURGER_MANIFEST))['overall'], 'original')
        mixed = {**check.BURGER_MANIFEST, 'payloads/base.usda': check.PUBLIC_BURGER_MANIFEST['payloads/base.usda']}
        self.assertEqual(check.classify_burger(mixed)['overall'], 'mixed')
        self.assertEqual(check.classify_burger({})['overall'], 'missing')
        extra = {**check.PUBLIC_BURGER_MANIFEST, 'payloads/extra.usda': 'f' * 64}
        self.assertEqual(check.classify_burger(extra)['overall'], 'closure_changed')

    def test_refusal_code_is_the_one_the_apps_own_inventory_gives(self):
        """Real folder states through the App's simulation_assets._inventory and the check: the same code."""
        def unlink(name):
            return lambda folder, outside: (folder / name).unlink()

        def put(name, data=b'#usda 1.0\n'):
            return lambda folder, outside: write(folder / name, data)

        def size(name, value):
            def change(folder, outside):
                with open(folder / name, 'r+b') as stream:
                    stream.truncate(value)  # sparse: no 32 MB is written
            return change

        def link(name, target):  # target 'outside' or a name inside the folder
            def change(folder, outside):
                source = outside / name if target == 'outside' else folder / target
                if target == 'outside':
                    source.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(folder / name), str(source))
                else:
                    shutil.copyfile(folder / name, source)
                    (folder / name).unlink()
                (folder / name).symlink_to(source, target_is_directory=source.is_dir())
            return change

        def folder_link(folder, outside):
            shutil.move(str(folder), str(outside / 'usd'))
            folder.symlink_to(outside / 'usd', target_is_directory=True)

        def dangling_main(folder, outside):
            (folder / 'turtlebot3_burger.usda').unlink()
            (folder / 'turtlebot3_burger.usda').symlink_to(outside / 'nothing.usda')

        limit = check.BURGER_SIZE_LIMIT
        rows = [('unchanged', [], None),
                ('folder missing', [lambda folder, outside: shutil.rmtree(folder)], 'SIM_BURGER_ASSET_MISSING'),
                ('main file missing', [unlink('turtlebot3_burger.usda')], 'SIM_BURGER_ASSET_MISSING'),
                ('main file missing, extra file', [unlink('turtlebot3_burger.usda'), put('payloads/extra.usda')], 'SIM_BURGER_ASSET_MISSING'),
                ('other file missing', [unlink('payloads/robot.usda')], 'SIM_BURGER_DEPENDENCY_CLOSURE_CHANGED'),
                ('extra file', [put('payloads/extra.usda')], 'SIM_BURGER_DEPENDENCY_CLOSURE_CHANGED'),
                ('extra empty folder', [lambda folder, outside: (folder / 'payloads/old').mkdir()], None),
                ('wrong bytes', [put('payloads/base.usda')], 'SIM_BURGER_ASSET_DIGEST_MISMATCH'),
                ('over the size limit', [size('payloads/geometries.usd', limit + 1)], 'SIM_BURGER_ASSET_SIZE_LIMIT'),
                ('exactly the size limit', [size('payloads/geometries.usd', limit)], 'SIM_BURGER_ASSET_DIGEST_MISMATCH'),
                ('over the limit, extra file', [size('payloads/geometries.usd', limit + 1), put('extra.usda')],
                 'SIM_BURGER_DEPENDENCY_CLOSURE_CHANGED'),
                ('over the limit, wrong bytes', [size('payloads/geometries.usd', limit + 1), put('payloads/base.usda')],
                 'SIM_BURGER_ASSET_SIZE_LIMIT'),
                ('metadata in every folder', [put('desktop.ini', b'[.ShellClassInfo]'), put('payloads/Thumbs.db', b'x'),
                                              put('payloads/Physics/.DS_Store', b'x'), put('payloads/DESKTOP.INI', b'x')], None),
                ('oversized metadata', [put('payloads/thumbs.db', b'x'), size('payloads/thumbs.db', limit + 1)], None),
                ('a metadata name with a suffix', [put('desktop.ini.bak')], 'SIM_BURGER_DEPENDENCY_CLOSURE_CHANGED'),
                ('a file inside a folder with a metadata name', [put('payloads/Thumbs.db/base.usda')],
                 'SIM_BURGER_DEPENDENCY_CLOSURE_CHANGED'),
                ('metadata only, main file missing', [unlink('turtlebot3_burger.usda'), put('desktop.ini')],
                 'SIM_BURGER_ASSET_MISSING')]
        links = [('file linked outside', [link('payloads/base.usda', 'outside')], 'SIM_ASSET_DEPENDENCY_UNSAFE'),
                 ('file linked inside', [link('payloads/base.usda', 'payloads/base-copy.usda')], 'SIM_ASSET_DEPENDENCY_UNSAFE'),
                 ('main file linked', [link('turtlebot3_burger.usda', 'outside')], 'SIM_ASSET_DEPENDENCY_UNSAFE'),
                 ('main file a dangling link', [dangling_main], 'SIM_BURGER_ASSET_MISSING'),
                 ('folder linked outside', [link('payloads/Physics', 'outside')], 'SIM_ASSET_DEPENDENCY_UNSAFE'),
                 ('the usd folder is a link', [folder_link], 'SIM_ASSET_DEPENDENCY_UNSAFE'),
                 ('link and extra file', [put('payloads/extra.usda'), link('payloads/base.usda', 'outside')],
                  'SIM_ASSET_DEPENDENCY_UNSAFE'),
                 ('link and over the limit', [size('payloads/robot.usda', limit + 1), link('payloads/base.usda', 'outside')],
                  'SIM_ASSET_DEPENDENCY_UNSAFE'),
                 ('a link under a metadata name',  # refused whatever its name, as the App refuses it
                  [lambda folder, outside: (folder / 'desktop.ini').symlink_to(folder / 'turtlebot3_burger.usda')],
                  'SIM_ASSET_DEPENDENCY_UNSAFE'),
                 ('a dangling link under a metadata name',
                  [lambda folder, outside: (folder / 'payloads/Thumbs.db').symlink_to(outside / 'nothing')],
                  'SIM_ASSET_DEPENDENCY_UNSAFE')]
        with tempfile.TemporaryDirectory() as temp:
            symlinks = can_symlink(temp)
        for name, changes, expected in rows + (links if symlinks else []):
            with self.subTest(name), tempfile.TemporaryDirectory() as temp:
                root, outside = Path(temp) / 'resources', Path(temp) / 'outside'
                folder = root / check.BURGER_FOLDERS[0]
                shutil.copytree(PUBLIC_USD, folder)
                outside.mkdir()
                for change in changes:
                    change(folder, outside)
                state, code, files = check.burger_verdict(check.burger_check(root))
                self.assertEqual((app_burger_code(folder), code), (expected, expected))
        if not symlinks:
            self.skipTest('this system cannot create symlinks: link rows not run')

    def test_explorer_and_finder_metadata_in_the_burger_folder_is_ignored(self):
        # The App's simulation_assets._inventory skips the same names (rows of the test above).
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / check.BURGER_FOLDERS[0]
            shutil.copytree(PUBLIC_USD, folder)
            for name in ('desktop.ini', 'payloads/Thumbs.db', 'payloads/Physics/.DS_Store', 'payloads/DESKTOP.INI'):
                write(folder / name, b'[.ShellClassInfo]')
            self.assertIsNone(app_burger_code(folder))
            burger = check.burger_check(root)
            entry = burger['folders'][0]
            self.assertEqual((entry['overall'], entry['code'], entry['extra']), ('public', None, []))
            self.assertEqual(entry['ignored'], ['desktop.ini', 'payloads/DESKTOP.INI', 'payloads/Physics/.DS_Store', 'payloads/Thumbs.db'])
            self.assertEqual(check.burger_verdict(burger), ('public', None, []))
            write(folder / 'payloads/thumbs.db.bak', b'x')  # only the exact names are metadata
            self.assertEqual(check.burger_verdict(check.burger_check(root))[1], 'SIM_BURGER_DEPENDENCY_CLOSURE_CHANGED')

    def test_linked_and_oversized_files_are_named_and_never_read(self):
        with tempfile.TemporaryDirectory() as temp:
            root, outside = Path(temp) / 'resources', Path(temp) / 'outside'
            folder = root / check.BURGER_FOLDERS[0]
            shutil.copytree(PUBLIC_USD, folder)
            outside.mkdir()
            with open(folder / 'payloads/geometries.usd', 'r+b') as stream:
                stream.truncate(check.BURGER_SIZE_LIMIT + 1)
            read = []
            real = check.sha256_file
            with patch.object(check, 'sha256_file', lambda path: read.append(Path(path).name) or real(path)):
                state, code, files = check.burger_verdict(check.burger_check(root))
            self.assertEqual((state, code, files), ('oversized', 'SIM_BURGER_ASSET_SIZE_LIMIT', ['payloads/geometries.usd']))
            self.assertNotIn('geometries.usd', read)
            self.assertEqual(len(read), 8)
            line = check.summary_lines([{'key': 'burger_' + state, 'release': 'r1', 'files': files, 'code': code}])[0]
            self.assertIn('32MB를 넘는 파일 1개 (geometries.usd) -> SIM_BURGER_ASSET_SIZE_LIMIT 원인', line)
            if not can_symlink(temp):
                self.skipTest('this system cannot create symlinks')
            shutil.move(str(folder / 'payloads/base.usda'), str(outside / 'base.usda'))
            (folder / 'payloads/base.usda').symlink_to(outside / 'base.usda')
            read.clear()
            with patch.object(check, 'sha256_file', lambda path: read.append(Path(path).name) or real(path)):
                state, code, files = check.burger_verdict(check.burger_check(root))
            self.assertEqual((state, code, files), ('linked', 'SIM_ASSET_DEPENDENCY_UNSAFE', ['payloads/base.usda']))
            self.assertNotIn('base.usda', read)
            line = check.summary_lines([{'key': 'burger_' + state, 'release': 'r1', 'files': files, 'code': code}])[0]
            self.assertIn('링크(심볼릭 링크/정션) 1개 (base.usda) -> SIM_ASSET_DEPENDENCY_UNSAFE 원인', line)


class InstallAndRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.local = Path(self.temp.name) / 'AppData/Local'
        self.installed = self.local / 'TwinPulse/installed'
        self.runtime = self.local / 'TwinPulse/runtime'

    def test_offline_install_with_bom_pointer_and_hand_patches(self):
        release = offline_release(self.installed / 'releases')
        write(self.installed / 'active-release.json', {'release_id': release.name, 'isaac_root': r'D:\isaacsim'}, bom=True)
        write(release / 'packages/twinpulse_provider/src/twinpulse_provider/nebius_pipeline.py', 'A = 2  # hand patch\n')
        write(release / 'packages/twinpulse_provider/src/twinpulse_provider/nebius_pipeline.py.backup-20261103-1345', 'A = 1\n')
        write(release / '.venv/pyvenv.cfg', 'home = C:\\Python312\n')
        part = check.install_section(self.local)
        keys = [item['key'] for item in part['findings']]
        self.assertEqual(keys, ['pointer_bom', 'offline_active', 'release_modified', 'release_backups', 'burger_mismatch'])
        self.assertEqual(part['facts'], {'pointer_isaac_root': r'D:\isaacsim'})
        self.assertNotIn('product_version', part['facts'])
        modified = part['findings'][2]
        self.assertEqual(modified['changed'], ['packages/twinpulse_provider/src/twinpulse_provider/nebius_pipeline.py'])
        text = '\n'.join(check.summary_lines(part['findings']))
        self.assertIn('active-release.json에 BOM 있음 -> 새 설치 프로그램이 자동 처리', text)
        self.assertIn('release tp-550821745917 파일 1개가 manifest와 다름 (nebius_pipeline.py) -> 수동 패치 흔적', text)
        self.assertIn('SIM_BURGER_ASSET_DIGEST_MISMATCH', text)
        self.assertIn('manifest-recorded hashes: mismatch', '\n'.join(part['lines']))
        write(release / 'release-manifest.json', '{"files": [')  # a damaged manifest: nothing can be compared
        broken = check.install_section(self.local)
        self.assertIn('release_manifest_unreadable', [item['key'] for item in broken['findings']])
        self.assertIn('not checked (the manifest has no readable file list)', '\n'.join(broken['lines']))

    def test_exe_release_supplies_the_user_agent_version_and_is_clean(self):
        release = exe_release(self.installed / 'releases')
        write(self.installed / 'active-release.json', {'schema': 'twinpulse-windows-install-1.0', 'release_id': release.name,
                                                       'exe': f'releases/{release.name}/TwinPulse.exe'})
        write(release / 'desktop.ini', '[.ShellClassInfo]')
        part = check.install_section(self.local)
        self.assertEqual([item['key'] for item in part['findings']], ['release_clean'])
        self.assertEqual(part['facts']['product_version'], '0.1.0a1')
        self.assertEqual(check.product_user_agent(part['facts']['product_version']), 'TwinPulse/0.1.0a1')
        self.assertEqual(check.product_user_agent('bad version!'), 'TwinPulse/dev')
        self.assertIn('Burger asset assets/simulation/turtlebot3_burger/usd (used at run time): public', '\n'.join(part['lines']))
        # The EXE start check refuses any unlisted file but Explorer metadata: bytecode from a diagnostic run, a backup copy.
        pyc = '_internal/resources/scripts/__pycache__/twinpulse_launcher.cpython-312.pyc'
        write(release / pyc, b'\0')
        write(release / 'TwinPulse.exe.bak', b'MZ')
        modified = check.install_section(self.local)['findings']
        self.assertEqual([(item['key'], item.get('extra') or item.get('files')) for item in modified],
                         [('release_modified', [pyc, 'TwinPulse.exe.bak']), ('release_backups', ['TwinPulse.exe.bak'])])
        self.assertIn('WINDOWS_PACKAGE_FILE_MISMATCH/UNMANIFESTED_FILE', check.summary_lines(modified)[0])

    def test_runtime_lock_settings_launches_and_provider_names_only(self):
        write(self.runtime / 'launcher.lock', {'owner_pid': 4242, 'launch_id': 'e3f951e41ddd49309f20f94359283386',
                                               'process_identity': {'executable': 'old.exe', 'creation_filetime': 1}})
        write(self.runtime / 'desktop-settings.json', {'schema_version': '1.0', 'preferred_port': 8765, 'isaac_root': r'D:\isaacsim',
                                                       'ready_timeout_s': 600}, bom=True)
        write(self.runtime / 'provider_settings.json', {'base_url': 'https://api.openai.com/v1/', 'model_id': 'vendor/planner-model-1',
                                                        'provider_profile': 'openai', 'credential_ref': 'TwinPulse/OpenAIResponsesAPI'})
        write(self.runtime / 'provider_keys.json', {'schema_version': '1.0', 'entries': [{'id': 'k1', 'name': 'Nebius-JW2', 'settings': {
            'base_url': 'https://api.tokenfactory.nebius.com/v1/', 'model_id': 'vendor/key-model-3',
            'provider_profile': 'nebius_token_factory', 'credential_ref': 'TwinPulse/ProviderKeys/nebius_token_factory/k1'}}]})
        write(self.runtime / 'provider_stage_routing.json', {'schema_version': '1.0', 'route': {
            'observer': {'key_id': 'k1', 'model_id': 'vendor/observer-model-2'}, 'planner': {'key_id': 'legacy', 'model_id': 'vendor/planner-model-1'}}})
        now = time.time()
        for offset, name, status, extra in (
                (300, '6a4cfa99ce80449a88bae82abc467a14', {'status': 'error', 'phase': 'engine_unresponsive', 'message': 'stale'}, {}),
                (200, 'cf22272927224874b6c96cf0f3b6e57d', {'status': 'error', 'phase': 'ValueError', 'message': 'DESKTOP_HOST_NOT_BUILT'}, {}),
                (100, 'e3f951e41ddd49309f20f94359283386', {'status': 'error', 'phase': 'engine_ready_timeout', 'message': 'Isaac did not complete',
                                                           'started_at_utc': '2026-11-03T00:24:15.888177+00:00',
                                                           'updated_at_utc': '2026-11-03T00:26:37.411178+00:00',
                                                           'engine': {'owned': False, 'state': 'not_started'}},
                 {'owned-exit-observations.json': {'roles': {'engine': {'pid': 11388, 'root_disposition': 'TERMINATE_AFTER_TIMEOUT',
                                                                         'return_code': 1, 'elapsed_s': 20.000000000000114}}},
                  'engine.log': '', 'engine-result.json': {'status': 'FAIL', 'startup_phase': 'simulation_app_init', 'error_type': 'RuntimeError',
                                                           'error': 'RuntimeError: Kit failed\nmore', 'traceback': 'Traceback ' + SECRET}})):
            folder = self.runtime / 'launches' / name
            write(folder / 'supervisor-status.json', status)
            for file, value in extra.items():
                write(folder / file, value)
            os.utime(folder, (now - offset, now - offset))
        part = check.runtime_section(self.local, alive=lambda pid: True, identity=lambda pid: {'executable': 'other.exe', 'creation_filetime': 2})
        keys = [item['key'] for item in part['findings']]
        self.assertEqual(keys[:3], ['lock_reused', 'desktop_settings_invalid', 'desktop_settings_bom'])
        self.assertEqual(keys[3:], ['launch_ready_timeout', 'launch_engine_ran', 'launch_engine_log_empty', 'launch_desktop_host',
                                    'launch_unresponsive'])
        # read_settings refuses this file (unknown key), so the EXE uses no saved folder from it.
        self.assertEqual(part['facts'], {'settings_refused': True, 'refused_settings_isaac_root': r'D:\isaacsim'})
        text = '\n'.join(part['lines'])
        self.assertIn('provider_settings.json: profile openai, host api.openai.com, models vendor/planner-model-1', text)
        self.assertIn('stage observer: Nebius-JW2 (nebius_token_factory), model vendor/observer-model-2', text)
        self.assertIn('stage planner: legacy key (provider_settings.json), model vendor/planner-model-1', text)
        self.assertIn('stop wait 20.0 s (time spent stopping, not run time)', text)
        self.assertIn('engine-result: FAIL, phase simulation_app_init, type RuntimeError, "RuntimeError: Kit failed"', text)
        for hidden in ('credential_ref', 'TwinPulse/ProviderKeys', 'TwinPulse/OpenAIResponsesAPI', SECRET, 'Traceback'):
            self.assertNotIn(hidden, text)
        timeout = part['findings'][3]
        self.assertEqual((timeout['seconds'], timeout['launch']), (142, 'e3f951e41ddd49309f20f94359283386'))
        dead = check.runtime_section(self.local, alive=lambda pid: False, identity=lambda pid: None)
        self.assertEqual(dead['findings'][0], {'key': 'lock_stale', 'pid': 4242})
        self.assertIn('남은 launcher.lock (PID 4242 종료됨)', check.summary_lines(dead['findings'])[0])
        write(self.runtime / 'desktop-settings.json', {'schema_version': '1.0', 'preferred_port': 80})  # read_settings refuses it
        self.assertEqual(check._settings_part(self.runtime, {})[1], [{'key': 'desktop_settings_invalid'}])

    def test_a_lock_pid_this_user_cannot_inspect_is_never_called_a_running_twinpulse(self):
        write(self.runtime / 'launcher.lock', {'owner_pid': 4242, 'launch_id': 'e3f951e41ddd49309f20f94359283386',
                                               'process_identity': {'executable': r'C:\TwinPulse\TwinPulse.exe', 'creation_filetime': 1}})
        inspected = []
        part = check.runtime_section(self.local, alive=lambda pid: check.ACCESS_DENIED, identity=inspected.append)
        self.assertEqual(part['findings'][0], {'key': 'lock_reused', 'pid': 4242, 'access_denied': True})
        self.assertEqual(inspected, [])  # nothing to compare: Windows refused to open the process
        self.assertIn('launcher.lock: pid 4242, running another program this user cannot inspect (access denied), launch', part['lines'][1])
        line = check.summary_lines(part['findings'][:1])[0]
        self.assertEqual(line, 'launcher.lock의 PID 4242를 이 사용자가 확인할 수 없는 다른 프로그램이 사용 중 -> 새 EXE 설치 프로그램이 자동 보관')
        self.assertNotIn('TwinPulse 실행 중', line)

    def test_lock_verdict_is_the_one_the_exe_installer_takes(self):
        """Each launcher.lock through the check and through the real windows_install._retire_launcher_lock."""
        from twinpulse_app import process_manager, windows_install
        recorded = {'executable': 'C:\\TwinPulse\\releases\\old\\TwinPulse.exe', 'creation_filetime': 133}
        other = {'executable': 'C:\\Windows\\explorer.exe', 'creation_filetime': 134}

        def lock(stored, **fields):
            return json.dumps({'owner_pid': 4242, 'launch_id': 'a' * 32, 'process_identity': stored, **fields}).encode()

        def plain(value):
            return json.dumps(value).encode()
        # (lock bytes, PID alive as the check sees it, as the App sees it, identity of that PID now, verdict);
        # 'running' is a refusal where the same start time shows the owner itself still runs.
        rows = [
            (lock(recorded), True, True, dict(recorded), 'running'),           # the owner still runs
            (lock(recorded), True, True, None, 'refuse'),                      # its identity cannot be read now
            (lock(None), True, True, other, 'refuse'),                         # an older lock without an identity
            (lock(recorded), True, True, dict(recorded, executable='\\\\?\\' + recorded['executable']), 'running'),  # same start
            (lock('malformed'), True, True, other, 'refuse'),
            (lock({'creation_filetime': True}), True, True, {'creation_filetime': 2}, 'refuse'),  # a bool is no start time
            (lock({'creation_filetime': '133'}), True, True, other, 'refuse'),
            (lock(recorded), True, True, {'executable': recorded['executable']}, 'refuse'),
            (lock(recorded), True, True, other, 'archive'),                    # Windows proves PID reuse
            (lock({'creation_filetime': 133}), True, True, {'creation_filetime': 134}, 'archive'),
            (lock(recorded), False, False, dict(recorded), 'archive'),         # the owner has exited
            (lock('malformed'), False, False, None, 'archive'),
            (lock(recorded), check.ACCESS_DENIED, False, None, 'archive'),     # the App cannot open it either
            (plain({'pid': 4242, 'process_identity': recorded}), True, True, other, 'archive'),  # the older key name
            (b'', True, True, other, 'unreadable'),                            # an empty file left by a crash
            (b'{"owner_pid": 4242', True, True, other, 'unreadable'),
            (b'\xff\xfe{}', True, True, other, 'unreadable'),
            (b'\xef\xbb\xbf' + lock(recorded), True, True, other, 'unreadable'),  # TwinPulse reads it without a BOM
            (b'[]', True, True, other, 'unreadable'),
            (b'"lock"', True, True, other, 'unreadable'),
            (b'{}', True, True, other, 'unreadable'),
            (plain({'owner_pid': '4242'}), True, True, other, 'unreadable'),
            (plain({'owner_pid': 0}), True, True, other, 'unreadable'),
            (plain({'owner_pid': -7}), True, True, other, 'unreadable'),
            (plain({'owner_pid': True}), True, True, other, 'unreadable'),
            (plain({'owner_pid': None, 'pid': 4242}), True, True, other, 'unreadable'),
        ]
        verdicts = {'lock_stale': 'archive', 'lock_reused': 'archive', 'lock_alive': 'running', 'lock_unproven': 'refuse',
                    'lock_unreadable': 'unreadable'}
        codes = {'EXIT_TWINPULSE_BEFORE_INSTALL': 'refuse', 'INSTALL_LAUNCHER_LOCK_UNREADABLE': 'unreadable'}
        for number, (content, seen, app_alive, current, expected) in enumerate(rows):
            with self.subTest(number=number, content=content[:70]):
                runtime = Path(self.temp.name) / f'row-{number:02d}'
                runtime.mkdir()
                (runtime / 'launcher.lock').write_bytes(content)
                lines, findings = check._lock_part(runtime, lambda pid: seen, lambda pid: current)
                self.assertEqual((runtime / 'launcher.lock').read_bytes(), content)  # the check only reads it
                with patch.object(process_manager, '_pid_alive', return_value=app_alive), \
                        patch.object(process_manager, '_process_identity', return_value=current):
                    try:
                        windows_install._retire_launcher_lock(runtime / 'launcher.lock', runtime)
                    except ValueError as error:
                        installer = codes[str(error)]
                    else:
                        installer = 'archive'
                self.assertEqual((verdicts[findings[0]['key']], installer), (expected, 'refuse' if expected == 'running' else expected))
                summary = check.summary_lines(findings)[0]
                code = {'lock_unreadable': 'INSTALL_LAUNCHER_LOCK_UNREADABLE', 'lock_unproven': 'EXIT_TWINPULSE_BEFORE_INSTALL',
                        'lock_alive': 'TwinPulse 실행 중'}
                if findings[0]['key'] in code:
                    self.assertIn(code[findings[0]['key']], summary)
                if expected != 'unreadable' and seen is True:
                    stored = json.loads(content).get('process_identity')
                    self.assertEqual(check.owner_replaced(stored, current), process_manager._owner_replaced(stored, current))

    def test_pid_alive_reads_openprocess_errors_as_the_app_does(self):
        def windows(handle, error=0, exit_code=259):
            kernel = SimpleNamespace(opened=[])

            def exit_code_of(process, code):
                code.value = exit_code
                return True
            kernel.OpenProcess = lambda access, inherit, pid: kernel.opened.append((access, inherit, pid)) or handle
            kernel.GetExitCodeProcess, kernel.CloseHandle = exit_code_of, lambda process: True
            return SimpleNamespace(get_last_error=lambda: error, byref=lambda value: value), SimpleNamespace(DWORD=lambda: SimpleNamespace(value=0)), kernel
        # ERROR_ACCESS_DENIED: another user's or a service's process, never ours; ERROR_INVALID_PARAMETER: no such process.
        for handle, error, exit_code, expected in ((0, 5, 0, check.ACCESS_DENIED), (0, 87, 0, False), (0, 6, 0, None),
                                                   (7, 0, 259, True), (7, 0, 1, False)):
            with self.subTest(error=error, exit_code=exit_code):
                fakes = windows(handle, error, exit_code)
                with patch.object(check, '_kernel32', return_value=fakes), patch.object(check.os, 'name', 'nt'):
                    self.assertEqual(check.pid_alive(4242), expected)
                self.assertEqual(fakes[2].opened, [(0x1000, False, 4242)])  # PROCESS_QUERY_LIMITED_INFORMATION only
        with patch.object(check.os, 'kill', side_effect=PermissionError(1, 'Operation not permitted')):
            self.assertEqual(check.pid_alive(4242), check.ACCESS_DENIED)

    def test_settings_are_flagged_exactly_when_read_settings_refuses_them(self):
        from twinpulse_app.desktop_settings import read_settings
        good = {'schema_version': '1.0', 'preferred_port': 8765}

        def sized(total):  # valid JSON padded with spaces to exactly `total` bytes
            text = json.dumps({**good, 'isaac_root': r'D:\isaacsim'})
            return (text[:-1] + ' ' * (total - len(text)) + '}').encode()

        def put(value):
            def make(path):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(value if isinstance(value, bytes) else json.dumps(value).encode())
            return make

        def linked(target_exists):
            def make(path):
                path.parent.mkdir(parents=True, exist_ok=True)
                target = path.parent / 'elsewhere.json'
                if target_exists:
                    target.write_text(json.dumps(good), encoding='utf-8')
                path.symlink_to(target)
            return make
        rows = [('valid', put(good), False), ('valid with isaac_root', put({**good, 'isaac_root': r'D:\isaacsim'}), False),
                ('empty isaac_root', put({**good, 'isaac_root': ''}), False),
                ('BOM', put(b'\xef\xbb\xbf' + json.dumps(good).encode()), False), ('missing', lambda path: None, False),
                ('exactly 8192 bytes', put(sized(8192)), False), ('8193 bytes', put(sized(8193)), True),
                ('isaac_root null', put({**good, 'isaac_root': None}), True), ('isaac_root number', put({**good, 'isaac_root': 5}), True),
                ('isaac_root list', put({**good, 'isaac_root': ['D:/isaacsim']}), True),
                ('port 1023', put({**good, 'preferred_port': 1023}), True), ('port 1024', put({**good, 'preferred_port': 1024}), False),
                ('port 65535', put({**good, 'preferred_port': 65535}), False), ('port 65536', put({**good, 'preferred_port': 65536}), True),
                ('port text', put({**good, 'preferred_port': '8765'}), True), ('port bool', put({**good, 'preferred_port': True}), True),
                ('port float', put({**good, 'preferred_port': 8765.0}), True), ('port missing', put({'schema_version': '1.0'}), True),
                ('schema 2.0', put({**good, 'schema_version': '2.0'}), True), ('schema missing', put({'preferred_port': 8765}), True),
                ('unknown key', put({**good, 'ready_timeout_s': 600}), True), ('not JSON', put(b'{"schema_version": '), True),
                ('empty file', put(b''), True), ('JSON list', put(b'[1, 2]'), True),
                ('not UTF-8', put(b'{"schema_version": "1.0", "preferred_port": 8765, "isaac_root": "D:\\\\\xff"}'), True),
                ('a folder', lambda path: path.mkdir(parents=True), True)]
        with tempfile.TemporaryDirectory() as temp:
            if can_symlink(temp):
                rows += [('link to a valid file', linked(True), True), ('link to nothing', linked(False), False)]
        for name, make, expected in rows:
            with self.subTest(name), tempfile.TemporaryDirectory() as temp:
                runtime = Path(temp) / 'runtime'
                runtime.mkdir()
                make(runtime / 'desktop-settings.json')
                try:
                    read_settings(runtime)
                except Exception:  # ValueError, or OSError for a folder: the EXE does not start either way
                    refused = True
                else:
                    refused = False
                facts = {}
                flagged = any(item['key'] == 'desktop_settings_invalid' for item in check._settings_part(runtime, facts)[1])
                self.assertEqual((refused, flagged), (expected, expected))
                # The saved folder the check names is the one read_settings gives the EXE, and none from a refused file.
                saved = None if refused else read_settings(runtime).get('isaac_root') or None
                self.assertEqual((facts.get('settings_isaac_root'), bool(facts.get('settings_refused'))), (saved, refused))

    def test_provider_evidence_summary_never_includes_request_redacted(self):
        evidence = self.runtime / 'provider-evidence'
        write(evidence / 'dispatches/1111111111111111111111111111aaaa.json', {'request_redacted': 'PROMPT_SENTINEL dispatch'})
        write(evidence / '1111111111111111111111111111aaaa.json', {
            'model_id': 'vendor/planner-model-1', 'schema_stage': 'twinpulse_site_tool_plan_v2', 'status': 'rejected', 'http_status': 400,
            'error_type': 'ProviderRequestError', 'saved_at': '2026-11-03T05:10:00+00:00', 'request_redacted': 'PROMPT_SENTINEL final',
            'response_redacted': json.dumps({'error': {'message': "'additionalProperties' is required to be supplied and to be false "
                                                       + SECRET + ' Bearer tok123', 'type': 'invalid_request_error',
                                                       'param': 'response_format', 'code': None}})})
        write(evidence / '2222222222222222222222222222bbbb.json', {
            'model_id': 'vendor/key-model-3', 'status': 'rejected', 'http_status': 503, 'request_redacted': 'PROMPT_SENTINEL',
            'response_redacted': '<html><head><title>외부사이트 차단</title></head><body>PROMPT_SENTINEL</body></html>'})
        for index in range(12):
            write(evidence / f'{index:032x}.json', {'model_id': 'm', 'status': 'received', 'http_status': 200,
                                                    'request_redacted': 'PROMPT_SENTINEL', 'response_redacted': '{"choices": []}'})
            os.utime(evidence / f'{index:032x}.json', (1000 + index, 1000 + index))
        reports = check.evidence_report(evidence)
        self.assertEqual(len(reports), 10)
        self.assertEqual({item['file'] for item in reports[:2]}, {'1111111111111111111111111111aaaa.json', '2222222222222222222222222222bbbb.json'})
        part = check.runtime_section(self.local)
        text = '\n'.join(part['lines'] + check.summary_lines(part['findings']))
        for hidden in ('PROMPT_SENTINEL', 'request_redacted', SECRET, 'tok123'):
            self.assertNotIn(hidden, text)
        self.assertIn("JSON invalid_request_error/response_format: 'additionalProperties' is required to be supplied", text)
        self.assertIn("HTML page '외부사이트 차단'", text)
        self.assertIn('공급자 오류 본문 저장됨', text)
        self.assertIn("공급자 응답이 HTML 페이지 '외부사이트 차단'", text)
        # A newer record may carry the typed provider_error instead of a raw body.
        write(evidence / '3333333333333333333333333333cccc.json', {'http_status': 403, 'status': 'rejected', 'request_redacted': 'PROMPT_SENTINEL',
                                                                   'provider_error': {'kind': 'html_page', 'title': 'Blocked ' + SECRET}})
        newest = check.evidence_report(evidence, 1)[0]
        self.assertEqual((newest['body']['kind'], newest['body']['title']), ('html', 'Blocked [REDACTED]'))
        self.assertNotIn('PROMPT_SENTINEL', json.dumps(newest))
        # A rejected 2xx JSON answer is the model's own output, not a provider error body; a 2xx block page still is one.
        rejected = [{'http_status': 200, 'status': 'rejected', 'modified': 0, 'body': {'kind': kind, **extra}}
                    for kind, extra in (('json', {}), ('html', {'title': 'Blocked'}))]
        self.assertEqual([item['key'] for item in check._evidence_findings(rejected)], ['evidence_html'])


class NetworkTests(unittest.TestCase):
    def setUp(self):
        FakeFilter.seen, FakeFilter.block_all, FakeFilter.drop_python = [], False, False
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), FakeFilter)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.url = f'http://127.0.0.1:{self.server.server_address[1]}/v1/models'
        # Local fake server only: never the configured proxy, never the internet.
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), check._NoRedirect)

    def test_filter_that_blocks_only_python_urllib(self):
        part = check.network_section('0.1.0a1', targets=(('Nebius', self.url),), opener=self.opener, timeout=5)
        finding = part['findings'][0]
        self.assertEqual(finding['key'], 'net_python_ua_blocked')
        self.assertEqual((finding['default']['status'], finding['default']['body']), (503, {'kind': 'html', 'title': '외부사이트 차단'}))
        self.assertEqual((finding['product']['status'], finding['product']['body']['kind'], finding['product']['body']['type']),
                         (401, 'json', 'invalid_request_error'))
        agents = [item['agent'] for item in FakeFilter.seen]
        self.assertTrue(agents[0].startswith('Python-urllib/'))
        self.assertEqual(agents[1], 'TwinPulse/0.1.0a1')
        self.assertEqual([item['authorization'] for item in FakeFilter.seen], [None, None])
        self.assertIn('Nebius: Python-urllib만 차단됨 -> 새 버전(TwinPulse UA)에서 해결 예상', check.summary_lines(part['findings']))
        self.assertIn("HTTP 503, text/html; charset=UTF-8, HTML page '외부사이트 차단'", '\n'.join(part['lines']))

    def test_both_blocked_redirect_reachable_and_unreachable(self):
        FakeFilter.block_all = True
        part = check.network_section(None, targets=(('Nebius', self.url),), opener=self.opener, timeout=5)
        self.assertEqual(part['findings'][0]['key'], 'net_both_blocked')
        self.assertEqual(part['facts']['user_agent'], 'TwinPulse/dev')
        self.assertIn("TwinPulse UA도 차단 페이지 '외부사이트 차단' -> IT에 127.0.0.1 허용 요청 필요", check.summary_lines(part['findings'])[0])
        redirect = check.probe(self.url.replace('/v1/models', '/redirect'), 'TwinPulse/dev', opener=self.opener, timeout=5)
        self.assertEqual((redirect['status'], redirect['redirect_host']), (302, 'blockpage.invalid'))
        self.assertEqual(len(FakeFilter.seen), 3)  # the redirect was reported, not followed
        FakeFilter.block_all = False
        reachable = {'agent': 'x', 'status': 401, 'body': {'kind': 'json'}}
        self.assertEqual(check.classify_pair(reachable, reachable), 'reachable')
        closed = ThreadingHTTPServer(('127.0.0.1', 0), FakeFilter)
        port = closed.server_address[1]
        closed.server_close()
        result = check.probe(f'http://127.0.0.1:{port}/v1/models', None, opener=self.opener, timeout=2)
        self.assertIn('error', result)
        self.assertEqual(check.classify_pair(result, result), 'unreachable')
        tls = {'agent': 'x', 'error': 'SSLCertVerificationError', 'detail': 'certificate verify failed'}
        self.assertEqual(check.classify_pair(tls, reachable), 'tls')

    def test_one_answered_request_is_not_called_unreachable(self):
        FakeFilter.drop_python = True  # a filter that drops Python-urllib instead of serving a page
        finding = check.network_section('0.1.0a1', targets=(('Nebius', self.url),), opener=self.opener, timeout=5)['findings'][0]
        self.assertEqual((finding['key'], 'error' in finding['default'], finding['product']['status']), ('net_unclear', True, 401))
        self.assertIn('판정 어려움', check.summary_lines([finding])[0])
        # Only 401 JSON is the expected answer without a key; a JSON 403 (for example a region refusal) is not "reachable".
        refused = {'agent': 'x', 'status': 403, 'body': {'kind': 'json', 'code': 'unsupported_country_region_territory'}}
        self.assertEqual(check.classify_pair(refused, refused), 'unclear')
        eof = {'agent': 'x', 'error': 'SSLEOFError', 'detail': '[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol'}
        self.assertEqual(check.classify_pair(eof, eof), 'unreachable')  # a dropped TLS connection, not a certificate problem

    def test_a_proxy_setting_urllib_cannot_use_is_named_without_its_credentials(self):
        url = 'https://api.openai.com/v1/models'  # never reached: each setting below fails before any connection
        for setting in ('http:/user0042:Secr3t@proxy.corp.example:8080', 'user0042:/Secr3t@proxy.corp.example:8080'):
            with self.subTest(setting=setting), patch.dict(os.environ, {'HTTPS_PROXY': setting}, clear=True):
                default, product = (check.probe(url, agent, timeout=2) for agent in (None, 'TwinPulse/0.1.0a1'))
                text = check._probe_line('OpenAI', default) + '\n' + check._probe_line('OpenAI', product)
                self.assertEqual((default['error'], product['detail']), ('ValueError', check.PROXY_SETTING_UNUSABLE))
                self.assertEqual(check.classify_pair(default, product), 'proxy_unusable')
                summary = check.summary_lines([{'key': 'net_proxy_unusable', 'name': 'OpenAI', 'host': 'api.openai.com',
                                                'default': default, 'product': product}])[0]
                for secret in ('user0042', 'Secr3t'):
                    self.assertNotIn(secret, text + summary)
                self.assertIn('프록시 설정 값을 Python이 쓸 수 없음', summary)
        # What urllib derives from a WinINET ProxyServer whose password holds ';' (see the system test): http.client
        # then says "nonnumeric port: '<a piece of the password>'".
        derived = urllib.request.build_opener(urllib.request.ProxyHandler({'https': 'http://user0042:Wq5'}), check._NoRedirect)
        facts = check.probe(url, None, opener=derived, timeout=2)
        self.assertEqual((facts['error'], facts['detail']), ('InvalidURL', check.PROXY_SETTING_UNUSABLE))
        self.assertNotIn('Wq5', check._probe_line('OpenAI', facts))
        # Any other error text loses a 'user:password@' piece too; plain text and an e-mail address stay.
        self.assertEqual(check.error_detail(OSError('Tunnel connection failed: 407 Proxy Authentication Required')),
                         'Tunnel connection failed: 407 Proxy Authentication Required')
        self.assertEqual(check.error_detail("via 'http:/user0042:Se@cr3t@proxy:8080' failed"), "via '[credentials removed]@proxy:8080' failed")
        self.assertEqual(check.error_detail('mail admin@corp.example'), 'mail admin@corp.example')

    def test_certificates_are_checked_as_the_exe_python_checks_them(self):
        loose = getattr(ssl, 'VERIFY_X509_STRICT', 0) | getattr(ssl, 'VERIFY_X509_PARTIAL_CHAIN', 0)  # added by Python 3.13+
        context = check.app_tls_context()
        self.assertEqual((context.verify_mode, context.check_hostname, context.verify_flags & loose), (ssl.CERT_REQUIRED, True, 0))
        handlers = [handler for handler in check.default_opener().handlers if isinstance(handler, urllib.request.HTTPSHandler)]
        self.assertEqual([handler._context.verify_flags & loose for handler in handlers], [0])
        exe_python = shutil.which('python3.12')  # the EXE embeds CPython 3.12
        if exe_python:
            done = subprocess.run([exe_python, '-I', '-c', 'import ssl; print(int(ssl.create_default_context().verify_flags))'],
                                  capture_output=True, text=True, timeout=60)
            self.assertEqual(int(done.stdout), int(context.verify_flags))

    def test_a_certificate_failure_is_named_as_one_and_not_as_the_proxy_setting(self):
        # ssl.SSLCertVerificationError is an OSError and a ValueError; only a plain ValueError is the proxy setting.
        reason = ssl.SSLCertVerificationError(1, '[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: '
                                                 'unable to get local issuer certificate (_ssl.c:1032)')

        class Inspected:  # a TLS-inspecting company proxy whose root certificate Python does not trust
            addheaders = [('User-agent', 'Python-urllib/3.12')]

            def open(self, request, timeout=None):
                raise urllib.error.URLError(reason)
        part = check.network_section('0.1.0a1', targets=(('OpenAI', 'https://api.openai.com/v1/models'),),
                                     opener=Inspected(), timeout=5)
        finding = part['findings'][0]
        self.assertEqual((finding['key'], finding['default']['error'], finding['product']['error']),
                         ('net_tls', 'SSLCertVerificationError', 'SSLCertVerificationError'))
        for facts in (finding['default'], finding['product']):
            self.assertIn('unable to get local issuer certificate', facts['detail'])
        self.assertIn('unable to get local issuer certificate', '\n'.join(part['lines']))

    def test_probes_without_an_opener_use_the_exe_tls_opener(self):
        with patch.object(check, 'default_opener', return_value=self.opener) as made:
            part = check.network_section('0.1.0a1', targets=(('Nebius', self.url),), timeout=5)
        self.assertEqual((made.call_count, part['findings'][0]['key']), (2, 'net_python_ua_blocked'))


class ReportAndSystemTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_report_goes_to_the_desktop_else_the_current_folder(self):
        profile, current = self.root / 'profile', self.root / 'current'
        current.mkdir()
        (profile / 'Desktop').mkdir(parents=True)
        path = check.write_report('요약\nline\n', {'USERPROFILE': str(profile)}, current)
        self.assertEqual(path.parent, profile / 'Desktop')
        self.assertTrue(path.read_bytes().startswith(b'\xef\xbb\xbf'))
        self.assertEqual(path.read_text(encoding='utf-8-sig'), '요약\nline\n')
        second = check.write_report('x\n', {'USERPROFILE': str(profile)}, current, now=time.time())
        self.assertNotEqual(path, second)
        fallback = check.write_report('x\n', {'USERPROFILE': str(self.root / 'nobody')}, current)
        self.assertEqual(fallback.parent, current)
        shell = FakeWinreg({('HKCU', r'Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders', 'Desktop'):
                            '%USERPROFILE%/OneDrive/Desktop'})  # a redirected (OneDrive) Desktop wins when it exists
        (profile / 'OneDrive/Desktop').mkdir(parents=True)
        self.assertEqual(check.desktop_folder({'USERPROFILE': str(profile)}, shell), profile / 'OneDrive/Desktop')
        self.assertEqual(check.desktop_folder({'USERPROFILE': str(profile)}, FakeWinreg({})), profile / 'Desktop')

    def test_a_desktop_that_refuses_the_report_leaves_it_to_the_next_folder(self):
        profile, current = self.root / 'profile', self.root / 'current'
        (profile / 'Desktop').mkdir(parents=True)
        current.mkdir()
        real_open = open

        def guarded(path, *args, **kwargs):  # Controlled Folder Access: the Desktop exists but refuses new files
            if Path(path).parent == profile / 'Desktop':
                raise PermissionError(13, 'Access is denied', str(path))
            return real_open(path, *args, **kwargs)
        with patch.object(check, 'open', guarded, create=True):
            self.assertEqual(check.write_report('x\n', {'USERPROFILE': str(profile)}, current).parent, current)
            self.assertEqual(check.write_report('x\n', {'USERPROFILE': str(profile)}, profile / 'Desktop').parent, profile)
            with self.assertRaisesRegex(OSError, 'no folder took the report'):  # --output-dir stays the only folder
                check.write_report('x\n', {'USERPROFILE': str(profile)}, current, profile / 'Desktop')
        self.assertEqual(list((profile / 'Desktop').iterdir()), [])

        class Full(io.StringIO):
            def write(self, text):
                raise OSError(28, 'No space left on device')

        def full_disk(path, *args, **kwargs):  # the file is created, then writing it fails
            if Path(path).parent == profile / 'Desktop':
                real_open(path, *args, **kwargs).close()
                return Full()
            return real_open(path, *args, **kwargs)
        with patch.object(check, 'open', full_disk, create=True):
            self.assertEqual(check.write_report('x\n', {'USERPROFILE': str(profile)}, current).parent, current)
        self.assertEqual(list((profile / 'Desktop').iterdir()), [])  # no half report stays behind

    def test_any_character_reaches_the_report_and_a_failed_write_leaves_no_file(self):
        profile, current = self.root / 'profile', self.root / 'current'
        (profile / 'Desktop').mkdir(parents=True)
        current.mkdir()
        # A lone surrogate, as Python reads a Windows file name that is not valid UTF-16.
        path = check.write_report('folder \ud83d cut\n', {'USERPROFILE': str(profile)}, current)
        self.assertEqual((path.parent, path.read_text(encoding='utf-8-sig')), (profile / 'Desktop', 'folder \\ud83d cut\n'))
        real_open = open

        class Broken(io.StringIO):
            def write(self, text):
                raise RuntimeError('cut off')

        def broken(name, *args, **kwargs):  # the file is created, then writing it fails with something other than OSError
            real_open(name, *args, **kwargs).close()
            return Broken()
        with patch.object(check, 'open', broken, create=True), self.assertRaises(RuntimeError):
            check.write_report('x\n', {'USERPROFILE': str(profile)}, current)
        self.assertEqual(list((profile / 'Desktop').iterdir()), [path])

    def test_report_is_never_written_inside_a_twinpulse_package(self):
        profile, package = self.root / 'profile', self.root / 'TP' / 'TwinPulse'
        profile.mkdir()
        write(package / 'windows-release-manifest.json', {'schema': 'twinpulse-windows-exe-1.0', 'product_version': '0.1.0a1'})
        (package / '_internal').mkdir()
        before = sorted(package.rglob('*'))
        env = {'USERPROFILE': str(profile)}  # and no Desktop folder
        self.assertEqual(check.write_report('x\n', env, package).parent, profile)  # started by a double-click there
        self.assertEqual(check.write_report('x\n', env, package / '_internal').parent, profile)
        with self.assertRaises(ValueError):
            check.write_report('x\n', env, self.root, package / '_internal')  # an explicit --output-dir inside it
        with self.assertRaises(FileNotFoundError):
            check.write_report('x\n', {}, package)  # nowhere else to go
        self.assertEqual(sorted(package.rglob('*')), before)
        self.assertTrue(check.inside_package(package / 'not' / 'created'))
        self.assertFalse(check.inside_package(self.root / 'TP'))
        printed = io.StringIO()
        with patch.object(check, 'probe', side_effect=AssertionError('network used')), \
                patch('urllib.request.getproxies', return_value={}):
            code = check.main(['--no-network', '--no-pause', '--output-dir', str(package)],
                              env={'USERPROFILE': str(profile), 'LOCALAPPDATA': str(profile / 'AppData/Local')}, cwd=self.root, out=printed)
        self.assertEqual(code, 1)
        self.assertIn('Report could not be written (ValueError: ', printed.getvalue())
        self.assertEqual(sorted(package.rglob('*')), before)

    def test_check_run_from_the_zip_sends_that_package_version(self):
        package, profile = self.root / 'TP' / 'TwinPulse', self.root / 'profile'
        write(package / 'windows-release-manifest.json', {'schema': 'twinpulse-windows-exe-1.0', 'product_version': '0.1.0a1', 'files': []})
        shutil.copyfile(ROOT / 'scripts/twinpulse_company_pc_check.py', package / 'twinpulse_company_pc_check.py')
        (profile / 'Desktop').mkdir(parents=True)
        with patch.object(sys, 'dont_write_bytecode', True):
            spec = importlib.util.spec_from_file_location('pc_check_in_zip', package / 'twinpulse_company_pc_check.py')
            shipped = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(shipped)
        before = sorted(package.rglob('*'))
        sent = []
        with patch.object(shipped, 'network_section', lambda version, **options: sent.append((version, options)) or
                          shipped.section([], [])), patch('urllib.request.getproxies', return_value={}):
            code = shipped.main(['--no-pause'], env={'USERPROFILE': str(profile), 'LOCALAPPDATA': str(profile / 'AppData/Local')},
                                cwd=package, out=io.StringIO())
        self.assertEqual((code, sent), (0, [('0.1.0a1', {'source': 'the package beside this check'})]))
        self.assertEqual(shipped.product_user_agent(sent[0][0]), 'TwinPulse/0.1.0a1')
        self.assertEqual(sorted(package.rglob('*')), before)  # the report went to the Desktop, nothing into the package
        self.assertEqual(len(list((profile / 'Desktop').iterdir())), 1)
        self.assertIsNone(check.package_product_version(ROOT / 'scripts'))  # a source checkout sends TwinPulse/dev
        lines = check.network_section('0.1.0a1', source='the package beside this check', targets=())['lines']
        self.assertIn('TwinPulse version in that User-Agent: from the package beside this check', lines)

    def test_system_section_with_fake_registry_and_powershell(self):
        internet = r'Software\Microsoft\Windows\CurrentVersion\Internet Settings'
        winreg = FakeWinreg({
            ('HKLM', r'SOFTWARE\Microsoft\Windows NT\CurrentVersion', 'CurrentBuild'): '22631',
            ('HKLM', r'SOFTWARE\Microsoft\Windows NT\CurrentVersion', 'UBR'): 4317,
            ('HKLM', r'SYSTEM\CurrentControlSet\Control\FileSystem', 'LongPathsEnabled'): 0,
            ('HKCU', internet, 'ProxyEnable'): 1, ('HKCU', internet, 'ProxyServer'): 'http://user:pass@proxy.corp:8080'})
        calls = []

        def run(command, **kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, '        Scope ExecutionPolicy\n        ----- ---------------\n'
                                                           'MachinePolicy       AllSigned\n   UserPolicy       Undefined\n', '')
        env = {'USERPROFILE': 'D:\\Profiles\\홍길동', 'LOCALAPPDATA': 'D:\\Profiles\\홍길동\\AppData\\Local', 'HTTPS_PROXY': 'http://u:p@proxy:3128'}
        part = check.system_section(env, winreg=winreg, run=run, getproxies=lambda: {'https': 'http://u:p@proxy:3128'},
                                    which=lambda name: 'C:/Windows/powershell.exe' if name == 'powershell' else None)
        keys = [item['key'] for item in part['findings']]
        self.assertEqual(keys, ['profile_non_ascii', 'long_paths_disabled', 'proxy_configured', 'ps_policy_restricted'])
        self.assertEqual(calls, [['C:/Windows/powershell.exe', '-NoProfile', '-NonInteractive', '-Command', 'Get-ExecutionPolicy -List']])
        text = '\n'.join(part['lines'])
        self.assertIn('Windows: ? build 22631.4317 (Windows 11 build)', text)  # ProductName missing: "?", never "None"
        self.assertIn('LongPathsEnabled: 0', text)
        self.assertIn('ProxyServer: http://[credentials removed]@proxy.corp:8080', text)
        for hidden in ('user:pass', 'u:p@'):
            self.assertNotIn(hidden, text)
        lines = check.summary_lines(part['findings'])
        self.assertTrue(any('PowerShell 없이' in line for line in lines))

    def test_proxy_finding_follows_what_python_urllib_really_uses(self):
        """CPython's own Windows getproxies (environment first, else the registry) decides, not the settings alone."""
        internet = r'Software\Microsoft\Windows\CurrentVersion\Internet Settings'
        pac, server = 'http://pac.corp.example/proxy.pac', 'proxy.corp.example:8080'
        through, direct = '아래 네트워크 결과는 이 프록시를 거친 결과', '프록시 없이 직접 연결한 결과'
        for name, values, environ, keys, said in (
                ('PAC file only', {'ProxyEnable': 0, 'AutoConfigURL': pac}, {}, ['proxy_pac_only'], 'PAC 파일을 읽지 않으므로'),
                ('WinINET proxy', {'ProxyEnable': 1, 'ProxyServer': server}, {}, ['proxy_configured'], through),
                ('WinINET proxy and a PAC file', {'ProxyEnable': 1, 'ProxyServer': server, 'AutoConfigURL': pac}, {},
                 ['proxy_configured'], through),
                # Any *_proxy variable, NO_PROXY too, makes urllib skip the registry: these requests go direct.
                ('WinINET proxy and NO_PROXY', {'ProxyEnable': 1, 'ProxyServer': server}, {'NO_PROXY': 'localhost'}, [], None),
                ('PAC file and NO_PROXY', {'ProxyEnable': 0, 'AutoConfigURL': pac}, {'NO_PROXY': 'localhost'}, ['proxy_pac_only'],
                 'PAC 파일을 읽지 않으므로'),
                ('HTTPS_PROXY', {}, {'HTTPS_PROXY': 'http://proxy.corp.example:3128'}, ['proxy_configured'], through),
                ('HTTP_PROXY only', {}, {'HTTP_PROXY': 'http://proxy.corp.example:3128'}, ['proxy_configured'], direct),
                ('nothing', {'ProxyEnable': 0}, {}, [], None)):
            with self.subTest(name):
                winreg = FakeWinreg({('HKCU', internet, key): value for key, value in values.items()})
                part = check.system_section(environ, winreg=winreg, getproxies=windows_getproxies(winreg, environ),
                                            which=lambda name: None)
                found = [item for item in part['findings'] if item['key'].startswith('proxy_')]
                self.assertEqual([item['key'] for item in found], keys)
                summary = check.summary_lines(found)[:-1]  # the last line is the fixed keep-the-evidence reminder
                self.assertEqual(len(summary), len(keys))
                if said:
                    self.assertIn(said, summary[0])
                    self.assertEqual(through in summary[0], said == through)
        broken = check.system_section({}, winreg=FakeWinreg({('HKCU', internet, 'AutoConfigURL'): pac}),
                                      getproxies=lambda: 1 / 0, which=lambda name: None)
        self.assertIn('Python urllib proxies: unknown (ZeroDivisionError)', broken['lines'])
        self.assertEqual([item for item in broken['findings'] if item['key'].startswith('proxy_')], [])  # unknown: no claim

    def test_profile_characters_the_app_quotes_or_refuses(self):
        keys = ('profile_special_chars', 'profile_import_refused_chars', 'profile_unsupported_chars')
        said = {'profile_special_chars': '따옴표로 감싸 시작하므로 지원됨',
                'profile_import_refused_chars': 'ENVIRONMENT_WORKER_PATH_INVALID, LIBRARY_WORKER_PATH_UNSAFE',
                'profile_unsupported_chars': 'Isaac 엔진을 시작하지 않음(engine_path_unsupported)'}
        for profile, local, expected in (
                (r'C:\Users\kim&lee', None, ('profile_import_refused_chars', ['&'])),
                (r'C:\Users\a(b)^c', None, ('profile_import_refused_chars', ['^', '(', ')'])),
                (r'C:\Users\a(b)', None, ('profile_special_chars', ['(', ')'])),
                (r'C:\Users\kim&lee', r'D:\Local', ('profile_special_chars', ['&'])),  # the workers run from D:\Local
                (r'C:\Users\Kim Lee', None, None),
                (r'C:\Users\100%user', None, ('profile_unsupported_chars', ['%'])),
                (r'C:\Users\user0042', r'D:\Data"\AppData\Local', ('profile_unsupported_chars', ['"'])),
                (r'C:\Users\kim&lee%', None, ('profile_unsupported_chars', ['%']))):  # a refused character wins
            with self.subTest(profile=profile, local=local):
                env = {'USERPROFILE': profile, 'LOCALAPPDATA': local or profile + r'\AppData\Local'}
                part = check.system_section(env, winreg=FakeWinreg({}), getproxies=dict, which=lambda name: None)
                found = [item for item in part['findings'] if item['key'] in keys]
                self.assertEqual([(item['key'], item['chars']) for item in found], [expected] if expected else [])
                for line in check.summary_lines(found)[:-1]:
                    self.assertIn(' '.join(expected[1]) + ' 문자 있음', line)
                    self.assertIn(said[expected[0]], line)

    def test_path_characters_are_the_apps_own_rules(self):
        from twinpulse_app import environment_workspace, process_manager
        app = ROOT / 'packages/twinpulse_app/src/twinpulse_app'
        for module, code in (('environment_workspace.py', 'ENVIRONMENT_WORKER_PATH_INVALID'), ('library_workspace.py', 'LIBRARY_WORKER_PATH_UNSAFE')):
            refused = re.findall(r"for c in '([^']*)'\) for \w+ in command\):raise ValueError\('" + code + r"'\)",
                                 (app / module).read_text(encoding='utf-8'))
            self.assertEqual([set(item.replace('\\n', '').replace('\\r', '')) for item in refused], [set(check.WORKER_REFUSED_CHARS)], module)
        self.assertEqual(set(process_manager._CMD_METACHARACTERS), set(check.CMD_METACHARACTERS))
        self.assertEqual(set(process_manager._CMD_UNSUPPORTED) - {'\r', '\n'}, set(check.CMD_UNSUPPORTED_CHARS))
        for command in ([r'C:\isaacsim\python.bat', '-B'], [r'D:\R&D\isaacsim\python.bat', '-B'], [r'C:\Users\a(b)\x\python.bat', 'C:\\dir\\'],
                        [r'C:\isaacsim\python.bat', r'C:\Users\a^b\script.py'], [r'C:\Users\a b\python.exe', 'x&y'],
                        [r'C:\Users\100%\python.bat'], [r'C:\isaacsim\python.bat', 'say "hi"'], [r'C:\isaacsim\python.bat', 'a\nb'], []):
            with self.subTest(command=command):
                try:
                    app_form = process_manager._batch_command_line(command)
                except process_manager.ProcessManagerError as error:
                    self.assertEqual(error.code, 'engine_path_unsupported')
                    with self.assertRaisesRegex(ValueError, '^engine_path_unsupported$'):
                        check.batch_command_line(command)
                else:
                    self.assertEqual(check.batch_command_line(command), app_form)
        # The App's own environment import, run from each user folder: refused exactly where the check says so.
        for user in ('kim&lee', 'a^b', 'a(b)', 'Kim Lee'):
            with self.subTest(user=user), tempfile.TemporaryDirectory() as temp:
                local = Path(temp) / 'Users' / user / 'AppData' / 'Local'
                isaac = Path(temp) / 'isaacsim'
                write(isaac / 'python.bat', '@echo off')
                folder = local / 'TwinPulse' / 'runtime' / 'environment-imports' / 'job1'
                write(folder / 'room.usda', '#usda 1.0')
                job, ran = {'status': 'inspecting', 'error': None, 'source_sha256': ''}, []
                with patch.dict(os.environ, {'LOCALAPPDATA': str(local), 'TWINPULSE_ISAAC_ROOT': str(isaac)}), \
                        patch.object(environment_workspace, 'run_finite', lambda *args, **kwargs: ran.append(args)), \
                        patch.object(environment_workspace, 'resource_root',
                                     lambda: local / 'TwinPulse' / 'installed' / 'releases' / 'r1' / '_internal' / 'resources'):
                    environment_workspace.EnvironmentWorkspace._inspect(SimpleNamespace(lock=threading.RLock()), folder, folder / 'room.usda',
                                                                         None, job, None, SimpleNamespace(finish=lambda *a, **k: None))
                refused_by_app = 'ENVIRONMENT_WORKER_PATH_INVALID' in str(job.get('error')) and not ran
                part = check.system_section({'USERPROFILE': str(local.parents[1]), 'LOCALAPPDATA': str(local)}, winreg=FakeWinreg({}),
                                            getproxies=dict, which=lambda name: None)
                said_refused = any(item['key'] == 'profile_import_refused_chars' for item in part['findings'])
                self.assertEqual((refused_by_app, said_refused), (user in ('kim&lee', 'a^b'),) * 2)

    def test_isaac_section_reads_version_and_redacts_kit_lines(self):
        isaac = self.root / 'isaacsim'
        write(isaac / 'python.bat', '@echo off')
        write(isaac / 'isaac-sim.bat', '@echo off')
        write(isaac / 'VERSION', '6.0.1-rc.7+release.42383.32955d8d.gl\n', bom=True)
        logs = isaac / 'kit/logs/Kit/Isaac-Sim Python/6.0'
        for index in range(4):
            lines = [f'[Error] failure {i} Authorization: Bearer tok{i}xyz\n' for i in range(100)]
            lines.insert(3, '[Warning] [omni.kit.registry.nucleus] Failed to solve some dependencies locally, syncing with extension registry\n')
            write(logs / f'kit_2026110{index}_000000.log', ''.join(lines) + '[Info] fine\n')
            os.utime(logs / f'kit_2026110{index}_000000.log', (1000 + index, 1000 + index))
        calls = []
        part = check.isaac_section({'USERPROFILE': str(self.root / 'nobody')}, [('desktop-settings', str(isaac))], candidates=(),
                                   popen=lambda args, **options: calls.append(args) or SimpleNamespace(
                                       pid=1, returncode=1, communicate=lambda timeout=None: ('', None)))
        self.assertEqual([args[0] for args in calls], [str(isaac / 'python.bat')] * 2)
        text = '\n'.join(part['lines'])
        self.assertIn('VERSION 6.0.1-rc.7+release.42383.32955d8d.gl (reviewed build)', text)
        self.assertEqual(text.count('Kit log '), 3)
        self.assertNotIn('kit_20261100_000000.log', text)
        self.assertNotIn('tok1xyz', text)
        self.assertEqual(sum(line.startswith('  [') for line in part['lines']), 3 * 80)
        self.assertEqual([item['key'] for item in part['findings']], ['isaac_found', 'kit_registry_sync'])
        missing = check.isaac_section({}, [], candidates=(str(self.root / 'none'),))
        self.assertEqual(missing['findings'], [{'key': 'isaac_missing'}])

    def test_isaac_folder_and_version_rules_are_the_exe_entrys(self):
        entry = runpy.run_path(str(ROOT / 'scripts/twinpulse_desktop_entry.py'))  # not run as __main__: nothing starts
        texts = {'reviewed': check.REVIEWED_ISAAC_VERSION, 'plain': '6.0.1', 'build': '6.0.1+local.7', 'bom': '\ufeff6.0.1\n',
                 'later-lines': '6.0.1\nsecond line\n', 'blank-first-line': '\n6.0.1', 'spaces': '  6.0.1  \n',
                 'four-parts': '6.0.1.2', 'ten': '6.0.10', 'minor': '6.1.0', 'older': '5.1.0', 'empty': '',
                 'at-limit': '6.0.1' + ' ' * 1019, 'over-limit': '6.0.1' + ' ' * 1020, 'latin1': b'6.0.1 \xe9'}
        folders = {}
        for name, text in texts.items():
            folders[name] = str(self.root / name)
            write(self.root / name / 'VERSION', text)
            write(self.root / name / 'python.bat', '@echo off')
        (self.root / 'version-folder/VERSION').mkdir(parents=True)
        write(self.root / 'version-folder/python.bat', '@echo off')
        write(self.root / 'no-bat/VERSION', '6.0.1')
        for name in [*folders, 'version-folder', 'no-bat', 'nothing-here']:
            with self.subTest(version=name):
                self.assertEqual(check.isaac_version(str(self.root / name)), entry['isaac_version'](str(self.root / name)))
        order = [folders[name] for name in ('older', 'empty', 'four-parts', 'ten', 'build', 'reviewed')]
        odd = [folders[name] for name in ('latin1', 'over-limit', 'blank-first-line')] + [str(self.root / 'version-folder')]
        rows = [(None, order), (None, order[:4]), (None, []), (None, odd), (None, odd + [folders['at-limit']]),
                (str(self.root / 'no-bat'), order), (folders['older'], order), (str(self.root / 'nothing-here'), order[:2]),
                ('', order), (folders['minor'], [])]
        for saved, candidates in rows:
            with self.subTest(saved=saved, candidates=candidates):
                self.assertEqual(check.find_isaac_root(saved, candidates), entry['find_isaac_root'](saved, candidates))

    def test_isaac_section_names_and_probes_the_folder_the_exe_will_use(self):
        def isaac(name, version=None, bat=True):
            if bat:
                write(self.root / name / 'python.bat', '@echo off')
            if version is not None:
                write(self.root / name / 'VERSION', version)
            return str(self.root / name)
        older, unversioned, release = isaac('older', '5.1.0'), isaac('unversioned'), isaac('release', '6.0.1-rc.7+local')
        offline, known = isaac('offline-drive', '6.0.1', bat=False), isaac('known', '6.0.1')
        entry = runpy.run_path(str(ROOT / 'scripts/twinpulse_desktop_entry.py'))

        def run(roots, candidates=(older, unversioned, release)):
            calls = []
            part = check.isaac_section({}, roots, candidates=candidates, popen=lambda args, **options: calls.append(args[0]) or
                                       SimpleNamespace(pid=1, returncode=1, communicate=lambda timeout=None: ('', None)))
            return calls, {item['key']: item for item in part['findings']}, check.summary_lines(part['findings'])
        calls, found, summary = run([])  # nothing saved yet: a 6.0.1 folder beats the earlier ones
        self.assertEqual((found['isaac_found']['root'], calls), (release, [str(Path(release) / 'python.bat')] * 2))
        self.assertEqual(release, entry['find_isaac_root'](None, (older, unversioned, release)))
        self.assertNotIn('isaac_version_other', found)
        calls, found, summary = run([('desktop-settings', older), ('active-release.json', known)])  # the saved folder wins
        self.assertEqual((found['isaac_found']['root'], calls), (older, [str(Path(older) / 'python.bat')] * 2))
        self.assertEqual(found['isaac_version_other'], {'key': 'isaac_version_other', 'root': older, 'version': '5.1.0'})
        calls, found, summary = run([('desktop-settings', offline)])  # saved drive not ready: this start only
        self.assertEqual((found['isaac_found']['root'], found['isaac_saved_unusable']),
                         (release, {'key': 'isaac_saved_unusable', 'saved': offline, 'root': release}))
        self.assertIn(f'저장된 Isaac 폴더 {offline}에 지금 python.bat 없음 -> EXE는 이번 실행에 {release} 사용(설정은 그대로 유지)',
                      '\n'.join(summary))
        calls, found, summary = run([('active-release.json', known)], candidates=())  # the EXE would ask with a picker
        self.assertEqual((calls, list(found)), ([], ['isaac_pick']))
        self.assertIn(f'폴더 선택 창에서 {known} 선택', summary[0])
        calls, found, summary = run([], candidates=())
        self.assertEqual((calls, list(found)), ([], ['isaac_missing']))
        # A refused desktop-settings.json: its folder is listed, the EXE uses what it finds once the file is renamed.
        part = check.isaac_section({}, [('refused desktop-settings.json', known)], candidates=(older, unversioned, release),
                                   saved_refused=True, popen=lambda args, **options: SimpleNamespace(
                                       pid=1, returncode=1, communicate=lambda timeout=None: ('', None)))
        self.assertIn(f'The EXE uses (once desktop-settings.json is renamed): {release}', part['lines'])
        self.assertEqual([item['root'] for item in part['findings'] if item['key'] == 'isaac_found'], [release])
        self.assertTrue(any(line.startswith(f'{known} (refused desktop-settings.json): python.bat yes') for line in part['lines']))

    def test_isaac_version_warning_follows_the_apps_startup_check(self):
        from twinpulse_app.startup_checks import file_checklist
        for version in (check.REVIEWED_ISAAC_VERSION, '6.0.1', '6.0.1+local', '6.0.1-rc.1', '6.0.1.2', '6.0.10', '6.1.0', '5.1.0'):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as temp:
                folder = Path(temp) / 'isaac'
                write(folder / 'VERSION', version + '\n')
                write(folder / 'python.bat', '@echo off')
                rows = file_checklist({}, state_dir=Path(temp), isaac_python=folder / 'python.bat')
                app = next(row for row in rows if row['id'] == 'isaac_version')['state']
                part = check.isaac_section({}, [('desktop-settings', str(folder))], candidates=(), popen=lambda args, **options:
                                           SimpleNamespace(pid=1, returncode=1, communicate=lambda timeout=None: ('', None)))
                warned = any(item['key'] == 'isaac_version_other' for item in part['findings'])
                self.assertEqual((warned, app), (True, 'needs_action') if app != 'ready' else (False, 'ready'))

    def test_isaac_python_probe_flags_user_site_packages(self):
        user = r'C:\Users\user0042\AppData\Roaming\Python\Python311\site-packages'
        bundled = r'D:\isaacsim\kit\python\Lib\site-packages'
        def answer(numpy, pil, user_site=True):
            return {'python': '3.11.9', 'user_site': user_site, 'user_site_path': user, 'modules': {'numpy': numpy, 'PIL': pil}}
        numpy_user, numpy_bundled = {'version': '2.1.0', 'file': user + r'\numpy\__init__.py'}, {'version': '1.26.0', 'file': bundled + r'\numpy\__init__.py'}
        pil_user, missing = {'version': '11.0.0', 'file': user.upper() + '/PIL/__init__.py'}, {'error': 'ModuleNotFoundError'}
        env = {'PYTHONPATH': r'C:\tools', 'PYTHONHOME': r'C:\Python312', 'PYTHONNOUSERSITE': '0', 'USERPROFILE': r'C:\Users\user0042'}
        for outputs, keys in (
                ({'default': answer(numpy_user, pil_user), 'twinpulse': answer(numpy_bundled, missing, False)},
                 [{'key': 'isaac_user_site_shadow', 'modules': ['numpy']}, {'key': 'isaac_needs_user_site', 'modules': ['PIL']}]),
                ({'default': answer(missing, missing), 'twinpulse': answer(numpy_bundled, missing, False)},
                 [{'key': 'isaac_user_site_shadow', 'modules': ['numpy']}]),
                ({'default': answer(numpy_bundled, missing), 'twinpulse': answer(numpy_bundled, missing, False)}, []),
                ({'default': answer(numpy_user, missing), 'twinpulse': 'hang'}, [])):
            with self.subTest(outputs=outputs):
                calls, ended = [], []
                lines, findings = check._probe_part(check.isaac_python_probe(
                    r'D:\isaacsim', env, popen=fake_python_bat(outputs, calls),
                    kill=lambda process: ended.append(process.pid) or setattr(process, 'ended', True)))
                self.assertEqual(findings, keys)
                self.assertEqual(len(lines), 2)
                self.assertEqual([args for args, _, _ in calls], [[str(Path(r'D:\isaacsim') / 'python.bat'), '-B', '-c',
                                  "import os; exec(os.environ['TWINPULSE_PROBE_CODE'])"]] * 2)
                self.assertEqual([options['stdin'] for _, options, _ in calls], [subprocess.DEVNULL] * 2)  # never waits for input
                self.assertEqual(ended, [calls[1][2].pid] if outputs['twinpulse'] == 'hang' else [])
                children = [options['env'] for _, options, _ in calls]
                # As TwinPulse starts the engine: no PYTHONHOME/PYTHONPATH; the user folder only in the first run.
                self.assertEqual([(c.get('PYTHONNOUSERSITE'), 'PYTHONPATH' in c, 'PYTHONHOME' in c) for c in children],
                                 [(None, False, False), ('1', False, False)])
                self.assertTrue(all(c['TWINPULSE_PROBE_CODE'] == check.ISAAC_PYTHON_PROBE for c in children))
        self.assertIn('Isaac Python probe, as TwinPulse starts it (PYTHONNOUSERSITE=1): not run (TimeoutExpired)', lines)
        summary = check.summary_lines([{'key': 'isaac_needs_user_site', 'modules': ['PIL']}])
        self.assertIn('PIL', summary[0])

    def test_isaac_python_probe_starts_python_bat_as_the_app_starts_it(self):
        from twinpulse_app import process_manager
        code = "import os; exec(os.environ['TWINPULSE_PROBE_CODE'])"
        answer = {'python': '3.11.9', 'user_site': False, 'user_site_path': 'x', 'modules': {}}
        for root, quoted in ((r'D:\isaacsim', False), (r'D:\R&D\isaacsim', True), (r'C:\Users\a^b\isaacsim', True),
                             (r'D:\tools (x86)\isaacsim', True), (r'D:\Isaac Sim\6.0.1', False)):
            with self.subTest(root=root):
                calls = []
                check.isaac_python_probe(root, {}, popen=fake_python_bat({'default': answer, 'twinpulse': answer}, calls))
                program = str(Path(root) / 'python.bat')
                if quoted:  # one line, every argument quoted: exactly the App's rule for this command
                    expected = process_manager._batch_command_line([program, '-B', '-c', code])
                    self.assertIsInstance(expected, str)
                else:  # a list; subprocess puts the code, which holds spaces, inside quotes
                    expected = [program, '-B', '-c', code]
                    self.assertTrue(subprocess.list2cmdline(expected).endswith(' "' + code + '"'))
                self.assertEqual([args for args, _, _ in calls], [expected] * 2)
        calls = []
        results = check.isaac_python_probe(r'D:\100%\isaacsim', {}, popen=fake_python_bat({}, calls))
        self.assertEqual(calls, [])  # the App refuses such a folder; the check does not start it either
        self.assertIn('engine_path_unsupported', results['default']['failed'])
        # The folder the EXE uses: '&' or '^' lets the engine start but stops USD imports; '%' stops the engine.
        for name, key in (('R&D', 'isaac_path_import_refused'), ('a^b', 'isaac_path_import_refused'), ('100%', 'isaac_path_unsupported'),
                          ('tools (x86)', None)):
            with self.subTest(folder=name):
                write(self.root / name / 'isaacsim' / 'python.bat', '@echo off')
                part = check.isaac_section({}, [], candidates=(str(self.root / name / 'isaacsim'),),
                                           popen=fake_python_bat({'default': answer, 'twinpulse': answer}, []))
                found = [item for item in part['findings'] if item['key'].startswith('isaac_path_')]
                self.assertEqual([item['key'] for item in found], [key] if key else [])
                for line in check.summary_lines(found)[:-1]:
                    self.assertIn('engine_path_unsupported' if key == 'isaac_path_unsupported'
                                  else 'ENVIRONMENT_WORKER_PATH_INVALID, LIBRARY_WORKER_PATH_UNSAFE', line)

    def test_isaac_and_user_folders_are_judged_as_the_app_resolves_them(self):
        from twinpulse_app import process_manager
        code = "import os; exec(os.environ['TWINPULSE_PROBE_CODE'])"
        answer = {'python': '3.11.9', 'user_site': False, 'user_site_path': 'x', 'modules': {}}
        real = self.root / 'R&D' / 'isaacsim'
        write(real / 'python.bat', '@echo off')
        tidy = self.root / 'isaacsim'
        link_folder(tidy, real)  # the App starts python.bat resolved (ProcessManager: isaac_python.resolve())
        calls = []
        part = check.isaac_section({}, [('desktop-settings', str(tidy))], candidates=(),
                                   popen=fake_python_bat({'default': answer, 'twinpulse': answer}, calls))
        found = {item['key']: item for item in part['findings']}
        resolved = str((tidy / 'python.bat').resolve().parent)
        self.assertNotIn('&', str(tidy))
        self.assertEqual((found['isaac_found']['root'], found['isaac_path_import_refused']),
                         (str(tidy), {'key': 'isaac_path_import_refused', 'root': resolved, 'chars': ['&']}))
        self.assertIn(f'The EXE uses: {tidy} (saved setting); TwinPulse resolves it to {resolved}', part['lines'])
        self.assertEqual([args for args, _, _ in calls],
                         [process_manager._batch_command_line([str(Path(resolved) / 'python.bat'), '-B', '-c', code])] * 2)
        plain = self.root / 'plain' / 'isaacsim'
        write(plain / 'python.bat', '@echo off')
        fancy = self.root / 'a&b'
        link_folder(fancy, plain)  # only the resolved folder counts, so a link's own '&' does not
        part = check.isaac_section({}, [('desktop-settings', str(fancy))], candidates=(),
                                   popen=fake_python_bat({'default': answer, 'twinpulse': answer}, []))
        self.assertEqual([item['key'] for item in part['findings'] if item['key'].startswith('isaac_path_')], [])
        local = self.root / 'kim&lee' / 'AppData' / 'Local'
        local.mkdir(parents=True)
        (self.root / 'user').mkdir()
        link_folder(self.root / 'Local', local)
        env = {'USERPROFILE': str(self.root / 'user'), 'LOCALAPPDATA': str(self.root / 'Local')}
        part = check.system_section(env, winreg=FakeWinreg({}), getproxies=dict, which=lambda name: None)
        self.assertEqual([(item['key'], item['chars']) for item in part['findings'] if item['key'].startswith('profile_')],
                         [('profile_import_refused_chars', ['&'])])
        line = next(line for line in part['lines'] if line.startswith('LOCALAPPDATA: '))
        self.assertTrue(line.startswith(f'LOCALAPPDATA: {self.root / "Local"} - ASCII only: '), line)
        self.assertTrue(line.endswith(f'; TwinPulse resolves it to {local.resolve()}'), line)

    def test_a_probe_that_hangs_is_ended_with_its_children_and_the_next_still_runs(self):
        answer = {'python': '3.11.9', 'user_site': False, 'user_site_path': 'x', 'modules': {}}
        calls, ended = [], []
        results = check.isaac_python_probe(r'D:\isaacsim', {}, popen=fake_python_bat({'default': 'hang', 'twinpulse': answer}, calls),
                                           kill=lambda process: ended.append(process.pid) or setattr(process, 'ended', True))
        self.assertEqual((results['default'], results['twinpulse']), ({'failed': 'TimeoutExpired'}, answer))
        hung, answered = calls[0][2], calls[1][2]
        self.assertEqual(ended, [hung.pid])  # only the run that hung, after its own timeout
        self.assertEqual(hung.waits, [90, check.PROBE_KILL_WAIT])  # then a bounded wait for what it wrote
        self.assertEqual((answered.waits, check.PROBE_KILL_WAIT), ([90], 10))

    def test_a_real_probe_that_hangs_is_killed_within_the_bound(self):
        processes = []

        def popen(args, **options):  # a python.bat that never answers
            processes.append(subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], **options))
            return processes[-1]
        self.addCleanup(lambda: [process.kill() or process.wait() for process in processes if process.poll() is None])
        started = time.monotonic()
        results = check.isaac_python_probe(self.root, dict(os.environ), popen=popen, timeout=0.5)
        self.assertEqual(results, {'default': {'failed': 'TimeoutExpired'}, 'twinpulse': {'failed': 'TimeoutExpired'}})
        self.assertLess(time.monotonic() - started, check.PROBE_KILL_WAIT)  # unkilled, each run would wait PROBE_KILL_WAIT more
        self.assertEqual([process.poll() is None for process in processes], [False, False])

    def test_kill_tree_ends_python_bat_and_its_children(self):
        commands, killed = [], []
        process = SimpleNamespace(pid=4321, kill=lambda: killed.append(4321))
        with patch.dict(os.environ, {'SystemRoot': '/fake/Windows'}):
            check.kill_tree(process, windows=True, run=lambda command, **options: commands.append((command, options)))
        # The absolute System32 path: a taskkill.exe in the current folder is never run.
        self.assertEqual([command for command, _ in commands],
                         [[str(Path('/fake/Windows') / 'System32' / 'taskkill.exe'), '/T', '/F', '/PID', '4321']])
        self.assertEqual((commands[0][1]['stdin'], killed), (subprocess.DEVNULL, [4321]))
        commands.clear()
        check.kill_tree(process, windows=False, run=lambda command, **options: commands.append(command))
        self.assertEqual((commands, killed), ([], [4321, 4321]))

    def test_isaac_python_probe_code_runs_in_a_real_python(self):
        # The real probe code, run by this Python in place of python.bat (no cmd.exe here).
        def popen(args, **options):
            return subprocess.Popen([sys.executable, *args[1:]], **options)
        results = check.isaac_python_probe(self.root, dict(os.environ), popen=popen, timeout=60)
        self.assertEqual(set(results), {'default', 'twinpulse'})
        for mode in ('default', 'twinpulse'):
            self.assertEqual(results[mode]['python'], sys.version.split()[0])
            self.assertEqual(set(results[mode]['modules']), {'numpy', 'PIL'})
        self.assertIs(results['twinpulse']['user_site'], False)
        lines, _findings = check._probe_part(results)
        self.assertTrue(lines[0].startswith('Isaac Python probe, plain python.bat: Python ' + sys.version.split()[0]))

    def test_main_without_network_writes_one_report_and_no_secrets(self):
        profile = self.root / 'profile'
        local = profile / 'AppData/Local'
        release = offline_release(local / 'TwinPulse/installed/releases')
        write(local / 'TwinPulse/installed/active-release.json', {'release_id': release.name}, bom=True)
        write(local / 'TwinPulse/runtime/provider-evidence/1111111111111111111111111111aaaa.json',
              {'status': 'rejected', 'http_status': 400, 'request_redacted': 'PROMPT_SENTINEL', 'response_redacted': '{"error": {"message": "x ' + SECRET + '"}}'})
        output = self.root / 'out'
        output.mkdir()
        printed = io.StringIO()

        def files():
            return {path: (path.stat().st_size, path.stat().st_mtime_ns) for path in self.root.rglob('*') if path.is_file()}
        before = files()
        with patch.object(check, 'probe', side_effect=AssertionError('network used')), \
                patch('urllib.request.getproxies', return_value={}):
            code = check.main(['--no-network', '--output-dir', str(output), '--no-pause'],
                              env={'LOCALAPPDATA': str(local), 'USERPROFILE': str(profile)}, cwd=self.root, out=printed)
        self.assertEqual(code, 0)
        reports = list(output.iterdir())
        self.assertEqual(len(reports), 1)
        self.assertIn(f'Report: {reports[0]}', printed.getvalue())
        text = reports[0].read_text(encoding='utf-8-sig')
        for heading in ('== Summary (요약) ==', '== 1. System ==', '== 2. Isaac Sim ==', '== 3. TwinPulse install ==',
                        '== 4. Runtime state ==', '== 5. Network =='):
            self.assertIn(heading, text)
        self.assertIn('네트워크 검사 생략(--no-network)', text)
        self.assertIn('active-release.json에 BOM 있음', printed.getvalue())
        for hidden in ('PROMPT_SENTINEL', SECRET):
            self.assertNotIn(hidden, text + printed.getvalue())
        after = files()  # read-only: the report is the only new or changed file in the whole tree
        self.assertEqual([path for path in after if after[path] != before.get(path)], [reports[0]])
        self.assertTrue(set(before) <= set(after))

    def test_main_gives_the_isaac_section_a_refused_settings_folder_as_refused(self):
        profile = self.root / 'profile'
        local = profile / 'AppData/Local'
        known = self.root / 'known'
        write(known / 'python.bat', '@echo off')
        write(local / 'TwinPulse/runtime/desktop-settings.json',  # an unknown key: read_settings refuses the file
              {'schema_version': '1.0', 'preferred_port': 8765, 'isaac_root': str(known), 'ready_timeout_s': 600})
        output = self.root / 'out'
        output.mkdir()
        seen = []

        def isaac(env, roots=(), **options):
            seen.append((list(roots), options))
            return check.section(['isaac'], [])
        with patch.object(check, 'isaac_section', isaac), patch.object(check, 'probe', side_effect=AssertionError('network used')), \
                patch('urllib.request.getproxies', return_value={}):
            code = check.main(['--no-network', '--output-dir', str(output), '--no-pause'],
                              env={'LOCALAPPDATA': str(local), 'USERPROFILE': str(profile)}, cwd=self.root, out=io.StringIO())
        self.assertEqual((code, seen), (0, [([('refused desktop-settings.json', str(known))], {'saved_refused': True})]))

    def test_script_imports_only_the_standard_library(self):
        tree = ast.parse((ROOT / 'scripts/twinpulse_company_pc_check.py').read_text(encoding='utf-8'))
        modules = {alias.name.split('.')[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        modules |= {node.module.split('.')[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
        self.assertEqual(sorted(name for name in modules if name not in sys.stdlib_module_names), [])
        self.assertFalse(any(name.startswith('twinpulse') for name in modules))
        ast.parse((ROOT / 'scripts/twinpulse_company_pc_check.py').read_text(encoding='utf-8'), feature_version=(3, 10))
        # feature_version does not reject 3.12-only f-strings on 3.12+, so compile with a real older Python where one is found
        # (Isaac's python.bat is 3.11). Nothing is written: no .pyc.
        older = [path for path in map(shutil.which, ('python3.10', 'python3.11')) if path]
        for python in older:
            with self.subTest(python=python):
                done = subprocess.run([python, '-I', '-c', 'import sys; compile(open(sys.argv[1], encoding="utf-8").read(), sys.argv[1], "exec")',
                                       str(ROOT / 'scripts/twinpulse_company_pc_check.py')], capture_output=True, text=True, timeout=120)
                self.assertEqual((done.returncode, done.stderr), (0, ''))


if __name__ == '__main__':
    unittest.main()
