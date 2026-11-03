# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Supplementary bootstrap byte/path checks; no installed App execution.

Deliberate guard change (owner decision 2026-11-03): the SHA-256 of every file
is verified at install (verify_package on the source and on the staged copy)
and by --inspect-package. A normal start runs the quick check (each listed
file exists, is no link, stays under the root, has its recorded size), and an
--internal-role child only validates the manifest. A same-size edit after
installation is therefore found by --inspect-package or a reinstall, not at
start. full=True keeps the per-byte check every start ran before.
"""
import hashlib
import json
from pathlib import Path
import runpy
import tempfile
import unittest

module=runpy.run_path(str(Path(__file__).resolve().parents[2]/'scripts/twinpulse_bootstrap_integrity.py'))
verify=module['verify_before_import'];read_manifest=module['read_manifest']


def package(root,names,prefix=''):
    files=[]
    for i,name in enumerate(names):
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);data=bytes([i])*20;path.write_bytes(data)
        files.append(dict(path=name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
    (root/'windows-release-manifest.json').write_text(prefix+json.dumps(dict(schema='twinpulse-windows-exe-1.0',files=files)),encoding='utf-8')
    return files


class BootstrapIntegrityTests(unittest.TestCase):
    def test_full_mode_still_hashes_every_file_and_next_call_revalidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);files=package(root,[f'shared/ancestor/{i}.bin' for i in range(5)])
            self.assertEqual(len(verify(root,full=True)['files']),5)
            (root/files[-1]['path']).write_bytes(b'x'*20)
            with self.assertRaisesRegex(ValueError,r'^WINDOWS_PACKAGE_FILE_MISMATCH: shared/ancestor/4\.bin$'):verify(root,full=True)

    def test_quick_start_check_names_missing_or_resized_files_but_not_same_size_edits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);files=package(root,[f'shared/ancestor/{i}.bin' for i in range(5)])
            (root/files[-1]['path']).write_bytes(b'x'*20)
            self.assertEqual(len(verify(root)['files']),5)  # accepted: found at install/inspect, not at start
            (root/files[0]['path']).write_bytes(b'x'*21)
            with self.assertRaisesRegex(ValueError,r'^WINDOWS_PACKAGE_FILE_MISMATCH: shared/ancestor/0\.bin$'):verify(root)
            (root/files[0]['path']).unlink()
            with self.assertRaisesRegex(ValueError,r'^WINDOWS_PACKAGE_FILE_MISMATCH: shared/ancestor/0\.bin$'):verify(root)

    def test_os_junk_is_ignored_and_unexpected_files_are_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);package(root,['data.bin'],prefix='﻿')  # PowerShell 5.1 style BOM
            for junk in ('desktop.ini','sub/Thumbs.db','.DS_Store'):
                (root/junk).parent.mkdir(exist_ok=True);(root/junk).write_bytes(b'junk')
            for full in (False,True):self.assertEqual(len(verify(root,full=full)['files']),1)
            (root/'sub/evil.py').write_bytes(b'x')
            for full in (False,True):
                with self.assertRaisesRegex(ValueError,r'^WINDOWS_PACKAGE_UNMANIFESTED_FILE: sub/evil\.py$'):verify(root,full=full)
            for i in range(6):(root/f'extra{i}.dll').write_bytes(b'x')
            with self.assertRaisesRegex(ValueError,r'^WINDOWS_PACKAGE_UNMANIFESTED_FILE: extra0\.dll, extra1\.dll, '
                    r'extra2\.dll, extra3\.dll, extra4\.dll \(\+2 more\)$'):verify(root)

    def test_listed_junk_named_file_is_still_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);package(root,['desktop/.DS_Store','data.bin'])
            self.assertEqual(len(verify(root)['files']),2)
            (root/'desktop/.DS_Store').unlink()
            with self.assertRaisesRegex(ValueError,r'^WINDOWS_PACKAGE_FILE_MISMATCH: desktop/\.DS_Store$'):verify(root)

    def test_unlisted_file_and_traversal_still_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'data.bin';path.write_bytes(b'data')
            files=[dict(path='data.bin',bytes=4,sha256=hashlib.sha256(b'data').hexdigest())]
            manifest=root/'windows-release-manifest.json'
            manifest.write_text(json.dumps(dict(schema='twinpulse-windows-exe-1.0',files=files)))
            extra=root/'unlisted.bin';extra.write_bytes(b'extra')
            with self.assertRaisesRegex(ValueError,'UNMANIFESTED_FILE: unlisted.bin'):verify(root)
            files[0]['path']='../data.bin';manifest.write_text(json.dumps(dict(schema='twinpulse-windows-exe-1.0',files=files)))
            for check in (verify,read_manifest):
                with self.assertRaisesRegex(ValueError,'PATH_INVALID'):check(root)
            manifest.write_text(json.dumps([files]))
            with self.assertRaisesRegex(ValueError,'^WINDOWS_MANIFEST_INVALID$'):read_manifest(root)

    def test_child_manifest_read_validates_structure_without_opening_listed_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);files=package(root,['_internal/a.bin','desktop/b.bin'])
            (root/files[0]['path']).unlink()
            self.assertEqual(read_manifest(root)['files'],files)
            with self.assertRaisesRegex(ValueError,r'^WINDOWS_PACKAGE_FILE_MISMATCH: _internal/a\.bin$'):verify(root)
            files.append(dict(files[1]));(root/'windows-release-manifest.json').write_text(json.dumps(
                dict(schema='twinpulse-windows-exe-1.0',files=files)))
            with self.assertRaisesRegex(ValueError,'PATH_INVALID'):read_manifest(root)


if __name__=='__main__':unittest.main()
