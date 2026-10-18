# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import verify_ad2_automatic_mapping as batch
import run_demo_preflight as preflight


class Worker:
    def join(self,timeout):pass
    def is_alive(self):return False


class FakeService:
    started=[]
    def __init__(self,root,project):self.worker=Worker();self.job=None
    def start(self,owner,job,*args):
        self.started.append(job)
        self.job={'state':'FAILED','error':'BROKEN_FIRST_RECORD','error_stage':'OPEN_RAW'} if job==batch.JOBS[0] else {
            'state':'COMPLETED','map_id':'a'*32,'result':{'motion_authorized':False,'alignment_verified':False,
                'counts':{},'reasons':{},'state':'UNVERIFIED','source_status':'FAILED','source_reason':'PRESERVED_FAILURE',
                'keyframe_count':0,'corrected_cells':[],'odom_cells':[],'loop_status':'NOT_RUN',
                'reference_eligible':False,'cache_builds':0,'transitions':[]}}
    def snapshot(self,owner):return {'job':self.job}
    def reopen(self,*args):return {'pose_candidate':None,'motion_authorized':False}
    def close(self):pass


class DemoBatchTests(unittest.TestCase):
    def test_one_failure_does_not_hide_other_shared_sessions(self):
        FakeService.started=[]
        with patch.object(batch,'hashes',return_value={'raw':'f'*64}):
            value=batch.run_batch(ROOT,service_factory=FakeService)
        self.assertEqual(FakeService.started,list(batch.JOBS))
        self.assertEqual([r['status'] for r in value['sessions']],['FAIL','PASS','PASS'])
        self.assertEqual(value['status'],'FAIL')
        self.assertEqual(value['first_failure']['error_stage'],'OPEN_RAW')
        self.assertTrue(all(r['originals_unchanged'] for r in value['sessions']))
        self.assertFalse(value['SAVED_REAL_ALIGNMENT_SUPPORTED'])

    def test_raw_mutation_cannot_be_pipeline_pass(self):
        with patch.object(batch,'hashes',side_effect=[{'raw':'before'},{'raw':'after'}]):
            value=batch.run_batch(ROOT,jobs=(batch.JOBS[1],),service_factory=FakeService)
        self.assertEqual(value['status'],'FAIL')
        self.assertEqual(value['sessions'][0]['integrity_error'],'ORIGINAL_CHANGED')

    def test_unknown_session_and_changed_matrix_rejected_before_any_execution(self):
        with self.assertRaisesRegex(ValueError,'ALLOWLIST'):batch.run_batch(ROOT,jobs=('f'*32,))
        with patch.dict(preflight.CASES,{'unreviewed':('some.module',)}):
            with self.assertRaisesRegex(ValueError,'MATRIX_MISMATCH'):preflight.run(ROOT)

    def test_single_report_continues_after_failed_mapping_and_contract(self):
        called=[]
        def execute(root,out,name,modules):
            called.append(name);return {'status':'FAIL' if name=='revision_ack' else 'PASS'}
        def mapping(*args,**kwargs):raise ValueError('ORIGINAL_REJECTED')
        with TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'packages').mkdir()
            with patch('run_robot_field_suite.inspect_saved',return_value=[{'status':'FAILED'}]):
                value,out=preflight.run(root,admission_audit=lambda root:{'status':'NOT_READY_BEFORE_ROBOT_CONNECTION'},
                    execute=execute,mapping=mapping)
            saved=json.loads((out/'report.json').read_text())
            self.assertEqual(called,list(preflight.CASES))
            self.assertTrue(saved['checks_completed']);self.assertEqual(saved['status'],'NEEDS_ATTENTION')
            self.assertEqual(saved['stages']['recorded_mapping_photo']['reason'],'ORIGINAL_REJECTED')
            self.assertEqual(saved['stages']['physical_mission']['status'],'SKIPPED_DEPENDENCY')
            self.assertEqual(saved['stages']['physical_mission']['blocked_by'],['recorded_mapping_photo'])
            self.assertFalse(saved['physical_demo_ready']);self.assertFalse(saved['motion_authorized'])

    def test_arbitrary_exception_text_does_not_leak_into_report(self):
        row=batch.failure(ValueError('secret=abc /private/path'),'SAFE_STAGE')
        self.assertEqual(row['reason'],'VERIFIER_EXCEPTION_REDACTED');self.assertNotIn('abc',str(row))

    def test_offline_mode_cannot_be_combined_with_field_or_another_room(self):
        import contextlib
        import io
        import run_robot_field_suite as field
        for flags in (['--demo-preflight','--field-run'],['--demo-preflight','--adaptive-preflight'],
                      ['--demo-preflight','--project-id','other']):
            with self.subTest(flags=flags),patch.object(sys,'argv',['run_robot_field_suite.py',*flags]),\
                 contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit) as exc:
                field.main()
            self.assertEqual(exc.exception.code,2)
