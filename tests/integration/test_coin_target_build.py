# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""No transport/device execution during local build-source regression."""
import ast
import json
import io
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import build_coin_target as build


class TargetBuildSourceTests(unittest.TestCase):
    def archive(self, path, members):
        with tarfile.open(path,'w') as archive:
            for name,data in members:
                info=tarfile.TarInfo(name); info.size=len(data)
                archive.addfile(info,io.BytesIO(data))

    def expected(self,members):
        return {'status':'CORRECTED_DRIVER_SOURCE_FROZEN_NOT_BUILT','members':len(members),
                'source_sha256':build.sha(__import__('json').dumps(
                    {k:build.sha(v) for k,v in members},sort_keys=True).encode())}

    def test_valid_exact_archive(self):
        members=[('CMakeLists.txt',b'reviewed'),('include/header.hpp',b'contract')]
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'source.tar'; self.archive(path,members)
            with patch.object(build,'sensor_target',return_value=self.expected(members)):
                digest,result=build.reviewed_archive(path)
            self.assertEqual(digest,build.sha(path.read_bytes()))

    def test_changed_archive_rejected(self):
        members=[('CMakeLists.txt',b'reviewed')]
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'source.tar'; self.archive(path,[('CMakeLists.txt',b'changed')])
            with patch.object(build,'sensor_target',return_value=self.expected(members)):
                with self.assertRaisesRegex(ValueError,'FROZEN_SENSOR_ARCHIVE_CHANGED'):build.reviewed_archive(path)

    def test_duplicate_rejected(self):
        members=[('a',b'a'),('a',b'b')]
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'source.tar'; self.archive(path,members)
            with patch.object(build,'sensor_target',return_value=self.expected(members)):
                with self.assertRaisesRegex(ValueError,'FROZEN_ARCHIVE_MEMBERS'):build.reviewed_archive(path)

    def test_directory_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'source.tar'
            with tarfile.open(path,'w') as archive:
                item=tarfile.TarInfo('dir'); item.type=tarfile.DIRTYPE; archive.addfile(item)
            with patch.object(build,'sensor_target',return_value=self.expected([('dir',b'')])):
                with self.assertRaisesRegex(ValueError,'FROZEN_ARCHIVE_MEMBERS'):build.reviewed_archive(path)

    def test_default_is_no_contact(self):
        with patch.object(sys,'argv',['build_coin_target','--archive','unused']), \
                patch.object(build,'reviewed_archive',return_value=('digest',{})), \
                patch.object(build.subprocess,'run') as transport:
            self.assertEqual(build.main(),0)
            transport.assert_not_called()

    def test_remote_worker_syntax(self):
        ast.parse(build.REMOTE)

    def test_missing_review_rejected(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(build,'sensor_target',return_value={'status':'CORRECTED_DRIVER_SOURCE_MISSING'}):
            path=Path(directory)/'source.tar'; path.write_bytes(b'')
            with self.assertRaisesRegex(ValueError,'CORRECTED_SOURCE_NOT_AVAILABLE'):build.reviewed_archive(path)

    def exported(self,directory):
        directory=Path(directory); (directory/'build').mkdir()
        (directory/'source').mkdir(); (directory/'source/main.cpp').write_bytes(b'source')
        (directory/'sensor-target.tar').write_bytes(b'archive')
        artifacts={}
        for name in ('single_coin_d4_node','multi_coin_d4_node','libcoin_d4_driver_lib.so'):
            (directory/'build'/name).write_bytes(name.encode())
            artifacts[name]={'sha256':build.sha(name.encode())}
        report={'status':'TARGET_BUILD_PASS_NOT_ACTIVATED','architecture':'aarch64',
                'existing_state_unchanged':True,'before':{'current':'old'},'after':{'current':'old'},
                'archive_sha256':build.sha(b'archive'),'artifacts':artifacts,
                'source_files':{'main.cpp':build.sha(b'source')},
                'sensor_started':False,'motor_command_sent':False,'release_selected':False}
        (directory/'report.json').write_text(json.dumps(report)); return directory,report

    def test_export_exact_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path,report=self.exported(directory)
            self.assertEqual(build.verify_export(path,build.sha(b'archive')),report)

    def test_export_missing_or_changed_binary_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path,_=self.exported(directory); (path/'build/single_coin_d4_node').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'EXPORTED_BINARY_SHA_MISMATCH'):build.verify_export(path,build.sha(b'archive'))

    def test_preservation_or_source_change_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path,report=self.exported(directory); report['after']={'current':'changed'}
            (path/'report.json').write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError,'PRESERVATION'):build.verify_export(path,build.sha(b'archive'))
            report['after']=report['before']; (path/'report.json').write_text(json.dumps(report))
            (path/'source/main.cpp').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'EXPORTED_SOURCE_SHA_MISMATCH'):build.verify_export(path,build.sha(b'archive'))

    def test_remote_failure_reason_preserved_without_success_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory); report={'status':'TARGET_BUILD_FAILED','reason':'compile: member to_msg missing'}
            (path/'report.json').write_text(json.dumps(report))
            self.assertEqual(build.verify_export(path,'expected'),report)

    def test_receipt_requires_pass_and_is_only_under_owned_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); output=root/'artifacts/coin-target-build/run'
            output.mkdir(parents=True); target=output/'target'; target.mkdir()
            self.exported(target)
            with patch.object(build,'reviewed_archive',return_value=(build.sha(b'archive'),{'source_sha256':'source'})):
                value=build.record_verified_build(root,output)
                self.assertFalse(value['activation_authorized'])
                self.assertEqual(value['target'],'artifacts/coin-target-build/run/target')
                report={'status':'TARGET_BUILD_FAILED','reason':'compile failure'}
                (target/'report.json').write_text(json.dumps(report))
                with self.assertRaisesRegex(ValueError,'REQUIRES_ACTUAL_PASS'):build.record_verified_build(root,output)
            with self.assertRaisesRegex(ValueError,'BUILD_RECEIPT_ROOT'):build.record_verified_build(root,root)


if __name__=='__main__':unittest.main()
