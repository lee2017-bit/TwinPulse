# SPDX-License-Identifier: Apache-2.0
"""Device-free contracts: simulated native packets, no robot/Isaac/model PASS."""
from copy import deepcopy
import math
from pathlib import Path
from threading import RLock
from types import SimpleNamespace
import tempfile
import time
import unittest
from unittest.mock import patch
from uuid import uuid4
from tests.integration import test_r5_product_api
from tests.integration.test_robot_fleet import Broker
from twinpulse_core.physical_task_observation import StationaryTaskCollector,wheel_se2,checked_observation,BASIS
from twinpulse_core.revisions import canonical_sha256
from twinpulse_core.robot_timing_profile import DEFAULTS
from twinpulse_app.physical_task_map import PhysicalTaskMap
from twinpulse_app.robot_task_service import RobotTaskService
from twinpulse_app.robot_fleet import parse_robot_command
from twinpulse_app.physical_live_session import PhysicalLiveSession
from twinpulse_app.command_broker import BrokerError
from tests.integration.test_robot_tasks import plan


CTX=dict(operation_id='a'*32,robot_id='b'*32,project_id='project-a',connection_epoch='c'*32,
    boot_id='d'*32,release_id='e'*64,worker_sha256='f'*64)
CFG=dict(schema='supervised-field-test-1.0',robot_id=CTX['robot_id'],binding_sha256='0'*64,
    provenance='operator_reviewed',axes_reviewed=True,angle_sign=1,footprint_radius_m=.12,
    sensor_x_m=-.032,sensor_y_m=0.,sensor_yaw_rad=0.,wheel_metres_per_tick=.0001,wheel_separation_m=.16)
TIMING=dict(DEFAULTS,native_receipt_ms=1000,odom_source_ms=1000,wheel_interval_ms=500)


def pose(x=0.,y=0.,yaw=0.,stamp=10.6):
    return dict(position_m=[x,y,.07],yaw_rad=yaw,source='wheel_odom',independent_body=False,frame_id='odom',sample_s=stamp)


def ring(sequence=1,start=10.3,end=10.5):
    return dict(stream_id='native-stream',frame_sequence=sequence,raw_sha256=canonical_sha256(['raw',sequence]),
        nodes_sha256=canonical_sha256(['nodes',sequence]),complete=True,interval_fallback=False,
        source_byte_span=dict(start=0,end=2000),timing=dict(receipt_start_s=start,receipt_end_s=end,
            acquisition_earliest_s=None,acquisition_latest_s=None,basis='serial_receipt_unqualified'))


def points(p=(0,0,0)):
    # Actual fixture rays to fixed square walls, not a moving circular map.
    result=[]
    for i in range(360):
        angle=math.tau*i/360+p[2];dx,dy=math.cos(angle),math.sin(angle)
        distances=[(edge-p[0])/dx for edge in (-2.,2.) if abs(dx)>1e-8 and (edge-p[0])/dx>0]
        distances += [(edge-p[1])/dy for edge in (-2.,2.) if abs(dy)>1e-8 and (edge-p[1])/dy>0]
        d=min(distances);result.append([d*math.cos(angle-p[2]),d*math.sin(angle-p[2])])
    return result


def packet(p=None,sequence=1,epoch='pose-epoch',motion='motion',now=10.7,context=None,config=None):
    p=p or pose();collector=StationaryTaskCollector(context or CTX);collector.epoch=epoch;collector.zero_since=now-1;collector.zero_epoch=(motion,0)
    rows=[dict(t=now-.6+i*.1,source_age_s=0.,encoders=[0,0]) for i in range(7)]
    p=dict(p,sample_s=now-.05)
    return collector.sample(p,ring(sequence,now-.4,now-.2),points(wheel_se2(p)),rows,config or CFG,now,motion,disabled=True,timing_values=TIMING)


