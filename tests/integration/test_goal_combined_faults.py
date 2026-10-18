# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Shared App task faults with reactive synthetic scans; not UI/Isaac acceptance."""
from copy import deepcopy
import errno
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from tests.integration import test_automatic_mission_service as fixture
from tests.integration import test_goal_task_loop as task_fixture
from packages.twinpulse_core.tests.test_room_localization import scan_points
from twinpulse_core.cleanup_diagnostics import retain_cleanup
from tests.fixtures.combined_fault_evidence import save


class MovingObstacle(fixture.RaycastAdapter):
    def __init__(self,*args,direction,**kwargs):
        super().__init__(*args,**kwargs);self.direction=direction;self.injected=False
    def observation_points(self):
        outline=deepcopy(self.outline)
        if len(self.sent)>=5:
            self.injected=True;x=self.direction*.25;y=-.6
            vertices=[[x-.02,y-.08],[x+.02,y-.08],[x+.02,y+.08],[x-.02,y+.08]]
            outline['segments'] += [[vertices[i],vertices[(i+1)%4]] for i in range(4)]
        return scan_points(outline,self.world)


class CombinedAppTests(unittest.TestCase):
    def helper(self):
        helper=fixture.AutomaticMissionTests();helper.setUp();self.addCleanup(helper.doCleanups)
        return helper

    def finish(self,helper):
        helper.service.worker.join(80.)
        if helper.service.worker.is_alive():
            helper.service.stop('owner',helper.service.job['job_id'],force=True);helper.service.worker.join(10.)
            self.fail('OFFLINE_COMBINED_FAULT_WALL_TIMEOUT')
        job=helper.service.snapshot('owner')['job'];a=helper.adapters[-1]
        self.assertEqual(a.velocity,(0.,0.));self.assertFalse(job['physical_demo_ready'])
        self.assertFalse(job['worker_active']);self.assertEqual(a.consumed,1)
        if job.get('visual'):
            self.assertIsNone(job['visual']['pose_room']);self.assertFalse(job['visual']['scan_room'])
        return job

    def test_both_directions_dynamic_obstacle_stops_without_frozen_pose(self):
        h=self.helper()
        for direction in (1,-1):
            with self.subTest(direction=direction):
                def factory(prior,room,effective,goal):
                    a=MovingObstacle(prior,room,effective,goal,outline=h.outline,start=[0.,-.6,0. if direction==1 else 3.141592653589793],direction=direction)
                    h.adapters.append(a);return a
                h.service.adapter_factory=factory
                h.service.start('owner',h.map_id,h.goal([direction*.3,-.6]));job=self.finish(h);a=h.adapters[-1]
                self.assertTrue(a.injected);self.assertTrue(any(v or w for _,v,w in a.sent))
                self.assertEqual(job['state'],'FAILED')
                self.assertIn(job['error'],{'OBSERVED_PATH_START_OR_GOAL_BLOCKED','OBSTACLE_IN_SWEPT_ENVELOPE','NO_BOUNDED_OBSERVED_PATH'})
                self.assertLess(abs(a.world[0]),.07)
                save('app-obstacle-'+str(direction).replace('-','minus'),{'job':job,'observations':a.raw,
                    'published_commands':a.sent,'final_world':a.world,'final_velocity':a.velocity,
                    'basis':'OUTPUT_REACTIVE_RAYCAST_WORLD_NOT_ESTIMATOR_POSE_INJECTION'})

    def test_primary_native_fault_cleanup_and_storage_keep_all_three_causes(self):
        h=self.helper();original_open=Path.open
        def factory(prior,room,effective,goal):
            a=fixture.RaycastAdapter(prior,room,effective,goal,outline=h.outline,start=[0.,-.6,0.])
            h.adapters.append(a)
            def safety():
                if len(a.sent)>5:
                    primary=ValueError('INPUT_DEADLINE_EXPIRED')
                    retain_cleanup(primary,'mission_halt',ValueError('STOP_READBACK_UNCONFIRMED'))
                    raise primary
            def close():a.halt();raise ValueError('OWNED_SENSOR_STOP_UNCONFIRMED')
            a.safety=safety;a.close=close;return a
        h.service.adapter_factory=factory
        def full(path,*args,**kwargs):
            if 'automatic-mission' in path.parts and (args[0] if args else kwargs.get('mode','r'))=='x':
                raise OSError(errno.ENOSPC,'SECRET_CANARY')
            return original_open(path,*args,**kwargs)
        with patch.object(Path,'open',full):
            h.service.start('owner',h.map_id,h.goal([.15,-.6]));job=self.finish(h)
        self.assertEqual(job['error'],'INPUT_DEADLINE_EXPIRED')
        self.assertEqual(job['native_cleanup_errors'][0]['code'],'STOP_READBACK_UNCONFIRMED')
        self.assertEqual(job['cleanup_error'],'OWNED_SENSOR_STOP_UNCONFIRMED')
        self.assertEqual(job['report_error'],'MISSION_REPORT_STORAGE_FULL')
        self.assertEqual(job['report_errno'],errno.ENOSPC);self.assertNotIn('SECRET_CANARY',json.dumps(job))
        save('app-native-cleanup-storage',{'job':job,'observations':h.adapters[-1].raw,
            'published_commands':h.adapters[-1].sent,'final_velocity':h.adapters[-1].velocity})

    def test_unknown_and_low_battery_block_current_output_and_preserve_cleanup_cause(self):
        h=self.helper()
        for code in ('TASK_BATTERY_UNAVAILABLE','BATTERY_BUTTON_OR_SOURCE_AGE'):
            with self.subTest(cause=code):
                def factory(prior,room,effective,goal):
                    a=fixture.RaycastAdapter(prior,room,effective,goal,outline=h.outline,start=[0.,-.6,0.])
                    h.adapters.append(a)
                    def safety():
                        if len(a.sent)>5:raise ValueError(code)
                    def close():a.halt();raise ValueError('OWNED_SENSOR_STOP_UNCONFIRMED')
                    a.safety=safety;a.close=close;return a
                h.service.adapter_factory=factory
                h.service.start('owner',h.map_id,h.goal([.15,-.6]));job=self.finish(h)
                self.assertEqual(job['error'],code);self.assertEqual(job['cleanup_error'],'OWNED_SENSOR_STOP_UNCONFIRMED')
                report=json.loads((h.root/'artifacts/automatic-mission/mission_room'/f"{job['job_id']}.json").read_text())
                self.assertEqual(report['error'],code);self.assertEqual(report['cleanup_error'],job['cleanup_error'])
                save('app-'+code.lower().replace('_','-'),{'job':job,'report':report,
                    'observations':h.adapters[-1].raw,'published_commands':h.adapters[-1].sent,
                    'battery_fault_basis':'EXPLICIT_BOARD_SAFETY_FAULT_INJECTION_NOT_MEASURED_VOLTAGE'})


