# SPDX-License-Identifier: Apache-2.0
"""No devices: deterministic contention and original clock-pair regressions."""
from copy import deepcopy
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace as S
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'packages/twinpulse_robot_safety'))
sys.path.insert(0,str(ROOT/'packages/twinpulse_core/src'))
import fleet_worker
import fleet_control
from fleet_worker import FleetWorker
from fleet_control import RobotControl
from teleop_ros import RosLink
from teleop_worker import ProtocolOutbox
from robot_journal import RobotJournal


def context():
    return dict(schema='physical-live-start-1.0',operation_id='o'*32,robot_id='b'*32,project_id='default',
                connection_epoch='c'*32,binding_sha256='a'*64,worker_sha256='a'*64)


class Control:
    def __init__(self,*a,**k):self.stop_requested=threading.Event();self.field_until=0.


class Native:
    def __init__(self,*a,**k):pass


class ContentionTests(unittest.TestCase):
    def test_wheel_result_stays_inconclusive_and_is_bound_to_renewed_request_and_twin(self):
        owner=RobotControl(dict(context(),source_twin_context={'context_id':'twin-reference'}),'.',lambda *_:None,Native())
        owner.field_mode=True;owner.field_config={'wheel_metres_per_tick':.00001,'wheel_separation_m':.16}
        owner.link=S(rows=[{'t':10.,'encoders':[100,200]}])
        command={'request_id':'first','motion_epoch':'epoch'}
        owner._start_motion_observation(command,'forward')
        owner._start_motion_observation(dict(command,request_id='renewal'),'forward')
        owner.link.rows.append({'t':10.1,'encoders':[1100,1200]})
        result=owner._observe_motion(reason='INPUT_DEADLINE_EXPIRED',ended=True,stop_readback=True)
        self.assertAlmostEqual(result['centre_m'],.01);self.assertEqual(result['yaw_rad'],0.)
        self.assertEqual(result['request_id'],'first');self.assertEqual(result['latest_request_id'],'renewal')
        self.assertEqual(result['source_twin_context_id'],'twin-reference')
        self.assertEqual(result['body_progress'],'UNKNOWN');self.assertEqual(result['result'],'INCONCLUSIVE_BODY_MOTION')
        self.assertEqual(result['reason'],'INPUT_DEADLINE_EXPIRED');self.assertTrue(result['stop_readback_confirmed'])
        owner.link.rows.append({'t':10.2,'encoders':[2100,2200]})
        self.assertIsNone(owner._observe_motion());self.assertAlmostEqual(owner.snapshot()['motion_observation']['centre_m'],.01)

    def test_owner_cancel_ends_observation_without_fabricating_stop_readback(self):
        owner=RobotControl(context(),'.',lambda *_:None,Native())
        owner.field_mode=True;owner.field_config={'wheel_metres_per_tick':.00001,'wheel_separation_m':.16}
        owner.link=S(rows=[{'t':10.,'encoders':[0,0],'source_age_s':.05}])
        owner._start_motion_observation({'request_id':'original','motion_epoch':'epoch'},'left')
        owner._field_snapshot=lambda:{}
        owner.cancel.set();owner._run()
        result=owner.snapshot()['motion_observation']
        self.assertEqual(result['state'],'ENDED');self.assertEqual(result['reason'],'SESSION_CLOSED')
        self.assertFalse(result['stop_readback_confirmed']);self.assertEqual(result['timing_basis'],'ROS_CALLBACK_RECEIPT')
        self.assertAlmostEqual(result['first_source_s'],9.95)

    def test_terminal_observation_delivery_error_cannot_skip_independent_cleanup(self):
        closed=[]
        def emit(*_):raise ValueError('PROTOCOL_CLOSED')
        owner=RobotControl(context(),'.',emit,Native())
        owner.field_mode=True;owner.field_config={'wheel_metres_per_tick':.00001,'wheel_separation_m':.16}
        owner.link=S(rows=[{'t':10.,'encoders':[0,0]}]);owner._field_snapshot=lambda:{}
        owner._start_motion_observation({'request_id':'first','motion_epoch':'epoch'},'forward')
        owner.tracker=S(close=lambda:(closed.append(True) or {'worker_reaped':True,'thread_reaped':True}))
        owner.cancel.set();owner._run()
        self.assertEqual(closed,[True]);self.assertEqual(owner.snapshot()['control_state'],'CLOSED')
        self.assertEqual(owner.snapshot()['motion_observation_error'],'PROTOCOL_CLOSED');self.assertFalse(owner.cleanup_confirmed)

    def test_prepared_wire_and_archive_preserve_json_source_clocks_and_redact_only_nonce(self):
        wire=[]
        data={'text':'quotes " } ,\\ newline\n한글', 'nested':{'challenge':'not-a-top-level-nonce'},
            'issued_s':9.95,'challenge':'wire-nonce','watch_challenge':'wire-watch'}
        with tempfile.TemporaryDirectory() as tmp:
            worker=FleetWorker(context(),tmp,lambda _:self.fail('Raw line writer required'),
                control_factory=Control,native_factory=Native,line_writer=wire.append)
            worker.emit('command',data);worker.emit('heartbeat',{'latest':True})
            journal=worker.journal.close();protocol=worker.protocol.close()
            rows=[json.loads(line) for line in wire]
            saved=[json.loads(line) for line in (Path(tmp)/'events-000000.jsonl').read_text(encoding='utf-8').splitlines()]
        self.assertEqual(journal['accepted'],journal['saved']);self.assertEqual(protocol['sent_messages'],2)
        self.assertEqual([row['sequence'] for row in rows],[1,2])
        self.assertEqual(rows[0]['data']['issued_s'],9.95)
        self.assertEqual(rows[0]['data']['text'],data['text']);self.assertEqual(rows[0]['data']['challenge'],'wire-nonce')
        self.assertEqual(saved[0]['data']['nested'],data['nested'])
        self.assertNotIn('challenge',saved[0]['data']);self.assertNotIn('watch_challenge',saved[0]['data'])
        self.assertEqual(saved[0]['data']['event_delivery'],rows[0]['data']['event_delivery'])
        self.assertNotIn('event_delivery',data)

    def test_prepared_protocol_counts_utf8_bytes_not_characters_and_keeps_sticky_failure(self):
        entered=threading.Event();release=threading.Event();line=json.dumps({'x':'한글'},ensure_ascii=False)
        size=len(line.encode('utf-8'))+1
        def writer(raw):entered.set();release.wait(2)
        box=ProtocolOutbox(None,line_writer=writer,max_bytes=size,buffered=True)
        box.send_prepared(line);self.assertTrue(entered.wait(1))
        try:
            self.assertEqual(box.status()['queued_bytes'],size)
            with self.assertRaisesRegex(ValueError,'BYTE_BUDGET'):box.send_prepared('{}')
            with self.assertRaisesRegex(ValueError,'BYTE_BUDGET'):box.check()
        finally:release.set();box.close(timeout=1)
        self.assertEqual(box.status()['sent_messages'],1)

    def test_prepared_journal_capacity_and_no_raw_line_injection(self):
        line=json.dumps({'kind':'command','text':'한글\n"{}'},ensure_ascii=False)+'\n'
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'events.jsonl';journal=RobotJournal(path,max_bytes=len(line.encode('utf-8')),buffered=True)
            journal.append_prepared(line,'command')
            with self.assertRaisesRegex(ValueError,'BYTE_BUDGET'):journal.append_prepared('{}\n','command')
            result=journal.close()
            self.assertEqual(result['accepted'],1);self.assertEqual(result['saved'],1)
            self.assertEqual(path.read_bytes(),line.encode('utf-8'))
        for value in ('{}\n{}','{}\n'):
            box=ProtocolOutbox(lambda _:None)
            try:
                with self.assertRaisesRegex(ValueError,'PREPARED_LINE'):box.send_prepared(value)
            finally:box.close()

    def test_oversized_event_stops_without_sending_truncated_or_retimestamped_input(self):
        sent=[]
        with tempfile.TemporaryDirectory() as tmp:
            worker=FleetWorker(context(),tmp,sent.append,control_factory=Control,native_factory=Native)
            try:
                with self.assertRaisesRegex(ValueError,'BYTE_LIMIT'):
                    worker.emit('command',{'issued_s':10.,'text':'x'*(256*1024)})
                self.assertTrue(worker.recording_failed);self.assertTrue(worker.control.stop_requested.is_set())
                self.assertEqual(worker.control.field_until,0.)
            finally:journal=worker.journal.close();worker.protocol.close()
        self.assertEqual(sent,[]);self.assertEqual(journal['accepted'],0)

    def test_slow_heartbeat_payload_preparation_does_not_own_nonce_emit_lock(self):
        entered=threading.Event();release=threading.Event();small_done=threading.Event();sent=[];errors=[]
        original=deepcopy
        def copy(value,*args,**kwargs):
            if isinstance(value,dict) and value.get('slow_heartbeat'):
                entered.set();release.wait(2)
            return original(value,*args,**kwargs)
        def emit(worker,kind,value,done=None):
            try:worker.emit(kind,value)
            except Exception as error:errors.append(error)
            finally:
                if done:done.set()
        with tempfile.TemporaryDirectory() as tmp:
            worker=FleetWorker(context(),tmp,sent.append,control_factory=Control,native_factory=Native)
            with patch('fleet_worker.deepcopy',side_effect=copy):
                large=threading.Thread(target=emit,args=(worker,'heartbeat',{'slow_heartbeat':True}),daemon=True)
                small=threading.Thread(target=emit,args=(worker,'command',dict(action='input_window',issued_s=10.,challenge='original'),small_done),daemon=True)
                large.start();self.assertTrue(entered.wait(1));small.start()
                try:completed_while_large_blocked=small_done.wait(.2)
                finally:release.set();large.join(1);small.join(1)
            journal=worker.journal.close();wire=worker.protocol.close()
            self.assertTrue(completed_while_large_blocked,'Large heartbeat preparation held the nonce/control emit lock')
            self.assertEqual(errors,[]);self.assertEqual(journal['saved'],2);self.assertFalse(wire['sender_alive'])
            self.assertEqual([r['sequence'] for r in sent],[1,2])
            self.assertEqual(sent[0]['data']['issued_s'],10.)
            self.assertNotIn('challenge',(Path(tmp)/'events-000000.jsonl').read_text(encoding='utf-8'))

    def test_slow_public_snapshot_does_not_block_small_control_update(self):
        owner=RobotControl(context(),'.',lambda *_:None,Native())
        owner._update(large={'slow_snapshot':True,'rows':[[1,2]]})
        entered=threading.Event();release=threading.Event();updated=threading.Event();original=deepcopy
        def copy(value,*args,**kwargs):
            if isinstance(value,dict) and 'large' in value:
                entered.set();release.wait(2)
            return original(value,*args,**kwargs)
        with patch('fleet_control.deepcopy',side_effect=copy):
            reader=threading.Thread(target=owner.snapshot,daemon=True);reader.start();self.assertTrue(entered.wait(1))
            writer=threading.Thread(target=lambda:(owner._update(challenge='new-original'),updated.set()),daemon=True);writer.start()
            try:self.assertTrue(updated.wait(.2),'Display deepcopy held the small control-state update lock')
            finally:release.set();reader.join(1);writer.join(1)
        self.assertEqual(owner.snapshot()['challenge'],'new-original')

    def test_snapshot_and_update_do_not_share_mutable_payloads(self):
        owner=RobotControl(context(),'.',lambda *_:None,Native())
        value={'rows':[[1,2]],'task':{'state':'RUNNING'}}
        owner._update(example=value)
        value['rows'][0][0]=999;value['task']['state']='EDITED_AFTER_PUBLISH'
        first=owner.snapshot();self.assertEqual(first['example']['rows'],[[1,2]])
        first['example']['rows'][0][0]=888
        self.assertEqual(owner.snapshot()['example']['rows'],[[1,2]])

    def test_sensor_receipt_and_source_age_are_one_original_clock_pair(self):
        link=RosLink.__new__(RosLink);now=[10.];msg=S(header=S(stamp=S(sec=9,nanosec=950000000)),
            left_encoder=0,right_encoder=0,torque=True,battery=11.7,button=0)
        link.sensor_t=0.;link.anchor=None;link.rows=[];link.raw=None
        link.node=S(get_clock=lambda:S(now=lambda:S(nanoseconds=int(now[0]*1e9))))
        link.record_sink=lambda *_:now.__setitem__(0,10.2)
        with patch('teleop_ros.time.monotonic_ns',side_effect=lambda:int(now[0]*1e9)):
            link._sensor(msg)
        self.assertAlmostEqual(link.rows[-1]['t'],10.)
        self.assertAlmostEqual(link.rows[-1]['t']-link.rows[-1]['source_age_s'],9.95)
        self.assertAlmostEqual(link.sensor_t,10.)
        # The delayed callback still leaves its real recording elapsed visible.
        self.assertAlmostEqual(link.sensor_receipt_timing['recording_elapsed_s'],.2)
        # Pair correction is NOT a freshness exception: at callback end the
        # original header is already 250ms old, even with recent receipts.
        link.sensor_t=link.guard_t=10.19
        with patch('teleop_ros.time.monotonic',return_value=10.2),self.assertRaisesRegex(ValueError,'BATTERY_BUTTON_OR_SOURCE_AGE'):
            link.fresh()
        self.assertEqual(link.fresh_diagnostic['reason'],'SENSOR_SOURCE_AGE')


