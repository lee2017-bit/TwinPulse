# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Package gate boundary tests; actual isolated App acceptance is separate."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from scripts import verify_packaged_automatic_demo as verifier


class PackageGateTests(unittest.TestCase):
    def package(self,root):
        package=root/'artifacts/offline-release/reviewed';package.mkdir(parents=True)
        rows=[]
        for i in range(10):
            name=f'file{i}.py';data=b'pass\n';(package/name).write_bytes(data)
            rows.append({'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
        (package/'release-manifest.json').write_text(json.dumps({'schema':'twinpulse-offline-release-1.0',
            'release_id':'reviewed','dirty':True,'files':rows}),encoding='utf-8')
        scripts=root/'scripts';scripts.mkdir()
        for name in ('verify_packaged_automatic_demo.py','build_offline_release.ps1'):
            (scripts/name).write_text('test fixture only',encoding='utf-8')
        return package

    def test_package_hash_failure_is_saved_and_never_launches_child(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);package=self.package(root);(package/'file0.py').write_text('changed')
            with patch.object(verifier,'ROOT',root),patch.object(verifier.subprocess,'run') as run:
                output=root/'artifacts/failure';report=verifier.verify(package,output)
                self.assertEqual(report['status'],'FAILED');run.assert_not_called()
                self.assertEqual(report['reason'],'RELEASE_FILE_HASH_MISMATCH')
                self.assertEqual(json.loads((output/'verification.json').read_text())['reason'],report['reason'])
                self.assertFalse(report['offline_implementation_ready'])

    def test_owned_output_and_release_only(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);package=self.package(root)
            with patch.object(verifier,'ROOT',root):
                with self.assertRaisesRegex(ValueError,'OWNED_ARTIFACT_OUTPUT_REQUIRED'):
                    verifier.verify(package,root/'outside')
                with self.assertRaisesRegex(ValueError,'REVIEWED_LOCAL_RELEASE_REQUIRED'):
                    verifier.checked_package(root/'outside')

    def test_explicit_raw_input_missing_is_diagnosed_before_child(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);package=self.package(root)
            with patch.object(verifier,'ROOT',root),patch.object(verifier.subprocess,'run') as run:
                report=verifier.verify(package,root/'artifacts/missing',saved_scan_fixture=True)
                self.assertEqual(report['reason'],'SAVED_SCAN_TEST_INPUT_MISSING');run.assert_not_called()
                self.assertFalse(report['physical_demo_ready'])

    def test_raw_test_input_copied_byte_identically_and_kept_separate_from_release(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);folder=root/verifier.SAVED_SCAN_RELATIVE;folder.mkdir(parents=True)
            for name in verifier.SAVED_SCAN_FILES:(folder/name).write_bytes(b'original fixture bytes')
            with TemporaryDirectory() as isolated,patch.object(verifier,'ROOT',root):
                hashes=verifier.provide_saved_scan(Path(isolated))
                self.assertEqual(len(hashes),6)
                for name in hashes:self.assertEqual((Path(isolated)/name).read_bytes(),(root/name).read_bytes())

    def test_failure_counts_retained_and_no_automatic_retry_or_readiness_promotion(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);package=self.package(root)
            child={'passed':False,'failure_ids':['fixed.test_failure'],'error_ids':[],
                'tests_run':3,'device_runtime_imported':False}
            result=SimpleNamespace(returncode=2,stdout='PACKAGED_RESULT='+json.dumps(child))
            with patch.object(verifier,'ROOT',root),patch.object(verifier.subprocess,'run',return_value=result) as run:
                report=verifier.verify(package,root/'artifacts/failure')
                self.assertEqual(report['status'],'FAILED');self.assertEqual(run.call_count,1)
                self.assertEqual(report['child']['failure_ids'],child['failure_ids'])
                self.assertFalse(report['physical_demo_ready']);self.assertEqual(report['clean_install'],'NOT_RUN')
                self.assertIn('-I',run.call_args.args[0])
                self.assertFalse(Path(run.call_args.kwargs['cwd']).is_relative_to(root))
                import os
                isolated=Path(run.call_args.kwargs['cwd'])
                module_roots=run.call_args.kwargs['env']['PYTHONPATH'].split(os.pathsep)
                self.assertEqual(module_roots,[str(isolated)]+[str(isolated/'packages'/p/'src') for p in
                    ('twinpulse_core','twinpulse_app','twinpulse_provider')])
                self.assertTrue(all(Path(p).is_relative_to(isolated) for p in module_roots))
                self.assertTrue(report['isolated_copy_removed'])

    def test_runtime_case_failure_does_not_suppress_other_fixed_checks(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);isolated=root/'package';isolated.mkdir()
            output=root/'output';output.mkdir()
            playwright=root/'apps/twinpulse-web/node_modules/@playwright/test/index.mjs'
            playwright.parent.mkdir(parents=True);playwright.write_text('fixture')
            driver=isolated/'apps/twinpulse-web/e2e/packaged-mission-isaac.mjs'
            driver.parent.mkdir(parents=True);driver.write_text('fixture')
            runtime=root/'python.bat';runtime.write_text('fixture')
            called=[]
            def execute(command,*args,**kwargs):
                name=next(n for n in ('normal','storage','geometry','startup') if any(str(output/n)==str(v) for v in command))
                called.append(name)
                if name=='normal':raise OSError(5,'private text must not be copied')
                folder=output/name;folder.mkdir()
                (folder/('result.json' if name=='startup' else 'verification.json')).write_text(json.dumps({'status':'PASS'}))
                return {'returncode':0,'owned_tree':'FIXTURE_ONLY'}
            with patch.object(verifier,'ROOT',root),patch.object(verifier,'_run_owned_runtime',side_effect=execute):
                report=verifier.run_runtime_cases(isolated,output,runtime)
            self.assertEqual(called,['normal','storage','geometry','startup'])
            self.assertFalse(report['passed']);self.assertEqual(report['cases'][0]['error_type'],'OSError')
            self.assertNotIn('private text',json.dumps(report))

    def test_runtime_only_cannot_claim_app_core_pass(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);package=self.package(root)
            with patch.object(verifier,'ROOT',root),patch.object(verifier.subprocess,'run') as run, \
                    patch.object(verifier,'run_runtime_cases',return_value={'passed':True,'cases':[]}):
                report=verifier.verify(package,root/'artifacts/runtime-only',isaac_python=root/'python.bat',runtime_only=True)
            run.assert_not_called();self.assertEqual(report['status'],'PACKAGED_RUNTIME_ONLY_PASS')
            self.assertEqual(report['child']['status'],'NOT_RUN');self.assertEqual(report['child']['tests_run'],0)
            self.assertFalse(report['child']['passed']);self.assertFalse(report['offline_implementation_ready'])
            self.assertTrue(report['isolated_copy_removed']);self.assertTrue(report['driver_unchanged'])

    def test_runtime_only_requires_an_explicit_runtime_before_copying(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);package=self.package(root)
            with patch.object(verifier,'ROOT',root),patch.object(verifier.subprocess,'run') as run:
                report=verifier.verify(package,root/'artifacts/no-runtime',runtime_only=True)
            run.assert_not_called();self.assertEqual(report['status'],'FAILED')
            self.assertEqual(report['reason'],'RUNTIME_ONLY_REQUIRES_ISAAC')
            self.assertEqual(report['error_stage'],'RELEASE_MANIFEST');self.assertNotIn('child',report)

    def test_missing_runtime_driver_never_launches_a_child(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);runtime=root/'python.bat';runtime.write_text('fixture')
            playwright=root/'apps/twinpulse-web/node_modules/@playwright/test/index.mjs'
            playwright.parent.mkdir(parents=True);playwright.write_text('fixture')
            with patch.object(verifier,'ROOT',root),patch.object(verifier.subprocess,'run') as run:
                with self.assertRaisesRegex(ValueError,'PACKAGED_BROWSER_DRIVER_MISSING'):
                    verifier.run_runtime_cases(root/'isolated',root/'out',runtime)
                run.assert_not_called()


if __name__=='__main__':unittest.main()
