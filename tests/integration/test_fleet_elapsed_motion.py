"""Pure SIM integration regressions, not actual Isaac or physical acceptance."""
import math
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from scripts.twinpulse_fleet_runtime import integrate_motion, FleetRuntime, bind_intent


class ElapsedMotionTests(unittest.TestCase):
    def test_original_90_and_360_at_five_fps_preserve_wall_time(self):
        for amount in (math.pi/2,math.pi*2):
            pose=[0.,0.,0.];travel=0.;elapsed=0.
            while travel<amount-1e-12:
                pose,delta,reason,steps=integrate_motion(pose,'left',.2,[],amount-travel)
                self.assertIsNone(reason);self.assertLessEqual(steps,4)
                travel+=delta;elapsed+=.2
            self.assertAlmostEqual(pose[2],amount)
            self.assertLess(elapsed,amount/.30+5.) # Unchanged task deadline.

    def test_runtime_stall_is_not_caught_up_even_with_a_fresh_transport(self):
        for elapsed in (.5,1.,60.,float('nan')):
            pose,travel,reason,steps=integrate_motion([1.,2.,0.],'forward',elapsed,[])
            self.assertEqual(pose,[1.,2.,0.]);self.assertEqual(travel,0.)
            self.assertEqual(reason,'INPUT_STALE');self.assertEqual(steps,0)

    def test_collision_checked_each_substep_and_fresh_reverse_can_escape(self):
        box=(.22,-1.,.5,1.)
        pose,travel,reason,steps=integrate_motion([0.,0.,0.],'forward',.4,[box])
        self.assertEqual(reason,'OBSTACLE_STOP');self.assertLess(travel,.02)
        escaped,delta,reason,_=integrate_motion(pose,'backward',.2,[box])
        self.assertIsNone(reason);self.assertLess(escaped[0],pose[0]);self.assertGreater(delta,0)

    def test_final_step_never_overshoots_and_zero_admission_does_not_move(self):
        pose,travel,reason,_=integrate_motion([0.,0.,0.],'right',.2,[],.01)
        self.assertAlmostEqual(travel,.01);self.assertAlmostEqual(pose[2],-.01)
        self.assertIsNone(reason)
        self.assertEqual(integrate_motion([1.,1.,1.],'forward',0.,[]),([1.,1.,1.],0.,None,0))


