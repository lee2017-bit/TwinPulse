# SPDX-License-Identifier: Apache-2.0
"""Supplementary synthetic truth/negative contracts, not hardware acceptance."""
import hashlib,math,time,unittest
from copy import deepcopy
from unittest.mock import Mock
from twinpulse_core.environment_alignment import StructuralMatcher,body_points,wall_references,reference_check,fixed_split
from twinpulse_core.environment_section import horizontal_section
from twinpulse_core.lidar_geometry import SectionIndex
from twinpulse_core.room_localization import compose
from tests.integration.test_environment_import import source

def room():
    env=source();floor=env['meshes'][0];floor['points_m']=[[0,0,0],[6,0,0],[6,4,0],[0,4,0]];floor['triangles']=[[0,1,2],[0,2,3]]
    env['meshes']=[floor]
    for i,(a,b) in enumerate((((0,0),(6,0)),((6,0),(6,4)),((6,4),(0,4)),((0,4),(0,0)))):
        env['meshes'].append(dict(id='Env_'+hashlib.sha256(str(i).encode()).hexdigest()[:20],source_path='/Source/Wall'+str(i),label='Wall'+str(i),category='wall',
            points_m=[[*a,0],[*b,0],[*b,2],[*a,2]],triangles=[[0,1,2],[0,2,3]],color_rgb=[.5,.5,.5],translation_m=[0,0,0]))
    return env

def samples(env,pose):
    section=horizontal_section(env,.182)
    sensor=compose(pose,[-.032,0,0])
    return SectionIndex([s['ends_m'] for s in section['segments']]).scan(sensor,samples=180)

