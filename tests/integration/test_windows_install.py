# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Supplementary installation atomicity and old-pointer preservation."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys
ROOT=Path(__file__).resolve().parents[2]
for name in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
from twinpulse_app.windows_install import install_package
from twinpulse_app.release_contract import MaintenanceLock, DATA_CONTRACT, atomic_json, initialize_data_epoch


class WindowsInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.source=self.root/'source';self.source.mkdir()
        data=b'package-placeholder';(self.source/'TwinPulse.exe').write_bytes(data)
        self.manifest={'schema':'twinpulse-windows-exe-1.0','build_id':'build_1',
            'source_manifest_sha256':'a'*64,'files':[{'path':'TwinPulse.exe','bytes':len(data),
                'sha256':hashlib.sha256(data).hexdigest()}]}
        (self.source/'windows-release-manifest.json').write_text(json.dumps(self.manifest))
        self.installed=self.root/'installed'
        self.environment=patch.dict(os.environ,{'LOCALAPPDATA':str(self.root/'profile')});self.environment.start()
    def tearDown(self):
        self.environment.stop();self.temp.cleanup()
    def test_legacy_pointer_preserved_and_idempotent_reinstall(self):
        self.installed.mkdir();active=self.installed/'active-release.json'
        original=b'{"release_id":"legacy","isaac_root":"existing"}';active.write_bytes(original)
        result=install_package(self.source,self.installed)
        self.assertTrue(Path(result['exe']).is_file())
        previous=list(self.installed.glob('active-release.previous.*.json'))
        self.assertEqual(previous[0].read_bytes(),original)
        self.assertEqual(install_package(self.source,self.installed)['build_id'],'build_1')
    def test_corrupt_package_does_not_change_active_pointer(self):
        self.installed.mkdir();active=self.installed/'active-release.json';active.write_bytes(b'old')
        (self.source/'TwinPulse.exe').write_bytes(b'bad')
        with self.assertRaises(ValueError):install_package(self.source,self.installed)
        self.assertEqual(active.read_bytes(),b'old')

    def test_optional_desktop_reuse_shares_only_verified_identical_immutable_bytes(self):
        from twinpulse_app.windows_package import verify_package
        (self.source/'desktop').mkdir();data=b'verified-electron-fixture'
        (self.source/'desktop/runtime.bin').write_bytes(data)
        self.manifest['files'].append(dict(path='desktop/runtime.bin',bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
        (self.source/'windows-release-manifest.json').write_text(json.dumps(self.manifest))
        first=install_package(self.source,self.installed);old=Path(first['exe']).parent
        self.manifest['build_id']='build_2';(self.source/'windows-release-manifest.json').write_text(json.dumps(self.manifest))
        second=install_package(self.source,self.installed,reuse_desktop_from=old);new=Path(second['exe']).parent
        self.assertEqual(second['verified_desktop_hardlinks'],1)
        self.assertTrue(os.path.samefile(old/'desktop/runtime.bin',new/'desktop/runtime.bin'))
        self.assertFalse(os.path.samefile(old/'TwinPulse.exe',new/'TwinPulse.exe'))
        verify_package(old);verify_package(new)
        self.manifest['build_id']='build_3';(self.source/'windows-release-manifest.json').write_text(json.dumps(self.manifest))
        with patch('twinpulse_app.windows_install.os.link',side_effect=OSError('unsupported')):
            fallback=install_package(self.source,self.installed,reuse_desktop_from=old)
        self.assertEqual(fallback['verified_desktop_hardlinks'],0)
        verify_package(Path(fallback['exe']).parent)
    def test_live_launch_is_not_overwritten(self):
        state=self.root/'profile/TwinPulse/runtime';state.mkdir(parents=True)
        (state/'launcher.lock').write_text('owned')
        with self.assertRaisesRegex(ValueError,'EXIT_TWINPULSE_BEFORE_INSTALL'):
            install_package(self.source,self.installed)
        self.assertFalse(self.installed.exists())

    def test_new_epoch_cannot_be_opened_by_old_program_and_bytes_are_preserved(self):
        state=self.root/'profile/TwinPulse/runtime';state.mkdir(parents=True)
        marker=state/'data-compatibility.json'
        atomic_json(marker,dict(schema='twinpulse-runtime-data-1.0',data_epoch=2))
        original=marker.read_bytes()
        with self.assertRaisesRegex(ValueError,'DATA_VERSION_REQUIRES_COMPATIBLE_RELEASE'):
            install_package(self.source,self.installed)
        self.assertEqual(marker.read_bytes(),original)
        self.assertFalse((self.installed/'active-release.json').exists())

    def test_kernel_maintenance_lock_excludes_concurrent_installer_without_stale_lock(self):
        state=self.root/'profile/TwinPulse/runtime'
        with MaintenanceLock(state):
            with self.assertRaisesRegex(ValueError,'UPDATE_IN_PROGRESS'):
                install_package(self.source,self.installed)
        self.assertEqual(install_package(self.source,self.installed)['build_id'],'build_1')

    def test_stable_entry_and_install_interruption_preserve_matching_data_and_program(self):
        self.manifest['data_contract']=DATA_CONTRACT
        (self.source/'windows-release-manifest.json').write_text(json.dumps(self.manifest))
        install_package(self.source,self.installed)
        state=self.root/'profile/TwinPulse/runtime';state.mkdir(parents=True,exist_ok=True)
        project=state/'active_project.json';project.write_bytes(b'private-user-scene')
        self.manifest['build_id']='build_2'
        (self.source/'windows-release-manifest.json').write_text(json.dumps(self.manifest))
        replace_original=os.replace
        def interrupt(source,target):
            if Path(target).name=='Start-TwinPulse.cmd':raise OSError('simulated-entry-write-interruption')
            return replace_original(source,target)
        with patch('twinpulse_app.windows_install.os.replace',side_effect=interrupt):
            with self.assertRaisesRegex(OSError,'simulated-entry'):
                install_package(self.source,self.installed)
        self.assertEqual(json.loads((self.installed/'active-release.json').read_text())['release_id'],'build_2')
        self.assertEqual(project.read_bytes(),b'private-user-scene')
        self.assertEqual(install_package(self.source,self.installed)['build_id'],'build_2')
        self.assertIn('active-release.json',(self.installed/'start-installed.ps1').read_text())
        self.assertEqual(project.read_bytes(),b'private-user-scene')

    def test_dead_launcher_record_is_archived_and_does_not_lock_installation(self):
        state=self.root/'profile/TwinPulse/runtime';state.mkdir(parents=True)
        original=b'{"pid":9999999,"launch_id":"old-test-owner"}'
        (state/'launcher.lock').write_bytes(original)
        with patch('twinpulse_app.process_manager._pid_alive',return_value=False):
            install_package(self.source,self.installed)
        self.assertEqual(next((state/'stale-launch-records').glob('*.json')).read_bytes(),original)

    def test_dangling_compatibility_link_is_rejected_without_replacement(self):
        state=self.root/'profile/TwinPulse/runtime';state.mkdir(parents=True)
        marker=state/'data-compatibility.json'
        target=self.root/'missing-target.json'
        try:
            marker.symlink_to(target)
        except OSError as error:
            self.skipTest(f'Native symlink creation unavailable: {error.errno}')
        with self.assertRaisesRegex(ValueError,'DATA_COMPATIBILITY_RECORD_INVALID'):
            initialize_data_epoch(state)
        self.assertTrue(marker.is_symlink())
        self.assertFalse(target.exists())
        with self.assertRaisesRegex(ValueError,'DATA_COMPATIBILITY_RECORD_INVALID'):
            install_package(self.source,self.installed)
        self.assertTrue(marker.is_symlink())
        self.assertFalse((self.installed/'active-release.json').exists())

if __name__=='__main__':unittest.main()