class RuntimeAdmissionTests(unittest.TestCase):
    """Actual update with USD stubs, not a real Isaac/hardware acceptance."""
    def tick(self,*,old=None,start=None,direction='forward',received=10.39,dt=.4,prior_task=None):
        class Op:
            def __init__(self,value):self.value=value
            def Set(self,value):self.value=value
            def Get(self):return self.value
        ops=[Op([0.,0.,0.]),Op(0.)]
        placement=SimpleNamespace(GetOrderedXformOps=lambda:ops,
            ComputeLocalToWorldTransform=lambda _:SimpleNamespace(ExtractTranslation=lambda:ops[0].value))
        stage=SimpleNamespace(GetPrimAtPath=lambda _:True)
        omni=SimpleNamespace(usd=SimpleNamespace(get_context=lambda:SimpleNamespace(get_stage=lambda:stage)))
        pxr=SimpleNamespace(Gf=SimpleNamespace(Vec3d=lambda *v:list(v)),UsdGeom=SimpleNamespace(Xform=lambda _:placement))
        runtime=FleetRuntime();runtime.identity=('engine','stage','revision');runtime.updated_at=10.4-dt;runtime.scan_at=10.4
        row=dict(epoch='connection',motion_epoch='motion',pose=[0.,0.,0.],reason=None,task=prior_task,travel=0.,scan=None,scan_at=10.4,
            intent_sequence=old['sequence'] if old else None,last_intent=old,intent_active_since=start,stale_intent_sequence=None)
        runtime.robots={'robot':row}
        incoming=dict(sequence=(old['sequence']+1 if old else 1),direction=direction,expires_at_ms=1000650)
        with patch.dict(sys.modules,{'omni':omni,'omni.usd':omni.usd,'pxr':pxr}),patch('scripts.twinpulse_fleet_runtime.time.monotonic',return_value=10.4),patch('scripts.twinpulse_fleet_runtime.time.time',return_value=1000.4):
            runtime.receive(dict(applied_revision='revision',robots=[dict(robot_id='robot',connection_epoch='connection',motion_epoch='motion',
                intent=incoming,lidar=False)]),received_at=received)
            runtime.update(SimpleNamespace(engine_session_id='engine',stage_epoch='stage',applied_revision='revision'))
        return runtime.report[0],row

    def test_first_input_and_direction_change_do_not_backdate_previous_tick(self):
        for old in (None,dict(sequence=1,direction='backward',expires_at_ms=1000500)):
            report,_=self.tick(old=old,start=9.)
            self.assertAlmostEqual(report['position_m'][0],.05*.01)
            self.assertAlmostEqual(report['runtime_timing']['integrated_s'],.01)

    def test_expired_gap_is_not_filled_by_same_direction_renewal(self):
        report,_=self.tick(old=dict(sequence=1,direction='forward',expires_at_ms=1000100),start=9.)
        self.assertAlmostEqual(report['position_m'][0],.05*.01)

    def test_continuous_renewal_preserves_full_eligible_time(self):
        report,_=self.tick(old=dict(sequence=1,direction='forward',expires_at_ms=1000500),start=9.)
        self.assertAlmostEqual(report['position_m'][0],.05*.4)
        self.assertEqual(report['runtime_timing']['substeps'],8)

    def test_fresh_input_never_conceals_full_main_thread_stall(self):
        report,_=self.tick(dt=.5)
        self.assertEqual(report['position_m'],[0.,0.,0.]);self.assertEqual(report['reason'],'INPUT_STALE')

    def test_same_or_lower_sequence_cannot_change_admission_or_expiry(self):
        old=dict(sequence=2,direction='forward',expires_at_ms=1000500)
        row=dict(intent_sequence=2,last_intent=old,intent_active_since=9.)
        bind_intent(row,dict(sequence=1,direction='backward',expires_at_ms=9999999),1000400,received_at=10.39,now=10.4)
        self.assertEqual(row['intent_active_since'],9.);self.assertEqual(row['last_intent'],old)

    def test_task_gap_breaks_manual_coverage_and_manual_clears_old_task_id(self):
        old=dict(sequence=1,direction='forward',expires_at_ms=1000500)
        row=dict(last_intent=old,intent_sequence=1,intent_active_since=9.)
        bind_intent(row,None,1000300,received_at=10.3,now=10.3)
        self.assertIsNone(row['last_intent']);self.assertIsNone(row['intent_active_since'])
        self.assertEqual(row['intent_sequence'],1)
        report,_=self.tick(old=row['last_intent'],start=row['intent_active_since'],prior_task='superseded-task')
        self.assertAlmostEqual(report['position_m'][0],.05*.01);self.assertIsNone(report['task_id'])

    def test_intermediate_io_task_or_direction_break_survives_single_render_tick(self):
        for middle in (None,dict(sequence=2,direction='backward',expires_at_ms=1000500)):
            runtime=FleetRuntime();runtime.identity=('e','s','r')
            row=dict(epoch='c',motion_epoch='m',intent_sequence=1,last_intent=dict(sequence=1,direction='forward',expires_at_ms=1000500),
                intent_active_since=9.,reason=None)
            runtime.robots={'robot':row}
            def state(intent):return dict(applied_revision='r',robots=[dict(robot_id='robot',connection_epoch='c',motion_epoch='m',intent=intent)])
            with patch('scripts.twinpulse_fleet_runtime.time.monotonic',return_value=10.4),patch('scripts.twinpulse_fleet_runtime.time.time',return_value=1000.4):
                runtime.receive(state(middle),received_at=10.08)
                runtime.receive(state(dict(sequence=3,direction='forward',expires_at_ms=1000650)),received_at=10.39)
            self.assertAlmostEqual(row['intent_active_since'],10.39)