class AlignmentTests(unittest.TestCase):
    def test_seeded_pose_and_fixed_heldout_recover_synthetic_truth(self):
        env=room();truth=[1.3,1.1,.22];raw=samples(env,truth);points=body_points(raw,[-.032,0,0]);matcher=StructuralMatcher(env,.182,[r['id'] for r in wall_references(env)])
        result=matcher.fit(points,[1.45,.98,.3],raw_sensor_points=raw,extrinsic=[-.032,0,0]);self.assertEqual(result['status'],'GEOMETRIC_REVIEW')
        self.assertLess(math.dist(result['body_pose'][:2],truth[:2]),.005);self.assertLess(abs(result['body_pose'][2]-truth[2]),.003)
        self.assertFalse(set(result['fit_indices'])&set(result['validation_indices']));self.assertFalse(result['physical_authority'])
        self.assertFalse(result['world_registration_verified'])
        self.assertEqual(result['method'],'OPERATOR_SEEDED_FIRST_VISIBLE_WALL_RANGE_1')
    def test_fixed_validation_corruption_is_not_trimmed_into_pass(self):
        env=room();raw=samples(env,[1.3,1.1,.22]);points=body_points(raw,[-.032,0,0]);train,test=fixed_split(points)
        for i in test:raw[i]=[raw[i][0]+2,raw[i][1]+1]
        points=body_points(raw,[-.032,0,0])
        match=StructuralMatcher(env,.182,[r['id'] for r in wall_references(env)]).fit(points,[1.3,1.1,.22],raw_sensor_points=raw,extrinsic=[-.032,0,0])
        self.assertEqual(match['status'],'HELD');self.assertEqual(match['validation']['count'],len(test))
    def test_parallel_walls_are_not_observable(self):
        env=room();points=body_points(samples(env,[1.3,1.1,0]),[-.032,0,0]);refs=wall_references(env)
        matcher=StructuralMatcher(env,.182,[refs[0]['id'],refs[2]['id']]);score=matcher.score(points,list(range(len(points))),[1.3,1.1,0])
        self.assertLess(score['normal_diversity'],.06);self.assertFalse(matcher.passes(score))
    def test_reference_is_exact_span_check_not_scene_calibration(self):
        env=room();ref=wall_references(env)[0]
        ok=reference_check(env,ref['id'],ref['length_m'],'SIM_ONLY');self.assertEqual(ok['status'],'REFERENCE_CONSISTENT');self.assertFalse(ok['whole_scene_scale_verified'])
        self.assertEqual(reference_check(env,ref['id'],ref['length_m']*1.1,'OPERATOR_REFERENCE')['status'],'SCALE_MISMATCH')
    def test_normalization_applies_translation_yaw_sign_once(self):
        raw=[[1.,0.],[0.,1.]]*20
        result=body_points(raw,[.1,.2,math.pi/2],-1)
        self.assertAlmostEqual(result[0][0],.1);self.assertAlmostEqual(result[0][1],1.2)
        self.assertAlmostEqual(result[1][0],1.1);self.assertAlmostEqual(result[1][1],.2)
    def test_original_non_wall_id_and_nonfinite_input_rejected(self):
        env=room()
        with self.assertRaises(ValueError):StructuralMatcher(env,.182,[env['meshes'][0]['id']])
        with self.assertRaises(ValueError):body_points([[float('nan'),0]]*40,[0,0,0])
        self.assertFalse(StructuralMatcher.passes({'count':2,'mean_error_m':0,'inlier_fraction':1,'normal_diversity':.5}))

    def test_pre_fit_visibility_is_independent_of_observed_range(self):
        env=room();raw=samples(env,[1.3,1.1,.22]);m=StructuralMatcher(env,.182,[r['id'] for r in wall_references(env)])
        a=m.structural_indices(raw,[1.4,1.05,.25],[-.032,0,0])
        b=m.structural_indices([[x*.25,y*.25] for x,y in raw],[1.4,1.05,.25],[-.032,0,0])
        self.assertEqual(a,b);self.assertEqual(a['indices'],list(range(180)))

    def test_first_visible_wall_rejects_a_hidden_parallel_face(self):
        env=room();m=StructuralMatcher(env,.182,[r['id'] for r in wall_references(env)])
        # Endpoints sit on the far wall, but an additional near wall hides it.
        raw=[[5.,(i-20)*.01] for i in range(40)];points=body_points(raw,[0,0,0]);pose=[1.,2.,0.]
        m.wall_index=SectionIndex([((3.,0.),(3.,4.)),((6.,0.),(6.,4.))])
        nearest=m.score(points,list(range(40)),pose);first=m.range_score(raw,list(range(40)),pose,[0,0,0])
        self.assertLess(nearest['mean_error_m'],.001);self.assertEqual(first['first_hit_inlier_fraction'],0)

    def test_first_hit_never_discards_foreground_or_missing_rays(self):
        env=room();m=StructuralMatcher(env,.182,[r['id'] for r in wall_references(env)]);raw=[[5.,0.]]*40
        m.nonwall_index=SectionIndex([((3.,0.),(3.,4.))])
        s=m.range_score(raw,list(range(40)),[1.,2.,0.],[0,0,0]);self.assertEqual(s['foreground_occlusions'],40);self.assertEqual(s['first_hit_inlier_fraction'],0)
        m.wall_index=SectionIndex([]);m.nonwall_index=SectionIndex([]);raw=[[20.,0.]]*40
        s=m.range_score(raw,list(range(40)),[1.,2.,0.],[0,0,0]);self.assertEqual(s['missing_wall_hits'],40);self.assertEqual(s['first_hit_inlier_fraction'],0)

    def test_equal_local_first_hit_solutions_remain_ambiguous(self):
        # Solver contract fixture, not evidence that a particular real room has
        # this symmetry. Two independent basins must not become a unique pose.
        env=room();m=StructuralMatcher(env,.182,[r['id'] for r in wall_references(env)]);raw=samples(env,[1.3,1.1,0])
        def cost(raw,ids,pose,tf,sign=1):return dict(first_hit_mean_error_m=min(abs(pose[0]-1.1),abs(pose[0]-1.5))+.1*abs(pose[1]-1.1)+.1*abs(pose[2]),first_hit_inlier_fraction=1.)
        m.range_score=cost;m.score=Mock(return_value=dict(mean_error_m=0.,inlier_fraction=1.,normal_diversity=.5,count=50))
        result=m.fit(raw,[1.3,1.1,0],raw_sensor_points=raw,extrinsic=[0,0,0]);self.assertEqual(result['status'],'AMBIGUOUS')
    def test_small_motion_tracking_uses_same_heldout_and_first_hit_gates(self):
        env=room();m=StructuralMatcher(env,.182,[r['id'] for r in wall_references(env)]);pose=[1.3,1.1,.22];tf=[-.032,0,0]
        for step in range(1,5):
            truth=[1.3+step*.02,1.1+step*.01,.22+step*.02];raw=samples(env,truth);ids=m.structural_indices(raw,pose,tf)['indices']
            result=m.fit(body_points(raw,tf),pose,raw_sensor_points=raw,extrinsic=tf,indices=ids,initial=False)
            self.assertEqual(result['status'],'GEOMETRIC_REVIEW');self.assertLess(math.dist(result['body_pose'][:2],truth[:2]),.01)
            self.assertTrue(m.passes(result['validation']));pose=result['body_pose']
