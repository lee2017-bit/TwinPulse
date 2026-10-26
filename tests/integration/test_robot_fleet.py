# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Device-free contract regressions; actual Isaac/UI acceptance is separate."""
from copy import deepcopy
import math
from pathlib import Path
import tempfile
import unittest
from threading import Event,Thread
from unittest.mock import Mock, patch

from tests.integration import test_r5_product_api  # existing source-path bootstrap
from twinpulse_app.robot_fleet import RobotFleet, parse_robot_command
from twinpulse_app.command_broker import BrokerError


class Broker:
    project_id='test-project'
    state=dict(engine_connected=True,engine_session_id='engine',stage_epoch='stage',snapshot=dict(applied_revision='revision'))
    def supervisor_state(self):return deepcopy(self.state)


class FleetTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.now=100.;self.fleet=RobotFleet(Broker(),Path(self.temp.name),clock=lambda:self.now,wall=lambda:self.now)
        self.counter=0
    def tearDown(self):self.fleet.close();self.temp.cleanup()
    def send(self,action,robot=None,payload=None,**extra):
        self.counter+=1
        value=dict(action=action,request_id='request_'+str(self.counter),robot_id=robot,connection_epoch=None,motion_epoch=None,payload=payload or {})
        value.update(extra);return self.fleet.action(value,'owner')
    def register(self,label='Alpha'):
        state=self.send('register_sim',payload=dict(label=label,position_m=[1,1,0]));return state['focused_robot_id']
    def report(self,robot,**extra):
        row=self.fleet.robots[robot]
        value=dict(robot_id=robot,connection_epoch=row['connection_epoch'],motion_epoch=row['motion_epoch'],sequence=row['telemetry_sequence']+1,position_m=[1,1,0],
            runtime_startup=dict(model_authored=True,render_observed=True,snapshot_capture_pending=False,post_author_updates=2,ready=True))
        value.update(extra)
        return self.fleet.engine_exchange('engine','stage',dict(engine_session_id='engine',stage_epoch='stage',report=dict(applied_revision='revision',robots=[value])))
    def connected(self,label='Alpha'):
        robot=self.register(label);self.send('connect',robot);self.report(robot);self.send('prepare',robot);return robot
    def test_green_requires_actual_engine_report_and_battery_has_no_invented_soc(self):
        robot=self.register();self.send('connect',robot)
        self.assertEqual(self.fleet.snapshot()['robots'][0]['connection_state'],'DEGRADED')
        self.report(robot);row=self.fleet.snapshot()['robots'][0]
        self.assertEqual(row['connection_state'],'CONNECTED');self.assertIsNone(row['battery']['percent'])
        self.assertEqual(row['battery']['source'],'simulated')
    def test_action_and_idempotent_retry_publish_only_one_snapshot(self):
        self.register('Alpha');self.register('Beta')
        body=dict(action='status',request_id='same_status',robot_id=self.fleet.focused,
                  connection_epoch=None,motion_epoch=None,payload={})
        for _ in range(2):
            with patch.object(self.fleet,'_snapshot_locked',wraps=self.fleet._snapshot_locked) as snapshot:
                self.fleet.action(body,'owner')
                self.assertEqual(snapshot.call_count,1)
    def test_public_snapshot_reads_one_current_engine_identity_for_all_rows(self):
        self.register('Alpha');self.register('Beta')
        with patch.object(self.fleet.broker,'supervisor_state',wraps=self.fleet.broker.supervisor_state) as state:
            value=self.fleet.snapshot()
            self.assertEqual(state.call_count,1)
        self.assertEqual(value['robots'][0]['current_twin_context'],value['robots'][1]['current_twin_context'])
    def test_physical_diagnostics_survive_public_row_filter_without_granting_drive(self):
        # Reproduces the powered ee9883.. data path: the adapter supplied these
        # fields but the initialized public row did not have them.
        from types import SimpleNamespace
        identity='p'*32
        row=self.fleet._robot(identity,'Physical',[0,0,0],kind='physical')
        self.fleet.robots[identity]=row;self.fleet.physical=SimpleNamespace()
        source=dict(robot_id=identity,project_id='test-project',
            telemetry_diagnostic=dict(reason='SENSOR_SOURCE_AGE',source_age_s=.223906317,
                sensor_receipt_age_s=.000876351,guard_receipt_age_s=.020916754),
            native_diagnostic=dict(checksum_errors=0,unframed_bytes=191),
            timing_values=dict(input_ttl_ms=350,output_timeout_ms=450),
            timing_profile_sha256='a'*64,output_timing=dict(output_timeout_ms=450),
            unreviewed_field='must not be copied')
        self.fleet._physical_rows(([],[source]))
        self.assertEqual(row['telemetry_diagnostic'],source['telemetry_diagnostic'])
        self.assertEqual(row['native_diagnostic'],source['native_diagnostic'])
        for name in ('timing_values','timing_profile_sha256','output_timing'):
            self.assertEqual(row[name],source[name])
        self.assertFalse(row['capabilities']['drive'])
        self.assertNotIn('unreviewed_field',row)
        source['telemetry_diagnostic']['reason']='changed'
        source['timing_values']['input_ttl_ms']=999
        self.assertEqual(row['timing_values']['input_ttl_ms'],350)
        self.assertEqual(row['telemetry_diagnostic']['reason'],'SENSOR_SOURCE_AGE')
        self.fleet._physical_rows(([],[dict(robot_id=identity,project_id='test-project',
            telemetry_diagnostic=None,native_diagnostic=None,timing_values=None,
            timing_profile_sha256=None,output_timing=None)]))
        self.assertIsNone(row['telemetry_diagnostic']);self.assertIsNone(row['native_diagnostic'])
        self.assertIsNone(row['timing_values']);self.assertIsNone(row['output_timing'])
    def test_sim_guard_uses_current_active_query_without_full_physical_journal(self):
        from types import SimpleNamespace
        robot=self.connected();row=self.fleet.robots[robot]
        snapshot=Mock(side_effect=AssertionError('Historical snapshot on motion admission'))
        query=Mock(return_value=True)
        self.fleet.devices=SimpleNamespace(snapshot=snapshot,operation_active=query)
        payload=dict(direction='forward',sequence=1,expires_at_ms=100220)
        with self.assertRaisesRegex(BrokerError,'active physical'):
            self.send('drive',robot,payload,connection_epoch=row['connection_epoch'],motion_epoch=row['motion_epoch'])
        query.return_value=False
        self.send('drive',robot,payload,connection_epoch=row['connection_epoch'],motion_epoch=row['motion_epoch'])
        self.assertEqual(query.call_count,2);snapshot.assert_not_called()
    def test_two_sessions_selection_and_disconnect_are_isolated(self):
        a=self.connected('Alpha');b=self.connected('Beta')
        old=self.fleet.robots[a]['connection_epoch'];self.send('focus',a);self.send('disconnect',b)
        self.assertTrue(self.fleet.robots[a]['_connected']);self.assertEqual(self.fleet.robots[a]['connection_epoch'],old)
    def test_stop_revokes_even_later_high_sequence_of_old_epoch(self):
        robot=self.connected();row=self.fleet.robots[robot];epoch=row['motion_epoch'];connection=row['connection_epoch']
        self.send('stop',robot)
        with self.assertRaisesRegex(BrokerError,'Motion was stopped'):
            self.send('drive',robot,dict(direction='forward',sequence=999,expires_at_ms=100100),connection_epoch=connection,motion_epoch=epoch)
        self.assertIsNone(row['_intent'])
    def test_stop_acceptance_is_not_engine_stop_confirmation(self):
        robot=self.connected();row=self.fleet.robots[robot];old=row['motion_epoch']
        self.send('stop',robot)
        self.assertNotEqual(row['applied_motion_epoch'],row['motion_epoch'])
        self.report(robot,motion_epoch=old)
        self.assertNotEqual(row['applied_motion_epoch'],row['motion_epoch'])
        self.report(robot,motion_epoch=row['motion_epoch'])
        self.assertEqual(row['applied_motion_epoch'],row['motion_epoch'])
    def test_expired_input_pauses_not_disconnects(self):
        robot=self.connected();row=self.fleet.robots[robot]
        with self.assertRaisesRegex(BrokerError,'expired'):
            self.send('drive',robot,dict(direction='forward',sequence=1,expires_at_ms=99999),connection_epoch=row['connection_epoch'],motion_epoch=row['motion_epoch'])
        self.assertTrue(row['_connected']);self.assertEqual(row['control_state'],'PAUSED')
    def test_old_engine_expiry_cannot_cancel_newer_still_valid_input(self):
        robot=self.connected();row=self.fleet.robots[robot];epoch=row['motion_epoch']
        self.send('drive',robot,dict(direction='forward',sequence=10,expires_at_ms=100220),connection_epoch=row['connection_epoch'],motion_epoch=epoch)
        desired=self.report(robot,reason='INPUT_STALE',intent_sequence=9,runtime_timing=dict(elapsed_s=.1,integrated_s=0.,substeps=0))
        self.assertEqual(row['motion_epoch'],epoch);self.assertEqual(row['control_state'],'DRIVING')
        self.assertEqual(desired['fleet']['robots'][0]['intent']['sequence'],10)
        self.report(robot,reason='INPUT_STALE',intent_sequence=10)
        self.assertNotEqual(row['motion_epoch'],epoch);self.assertIsNone(row['_intent'])
    def test_large_or_unmeasured_engine_gap_cannot_be_hidden_by_newer_held_sequence(self):
        for reason,timing in [('INPUT_STALE',dict(elapsed_s=.891,integrated_s=0.,substeps=0)),
                ('INPUT_STALE',None),('ISAAC_UPDATE_STALLED',dict(elapsed_s=.891,integrated_s=0.,substeps=0)),
                ('ISAAC_TRANSPORT_STALE',dict(elapsed_s=.03,integrated_s=0.,substeps=0))]:
            robot=self.connected(reason+str(timing));row=self.fleet.robots[robot];epoch=row['motion_epoch']
            self.send('drive',robot,dict(direction='forward',sequence=10,expires_at_ms=100220),connection_epoch=row['connection_epoch'],motion_epoch=epoch)
            self.report(robot,reason=reason,intent_sequence=9,runtime_timing=timing)
            self.assertNotEqual(row['motion_epoch'],epoch);self.assertIsNone(row['_intent'])
    def test_missing_post_model_or_render_readiness_blocks_prepare_and_drive(self):
        robot=self.register();self.send('connect',robot)
        for startup in (None,dict(model_authored=True,render_observed=False,snapshot_capture_pending=False,post_author_updates=2,ready=True),
                dict(model_authored=True,render_observed=True,snapshot_capture_pending=True,post_author_updates=2,ready=True)):
            self.report(robot,runtime_startup=startup)
            with self.assertRaisesRegex(BrokerError,'post-model'):self.send('prepare',robot)
            self.assertEqual(self.fleet.robots[robot]['reason'],'ISAAC_MODEL_WARMING_UP')
        self.report(robot);self.send('prepare',robot);self.assertEqual(self.fleet.robots[robot]['control_state'],'READY')
    def test_old_engine_expiry_still_stops_when_current_input_has_expired(self):
        robot=self.connected();row=self.fleet.robots[robot];epoch=row['motion_epoch']
        self.send('drive',robot,dict(direction='forward',sequence=10,expires_at_ms=100100),connection_epoch=row['connection_epoch'],motion_epoch=epoch)
        self.now+=.11;self.report(robot,reason='INPUT_STALE',intent_sequence=9)
        self.assertNotEqual(row['motion_epoch'],epoch);self.assertIsNone(row['_intent'])
    def test_runtime_late_expiry_binding_never_replays_same_or_lower_sequence(self):
        from scripts.twinpulse_fleet_runtime import bind_intent
        r=dict(reason='INPUT_STALE',intent_sequence=9,stale_intent_sequence=9,last_intent=dict(sequence=9,expires_at_ms=990,direction='forward'))
        bind_intent(r,dict(sequence=10,expires_at_ms=1050,direction='forward'),1000)
        self.assertIsNone(r['reason']);self.assertEqual(r['intent_sequence'],10)
        r.update(reason='INPUT_STALE',stale_intent_sequence=10)
        bind_intent(r,dict(sequence=9,expires_at_ms=9999,direction='backward'),1100)
        self.assertEqual(r['reason'],'INPUT_STALE');self.assertEqual(r['last_intent']['direction'],'forward')
        r=dict(reason='INPUT_STALE',intent_sequence=9,stale_intent_sequence=9,last_intent=None)
        bind_intent(r,dict(sequence=10,expires_at_ms=990,direction='forward'),1000)
        self.assertEqual(r['stale_intent_sequence'],10)
        old=deepcopy(r['last_intent'])
        bind_intent(r,dict(sequence=10,expires_at_ms=9999,direction='backward'),1000)
        self.assertEqual(r['last_intent'],old);self.assertEqual(r['reason'],'INPUT_STALE')
        bind_intent(r,dict(sequence=11,expires_at_ms=1250,direction='forward'),1000)
        self.assertIsNone(r['reason'])
        r.update(reason='OBSTACLE_STOP')
        bind_intent(r,dict(sequence=12,expires_at_ms=1250,direction='forward'),1000)
        self.assertEqual(r['reason'],'OBSTACLE_STOP')
    def test_lidar_off_stops_movement_but_not_connection(self):
        robot=self.connected();self.send('command',payload=dict(text='앞으로 10cm 이동해'))
        self.send('command',payload=dict(text='라이다 꺼줘'))
        row=self.fleet.robots[robot];self.assertIsNone(row['_task']);self.assertTrue(row['_connected']);self.assertEqual(row['lidar_state'],'OFF')
    def test_stage_change_and_stale_telemetry_cannot_revive_task(self):
        robot=self.connected();self.send('command',payload=dict(text='왼쪽으로 90도'))
        self.now+=1.1;self.fleet.snapshot();self.assertIsNone(self.fleet.robots[robot]['_task'])
        self.report(robot);self.assertEqual(self.fleet.robots[robot]['control_state'],'PAUSED')
    def test_full_turn_is_finite_and_measured_completion_not_acceptance(self):
        robot=self.connected();self.send('command',payload=dict(text='제자리에서 한 바퀴 돌면서 라이다 기록해'))
        task=self.fleet.robots[robot]['_task'];self.assertAlmostEqual(task['amount'],2*math.pi)
        self.assertEqual(self.fleet.robots[robot]['control_state'],'DRIVING')
        self.report(robot,reason='TASK_COMPLETED',position_m=[1,1,2*math.pi])
        self.assertEqual(self.fleet.robots[robot]['reason'],'TASK_COMPLETED');self.assertIsNone(self.fleet.robots[robot]['_task'])
    def test_cold_restore_has_definitions_but_no_authority(self):
        robot=self.connected();self.send('command',payload=dict(text='전진 10cm'))
        self.fleet.close() # Cold normal restart: queued atomic summaries must be drained.
        restored=RobotFleet(Broker(),Path(self.temp.name))
        row=restored.snapshot()['robots'][0];self.assertEqual(row['robot_id'],robot)
        self.assertEqual(row['connection_state'],'DISCONNECTED');self.assertIsNone(row['operation_id'])
        restored.close()

    def test_engine_restart_rotates_connection_and_accepts_new_low_sequence_only(self):
        robot=self.connected();row=self.fleet.robots[robot];old=row['connection_epoch']
        self.report(robot,sequence=100)
        broker=self.fleet.broker;broker.state=deepcopy(broker.state)
        broker.state.update(engine_session_id='new-engine',stage_epoch='new-stage')
        def exchange(value):
            return self.fleet.engine_exchange('new-engine','new-stage',dict(engine_session_id='new-engine',stage_epoch='new-stage',
                report=dict(applied_revision='revision',robots=[value])))
        report=dict(robot_id=robot,connection_epoch=old,motion_epoch=row['motion_epoch'],sequence=101,position_m=[99,99,0])
        exchange(report)
        self.assertNotEqual(row['connection_epoch'],old);self.assertEqual(row['telemetry_sequence'],0)
        self.assertNotEqual(row['pose']['position_m'],[99,99,0]);self.assertIsNone(row['_task'])
        exchange(dict(report,connection_epoch=row['connection_epoch'],motion_epoch=row['motion_epoch'],sequence=1,position_m=[1,1,0]))
        self.assertEqual(row['telemetry_sequence'],1);self.assertEqual(row['connection_state'],'CONNECTED')
        with self.assertRaises(BrokerError):self.report(robot,sequence=999)

    def test_physical_cleanup_does_not_hold_other_robot_stop_or_engine_lock(self):
        robot=self.connected();entered=Event();release=Event();errors=[]
        class Pool:
            def disconnect(self,*args,**kwargs):entered.set();release.wait(3)
            def snapshot(self):return {'robots':[]}
        self.fleet.physical=Pool();identity='physical_fixture'
        self.fleet.robots[identity]=self.fleet._robot(identity,'Offline fixture',[0,0,0],'physical')
        def disconnect():
            try:self.send('disconnect',identity)
            except Exception as error:errors.append(error)
        thread=Thread(target=disconnect);thread.start()
        try:
            self.assertTrue(entered.wait(1))
            done=Event()
            stop=Thread(target=lambda:(self.send('stop',robot),self.report(robot),done.set()));stop.start()
            self.assertTrue(done.wait(1),'Other robot Stop/engine exchange waited for physical cleanup')
            stop.join()
        finally:release.set();thread.join()
        self.assertEqual(errors,[])

    def test_snapshot_disk_stall_never_holds_stop_or_engine_exchange(self):
        robot=self.connected();entered=Event();release=Event();original=Path.write_bytes
        def write(path,data):
            if path.suffix=='.tmp':entered.set();release.wait(3)
            return original(path,data)
        with patch.object(Path,'write_bytes',write):
            self.send('stop',robot);self.assertTrue(entered.wait(1))
            try:
                done=Event();worker=Thread(target=lambda:(self.send('stop',robot),self.report(robot),done.set()));worker.start()
                self.assertTrue(done.wait(1),'Stop/engine waited for disk')
                worker.join()
            finally:release.set()

    def test_snapshot_write_failure_is_incomplete_and_paused_not_disconnected(self):
        robot=self.connected();row=self.fleet.robots[robot]
        self.fleet.snapshot_writer.error='SNAPSHOT_WRITE_FAILED'
        state=self.fleet.snapshot();self.assertTrue(row['_connected'])
        self.assertEqual(state['robots'][0]['control_state'],'PAUSED')
        self.assertEqual(row['recording_state'],'INCOMPLETE')
        self.fleet.snapshot_writer.error=None # allow the fixture to drain its pre-fault writes

    def test_physical_cold_restore_keeps_history_reference_only(self):
        from types import SimpleNamespace
        identity='a'*32;operation='b'*32
        self.fleet.physical_history[identity]=operation;self.fleet.close()
        registry=SimpleNamespace(registration_snapshot=lambda:dict(robots=[dict(id=identity,label='Saved robot')]))
        devices=SimpleNamespace(registry_service=SimpleNamespace(registry=registry),physical_fleet=None)
        restored=RobotFleet(Broker(),Path(self.temp.name),devices=devices)
        try:
            row=restored.snapshot()['robots'][0]
            self.assertEqual(row['last_operation_id'],operation)
            self.assertEqual(row['connection_state'],'DISCONNECTED')
            self.assertIsNone(row['operation_id']);self.assertIsNone(row['connection_epoch'])
            self.assertFalse(row['capabilities']['drive'])
        finally:restored.close()

    def test_late_disconnect_finalizes_captured_operation_not_reconnected_robot(self):
        robot=self.connected();row=self.fleet.robots[robot];old=row['operation_id']
        entered=Event();release=Event();errors=[];original=self.fleet.recorders[old].close
        def close():entered.set();release.wait(3);return original()
        def disconnect():
            try:self.send('disconnect',robot)
            except Exception as error:errors.append(error)
        with patch.object(self.fleet.recorders[old],'close',close):
            thread=Thread(target=disconnect);thread.start();self.assertTrue(entered.wait(1))
            try:
                self.send('connect',robot);new=row['operation_id'];self.assertNotEqual(old,new)
                self.report(robot,sequence=1);self.assertEqual(row['connection_state'],'CONNECTED')
                self.assertEqual(row['recording_state'],'RECORDING')
            finally:release.set();thread.join()
        self.assertEqual(errors,[]);self.assertFalse(self.fleet.recorders[new].closed)
        self.assertEqual(row['recording_state'],'RECORDING')
        self.assertTrue(self.fleet.operation(old)['manifest']['complete'])
        self.assertFalse(self.fleet.operation(new)['manifest']['complete'])

    def test_recorder_close_cannot_overtake_an_admitted_append(self):
        from twinpulse_app.fleet_recorder import FleetRecorder
        recorder=FleetRecorder(Path(self.temp.name)/'close-race.jsonl')
        entered=Event();release=Event();done=Event();receipts=[];original=recorder.queue.put_nowait
        def put(value):entered.set();release.wait(2);return original(value)
        with patch.object(recorder.queue,'put_nowait',put):
            append=Thread(target=lambda:recorder.append(dict(kind='fixture')));append.start()
            self.assertTrue(entered.wait(1))
            close=Thread(target=lambda:(receipts.append(recorder.close()),done.set()));close.start()
            try:self.assertFalse(done.wait(.1),'Close overtook an admitted append')
            finally:release.set();append.join();close.join()
        self.assertTrue(receipts[0]['complete']);self.assertEqual(receipts[0]['accepted'],1)
        self.assertEqual(receipts[0]['saved'],1)
    def test_original_operation_keeps_robot_project_and_source(self):
        robot=self.connected();self.send('command',payload=dict(text='전진 10cm'));self.send('stop',robot)
        record=self.fleet.operation(self.fleet.robots[robot]['operation_id'])
        self.assertEqual(record['robot_id'],robot);self.assertEqual(record['project_id'],'test-project')
        self.assertEqual(record['manifest']['source'],'isaac_kinematic_sim')
        self.assertIn('command_accepted',[event['kind'] for event in record['events']])
        self.send('disconnect',robot)
        final=self.fleet.operation(record['operation_id'])
        self.assertTrue(final['manifest']['complete'])
        self.assertEqual(final['manifest']['journal']['saved'],len(final['events']))
        self.assertEqual(len(final['manifest']['journal']['sha256']),64)
    def test_direct_task_payload_cannot_bypass_bounded_text_and_focus(self):
        robot=self.connected()
        with self.assertRaises(BrokerError):self.send('task',robot,dict(amount=999,direction='forward'))
        second=self.connected('Beta')
        with self.assertRaisesRegex(BrokerError,'Select this robot'):
            self.send('command',robot,payload=dict(text='Alpha 앞으로 10cm'))
        self.assertIsNone(self.fleet.robots[robot]['_task'])
        self.assertIsNone(self.fleet.robots[second]['_task'])
    def test_too_large_request_and_ambiguous_target_do_not_drive(self):
        a=self.connected('Alpha');b=self.connected('Beta')
        with self.assertRaises(BrokerError):self.send('command',payload=dict(text='Alpha와 Beta 앞으로 10cm'))
        with self.assertRaises(BrokerError):self.send('command',payload=dict(text='전진 100m'))
        self.assertIsNone(self.fleet.robots[a]['_task']);self.assertIsNone(self.fleet.robots[b]['_task'])


class CommandTests(unittest.TestCase):
    def test_metric_and_angular_units(self):
        self.assertAlmostEqual(parse_robot_command('앞으로 10cm 이동해')['amount'],.1)
        self.assertAlmostEqual(parse_robot_command('turn right 90 degrees')['amount'],math.pi/2)
        self.assertEqual(parse_robot_command('모든 로봇 정지')['action'],'stop_all')
        self.assertEqual(parse_robot_command('Alpha 로봇 멈춰')['action'],'stop')
        self.assertEqual(parse_robot_command('Beta stop')['action'],'stop')
        self.assertEqual(parse_robot_command('모든 로봇 정지해줘')['action'],'stop_all')
        self.assertAlmostEqual(parse_robot_command('turn left 90°')['amount'],math.pi/2)
    def test_ordinary_scene_edits_not_robot_tasks(self):
        self.assertIsNone(parse_robot_command('침대를 만들어줘'))
        self.assertIsNone(parse_robot_command('6m x 5m 방을 만들어줘. 왼쪽에 침대와 로봇 2대를 배치해줘'))
    def test_unbounded_directions_need_extent(self):
        with self.assertRaises(BrokerError):parse_robot_command('계속 전진해')
