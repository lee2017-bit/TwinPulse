# SPDX-License-Identifier: Apache-2.0
"""Synthetic independent scene/ray fixtures, not hardware or installed UI."""
from copy import deepcopy
import hashlib,math,tempfile,unittest
from pathlib import Path
from tests.integration import test_r5_product_api
from tests.integration.test_environment_alignment import room,samples
from twinpulse_core.environment_alignment import wall_references
from twinpulse_core.environment_survey import checked_frames,review_collection
from twinpulse_core.environment_section import horizontal_section
from twinpulse_core.lidar_geometry import SectionIndex
from twinpulse_core.revisions import canonical_sha256
from twinpulse_core.room_localization import compose,inverse
from twinpulse_app.task_collection import TaskCollection
from twinpulse_app.library_asset_store import atomic_json


def collection_frames(env,poses):
    return [dict(identity=['stream',i,'raw'+str(i)],points=samples(env,p),local_pose=compose(inverse(poses[0]),p),native_pose=p,
        extrinsic=[-.032,0.,0.],source_owner=['robot','op','conn'],source_sha256=canonical_sha256(['original',i]),stamp=1000.+i,
        source_kind='SIM') for i,p in enumerate(poses)]


class EnvironmentSurveyTests(unittest.TestCase):
    def review(self,env,frames):
        r=wall_references(env)[0]
        return review_collection(env,frames,[1.35,1.05,.25],r['id'],r['length_m'],'SIM_ONLY',.182)

    def test_multiple_positions_use_their_original_relative_poses(self):
        env=room();poses=[[1.3,1.1,.22],[1.6,1.1,.4],[1.8,1.4,.6],[1.3,1.1,.22]]
        frames=collection_frames(env,poses);value=self.review(env,frames)
        self.assertEqual(value['status'],'GEOMETRIC_REVIEW',value['frame_validations'])
        self.assertLess(math.dist(value['match']['body_pose'][:2],poses[0][:2]),.01)
        self.assertGreater(value['maximum_view_baseline_m'],.5)
        self.assertTrue(all(v['passes'] for v in value['frame_validations']))
        self.assertEqual(value['obstacle_candidates'],[])
        self.assertFalse(value['physical_authority']);self.assertFalse(value['world_registration_verified'])

    def test_later_wrong_wheel_pose_is_not_refit_or_selected_away(self):
        env=room();frames=collection_frames(env,[[1.3,1.1,.22],[1.6,1.1,.4],[1.8,1.4,.6]])
        frames[-1]['local_pose'][0]+=1.
        value=self.review(env,frames);self.assertEqual(value['status'],'HELD')
        self.assertEqual(len(value['frame_validations']),3);self.assertFalse(value['frame_validations'][-1]['passes'])

    def test_duplicate_source_change_physical_sim_reference_and_cancel_rejected(self):
        env=room();frames=collection_frames(env,[[1.3,1.1,.22],[1.6,1.1,.4],[1.8,1.4,.6]])
        bad=deepcopy(frames);bad[-1]['identity']=bad[0]['identity']
        with self.assertRaisesRegex(ValueError,'DUPLICATE'):checked_frames(bad)
        bad=deepcopy(frames);bad[-1]['extrinsic'][0]+=.01
        with self.assertRaisesRegex(ValueError,'SOURCE_OR_TF'):checked_frames(bad)
        for f in frames:f['source_kind']='PHYSICAL'
        with self.assertRaisesRegex(ValueError,'PHYSICAL_REFERENCE'):self.review(env,frames)

    def test_unmodelled_multiview_box_becomes_only_an_unclassified_xy_candidate(self):
        env=room();truth=deepcopy(env);x,y,w,h=2.6,1.8,.35,.35
        vertices=[[x+a,y+b,z] for z in (0.,.5) for b in (-h/2,h/2) for a in (-w/2,w/2)]
        triangles=[[0,1,3],[0,3,2],[4,6,7],[4,7,5],[0,4,5],[0,5,1],[2,3,7],[2,7,6],[0,2,6],[0,6,4],[1,5,7],[1,7,3]]
        truth['meshes'].append(dict(id='Env_'+hashlib.sha256(b'clutter').hexdigest()[:20],source_path='/Source/UnmodelledBox',category='unknown',
            label='Truth fixture only',points_m=vertices,triangles=triangles,color_rgb=[.5,.5,.5],translation_m=[0,0,0]))
        frames=collection_frames(truth,[[1.3,1.1,.22],[1.6,1.1,.4],[1.8,1.4,.6],[1.3,1.1,.22]])
        value=self.review(env,frames);self.assertEqual(value['status'],'GEOMETRIC_REVIEW',value['frame_validations'])
        candidates=value['obstacle_candidates'];self.assertGreater(len(candidates),0)
        near=min(candidates,key=lambda c:math.dist(c['position_xy_m'],[x,y]))
        self.assertLess(math.dist(near['position_xy_m'],[x,y]),.35)
        self.assertEqual(near['classification'],'unknown');self.assertFalse(near['full_3d_size_known'])
        self.assertGreaterEqual(near['view_baseline_m'],.1);self.assertGreaterEqual(len(near['view_indices']),2)


class TaskCollectionTests(unittest.TestCase):
    def test_source_bound_original_sim_files_and_failed_state_are_preserved(self):
        env=room();poses=[[1.3,1.1,.22],[1.6,1.1,.4],[1.8,1.4,.6]]
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);identity='a'*32;binding=['engine','stage','c'*64];events=[]
            capture=dict(source_sha256=env['source_sha256'],meters_per_unit=1.,source_up_axis='Z',units_basis='selected_for_sim',environment_sha256=canonical_sha256(env),scene_revision='c'*64)
            for i,p in enumerate(poses,1):
                scan=dict(source='isaac_usd_surface_rays',point_frame='sensor_local',points=samples(env,p),stream_id='stream',frame_sequence=i,captured_at_ms=1000.+i)
                obs=dict(robot_id='robot',operation_id='op',connection_epoch='conn',binding=binding,scan=scan,body_pose=dict(position_m=p))
                atomic_json(root/identity/f'observation-{i:04d}.json',obs)
                events.append(dict(kind='observation',scan_sha256=canonical_sha256(scan),pose=obs['body_pose'],scan_identity=['stream',i,1000.+i]))
            job=dict(task_id=identity,project_id='project',robot_id='robot',robot_kind='sim',operation_id='op',connection_epoch='conn',state='FAILED',reason='ORIGINAL_FAIL',
                environment_source=capture,scene_binding=binding,events=events)
            job['record_sha256']=canonical_sha256(job);atomic_json(root/identity/'task.json',job)
            reader=TaskCollection(root,'project');value=reader.load(identity)
            self.assertEqual(value['original_state'],'FAILED');self.assertEqual(value['original_reason'],'ORIGINAL_FAIL')
            self.assertEqual(len(value['frames']),3);self.assertGreater(value['frames'][-1]['local_pose'][0],.3)
            path=root/identity/'observation-0002.json';changed=deepcopy(obs);atomic_json(path,changed)
            with self.assertRaisesRegex(ValueError,'EVENT_POSE'):reader.load(identity)


if __name__=='__main__':unittest.main()