def row(p=None,sequence=1,motion='motion',now=10.7):
    p=p or pose();v=packet(p,sequence,motion=motion,now=now)
    return dict(**{k:CTX[k] for k in ('robot_id','operation_id','connection_epoch','project_id')},kind='physical',
        connection_state='CONNECTED',control_state='PAUSED',motion_epoch=motion,applied_motion_epoch=motion,
        pose=dict(p,sample_s=now-.05),device_boot_id=CTX['boot_id'],device_release_id=CTX['release_id'],
        task_local_state=dict(pose_epoch=v['pose_epoch'],fault=None,pose_valid=True),task_local_observation=v,task_observation_age_ms=200.,
        timing_values=TIMING,lidar_state='STREAMING',recording_state='RECORDING',live_heartbeat=True,_task_snapshot_started_at=now,
        capabilities=dict(drive=True),field=dict(config=CFG,armed=True,remaining_s=900.,stop_receipt={'bootstrap':'not-current-stop'},
            tracking=dict(status='INCONCLUSIVE',accuracy='UNQUALIFIED')),
        command=None,stop_receipt=None)


class NativeTaskPairTests(unittest.TestCase):
    def test_height_is_not_yaw_and_original_timing_is_not_promoted(self):
        self.assertEqual(wheel_se2(pose(12.,24.,.9)),[12.,24.,.9])
        value=packet();self.assertEqual(checked_observation(value)['scope'],BASIS)
        self.assertEqual(value['scan']['timing']['basis'],'serial_receipt_unqualified')
        self.assertFalse(value['independent_body']);self.assertFalse(value['deskewed'])
        bad=deepcopy(value);bad['points_base'][0][0]+=1
        with self.assertRaises(ValueError):checked_observation(bad)

    def test_ring_requires_post_stop_encoder_brackets(self):
        c=StationaryTaskCollector(CTX)
        r=[dict(t=10.2+i*.1,source_age_s=0,encoders=[0,0]) for i in range(5)]
        with self.assertRaisesRegex(ValueError,'POST_STOP'):c.sample(pose(),ring(),points(),r,CFG,10.7,'m',disabled=True,timing_values=TIMING)
        c.zero_since=10.;c.zero_epoch=('m',0)
        self.assertTrue(c.sample(pose(),ring(),points(),r,CFG,10.7,'m',disabled=True,timing_values=TIMING))
        r[2]['encoders']=[1,0]
        with self.assertRaisesRegex(ValueError,'NOT_STATIONARY'):c.sample(pose(),ring(),points(),r,CFG,10.7,'m',disabled=True,timing_values=TIMING)
        with self.assertRaisesRegex(ValueError,'BRACKETS'):c.sample(pose(),ring(),points(),r[-1:],CFG,10.7,'m',disabled=True,timing_values=TIMING)

    def test_odom_reset_is_sticky_not_an_automatic_new_origin(self):
        c=StationaryTaskCollector(CTX);c.zero_since=10.;c.zero_epoch=('m',0)
        r=[dict(t=10.2+i*.1,source_age_s=0,encoders=[0,0]) for i in range(5)]
        c.sample(pose(),ring(),points(),r,CFG,10.7,'m',disabled=True,timing_values=TIMING)
        with self.assertRaisesRegex(ValueError,'ORIGIN_CHANGED'):
            c.sample(pose(1,0,0,10.7),ring(),points(),r,CFG,10.8,'m',disabled=True,timing_values=TIMING)
        self.assertEqual(c.status()['fault'],'TASK_ODOM_FRAME_OR_ORIGIN_CHANGED')

    def test_small_post_ring_move_or_new_stop_generation_cannot_reuse_scan_pose(self):
        c=StationaryTaskCollector(CTX);c.zero_since=10.;c.zero_epoch=('m',0)
        rows=[dict(t=10.2+i*.1,source_age_s=0,encoders=[0,0] if i<4 else [1,0]) for i in range(5)]
        with self.assertRaisesRegex(ValueError,'NOT_STATIONARY'):
            c.sample(pose(.001,0,0,10.6),ring(),points(),rows,CFG,10.7,'m',disabled=True,timing_values=TIMING)
        with self.assertRaisesRegex(ValueError,'POST_STOP'):
            c.sample(pose(.001,0,0,10.6),ring(),points(),rows,CFG,10.7,'m',disabled=True,timing_values=TIMING,stop_generation=1)

    def test_live_projection_does_not_restart_age_at_packet_creation(self):
        now=[10.3]
        with tempfile.TemporaryDirectory() as folder:
            s=PhysicalLiveSession(Path(__file__).parents[2],folder,identity=Path('unused'),known_hosts=Path('unused'),clock=lambda:now[0])
            s.context=dict(CTX)
            event=dict(schema='physical-live-event-1.0',**{k:CTX[k] for k in ('operation_id','robot_id','project_id','connection_epoch')},
                sequence=1,kind='heartbeat',robot_monotonic_s=10.3,data=dict(boot_id=CTX['boot_id'],release_id=CTX['release_id'],
                    worker_sha256=CTX['worker_sha256'],task_local_observation=packet(now=10.2),pose=pose(stamp=10.0)))
            s.receive(event);now[0]=10.6
            self.assertAlmostEqual(s.snapshot()['task_observation_age_ms'],600.)
            self.assertAlmostEqual(s.snapshot()['pose_age_ms'],600.)

    def test_idle_stop_has_new_readback_request_not_a_bootstrap_or_old_pause(self):
        from packages.twinpulse_robot_safety.tests.test_finite_execution import FiniteExecutionTests
        _,owner,_,events=FiniteExecutionTests().make()
        calls=[]
        def release():
            calls.append('release');owner.link.enabled=False;owner.link.stop_diagnostic=dict(confirmed=True)
        owner.link.release=release
        for index in (1,2):
            owner._command(dict(action='stop',request_id='stop'+str(index),motion_epoch='epoch'+str(index),payload={}))
            receipt=owner.snapshot()['stop_receipt']
            self.assertEqual(receipt['request_id'],'stop'+str(index));self.assertTrue(receipt['readback']['confirmed'])
            self.assertEqual(owner.snapshot()['applied_motion_epoch'],'epoch'+str(index))
        self.assertEqual(len(calls),2)

    def test_local_map_source_and_freshness_are_pinned_not_usd_or_icp(self):
        now=[10.7];r=row();m=PhysicalTaskMap(*[r[k] for k in ('robot_id','operation_id','connection_epoch')],clock=lambda:now[0])
        value=m.accept(r);self.assertEqual(value['pose'],[0.,0.,0.]);self.assertFalse(m.summary()['world_aligned'])
        self.assertTrue(m.scene(r,lambda:now[0])['observed_cells'])
        with self.assertRaisesRegex(ValueError,'NEW_RING'):m.accept(r)
        now[0]+=1.1
        with self.assertRaisesRegex(ValueError,'FRESH_RING'):m.scene(r,lambda:now[0])
        changed=deepcopy(r);changed['task_local_state']['pose_epoch']='new'
        with self.assertRaisesRegex(ValueError,'EPOCH'):m.pose(changed)
        self.assertEqual(m.origin,[0.,0.,0.])

    def test_snapshot_and_grid_compute_time_never_rejuvenate_source_age(self):
        from twinpulse_app import physical_task_map as module
        now=[10.7]
        with patch.dict(TIMING,native_receipt_ms=500):r=deepcopy(row())
        r['_task_snapshot_started_at']=10.5
        m=PhysicalTaskMap(*[r[k] for k in ('robot_id','operation_id','connection_epoch')],clock=lambda:now[0])
        original=module.EvidenceGrid.insert
        def slow_insert(grid,*args,**kwargs):
            result=original(grid,*args,**kwargs);now[0]+=.1;return result
        with patch.object(module.EvidenceGrid,'insert',new=slow_insert):m.accept(r)
        self.assertEqual(m.accepted_at,10.5)
        self.assertAlmostEqual(m.accepted_at-m.accepted_age_ms/1000,10.3)
        with self.assertRaisesRegex(ValueError,'FRESH_RING_REQUIRED'):m.scene(r,lambda:now[0])

    def test_missing_future_and_nonfinite_pc_source_clock_fail_closed(self):
        for stamp in (None,float('nan'),float('inf'),10.8):
            r=row();r['_task_snapshot_started_at']=stamp
            m=PhysicalTaskMap(*[r[k] for k in ('robot_id','operation_id','connection_epoch')],clock=lambda:10.7)
            with self.assertRaisesRegex(ValueError,'PC_SOURCE_CLOCK_REQUIRED'):m.accept(r)
            self.assertIsNone(m.latest);self.assertIsNone(m.origin)

    def test_bootstrap_receipt_is_not_current_stop_confirmation(self):
        r=row();pin=dict(request_id='stop-request',operation_id=r['operation_id'],connection_epoch=r['connection_epoch'],motion_epoch=r['motion_epoch'])
        r['field']['stop_receipt']=dict(pin,stop_readback_confirmed=True)
        self.assertFalse(RobotTaskService._physical_stop_confirmed(r,pin))
        r['stop_receipt']=dict(pin,zero_off_readback_confirmed=True,readback=dict(confirmed=True))
        self.assertTrue(RobotTaskService._physical_stop_confirmed(r,pin))
        r['stop_receipt']['request_id']='other'
        self.assertFalse(RobotTaskService._physical_stop_confirmed(r,pin))

    def test_normal_stop_fence_waits_for_new_ring_but_context_change_is_not_waitable(self):
        original=row();m=PhysicalTaskMap(*[original[k] for k in ('robot_id','operation_id','connection_epoch')],clock=lambda:10.7)
        m.accept(original)
        pending=deepcopy(original);pending['motion_epoch']='new-stop'
        with self.assertRaisesRegex(ValueError,'POST_STOP_RING_PENDING'):m.accept(pending)
        pending['applied_motion_epoch']='new-stop'
        with self.assertRaisesRegex(ValueError,'POST_STOP_RING_PENDING'):m.accept(pending)
        changed=deepcopy(pending);changed['field']['config']['sensor_x_m']+=.01
        with self.assertRaisesRegex(ValueError,'CONTEXT_CHANGED'):m.accept(changed)
        pending['task_local_observation']=packet(sequence=2,motion='new-stop')
        self.assertTrue(m.accept(pending))

    def test_revoked_task_is_checked_at_queue_and_last_wire_admission(self):
        with tempfile.TemporaryDirectory() as folder:
            s=PhysicalLiveSession(Path(__file__).parents[2],folder,identity=Path('unused'),known_hosts=Path('unused'))
            s.context=dict(CTX);s.last={};s.at=time.monotonic();s.watch_ack_at=s.at;live=[False]
            with self.assertRaisesRegex(BrokerError,'expired'):
                s.command('lidar',dict(enabled=True),motion_epoch='m',request_id='r',admission_guard=lambda _:live[0])
            live[0]=True
            s.command('lidar',dict(enabled=True),motion_epoch='m',request_id='r',admission_guard=lambda _:live[0])
            item=s.writes.get_nowait();live[0]=False
            self.assertFalse(s._claim_task_packet(item));self.assertIsNone(s.process)


