# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Persistent diagnostics through the real product code, no paid calls/hardware."""
import asyncio
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch

from tests.integration.test_r5_product_api import R5ProductApiTests
from tests.integration.test_chat_conversation import ChatConversationTests
from twinpulse_core.execution_diagnostics import ExecutionStore, TraceContext, metadata, profile_call


class ExecutionStoreTests(unittest.TestCase):
    def test_manifest_encoding_and_structured_version_fail_closed_without_rewriting(self):
        trace=self.store.begin('selected');trace.finish();self.store.flush()
        path=self.root/trace.execution_id/'manifest.json';original=path.read_bytes()
        manifest=json.loads(original);manifest.pop('component',None)
        invalid=[original.decode('utf-8').encode('utf-16')]
        invalid += [json.dumps({**manifest,'schema_version':version}).encode('utf-8')
                    for version in ([],{},None,True,1)]
        for encoded in invalid:
            with self.subTest(encoded=encoded[:12]):
                path.write_bytes(encoded)
                with self.assertRaises((ValueError,OSError)):self.store.detail(trace.execution_id)
                with self.assertRaises((ValueError,OSError)):self.store.graph(trace.execution_id)
                listing=self.store.list()
                self.assertEqual(listing['executions'],[])
                self.assertEqual(listing['health']['unavailable_executions'],1)
                self.assertTrue(listing['health']['diagnostics_degraded'])
                self.assertEqual(path.read_bytes(),encoded)
        path.write_bytes(original)
        self.assertEqual(self.store.detail(trace.execution_id)['status'],'succeeded')

    def test_graph_bounds_nested_event_directory_and_preserves_other_records(self):
        damaged=self.store.begin('crowded_record');damaged.finish()
        selected=self.store.begin('selected',command_execution_id=damaged.execution_id)
        selected.finish();self.store.flush()
        directory=self.root/damaged.execution_id
        original={path.name:path.read_bytes() for path in directory.iterdir()}
        real_iterdir=Path.iterdir;visits=0
        def entries(path):
            if path!=directory:return real_iterdir(path)
            def crowded():
                nonlocal visits
                for number in range(5000):
                    visits+=1
                    yield directory/f'unrelated-{number}.txt'
            return crowded()
        with patch.object(Path,'iterdir',entries):
            graph=self.store.graph(selected.execution_id)
        self.assertEqual(visits,4097)
        self.assertTrue(graph['partial'])
        node=next(node for node in graph['nodes'] if node['execution_id']==damaged.execution_id)
        self.assertEqual((node['available'],node['stage'],node['status']),(False,None,'unknown'))
        self.assertEqual({path.name:path.read_bytes() for path in directory.iterdir()},original)
        self.assertEqual(self.store.detail(selected.execution_id)['status'],'succeeded')

    def test_graph_total_actual_reads_remain_bounded_across_many_medium_records(self):
        records = [self.store.begin('medium_record') for _ in range(12)]
        selected = self.store.begin('selected')
        for record in records:
            selected.bind(command_execution_id=record.execution_id)
            record.finish()
        selected.finish();self.store.flush()
        for record in records:
            path = self.root/record.execution_id/'events.jsonl'
            template = json.loads(path.read_text().splitlines()[0])
            with path.open('ab') as stream:
                for index in range(900):
                    value = {**template, 'type':'references', 'sequence':index+100,
                             'event_id':f'{index+100:032x}', 'metadata':{}}
                    line = json.dumps(value).encode()
                    stream.write(line+b' '*(999-len(line))+b'\n')
        opened = Path.open
        total = 0
        class Counted:
            def __init__(self, stream):self.stream=stream
            def __enter__(self):self.stream.__enter__();return self
            def __exit__(self,*args):return self.stream.__exit__(*args)
            def read(self,*args):
                nonlocal total
                value=self.stream.read(*args);total+=len(value);return value
            def readline(self,*args):
                nonlocal total
                value=self.stream.readline(*args);total+=len(value);return value
        with patch.object(Path,'open',lambda path,*args,**kwargs:Counted(opened(path,*args,**kwargs))):
            graph = self.store.graph(selected.execution_id)
        self.assertTrue(graph['partial'])
        self.assertLessEqual(total,graph['limits']['total_read_bytes'])
        self.assertEqual(len(graph['edges']),12)
        self.assertTrue(any(node['status']=='unknown' for node in graph['nodes'] if node['execution_id']!=selected.execution_id))

    def test_graph_stops_directory_enumeration_at_its_declared_bound(self):
        trace = self.store.begin('selected');trace.finish();self.store.flush()
        real_iterdir=Path.iterdir
        visits=0
        def entries(path):
            nonlocal visits
            if path!=self.root:return real_iterdir(path)
            def bounded_entries():
                nonlocal visits
                for _ in range(5000):
                    visits+=1
                    yield self.root/trace.execution_id
            return bounded_entries()
        with patch.object(Path,'iterdir',entries):
            graph=self.store.graph(trace.execution_id)
        self.assertTrue(graph['partial']);self.assertEqual(visits,4097)
        self.assertLessEqual(graph['reverse_scanned_count'],100)

    def test_graph_uses_typed_references_in_both_directions_without_raw_or_writes(self):
        launch = self.store.begin('launcher_start'); launch.finish()
        generation = self.store.begin('generation', launch_execution_id=launch.execution_id,
                                      request_id='same-request'); generation.finish()
        build = self.store.begin('engine_command_build_site_scene', request_id='same-request')
        build.bind(evidence_kind='generation_execution', evidence_id=generation.execution_id)
        build.finish()
        retry = self.store.begin('retry', retry_of=build.execution_id); retry.finish()
        unrelated = self.store.begin('unrelated', request_id='same-request',
                                    evidence_kind='private_raw', evidence_id=generation.execution_id)
        unrelated.finish(); self.store.flush()
        def hashes():
            return {str(p.relative_to(self.root)):hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in self.root.rglob('*') if p.is_file()}
        before = hashes()
        graph = self.store.graph(generation.execution_id)
        self.assertFalse(graph['partial']); self.assertFalse(graph['raw_included'])
        self.assertFalse(graph['physical_authority'])
        self.assertEqual({tuple(edge.values()) for edge in graph['edges']}, {
            (generation.execution_id, launch.execution_id, 'launch_execution_id'),
            (build.execution_id, generation.execution_id, 'evidence_id')})
        self.assertNotIn(unrelated.execution_id, {node['execution_id'] for node in graph['nodes']})
        self.assertEqual(hashes(), before)
        retry_graph = self.store.graph(build.execution_id)
        self.assertIn(dict(source=retry.execution_id, target=build.execution_id, relation='retry_of'), retry_graph['edges'])
        self.assertNotIn('graph', self.store.export(generation.execution_id)['diagnostics'])

    def test_graph_unavailable_foreign_missing_corrupt_and_cycle_are_not_success(self):
        foreign = ExecutionStore(self.root, 'other-project')
        other = foreign.begin('private_foreign_stage'); other.finish(); foreign.flush()
        missing = 'f'*32
        selected = self.store.begin('selected', command_execution_id=other.execution_id,
                                    scene_edit_execution_id=missing)
        selected.finish(); self.store.flush()
        graph = self.store.graph(selected.execution_id)
        self.assertTrue(graph['partial'])
        for node in graph['nodes']:
            if node['execution_id'] != selected.execution_id:
                self.assertEqual((node['available'],node['stage'],node['status']), (False,None,'unknown'))
        self.assertNotIn('private_foreign_stage', json.dumps(graph))
        for identity in (other.execution_id, missing, '../private'):
            with self.assertRaises((ValueError,OSError)): self.store.graph(identity)
        first = self.store.begin('cycle_a')
        second = self.store.begin('cycle_b', command_execution_id=first.execution_id)
        first.bind(command_execution_id=second.execution_id)
        first.finish();second.finish();self.store.flush()
        self.assertEqual(len(self.store.graph(first.execution_id)['edges']),2)

    def test_graph_caps_nodes_reverse_scan_and_large_record_reads(self):
        selected = self.store.begin('selected');selected.finish();self.store.flush()
        traces = [self.store.begin('incoming', command_execution_id=selected.execution_id) for _ in range(105)]
        for trace in traces:trace.finish()
        self.store.flush()
        graph = self.store.graph(selected.execution_id)
        self.assertTrue(graph['partial']); self.assertLessEqual(len(graph['nodes']),32)
        self.assertEqual(graph['reverse_scanned_count'],100)
        large = self.store.begin('large', command_execution_id=selected.execution_id)
        large.finish();self.store.flush()
        with (self.root/large.execution_id/'events.jsonl').open('ab') as stream:
            stream.write(b' '*(1024*1024))
        with patch.object(self.store, 'detail', wraps=self.store.detail) as read:
            graph = self.store.graph(large.execution_id)
        self.assertTrue(graph['partial'])
        self.assertFalse(any(call.args[0]==large.execution_id for call in read.call_args_list))
        large_node = next(node for node in graph['nodes'] if node['execution_id']==large.execution_id)
        self.assertEqual(large_node['status'],'unknown')
        self.assertIn(dict(source=large.execution_id,target=selected.execution_id,relation='command_execution_id'),graph['edges'])

    def test_bounded_detail_read_rejects_growth_and_graph_ignores_linked_evidence(self):
        trace = self.store.begin('bounded');trace.finish();self.store.flush()
        with self.assertRaisesRegex(ValueError, 'read budget'):
            self.store.detail(trace.execution_id, read_limit=1)
        selected = self.store.begin('selected',command_execution_id=trace.execution_id)
        selected.finish();self.store.flush()
        import os
        events = self.root/trace.execution_id/'events.jsonl'
        os.link(events, self.root/'retained-hardlink')
        graph = self.store.graph(selected.execution_id)
        node = next(node for node in graph['nodes'] if node['execution_id']==trace.execution_id)
        self.assertFalse(node['available']);self.assertTrue(graph['partial'])
        self.assertTrue((self.root/'retained-hardlink').exists())

    def test_coded_cleanup_failure_without_exception_never_replaces_primary_cause(self):
        trace=self.store.begin('coded_cleanup')
        trace.child('primary').finish('failed',error_code='PRIMARY_FAILED')
        trace.child('cleanup').finish('failed',role='cleanup',error_code='CLEANUP_FAILED')
        trace.finish('failed');self.store.flush()
        detail=self.store.detail(trace.execution_id)
        self.assertEqual(detail['first_error']['error_code'],'PRIMARY_FAILED')
        cleanup=next(span for span in detail['spans'] if span['stage']=='cleanup')
        self.assertEqual(cleanup['metadata']['role'],'cleanup')

    def test_edit_binding_requires_exact_committed_history_and_preserves_failed_review(self):
        selectors=dict(request_id='request-edit',input_revision='a'*64,source_revision='b'*64,
            operation_id='move-bed',history_digest='c'*64,result_revision='d'*64)
        trace=self.store.begin('scene_edit_apply',request_id='request-edit',input_revision='a'*64,
            source_scene_revision='b'*64,operation_id='move-bed')
        with trace.span('scene_edit_validate_and_save'):pass
        trace.bind(scene_edit_revision='d'*64,scene_change_sha256='c'*64)
        with self.assertRaises(ValueError):
            with trace.span('scene_edit_register_review'):raise ValueError('PRIVATE')
        trace.finish('failed');self.store.flush()
        self.assertTrue(self.store.remember_edit_binding(trace.execution_id,**selectors))
        reopened=ExecutionStore(self.root,'project-a')
        refs=reopened.restore_edit_binding(**selectors)
        self.assertEqual(refs['scene_edit_execution_id'],trace.execution_id)
        self.assertEqual(reopened.detail(trace.execution_id)['first_error']['stage'],'scene_edit_register_review')
        for field in selectors:
            other={**selectors,field:'another' if field in {'request_id','operation_id'} else 'e'*64}
            self.assertEqual(reopened.restore_edit_binding(**other),{})
        self.assertEqual(ExecutionStore(self.root,'project-b').restore_edit_binding(**selectors),{})
        self.assertFalse(reopened.remember_edit_binding('f'*32,**selectors))
        path=next((self.root/'links').iterdir());original=path.read_bytes()
        value=json.loads(original);value['metadata']['scene_edit_execution_id']='f'*32
        path.write_text(json.dumps(value))
        self.assertEqual(reopened.restore_edit_binding(**selectors),{})
        self.assertTrue(reopened.health['diagnostics_degraded'])
        self.assertNotIn('PRIVATE',json.dumps(reopened.list()))

    def test_uncommitted_edit_and_binding_storage_failure_never_fabricate_a_reference(self):
        selectors=dict(request_id='request-edit',input_revision='a'*64,source_revision='b'*64,
            operation_id='move-bed',history_digest='c'*64,result_revision='d'*64)
        trace=self.store.begin('scene_edit_apply',request_id='request-edit',input_revision='a'*64,
            source_scene_revision='b'*64,operation_id='move-bed')
        trace.bind(scene_edit_revision='d'*64,scene_change_sha256='c'*64)
        trace.finish('failed');self.store.flush()
        self.assertFalse(self.store.remember_edit_binding(trace.execution_id,**selectors))
        self.assertEqual(self.store.restore_edit_binding(**selectors),{})
        committed=self.store.begin('scene_edit_undo',request_id='request-edit',input_revision='a'*64,
            source_scene_revision='b'*64,operation_id='move-bed')
        with committed.span('scene_edit_validate_and_save'):pass
        committed.bind(scene_edit_revision='d'*64,scene_change_sha256='c'*64)
        committed.finish();self.store.flush()
        with patch.object(self.store,'_budget',side_effect=OSError('PRIVATE DISK')):
            self.assertFalse(self.store.remember_edit_binding(committed.execution_id,**selectors))
        self.assertEqual(self.store.restore_edit_binding(**selectors),{})
        self.assertEqual(self.store.detail(committed.execution_id)['status'],'succeeded')

    def test_search_pages_keep_ties_snapshot_and_restart_scope_without_duplicates(self):
        import os
        traces=[self.store.begin('saved_step',request_id=f'request-{i}') for i in range(4)]
        for trace in traces:trace.finish()
        self.store.flush()
        for trace in traces:os.utime(self.root/trace.execution_id/'manifest.json',ns=(10**9,10**9))
        expected=sorted([trace.execution_id for trace in traces],reverse=True)
        first=self.store.list(2)
        self.assertEqual([row['execution_id'] for row in first['executions']],expected[:2])
        new=self.store.begin('new_after_snapshot');new.finish();self.store.flush()
        # Appending evidence changes the directory, not the manifest order.
        traces[0].bind(request_id='late-reference');self.store.flush()
        reopened=ExecutionStore(self.root,'project-a')
        second=reopened.list(2,cursor=first['next_cursor'])
        self.assertEqual([row['execution_id'] for row in second['executions']],expected[2:])
        self.assertFalse(second['has_more'])
        self.assertEqual(reopened.list(1)['executions'][0]['execution_id'],new.execution_id)
        with self.assertRaises(ValueError):reopened.list(cursor=first['next_cursor'],query='different')
        with self.assertRaises(ValueError):ExecutionStore(self.root,'project-b').list(cursor=first['next_cursor'])
        import base64
        value=json.loads(base64.urlsafe_b64decode(first['next_cursor']+'='*(-len(first['next_cursor'])%4)))
        value['version']=True
        invalid=base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip('=')
        with self.assertRaises(ValueError):reopened.list(cursor=invalid)

    def test_sparse_filtered_pages_are_bounded_and_search_safe_child_metadata(self):
        import os
        for index in range(105):
            trace=self.store.begin('search_candidate')
            trace.child('worker',mission_id='find-this-mission' if index==0 else 'unrelated').finish()
            trace.finish('failed' if index==0 else 'succeeded')
            stamp=10**9+index*10**6  # Above Windows filesystem timestamp precision.
            os.utime(self.root/trace.execution_id/'manifest.json',ns=(stamp,stamp))
        self.store.flush()
        first=self.store.list(5,query='FIND-THIS-MISSION',status='failed')
        self.assertEqual(first['executions'],[]);self.assertEqual(first['scanned_count'],100)
        self.assertTrue(first['has_more'])
        second=self.store.list(5,query='FIND-THIS-MISSION',status='failed',cursor=first['next_cursor'])
        self.assertEqual(len(second['executions']),1);self.assertEqual(second['scanned_count'],5)
        self.assertFalse(second['has_more'])
        self.assertEqual(self.store.list(query='PRIVATE')['executions'],[])

    def test_list_marks_corruption_and_validates_query_without_private_echo(self):
        trace=self.store.begin('saved_step');trace.finish();self.store.flush()
        (self.root/trace.execution_id/'manifest.json').write_text('PRIVATE malformed file')
        value=self.store.list()
        self.assertEqual(value['executions'],[])
        self.assertEqual(value['health']['unavailable_executions'],1)
        self.assertTrue(value['health']['diagnostics_degraded'])
        self.assertNotIn('PRIVATE',json.dumps(value))
        for args in ({'limit':0},{'limit':True},{'query':'x'*161},{'query':'<script>'},
                     {'status':'bogus'},{'cursor':'../PRIVATE'},{'cursor':'e30'}):
            with self.assertRaises(ValueError):self.store.list(**args)

    def test_duplicate_events_never_rewrite_a_failure_and_keep_first_stage(self):
        trace=self.store.begin('generation')
        with self.assertRaises(ValueError):
            with trace.span('planner_validation'):raise ValueError('PRIVATE')
        trace.finish('failed');self.store.flush()
        path=self.root/trace.execution_id/'events.jsonl'
        original=self.store.detail(trace.execution_id)
        duplicate=next(e for e in original['events'] if e.get('status')=='failed')
        with path.open('a') as stream:stream.write(json.dumps({**duplicate,'status':'succeeded'})+'\n')
        result=self.store.detail(trace.execution_id)
        self.assertEqual(result['status'],'failed')
        self.assertEqual(result['event_count'],original['event_count'])
        self.assertEqual(result['health']['duplicate_events'],1)
        self.assertTrue(result['health']['diagnostics_degraded'])
        self.assertEqual(result['first_error']['stage'],'planner_validation')
        self.assertEqual(result['first_error']['failed_span_id'],duplicate['span_id'])

    def test_event_identity_component_and_legacy_sidecars_reopen(self):
        trace=self.store.begin('generation',component='app')
        with trace.span('planner',component='provider'):pass
        trace.finish();self.store.flush()
        value=self.store.detail(trace.execution_id)
        self.assertEqual(value['manifest']['schema_version'],'1.1')
        self.assertEqual(len({e['event_id'] for e in value['events']}),len(value['events']))
        self.assertEqual({e['component'] for e in value['events']},{'app','provider'})
        directory=self.root/trace.execution_id
        manifest=value['manifest'];manifest['schema_version']='1.0';manifest.pop('component')
        (directory/'manifest.json').write_text(json.dumps(manifest))
        rows=[{k:v for k,v in e.items() if k not in {'event_id','component','schema_version'}} for e in value['events']]
        (directory/'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in rows))
        self.assertEqual(self.store.detail(trace.execution_id)['status'],'succeeded')

    def test_binding_reopens_only_exact_project_request_input_scene_and_counts_quota(self):
        trace=self.store.begin('scene_generation',request_id='request-1',input_revision='a'*64,generation_id='g-1')
        trace.bind(draft_revision='b'*64);trace.finish();self.store.flush()
        self.assertTrue(self.store.remember_binding(trace.execution_id,request_id='request-1',input_revision='a'*64,source_revision='b'*64))
        restored=ExecutionStore(self.root,'project-a')
        refs=restored.restore_binding(request_id='request-1',input_revision='a'*64,source_revision='b'*64)
        self.assertEqual(refs['evidence_id'],trace.execution_id)
        self.assertEqual(refs['generation_id'],'g-1')
        self.assertEqual(restored.restore_binding(request_id='request-2',input_revision='a'*64,source_revision='b'*64),{})
        self.assertEqual(ExecutionStore(self.root,'project-b').restore_binding(request_id='request-1',input_revision='a'*64,source_revision='b'*64),{})
        restored._budget('0'*32,0)
        self.assertEqual(restored._total_size,sum(p.stat().st_size for p in self.root.rglob('*') if p.is_file()))
        path=next((self.root/'links').iterdir());value=json.loads(path.read_text());value['metadata']['prompt']='PRIVATE'
        path.write_text(json.dumps(value))
        self.assertEqual(restored.restore_binding(request_id='request-1',input_revision='a'*64,source_revision='b'*64),{})
        self.assertTrue(restored.health['diagnostics_degraded'])

    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name) / 'diagnostics'
        self.store = ExecutionStore(self.root, 'project-a')

    def tearDown(self):
        self.store.flush()
        self.temporary.cleanup()

    def test_nested_failure_cleanup_success_and_reopen(self):
        trace = self.store.begin('generation', workflow_id='chat-1')
        child = trace.child('planner', attempt_id='a' * 32)
        child.finish('failed', error=ValueError('SECRET input text'))
        cleanup = trace.child('cleanup')
        cleanup.finish('failed', error=OSError('SECRET path'), role='cleanup')
        repaired = trace.child('repair')
        repaired.finish()
        trace.finish()
        trace.finish('failed', error_code='late_failure')
        self.assertTrue(self.store.flush())
        value = ExecutionStore(self.root, 'project-a').detail(trace.execution_id)
        self.assertEqual(value['status'], 'succeeded')
        self.assertEqual(value['first_error']['error_type'], 'ValueError')
        self.assertEqual([s['status'] for s in value['spans']], ['succeeded', 'failed', 'failed', 'succeeded'])
        self.assertGreaterEqual(value['duration_s'], 0)
        self.assertNotIn('SECRET', json.dumps(value))
        self.assertEqual(len([e for e in value['events'] if e['type']=='span_finished']), 4)

    def test_context_is_explicit_and_separate_executions_never_mix(self):
        from concurrent.futures import ThreadPoolExecutor
        traces = [self.store.begin('same_plan', plan_id='p-1') for _ in range(2)]
        def run(trace, attempt):
            with trace.span('worker', attempt_id=attempt):
                trace.bind(request_id=attempt)
            trace.finish()
        with ThreadPoolExecutor(2) as pool:
            list(pool.map(run, traces, ['attempt-a', 'attempt-b']))
        self.store.flush()
        for trace, expected in zip(traces, ['attempt-a', 'attempt-b']):
            value = self.store.detail(trace.execution_id)
            self.assertIn(expected, json.dumps(value))
            self.assertNotIn('attempt-b' if expected=='attempt-a' else 'attempt-a', json.dumps(value))
        self.assertNotEqual(traces[0].execution_id, traces[1].execution_id)

    def test_started_without_result_after_process_restart_is_unknown(self):
        trace = self.store.begin('generation')
        self.store.flush()
        with patch('twinpulse_core.execution_diagnostics._CLOCK', 'different-process'):
            value = ExecutionStore(self.root, 'project-a').detail(trace.execution_id)
        self.assertEqual(value['status'], 'unknown')
        self.assertIsNone(value['duration_s'])

    def test_owned_child_exit_leaves_dispatch_unknown_without_replaying_http(self):
        import subprocess
        import sys
        code='''import asyncio, os, sys
from pathlib import Path
from twinpulse_core.execution_diagnostics import ExecutionStore
from twinpulse_provider import CancellationToken
from twinpulse_provider.reliability import InferenceEvidence, AuditedChatTransport
from packages.twinpulse_provider.tests.test_nebius_pipeline import config, PLANNER_MODEL
root=Path(sys.argv[1]);store=ExecutionStore(root/'diagnostics','project-a');trace=store.begin('generation')
token=CancellationToken();token.diagnostics=trace;store.flush()
class Response:
 def __enter__(self):return self
 def __exit__(self,*args):pass
 def geturl(self):return config().endpoint_url()
 def read(self,n):os._exit(7)
def offline_opener(*args,**kwargs):
 if sys.argv[2]=='before_response':os._exit(7)
 return Response()
transport=AuditedChatTransport(lambda:'fixture-secret',InferenceEvidence(root/'private'),opener=offline_opener)
asyncio.run(transport.complete(dict(model=PLANNER_MODEL,max_tokens=100,response_format={}),token,config()))
'''
        for mode in ('before_response','during_response'):
            with self.subTest(mode=mode):
                root=Path(self.temporary.name)/mode
                child=subprocess.run([sys.executable,'-c',code,str(root),mode],capture_output=True,timeout=15)
                self.assertEqual(child.returncode,7,child.stderr.decode(errors='replace'))
                recovered=ExecutionStore(root/'diagnostics','project-a')
                summary=recovered.list()['executions'][0]
                self.assertEqual(summary['status'],'unknown')
                intents=list((root/'private/dispatches').glob('*.json'))
                self.assertEqual(len(intents),1)
                intent=json.loads(intents[0].read_text())
                self.assertEqual(intent['execution_id'],summary['execution_id'])
                self.assertEqual(intent['dispatch_state'],'admitted_not_proven_sent')
                self.assertFalse(list((root/'private').glob('*.json')))
                recovered.export(summary['execution_id'])
                self.assertEqual(len(list((root/'private/dispatches').glob('*.json'))),1)

    def test_allowlist_drops_inputs_urls_headers_paths_and_nonfinite_values(self):
        item = metadata(dict(prompt='private', image='data:a;base64,123', authorization='Bearer secret',
            source_file='C:\\private\\key.py', error_type='BearerSecret', model_id='https://secret.invalid',
            elapsed_s=float('nan'), request_id='safe-1', max_tokens=10000))
        self.assertEqual(item, dict(request_id='safe-1', max_tokens=10000))

    def test_project_scope_and_path_traversal(self):
        trace = self.store.begin('generation'); trace.finish(); self.store.flush()
        with self.assertRaises(ValueError): ExecutionStore(self.root, 'project-b').detail(trace.execution_id)
        for identity in ('../manifest.json', '', 'a' * 31, 'G' * 32):
            with self.assertRaises(ValueError): self.store.detail(identity)

    def test_export_hash_and_no_raw(self):
        trace = self.store.begin('generation'); trace.finish(); self.store.flush()
        value = self.store.export(trace.execution_id)
        raw = json.dumps(value['diagnostics'], ensure_ascii=True, sort_keys=True, separators=(',', ':')).encode()
        self.assertEqual(value['export_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertFalse(value['diagnostics']['raw_included'])
        self.assertFalse(value['diagnostics']['physical_authority'])

    def test_unwritable_optional_sink_keeps_original_failure(self):
        self.root.write_text('not a directory')
        trace = self.store.begin('generation')
        with self.assertRaisesRegex(ValueError, 'original'):
            with trace.span('planner'): raise ValueError('original')
        trace.finish('failed'); self.store.flush()
        self.assertTrue(self.store.health['diagnostics_degraded'])

    def test_quota_does_not_delete_other_evidence(self):
        raw = Path(self.temporary.name) / 'raw.json'; raw.write_text('original')
        store = ExecutionStore(self.root, 'project-a', total_limit=10)
        trace = store.begin('generation'); trace.finish(); store.flush()
        self.assertTrue(store.health['diagnostics_degraded'])
        self.assertEqual(raw.read_text(), 'original')

    def test_independent_store_caches_cannot_exceed_shared_quota(self):
        stores=[ExecutionStore(self.root,'project-a',total_limit=12000) for _ in range(2)]
        for index in range(18):
            store=stores[index%2];trace=store.begin('generation',request_id=f'request-{index}')
            trace.finish();self.assertTrue(store.flush())
        size=sum(path.stat().st_size for path in self.root.rglob('*') if path.is_file())
        self.assertLessEqual(size,12000)
        self.assertTrue(any(store.health['diagnostics_degraded'] for store in stores))

    def test_two_owned_processes_reserve_shared_quota_without_mixing_project_scopes(self):
        import subprocess,sys
        code='''import json,sys
from pathlib import Path
from twinpulse_core.execution_diagnostics import ExecutionStore
store=ExecutionStore(Path(sys.argv[1]),sys.argv[2],total_limit=24000)
sys.stdin.readline()
for index in range(60):
 trace=store.begin('parallel_write',request_id=f'{sys.argv[2]}-{index}');trace.finish();store.flush()
print(json.dumps(store.health))
'''
        children=[]
        try:
            for project in ('project-a','project-b'):
                children.append(subprocess.Popen([sys.executable,'-c',code,str(self.root),project],
                    cwd=Path(__file__).resolve().parents[2],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True))
            for child in children:child.stdin.write('start\n');child.stdin.flush()
            reports=[]
            for child in children:
                output,error=child.communicate(timeout=15)
                self.assertEqual(child.returncode,0,error);reports.append(json.loads(output))
            size=sum(path.stat().st_size for path in self.root.rglob('*') if path.is_file())
            self.assertLessEqual(size,24000);self.assertTrue(any(report['diagnostics_degraded'] for report in reports))
            for directory in self.root.iterdir():
                if not directory.is_dir() or not (directory/'manifest.json').is_file():continue
                value=json.loads((directory/'manifest.json').read_text())
                owner=value['project_id'];other='project-b' if owner=='project-a' else 'project-a'
                detail=ExecutionStore(self.root,owner).detail(directory.name)
                self.assertTrue(all(event['execution_id']==directory.name for event in detail['events']))
                self.assertNotIn(other,json.dumps(detail))
                with self.assertRaises(ValueError):ExecutionStore(self.root,other).detail(directory.name)
        finally:
            for child in children:
                if child.poll() is None:child.terminate();child.wait(timeout=5)  # Only these owned test children.

    def test_writer_contention_is_degraded_not_blocking_control_admission(self):
        other=ExecutionStore(self.root,'project-a')
        with self.store._write_guard():
            started=time.monotonic();trace=other.begin('engine_command_pause',durable=False);trace.finish()
            self.assertLess(time.monotonic()-started,.2)
            self.assertTrue(other.flush());self.assertTrue(other.health['diagnostics_degraded'])
        self.assertFalse((self.root/trace.execution_id/'manifest.json').exists())

    def test_corrupt_or_hardlinked_writer_marker_is_preserved_and_reports_degraded(self):
        import os
        self.root.mkdir();marker=self.root/'writer.lock';marker.write_bytes(b'original-invalid-marker')
        trace=self.store.begin('generation');trace.finish();self.store.flush()
        self.assertEqual(marker.read_bytes(),b'original-invalid-marker')
        self.assertTrue(self.store.health['diagnostics_degraded'])
        marker.unlink();outside=Path(self.temporary.name)/'protected-marker';outside.write_bytes(b'original')
        os.link(outside,marker)
        another=ExecutionStore(self.root,'project-a');trace=another.begin('generation');trace.finish();another.flush()
        self.assertEqual(outside.read_bytes(),b'original');self.assertTrue(another.health['diagnostics_degraded'])

    def test_owned_writer_crash_invalidates_existing_quota_cache_and_releases_os_lock(self):
        import subprocess,sys
        initial=self.store.begin('generation');initial.finish();self.store.flush()
        cached=self.store._total_size
        code='''import os,sys
from pathlib import Path
from twinpulse_core.execution_diagnostics import ExecutionStore
store=ExecutionStore(Path(sys.argv[1]),'project-a')
with store._write_guard():
 directory=store._directory('a'*32,create=True)
 (directory/'events.jsonl').write_bytes(b'x'*4096)
 os._exit(7)
'''
        child=subprocess.run([sys.executable,'-c',code,str(self.root)],cwd=Path(__file__).resolve().parents[2],timeout=10)
        self.assertEqual(child.returncode,7)
        self.assertEqual(int.from_bytes((self.root/'writer.lock').read_bytes(),'little')%2,1)
        next_trace=self.store.begin('after_crash');next_trace.finish();self.store.flush()
        self.assertEqual(self.store.detail(next_trace.execution_id)['status'],'succeeded')
        self.assertGreater(self.store._total_size,cached+4096)
        self.assertEqual(self.store._total_size,sum(path.stat().st_size for path in self.root.rglob('*') if path.is_file()))
        self.assertEqual((self.root/('a'*32)/'events.jsonl').stat().st_size,4096)

    def test_queue_full_has_reserved_terminal_slots_and_visible_drop(self):
        store = ExecutionStore(self.root, 'project-a', queue_limit=1)
        store._worker = object()  # Isolate queue policy without running a writer.
        trace = TraceContext(store, 'a' * 32, 'b' * 32)
        trace.bind(request_id='one'); trace.bind(request_id='two'); trace.finish('failed')
        self.assertEqual(store.health['dropped_events'], 1)
        self.assertEqual(store._terminal.qsize(), 1)

    def test_async_control_command_diagnostic_start_has_no_synchronous_io(self):
        with patch.object(self.store, '_directory', side_effect=OSError('offline sink')):
            trace = self.store.begin('engine_command_pause', durable=False)
            trace.finish()
        self.store.flush()
        # Actual writer failure is allowed; command admission never raises.

    def test_profile_is_opt_in_strips_paths_and_labels_actual_cpu(self):
        trace = self.store.begin('pure_compile')
        self.assertEqual(profile_call(trace, 'disabled', sum, [1,2]), 3)
        def pure(): return sum(i * i for i in range(2000))
        self.assertEqual(profile_call(trace, 'enabled', pure, enabled=True), pure())
        trace.finish(); self.store.flush()
        rows = [e for e in self.store.detail(trace.execution_id)['events'] if e['type']=='profile_row']
        self.assertTrue(rows)
        self.assertLessEqual(len(rows), 30)
        self.assertTrue(all(e['metadata']['timer_basis']=='thread_cpu' for e in rows))
        self.assertNotIn(str(Path(__file__).parent), json.dumps(rows))

    def test_tampered_export_cannot_include_extra_raw_fields(self):
        trace=self.store.begin('generation');trace.finish();self.store.flush()
        path=self.root/trace.execution_id/'events.jsonl'
        with path.open('a') as stream:
            stream.write(json.dumps({'execution_id':trace.execution_id,'span_id':trace.span_id,
                'sequence':100,'type':'references','response_raw':'PRIVATE'})+'\n')
        self.assertNotIn('PRIVATE',json.dumps(self.store.export(trace.execution_id)))

    def test_chunk_rollover_reopens_complete_tree_and_quota_counts_all_chunks(self):
        store=ExecutionStore(self.root,'project-a',chunk_limit=8192,execution_limit=32768)
        trace=store.begin('generation')
        for index in range(35):
            trace.bind(request_id=f'request-{index}',model_id='safe-model-'+'x'*120)
        trace.finish();store.flush()
        paths=list((self.root/trace.execution_id).glob('events*.jsonl'))
        self.assertGreater(len(paths),1)
        self.assertTrue(all(p.stat().st_size<=8192 for p in paths))
        reopened=ExecutionStore(self.root,'project-a',chunk_limit=8192,execution_limit=32768)
        value=reopened.detail(trace.execution_id)
        self.assertEqual(value['status'],'succeeded')
        self.assertEqual(value['event_count'],37)
        reopened._budget(trace.execution_id,0)
        self.assertEqual(reopened._total_size,8+sum(p.stat().st_size for p in (self.root/trace.execution_id).iterdir()))

    def test_malformed_event_types_are_not_exported_or_assumed_success(self):
        trace=self.store.begin('generation');self.store.flush()
        path=self.root/trace.execution_id/'events.jsonl'
        with path.open('a') as stream:
            for change in ({'status':['succeeded']},{'type':[]},{'parent_span_id':{'private':'PRIVATE'}},{'status':None}):
                item=dict(execution_id=trace.execution_id,span_id=trace.span_id,sequence=100,
                    type='span_finished',at='2026-10-07',clock_instance_id='other',monotonic_ns=1,metadata={})
                item.update(change);stream.write(json.dumps(item)+'\n')
        value=self.store.detail(trace.execution_id)
        self.assertEqual(value['status'],'running')
        self.assertEqual(value['health']['malformed_events'],4)
        self.assertTrue(value['health']['diagnostics_degraded'])
        self.assertNotIn('PRIVATE',json.dumps(value))

    def test_terminal_persists_writer_quota_failures_across_reopen(self):
        store=ExecutionStore(self.root,'project-a',execution_limit=6000)
        trace=store.begin('generation')
        for index in range(40):trace.bind(request_id=f'request-{index}')
        trace.finish();store.flush()
        value=ExecutionStore(self.root,'project-a').detail(trace.execution_id)
        self.assertEqual(value['status'],'succeeded')
        self.assertTrue(value['health']['diagnostics_degraded'])
        self.assertGreater(value['health']['storage_errors'],0)


class ProviderTraceTests(unittest.IsolatedAsyncioTestCase):
    async def test_mandatory_dispatch_record_failure_sends_no_http(self):
        from twinpulse_provider.reliability import InferenceEvidence, AuditedChatTransport
        from twinpulse_provider import CancellationToken
        from packages.twinpulse_provider.tests.test_nebius_pipeline import config, PLANNER_MODEL
        with TemporaryDirectory() as td:
            root=Path(td);store=ExecutionStore(root/'diagnostics','default');trace=store.begin('generation')
            token=CancellationToken();token.diagnostics=trace
            evidence=InferenceEvidence(root/'private')
            with patch.object(evidence,'started',side_effect=OSError('private path')):
                with patch('urllib.request.urlopen') as http:
                    transport=AuditedChatTransport(lambda:'secret-example',evidence,opener=http)
                    with self.assertRaises(OSError):
                        await transport.complete(dict(model=PLANNER_MODEL,max_tokens=100,response_format={}),token,config())
                    http.assert_not_called()
            trace.finish('failed');store.flush()
            self.assertEqual(store.detail(trace.execution_id)['first_error']['error_code'],'dispatch_record_failed')

    async def test_production_audit_records_before_http_and_keeps_two_response_hashes(self):
        from twinpulse_provider.reliability import InferenceEvidence, AuditedChatTransport
        from twinpulse_provider import CancellationToken
        from packages.twinpulse_provider.tests.test_nebius_pipeline import config, PLANNER_MODEL
        with TemporaryDirectory() as td:
            root=Path(td);store=ExecutionStore(root/'diagnostics','default');trace=store.begin('generation')
            token=CancellationToken();token.diagnostics=trace
            evidence=InferenceEvidence(root/'private');seen=[]
            raw=json.dumps(dict(id='response',model=PLANNER_MODEL,
                choices=[dict(finish_reason='stop',message=dict(content='{"safe":"not-logged"}'))],
                usage=dict(prompt_tokens=10,completion_tokens=20))).encode()
            class Response:
                def __enter__(self):return self
                def __exit__(self,*args):pass
                def geturl(self):return config().endpoint_url()
                def read(self,n):return raw
            def opener(*args,**kwargs):
                intent=json.loads(next((root/'private/dispatches').glob('*.json')).read_text())
                seen.append(intent)
                self.assertEqual(intent['dispatch_state'],'admitted_not_proven_sent')
                self.assertFalse(list((root/'private').glob('*.json')))
                return Response()
            transport=AuditedChatTransport(lambda:'not-logged',evidence,opener=opener)
            await transport.complete(dict(model=PLANNER_MODEL,max_tokens=100,response_format={}),token,config())
            trace.finish();store.flush()
            saved=json.loads(next((root/'private').glob('*.json')).read_text())
            self.assertEqual(saved['execution_id'],trace.execution_id)
            self.assertEqual(saved['response_sha256'],hashlib.sha256(raw).hexdigest())
            self.assertEqual(saved['stored_response_sha256'],hashlib.sha256(saved['response_redacted'].encode()).hexdigest())
            self.assertNotEqual(saved['response_sha256'],saved['stored_response_sha256'])
            self.assertNotIn('not-logged',json.dumps(saved))
            self.assertEqual(len(seen),1)

    async def test_one_repair_retains_failed_validation_and_new_stage(self):
        from dataclasses import replace
        from tests.integration.test_agent_reliability import adapter
        from packages.twinpulse_provider.tests.test_nebius_pipeline import ScriptedTransport, completion, config, PLANNER_MODEL
        from tests.integration.test_chat_site_text_generation import room
        from twinpulse_provider import GenerationRequest, GenerationService
        with TemporaryDirectory() as td:
            store=ExecutionStore(Path(td)/'diagnostics','default');trace=store.begin('generation')
            transport=ScriptedTransport(completion('bad',PLANNER_MODEL,{'invalid':True}),completion('good',PLANNER_MODEL,room()))
            service=GenerationService(adapter(transport),config(timeout_s=20),plan_version='2.2')
            await service.generate(GenerationRequest('request-1','Bedroom',diagnostics=trace))
            trace.finish();store.flush();value=store.detail(trace.execution_id)
            self.assertEqual(value['status'],'succeeded')
            self.assertEqual(len(transport.bodies),2)
            validations=[s for s in value['spans'] if s['stage']=='planner_validation']
            self.assertEqual([s['status'] for s in validations],['failed','succeeded'])
            self.assertEqual(value['first_error']['error_type'],'SceneContractError')
            self.assertEqual(value['first_error']['error_code'],'REQUIRED_TOOL_COUNT')

    def test_validation_codes_are_public_but_exception_details_remain_private(self):
        from twinpulse_app.product_workflow_service import _public_generation_diagnostics
        from twinpulse_provider.nebius_pipeline import _validation_code
        error=ValueError('photo layout: PHOTO_LAYOUT_REGION_FULL: private object name SECRET')
        self.assertEqual(_validation_code(error),'PHOTO_LAYOUT_REGION_FULL')
        public=_public_generation_diagnostics(dict(validation_code=_validation_code(error),
            validation_error=str(error),attempts=[dict(validation_code='PHOTO_RELATION_PART_UNSUPPORTED',
                                                       validation_error='PRIVATE')]))
        self.assertEqual(public['validation_code'],'PHOTO_LAYOUT_REGION_FULL')
        self.assertEqual(public['attempts'][0]['validation_code'],'PHOTO_RELATION_PART_UNSUPPORTED')
        self.assertNotIn('PRIVATE',json.dumps(public));self.assertNotIn('SECRET',json.dumps(public))
        for bad in ('private secret','PHOTO_FOO: private','PROVIDER_'+('A'*81),'PHOTO_bad'):
            self.assertNotIn('validation_code',_public_generation_diagnostics({'validation_code':bad}))

    async def test_openai_uses_same_durable_evidence_contract(self):
        from twinpulse_provider import OpenAIResponsesProvider, GenerationRequest, CancellationToken
        from twinpulse_provider.reliability import InferenceEvidence
        from packages.twinpulse_provider.tests.test_provider import config
        with TemporaryDirectory() as td:
            root=Path(td);store=ExecutionStore(root/'diagnostics','default');trace=store.begin('generation')
            raw=json.dumps({'output':[{'type':'message','content':[{'type':'output_text','text':'{"safe":true}'}]}],
                            'usage':{'input_tokens':10,'output_tokens':20}}).encode()
            class Response:
                def __enter__(self):return self
                def __exit__(self,*args):pass
                def read(self):return raw
            evidence=InferenceEvidence(root/'private');provider=OpenAIResponsesProvider(lambda:'secret-example',evidence=evidence)
            with patch('urllib.request.urlopen',return_value=Response()) as http:
                result=await provider.generate(GenerationRequest('request-1','Scene',diagnostics=trace),CancellationToken(),config())
            trace.finish();store.flush()
            self.assertEqual(http.call_count,1)
            identity=result.provenance['attempt_id']
            saved=json.loads((root/'private'/f'{identity}.json').read_text())
            self.assertEqual(saved['execution_id'],trace.execution_id)
            self.assertTrue((root/'private/dispatches'/f'{identity}.json').is_file())
            self.assertEqual(saved['usage']['output_tokens'],20)
            self.assertNotIn('secret-example',json.dumps(saved))


class DiagnosticsProductTests(unittest.TestCase):
    def test_input_save_failure_returns_coded_http_error_and_preserves_input(self):
        first=self.send();app=self.workflow._application
        old=app._project_store.path.read_bytes();prepared=app._prepared;epoch=app._epoch
        with patch.object(app._project_store,'save',side_effect=OSError('TEST INPUT DISK FAILURE')):
            status,body,_=self.request('/v1/product/conversation',self.answer(first),headers=self.product_headers)
        self.assertEqual(status,503);self.assertEqual(body['error']['code'],'input_persistence_failed')
        self.assertEqual(old,app._project_store.path.read_bytes());self.assertIs(app._prepared,prepared)
        self.assertEqual(app._epoch,epoch+1);self.assertFalse(self.workflow.has_active_generation())
        app.diagnostics.flush();detail=app.diagnostics.detail(app.last_execution_id)
        self.assertEqual(detail['status'],'failed');self.assertEqual(detail['first_error']['stage'],'input_project_save')

    def test_mandatory_generation_save_failure_keeps_memory_but_blocks_ack_and_preview(self):
        from twinpulse_app import BrokerError
        self.use_room_gateway();first=self.send();app=self.workflow._application
        old=[];original_save=app._project_store.save
        def fail_generated_commit(record):
            if record.site_draft is not None:
                old.append(app._project_store.path.read_bytes())
                raise OSError('TEST COMMIT FAILURE')
            return original_save(record)
        with patch.object(app._project_store,'save',side_effect=fail_generated_commit):
            self.call(self.answer(first))
            for _ in range(100):
                if self.call()['generation']['state']!='running':break
                time.sleep(.02)
        state=self.workflow.snapshot();app.diagnostics.flush()
        self.assertEqual(state['error']['code'],'project_persistence_failed')
        self.assertIsNotNone(state['site_draft']);self.assertEqual(old[0],app._project_store.path.read_bytes())
        for action in (lambda:self.workflow.acknowledge(state['site_draft']['revision']),self.workflow.simulation_preview):
            with self.assertRaises(BrokerError) as rejected:action()
            self.assertEqual(rejected.exception.code,'project_persistence_failed')
        self.assertFalse(self.broker.has_pending_operations())
        detail=app.diagnostics.detail(app.last_execution_id)
        self.assertEqual(detail['status'],'failed');self.assertEqual(detail['first_error']['stage'],'project_save')

    def test_committed_edit_and_undo_reopen_exact_origin_without_dispatch_or_original_changes(self):
        from twinpulse_app import ApplicationService,CommandBroker,ProductWorkflow
        from twinpulse_core import canonical_sha256
        self.use_room_gateway();self.call(self.answer(self.send()))
        for _ in range(100):
            if not self.workflow.has_active_generation():break
            time.sleep(.02)
        app=self.workflow._application;record=app.site_draft
        original=app._project_store.path.read_bytes()
        bed=next(c for c in self.workflow.snapshot()['site_draft']['editable_calls']
                 if c['tool']=='place_furniture' and c['arguments']['kind']=='bed')
        moved={**bed,'arguments':{**bed['arguments'],'center_m':[-.8,.8]}}
        for mode,operation in (('change','move-reopen'),('undo','undo-reopen')):
            preview=self.workflow.preview_scene_edit(operation_id=operation,mode=mode,
                target_call_id=bed['call_id'] if mode=='change' else None,
                tool_call=moved if mode=='change' else None)
            self.workflow.apply_scene_edit(preview['operation'],preview['preview_digest'])
            app.diagnostics.flush()
            edited=self.workflow.snapshot()['site_draft']
            history=app.scene_change_store().load();history_bytes=app.scene_change_store().path.read_bytes()
            origin=self.broker._diagnostic_artifacts[edited['artifact_id']]['scene_edit_execution_id']
            broker=CommandBroker()
            restored=ApplicationService(app._generation_gateway,project_store=app._project_store,artifact_store=app._artifact_store)
            workflow=ProductWorkflow(restored,broker,mode='explicit_fixture',generation_settings_getter=lambda:{})
            state=workflow.resume_saved_scene('default',record.site.scene.revision,record.input_revision.digest)
            refs=broker._diagnostic_artifacts[state['site_draft']['artifact_id']]
            self.assertEqual(refs['scene_edit_execution_id'],origin)
            self.assertEqual(refs['scene_change_sha256'],canonical_sha256(history.to_dict()))
            self.assertEqual(refs['scene_edit_revision'],edited['revision'])
            self.assertEqual(refs['evidence_id'],app.last_execution_id)
            self.assertIsNone(state['acknowledged_revision']);self.assertFalse(broker.has_pending_operations())
            self.assertEqual(original,app._project_store.path.read_bytes())
            self.assertEqual(history_bytes,app.scene_change_store().path.read_bytes())

    def test_edit_storage_failure_and_post_commit_registration_failure_are_distinct(self):
        from twinpulse_app.command_broker import BrokerError
        self.use_room_gateway();self.call(self.answer(self.send()))
        for _ in range(100):
            if not self.workflow.has_active_generation() and self.call()['generation']['state']!='running':break
            time.sleep(.02)
        store=self.workflow._application.diagnostics
        raw=self.workflow._application._project_store.path.read_bytes()
        state=self.workflow.snapshot()
        bed=next(c for c in state['site_draft']['editable_calls'] if c['tool']=='place_furniture' and c['arguments']['kind']=='bed')
        moved={**bed,'arguments':{**bed['arguments'],'center_m':[-.8,.8]}}
        preview=self.workflow.preview_scene_edit(operation_id='storage-fail',mode='change',target_call_id=bed['call_id'],tool_call=moved)
        with patch('twinpulse_app.scene_changes.SceneChangeStore.apply',side_effect=OSError('PRIVATE DISK PATH')):
            with self.assertRaises(BrokerError):self.workflow.apply_scene_edit(preview['operation'],preview['preview_digest'])
        self.assertEqual(state['site_draft']['revision'],self.workflow.snapshot()['site_draft']['revision'])
        with patch.object(self.workflow,'_register_scene_change',side_effect=ValueError('PRIVATE REGISTER')):
            with self.assertRaises(BrokerError) as failed:self.workflow.apply_scene_edit(preview['operation'],preview['preview_digest'])
        self.assertEqual(failed.exception.code,'scene_edit_saved_review_unavailable')
        self.assertIsNone(self.workflow._site_artifact)
        store.flush()
        failures=[store.detail(e['execution_id']) for e in store.list()['executions'] if e['stage']=='scene_edit_apply']
        self.assertEqual({d['first_error']['stage'] for d in failures},
            {'scene_edit_validate_and_save','scene_edit_register_review'})
        self.assertTrue(all(d['status']=='failed' for d in failures))
        self.assertNotIn('PRIVATE',json.dumps(failures))
        self.assertEqual(raw,self.workflow._application._project_store.path.read_bytes())
        self.assertFalse(self.broker.has_pending_operations())

        # A new process can register the committed history while retaining the
        # failed registration origin; it must not turn the old trace into PASS.
        from twinpulse_app import ApplicationService,CommandBroker,ProductWorkflow
        app=self.workflow._application;record=app.site_draft
        broker=CommandBroker()
        restored=ApplicationService(app._generation_gateway,project_store=app._project_store,artifact_store=app._artifact_store)
        workflow=ProductWorkflow(restored,broker,mode='explicit_fixture',generation_settings_getter=lambda:{})
        reopened=workflow.resume_saved_scene('default',record.site.scene.revision,record.input_revision.digest)
        origin=broker._diagnostic_artifacts[reopened['site_draft']['artifact_id']]['scene_edit_execution_id']
        previous=restored.diagnostics.detail(origin)
        self.assertEqual(previous['status'],'failed')
        self.assertEqual(previous['first_error']['stage'],'scene_edit_register_review')
        self.assertIsNone(reopened['acknowledged_revision']);self.assertFalse(broker.has_pending_operations())

    def test_optional_edit_binding_failure_does_not_undo_commit_or_hide_degradation(self):
        self.use_room_gateway();self.call(self.answer(self.send()))
        for _ in range(100):
            if not self.workflow.has_active_generation():break
            time.sleep(.02)
        app=self.workflow._application;original=app._project_store.path.read_bytes()
        bed=next(c for c in self.workflow.snapshot()['site_draft']['editable_calls']
                 if c['tool']=='place_furniture' and c['arguments']['kind']=='bed')
        moved={**bed,'arguments':{**bed['arguments'],'center_m':[-.8,.8]}}
        preview=self.workflow.preview_scene_edit(operation_id='missing-link',mode='change',target_call_id=bed['call_id'],tool_call=moved)
        with patch.object(app.diagnostics,'_link_directory',side_effect=OSError('PRIVATE LINK DISK')):
            result=self.workflow.apply_scene_edit(preview['operation'],preview['preview_digest'])
        app.diagnostics.flush()
        self.assertEqual(result['site_draft']['scene_edit_count'],1)
        self.assertIsNone(result['acknowledged_revision']);self.assertFalse(self.broker.has_pending_operations())
        self.assertEqual(original,app._project_store.path.read_bytes())
        self.assertTrue(app.diagnostics.health['diagnostics_degraded'])
        self.assertNotIn('PRIVATE',json.dumps(app.diagnostics.list()))

    def test_real_saved_generation_reopens_with_origin_without_any_dispatch(self):
        from twinpulse_app import ApplicationService,CommandBroker,ProductWorkflow
        self.use_room_gateway();self.call(self.answer(self.send()))
        for _ in range(100):
            if self.call()['generation']['state']!='running':break
            time.sleep(.02)
        old=self.workflow._application;old.diagnostics.flush()
        for _ in range(100):
            if not self.workflow.has_active_generation():break
            time.sleep(.01)
        record=old.site_draft;raw=old._project_store.path.read_bytes()
        origin=old.last_execution_id
        broker=CommandBroker()
        restored=ApplicationService(old._generation_gateway,project_store=old._project_store,artifact_store=old._artifact_store)
        workflow=ProductWorkflow(restored,broker,mode='explicit_fixture',generation_settings_getter=lambda:{})
        state=workflow.resume_saved_scene('default',record.site.scene.revision,record.input_revision.digest)
        refs=broker._diagnostic_artifacts[state['site_draft']['artifact_id']]
        self.assertEqual(refs['evidence_id'],origin)
        self.assertFalse(broker.has_pending_operations())
        self.assertIsNone(state['acknowledged_revision'])
        self.assertEqual(raw,old._project_store.path.read_bytes())
        restored.diagnostics.flush()

    def test_edit_preview_apply_undo_and_rejected_proposal_preserve_original_and_failure(self):
        from twinpulse_app.command_broker import BrokerError
        self.use_room_gateway();self.call(self.answer(self.send()))
        for _ in range(100):
            if self.call()['generation']['state']!='running':break
            time.sleep(.02)
        for _ in range(100):
            if not self.workflow.has_active_generation():break
            time.sleep(.01)
        state=self.workflow.snapshot();original=self.workflow._application._project_store.path.read_bytes()
        bed=next(c for c in state['site_draft']['editable_calls'] if c['tool']=='place_furniture' and c['arguments']['kind']=='bed')
        moved={**bed,'arguments':{**bed['arguments'],'center_m':[-.8,.8]}}
        preview=self.workflow.preview_scene_edit(operation_id='move-bed',mode='change',target_call_id=bed['call_id'],tool_call=moved)
        self.workflow.apply_scene_edit(preview['operation'],preview['preview_digest'])
        undo=self.workflow.preview_scene_edit(operation_id='undo-bed',mode='undo',target_call_id=None,tool_call=None)
        self.workflow.apply_scene_edit(undo['operation'],undo['preview_digest'])
        with self.assertRaises(BrokerError):
            self.workflow.preview_scene_edit_proposal(operation_id='bad',request_text='PRIVATE PROMPT',
                selected_call_id=bed['call_id'],expected_revision='bad',proposal={})
        store=self.workflow._application.diagnostics;store.flush()
        executions=store.list()['executions'];stages={e['stage'] for e in executions}
        self.assertTrue({'scene_edit_preview','scene_edit_apply','scene_edit_undo','scene_edit_proposal'}<=stages)
        failed=next(e for e in executions if e['stage']=='scene_edit_proposal')
        self.assertEqual(failed['status'],'failed')
        self.assertEqual(failed['first_error']['error_code'],'scene_edit_proposal_stale')
        self.assertNotIn('PRIVATE',json.dumps(store.detail(failed['execution_id'])))
        self.assertEqual(original,self.workflow._application._project_store.path.read_bytes())
        self.assertFalse(self.broker.has_pending_operations())

    setUp = ChatConversationTests.setUp
    tearDown = ChatConversationTests.tearDown
    request = ChatConversationTests.request
    product_headers = R5ProductApiTests.product_headers
    call = ChatConversationTests.call
    send = ChatConversationTests.send
    answer = ChatConversationTests.answer
    use_room_gateway = ChatConversationTests.use_room_gateway

    def test_chat_text_generation_same_id_through_archive_validation_save_and_api(self):
        self.use_room_gateway()
        self.workflow._application._profile_generation = True
        first = self.send()
        answer = self.answer(first)
        self.call(answer)
        for _ in range(100):
            state = self.call()
            if state['generation']['state'] != 'running': break
            time.sleep(.02)
        self.assertEqual(state['generation']['state'], 'completed', state)
        store = self.workflow._application.diagnostics
        store.flush()
        status, result, _ = self.request('/v1/product/diagnostics', headers=self.product_headers)
        self.assertEqual(status, 200)
        self.assertEqual(len(result['executions']), 1)
        execution = result['executions'][0]
        identity = execution['execution_id']
        self.assertEqual(execution['status'], 'succeeded')
        self.assertEqual(execution['metadata']['workflow_id'], state['session_id'])
        self.assertEqual(execution['metadata']['operation_id'], state['generation']['operation_id'])
        self.assertEqual(execution['metadata']['generation_id'], state['generation']['generation_id'])
        status, detail, _ = self.request('/v1/product/diagnostics/' + identity, headers=self.product_headers)
        self.assertEqual(status, 200)
        stages = {s['stage'] for s in detail['spans']}
        self.assertTrue({'scene_generation','application_generation','input_archive','provider_generation','site_validation_compile','project_save'} <= stages)
        self.assertTrue(any(e['type']=='profile_row' for e in detail['events']))
        saved = self.workflow._application.site_draft.to_dict()
        self.call(answer)  # Idempotent answer must not create another execution.
        self.request('/v1/product/diagnostics/' + identity + '/export', headers=self.product_headers)
        self.assertEqual(len(store.list()['executions']), 1)
        self.assertEqual(saved, self.workflow._application.site_draft.to_dict())
        self.assertFalse(self.broker.has_pending_operations())

    def test_diagnostics_requires_authentication_and_never_dispatches(self):
        trace = self.workflow._application.diagnostics.begin('saved_fixture'); trace.finish()
        self.workflow._application.diagnostics.flush()
        status, _, _ = self.request('/v1/product/diagnostics')
        self.assertEqual(status, 401)
        for path in ('/v1/product/diagnostics', '/v1/product/diagnostics/' + trace.execution_id,
                     '/v1/product/diagnostics/' + trace.execution_id + '/export',
                     '/v1/product/diagnostics/' + trace.execution_id + '/graph'):
            self.assertEqual(self.request(path)[0], 401)
            self.assertEqual(self.request(path, headers=self.product_headers)[0], 200)
        path='/v1/product/diagnostics/'+trace.execution_id+'/graph'
        self.assertEqual(self.request(path+'?project_id=other',headers=self.product_headers)[0],400)
        self.assertEqual(self.request('/v1/product/diagnostics/'+'a'*32+'/graph',headers=self.product_headers)[0],404)
        self.assertEqual(self.request('/v1/product/diagnostics/'+'a'*32, headers=self.product_headers)[0], 404)
        self.assertFalse(self.broker.has_pending_operations())

    def test_authenticated_diagnostic_query_pages_validate_scope_and_never_dispatch(self):
        from urllib.parse import urlencode
        store=self.workflow._application.diagnostics
        traces=[store.begin('api_page',request_id='request-matching') for _ in range(3)]
        for trace in traces:trace.finish('failed')
        store.flush()
        query=dict(limit=1,q='request-matching',status='failed')
        path='/v1/product/diagnostics?'+urlencode(query)
        self.assertEqual(self.request(path)[0],401)
        code,first,_=self.request(path,headers=self.product_headers)
        self.assertEqual(code,200);self.assertEqual(len(first['executions']),1)
        code,second,_=self.request(path+'&'+urlencode(dict(cursor=first['next_cursor'])),headers=self.product_headers)
        self.assertEqual(code,200)
        self.assertNotEqual(first['executions'][0]['execution_id'],second['executions'][0]['execution_id'])
        for bad in ('limit=0','q=%3Cscript%3E','limit=1&limit=2','project_id=other','cursor=..%2Fprivate','limit=abc'):
            code,value,_=self.request('/v1/product/diagnostics?'+bad,headers=self.product_headers)
            self.assertEqual(code,400);self.assertEqual(value['error']['code'],'diagnostic_query_invalid')
        self.assertEqual(self.request('/v1/product/state?query=forbidden',headers=self.product_headers)[0],400)
        self.assertEqual(self.request('/v1/product/diagnostics?limit=1',body={},headers=self.product_headers)[0],400)
        self.assertFalse(self.broker.has_pending_operations())

    def test_diagnostic_storage_failure_is_not_misreported_as_invalid_search(self):
        store=self.workflow._application.diagnostics
        for failure in (OSError('PRIVATE path'),ValueError('PRIVATE linked location')):
            with patch.object(store,'list',side_effect=failure):
                code,value,_=self.request('/v1/product/diagnostics?q=mission',headers=self.product_headers)
            self.assertEqual(code,503);self.assertEqual(value['error']['code'],'diagnostics_unavailable')
            self.assertNotIn('PRIVATE',json.dumps(value))
        self.assertFalse(self.broker.has_pending_operations())

    def test_provider_failure_is_persistent_not_a_success(self):
        class Failed:
            def cancel_active(self): pass
            async def generate(self, request): raise ValueError('PRIVATE prompt / token')
        self.workflow._application.set_generation_gateway(Failed())
        self.call(self.answer(self.send()))
        for _ in range(100):
            state = self.call()
            if state['generation']['state'] != 'running': break
            time.sleep(.02)
        self.assertEqual(state['generation']['state'], 'failed')
        store = self.workflow._application.diagnostics; store.flush()
        execution = store.list()['executions'][0]
        self.assertEqual(execution['status'], 'failed')
        self.assertEqual(execution['first_error']['error_type'], 'ValueError')
        self.assertNotIn('PRIVATE', json.dumps(store.detail(execution['execution_id'])))


class ParallelProjectDiagnosticsTests(unittest.TestCase):
    def test_two_authenticated_project_journeys_keep_same_request_ids_scoped_after_reopen(self):
        from concurrent.futures import ThreadPoolExecutor
        from types import SimpleNamespace
        from twinpulse_app import ApplicationService,CommandBroker,LocalApiServer,ProductWorkflow,ProjectStore
        from twinpulse_app.project_catalog import ProjectCatalog
        from twinpulse_core import InputArtifactStore
        from twinpulse_provider import SiteGenerationResult
        from tests.integration.test_scene_changes import furnished_source
        class Gateway:
            def cancel_active(self):pass
            async def generate(self,request):
                await asyncio.sleep(.1)
                return SiteGenerationResult(request.request_id,'explicit-parallel-fixture','fixture',len(request.images),furnished_source().plan)
        with TemporaryDirectory() as temporary:
            root=Path(temporary);servers=[];contexts=[]
            try:
                for index,project in enumerate(('parallel-a','parallel-b')):
                    ProjectCatalog(root,'default').create_empty(project)
                    store=ProjectStore.for_project(root,project)
                    app=ApplicationService(Gateway(),project_store=store,artifact_store=InputArtifactStore(store.input_root()),project_id=project)
                    broker=CommandBroker(project_id=project)
                    workflow=ProductWorkflow(app,broker,mode='explicit_fixture',generation_settings_getter=lambda:{'model_id':'explicit-parallel-fixture'},provider_state_getter=lambda:{'configured':True})
                    secret=chr(97+index)*43
                    server=LocalApiServer(broker,product_bootstrap_secret=secret,engine_bootstrap_secret='e'*43,product_workflow=workflow)
                    server.start();servers.append(server);holder=SimpleNamespace(server=server)
                    code,bootstrap,headers=R5ProductApiTests.request(holder,'/v1/bootstrap',{'role':'product','secret':secret})
                    self.assertEqual(code,200)
                    auth={'Cookie':headers.get('Set-Cookie').split(';',1)[0],'X-TwinPulse-CSRF':bootstrap['csrf_token']}
                    contexts.append((project,app,broker,workflow,holder,auth))
                def journey(context):
                    project,app,broker,workflow,holder,auth=context
                    def call(body=None):
                        code,value,_=R5ProductApiTests.request(holder,'/v1/product/conversation',body,headers=auth)
                        self.assertEqual(code,200,value);return value
                    first=call({'action':'message','request_id':'same-message','text':'Create a bedroom','mode':'new','attachment':None})
                    card=first['cards'][-1]
                    answer={'action':'answer','request_id':'same-answer','card_id':card['id'],'choice_id':'sim','expected_session_revision':card['expected_session_revision']}
                    call(answer)
                    deadline=time.monotonic()+5
                    while time.monotonic()<deadline:
                        state=call()
                        if state['generation']['state']!='running':break
                        time.sleep(.02)
                    self.assertEqual(state['generation']['state'],'completed',state)
                    call(answer);self.assertTrue(app.diagnostics.flush())
                    code,listed,_=R5ProductApiTests.request(holder,'/v1/product/diagnostics',headers=auth)
                    self.assertEqual(code,200);self.assertEqual(len(listed['executions']),1)
                    execution=listed['executions'][0]
                    self.assertEqual(execution['status'],'succeeded');self.assertEqual(listed['project_id'],project)
                    self.assertEqual(execution['metadata']['workflow_id'],state['session_id'])
                    self.assertFalse(broker.has_pending_operations());return execution['execution_id']
                with ThreadPoolExecutor(2) as pool:identities=list(pool.map(journey,contexts))
                self.assertNotEqual(*identities)
                for index,context in enumerate(contexts):
                    project,app,broker,workflow,holder,auth=context;identity=identities[index];other=identities[1-index]
                    for suffix in ('','/export','/graph'):
                        self.assertEqual(R5ProductApiTests.request(holder,f'/v1/product/diagnostics/{identity}{suffix}',headers=auth)[0],200)
                        self.assertEqual(R5ProductApiTests.request(holder,f'/v1/product/diagnostics/{other}{suffix}',headers=auth)[0],404)
                    self.assertEqual(R5ProductApiTests.request(holder,'/v1/product/diagnostics',headers=contexts[1-index][-1])[0],401)
                    before=app._project_store.path.read_bytes()
                    restored=ApplicationService(Gateway(),project_store=ProjectStore.for_project(root,project),project_id=project)
                    self.assertEqual(restored.diagnostics.detail(identity)['status'],'succeeded')
                    self.assertEqual(restored.site_draft.to_dict(),app.site_draft.to_dict())
                    self.assertEqual(app._project_store.path.read_bytes(),before)
                    self.assertEqual(restored.diagnostics.list()['project_id'],project)
            finally:
                for server in servers:server.stop()
                for context in contexts:context[1].diagnostics.flush()


class BrokerTraceTests(unittest.TestCase):
    def test_failed_apply_has_exact_command_diagnosis_and_no_frame_success(self):
        from twinpulse_core import CommandReceipt, fixed_warehouse_bundle
        broker,values,_=self.runtime_fixture()
        artifact=broker.register_artifact('apply-fault',fixed_warehouse_bundle())
        operation=broker.submit('owner',dict(client_request_id='failed-build',command_type='build_scene',
            artifact_id=artifact.artifact_id,expected_applied_revision=artifact.revision))
        command=broker.claim('engine-1','stage-1')
        broker.record_receipt(CommandReceipt(command.command_id,'build_scene','default','engine-1','stage-1',
            'failed',error_code='RuntimeError',message='SIM_TEST_APPLY_FAILED'))
        view=broker.public_state('owner')['build_view'];self.store.flush()
        self.assertEqual(view['phase'],'apply');self.assertEqual(view['status'],'failed')
        self.assertEqual(view['error_code'],'RuntimeError');self.assertEqual(view['execution_id'],operation['execution_id'])
        self.assertEqual(self.store.detail(view['execution_id'])['status'],'failed')
        broker.record_current_frame('engine-1','stage-1',artifact.revision,10,'c'*64)
        self.assertEqual(broker.public_state('owner')['build_view'],view)

    def test_first_frame_deadline_preserves_apply_success_and_links_one_failed_observation(self):
        broker,values,_=self.runtime_fixture()
        build=broker.public_state('owner')['operations'][0]
        self.assertEqual(broker.public_state('owner')['build_view']['status'],'waiting')
        broker._clock.advance(15);broker.engine_heartbeat('engine-1','stage-1')
        state=broker.public_state('owner');view=state['build_view'];self.store.flush()
        self.assertEqual(view['status'],'failed');self.assertEqual(view['error_code'],'first_current_frame_timeout')
        detail=self.store.detail(view['execution_id'])
        self.assertEqual(detail['status'],'failed')
        self.assertEqual(detail['first_error']['stage'],'first_current_frame_deadline')
        self.assertEqual(detail['manifest']['metadata']['command_execution_id'],build['execution_id'])
        self.assertEqual(self.store.detail(build['execution_id'])['status'],'succeeded')
        self.assertEqual(state['operations'][0]['receipt']['status'],'succeeded')
        span=next(s for s in detail['spans'] if s['stage']=='first_current_frame_deadline')
        self.assertEqual(span['metadata']['elapsed_s'],15.)
        for _ in range(3):self.assertEqual(broker.public_state('owner')['build_view'],view)
        self.assertEqual(len([r for r in self.store.list()['executions'] if r['stage']=='engine_view_observation']),1)
        # A rejected/mismatched frame cannot clear this fault. A later accepted
        # current frame may restore display without rewriting the failed history.
        broker.record_current_frame('engine-1','stage-1','f'*64,9,'b'*64)
        self.assertEqual(broker.public_state('owner')['build_view']['status'],'failed')
        broker.record_current_frame('engine-1','stage-1',values['applied_revision'],10,'c'*64)
        self.assertEqual(broker.public_state('owner')['build_view']['status'],'succeeded')
        self.assertIsNone(broker.public_state('owner')['build_view']['error_code'])
        self.assertEqual(self.store.detail(view['execution_id'])['status'],'failed')

    def test_frame_wait_disconnect_and_replacement_are_unknown_not_apply_failure(self):
        broker,values,_=self.runtime_fixture();broker._clock.advance(4)
        view=broker.public_state('owner')['build_view'];self.store.flush()
        self.assertEqual(view['status'],'unknown');self.assertEqual(view['error_code'],'engine_disconnected')
        self.assertEqual(self.store.detail(view['execution_id'])['status'],'unknown')
        broker.register_engine('engine-2','stage-2')
        broker.record_current_frame('engine-1','stage-1',values['applied_revision'],10,'c'*64)
        self.assertIsNone(broker.public_state('owner')['build_view'])

    def test_frame_before_receipt_counts_only_after_current_build_claim(self):
        from twinpulse_app import CommandBroker
        from twinpulse_core import fixed_warehouse_bundle,CommandReceipt
        from tests.integration.test_r4_bridge_api import FakeClock
        broker=CommandBroker(clock=FakeClock());broker.diagnostics=self.store
        broker.register_engine('engine-1','stage-1');broker.acquire_lease('owner')
        artifact=broker.register_artifact('fixed',fixed_warehouse_bundle())
        for index in (1,2):
            op=broker.submit('owner',dict(client_request_id=f'build-{index}',command_type='build_scene',
                artifact_id='fixed',expected_applied_revision=artifact.revision))
            broker.record_current_frame('engine-1','stage-1',artifact.revision,index,'b'*64)
            command=broker.claim('engine-1','stage-1')
            if index==1:broker.record_current_frame('engine-1','stage-1',artifact.revision,3,'b'*64)
            broker.record_receipt(CommandReceipt(command.command_id,'build_scene','default','engine-1','stage-1',
                'succeeded',applied_revision=artifact.revision,build_fingerprint='b'*64))
            self.assertEqual(broker.public_state('owner')['build_view']['status'],'succeeded' if index==1 else 'waiting')
        broker.record_current_frame('engine-1','stage-1',artifact.revision,4,'b'*64)
        self.assertEqual(broker.public_state('owner')['build_view']['status'],'succeeded')
        self.store.flush();detail=self.store.detail(op['execution_id'])
        self.assertEqual(next(s for s in detail['spans'] if s['stage']=='first_current_frame_after_receipt')['status'],'succeeded')
        self.assertFalse(any(r['stage']=='engine_view_observation' for r in self.store.list()['executions']))

    def test_optional_view_diagnostics_failure_never_changes_frame_or_receipt(self):
        broker,values,_=self.runtime_fixture()
        broker._clock.advance(15);broker.engine_heartbeat('engine-1','stage-1')
        with patch.object(self.store,'begin',side_effect=OSError('PRIVATE credential disk failure')):
            view=broker.public_state('owner')['build_view']
        self.assertEqual(view['status'],'failed');self.assertIsNone(view['execution_id'])
        self.assertTrue(self.store.health['diagnostics_degraded'])
        broker.record_current_frame('engine-1','stage-1',values['applied_revision'],5,'b'*64)
        self.assertEqual(broker.public_state('owner')['build_view']['status'],'succeeded')
        self.assertNotIn('PRIVATE',json.dumps(broker.public_state('owner')))

    def runtime_fixture(self):
        from twinpulse_app import CommandBroker
        from twinpulse_core import fixed_warehouse_bundle, CommandReceipt, SimulationSnapshot
        from tests.integration.test_r4_bridge_api import FakeClock
        broker=CommandBroker(clock=FakeClock());broker.diagnostics=self.store
        broker.register_engine('engine-1','stage-1');broker.acquire_lease('owner')
        artifact=broker.register_artifact('fixed',fixed_warehouse_bundle())
        broker.submit('owner',dict(client_request_id='build',command_type='build_scene',artifact_id='fixed',
            expected_applied_revision=artifact.revision))
        command=broker.claim('engine-1','stage-1')
        broker.record_receipt(CommandReceipt(command.command_id,'build_scene','default','engine-1','stage-1',
            'succeeded',applied_revision=artifact.revision,build_fingerprint='b'*64))
        values=dict(engine_session_id='engine-1',stage_epoch='stage-1',project_id='default',
            applied_revision=artifact.revision,run_id=None,sequence=1,runtime_state='built',safety_state=None,
            safety_reason=None,permitted_commands=('run','reset','get_state'),capabilities=('simulation',),telemetry_available=False)
        broker.record_snapshot(SimulationSnapshot(**values))
        op=broker.submit('owner',dict(client_request_id='run',command_type='run',expected_applied_revision=artifact.revision))
        command=broker.claim('engine-1','stage-1')
        broker.record_receipt(CommandReceipt(command.command_id,'run','default','engine-1','stage-1','succeeded'))
        return broker,values,op

    def test_runtime_primary_cleanup_fault_links_command_success_without_rewriting_receipt(self):
        from twinpulse_core import SimulationSnapshot
        broker,values,op=self.runtime_fixture()
        values.update(sequence=2,runtime_state='error',safety_state='simulation_error',
            safety_reason='RuntimeError: SIM_TEST_POSE_LOST; cleanup: RuntimeError: SIM_TEST_CLEANUP_FAILED')
        broker.record_snapshot(SimulationSnapshot(**values));identity=broker.public_state('owner')['snapshot_execution_id']
        self.store.flush();detail=self.store.detail(identity)
        self.assertEqual(detail['status'],'failed')
        self.assertEqual(detail['first_error']['stage'],'engine_runtime_fault')
        self.assertEqual(detail['first_error']['error_code'],'SIM_TEST_POSE_LOST')
        self.assertEqual(detail['manifest']['metadata']['command_execution_id'],op['execution_id'])
        cleanup=next(s for s in detail['spans'] if s['stage']=='engine_runtime_cleanup')
        self.assertEqual(cleanup['metadata']['role'],'cleanup')
        self.assertEqual(cleanup['metadata']['error_code'],'SIM_TEST_CLEANUP_FAILED')
        self.assertEqual(self.store.detail(op['execution_id'])['status'],'succeeded')
        self.assertEqual(broker.public_state('owner')['operations'][-1]['status'],'succeeded')
        for sequence in (3,4):
            if sequence==4:values['safety_reason']='RuntimeError: PRIVATE_SECRET'
            values['sequence']=sequence;broker.record_snapshot(SimulationSnapshot(**values))
            self.assertEqual(broker.public_state('owner')['snapshot_execution_id'],identity)
        self.store.flush()
        self.assertEqual(len([r for r in self.store.list()['executions'] if r['stage']=='engine_runtime_observation']),1)
        values.update(sequence=5,runtime_state='paused',safety_state=None,safety_reason=None)
        broker.record_snapshot(SimulationSnapshot(**values))
        self.assertIsNone(broker.public_state('owner')['snapshot_execution_id'])
        broker.register_engine('engine-2','stage-2')
        self.assertIsNone(broker.public_state('owner')['snapshot_execution_id'])

    def test_runtime_fault_cannot_attach_to_mismatched_revision_and_never_exports_exception_prose(self):
        from twinpulse_core import SimulationSnapshot
        broker,values,op=self.runtime_fixture()
        values.update(sequence=2,applied_revision='f'*64,runtime_state='error',safety_state='simulation_error',
            safety_reason='RuntimeError: PRIVATE_CREDENTIAL path /x; cleanup: OSError: PRIVATE_TOKEN secret')
        broker.record_snapshot(SimulationSnapshot(**values));self.store.flush()
        detail=self.store.detail(broker.public_state('owner')['snapshot_execution_id'])
        self.assertNotIn('command_execution_id',detail['manifest']['metadata'])
        self.assertEqual(detail['first_error']['error_code'],'engine_runtime_fault')
        self.assertNotIn('PRIVATE',json.dumps(self.store.export(detail['manifest']['execution_id'])))
        self.assertEqual(self.store.detail(op['execution_id'])['status'],'succeeded')
        broker._clock.advance(4)
        self.assertIsNone(broker.public_state('owner')['snapshot_execution_id'])

    def test_stage_invalid_fault_uses_only_previous_same_epoch_revision_and_optional_sink_cannot_reject_snapshot(self):
        from twinpulse_core import SimulationSnapshot
        broker,values,op=self.runtime_fixture()
        values.update(sequence=2,applied_revision=None,run_id=None,runtime_state='stage_invalid',
            safety_reason='Stage changed or geometry mismatched')
        broker.record_snapshot(SimulationSnapshot(**values));self.store.flush()
        detail=self.store.detail(broker.public_state('owner')['snapshot_execution_id'])
        self.assertEqual(detail['manifest']['metadata']['command_execution_id'],op['execution_id'])
        broker.register_engine('engine-2','stage-2')
        values.update(engine_session_id='engine-2',stage_epoch='stage-2',sequence=1)
        with patch.object(self.store,'begin',side_effect=OSError('PRIVATE disk full')):
            broker.record_snapshot(SimulationSnapshot(**values))
        state=broker.public_state('owner')
        self.assertEqual(state['snapshot']['runtime_state'],'stage_invalid')
        self.assertIsNone(state['snapshot_execution_id']);self.assertTrue(self.store.health['diagnostics_degraded'])
        values['sequence']=2;broker.record_snapshot(SimulationSnapshot(**values))
        self.assertIsNone(broker.public_state('owner')['snapshot_execution_id'])  # No repeated sink retries per sample.

    def test_restored_reference_keys_do_not_collide_with_new_command_identity(self):
        from twinpulse_app import CommandBroker
        from twinpulse_core import fixed_warehouse_bundle
        from tests.integration.test_r4_bridge_api import FakeClock
        broker=CommandBroker(clock=FakeClock());broker.diagnostics=self.store
        broker.register_engine('engine-1','stage-1');broker.acquire_lease('owner')
        artifact=broker.register_artifact('restored',fixed_warehouse_bundle())
        broker.bind_artifact_diagnostics('restored',request_id='original-generation',draft_revision='a'*64,
            evidence_id='b'*32,evidence_kind='generation_execution',scene_edit_execution_id='c'*32)
        value=dict(client_request_id='new-build',command_type='build_scene',artifact_id='restored',
                   expected_applied_revision=artifact.revision)
        operation=broker.submit('owner',value)
        self.assertEqual(broker.submit('owner',value),operation)
        self.store.flush();refs=self.store.detail(operation['execution_id'])['manifest']['metadata']
        self.assertEqual(refs['request_id'],'new-build');self.assertEqual(refs['draft_revision'],artifact.revision)
        self.assertEqual(refs['evidence_id'],'b'*32);self.assertEqual(refs['scene_edit_execution_id'],'c'*32)
        self.assertEqual(refs['command_id'],operation['command_id'])

    setUp=ExecutionStoreTests.setUp
    tearDown=ExecutionStoreTests.tearDown
    def test_same_plan_repeated_run_distinct_execution_and_dedup_same_execution(self):
        from twinpulse_app import CommandBroker
        from twinpulse_core import fixed_warehouse_bundle, CommandReceipt, SimulationSnapshot
        from tests.integration.test_r4_bridge_api import FakeClock
        clock=FakeClock();broker=CommandBroker(clock=clock);broker.diagnostics=self.store
        broker.register_engine('engine-1','stage-1');broker.acquire_lease('owner')
        artifact=broker.register_artifact('fixed',fixed_warehouse_bundle())
        broker.bind_artifact_diagnostics('fixed',generation_id='generation-1',evidence_id='a'*32)
        value=dict(client_request_id='build',command_type='build_scene',artifact_id='fixed',expected_applied_revision=artifact.revision)
        first=broker.submit('owner',value);self.assertEqual(broker.submit('owner',value),first)
        command=broker.claim('engine-1','stage-1')
        self.assertNotIn('execution_id',command.to_dict())
        self.assertNotIn('diagnostics',command.payload)
        broker.record_receipt(CommandReceipt(command.command_id,'build_scene','default','engine-1','stage-1',
            'succeeded',applied_revision=artifact.revision,build_fingerprint='b'*64))
        broker.record_snapshot(SimulationSnapshot(engine_session_id='engine-1',stage_epoch='stage-1',project_id='default',
            applied_revision=artifact.revision,run_id=None,sequence=1,runtime_state='built',safety_state=None,safety_reason=None,
            permitted_commands=('run','reset','get_state'),capabilities=('simulation',),telemetry_available=False))
        identities=[]
        for number in range(2):
            value=dict(client_request_id=f'run-{number}',command_type='run',expected_applied_revision=artifact.revision)
            outcome=broker.submit('owner',value);identities.append(outcome['execution_id'])
            self.assertEqual(outcome,broker.submit('owner',value))
            command=broker.claim('engine-1','stage-1')
            receipt=CommandReceipt(command.command_id,'run','default','engine-1','stage-1','succeeded')
            timing=dict(clock_instance_id='c'*32,kit_queue_s=.15,adapter_execute_s=.04,receipt_queue_s=.08,dropped_receipts=0)
            broker.record_receipt(receipt,diagnostics=timing)
            broker.record_receipt(receipt,diagnostics=timing)  # Duplicate receipt never adds spans.
        self.store.flush()
        self.assertEqual(len(set(identities)),2)
        for identity in identities:
            result=self.store.detail(identity)
            self.assertEqual(result['status'],'succeeded')
            self.assertEqual(result['manifest']['metadata']['generation_id'],'generation-1')
            measured=[s for s in result['spans'] if s['metadata'].get('measurement_source')=='engine_local_elapsed']
            self.assertEqual(len(measured),3)
            self.assertEqual([s['metadata']['elapsed_s'] for s in measured],[.15,.04,.08])
            self.assertTrue(all(s['metadata']['reported_clock_instance_id']=='c'*32 for s in measured))
        self.assertEqual(len(self.store.list()['executions']),3)

    def test_engine_disconnect_retains_unknown_not_success(self):
        from twinpulse_app import CommandBroker
        from twinpulse_core import fixed_warehouse_bundle
        from tests.integration.test_r4_bridge_api import FakeClock
        clock=FakeClock();broker=CommandBroker(clock=clock);broker.diagnostics=self.store
        broker.register_engine('engine-1','stage-1');broker.acquire_lease('owner')
        artifact=broker.register_artifact('fixed',fixed_warehouse_bundle())
        outcome=broker.submit('owner',dict(client_request_id='build',command_type='build_scene',artifact_id='fixed',
                            expected_applied_revision=artifact.revision))
        broker.claim('engine-1','stage-1');clock.advance(4);broker.public_state('owner');self.store.flush()
        self.assertEqual(self.store.detail(outcome['execution_id'])['status'],'unknown')


class MissionTraceTests(unittest.TestCase):
    def test_parallel_robot_read_only_failure_does_not_replace_successful_generation(self):
        from tests.integration.test_chat_robot_preparation import ChatRobotTests
        fixture=ChatRobotTests();fixture.setUp()
        try:
            prep=fixture.attach(fault={'status':'SSH_OR_REMOTE_SETUP_FAILED','exit_code':255,'reason':'PRIVATE_PATH connection refused'})
            store=fixture.workflow._application.diagnostics;prep.execution_diagnostics=store
            fixture.start_real();state=fixture.wait('BLOCKED')
            for _ in range(100):
                state=fixture.call()
                if state['generation']['state']=='completed':break
                time.sleep(.01)
            self.assertEqual(state['generation']['state'],'completed')
            prep.thread.join(3);store.flush();records=store.list()['executions']
            self.assertEqual(len(records),2)
            check=next(row for row in records if row['stage']=='robot_read_only_preparation')
            generated=next(row for row in records if row['stage']=='scene_generation')
            self.assertEqual(check['status'],'failed');self.assertEqual(generated['status'],'succeeded')
            self.assertEqual(check['first_error']['error_code'],'SSH_CONNECTION_REFUSED')
            self.assertEqual(check['metadata']['workflow_id'],generated['metadata']['workflow_id'])
            self.assertNotEqual(check['execution_id'],generated['execution_id'])
            self.assertNotIn('PRIVATE_PATH',json.dumps(store.export(check['execution_id'])))
            self.assertEqual(fixture.controller.calls,[])
        finally:fixture.doCleanups()

    def test_stationary_collection_records_gaps_without_claiming_alignment_or_motion(self):
        from tests.integration.test_robot_readiness_app import receipt
        from twinpulse_app.robot_readiness import RobotReadiness
        with TemporaryDirectory() as td:
            root=Path(td);store=ExecutionStore(root/'diagnostics','default')
            for index,source_status in enumerate(('EVIDENCE_GAPS','NO_MOTION_COLLECTION_COMPLETE')):
                service=RobotReadiness(root,runner=lambda:(receipt(source_status),str(root/'report.json'),2 if index==0 else 0))
                service.execution_diagnostics=store
                job_id=f'{index+1:032x}'
                service.start('owner',job_id,True,time.time()*1000+1000);service._thread.join(3)
                original=service._state_path.read_bytes();store.flush()
                value=next(row for row in store.list()['executions'] if row['metadata']['request_id']==job_id)
                self.assertEqual(value['status'],'failed' if index==0 else 'succeeded')
                self.assertFalse(store.detail(value['execution_id'])['physical_authority'])
                self.assertFalse(service.snapshot('owner')['demo_ready'])
                self.assertEqual(original,service._state_path.read_bytes())
                service.close()

    def test_task_loop_groups_fresh_legs_without_changing_its_raw_journal(self):
        from tests.integration.test_goal_task_loop import LoopTests
        for fault in (None,'watchdog'):
            with self.subTest(fault=fault):
                fixture=LoopTests();fixture.setUp()
                try:
                    store=ExecutionStore(Path(fixture.temp.name)/'diagnostics','room')
                    fixture.nav.mission.diagnostics=store;fixture.fault=fault
                    fixture.start();job=fixture.finish()
                    digest=hashlib.sha256(fixture.loop.path.read_bytes()).hexdigest()
                    store.flush();summary=store.list()['executions'][0];detail=store.detail(summary['execution_id'])
                    self.assertEqual(detail['status'],'failed' if fault else 'cancelled')
                    self.assertEqual(detail['manifest']['metadata']['task_id'],job['task_id'])
                    legs=[s for s in detail['spans'] if s.get('stage')=='goal_task_leg']
                    self.assertEqual(len(legs),1 if fault else 3)
                    self.assertTrue(all('mission_id' in s['metadata'] for s in legs))
                    self.assertTrue(all(s['status']!='running' for s in legs))
                    if fault:self.assertEqual(detail['first_error']['error_code'],'INPUT_DEADLINE_EXPIRED')
                    self.assertEqual(digest,hashlib.sha256(fixture.loop.path.read_bytes()).hexdigest())
                finally:fixture.doCleanups()

    def test_existing_sensor_reactive_mission_and_cleanup_keep_raw_and_primary_cause(self):
        from tests.integration.test_automatic_mission_service import AutomaticMissionTests
        fixture=AutomaticMissionTests();fixture.setUp()
        try:
            store=ExecutionStore(fixture.root/'diagnostics','mission_room');fixture.service.diagnostics=store
            fixture.configure([0.,-.6,0.],fault='battery');factory=fixture.service.adapter_factory
            def broken_cleanup(*args):
                value=factory(*args)
                def close(): value.halt();raise ValueError('OWNED_SENSOR_STOP_UNCONFIRMED')
                value.close=close;return value
            fixture.service.adapter_factory=broken_cleanup
            fixture.service.start('owner',fixture.map_id,fixture.goal([.05,-.6]));job=fixture.finish()
            self.assertEqual(job['error'],'BATTERY_BUTTON_OR_SOURCE_AGE')
            path=fixture.root/'artifacts/automatic-mission/mission_room'/f"{job['job_id']}.json"
            before=hashlib.sha256(path.read_bytes()).hexdigest();store.flush()
            execution=store.list()['executions'][0];detail=store.detail(execution['execution_id'])
            self.assertEqual(detail['status'],'failed')
            self.assertEqual(detail['first_error']['error_code'],'BATTERY_BUTTON_OR_SOURCE_AGE')
            self.assertTrue(any(s['metadata'].get('error_code')=='OWNED_SENSOR_STOP_UNCONFIRMED' and
                                s['metadata'].get('role')=='cleanup' for s in detail['spans']))
            self.assertFalse(detail['physical_authority'])
            self.assertEqual(before,hashlib.sha256(path.read_bytes()).hexdigest())
        finally:fixture.doCleanups()

    def test_failed_robot_result_with_successful_cleanup_is_not_a_success(self):
        from twinpulse_app.physical_controller import PhysicalController
        with TemporaryDirectory() as td:
            store=ExecutionStore(Path(td)/'diagnostics','default')
            controller=PhysicalController(td,command=lambda *_:['unused-fake'])
            trace=store.begin('robot_operation_fixture');controller.state={'state':'FINISHED','result':'FAILED',
                'cleanup_confirmed':True,'reason':'INPUT_DEADLINE_EXPIRED'}
            with patch.object(controller,'_run_impl',return_value=None):controller._run(trace)
            store.flush();self.assertEqual(store.detail(trace.execution_id)['status'],'failed')
            self.assertEqual(store.detail(trace.execution_id)['first_error']['error_code'],'INPUT_DEADLINE_EXPIRED')
            controller.close()


if __name__ == '__main__': unittest.main()
