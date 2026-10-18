# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only prerequisites and API checklist sanitization, with no installation."""
import unittest
from pathlib import Path
from unittest.mock import patch
from tests.integration.test_chat_conversation import ChatConversationTests
from twinpulse_app.startup_checks import file_checklist, package_checklist, prepare_owned_directories
from twinpulse_app.api import _sanitize_supervisor_status


class StartupChecklistTests(unittest.TestCase):
    setUp = ChatConversationTests.setUp
    tearDown = ChatConversationTests.tearDown
    request = ChatConversationTests.request
    product_headers = ChatConversationTests.product_headers

    def test_missing_file_does_not_hide_independent_checks(self):
        found=self.static/'runtime.exe';found.write_bytes(b'fixture')
        version=self.static/'VERSION';version.write_text('6.0.1-rc.7+release.42383.32955d8d.gl',encoding='utf-8')
        before=version.read_bytes()
        rows=file_checklist({'found':found,'missing':self.static/'missing.exe'},state_dir=self.static,isaac_python=found)
        states={row['id']:row['state'] for row in rows}
        self.assertEqual(states['found'],'ready');self.assertEqual(states['missing'],'needs_action')
        self.assertEqual(states['isaac_version'],'ready')
        self.assertEqual(version.read_bytes(),before)

    def test_unknown_version_and_disk_error_are_not_ready(self):
        (self.static/'VERSION').write_text('unknown-version',encoding='utf-8')
        with patch('twinpulse_app.startup_checks.shutil.disk_usage',side_effect=OSError('fixture')):
            rows=file_checklist({},state_dir=self.static,isaac_python=self.static/'runtime.exe')
        self.assertEqual({row['id']:row['state'] for row in rows},{'project_disk':'failed','project_write':'ready','isaac_version':'needs_action'})

    def test_permission_failure_is_distinct_and_does_not_change_permissions(self):
        with patch('twinpulse_app.startup_checks.tempfile.NamedTemporaryFile',side_effect=PermissionError('fixture')):
            rows=file_checklist({},state_dir=self.static,isaac_python=self.static/'runtime.exe')
        states={row['id']:row['state'] for row in rows}
        self.assertEqual(states['project_write'],'failed');self.assertEqual(states['project_disk'],'ready')
        self.assertEqual(list(self.static.glob('twinpulse-write-check-*')),[])

    def test_checklist_api_only_exposes_bounded_display_fields(self):
        status=_sanitize_supervisor_status({'status':'error','secret':'do-not-copy', 'startup_checks':[
            {'id':'web_build','state':'needs_action','detail':'Missing local Web build','action':'Restore reviewed build','sampled_at':'now','secret':'do-not-copy'},
            {'id':'../../private','state':'ready','detail':'bad'}]})
        self.assertNotIn('do-not-copy',str(status))
        self.assertEqual(len(status['startup_checks']),1)

    def test_web_manifest_detects_modified_chunk_without_overwriting_it(self):
        import json
        from hashlib import sha256
        web=self.static/'apps/twinpulse-web/dist';web.mkdir(parents=True)
        (web/'assets').mkdir()
        index=b'<script type="module" src="/assets/app.js"></script>'
        (web/'index.html').write_bytes(index);(web/'assets/app.js').write_bytes(b'original')
        (web/'twinpulse-build-manifest.json').write_text(json.dumps({'schema_version':'1.0','files':{
            'index.html':sha256(index).hexdigest(),'assets/app.js':sha256(b'original').hexdigest()}}))
        rows=package_checklist(self.static)
        self.assertEqual(next(r for r in rows if r['id']=='web_dependencies')['state'],'ready')
        (web/'assets/app.js').write_bytes(b'changed')
        row=next(r for r in package_checklist(self.static) if r['id']=='web_dependencies')
        self.assertEqual(row['state'],'needs_action');self.assertIn('BUILD_DIGEST_MISMATCH',row['detail'])
        self.assertEqual((web/'assets/app.js').read_bytes(),b'changed')

    def test_unsafe_and_incomplete_web_manifest_keep_other_results(self):
        import json
        web=self.static/'apps/twinpulse-web/dist';web.mkdir(parents=True)
        (web/'twinpulse-build-manifest.json').write_text(json.dumps({'schema_version':'1.0','files':{'../private':'0'*64}}))
        rows=package_checklist(self.static)
        self.assertIn('BUILD_MANIFEST_UNSAFE',next(r for r in rows if r['id']=='web_dependencies')['detail'])
        self.assertTrue({'burger_asset_manifest','extension_contract','python_dependencies'} <= {r['id'] for r in rows})

    def test_asset_tampering_rejected_and_original_not_repaired(self):
        from twinpulse_app.simulation_assets import _inventory, ASSET_ROOT
        import shutil
        local=self.static/'burger';shutil.copytree(ASSET_ROOT,local)
        _inventory(local)
        (local/'payloads/base.usda').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'SIM_BURGER_ASSET_DIGEST_MISMATCH'):_inventory(local)
        self.assertEqual((local/'payloads/base.usda').read_bytes(),b'changed')

    def test_owned_directory_repair_is_bounded_and_preserves_existing_content(self):
        launch=self.static/'launches'/'fresh_owned'
        rows=prepare_owned_directories(launch)
        self.assertEqual(len(rows),2);self.assertTrue(all(r['state']=='ready' for r in rows))
        self.assertTrue(all(r['attempts']==1 for r in rows))
        source=launch/'engine-state'/'preserve.json';source.write_bytes(b'original')
        self.assertTrue(all(r['attempts']==0 for r in prepare_owned_directories(launch)))
        self.assertEqual(source.read_bytes(),b'original')
        with patch('twinpulse_app.startup_checks.Path.mkdir',side_effect=PermissionError('fixture')) as mkdir:
            rows=prepare_owned_directories(self.static/'launches'/'blocked')
        self.assertEqual(mkdir.call_count,2);self.assertTrue(all(r['state']=='failed' for r in rows))
        self.assertTrue(all(r['attempts']==1 for r in rows))

    def test_malformed_manifest_and_extension_do_not_abort_other_checks(self):
        web=self.static/'apps/twinpulse-web/dist';web.mkdir(parents=True)
        (web/'twinpulse-build-manifest.json').write_text('[]')
        extension=self.static/'extensions/twinpulse.extension/config';extension.mkdir(parents=True)
        (extension/'extension.toml').write_text('python = 7\nsettings = 3')
        rows={r['id']:r for r in package_checklist(self.static)}
        self.assertEqual(rows['web_dependencies']['detail'],'BUILD_MANIFEST_INVALID')
        self.assertEqual(rows['extension_contract']['detail'],'EXTENSION_CONTRACT_INVALID')
        self.assertEqual(rows['python_dependencies']['state'],'ready')

    def test_different_configured_python_not_claimed_qualified(self):
        row=next(r for r in package_checklist(self.static,python_executable=self.static/'other.exe') if r['id']=='python_dependencies')
        self.assertEqual(row['detail'],'CONFIGURED_PYTHON_ENVIRONMENT_NOT_OBSERVED')
        self.assertEqual(row['state'],'needs_action')


if __name__=='__main__':unittest.main()
