# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""The build refuses to start without a fresh Verify-Sprint PASS for the exact committed tree (P0-8)."""
from datetime import datetime,timedelta,timezone
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import build_windows_exe as build
import verify_sprint as gate


def git(root,*args):
    return subprocess.run(['git','-C',str(root),*args],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,check=True,text=True).stdout.strip()


class SprintGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        git(self.root,'init','-q');git(self.root,'config','user.email','t@example.invalid');git(self.root,'config','user.name','t')
        (self.root/'tracked.txt').write_text('a');git(self.root,'add','tracked.txt');git(self.root,'commit','-q','-m','one')
        self.head=git(self.root,'rev-parse','HEAD')

    def receipt(self,**changes):
        value=dict(schema='twinpulse-sprint-gate-1.0',run_id='r1',head=self.head,dirty=False,
            finished_utc=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),status='PASS',steps=[])
        value.update(changes)
        path=self.root/'outputs/verify-sprint/latest.json';path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text('\ufeff'+json.dumps(value),encoding='utf-8')  # PowerShell UTF8 writes a BOM
        return value

    def test_missing_failed_stale_or_dirty_receipts_refuse_the_build(self):
        with self.assertRaisesRegex(ValueError,'^SPRINT_GATE_RECEIPT_MISSING'):build.sprint_gate_receipt(self.root)
        self.receipt(status='FAIL')
        with self.assertRaisesRegex(ValueError,'^SPRINT_GATE_FAILED'):build.sprint_gate_receipt(self.root)
        self.receipt(head='0'*40)
        with self.assertRaisesRegex(ValueError,'^SPRINT_GATE_STALE_COMMIT'):build.sprint_gate_receipt(self.root)
        self.receipt(dirty=True)
        with self.assertRaisesRegex(ValueError,'^SPRINT_GATE_DIRTY_TREE'):build.sprint_gate_receipt(self.root)
        # A full gate run takes about an hour and the robot evening may start long after it: 24 h is fresh enough.
        self.receipt(finished_utc=(datetime.now(timezone.utc)-timedelta(hours=3)).strftime('%Y-%m-%dT%H:%M:%SZ'))
        self.assertEqual(build.sprint_gate_receipt(self.root)['status'],'PASS')
        old=(datetime.now(timezone.utc)-timedelta(hours=25)).strftime('%Y-%m-%dT%H:%M:%SZ')
        self.receipt(finished_utc=old)
        with self.assertRaisesRegex(ValueError,'^SPRINT_GATE_STALE_TIME'):build.sprint_gate_receipt(self.root)
        self.receipt()
        (self.root/'tracked.txt').write_text('edited after the gate')
        with self.assertRaisesRegex(ValueError,'^SPRINT_GATE_DIRTY_TREE'):build.sprint_gate_receipt(self.root)

    def test_fresh_pass_on_the_committed_head_is_accepted_and_untracked_files_do_not_matter(self):
        expected=self.receipt()
        (self.root/'scratch.txt').write_text('untracked')  # e.g. outputs/ or a local note
        self.assertEqual(build.sprint_gate_receipt(self.root)['run_id'],expected['run_id'])
        self.assertEqual(build.sprint_gate_receipt(self.root,max_age_s=60)['status'],'PASS')

    def test_full_gate_run_refuses_a_dirty_tree_at_once_naming_the_files_but_partial_runs_proceed(self):
        row=dict(name='compileall',argv=['py','-c','pass'],required=True)
        done=dict(name='compileall',required=True,exit_code=0,seconds=0.1,failures=[],text='')
        (self.root/'tracked.txt').write_text('edited');(self.root/'scratch.txt').write_text('untracked only')
        with patch.object(gate,'ROOT',self.root),patch.object(gate,'steps',return_value=[row]),patch.object(gate,'run_step',return_value=done) as run, \
                patch('sys.stdout',new_callable=io.StringIO):
            with self.assertRaises(SystemExit) as stop:gate.main([])
            self.assertRegex(str(stop.exception),r'^SPRINT_GATE_DIRTY_TREE(?s:.*)\n ?M tracked\.txt');self.assertNotIn('scratch.txt',str(stop.exception))
            run.assert_not_called();self.assertFalse((self.root/'outputs/verify-sprint').exists())
            # A partial run is a developer loop, not a build receipt: it runs, records dirty=True and never writes latest.json.
            self.assertEqual(gate.main(['--steps','compileall']),1)  # exit 1: a PARTIAL receipt is never a PASS (unchanged)
            run.assert_called_once()
            receipt=json.loads(next((self.root/'outputs/verify-sprint').glob('*/receipt.json')).read_text(encoding='utf-8-sig'))
            self.assertEqual((receipt['dirty'],receipt['status'],receipt['partial']),(True,'PARTIAL',True))
            self.assertFalse((self.root/'outputs/verify-sprint/latest.json').exists())
            # Clean tree (untracked file still present): the full run proceeds and writes a receipt for the build.
            git(self.root,'checkout','--','tracked.txt');run.reset_mock()
            self.assertEqual(gate.main([]),0);run.assert_called_once()
            self.assertEqual(json.loads((self.root/'outputs/verify-sprint/latest.json').read_text(encoding='utf-8-sig'))['status'],'PASS')

    def test_after_build_phase_writes_its_own_receipt_and_never_the_build_receipt(self):
        row=dict(name='integration',argv=['py','-c','pass'],required=False)
        done=dict(name='integration',required=False,exit_code=1,seconds=0.1,failures=['tests.integration.test_old.T.test_x'],text='')
        (self.root/'scratch.txt').write_text('untracked only')
        with patch.object(gate,'ROOT',self.root),patch.object(gate,'steps',return_value=[row]) as steps,patch.object(gate,'run_step',return_value=done), \
                patch('sys.stdout',new_callable=io.StringIO):
            # No baseline yet: the old failure counts as new, the after-build receipt says FAIL, and latest.json stays absent.
            self.assertEqual(gate.main(['--after-build']),1)
            self.assertEqual(steps.call_args.kwargs['phase'],'after_build')
            after=json.loads((self.root/'outputs/verify-sprint/after-build-latest.json').read_text(encoding='utf-8-sig'))
            self.assertEqual((after['phase'],after['status'],after['new_failures']),('after_build','FAIL',{'integration':['tests.integration.test_old.T.test_x']}))
            self.assertFalse((self.root/'outputs/verify-sprint/latest.json').exists())
            # Grandfathering is an explicit operator decision and only an after-build run can record it.
            with self.assertRaises(SystemExit):gate.main(['--set-baseline'])
            self.assertEqual(gate.main(['--after-build','--set-baseline']),0)
            self.assertEqual(gate.load_baseline(self.root/'outputs/verify-sprint/baseline.json')['failures'],{'integration':['tests.integration.test_old.T.test_x']})
            # A dirty tree does not refuse the after-build run (it blocks nothing), while the build phase still refuses it.
            (self.root/'tracked.txt').write_text('edited')
            self.assertEqual(gate.main(['--after-build']),0)
            with self.assertRaises(SystemExit):gate.main([])
        # The build phase writes latest.json with phase 'build' and names the functional pass as post-install acceptance.
        git(self.root,'checkout','--','tracked.txt')
        brow=dict(name='compileall',argv=['py','-c','pass'],required=True);bdone=dict(name='compileall',required=True,exit_code=0,seconds=0.1,failures=[],text='')
        with patch.object(gate,'ROOT',self.root),patch.object(gate,'steps',return_value=[brow]),patch.object(gate,'run_step',return_value=bdone), \
                patch('sys.stdout',new_callable=io.StringIO):
            self.assertEqual(gate.main([]),0)
        latest=json.loads((self.root/'outputs/verify-sprint/latest.json').read_text(encoding='utf-8-sig'))
        self.assertEqual((latest['phase'],latest['status'],latest['functional_pass']),('build','PASS','post_install_acceptance'))
        self.assertEqual(build.sprint_gate_receipt(self.root)['run_id'],latest['run_id'])

    def test_build_main_checks_the_gate_before_tool_versions_unless_skipped(self):
        out=self.root/'never-created'
        with patch.object(build,'ROOT',self.root), patch.object(sys,'argv',['build','--output-dir',str(out)]):
            with self.assertRaisesRegex(ValueError,'^SPRINT_GATE_RECEIPT_MISSING'):build.main()
        self.assertFalse(out.exists())
        with patch.object(build,'ROOT',self.root), patch.object(sys,'argv',['build','--output-dir',str(out),'--skip-sprint-gate']), \
                patch.object(build,'version',return_value='0.0'):
            with self.assertRaisesRegex(ValueError,'^BUILD_TOOL_VERSION_MISMATCH$'):build.main()