class FakePhysicalFleet:
    def __init__(self,root):
        self.root=Path(root);self.lock=RLock();self.broker=Broker();self.broker._lock=RLock();self.broker.has_pending_operations=lambda:False
        self.row=row(now=time.monotonic());self.focused=self.row['robot_id'];self.robots={self.focused:self.row};self.sequence=1;self.sent=[]
        self.navigation_scene=None
    def snapshot(self):
        with self.lock:
            now=time.monotonic()
            self.sequence+=1;self.row.update(_task_snapshot_started_at=now,task_local_observation=packet(self.row['pose'],self.sequence,motion=self.row['motion_epoch'],now=now))
            return dict(robots=[deepcopy(self.row)],focused_robot_id=self.focused)
    def action(self,body,owner,_task_token=None):
        with self.lock:
            if body['action']=='stop':
                epoch=uuid4().hex;self.row.update(motion_epoch=epoch,applied_motion_epoch=epoch,control_state='PAUSED',
                    stop_receipt=dict(request_id=body['request_id'],operation_id=self.row['operation_id'],connection_epoch=self.row['connection_epoch'],
                        motion_epoch=epoch,zero_off_readback_confirmed=True,readback=dict(confirmed=True)))
            elif body['action']=='command':
                self.task_service.admit(_task_token);self.task_service.admit_motion(body,self.row,None)
                self.sent.append(deepcopy(body));step=parse_robot_command(body['payload']['text']);p=wheel_se2(self.row['pose'])
                if step['direction'] in {'forward','backward'}:
                    d=step['amount']*(1 if step['direction']=='forward' else -1);p[0]+=d*math.cos(p[2]);p[1]+=d*math.sin(p[2])
                else:p[2]+=step['amount']*(1 if step['direction']=='left' else -1)
                self.row['pose']=pose(*p,stamp=time.monotonic())
                self.row['command']=dict(request_id=body['request_id'],state='COMPLETED',reason='TASK_WHEEL_ODOM_TARGET_REACHED',stop_readback_confirmed=True)
            else:raise AssertionError(body)
            return self.snapshot()


