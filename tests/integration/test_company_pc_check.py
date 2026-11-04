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
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
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


class FakeWinreg:
    HKEY_LOCAL_MACHINE, HKEY_CURRENT_USER, KEY_READ = 'HKLM', 'HKCU', 1

    def __init__(self, values):
        self.values = values

    def OpenKey(self, hive, key, reserved, access):
        if not any(h == hive and k == key for h, k, _ in self.values):
            raise OSError('no key')
        return FakeKey(hive, key)

    def QueryValueEx(self, handle, name):
        if (handle.hive, handle.key, name) not in self.values:
            raise OSError('no value')
        return self.values[(handle.hive, handle.key, name)], 1


class FakeFilter(BaseHTTPRequestHandler):
    """A network filter that answers Python-urllib (or everyone) with an HTML block page."""
    seen, block_all = [], False

    def do_GET(self):
        agent = self.headers.get('User-Agent', '')
        FakeFilter.seen.append({'agent': agent, 'authorization': self.headers.get('Authorization'), 'path': self.path})
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
                            r'D:\isaacsim\isaac-sim-standalone-6.0.1-windows-x86_64 omni.kit.pip_archive-0.0.0+f9bf0dda.wx64.cp312 외부사이트 차단')
        for secret in (SECRET, 'abc.def-123', 'plain-value', 'hunter2', '9f86d081884c7d659a2feaa0c55ad015',
                       'Zm9vYmFyYmF6cXV4', 'user:pw', 'eyJhbGciOiJIUzI1NiJ9', 'c2lnbmF0dXJl'):
            self.assertNotIn(secret, text)
        for kept in (r'D:\isaacsim\isaac-sim-standalone-6.0.1-windows-x86_64', 'omni.kit.pip_archive-0.0.0+f9bf0dda.wx64.cp312',
                     'proxy.example:8080', '외부사이트 차단'):
            self.assertIn(kept, text)
        self.assertEqual(check.redact('test_robot_evidence_recovery_with_long_names'), 'test_robot_evidence_recovery_with_long_names')
        long = check.short('x' * 50 + ' ' + SECRET + ' y' * 400, 120)
        self.assertLessEqual(len(long), 120)
        self.assertNotIn('SECRETSECRET', check.short(('a' * 4790) + SECRET, 300))

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
        self.assertEqual(part['facts'], {'settings_isaac_root': r'D:\isaacsim'})
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


class NetworkTests(unittest.TestCase):
    def setUp(self):
        FakeFilter.seen, FakeFilter.block_all = [], False
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
        self.assertIn('ProxyServer: http://[REDACTED]@proxy.corp:8080', text)
        for hidden in ('user:pass', 'u:p@'):
            self.assertNotIn(hidden, text)
        lines = check.summary_lines(part['findings'])
        self.assertTrue(any('PowerShell 없이' in line for line in lines))

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
        part = check.isaac_section({'USERPROFILE': str(self.root / 'nobody')}, [('desktop-settings', str(isaac))], candidates=())
        text = '\n'.join(part['lines'])
        self.assertIn('VERSION 6.0.1-rc.7+release.42383.32955d8d.gl (reviewed build)', text)
        self.assertEqual(text.count('Kit log '), 3)
        self.assertNotIn('kit_20261100_000000.log', text)
        self.assertNotIn('tok1xyz', text)
        self.assertEqual(sum(line.startswith('  [') for line in part['lines']), 3 * 80)
        self.assertEqual([item['key'] for item in part['findings']], ['isaac_found', 'kit_registry_sync'])
        missing = check.isaac_section({}, [], candidates=(str(self.root / 'none'),))
        self.assertEqual(missing['findings'], [{'key': 'isaac_missing'}])

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
        self.assertEqual(sorted(p.name for p in (local / 'TwinPulse').rglob('*') if p.name.startswith('TwinPulse-PC-Check')), [])

    def test_script_imports_only_the_standard_library(self):
        tree = ast.parse((ROOT / 'scripts/twinpulse_company_pc_check.py').read_text(encoding='utf-8'))
        modules = {alias.name.split('.')[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        modules |= {node.module.split('.')[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
        self.assertEqual(sorted(name for name in modules if name not in sys.stdlib_module_names), [])
        self.assertFalse(any(name.startswith('twinpulse') for name in modules))
        ast.parse((ROOT / 'scripts/twinpulse_company_pc_check.py').read_text(encoding='utf-8'), feature_version=(3, 10))


if __name__ == '__main__':
    unittest.main()
