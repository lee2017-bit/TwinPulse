# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import copy
import math
import unittest
from twinpulse_core.sensor_photo_link import link_sensor_to_photo, preview_link_goal, photo_wall_anchors
from twinpulse_core.room_localization import compose,inverse


def fixture():
    transform=[.4,-.2,.7];source=[[0,0],[2,0],[0,1],[2,1]]
    sensor={'status':'SENSOR_MAP_GEOMETRIC_CANDIDATE','reference_endpoint_cells':[[*p,2,i,i+1] for i,p in enumerate(source)],
        'best_diagnostic_hypothesis':{'reference_from_query_odom_candidate':[.3,.2,.4],'sensor_pose_reference_candidate':[.5,.2,.4]},
        'overlays':[{'frame':3,'points':source,'sensor_pose_reference_candidate':[.5,.2,.4]}]}
    context={'reference_kind':'PHOTO_APPROXIMATION_NOT_METRIC_REFERENCE',
        'anchors':[{'id':str(i),'xy_m':compose(transform,[*p,0])[:2]} for i,p in enumerate(source)],
        'outline':{'bounds_m':[-3,3,-3,3],'segments':[]}}
    pairs=[{'endpoint_index':i,'anchor_id':str(i),'role':'fit' if i<3 else 'validation'} for i in range(4)]
    return sensor,context,pairs,transform


class LinkTests(unittest.TestCase):
    def test_proper_transform_and_historical_goal_without_authority_or_mutation(self):
        sensor,context,pairs,transform=fixture();before=copy.deepcopy((sensor,context,pairs))
        result=link_sensor_to_photo(sensor,context,pairs)
        self.assertEqual(result['status'],'APPROXIMATE_VISUAL_LINK_CANDIDATE')
        for a,b in zip(result['room_from_reference_candidate'],transform):self.assertAlmostEqual(a,b)
        self.assertLess(result['validation_max_residual_m'],1e-12)
        self.assertEqual(result['scale'],1.);self.assertEqual(result['rotation_determinant'],1.)
        self.assertFalse(result['alignment_verified']);self.assertFalse(result['motion_authorized'])
        self.assertFalse(result['correspondences_verified']);self.assertEqual((sensor,context,pairs),before)
        target=[.1,.2];goal=preview_link_goal(result,target)
        expected=compose(inverse(compose(transform,[.3,.2,.4])),[*target,0])[:2]
        self.assertEqual(goal['query_odom_goal_candidate_m'],expected);self.assertIsNone(goal['mission_request'])

    def test_validation_is_not_fitted_and_rejects_a_bad_held_out_point(self):
        sensor,context,pairs,_=fixture()
        context['anchors'][3]['xy_m'][0]+=.4
        result=link_sensor_to_photo(sensor,context,pairs)
        self.assertEqual(result['status'],'ANCHOR_MISMATCH');self.assertLess(result['fit_rms_m'],1e-12)
        self.assertAlmostEqual(result['validation_max_residual_m'],.4);self.assertIsNone(result['sensor_pose_room_candidate'])
        with self.assertRaisesRegex(ValueError,'ANCHORS_NOT_CONSISTENT'):preview_link_goal(result,[0,0])

    def test_scale_and_reflection_are_not_silently_corrected(self):
        for mode in ('scale','mirror'):
            sensor,context,pairs,_=fixture()
            for a in context['anchors']:
                if mode=='scale':a['xy_m']=[v*1.4 for v in a['xy_m']]
                else:a['xy_m'][1]*=-1
            with self.subTest(mode=mode):
                result=link_sensor_to_photo(sensor,context,pairs)
                self.assertEqual(result['status'],'ANCHOR_MISMATCH');self.assertEqual(result['scale'],1.)

    def test_pair_identity_role_conditioning_and_candidate_are_required(self):
        for change,reason in (('ambiguous','NOT_UNIQUE'),('short','REQUIRES_3_FIT'),('duplicate','DUPLICATE'),
                              ('unknown','NOT_CURRENT'),('boolean','NOT_RECORDED'),('shape','PAIR_SHAPE'),
                              ('roles','REQUIRES_3_FIT'),('nan','POINT_VALUE'),('line','COLLINEAR')):
            sensor,context,pairs,_=fixture()
            if change=='ambiguous':sensor['status']='AMBIGUOUS'
            if change=='short':pairs.pop()
            if change=='duplicate':pairs[1]=dict(pairs[0])
            if change=='unknown':pairs[0]['anchor_id']='unknown'
            if change=='boolean':pairs[0]['endpoint_index']=True
            if change=='shape':pairs[0]['target_xy_m']=[99,99]
            if change=='roles':pairs[3]['role']='fit'
            if change=='nan':context['anchors'][0]['xy_m'][0]=math.nan
            if change=='line':sensor['reference_endpoint_cells'][2][:2]=[1,0]
            with self.subTest(change=change),self.assertRaisesRegex(ValueError,reason):link_sensor_to_photo(sensor,context,pairs)

    def test_goal_invalid_bounds_and_wall_only_nominal_source(self):
        sensor,context,pairs,_=fixture();result=link_sensor_to_photo(sensor,context,pairs)
        for goal in ([math.nan,0],[True,0],[9,0]):
            with self.subTest(goal=goal),self.assertRaises(ValueError):preview_link_goal(result,goal)
        def box(name,kind,p,d):return {'id':name,'kind':kind,'transform':{'position_m':p},'shape':{'dimensions_m':d}}
        objects=[box('floor','floor',[0,0,-.02],[4,4,.04]),box('chair','chair',[0,0,.3],[.5,.5,.6]),
            box('wall_left','wall',[-2,0,1],[.04,4,2]),box('wall_right','wall',[2,0,1],[.04,4,2]),
            box('wall_window','wall',[0,2,1],[4,.04,2])]
        context=photo_wall_anchors(objects,.182)
        self.assertEqual(len(context['anchors']),12)
        self.assertTrue(all(a['object_id'].startswith('wall_') for a in context['anchors']))
        self.assertEqual(context['reference_kind'],'PHOTO_APPROXIMATION_NOT_METRIC_REFERENCE')