class CombinedTaskTests(unittest.TestCase):
    def test_owner_loss_during_prepare_and_failed_final_cancel_never_confirms(self):
        h=task_fixture.LoopTests();h.setUp();self.addCleanup(h.doCleanups)
        h.delay=True;h.start();self.assertTrue(h.preparing.wait(1.))
        h.loop.owner_seen_s-=3.
        h.nav.cancel=lambda _:(_ for _ in ()).throw(ValueError('OWNED_SENSOR_STOP_UNCONFIRMED'))
        h.release.set();job=h.finish()
        self.assertEqual(job['state'],'FAILED');self.assertEqual(job['error'],'TASK_OWNER_CONNECTION_LOST')
        self.assertEqual(job['cleanup_error'],'OWNED_SENSOR_STOP_UNCONFIRMED');self.assertEqual(h.checks,[])
        save('task-owner-cleanup',{'task':job,'history':h.loop.path.read_text(),
            'prepare_requests':h.inputs,'confirm_checks':h.checks,'basis':'TASK_ADMISSION_DOUBLE'})

    def test_force_preempts_prepare_even_with_journal_end_failure(self):
        h=task_fixture.LoopTests();h.setUp();self.addCleanup(h.doCleanups)
        h.delay=True;h.start();self.assertTrue(h.preparing.wait(1.));original=h.loop._record
        def record(kind,**data):
            if kind=='task_ended':raise OSError(errno.ENOSPC,'test only')
            return original(kind,**data)
        h.loop._record=record;h.loop.stop('owner',True);h.release.set();job=h.finish()
        self.assertEqual(h.checks,[]);self.assertEqual(job['completed_legs'],0)
        self.assertEqual(job['state'],'FAILED');self.assertEqual(job['cleanup_error'],'TASK_JOURNAL_WRITE_FAILED')
        self.assertFalse(job['worker_active']);self.assertFalse(job['motion_authorized'])
        save('task-force-storage',{'task':job,'history':h.loop.path.read_text(),
            'prepare_requests':h.inputs,'confirm_checks':h.checks,'basis':'TASK_ADMISSION_DOUBLE'})


if __name__=='__main__':unittest.main()
