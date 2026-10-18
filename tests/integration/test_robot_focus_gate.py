"""Synthetic receipts test the gate only, never count as App acceptance."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import runpy
import tempfile
import unittest

module=runpy.run_path(str(Path(__file__).resolve().parents[2]/'scripts/verify_robot_focus_gate.py'))
validate=module['validate_records'];required=module['REQUIRED']

def fixture():
    rows={role:dict(status='PASS',project='p',phase={'fresh':'fresh','cold':'reopen','lineage':'run','lineage_cold':'cold'}[role],
        desktop=dict(engine=dict(release_id='release')),steps=[dict(name=n,status='PASS',evidence={}) for n in names]) for role,names in required.items()}
    for s in rows['fresh']['steps']:
        if s['name']=='Main chat bounded 90 degree command, measured completion':s['evidence']['delta']=math.pi/2
        if s['name']=='One session full turn with actual simulated scan':s['evidence']['delta']=2*math.pi
    rows['lineage']['requested_command']='left 90 degrees'
    rows.update(normal=dict(status='PASS_NORMAL_START_REUSE_DEBUG_OFF',release_id='release',source_sha256='source',launch_id='first',ready_wait_ms=40000,
        debug_listener_count=0,app_listener_count=1,repeated_start_same_owner=True),
        installation=dict(status='PASS',release_id='release',source_manifest_sha256='source',mismatches=[],capabilities=dict(physical_robot=True)),
        lifecycle=dict(status='PASS',release_id='release',source_sha256='source',normal_start_launch_id='first',shutdown_clean=True,
            restart_ready=True,restart_launch_id='second',restart_debug_listener_count=0,restart_app_listener_count=1,
            restart_authenticated_ready=True,restart_ready_wait_ms=45000),
        supplementary=dict(status='PASS',release_id='release',source_sha256='source',source_unchanged=True,
            groups=[dict(name=n,status='PASS') for n in ['lineage-and-pc','native-worker','field','ui','web-build']]),
        budget=dict(within_approved_total=True))
    return rows

class GateTests(unittest.TestCase):
    def test_complete_synthetic_fixture_only_tests_gate_logic(self):self.assertEqual(validate(fixture(),'release','source'),[])
    def test_missing_role_and_failed_whole_flow_rejected(self):
        r=fixture();r.pop('cold');r['fresh']['status']='FAIL'
        issues=validate(r,'release','source');self.assertIn('MISSING_ROLE:cold',issues);self.assertIn('RUN_NOT_PASS:fresh',issues)
    def test_old_release_and_split_resume_rejected(self):
        r=fixture();r['lineage']['phase']='resume-completed-motion';r['fresh']['desktop']['engine']['release_id']='old'
        issues=validate(r,'release','source');self.assertIn('WRONG_RELEASE:fresh',issues);self.assertIn('SPLIT_OR_WRONG_PHASE:lineage',issues)
    def test_observation_only_package_cannot_claim_powered_control_readiness(self):
        r=fixture();r['installation']['capabilities']['physical_robot']=False
        self.assertIn('INSTALLATION_NOT_EXACT',validate(r,'release','source'))
    def test_each_required_step_missing_is_rejected_even_when_overall_pass(self):
        for role,names in required.items():
            for name in names:
                with self.subTest(role=role,name=name):
                    r=fixture();r[role]['steps']=[s for s in r[role]['steps'] if s['name']!=name]
                    self.assertIn('MISSING_OR_FAILED_STEP:'+role+':'+name,validate(r,'release','source'))
    def test_old_source_supplementary_and_unclean_lifecycle_rejected(self):
        r=fixture();r['supplementary']['source_sha256']='old';r['lifecycle']['shutdown_clean']=False
        issues=validate(r,'release','source');self.assertIn('SUPPLEMENTARY_MISSING_OR_FAILED',issues)
        self.assertIn('NORMAL_LIFECYCLE_NOT_QUALIFIED',issues)
    def test_slow_restart_does_not_resolve_original_startup_failure(self):
        r=fixture();r['lifecycle']['restart_ready_wait_ms']=120210
        self.assertIn('NORMAL_LIFECYCLE_NOT_QUALIFIED',validate(r,'release','source'))
    def test_unexplained_get_failure_is_not_hidden_by_overall_pass(self):
        r=fixture();r['fresh']['request_failures']=[dict(method='GET',path='/v1/product/runtime',error='net::ERR_FAILED',exiting=False)]
        self.assertIn('UNCLASSIFIED_REQUEST_FAILURE:fresh',validate(r,'release','source'))
    def test_short_rotation_cannot_resolve_original_failure(self):
        r=fixture();r['lineage']['requested_command']='left 10 degrees'
        step=next(s for s in r['fresh']['steps'] if '90 degree command' in s['name']);step['evidence']['delta']=math.radians(10)
        self.assertTrue(any('ANGLE_NOT_PROVEN' in i for i in validate(r,'release','source')))
        self.assertIn('ORIGINAL_LINEAGE_90_NOT_RUN',validate(r,'release','source'))
    def test_timeout_and_budget_and_changed_input_rejected(self):
        r=fixture();r['normal']['ready_wait_ms']=120210;r['budget']['within_approved_total']=False;r['cold']['project']='other'
        issues=validate(r,'release','source');self.assertIn('NORMAL_START_NOT_QUALIFIED',issues);self.assertIn('BUDGET_UNCONFIRMED_OR_EXCEEDED',issues)
        self.assertIn('PROJECT_MISMATCH:fresh:cold',issues)
    def test_file_hash_and_duplicate_role_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=root/'evidence.json';p.write_text(json.dumps(dict(status='PASS')))
            m=dict(evidence=[dict(role='fresh',path=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest()),
                             dict(role='fresh',path=p.name,sha256='wrong'),dict(role='cold',path=p.name,sha256='wrong')])
            _,_,issues=module['load_evidence'](m,root)
            self.assertIn('INVALID_OR_DUPLICATE_REFERENCE:fresh',issues);self.assertIn('EVIDENCE_HASH_MISMATCH:cold',issues)