class UnpreparedPauseJsonTests(unittest.TestCase):
    """Real control -> strict FleetWorker JSON; no devices or worker threads."""
    def fixture(self):
        class NativeIdle:
            def latest_frame(self):return None
            def snapshot(self):return {'lidar_state':'OFF'}
        class JournalMemory:
            def __init__(self):self.rows=[]
            def append_prepared(self,line,kind):self.rows.append(json.loads(line));return True
        class ProtocolMemory:
            def __init__(self):self.rows=[]
            def send_prepared(self,line):self.rows.append(json.loads(line))
        worker=FleetWorker.__new__(FleetWorker)
        worker.context=dict(context(),schema='physical-live-start-2.0',
            source_twin_context={'context_id':'d'*64})
        worker.clock=__import__('time').monotonic;worker.lock=threading.RLock()
        worker.sequence=0;worker.recording_failed=False
        worker.emit_timing=dict(events=0,maximum_payload_prepare_s=0.,maximum_order_lock_wait_s=0.)
        worker.journal=JournalMemory();worker.protocol=ProtocolMemory()
        owner=RobotControl(worker.context,'.',worker.emit,NativeIdle());worker.control=owner
        return worker,owner

    def test_first_field_setup_crosses_actual_strict_json_without_output_or_authority(self):
        worker,owner=self.fixture()
        config=dict(schema='supervised-field-test-1.0',robot_id=context()['robot_id'],
            binding_sha256=context()['binding_sha256'],provenance='reference',axes_reviewed=True,
            angle_sign=1,footprint_radius_m=.12,sensor_x_m=0.,sensor_y_m=0.,sensor_yaw_rad=0.,
            wheel_metres_per_tick=.00005,wheel_separation_m=.16)
        command=dict(action='field_setup',request_id='first-setup',payload={'config':config})
        owner._input_window()
        tracker=S(snapshot=lambda:{},close=lambda:{'worker_reaped':True,'thread_reaped':True})
        with patch('fleet_control.NativeTracker',return_value=tracker),patch.object(owner,'_field_write',return_value='fixture-write'):
            owner._drain_commands(command)
        self.assertEqual(owner.field_config,config);self.assertTrue(owner.field_mode)
        self.assertFalse(worker.recording_failed);self.assertIsNone(owner.thread.ident)
        self.assertIsNone(owner.link);self.assertIsNone(owner.direction);self.assertEqual(owner.field_until,0.)
        self.assertEqual(worker.protocol.rows[-1]['data']['status'],'COMPLETED')
        pause=next(r['data'] for r in worker.journal.rows if r['kind']=='control_pause')
        self.assertIsNone(pause['input_diagnostic']['last_publish_s'])
        self.assertFalse(pause['zero_off_readback_confirmed'])
        self.assertEqual(owner.last_publish,float('-inf'))

    def test_stop_before_prepare_keeps_no_publication_as_null_not_a_stop_readback(self):
        worker,owner=self.fixture();owner._pause('OPERATOR_STOP')
        pause=worker.protocol.rows[-1]['data']
        self.assertEqual(pause['reason'],'OPERATOR_STOP')
        self.assertIsNone(pause['input_diagnostic']['last_publish_s'])
        self.assertFalse(pause['zero_off_readback_confirmed']);self.assertFalse(worker.recording_failed)
        self.assertEqual(owner.last_publish,float('-inf'));self.assertFalse(owner.gate.active)

    def test_real_control_thread_survives_initial_setup_and_stop_without_devices(self):
        worker,owner=self.fixture();setup_done=threading.Event();stop_done=threading.Event()
        waiting_for_stop=threading.Event();stop_submitted=threading.Event()
        class StopArrivalQueue(fleet_control.queue.Queue):
            signalled=False
            def get(self,*args,**kwargs):
                # The main loop has checked stop_requested before this get.
                # Submit Stop only after that check, not through a timing sleep.
                block=kwargs.get('block',args[0] if args else True)
                if block and setup_done.is_set() and not self.signalled:
                    self.signalled=True;waiting_for_stop.set()
                    if not stop_submitted.wait(2):raise RuntimeError('TEST_STOP_BARRIER_TIMEOUT')
                return super().get(*args,**kwargs)
        owner.queue=StopArrivalQueue(maxsize=32)
        config=dict(schema='supervised-field-test-1.0',robot_id=context()['robot_id'],
            binding_sha256=context()['binding_sha256'],provenance='reference',axes_reviewed=True,
            angle_sign=1,footprint_radius_m=.12,sensor_x_m=0.,sensor_y_m=0.,sensor_yaw_rad=0.,
            wheel_metres_per_tick=.00005,wheel_separation_m=.16)
        original=worker.protocol.send_prepared
        def observe(line):
            original(line);row=json.loads(line);data=row['data']
            if row['kind']=='command' and data.get('status')=='COMPLETED':
                if data.get('request_id')=='initial-setup':setup_done.set()
                if data.get('request_id')=='first-stop':stop_done.set()
        worker.protocol.send_prepared=observe
        owner.queue.put_nowait(dict(action='field_setup',request_id='initial-setup',payload={'config':config}))
        tracker=S(snapshot=lambda:{},close=lambda:{'worker_reaped':True,'thread_reaped':True})
        with patch('fleet_control.NativeTracker',return_value=tracker),patch.object(owner,'_field_write',return_value='fixture-write'):
            owner.start()
            try:
                self.assertTrue(setup_done.wait(2),'Initial setup did not cross the actual emit boundary')
                self.assertTrue(owner.thread.is_alive());self.assertFalse(worker.recording_failed)
                self.assertTrue(waiting_for_stop.wait(2),'Owner did not enter the declared queue-get boundary')
                owner.submit(dict(action='stop',request_id='first-stop',motion_epoch='stopped-epoch',payload={}))
                stop_submitted.set()
                self.assertTrue(stop_done.wait(2),'Pre-Prepare Stop did not complete on the same worker: '+
                    repr([(r['kind'],r['data'].get('action'),r['data'].get('reason'),r['data'].get('status')) for r in worker.protocol.rows[-5:]]))
                self.assertTrue(owner.thread.is_alive());self.assertIsNone(owner.link)
                self.assertEqual(owner.snapshot()['applied_motion_epoch'],'stopped-epoch')
                self.assertFalse(owner.gate.active);self.assertEqual(owner.last_publish,float('-inf'))
            finally:
                stop_submitted.set();owner.cancel.set();owner.thread.join(2)
        self.assertFalse(owner.thread.is_alive());self.assertFalse(worker.recording_failed)
        pauses=[row['data'] for row in worker.journal.rows if row['kind']=='control_pause']
        self.assertTrue(pauses)
        self.assertTrue(all(row['input_diagnostic']['last_publish_s'] is None for row in pauses))
        self.assertTrue(all(row['zero_off_readback_confirmed'] is False for row in pauses))

    def test_rejected_unprepared_drive_keeps_original_reason_and_json_owner_alive(self):
        worker,owner=self.fixture()
        owner._drain_commands(dict(action='drive',request_id='not-prepared',
            payload={'motion_generation':owner.gate.generation,'direction':'forward'}))
        rejected=worker.protocol.rows[-1]['data']
        self.assertEqual(rejected['status'],'REJECTED')
        self.assertEqual(rejected['reason'],'PREPARE_REQUIRED')
        self.assertFalse(worker.recording_failed);self.assertIsNone(owner.direction)
        self.assertEqual(owner.snapshot()['control_state'],'UNPREPARED')

    def test_finite_publication_timestamp_is_preserved_exactly(self):
        worker,owner=self.fixture();owner.last_publish=12.5;owner._pause('OPERATOR_STOP')
        self.assertEqual(worker.protocol.rows[-1]['data']['input_diagnostic']['last_publish_s'],12.5)
        self.assertEqual(owner.last_publish,12.5);self.assertFalse(worker.recording_failed)

    def test_stop_priority_still_discards_other_commands_and_cancel_blocks_all(self):
        for action in ('drive','task','watch','field_setup','stop'):
            for cancelled in (False,True):
                if action=='stop' and not cancelled:continue
                with self.subTest(action=action,cancelled=cancelled):
                    worker,owner=self.fixture();owner.stop_requested.set()
                    if cancelled:owner.cancel.set()
                    result=owner._drain_commands(dict(action=action,request_id='blocked',payload={}))
                    self.assertEqual(result,0)
                    if action=='stop' and cancelled:
                        self.assertEqual(worker.protocol.rows[-1]['data']['status'],'REJECTED')
                        self.assertEqual(worker.protocol.rows[-1]['data']['request_id'],'blocked')
                    else:self.assertEqual(worker.protocol.rows,[])
                    self.assertIsNone(owner.direction);self.assertFalse(owner.gate.active)

    def test_stop_keeps_its_epoch_and_does_not_drain_an_old_motion_after_it(self):
        worker,owner=self.fixture();owner.stop_requested.set()
        owner.queue.put_nowait(dict(action='drive',request_id='old-motion',
            payload={'motion_generation':0,'direction':'forward'}))
        result=owner._drain_commands(dict(action='stop',request_id='own-stop',
            motion_epoch='exact-stop-epoch',payload={}))
        self.assertEqual(result,1);self.assertEqual(owner.queue.qsize(),1)
        self.assertEqual(owner.snapshot()['applied_motion_epoch'],'exact-stop-epoch')
        self.assertEqual(worker.protocol.rows[-1]['data'],
            dict(request_id='own-stop',action='stop',status='COMPLETED',
                 event_delivery=worker.protocol.rows[-1]['data']['event_delivery']))
        self.assertFalse(owner.gate.active);self.assertIsNone(owner.direction)

    def test_other_nonfinite_diagnostic_still_fails_strict_json_and_latches_recording(self):
        for value in (float('inf'),float('nan')):
            with self.subTest(value=value):
                worker,owner=self.fixture();owner.last_publish=value
                with self.assertRaises(ValueError):owner._pause('OPERATOR_STOP')
                self.assertTrue(worker.recording_failed);self.assertFalse(owner.gate.active)

    def test_recording_failure_cancels_old_control_queue_and_only_requests_stop_once(self):
        worker,owner=self.fixture()
        original_generation=owner.gate.generation
        queued=dict(action='prepare',request_id='old-queued-prepare',payload={'confirmed':True})
        owner.queue.put_nowait(queued)
        worker._recording_fault('SESSION_JOURNAL_QUEUE_FULL')
        self.assertTrue(owner.cancel.is_set());self.assertTrue(owner.stop_requested.is_set())
        owner.stop_requested.clear()  # An old Stop-handler clear is not recovery.
        worker._recording_fault('SECONDARY_RECORDING_ERROR')
        self.assertFalse(owner.stop_requested.is_set())
        self.assertEqual(worker.recording_failure_reason,'SESSION_JOURNAL_QUEUE_FULL')
        self.assertEqual(owner._drain_commands(queued),0)
        self.assertEqual(owner.queue.qsize(),1)
        with self.assertRaisesRegex(ValueError,'OPERATOR_STOP'):owner._safety()
        self.assertEqual(owner.gate.generation,original_generation)

    def test_stop_after_recording_fault_and_real_owner_exit_has_own_rejected_result(self):
        worker,owner=self.fixture()
        worker._recording_fault('FIRST_RECORDING_FAILURE')
        owner.start();owner.thread.join(2)
        self.assertFalse(owner.thread.is_alive())
        self.assertEqual(owner.snapshot()['control_state'],'CLOSED')
        epoch=owner.snapshot()['applied_motion_epoch']
        worker.last_command=0
        command=dict(schema='physical-live-command-2.0',
            **{k:worker.context[k] for k in fleet_worker.IDENTITY},
            source_twin_context_id=worker.context['source_twin_context']['context_id'],request_twin_context=None,
            motion_epoch='s'*32,request_id='s'*32,sequence=1,action='stop',payload={})
        worker.command(command)
        result=worker.protocol.rows[-1]['data']
        self.assertEqual(result['request_id'],command['request_id'])
        self.assertEqual(result['status'],'REJECTED');self.assertEqual(result['reason'],'RECORDING_INCOMPLETE')
        self.assertEqual(result['execution'],'NOT_EXECUTED_CONTROL_OWNER_CLOSING')
        self.assertEqual(owner.snapshot()['applied_motion_epoch'],epoch)
        self.assertEqual(owner.queue.qsize(),0)
        owner.submit(dict(command,request_id='direct-stop'))
        direct=worker.protocol.rows[-1]['data']
        self.assertEqual(direct['request_id'],'direct-stop');self.assertEqual(direct['status'],'REJECTED')
        self.assertEqual(direct['execution'],'NOT_EXECUTED')
        owner.submit(dict(command,action='close'))
        self.assertEqual(owner.queue.qsize(),0)
        self.assertTrue(owner.close()['worker_reaped'])

    def test_stop_queued_at_recording_cancel_boundary_gets_own_terminal(self):
        for cancel_during_put in (False,True):
            with self.subTest(cancel_during_put=cancel_during_put):
                worker,owner=self.fixture()
                if cancel_during_put:
                    class CancelDuringPut(fleet_control.queue.Queue):
                        def put_nowait(self,value):
                            worker._recording_fault('FAULT_AFTER_ADMISSION_CHECK')
                            return super().put_nowait(value)
                    owner.queue=CancelDuringPut(maxsize=32)
                owner.submit(dict(action='stop',request_id='queued-stop',motion_epoch='never-applied',payload={}))
                if not cancel_during_put:worker._recording_fault('FAULT_AFTER_QUEUE')
                owner.start();owner.thread.join(2)
                self.assertFalse(owner.thread.is_alive());self.assertEqual(owner.queue.qsize(),0)
                result=[r['data'] for r in worker.protocol.rows if r['data'].get('request_id')=='queued-stop']
                self.assertEqual(len(result),1);self.assertEqual(result[0]['status'],'REJECTED')
                self.assertEqual(result[0]['execution'],'NOT_EXECUTED')
                self.assertNotEqual(owner.snapshot()['applied_motion_epoch'],'never-applied')


if __name__=='__main__':unittest.main()
