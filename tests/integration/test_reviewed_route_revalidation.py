# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Conservative candidate admission, no device or measured accuracy claim."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock
import unittest

from twinpulse_core.current_goal_preview import goal_preview,check_preview
from twinpulse_core.bounded_grid_plan import plan_bounded_grid
from twinpulse_core.revisions import canonical_sha256
from twinpulse_app.remote_observed_adapter import RemoteObservedFactory
from tests.integration import test_current_goal_preview as preview_tests
from tests.integration.test_current_goal_preview import evidence
from tests.integration.test_scene_changes import room_source


class ReviewedRouteTests(preview_tests.CurrentGoalPreviewTests):
    # Inherit all v1 regressions, which retain their exact binding semantics.
    def v2(self):return self.preview(revalidate_route=True)['plan']

    def checked(self,plan):
        return check_preview(plan,self.current,self.context,1.,plan['goal_contract'])

    def test_small_jitter_and_unrelated_cells_keep_exact_reviewed_waypoints(self):
        plan=self.v2()
        for dx,yaw in ((0.,0.),(.001,.001),(.009,.019)):
            self.current=evidence();self.current['pose_map'][0]+=dx;self.current['pose_map'][2]+=yaw
            self.current['map_revision']='f'*64;self.current['cells'][0][2]='occupied'
            self.assertEqual(self.checked(plan),plan)
        legacy=self.preview()['plan'];self.current['pose_map'][0]+=.000001
        with self.assertRaisesRegex(ValueError,'START_MAP_OR_SOURCE_CHANGED'):self.checked(legacy)

    def test_pose_envelope_source_transform_footprint_and_freshness_still_block(self):
        plan=self.v2()
        faults=({'pose_map':[.011,-1.8,0.]},{'pose_map':[0.,-1.8,.021]},
            {'room_from_map':[.001,0.,0.]},{'alignment_revision':'f'*64},
            {'room_revision':'f'*64},{'footprint_radius_m':.181},
            {'epoch':2},{'source_revision':'f'*64},{'sample_s':.8},{'state':'LOST'})
        for change in faults:
            self.current=evidence();self.current.update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):self.checked(plan)

    def test_only_session_id_may_change_after_new_owned_observation(self):
        self.current.update(session_id='old',boot_id='boot',release_id='e'*64,origin='live_ros')
        self.context={k:self.current[k] for k in ('project_id','source_revision','epoch','session_id','boot_id','release_id','origin')}
        plan=self.v2();self.current['session_id']='new';self.context['session_id']='new'
        self.assertEqual(self.checked(plan),plan)
        for key in ('boot_id','release_id','origin','project_id','epoch','source_revision'):
            before=deepcopy(self.current);context=deepcopy(self.context)
            self.current[key]=2 if key=='epoch' else 'changed';self.context[key]=self.current[key]
            with self.subTest(key=key),self.assertRaises(ValueError):self.checked(plan)
            self.current=before;self.context=context

    def test_full_route_unknown_occupied_absent_and_conflicts_block(self):
        plan=self.v2()
        for fault in ('unknown','occupied','missing','conflict'):
            self.current=evidence()
            row=next(r for r in self.current['cells'] if abs(r[0]-.15)<.01 and abs(r[1]+1.85)<.01)
            if fault=='missing':self.current['cells'].remove(row)
            elif fault=='conflict':self.current['cells'].append([*row[:2],'occupied',*row[3:]])
            else:row[2]=fault
            with self.subTest(fault=fault),self.assertRaises(ValueError):self.checked(plan)

    def test_admission_tamper_cannot_be_rehashed_into_weaker_policy(self):
        plan=self.v2();plan['admission']['max_start_delta_m']=.5
        plan['plan_id']=canonical_sha256({k:v for k,v in plan.items() if k!='plan_id'})
        with self.assertRaisesRegex(ValueError,'ADMISSION_CHANGED'):self.checked(plan)

    def test_numerical_endpoint_gap_checked_not_replaced_or_physical_slack(self):
        route=((.15+2e-16,-1.8),)
        value=plan_bounded_grid((0.,-1.8),(.15,-1.8),(-3.,3.,-3.,3.),resolution=.10,clearance=.276,checked_route=route)
        self.assertEqual(value,route)
        with self.assertRaisesRegex(ValueError,'REVIEWED_ROUTE_INVALID'):
            plan_bounded_grid((0.,-1.8),(.15,-1.8),(-3.,3.,-3.,3.),resolution=.10,clearance=.276,checked_route=((.150001,-1.8),))

    def test_added_margin_blocks_more_not_less_than_existing_clearance(self):
        args=((0.,-1.8),(.15,-1.8),(-3.,3.,-3.,3.))
        route=((.15,-1.8),);discs=((.075,-1.528,0.),)
        self.assertEqual(plan_bounded_grid(*args,resolution=.10,clearance=.266,discs=discs,checked_route=route),route)
        with self.assertRaisesRegex(ValueError,'BLOCKED'):
            plan_bounded_grid(*args,resolution=.10,clearance=.276,discs=discs,checked_route=route)

    def test_nonidentity_transform_preserves_exact_sim_goal_and_native_path(self):
        from twinpulse_core.room_localization import compose,inverse
        from twinpulse_core.goal_simulation import make_goal_simulation
        self.current['room_from_map']=[.2,.1,.13]
        self.current['pose_map']=compose(inverse(self.current['room_from_map']),[0.,-1.8,0.])
        plan=self.v2();self.assertEqual(plan['route'][-1],plan['goal'])
        self.assertEqual(make_goal_simulation(self.scene,plan,{'fixture':'a'*64})['route'],plan['route'])
        self.assertEqual(self.checked(plan),plan)

    def test_first_tick_and_first_nonzero_recheck_reject_outside_envelope(self):
        plan=self.v2();mission=self.mission(plan);self.current['pose_map'][0]+=.011
        result=self.step(mission,1.)
        self.assertFalse(result['allowed']);self.assertEqual(result['linear_m_s'],0.)
        self.current=evidence();mission=self.mission(plan);self.step(mission,1.)
        mission.last_evidence['pose_map'][0]+=.011
        with self.assertRaisesRegex(ValueError,'OUTSIDE_REVIEW_ENVELOPE'):mission.validate_first_output(1.)


