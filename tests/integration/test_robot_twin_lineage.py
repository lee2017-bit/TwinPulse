# SPDX-License-Identifier: Apache-2.0
"""Supplementary protocol/history regressions. No real device or provider I/O."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from threading import RLock
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4
from tests.integration import test_robot_fleet as sim
from tests.integration import test_physical_fleet_adapter as physical
from tests.integration import test_physical_live_session as live
from twinpulse_core.robot_lineage import twin_context,checked_twin_context,context_relation

sys.path.insert(0,str(physical.ROOT/'packages/twinpulse_robot_safety'))
from fleet_worker import checked_context,checked_command,FleetWorker


def reference(revision='a'*64,project='project-a',session='conversation-a',kind='physical'):
    return twin_context(project,session,dict(engine_connected=True,engine_session_id='engine-a',stage_epoch='stage-a',
        snapshot=dict(applied_revision=revision)),kind=kind)


class ContextTests(unittest.TestCase):
    def test_hash_is_content_bound_detached_and_not_authorization(self):
        a=reference();b=reference();self.assertEqual(a,b)
        b['scene_revision']='b'*64
        with self.assertRaisesRegex(ValueError,'SHA'):checked_twin_context(b)
        with self.assertRaisesRegex(ValueError,'PROJECT'):checked_twin_context(a,project_id='other')
        self.assertFalse(a['alignment']['aligned']);self.assertEqual(a['alignment']['status'],'UNALIGNED')
        self.assertNotEqual(a['context_id'],reference(session='conversation-b')['context_id'])

    def test_no_scene_and_changed_engine_and_undo_do_not_become_aligned(self):
        missing=twin_context('project-a','conversation-a',dict(engine_connected=False,snapshot=dict(applied_revision='old')))
        self.assertIsNone(missing['scene_revision']);self.assertEqual(missing['association'],'NO_CURRENT_TWIN')
        a=reference();before=json.dumps(a,sort_keys=True)
        self.assertEqual(context_relation(a,reference('b'*64)),'DIFFERENT_TWIN_REVISION')
        self.assertEqual(context_relation(a,reference()),'SAME_TWIN_REFERENCE_NOT_ALIGNMENT_PROOF')
        self.assertEqual(json.dumps(a,sort_keys=True),before)
        self.assertEqual(context_relation(None,a),'LEGACY_UNKNOWN')
        self.assertEqual(context_relation(a,reference(project='other')),'OTHER_PROJECT')

    def test_operator_anchor_keeps_its_own_revision_and_never_proves_alignment(self):
        anchor=dict(position_m=[1.,2.,0.],source='operator_estimate_not_localized',scene_revision='old',
                    frame_id='isaac_world',aligned=False,visual_epoch='visual')
        a=twin_context('p','chat',dict(engine_connected=True,engine_session_id='e',stage_epoch='s',snapshot=dict(applied_revision='new')),anchor=anchor)
        anchor['position_m'][0]=99
        self.assertEqual(a['alignment']['anchor']['position_m'][0],1.)
        self.assertEqual(a['alignment']['anchor']['scene_revision'],'old');self.assertFalse(a['alignment']['aligned'])


class SimLineageTests(unittest.TestCase):
    def setUp(self):
        self.f=sim.FleetTests();self.f.setUp();self.addCleanup(self.f.tearDown)
        self.f.fleet.conversation_session_id='chat-a'

    def test_each_report_keeps_its_revision_and_late_result_joins_original_request(self):
        f=self.f;robot=f.connected();f.send('command',robot,dict(text='left 90 degrees'))
        request=f.fleet.last_command['request_id'];operation=f.fleet.robots[robot]['operation_id']
        f.report(robot,reason='TASK_COMPLETED',task_id=request)
        old=deepcopy(f.fleet.operations[operation]['events'])
        command=next(e for e in old if e['kind']=='command_accepted')
        result=next(e for e in old if e['kind']=='motion_result')
        self.assertEqual(result['request_twin_context'],command['twin_context'])
        f.fleet.broker.state=deepcopy(f.fleet.broker.state);f.fleet.broker.state['snapshot']['applied_revision']='revision-b'
        f.fleet.engine_exchange('engine','stage',dict(engine_session_id='engine',stage_epoch='stage',report=dict(applied_revision='revision-b',robots=[])))
        row=f.fleet.robots[robot];f.now+=.6
        f.fleet.engine_exchange('engine','stage',dict(engine_session_id='engine',stage_epoch='stage',report=dict(applied_revision='revision-b',robots=[
            dict(robot_id=robot,connection_epoch=row['connection_epoch'],motion_epoch=row['motion_epoch'],sequence=1,position_m=[1,1,0])])) )
        current=f.fleet.operations[operation]
        self.assertEqual(current['events'][:len(old)],old)
        self.assertEqual(current['events'][-1]['twin_context']['scene_revision'],'revision-b')
        self.assertEqual(current['manifest']['source_twin_context']['scene_revision'],'revision')
        self.assertEqual(current['events'][0]['conversation_session_id'],'chat-a')

    def test_connect_effect_captures_admission_not_later_scene(self):
        f=self.f;robot=f.register();original=f.fleet._begin;captured=[]
        def delayed(row,connection,context,request_id=None):captured.append((row,connection,context,request_id))
        with patch.object(f.fleet,'_begin',delayed):f.send('connect',robot)
        f.fleet.broker.state=deepcopy(f.fleet.broker.state);f.fleet.broker.state['snapshot']['applied_revision']='later'
        original(*captured[0]);op=f.fleet.operation(f.fleet.robots[robot]['operation_id'])
        self.assertEqual(op['manifest']['source_twin_context']['scene_revision'],'revision')
        self.assertEqual(op['events'][0]['twin_context']['scene_revision'],'revision')

    def test_stop_all_preserves_parent_request_and_new_chat_reference_for_each_robot(self):
        f=self.f;sent=[]
        f.fleet.physical=SimpleNamespace(snapshot=lambda owner:{'robots':[dict(robot_id='a',owned=True),dict(robot_id='b',owned=True)]},
            stop=lambda robot,owner,**kw:sent.append((robot,deepcopy(kw))))
        f.send('stop_all')
        self.assertEqual([r[0] for r in sent],['a','b'])
        self.assertEqual({r[1]['request_id'] for r in sent},{f.fleet.last_command['request_id']})
        self.assertTrue(all(r[1]['request_twin_context']['project_id']=='test-project' for r in sent))


class PhysicalHistoryTests(unittest.TestCase):
    def setUp(self):
        self.f=physical.PhysicalFleetAdapterTests();self.f.setUp();self.addCleanup(self.f.doCleanups)

    def test_source_context_survives_closed_cold_history_without_rewriting_or_authority(self):
        f=self.f;a=reference();row=f.connect(source_twin_context=a);identity=row['operation_id']
        a['scene_revision']='changed';f.pool.disconnect(f.rows[0]['id'],f.owner)
        path=Path(f.tmp.name)/'physical-fleet-operations'/(identity+'.jsonl');original=path.read_bytes()
        f.history_session();cold=f.cold_pool()
        record=cold.operation(identity,f.owner,project_id='project-a')
        self.assertTrue(record['manifest']['complete']);self.assertEqual(path.read_bytes(),original)
        self.assertEqual(record['manifest']['source_twin_context'],reference())
        self.assertIn('NOT_ACQUISITION_SYNC',record['manifest']['lineage_status'])
        self.assertFalse(record['manifest']['device_authority_restored'])
        self.assertNotIn(f.owner,original.decode());self.assertNotIn(f.created[f.rows[0]['id']].diagnostics.token,original.decode())

    def test_existing_context_cannot_be_rebound_but_stop_still_works(self):
        f=self.f;row=f.connect(source_twin_context=reference())
        with self.assertRaisesRegex(Exception,'immutable'):
            f.connect(operation_id=row['operation_id'],source_twin_context=reference('b'*64))
        f.pool.stop(f.rows[0]['id'],f.owner)
        self.assertEqual(f.pool.operation(row['operation_id'],f.owner)['manifest']['source_twin_context'],reference())

    def test_legacy_records_remain_unknown_not_backfilled(self):
        f=self.f;identity,path,original=f.saved_operation();f.history_session()
        record=f.cold_pool().operation(identity,f.owner,project_id='project-a')
        self.assertTrue(record['manifest']['complete']);self.assertIsNone(record['manifest']['source_twin_context'])
        self.assertEqual(record['manifest']['lineage_status'],'LEGACY_UNKNOWN');self.assertEqual(path.read_bytes(),original)


class ProtocolV2Tests(unittest.TestCase):
    def setUp(self):
        self.f=live.PhysicalLiveSessionTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.f.session.context.update(schema='physical-live-start-2.0',binding_sha256='d'*64,source_twin_context=reference())

    def test_remote_commands_and_raw_scan_source_exports_keep_same_reference(self):
        f=self.f;context=deepcopy(f.session.context);context.pop('motion_epoch',None)
        self.assertEqual(checked_context(context),context)
        for kind in ('raw','scan','raw_source'):
            data=dict(points=[[1.,0.]],source='physical_native_sensor_unaligned',aligned=False) if kind=='scan' else {}
            event=f.event(kind,**data);event.update(schema='physical-live-event-2.0',source_twin_context_id=reference()['context_id'])
            f.session.receive(event)
        self.assertEqual(f.session.scan['source_twin_context_id'],reference()['context_id'])
        self.assertFalse(f.session.scan['aligned'])
        # Stop has priority even without a fresh heartbeat or a current Twin.
        f.session.command('stop',{},motion_epoch=uuid4().hex,request_id=uuid4().hex,request_twin_context=reference('b'*64))
        packet=f.session.writes.get_nowait();checked=checked_command(packet,context,0)
        self.assertEqual(checked['source_twin_context_id'],reference()['context_id'])
        self.assertEqual(checked['request_twin_context']['scene_revision'],'b'*64)
        packet['source_twin_context_id']='wrong'
        with self.assertRaisesRegex(ValueError,'TWIN_CONTEXT_IDENTITY'):checked_command(packet,context,0)

    def test_missing_or_changed_raw_reference_rejected_without_relabelling(self):
        f=self.f;event=f.event('raw');event.update(schema='physical-live-event-2.0',source_twin_context_id='wrong')
        with self.assertRaisesRegex(ValueError,'TWIN_CONTEXT_IDENTITY'):f.session.receive(event)
        del event['source_twin_context_id']
        with self.assertRaisesRegex(ValueError,'SHAPE'):f.session.receive(event)

    def test_actual_worker_emitter_keeps_buffered_scan_and_late_export_on_start_reference(self):
        context=deepcopy(self.f.session.context);context.pop('motion_epoch',None)
        worker=object.__new__(FleetWorker);worker.context=checked_context(context)
        worker.lock=RLock();worker.sequence=0;worker.clock=lambda:50.;saved=[];sent=[]
        worker.emit_timing=dict(events=0,maximum_payload_prepare_s=0.,maximum_order_lock_wait_s=0.)
        worker.journal=SimpleNamespace(append_prepared=lambda line,kind:saved.append(json.loads(line)))
        worker.protocol=SimpleNamespace(send_prepared=lambda line:sent.append(json.loads(line)))
        for kind in ('raw','scan','raw_source','command','cleanup'):
            worker.emit(kind,dict(receipt_start_s=1.,receipt_end_s=2.))
        self.assertEqual(len(sent),5);self.assertEqual(saved,sent)
        self.assertTrue(all(e['schema']=='physical-live-event-2.0' and e['source_twin_context_id']==reference()['context_id'] for e in sent))
        self.assertEqual(worker.context['source_twin_context'],reference())


if __name__=='__main__':unittest.main()
