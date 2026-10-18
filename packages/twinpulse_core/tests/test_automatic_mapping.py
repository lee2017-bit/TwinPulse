# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import copy
import math
import unittest

from twinpulse_core.automatic_mapping import AutomaticMapping, EvidenceGrid, checked_saved_map
from twinpulse_core.observation_stream import ObservationWindow
from twinpulse_core.room_localization import compose, inverse, angle
from packages.twinpulse_core.tests.test_room_localization import fixture, scan_points, pose


CONTEXT={'project_id':'default','session_id':'synthetic','boot_id':'synthetic-boot',
         'release_id':'b'*64,'source_revision':'a'*64,'origin':'recorded_ros'}


def observations(positions, *, odom_positions=None, outline=None, context=None, start=1_000_000_000):
    """Ray-cast truth stays in the evaluator; the runner only gets odom and scan."""
    window=ObservationWindow(context or CONTEXT);seq=0
    for i,truth in enumerate(positions):
        stamp=start+i*100_000_000
        odom=truth if odom_positions is None else odom_positions[i]
        row=pose(stamp,*odom)
        event=window.receive('odom',row,seq,stamp);seq+=1;yield event
        points=scan_points(outline or fixture(),truth)
        scan={'stamp_ns':stamp,'frame_id':'base_scan','ranges_m':[math.hypot(*p) for p in points],
              'angle_min':0.,'angle_max':119*math.tau/120,'angle_increment':math.tau/120,
              'time_increment':0.,'scan_time':.1,'range_min':.05,'range_max':100.}
        event=window.receive('scan',scan,seq,stamp);seq+=1;yield event


