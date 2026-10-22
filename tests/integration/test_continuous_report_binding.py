# SPDX-License-Identifier: Apache-2.0
"""Report aggregation checks, not App/engine/physical acceptance."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('continuous_report',ROOT/'scripts/report_continuous_repair_20261021.py')
report=importlib.util.module_from_spec(spec);spec.loader.exec_module(report)

class BindingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name);self.current=dict(release_id='release',source_manifest_sha256='source')
        self.roles=dict(fresh='ui-19/result.json',cold='ui-cold-19/result.json',lineage='lineage-19/result.json',
            lineage_cold='lineage-cold-19/result.json',normal='normal19/result.json',installation='installed-files19.json',
            supplementary='supplementary19/result.json',budget='budget-final19.json',lifecycle='normal-lifecycle19.json')
        names=[*self.roles.values(),'normal19-restart/result.json','ui-reproduction-20/result.json',
            'cleanup-reproduction-20.json','normal19/shutdown.json','normal19-restart/shutdown.json',
            *(f'cleanup-{b}-19.json' for b in ('fresh','cold','lineage','history'))]
        for name in names:self.save(name,dict(status='PASS'))
        for name in ('normal19/result.json','normal19-restart/result.json'):
            self.save(name,dict(status='PASS_NORMAL_START_REUSE_DEBUG_OFF'))
        self.save('ui-reproduction-20/result.json',dict(status='PASS',desktop=dict(engine=dict(release_id='release',source_manifest_sha256='source'))))
        self.review=dict(status='SOFTWARE_NO_KNOWN_BLOCKER',unresolved=[],reproduction=self.ref('ui-reproduction-20/result.json'),evidence=[self.ref(n) for n in ('ui-reproduction-20/result.json','cleanup-reproduction-20.json')])
        self.save('physical-readiness-review19.json',self.review)
        self.gate=dict(release_id='release',source_sha256='source',physical_readiness_review=deepcopy(self.review),
            evidence=[dict(role=role,**self.ref(name)) for role,name in self.roles.items()])
    def save(self,name,value):
        p=self.folder/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value),encoding='utf-8')
    def ref(self,name):return dict(path=name,sha256=report.digest(self.folder/name))
    def issues(self):return report.final_binding_issues(self.folder,'19','20',self.current,self.gate)
    def test_exact_attempt(self):self.assertEqual(self.issues(),[])
    def test_explicit_later_snapshot_requires_its_own_exact_hash(self):
        self.save('budget-final19b.json',dict(status='PASS',new_http=5))
        entry=next(e for e in self.gate['evidence'] if e['role']=='budget')
        entry.update(self.ref('budget-final19b.json'))
        self.assertEqual(report.final_binding_issues(self.folder,'19','20',self.current,self.gate,'budget-final19b.json'),[])
        self.assertIn('FINAL_GATE_ATTEMPT_BINDING:budget',self.issues())
        self.save('budget-final19b.json',dict(status='PASS',new_http=6))
        self.assertIn('FINAL_GATE_ATTEMPT_BINDING:budget',report.final_binding_issues(self.folder,'19','20',self.current,self.gate,'budget-final19b.json'))
    def test_other_attempt_and_paths_are_not_budget_selectors(self):
        for name in ('budget-final18b.json','../budget-final19b.json','budget-before19.json'):
            with self.subTest(name=name),self.assertRaises(ValueError):report.selected_budget_name('19',name)
    def test_same_release_other_attempt_is_rejected(self):
        self.gate['evidence'][0]['path']='ui-12/result.json'
        self.assertIn('FINAL_GATE_ATTEMPT_BINDING:fresh',self.issues())
    def test_missing_current_journey_vetoes(self):
        (self.folder/'lineage-19/result.json').unlink()
        self.assertIn('FINAL_REQUIRED_NOT_PASS:lineage-19/result.json',self.issues())
    def test_current_failure_vetoes_even_if_gate_reference_rehashed(self):
        self.save('ui-19/result.json',dict(status='FAIL'))
        self.gate['evidence'][0].update(self.ref('ui-19/result.json'))
        self.assertIn('FINAL_REQUIRED_NOT_PASS:ui-19/result.json',self.issues())
    def test_reproduction_not_current(self):
        self.save('ui-reproduction-20/result.json',dict(status='PASS',release_id='old',source_sha256='source'))
        self.assertIn('FINAL_REPRODUCTION_WRONG_RELEASE',self.issues())
    def test_review_reproduction_binding(self):
        self.review['evidence']=[];self.save('physical-readiness-review19.json',self.review)
        self.gate['physical_readiness_review']=deepcopy(self.review)
        self.assertIn('FINAL_REPRODUCTION_NOT_BOUND:ui-reproduction-20/result.json',self.issues())
    def test_other_same_release_reproduction_shutdown_cannot_be_borrowed(self):
        self.save('ui-reproduction-22/result.json',dict(status='PASS',desktop=dict(engine=dict(release_id='release',launch_id='other'))))
        self.review['reproduction']=self.ref('ui-reproduction-22/result.json')
        self.save('physical-readiness-review19.json',self.review)
        self.gate['physical_readiness_review']=deepcopy(self.review)
        self.assertIn('FINAL_REPRODUCTION_SHUTDOWN_SELECTION_MISMATCH',self.issues())
    def test_failed_normal_vetoes(self):
        self.save('normal19-restart/result.json',dict(status='FAIL'))
        self.assertIn('FINAL_NORMAL_NOT_PASS:normal19-restart/result.json',self.issues())

if __name__=='__main__':unittest.main()
