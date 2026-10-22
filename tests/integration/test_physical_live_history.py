# SPDX-License-Identifier: Apache-2.0
"""Supplementary cold evidence tests; no transport or device activation."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import base64
from unittest.mock import patch
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[2]
for p in ('twinpulse_app','twinpulse_core','twinpulse_provider'):sys.path.insert(0,str(ROOT/'packages'/p/'src'))
from twinpulse_app.physical_live_history import recover_live_history,checked_worker_sources

class HistoryTests(unittest.TestCase):
    def test_complete_current_bootstrap_manifest_survives_cold_reader(self):
        from twinpulse_app.physical_live_session import reviewed_bundle
        sha,_,files=reviewed_bundle(ROOT)
        self.assertGreater(len(files),60)
        self.assertIn('guard_base/CMakeLists.txt',files)
        self.assertEqual(checked_worker_sources(files,sha),files)
        for name in ('../bad.py','guard_base/../../bad.cpp','guard_base/src/unsafe.py',
                     'guard_base/bin/tool.exe','tests/unreviewed.cpp','/absolute.cpp'):
            altered={**files,name:'a'*64}
            digest=hashlib.sha256(json.dumps(altered,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'WORKER_SOURCES_MEMBER'):
                checked_worker_sources(altered,digest)

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)
        self.files={'fleet_worker.py':'a'*64,'twinpulse_core/__init__.py':'b'*64}
        self.sha=hashlib.sha256(json.dumps(self.files,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        self.identity=dict(operation_id='a'*32,project_id='project-a',robot_id='b'*32,connection_epoch='c'*32,
                           binding_sha256='d'*64,source_twin_context={'context_id':'e'*64})
        self.first=dict(schema='physical-live-pc-start-2.0',**self.identity,worker_sha256=self.sha,worker_sources=self.files)
        self.events=[self.first]
        for i in range(1,131):
            self.events.append(dict(schema='physical-live-event-2.0',**{k:v for k,v in self.identity.items() if k not in {'binding_sha256','source_twin_context'}},
                source_twin_context_id='e'*64,sequence=i,robot_monotonic_s=i/10,kind='heartbeat',
                data=dict(worker_sha256=self.sha,challenge='NO_AUTHORITY_FROM_HISTORY',watch_challenge='SECRET')))
        self.events[-1].update(kind='cleanup',data=dict(subsystem='session',confirmed=True))
    def receipt(self):
        raw=b''.join((json.dumps(e)+'\n').encode() for e in self.events);(self.path/'events-00000.jsonl').write_bytes(raw)
        return dict(event_count=len(self.events),bytes=len(raw),segments=[dict(path='events-00000.jsonl',bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())])
    def recover(self):return recover_live_history(self.path,self.receipt(),**self.identity)
    def test_bounded_tail_sources_cleanup_without_authority(self):
        result=self.recover();self.assertEqual(len(result['events']),100);self.assertTrue(result['cleanup_confirmed'])
        self.assertEqual(result['worker_sources'],self.files);self.assertEqual(result['runtime_event_count'],131)
        self.assertNotIn('challenge',result['events'][0]['data']);self.assertNotIn('watch_challenge',result['events'][0]['data'])
        self.assertNotIn('device_authority_restored',result)

    def test_only_retained_tail_is_deepcopied_after_all_rows_are_verified(self):
        import twinpulse_app.physical_live_history as history
        with patch.object(history, 'deepcopy', wraps=history.deepcopy) as copied:
            result = self.recover()
        # One source manifest and exactly the final100 events, not every
        # candidate that the bounded tail eventually discards.
        self.assertEqual(copied.call_count, 101)
        self.assertEqual(len(result['events']), 100)
        self.assertEqual(result['events'][0]['sequence'], 31)

    def test_retained_copy_redaction_does_not_change_cleanup_projection(self):
        self.events[-1]['data']['challenge'] = 'ORIGINAL_CLEANUP_VALUE'
        result = self.recover()
        self.assertNotIn('challenge', result['events'][-1]['data'])
        self.assertEqual(result['cleanup']['challenge'], 'ORIGINAL_CLEANUP_VALUE')
        result['events'][-1]['data']['confirmed'] = False
        self.assertTrue(result['cleanup']['confirmed'])

    def test_discarded_tail_candidates_are_still_fully_checked(self):
        # This row is older than the returned100; changing the receipt hashes
        # cannot turn a sequence/context/worker violation into valid history.
        for key, value in [('sequence', 99), ('source_twin_context_id', 'f'*64)]:
            prior = self.events[1][key]
            self.events[1][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.recover()
            self.events[1][key] = prior
        self.events[1]['data']['worker_sha256'] = 'f'*64
        with self.assertRaisesRegex(ValueError, 'WORKER_CHANGED'):
            self.recover()

    def test_actual_writer_ledger_is_resolved_through_product_cold_history(self):
        sys.path.insert(0,str(ROOT/'packages/twinpulse_robot_safety'))
        from fleet_control import RobotControl
        directory=self.path/'writer';directory.mkdir()
        context={k:v for k,v in self.identity.items() if k not in {'binding_sha256','source_twin_context'}}
        owner=RobotControl(context,directory,lambda *_:None,SimpleNamespace(),clock=lambda:1.)
        owner.field_trial=dict(trial_id='actual-local-writer',case='stationary',status='RUNNING',frames=80)
        owner._finish_field('PASS','ZERO_MOTION_NATIVE_COLLECTION');closed=owner.field_writer.close()
        def event(kind,data):
            value=dict(self.events[-1],sequence=self.events[-1]['sequence']+1,kind=kind,data=data)
            self.events.append(value)
        members=[]
        for name in ('field-trials.json','field-commits.jsonl'):
            raw=(directory/name).read_bytes();sha=hashlib.sha256(raw).hexdigest()
            event('raw_source',dict(kind='chunk',member=name,offset=0,length=len(raw),sha256=sha,base64=base64.b64encode(raw).decode()))
            members.append(dict(member=name,source_complete=True,source_sha256=sha))
        event('raw_source',dict(kind='manifest',members=members))
        event('cleanup',dict(subsystem='session',confirmed=True,control=dict(field_evidence=closed)))
        recovered=self.recover()['field_trial_resolution']
        self.assertEqual(recovered['status'],'VERIFIED_READ_ONLY');self.assertFalse(recovered['authority_restored'])
        self.assertEqual(recovered['trials'][0]['status'],'PASS')
        self.events[-1]['data']['control']['field_evidence']['writer_id']='0'*32
        self.assertEqual(self.recover()['field_trial_resolution']['trials'][0]['status'],'INCONCLUSIVE')
    def test_legacy_missing_sources_remains_unknown(self):
        del self.first['worker_sources'];result=self.recover();self.assertIsNone(result['worker_sources'])
        self.assertEqual(result['worker_sources_provenance'],'NOT_RECORDED')

    def test_actual_failed_build_diagnostic_survives_export_and_cold_read_without_authority(self):
        sys.path.insert(0,str(ROOT/'packages/twinpulse_robot_safety'))
        import guard_runtime
        from fleet_control import RobotControl
        from fleet_worker import export_sources
        self.events=self.events[:1]
        def emit(kind,data):
            self.events.append(dict(schema='physical-live-event-2.0',
                **{k:self.identity[k] for k in ('operation_id','robot_id','project_id','connection_epoch')},
                source_twin_context_id='e'*64,sequence=len(self.events),robot_monotonic_s=1.,kind=kind,data=data))
        directory=self.path/'diagnostic';directory.mkdir()
        context=dict(self.identity,worker_sha256=self.sha)
        owner=RobotControl(context,directory,emit,SimpleNamespace(),clock=lambda:1.)
        def missing(command,log,env):
            log.write_bytes(b'original compiler failure\n')
            raise FileNotFoundError(2,'No such file',str(log.parent/'build/libturtlebot3_node_lib.so'))
        with self.assertRaises(FileNotFoundError):
            guard_runtime.ensure(Path(guard_runtime.__file__).parent,self.path/'home',runner=missing,
                diagnostic=lambda row,log:owner._guard_diagnostic('original-prepare-request','EXPLICIT_PREPARE',row,log))
        manifest=export_sources(directory,emit,required_members=('output-guard-build.jsonl','output-guard-build.log'))
        emit('cleanup',dict(subsystem='session',confirmed=False))
        recovered=self.recover()
        diagnostic=next(e['data']['build_diagnostic'] for e in reversed(recovered['events'])
            if e['data'].get('action')=='output_guard_diagnostic')
        self.assertEqual(diagnostic['error']['exception_type'],'FileNotFoundError')
        self.assertEqual(diagnostic['binding']['request_id'],'original-prepare-request')
        self.assertEqual(diagnostic['binding']['operation_id'],self.identity['operation_id'])
        self.assertEqual(diagnostic['binding']['worker_sha256'],self.sha)
        self.assertEqual(recovered['source_export'],manifest)
        self.assertFalse(recovered['cleanup_confirmed'])
        self.assertFalse(recovered['field_trial_resolution']['authority_restored'])
    def test_missing_cleanup_is_unknown_not_false_success(self):
        self.events.pop();self.assertIsNone(self.recover()['cleanup_confirmed'])
    def test_identity_sequence_context_and_worker_changes_rejected(self):
        for key,value in [('operation_id','f'*32),('sequence',9),('source_twin_context_id','f'*64)]:
            original=self.events[1][key];self.events[1][key]=value
            with self.assertRaises(ValueError):self.recover()
            self.events[1][key]=original
        self.events[1]['data']['worker_sha256']='f'*64
        with self.assertRaisesRegex(ValueError,'WORKER_CHANGED'):self.recover()
    def test_digest_and_total_count_rejected(self):
        receipt=self.receipt();receipt['event_count']+=1
        with self.assertRaisesRegex(ValueError,'RECEIPT_COUNT'):recover_live_history(self.path,receipt,**self.identity)
        receipt=self.receipt();receipt['segments'][0]['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'SEGMENT_SHA'):recover_live_history(self.path,receipt,**self.identity)
    def test_traversal_and_nonfinite_rejected(self):
        receipt=self.receipt();receipt['segments'][0]['path']='../outside.jsonl'
        with self.assertRaisesRegex(ValueError,'MEMBER_PATH'):recover_live_history(self.path,receipt,**self.identity)
        self.events[1]['robot_monotonic_s']=float('nan')
        with self.assertRaisesRegex(ValueError,'NONFINITE'):self.recover()
    def test_changed_source_map_cannot_claim_original_bundle(self):
        self.first['worker_sources']={**self.files,'fleet_worker.py':'f'*64}
        with self.assertRaisesRegex(ValueError,'SHA_MISMATCH'):self.recover()
        with self.assertRaises(ValueError):checked_worker_sources({'../bad.py':'a'*64},self.sha)
    def test_verified_sidecar_is_bound_to_same_original_operation(self):
        del self.first['worker_sources']
        side=dict(schema='physical-live-worker-sources-1.0',**{k:v for k,v in self.identity.items() if k not in {'binding_sha256','source_twin_context'}},worker_sha256=self.sha,files=self.files)
        (self.path/'worker-sources.json').write_text(json.dumps(side),encoding='utf-8')
        result=self.recover();self.assertEqual(result['worker_sources_provenance'],'VERIFIED_MATCHING_PRESERVED_PACKAGE')
        side['operation_id']='f'*32;(self.path/'worker-sources.json').write_text(json.dumps(side),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'BINDING'):self.recover()

if __name__=='__main__':unittest.main()