class ParkedReviewTests(unittest.TestCase):
    def setUp(self):
        self.current=evidence();self.context={k:self.current[k] for k in ('project_id','source_revision','epoch')}
        self.plan=goal_preview(room_source().site.scene,'Go x=.15 y=-1.8',self.current,self.context,1.,revalidate_route=True)['plan']
        self.state={'busy':True,'cleanup_confirmed':True,'sensor_cleanup_confirmed':True}
        controller=SimpleNamespace(snapshot=lambda _:self.state,
            mission_scope={'reference':{'payload':{},'revision':'a'*64}})
        self.factory=RemoteObservedFactory(controller,None,'goal_room')
        self.factory.owns_idle=lambda owner,key:owner=='owner' and key=='key' and self.state['busy']
        self.factory.preview_current=Mock(return_value={'evidence':self.current,'context':self.context})
        self.factory.clock=lambda:1.;self.factory.idle_job='old'
        self.factory.close_idle=Mock(side_effect=lambda _=None:self.state.update(busy=False))

    def test_cleanup_confirmed_before_memory_reservation_owner_cancel_and_close(self):
        f=self.factory;f.park_review('owner','key',self.plan)
        self.assertTrue(f.owns_review('owner','key',self.plan));self.assertFalse(f.owns_review('other','key',self.plan))
        f.discard_review('other');self.assertTrue(f.owns_review('owner','key',self.plan))
        changed=deepcopy(self.plan);changed['goal'][0]+=.001
        self.assertFalse(f.owns_review('owner','key',changed))
        self.state['busy']=True;self.assertFalse(f.owns_review('owner','key',self.plan));self.state['busy']=False
        f.close();self.assertIsNone(f.parked_review)

    def test_cleanup_failure_has_no_reservation_or_resume(self):
        self.state['sensor_cleanup_confirmed']=False
        with self.assertRaisesRegex(ValueError,'CLEANUP_NOT_CONFIRMED'):self.factory.park_review('owner','key',self.plan)
        self.assertIsNone(self.factory.parked_review)
        with self.assertRaisesRegex(ValueError,'RESERVATION_CHANGED'):self.factory.resume_review('owner','key',self.plan)

    def test_changed_reference_consumes_reservation_without_new_worker(self):
        f=self.factory;f.park_review('owner','key',self.plan)
        f.reference_loader=Mock(side_effect=ValueError('RAW_REFERENCE_CHANGED'))
        before=f.preview_current.call_count
        with self.assertRaisesRegex(ValueError,'RAW_REFERENCE_CHANGED'):f.resume_review('owner','key',self.plan)
        self.assertIsNone(f.parked_review);self.assertEqual(f.preview_current.call_count,before)
        with self.assertRaisesRegex(ValueError,'RESERVATION_CHANGED'):f.resume_review('owner','key',self.plan)


if __name__=='__main__':unittest.main()
