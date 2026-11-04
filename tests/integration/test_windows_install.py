# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Supplementary installation atomicity and old-pointer preservation."""
from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import shutil
import sys
ROOT=Path(__file__).resolve().parents[2]
for name in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
from twinpulse_app.windows_install import install_package
from twinpulse_app.windows_package import verify_package
from twinpulse_app.release_contract import (MaintenanceLock, DATA_CONTRACT, REPLACE_ATTEMPTS, atomic_json,
                                            initialize_data_epoch)
from twinpulse_app.process_manager import ProcessManagerError, TwinPulseProcessManager


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
    def test_bom_legacy_pointer_installs_with_identical_backup_and_parsed_journal(self):
        self.installed.mkdir();active=self.installed/'active-release.json'
        # Install-Offline.cmd (PowerShell 5.1 Set-Content -Encoding UTF8) wrote a BOM.
        original=(b'\xef\xbb\xbf{\r\n    "release_id":  "tp-550821745917",\r\n'
                  b'    "isaac_root":  "D:\\\\isaacsim\\\\isaac-sim-standalone-6.0.1-windows-x86_64"\r\n}\r\n')
        active.write_bytes(original)
        result=install_package(self.source,self.installed)
        self.assertTrue(Path(result['exe']).is_file())
        self.assertEqual(next(self.installed.glob('active-release.previous.*.json')).read_bytes(),original)
        journal=json.loads(next((self.installed/'update-journals').glob('*.json')).read_text(encoding='utf-8'))
        self.assertEqual(journal['previous'],{'release_id':'tp-550821745917',
            'isaac_root':'D:\\isaacsim\\isaac-sim-standalone-6.0.1-windows-x86_64'})
        self.assertEqual(journal['phase'],'completed')
        self.assertEqual(json.loads(active.read_bytes())['release_id'],'build_1')

    def test_unparseable_legacy_pointer_is_recorded_not_fatal(self):
        self.installed.mkdir();active=self.installed/'active-release.json'
        original=b'\xff\xfe{not json';active.write_bytes(original)
        self.assertEqual(install_package(self.source,self.installed)['build_id'],'build_1')
        self.assertEqual(next(self.installed.glob('active-release.previous.*.json')).read_bytes(),original)
        journal=json.loads(next((self.installed/'update-journals').glob('*.json')).read_text(encoding='utf-8'))
        self.assertEqual(journal['previous'],{'unparsed':True,'bytes':len(original)})
        self.assertEqual(json.loads(active.read_bytes())['release_id'],'build_1')

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
        state=self.root/'profile/TwinPulse/runtime';state.mkdir(parents=True);lock=state/'launcher.lock'
        identity={'executable':'C:\\TwinPulse\\releases\\old\\TwinPulse.exe','creation_filetime':133}
        lock.write_text(json.dumps({'owner_pid':4242,'launch_id':'a'*32,'process_identity':identity}),encoding='utf-8')
        original=lock.read_bytes()
        with patch('twinpulse_app.process_manager._pid_alive',return_value=True), \
                patch('twinpulse_app.process_manager._process_identity',return_value=dict(identity)):
            with self.assertRaisesRegex(ValueError,'^EXIT_TWINPULSE_BEFORE_INSTALL$'):
                install_package(self.source,self.installed)
        self.assertEqual(lock.read_bytes(),original)
        self.assertFalse(self.installed.exists())

    def test_unreadable_lock_or_one_without_a_valid_pid_stops_install_with_its_own_code_and_is_kept(self):
        state=self.root/'profile/TwinPulse/runtime';state.mkdir(parents=True);lock=state/'launcher.lock'
        # An empty file is what a crash between creating and writing the lock leaves.
        for content in (b'',b'owned',b'{"owner_pid":',b'\xff\xfe{}',b'[4242]',b'"4242"',b'{}',b'{"owner_pid":"4242"}',
                        b'{"owner_pid":0}',b'{"pid":-7}',b'{"owner_pid":true}',b'{"owner_pid":null,"pid":4242}'):
            with self.subTest(content=content):
                lock.write_bytes(content)
                # Even with no live process, such a lock is never judged stale.
                with patch('twinpulse_app.process_manager._pid_alive',return_value=False):
                    with self.assertRaisesRegex(ValueError,'^INSTALL_LAUNCHER_LOCK_UNREADABLE$'):
                        install_package(self.source,self.installed)
                self.assertEqual(lock.read_bytes(),content)
                self.assertFalse((state/'stale-launch-records').exists())
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

    def test_required_feature_barrier_rejects_legacy_install_before_pointer_change(self):
        from twinpulse_app.release_contract import require_data_capability
        state=self.root/'profile/TwinPulse/runtime'
        require_data_capability(state,'environment-static-1.1')
        marker=(state/'data-compatibility.json').read_bytes()
        # No contract must not inherit the new installer's feature support.
        with self.assertRaisesRegex(ValueError,'DATA_CAPABILITY'):
            install_package(self.source,self.installed)
        self.assertFalse((self.installed/'active-release.json').exists())
        self.manifest['data_contract']=dict(DATA_CONTRACT)
        (self.source/'windows-release-manifest.json').write_text(json.dumps(self.manifest))
        self.assertEqual(install_package(self.source,self.installed)['build_id'],'build_1')
        self.assertEqual((state/'data-compatibility.json').read_bytes(),marker)
        self.manifest['build_id']='old_compatible_epoch_only'
        self.manifest['data_contract']={k:v for k,v in DATA_CONTRACT.items() if k!='read_capabilities'}
        (self.source/'windows-release-manifest.json').write_text(json.dumps(self.manifest))
        active=(self.installed/'active-release.json').read_bytes()
        with self.assertRaisesRegex(ValueError,'DATA_CAPABILITY'):
            install_package(self.source,self.installed)
        self.assertEqual((self.installed/'active-release.json').read_bytes(),active)

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

    def test_installer_and_launcher_take_the_same_decision_on_every_launcher_lock(self):
        recorded={'executable':'C:\\TwinPulse\\releases\\old\\TwinPulse.exe','creation_filetime':133}
        other={'executable':'C:\\Windows\\explorer.exe','creation_filetime':134}
        rows=(  # (owner PID alive, recorded identity, identity of that PID now, decision)
            (True,recorded,dict(recorded),'refuse'),           # the owner still runs
            (True,recorded,None,'refuse'),                     # its identity cannot be read now
            (True,None,other,'refuse'),                        # an older lock without an identity
            (True,recorded,dict(recorded,executable='\\\\?\\'+recorded['executable']),'refuse'),  # same start, other spelling
            (True,'malformed',other,'refuse'),
            (True,{'creation_filetime':True},{'creation_filetime':2},'refuse'),   # a bool is no creation time
            (True,{'creation_filetime':'133'},other,'refuse'),
            (True,recorded,{'executable':recorded['executable']},'refuse'),
            (True,recorded,other,'archive'),                   # Windows proves PID reuse
            (True,{'creation_filetime':133},{'creation_filetime':134},'archive'),
            (False,recorded,dict(recorded),'archive'),         # the owner has exited
            (False,'malformed',None,'archive'),
        )
        for number,(alive,stored,current,decision) in enumerate(rows):
            with self.subTest(alive=alive,stored=stored,current=current):
                content=json.dumps({'owner_pid':4242,'launch_id':'a'*32,'process_identity':stored}).encode()
                profile=self.root/('row-%02d'%number)
                launcher_state=profile/'launcher';install_state=profile/'TwinPulse/runtime'
                for state in (launcher_state,install_state):
                    state.mkdir(parents=True);(state/'launcher.lock').write_bytes(content)
                manager=TwinPulseProcessManager(repo_root=self.root,state_dir=launcher_state,
                    python_executable=self.root/'python.exe',isaac_python=self.root/'isaac/python.bat')
                outcome={}
                with patch('twinpulse_app.process_manager._pid_alive',return_value=alive), \
                        patch('twinpulse_app.process_manager._process_identity',return_value=current), \
                        patch.dict(os.environ,{'LOCALAPPDATA':str(profile)}):
                    try:
                        with redirect_stdout(io.StringIO()):manager._acquire_launcher_lock()
                    except ProcessManagerError:outcome['launcher']='refuse'
                    else:
                        outcome['launcher']='archive';manager._release_lock()
                    try:install_package(self.source,profile/'installed')
                    except ValueError as error:
                        self.assertEqual(str(error),'EXIT_TWINPULSE_BEFORE_INSTALL');outcome['installer']='refuse'
                    else:outcome['installer']='archive'
                self.assertEqual(outcome,{'launcher':decision,'installer':decision})
                for state in (launcher_state,install_state):
                    archived=[p.read_bytes() for p in (state/'stale-launch-records').glob('*.json')]
                    if decision=='refuse':
                        self.assertEqual((state/'launcher.lock').read_bytes(),content);self.assertEqual(archived,[])
                    else:
                        self.assertFalse((state/'launcher.lock').exists());self.assertEqual(archived,[content])
                self.assertEqual((profile/'installed/active-release.json').exists(),decision=='archive')

    def journal(self,build_id):
        rows=[json.loads(p.read_text(encoding='utf-8')) for p in (self.installed/'update-journals').glob('*.json')]
        return [row for row in rows if row['target']['release_id']==build_id]

    def update_to_build_2(self):
        self.manifest['data_contract']=DATA_CONTRACT
        (self.source/'windows-release-manifest.json').write_text(json.dumps(self.manifest))
        install_package(self.source,self.installed)
        self.manifest['build_id']='build_2'
        (self.source/'windows-release-manifest.json').write_text(json.dumps(self.manifest))

    def entry_release(self,name):
        content=(self.installed/name).read_bytes()
        return [build for build in ('build_1','build_2') if ('releases\\'+build+'\\').encode() in content]

    def test_entry_replace_waits_out_a_scanner_and_names_the_new_release(self):
        self.update_to_build_2();replace=os.replace;held=[]
        def scanned_once(source,target):
            if Path(target).name=='Start-TwinPulse.cmd' and not held:
                held.append(target);raise PermissionError(13,'held by a scanner',str(target))
            return replace(source,target)
        with patch('twinpulse_app.release_contract.os.replace',side_effect=scanned_once):
            install_package(self.source,self.installed)
        self.assertEqual(len(held),1)
        for name in ('Start-TwinPulse.cmd','Start-TwinPulse-Test.cmd'):
            self.assertEqual(self.entry_release(name),['build_2'])
        [journal]=self.journal('build_2')
        self.assertEqual((journal['phase'],journal['entries_pending']),('completed',[]))
        self.assertEqual(sorted(p.name for p in self.installed.iterdir() if p.name.endswith('.tmp')),[])

    def test_entry_held_open_raises_after_the_pointer_commit_and_the_journal_lists_it_as_pending(self):
        self.update_to_build_2();replace=os.replace;attempts=[]
        def held(source,target):
            if Path(target).name=='Start-TwinPulse-Test.cmd':
                attempts.append(target);raise PermissionError(13,'held open',str(target))
            return replace(source,target)
        with patch('twinpulse_app.release_contract.os.replace',side_effect=held):
            with self.assertRaises(PermissionError):
                install_package(self.source,self.installed)
        self.assertEqual(len(attempts),REPLACE_ATTEMPTS)
        self.assertEqual(json.loads((self.installed/'active-release.json').read_text())['release_id'],'build_2')
        self.assertEqual(self.entry_release('Start-TwinPulse.cmd'),['build_2'])
        self.assertEqual(self.entry_release('Start-TwinPulse-Test.cmd'),['build_1'])
        [journal]=self.journal('build_2')
        self.assertEqual((journal['phase'],journal['entries_pending']),
                         ('active_pointer_committed',['Start-TwinPulse-Test.cmd','start-installed.ps1']))
        self.assertEqual(sorted(p.name for p in self.installed.iterdir() if p.name.endswith('.tmp')),[])
        install_package(self.source,self.installed)  # installing again finishes the entries
        self.assertEqual(self.entry_release('Start-TwinPulse-Test.cmd'),['build_2'])

    def test_entries_are_written_before_the_pointer_moves(self):
        self.update_to_build_2();open_file=Path.open
        def full(path,*arguments,**options):
            if path.name.startswith('.start-installed.ps1-'):raise OSError(28,'No space left on device')
            return open_file(path,*arguments,**options)
        with patch.object(Path,'open',autospec=True,side_effect=full):
            with self.assertRaisesRegex(OSError,'No space left'):
                install_package(self.source,self.installed)
        # A failed entry write leaves the old pointer and the old entries together.
        self.assertEqual(json.loads((self.installed/'active-release.json').read_text())['release_id'],'build_1')
        self.assertEqual(self.entry_release('Start-TwinPulse.cmd'),['build_1'])
        [journal]=self.journal('build_2')
        self.assertEqual(journal['phase'],'package_verified')
        self.assertEqual(sorted(p.name for p in self.installed.iterdir() if p.name.endswith('.tmp')),[])

    def test_journal_and_record_writes_wait_out_a_scanner_and_raise_when_the_file_stays_held(self):
        target=self.root/'state'/'record.json';replace=os.replace;calls=[]
        def held_once(source,destination):
            calls.append(destination)
            if len(calls)==1:raise PermissionError(13,'held by a scanner',str(destination))
            return replace(source,destination)
        with patch('twinpulse_app.release_contract.os.replace',side_effect=held_once):
            atomic_json(target,{'value':1})
        self.assertEqual((len(calls),json.loads(target.read_text())),(2,{'value':1}))
        with patch('twinpulse_app.release_contract.os.replace',side_effect=PermissionError(13,'held open')) as held:
            with self.assertRaises(PermissionError):
                atomic_json(target,{'value':2})
        self.assertEqual(held.call_count,REPLACE_ATTEMPTS)
        self.assertEqual(json.loads(target.read_text()),{'value':1})  # the earlier record stays whole

    def test_file_manager_junk_never_enters_a_release_and_stage_name_is_short(self):
        (self.source/'desktop.ini').write_bytes(b'[.ShellClassInfo]');(self.source/'sub').mkdir()
        (self.source/'sub/Thumbs.db').write_bytes(b'thumbnail')
        data=b'listed-content'  # A listed junk-named file is package content and is kept.
        (self.source/'.DS_Store').write_bytes(data)
        self.manifest['files'].append(dict(path='.DS_Store',bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
        (self.source/'windows-release-manifest.json').write_text('\ufeff'+json.dumps(self.manifest),encoding='utf-8')
        stages=[];copytree=shutil.copytree
        def record(source,target,*arguments,**options):  # shutil recurses through this name
            stages.append(Path(target).name);return copytree(source,target,*arguments,**options)
        with patch('twinpulse_app.windows_install.shutil.copytree',side_effect=record):
            release=Path(install_package(self.source,self.installed)['exe']).parent
        self.assertRegex(stages[0],r'^\.stage-[0-9a-f]{12}$')
        self.assertEqual(sorted(p.relative_to(release).as_posix() for p in release.rglob('*') if p.is_file()),
                         ['.DS_Store','TwinPulse.exe','windows-release-manifest.json'])
        self.assertEqual(verify_package(release)['files'],2)
        (self.source/'notes.txt').write_bytes(b'unlisted');self.manifest['build_id']='build_2'
        (self.source/'windows-release-manifest.json').write_text(json.dumps(self.manifest))
        active=(self.installed/'active-release.json').read_bytes()
        with self.assertRaisesRegex(ValueError,'^WINDOWS_PACKAGE_UNMANIFESTED_FILE: notes.txt$'):
            install_package(self.source,self.installed)
        self.assertEqual((self.installed/'active-release.json').read_bytes(),active)

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