class AutomaticMappingTests(unittest.TestCase):
    def run_path(self, positions, odom_positions=None, *, outline=None, **kwargs):
        runner=AutomaticMapping(CONTEXT,[0,0,0],**kwargs)
        for e in observations(positions,odom_positions=odom_positions,outline=outline):runner.consume(e)
        runner.finish();return runner

    def test_causal_bootstrap_drift_tracking_and_separate_odom_map(self):
        truth=[[0,-.7+i*.014,.35+i*.004] for i in range(100)]
        odom=[[t[0]+i*.0008,t[1]+i*.0008,t[2]+i*.0002] for i,t in enumerate(truth)]
        runner=self.run_path(truth,odom);result=runner.snapshot(include_map=True)
        self.assertEqual(result['counts']['scans_seen'],100)
        self.assertGreater(result['counts']['derived_skipped'],0)
        self.assertGreater(len(result['keyframes']),3)
        self.assertFalse(result['motion_authorized']);self.assertFalse(result['alignment_verified'])
        self.assertTrue(result['odom_cells']);self.assertTrue(result['corrected_cells'])
        anchor=inverse(truth[0]);expected=compose(anchor,truth[-5])
        estimates=[r for r in result['trajectory'] if r['state']=='TRACKING_CANDIDATE']
        self.assertTrue(estimates,result['transitions'])
        corrected=estimates[-1]['corrected_pose'];raw=estimates[-1]['odom_pose']
        self.assertLess(math.dist(corrected[:2],expected[:2]),math.dist(raw[:2],expected[:2]))
        self.assertEqual(checked_saved_map(runner.saved_map(),'default')['schema'],'automatic-map-1.0')

    def test_no_future_or_fixed_global_pose_in_new_map(self):
        for start in ([0,-.6,.4],[-.5,.5,-1.1]):
            runner=self.run_path([start]*3);result=runner.snapshot()
            self.assertLess(math.dist(result['pose_candidate'][:2],[0,0]),1e-9)
            self.assertFalse(result['reference_eligible']);self.assertEqual(len(runner.supports),0)
        # The first scan has no future odom, so it must remain pending.
        runner=AutomaticMapping(CONTEXT,[0,0,0]);events=list(observations([[0,0,0]]))
        events[1]['data']['time_increment']=.0001
        for e in events:runner.consume(e)
        self.assertEqual(runner.counts['scans_paired'],0)
        runner.finish();self.assertEqual(runner.reasons['ODOM_TIME_UNBRACKETED'],1)

    def test_unknown_and_conflicting_rays_never_make_clearance(self):
        grid=EvidenceGrid();grid.insert([([0,0],[1,0])],100)
        self.assertIn('free',[r[2] for r in grid.rows()]);self.assertEqual(grid.rows()[-1][2],'occupied')
        grid.insert([([0,0],[2,0])],200);grid.insert([([0,0],[2,0])],300)
        self.assertEqual(next(r for r in grid.rows() if abs(r[0]-1.05)<.001)[2],'unknown')
        previous=copy.deepcopy(grid.rows());grid.insert([],400);self.assertEqual(previous,grid.rows())
        runner=AutomaticMapping(CONTEXT,[0,0,0]);events=list(observations([[0,0,0]]));events[1]['data']['ranges_m']=[None]*120
        for e in events:runner.consume(e)
        self.assertEqual(runner.odom_grid.rows(),[]);self.assertIsNone(runner.pose)

    def test_clock_frame_jump_gap_and_budget_do_not_reuse_pose(self):
        runner=self.run_path([[0,0,0],[0,.1,0]])
        with self.assertRaisesRegex(ValueError,'AFTER_FINISH'):runner.consume(list(observations([[0,0,0]]))[0])
        runner=AutomaticMapping(CONTEXT,[0,0,0]);events=list(observations([[0,0,0],[0,.01,0]]))
        for e in events[:2]:runner.consume(e)
        events[2]['data']['frame_id']='other'
        with self.assertRaisesRegex(ValueError,'FRAME_CHANGED'):runner.consume(events[2])
        self.assertIsNone(runner.pose)
        grid=EvidenceGrid()
        with self.assertRaisesRegex(ValueError,'EXTENT_BUDGET'):grid.insert([([0,0],[13,0])],1)
        self.assertFalse(grid.cells)

    def test_saved_map_rejects_cross_project_same_raw_and_authority(self):
        runner=self.run_path([[0,0,0]]);saved=runner.saved_map()
        with self.assertRaisesRegex(ValueError,'PROJECT'):checked_saved_map(saved,'other')
        with self.assertRaisesRegex(ValueError,'SOURCE_REUSE'):AutomaticMapping(CONTEXT,[0,0,0],reference=saved)
        saved['motion_authorized']=True
        from twinpulse_core.revisions import canonical_sha256
        saved.pop('revision');saved['revision']=canonical_sha256(saved)
        with self.assertRaisesRegex(ValueError,'AUTHORITY'):checked_saved_map(saved,'default')

    def test_revisit_global_localization_different_start_and_symmetric_rejection(self):
        # Independent prior grid, not the query's future lap or a pose seed.
        from twinpulse_core.revisions import canonical_sha256
        prior=EvidenceGrid()
        for start in ([0,-.7,.1],[-.5,.2,1.2],[.5,.8,-.5]):
            prior.insert([(start[:2],compose(start,[*p,0])[:2]) for p in scan_points(fixture(),start)],1,'prior')
        body={'schema':'automatic-map-1.0','project_id':'default','source_revision':'d'*64,'boot_id':'prior-boot',
              'last_receipt_monotonic_ns':1,'reference_eligible':True,'offset':[0,0,0],
              'cells':prior.rows(),'endpoint_cells':prior.endpoints(),'keyframes':[],'odom_cells':[],
              'loop_status':'SYNTHETIC_PRIOR','timing_basis':'DECLARED_HEADER_UNVERIFIED_ACQUISITION',
              'alignment_verified':False,'motion_authorized':False,'physical_demo_ready':False,'reference_revision':None}
        reference={**body,'revision':canonical_sha256(body)}
        for start in ([0,-.8,.4],[-.6,.5,-1.2]):
            positions=[[start[0],start[1]+i*.008,start[2]] for i in range(35)]
            odom=[[0,i*.008,0] for i in range(35)]
            runner=self.run_path(positions,odom,reference=reference)
            self.assertTrue(runner.trace,runner.transitions)
            first=runner.trace[0]['corrected_pose']
            self.assertLess(math.dist(first[:2],start[:2]),.15)
            self.assertLess(abs(angle(first[2]-start[2])),.12)
            self.assertFalse(runner.snapshot()['motion_authorized'])
        square={'bounds_m':[-1.5,1.5,-1.5,1.5], 'segments':[[[-1.5,-1.5],[1.5,-1.5]],[[1.5,-1.5],[1.5,1.5]],[[1.5,1.5],[-1.5,1.5]],[[-1.5,1.5],[-1.5,-1.5]]]}
        grid=EvidenceGrid();grid.insert([([0,0],p) for p in scan_points(square,[0,0,0])],1,'prior')
        body.update(cells=grid.rows(),endpoint_cells=grid.endpoints());reference={**body,'revision':canonical_sha256(body)}
        runner=AutomaticMapping(CONTEXT,[0,0,0],reference=reference)
        for e in observations([[.1,.1,.4]]*4,outline=square):runner.consume(e)
        self.assertIsNone(runner.pose);self.assertEqual(runner.state,'AMBIGUOUS')

    def test_closed_loop_output_changes_sensors_with_drift_and_different_starts(self):
        # Evaluator alone holds truth. This controller sees only estimated local
        # pose; its output changes the world and therefore the next scan.
        self.closed_loop_metrics=[]
        for start,goal in (([0,-.7,.35],[.6,.25]),([-.5,.5,-1.1],[.5,-.2])):
            runner=AutomaticMapping(CONTEXT,[0,0,0]);world=list(start);window=ObservationWindow(CONTEXT)
            seq=0;commands=0;first_scan=copy.deepcopy(world);drift=0.;odom_error=0.;error=99.
            for tick in range(180):
                estimated=runner.pose
                if estimated is None:linear=turn=0.
                else:
                    dx,dy=goal[0]-estimated[0],goal[1]-estimated[1]
                    heading=angle(math.atan2(dy,dx)-estimated[2]);linear=.08 if abs(heading)<.5 else 0.
                    turn=max(-.5,min(.5,heading));commands+=linear!=0 or turn!=0
                world=compose(world,[linear*.1,0,turn*.1]);drift+=.0004
                stamp=1_000_000_000+tick*100_000_000
                measured=[world[0]+drift,world[1]+drift,world[2]+tick*.0001]
                e=window.receive('odom',pose(stamp,*measured),seq,stamp);seq+=1;runner.consume(e)
                points=scan_points(fixture(),world)
                scan={'stamp_ns':stamp,'frame_id':'base_scan','ranges_m':[math.hypot(*p) for p in points],
                      'angle_min':0.,'angle_max':119*math.tau/120,'angle_increment':math.tau/120,
                      'time_increment':0.,'scan_time':.1,'range_min':.05,'range_max':100.}
                e=window.receive('scan',scan,seq,stamp);seq+=1;runner.consume(e)
                truth_local=compose(inverse(first_scan),world)
                error=math.dist(truth_local[:2],goal)
                odom_error=math.dist(compose(inverse(first_scan),measured)[:2],truth_local[:2])
                if error<.10:break
            self.assertGreater(commands,20);self.assertLess(error,.15)
            self.assertIsNotNone(runner.pose,runner.transitions)
            measured_error=math.dist(runner.pose[:2],truth_local[:2])
            self.assertLess(measured_error,odom_error+.025)
            self.assertFalse(runner.snapshot()['motion_authorized'])
            self.closed_loop_metrics.append({'start':start,'goal':goal,'ticks':tick+1,'goal_error_m':error,
                                            'frontend_pose_error_m':measured_error,'odom_error_m':odom_error})

    def test_two_rooms_five_revisit_starts_tracking_accuracy(self):
        from twinpulse_core.revisions import canonical_sha256
        vertices=[[-1.7,-1.8],[1.7,-1.8],[1.7,.6],[1.1,.6],[1.1,1.5],[-.5,1.5],[-.5,1.9],[-1.7,1.9]]
        second={'bounds_m':[-1.7,1.7,-1.8,1.9],
                'segments':[[vertices[i],vertices[(i+1)%len(vertices)]] for i in range(len(vertices))]}
        starts=([0,-.8,.4],[-.6,.5,-1.2],[.3,-.3,2.3],[.5,.2,-2.2],[-.7,-.6,.9])
        self.revisit_metrics=[]
        for room_index,outline in enumerate((fixture(),second)):
            prior=EvidenceGrid()
            # Independent completed prior survey, never the query's future trajectory.
            for p in ([0,-.7,.1],[-.7,.4,1.2],[.7,.3,-.5]):
                prior.insert([(p[:2],compose(p,[*point,0])[:2]) for point in scan_points(outline,p)],1,'prior')
            body={'schema':'automatic-map-1.0','project_id':'default','source_revision':'d'*64,'boot_id':'prior-boot',
                  'last_receipt_monotonic_ns':1,'reference_eligible':True,'offset':[0,0,0],
                  'cells':prior.rows(),'endpoint_cells':prior.endpoints(),'keyframes':[],'odom_cells':[],
                  'loop_status':'SYNTHETIC_PRIOR','timing_basis':'DECLARED_HEADER_UNVERIFIED_ACQUISITION',
                  'alignment_verified':False,'motion_authorized':False,'physical_demo_ready':False,'reference_revision':None}
            reference={**body,'revision':canonical_sha256(body)}
            for start in starts:
                truth=[[start[0],start[1]+i*.008,start[2]+i*.001] for i in range(45)]
                odom=[compose(inverse(start),p) for p in truth]
                for i,p in enumerate(odom):p[0]+=i*.0004;p[1]+=i*.0004;p[2]+=i*.0001
                runner=self.run_path(truth,odom,reference=reference,outline=outline)
                tracked=[p for p in runner.trace if p['state']=='TRACKING_CANDIDATE'];accurate=0;errors=[]
                for row in tracked:
                    index=round((row['stamp_ns']-1_000_000_000)/100_000_000)
                    xy=math.dist(row['corrected_pose'][:2],truth[index][:2]);yaw=abs(angle(row['corrected_pose'][2]-truth[index][2]))
                    accurate+=xy<=.10 and yaw<=math.radians(5);errors.append([xy,yaw])
                metric={'room':room_index,'start':start,'tracked':len(tracked),'accurate':accurate,
                        'max_xy_m':max((p[0] for p in errors),default=None),'max_yaw_rad':max((p[1] for p in errors),default=None)}
                self.revisit_metrics.append(metric)
                with self.subTest(room=room_index,start=start):
                    self.assertGreater(len(tracked),0,runner.transitions)
                    self.assertGreaterEqual(accurate/max(1,len(tracked)),.95,metric)

    def test_position_jump_relocalizes_instead_of_reusing_old_binding(self):
        positions=[[0,-.7+i*.014,.35] for i in range(50)]
        odom=[p[:] if i<25 else [p[0]+.8,p[1]-.6,p[2]+.4] for i,p in enumerate(positions)]
        runner=self.run_path(positions,odom)
        self.assertTrue(any(r['reason']=='ODOM_DISCONTINUITY' for r in runner.transitions))
        self.assertTrue(runner.match is None or runner.match['status'] in {'GEOMETRIC_CANDIDATE','TRACKING_CANDIDATE','AMBIGUOUS','POOR_FIT'})
        # False confidence is not mandatory recovery: unresolved cases stay lost.
        if runner.pose is not None:
            expected=compose(inverse(positions[0]),positions[-1])
            self.assertLess(math.dist(runner.pose[:2],expected[:2]),.2)
        else:self.assertIn(runner.state,{'LOST','AMBIGUOUS'})
        self.assertFalse(runner.snapshot()['motion_authorized'])

    def test_analysis_pending_overflow_is_bounded_and_raw_not_reported_dropped(self):
        runner=AutomaticMapping(CONTEXT,[0,0,0]);events=list(observations([[0,0,0]]*20))
        # No odom consumer: faster scan delivery fills only the derived queue.
        seq=0
        for event in events:
            if event['topic']!='scan':continue
            event['sequence']=seq;event['receipt_monotonic_ns']=seq+1;seq+=1
            runner.consume(event)
        result=runner.snapshot();self.assertLessEqual(result['pending_scans'],8)
        self.assertGreater(result['counts']['derived_dropped'],0);self.assertEqual(result['raw_recording_dropped'],0)
        self.assertIsNone(result['pose_candidate'])

    def test_dynamic_tf_conflict_is_fatal_but_missing_static_is_explicit(self):
        runner=AutomaticMapping(CONTEXT,[0,0,0]);events=list(observations([[0,0,0]]))
        for event in events:runner.consume(event)
        self.assertEqual(runner.snapshot()['input_health']['faults']['/tf_static'],'NOT_RECEIVED')
        tf={'topic':'/tf','sequence':2,'receipt_monotonic_ns':1_000_000_000,
            'data':{'transforms':[{'frame_id':'odom','child_frame_id':'base_footprint','stamp_ns':1_000_000_000,
                                   'translation_m':[.5,0,0],'quaternion_xyzw':[0,0,0,1]}]}}
        with self.assertRaisesRegex(ValueError,'ODOM_DYNAMIC_TF_CONFLICT'):runner.consume(tf)
        self.assertIsNone(runner.pose);self.assertEqual(runner.failed,'ODOM_DYNAMIC_TF_CONFLICT')


if __name__=='__main__':unittest.main()
