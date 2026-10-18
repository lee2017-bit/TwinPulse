# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import math
import unittest
from twinpulse_core.room_localization import (RoomMatcher,PoseTimeline,SessionLocalization,
    compose,inverse,angle,deskew)


def pose(t,x=0,y=0,yaw=0):
    return {'stamp_ns':t,'frame_id':'odom','child_frame_id':'base_footprint',
            'position_m':[x,y,0],'quaternion_xyzw':[0,0,math.sin(yaw/2),math.cos(yaw/2)]}


def fixture():
    # Asymmetric enclosed room: not the user's physical geometry.
    vertices=[[-1.5,-2],[1.5,-2],[1.5,1],[.8,1],[.8,2],[-1.5,2]]
    return {'bounds_m':[-1.5,1.5,-2,2],
            'segments':[[vertices[i],vertices[(i+1)%len(vertices)]] for i in range(len(vertices))]}


def scan_points(outline,start,*,beam_count=120):
    result=[]
    for i in range(beam_count):
        a=start[2]+i*math.tau/beam_count;dx,dy=math.cos(a),math.sin(a);hits=[]
        for p,q in outline['segments']:
            sx,sy=q[0]-p[0],q[1]-p[1];det=dx*sy-dy*sx
            if abs(det)<1e-8:continue
            ox,oy=p[0]-start[0],p[1]-start[1]
            distance=(ox*sy-oy*sx)/det;fraction=(ox*dy-oy*dx)/det
            if distance>0 and 0<=fraction<=1:hits.append(distance)
        if hits:
            distance=min(hits);result.append([distance*math.cos(i*math.tau/beam_count),distance*math.sin(i*math.tau/beam_count)])
    return result


class LocalizationTests(unittest.TestCase):
    def test_different_starts_and_headings_do_not_reuse_a_fixed_route(self):
        matcher=RoomMatcher(fixture())
        for start in ([0,-.8,.4],[-.6,.5,-1.2],[.3,-.3,2.3]):
            with self.subTest(start=start):
                result=matcher.match(scan_points(fixture(),start))
                self.assertEqual(result['status'],'GEOMETRIC_CANDIDATE',result)
                self.assertLess(math.dist(result['pose'][:2],start[:2]),.08)
                self.assertLess(abs(angle(result['pose'][2]-start[2])),.06)
                self.assertFalse(result['alignment_verified'])

    def test_symmetric_room_is_not_silently_resolved(self):
        square={'bounds_m':[-2,2,-2,2],'segments':[[[-2,-2],[2,-2]],[[2,-2],[2,2]],[[2,2],[-2,2]],[[-2,2],[-2,-2]]]}
        result=RoomMatcher(square).match(scan_points(square,[.3,.5,.1]))
        self.assertEqual(result['status'],'AMBIGUOUS')

    def test_missing_view_is_not_clear_space(self):
        points=[[1+.01*i,.01*i] for i in range(40)]
        self.assertEqual(RoomMatcher(fixture()).match(points)['status'],'INSUFFICIENT_ANGULAR_COVERAGE')

    def test_odom_yaw_interpolates_across_pi_and_gaps_are_rejected(self):
        timeline=PoseTimeline([pose(1_000_000_000,yaw=3.1),pose(1_100_000_000,x=1,yaw=-3.1)])
        value=timeline.at(1_050_000_000)
        self.assertAlmostEqual(value[0],.5);self.assertAlmostEqual(abs(value[2]),math.pi)
        with self.assertRaisesRegex(ValueError,'UNBRACKETED'):timeline.at(999_999_999)
        gap=PoseTimeline([pose(1_000_000_000),pose(1_200_000_000)])
        with self.assertRaisesRegex(ValueError,'GAP'):gap.at(1_100_000_000)

    def test_rolling_scan_is_deskewed_without_fabricating_missing_rays(self):
        timeline=PoseTimeline([pose(1_000_000_000),pose(1_100_000_000,x=.1)])
        scan={'stamp_ns':1_000_000_000,'time_increment':.025,'angle_min':0,
              'angle_increment':.1,'ranges_m':[1.,None,1.,1.]}
        points,_=deskew(scan,timeline,[0,0,0]);self.assertEqual(len(points),3)
        self.assertAlmostEqual(points[1][0],math.cos(.2)+.05)

    def test_session_manual_reposition_staleness_and_poor_fit_revoke_goal(self):
        binding=SessionLocalization();epoch=binding.begin('session-a','raw-a','scene-a')
        good={'status':'GEOMETRIC_CANDIDATE','pose':[1,2,.2]}
        self.assertTrue(binding.accept(epoch,good,[.3,.4,.1],1_000_000_000))
        goal=binding.goal([1,2],epoch=epoch,session_id='session-a',source_revision='raw-a',scene_revision='scene-a',stamp_ns=1_000_000_000)
        self.assertFalse(goal['motion_authorized'])
        for a,b in zip(goal['odom_goal_candidate_m'],[.3,.4]):self.assertAlmostEqual(a,b)
        for changed in ({'epoch':epoch+1},{'session_id':'session-b'},{'source_revision':'raw-b'},
                        {'scene_revision':'scene-b'},{'stamp_ns':1_500_000_001}):
            args=dict(epoch=epoch,session_id='session-a',source_revision='raw-a',scene_revision='scene-a',stamp_ns=1_000_000_000);args.update(changed)
            with self.subTest(changed=changed),self.assertRaises(ValueError):binding.goal([0,0],**args)
        binding.invalidate();self.assertIsNone(binding.binding)
        with self.assertRaises(ValueError):binding.accept(epoch,good,[0,0,0],1_000_000_000)
        epoch=binding.begin('session-b','raw-a','scene-a')
        self.assertFalse(binding.accept(epoch,{'status':'AMBIGUOUS'},[0,0,0],1_000_000_000))


if __name__=='__main__':unittest.main()