class VerifySprintEvaluationTests(unittest.TestCase):
    REPORT=("..F.E\n======================================================================\n"
            "FAIL: test_a (test_mod.Case.test_a)\n----\nAssertionError: 1 != 2\n\n"
            "ERROR: test_b (test_mod.Case.test_b) (target='x.y')\n----\nKeyError: 'k'\n\n"
            "ERROR: test_loader (unittest.loader._FailedTest.test_loader)\n----\nImportError\n\n"
            "FAIL: test_a (test_mod.Case.test_a) [sub=1]\n----\n\nRan 5 tests\n\nFAILED (failures=2, errors=2)\n")

    def test_failure_ids_are_parsed_from_unittest_text_including_subtests_and_loader_errors(self):
        self.assertEqual(gate.parse_failures(self.REPORT),
            ['test_mod.Case.test_a','test_mod.Case.test_b','unittest.loader._FailedTest.test_loader'])
        self.assertEqual(gate.parse_failures('....\nOK\n'),[])

    def test_required_steps_need_exit_zero_and_other_steps_allow_only_baseline_failures(self):
        results=[dict(name='robot_safety_test_prefix',required=True,exit_code=0,failures=[]),
                 dict(name='integration_robot_path',required=True,exit_code=1,failures=['tests.integration.test_physical_live_session.T.test_x']),
                 dict(name='provider',required=False,exit_code=1,failures=['p.T.old','p.T.new']),
                 dict(name='core',required=False,exit_code=1,failures=[]),
                 dict(name='integration',required=False,exit_code=1,failures=['i.T.old'])]
        baseline={'provider':['p.T.old','p.T.fixed'],'integration':['i.T.old']}
        verdict=gate.evaluate(results,baseline)
        self.assertEqual(verdict['status'],'FAIL')
        self.assertEqual(verdict['verdicts'],dict(robot_safety_test_prefix='PASS',integration_robot_path='FAIL',provider='FAIL',core='FAIL',integration='PASS'))
        self.assertEqual(verdict['new_failures'],dict(integration_robot_path=['tests.integration.test_physical_live_session.T.test_x'],
                                                      provider=['p.T.new'],core=['<exit 1>']))
        self.assertEqual(verdict['baseline_failures'],dict(provider=['p.T.old'],integration=['i.T.old']))
        self.assertEqual(verdict['fixed_since_baseline'],dict(provider=['p.T.fixed']))
        results[1].update(exit_code=0,failures=[]);results[2]['failures']=['p.T.old'];results[3]['exit_code']=0
        self.assertEqual(gate.evaluate(results,baseline)['status'],'PASS')
        # Without any baseline every failure outside the required steps is new.
        self.assertEqual(gate.evaluate(results,None)['new_failures'],dict(provider=['p.T.old'],integration=['i.T.old']))
        # A required step is never excused by a baseline entry.
        results[1].update(exit_code=1,failures=['tests.integration.test_robot_health.T.test_y'])
        self.assertEqual(gate.evaluate(results,{'integration_robot_path':['tests.integration.test_robot_health.T.test_y']})['status'],'FAIL')

    def test_required_integration_modules_cover_the_robot_path_and_the_gate_itself(self):
        modules=gate.required_integration_modules(ROOT)
        for name in ('test_physical_live_session','test_physical_fleet_adapter','test_robot_health','test_robot_fleet',
                     'test_live_bootstrap_roundtrip','test_build_sprint_gate','test_license_policy','test_fleet_diagnostics'):
            self.assertIn('tests.integration.'+name,modules)
        self.assertNotIn('tests.integration.test_a2_project_catalog',modules)
        # 2026-10-27 (user decision): before a build only the required suites run (about 10 min); core, provider and
        # the full integration discover are the --after-build phase, compared with the baseline and never blocking.
        rows=gate.steps(ROOT,'py',skip_web=True)
        self.assertEqual([r['name'] for r in rows],['compileall','robot_safety_test_prefix','robot_safety_test_suffix',
                                                    'integration_robot_path','integration_regression'])
        self.assertTrue(all(r['required'] for r in rows))
        self.assertEqual(rows[3]['argv'][:4],['py','-B','-m','unittest']);self.assertEqual(rows[3]['argv'][4:],modules)
        regression=gate.regression_integration_modules(ROOT)
        self.assertEqual(rows[4]['argv'][4:],regression)
        for name in ('test_declared_route','test_environment_photo','test_h2b2_site_review','test_r3_application'):
            self.assertIn('tests.integration.'+name,regression)
        self.assertEqual(gate.steps(ROOT,'py')[5]['name'],'web')
        after=gate.steps(ROOT,'py',phase='after_build')
        self.assertEqual([r['name'] for r in after],['core','provider','integration']);self.assertFalse(any(r['required'] for r in after))
        with self.assertRaises(ValueError):gate.steps(ROOT,'py',phase='other')
        self.assertEqual(gate.FUNCTIONAL_PASS,'post_install_acceptance')  # the scripted App pass stays a recorded post-install step

    def test_baseline_file_round_trip_and_schema_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'baseline.json'
            self.assertIsNone(gate.load_baseline(path))
            gate.write_json(path,dict(schema=gate.BASELINE_SCHEMA,run_id='r',head='h',failures={'core':['c.T.x']}))
            self.assertEqual(gate.load_baseline(path)['failures'],{'core':['c.T.x']})
            path.write_text('\ufeff'+json.dumps(dict(schema='other')),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'SPRINT_BASELINE_SCHEMA'):gate.load_baseline(path)


if __name__=='__main__':unittest.main()