class PhysicalTaskExecutionTests(unittest.TestCase):
    def _command_fixture(self,folder):
        f=FakePhysicalFleet(folder);s=RobotTaskService(SimpleNamespace(),f,object());self.addCleanup(s.close)
        r=f.row;s.owner='owner';s.permit=object();s.presence=s.started=time.monotonic();s.expected_epoch=r['motion_epoch']
        s.job=dict(task_id='6'*32,robot_id=r['robot_id'],operation_id=r['operation_id'],connection_epoch=r['connection_epoch'],
            state='RUNNING',plan=plan(),events=[],segments=0,distance_m=0.)
        s.binding=(r['robot_id'],r['connection_epoch'],r['operation_id'],s._scene_binding())
        s.physical_local=PhysicalTaskMap(r['robot_id'],r['operation_id'],r['connection_epoch'])
        s.physical_local.accept(r);s.start_pose=[0.,0.,0.];s.observations=0;s.geometry_records=set();s.distance=0.;s.segments=0
        return f,s

    def test_actual_500ms_policy_refreshes_preplanning_ring_once_before_child(self):
        # The old _command used the planning ring and failed here before send.
        # Source clocks/policy are unchanged; a different real-shaped ring is
        # accepted once before generating the single child request.
        with tempfile.TemporaryDirectory() as folder,patch.dict(TIMING,native_receipt_ms=500):
            f,s=self._command_fixture(folder);old=s.physical_local.latest['packet']['sha256']
            s.physical_local.accepted_at-=.6
            with patch.object(s,'_observe_physical',wraps=s._observe_physical) as observed:
                s._command(dict(op='move_relative',direction='forward',amount=.1))
            self.assertEqual(observed.call_count,1);self.assertEqual(len(f.sent),1)
            child=next(e for e in s.job['events'] if e['kind']=='child_started')
            self.assertNotEqual(child['observation_sha256'],old)
            self.assertEqual(TIMING['native_receipt_ms'],500)
            self.assertEqual(s.segments,1)

    def test_new_ring_expired_by_storage_is_not_restamped_or_retried(self):
        from twinpulse_app import robot_task_service as module
        original=module.atomic_json
        def slow(path,value):
            if path.name.startswith('observation-'):time.sleep(.55)
            return original(path,value)
        with tempfile.TemporaryDirectory() as folder,patch.dict(TIMING,native_receipt_ms=500):
            f,s=self._command_fixture(folder)
            with patch.object(module,'atomic_json',side_effect=slow),patch.object(s,'_observe_physical',wraps=s._observe_physical) as observed:
                with self.assertRaisesRegex(ValueError,'FRESH_RING_REQUIRED'):
                    s._command(dict(op='move_relative',direction='forward',amount=.1))
            self.assertEqual(observed.call_count,1);self.assertEqual(f.sent,[])

    def test_guard_preserves_first_exact_500ms_rejection_without_io(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict(TIMING,native_receipt_ms=500):
            f,s=self._command_fixture(folder);r=f.row;scene=s.physical_local.scene(r,s.clock)
            s.motion_pin=dict(request_id='expired',text='forward 10 cm',pose=[0.,0.,0.],
                observation_sha256=scene['observation_sha256'],produced_at=s.clock()-.6,
                step=dict(direction='forward',amount=.1),geometry=scene['geometry'],fresh_cells=scene['fresh_cells'])
            body=dict(request_id='expired',payload=dict(text='forward 10 cm'))
            with patch.object(s,'_event',side_effect=AssertionError('No I/O under guard')):
                with self.assertRaisesRegex(BrokerError,'Physical task pose or observed map changed'):
                    s.admit_motion(body,r,None)
            first=dict(s.motion_guard_rejections[0])
            self.assertEqual(first['code'],'PINNED_RING_EXPIRED');self.assertEqual(first['source_limit_ms'],500)
            self.assertAlmostEqual(first['source_age_ms'],600,places=4)
            s.revoke('STOP');self.assertFalse(s._physical_motion_guard(s.motion_pin)(r))
            self.assertEqual(s.motion_guard_rejections,[first])
            s._flush_motion_rejections()
            saved=next(e for e in s.job['events'] if e['kind']=='motion_admission_rejected')
            self.assertEqual(saved['code'],first['code']);self.assertEqual(saved['source_age_ms'],first['source_age_ms'])

    def test_rejection_storage_failure_cannot_replace_original_admission_error(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict(TIMING,native_receipt_ms=500):
            f,s=self._command_fixture(folder);r=f.row;scene=s.physical_local.scene(r,s.clock)
            pin=dict(pose=[0.,0.,0.],observation_sha256=scene['observation_sha256'],produced_at=s.clock()-.6,
                step=dict(direction='forward',amount=.1),geometry=scene['geometry'],fresh_cells=scene['fresh_cells'],text='forward 10 cm')
            with patch.object(s,'_event',side_effect=OSError('diagnostic disk failure')):
                with self.assertRaisesRegex(BrokerError,'Physical task pose or observed map changed'):
                    s._send('command',dict(text='forward 10 cm'),motion_pin=pin)
                # The caller attempts Stop BEFORE flushing any diagnostics.
                self.assertIsNone(s.storage_error)
                s._flush_motion_rejections()
            self.assertEqual(s.storage_error,'ROBOT_TASK_STORAGE_FAILED');self.assertEqual(f.sent,[])

    def test_execute_stops_before_diagnostic_io_and_preserves_terminal_primary_error(self):
        with tempfile.TemporaryDirectory() as folder:
            f,s=self._command_fixture(folder);order=[]
            s.job['plan']=plan([dict(op='move_relative',direction='forward',amount=.1)])
            def command(step):
                s.motion_guard_rejections.append(dict(code='PINNED_RING_EXPIRED',checked_at_ms=1,source_age_ms=601,source_limit_ms=500))
                order.append('command');raise BrokerError('robot_task_motion_context_changed','original admission failure',status=409)
            def save():
                order.append('write')
                if 'command' in order:
                    s.storage_error='ROBOT_TASK_STORAGE_FAILED';raise OSError('diagnostic storage failed')
            with patch.object(s,'_stop',side_effect=lambda:order.append('stop')),patch.object(s,'_observe'),patch.object(s,'_command',side_effect=command),patch.object(s,'_save',side_effect=save):
                s._execute()
            after=order[order.index('command')+1:]
            self.assertEqual(after[0],'stop');self.assertEqual(after[1],'write')
            self.assertEqual(s.job['reason'],'original admission failure')
            self.assertEqual(s.job['diagnostic_storage_error'],'ROBOT_TASK_STORAGE_FAILED')
            self.assertEqual(s.job['terminal_save_error'],'ROBOT_TASK_STORAGE_FAILED')
            self.assertEqual(s.job['state'],'FAILED')

    def test_500ms_finite_composition_remains_source_bound(self):
        with patch.dict(TIMING,native_receipt_ms=500):
            self._complete_plan(plan([dict(op='move_relative',direction='forward',amount=.1),
                dict(op='return_to_start'),dict(op='stop')]),'Move forward then return and stop',survey=False)

    def test_real_live_adapter_fleet_projection_and_revocable_task_queue(self):
        with patch.dict(TIMING,native_receipt_ms=500):
            self._real_live_adapter_boundary(expire=False)

    def test_real_500ms_adapter_queued_pin_cannot_refresh_itself_before_wire(self):
        with patch.dict(TIMING,native_receipt_ms=500):
            self._real_live_adapter_boundary(expire=True)

    def _real_live_adapter_boundary(self,*,expire):
        # Real bridge, adapter and fleet classes; synthetic sensor source and
        # no process/SSH/device. Unlike FakePhysicalFleet this exercises the
        # production field projection and both queue-admission guards.
        from tests.integration.test_physical_live_session import FleetPhysicalEnvelopeTests
        env=FleetPhysicalEnvelopeTests('test_physical_payload_complete_and_age_not_replaced_with_sim_private_timestamp')
        env.setUp();self.addCleanup(env.doCleanups)
        env.action('focus');env.action('connect')
        entry=env.pool._entry(env.identity);ctx=dict(env.live.context,worker_sha256=CTX['worker_sha256'])
        now=10.7
        live=PhysicalLiveSession(Path(__file__).parents[2],Path(env.tmp.name)/'actual-live',
            identity=Path('unused'),known_hosts=Path('unused'),clock=lambda:now,wall=lambda:100.,
            process_factory=lambda *a,**k:self.fail('No transport in device-free test'))
        live.context=ctx;live.motion_epoch=entry.motion_epoch;live.watch_ack_at=now
        entry.services.live=live
        config=dict(CFG,robot_id=env.identity,binding_sha256=entry.binding['sha256'])
        source=dict(CTX,**{k:ctx[k] for k in ('robot_id','operation_id','project_id','connection_epoch')})
        observation=packet(now=now,motion=entry.motion_epoch,context=source,config=config)
        data=dict(row(now=now),worker_sha256=ctx['worker_sha256'],boot_id=CTX['boot_id'],release_id=CTX['release_id'],
            motion_epoch=entry.motion_epoch,applied_motion_epoch=entry.motion_epoch,
            drive_ready=True,task_local_observation=observation,field=dict(config=config,armed=True,remaining_s=900.,stop_receipt={'bootstrap':True}))
        if ctx.get('timing_profile_sha256'):data['timing_profile_sha256']=ctx['timing_profile_sha256']
        event=dict(schema='physical-live-event-2.0' if ctx.get('schema')=='physical-live-start-2.0' else 'physical-live-event-1.0',
            **{k:ctx[k] for k in ('operation_id','robot_id','project_id','connection_epoch')},sequence=1,kind='heartbeat',robot_monotonic_s=now,data=data)
        if ctx.get('schema')=='physical-live-start-2.0':event['source_twin_context_id']=ctx['source_twin_context']['context_id']
        live.receive(event)
        projected=env.fleet.snapshot()['robots'][0]
        self.assertEqual(projected['timing_values']['native_receipt_ms'],500)
        self.assertEqual(projected['task_local_observation']['sha256'],observation['sha256'])
        self.assertEqual(projected['device_boot_id'],CTX['boot_id']);self.assertTrue(projected['capabilities']['drive'])
        service=RobotTaskService(SimpleNamespace(),env.fleet,object(),clock=lambda:now);self.addCleanup(service.close)
        service.owner=env.owner;service.permit=object();service.job=dict(task_id='7'*32,robot_id=env.identity,
            operation_id=entry.operation_id,connection_epoch=entry.connection_epoch,state='RUNNING',events=[])
        service.binding=(env.identity,entry.connection_epoch,entry.operation_id,service._scene_binding())
        service.physical_local=PhysicalTaskMap(env.identity,entry.operation_id,entry.connection_epoch,clock=lambda:now)
        projected['_task_snapshot_started_at']=now
        service.physical_local.accept(projected);scene=service.physical_local.scene(projected,lambda:now)
        request=uuid4().hex;text='forward 10 cm'
        service.motion_pin=dict(request_id=request,text=text,pose=[0.,0.,0.],observation_sha256=observation['sha256'],
            produced_at=scene['produced_at'],step=dict(direction='forward',amount=.1),geometry=scene['geometry'],fresh_cells=scene['fresh_cells'])
        env.fleet.action(dict(action='command',request_id=request,robot_id=env.identity,connection_epoch=entry.connection_epoch,
            motion_epoch=entry.motion_epoch,payload=dict(text=text)),env.owner,_task_token=service.permit)
        outgoing=live.writes.get_nowait()
        self.assertEqual(outgoing['action'],'task');self.assertEqual(outgoing['request_id'],request)
        if expire:
            now+=.31
            self.assertFalse(live._claim_task_packet(outgoing))
            failure=service.motion_guard_rejections[0]
            self.assertEqual(failure['code'],'PINNED_RING_EXPIRED')
            self.assertGreater(failure['source_age_ms'],500)
            self.assertEqual(failure['source_limit_ms'],500)
            self.assertEqual(service.physical_local.latest['packet']['sha256'],observation['sha256'])
        else:self.assertTrue(live._claim_task_packet(outgoing))
        self.assertIsNone(live.process)
        # Exact same sensor/pose is not enough after Stop/cancellation revoked
        # its owner. No source/nonce/expiry is renewed to force acceptance.
        service.revoke('TEST_STOP')
        self.assertFalse(service._physical_motion_guard(service.motion_pin)(live.last))
        service.job['state']='CANCELLED'

    def test_exact_stop_and_late_ack_survive_local_pose_fault_and_focus_change(self):
        with tempfile.TemporaryDirectory() as folder:
            f=FakePhysicalFleet(folder);s=RobotTaskService(SimpleNamespace(),f,object());self.addCleanup(s.close)
            s.owner='owner';s.permit=object();r=f.row
            s.job=dict(task_id='2'*32,robot_id=r['robot_id'],operation_id=r['operation_id'],connection_epoch=r['connection_epoch'],state='FAILED',events=[])
            s.physical_local=PhysicalTaskMap(r['robot_id'],r['operation_id'],r['connection_epoch']);s.physical_local.accept(r)
            f.row['task_local_state']['fault']='TASK_ODOM_FRAME_OR_ORIGIN_CHANGED';f.focused=None
            with self.assertRaises(ValueError):s._row()
            s._stop();self.assertIsNone(s.pending_stop)
            pin=dict(f.row['stop_receipt']);pin.pop('readback');pin.pop('zero_off_readback_confirmed');pin.pop('observed_monotonic_s',None)
            s.pending_stop=pin;s.snapshot('owner');self.assertIsNone(s.pending_stop)

    def test_common_survey_return_stop_uses_physical_adapter_without_world_alignment(self):
        self._complete_plan(plan(),'survey and return and stop',survey=True)

    def test_finite_composition_refreshes_each_physical_observation(self):
        self._complete_plan(plan([dict(op='move_relative',direction='forward',amount=.1),
            dict(op='move_relative',direction='left',amount=math.pi/6),dict(op='return_to_start'),dict(op='stop')]),
            'Move forward then turn left then return and stop',survey=False)

    def test_registered_semantic_target_reuses_finite_executor_and_native_free_space(self):
        self._complete_plan(plan([dict(op='observe'),dict(op='navigate',target_kind='sofa'),dict(op='return_to_start'),dict(op='stop')]),
            'Go to the sofa, return to the start and stop',survey=False,registered=True)

    def _complete_plan(self,p,text,*,survey,registered=False):
        with tempfile.TemporaryDirectory() as folder:
            f=FakePhysicalFleet(folder);s=RobotTaskService(SimpleNamespace(),f,object());self.addCleanup(s.close)
            if registered:
                token=object()
                s.spatial_review=SimpleNamespace(registration=token,registration_for=lambda r:dict(_token=token,
                    job_id='9'*32,review_digest='8'*64,world_from_native=[0.,0.,0.]))
                f.navigation_scene=dict(binding=list(s._scene_binding()),produced_at=time.monotonic(),
                    geometry=dict(epoch=1,bounds=[-2.,-2.,2.,2.],obstacles=[],targets=[dict(id='sofa',kind='sofa',label='Sofa',bounds=[.8,-.2,1.,.2])]),
                    observed_cells=[[(x+.5)*.1,(y+.5)*.1,'free',0,0,0,0] for x in range(-20,20) for y in range(-20,20)])
            p['limits'].update(distance_m=2.5,duration_s=600)
            r=f.row;s.owner='owner';s.job=dict(schema_version='robot-task-plan-1.0',task_id='1'*32,request_id='fixture',text=text,
                project_id=f.broker.project_id,robot_id=r['robot_id'],robot_kind='physical',state='READY',plan=p,plan_sha256=canonical_sha256(p),
                source_state_sha256=canonical_sha256(s.source_binding()),proposal_binding=[r['robot_id'],'physical',r['connection_epoch'],r['operation_id'],list(s._scene_binding())],
                events=[],segments=0,distance_m=0.,physical_authority=False,whole_room_coverage_verified=False)
            s.run('owner',s.job['plan_sha256']);deadline=time.monotonic()+20
            while s.worker.is_alive() and time.monotonic()<deadline:s.snapshot('owner');time.sleep(.02)
            self.assertFalse(s.worker.is_alive(),s.job)
            self.assertEqual(s.job['state'],'PARTIAL' if survey else 'COMPLETED',s.job)
            self.assertGreater(len(f.sent),0);self.assertGreater(s.job['measured_coverage']['observations'],2)
            self.assertTrue(any(e['kind']=='return_verified' and e['position_basis']=='WHEEL_LOCAL_ESTIMATE_NOT_INDEPENDENT_BODY' for e in s.job['events']))
            self.assertFalse(s.job['measured_coverage']['independent_body']);self.assertFalse(s.job['whole_room_coverage_verified'])
            self.assertIsNone(s.pending_stop)
            if registered:self.assertEqual(s.job['spatial_review']['job_id'],'9'*32)
            if not survey:
                children=[e for e in s.job['events'] if e['kind']=='child_started']
                self.assertGreaterEqual(s.observations,len(children)+1)
                self.assertEqual(len({e['observation_sha256'] for e in children}),len(children))


if __name__=='__main__':unittest.main()
