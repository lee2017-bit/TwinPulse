# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Route-independent planar scan matching and session-local coordinate binding.

Geometric quality is NOT physical calibration or motion permission. The input
room can be an approximate photo Twin. Unknown rays never become clear space.
"""
import bisect
import math
from .revisions import canonical_sha256


def angle(value): return math.atan2(math.sin(value), math.cos(value))


def compose(a, b):
    c, s = math.cos(a[2]), math.sin(a[2])
    return [a[0] + c*b[0] - s*b[1], a[1] + s*b[0] + c*b[1], angle(a[2] + b[2])]


def inverse(a):
    c, s = math.cos(a[2]), math.sin(a[2])
    return [-c*a[0]-s*a[1], s*a[0]-c*a[1], -a[2]]


def planar_pose(value):
    p, q = value['position_m'], value['quaternion_xyzw']
    if (len(p) != 3 or len(q) != 4 or not all(math.isfinite(v) for v in p+q) or
        abs(sum(v*v for v in q)-1) > .001 or abs(q[0])+abs(q[1]) > .001):
        raise ValueError('NONPLANAR_OR_INVALID_ODOM')
    return [p[0], p[1], angle(2*math.atan2(q[2], q[3]))]


class PoseTimeline:
    def __init__(self, odom, max_gap_ns=100_000_000):
        if not odom or len(odom) > 65536: raise ValueError('ODOM_TIMELINE_COUNT')
        self.rows = odom; self.stamps = [r['stamp_ns'] for r in odom]
        self.poses = [planar_pose(r) for r in odom]; self.max_gap = max_gap_ns
        if any(a >= b for a,b in zip(self.stamps,self.stamps[1:])):
            raise ValueError('ODOM_TIME_NOT_STRICTLY_INCREASING')
        if len({(r['frame_id'],r['child_frame_id']) for r in odom}) != 1:
            raise ValueError('ODOM_FRAME_CHANGED')
        if odom[0]['frame_id'] != 'odom': raise ValueError('ODOM_FRAME_UNSUPPORTED')

    def at(self, stamp):
        i = bisect.bisect_left(self.stamps, stamp)
        if i < len(self.stamps) and self.stamps[i] == stamp: return list(self.poses[i])
        if i == 0 or i == len(self.stamps): raise ValueError('ODOM_TIME_UNBRACKETED')
        lo, hi = self.stamps[i-1], self.stamps[i]
        if hi-lo > self.max_gap: raise ValueError('ODOM_TIME_GAP')
        f = (stamp-lo)/(hi-lo); a,b = self.poses[i-1],self.poses[i]
        return [a[0]+f*(b[0]-a[0]), a[1]+f*(b[1]-a[1]), angle(a[2]+f*angle(b[2]-a[2]))]


def deskew(scan, timeline, child_to_scan, max_points=160):
    if len(child_to_scan) != 3 or not all(math.isfinite(v) for v in child_to_scan):
        raise ValueError('SENSOR_EXTRINSIC_REQUIRED')
    first_sensor = compose(timeline.at(scan['stamp_ns']), child_to_scan)
    # Verify the entire rolling scan is bracketed, not just the sampled beams.
    end = scan['stamp_ns'] + round((len(scan['ranges_m'])-1)*scan['time_increment']*1e9)
    timeline.at(end)
    step = max(1, math.ceil(len(scan['ranges_m'])/max_points)); points = []
    for i in range(0,len(scan['ranges_m']),step):
        distance = scan['ranges_m'][i]
        if distance is None: continue
        stamp = scan['stamp_ns'] + round(i*scan['time_increment']*1e9)
        sensor = compose(timeline.at(stamp),child_to_scan)
        ray = scan['angle_min'] + i*scan['angle_increment']
        world = compose(sensor,[distance*math.cos(ray),distance*math.sin(ray),0])
        local = compose(inverse(first_sensor),world)
        points.append(local[:2])
    return points, first_sensor


def scene_outline(objects, scan_height_m=.18):
    floor = next((o for o in objects if o['kind']=='floor'),None)
    if floor is None: raise ValueError('ROOM_FLOOR_REQUIRED')
    fp, fd = floor['transform']['position_m'], floor['shape']['dimensions_m']
    bounds = [fp[0]-fd[0]/2,fp[0]+fd[0]/2,fp[1]-fd[1]/2,fp[1]+fd[1]/2]
    if max(fd[:2]) > 12 or min(fd[:2]) <= 0: raise ValueError('ROOM_SEARCH_BUDGET')
    segments = []; solids=[]
    for obj in objects:
        if obj['kind']=='floor': continue
        p,d = obj['transform']['position_m'],obj['shape']['dimensions_m']
        if not p[2]-d[2]/2 <= scan_height_m <= p[2]+d[2]/2: continue
        yaw = math.radians(obj['transform'].get('rotation_rpy_deg',[0,0,0])[2])
        corners = [compose([p[0],p[1],yaw],[x*d[0]/2,y*d[1]/2,0])[:2]
                   for x,y in ((-1,-1),(1,-1),(1,1),(-1,1))]
        segments.extend([[corners[i],corners[(i+1)%4]] for i in range(4)])
        solids.append(corners)
    if not segments or len(segments)>256: raise ValueError('ROOM_OUTLINE_BUDGET')
    body={'bounds_m':bounds,'segments':segments,'solids':solids,'geometry_status':'PHOTO_APPROXIMATION_NOT_SURVEYED'}
    return {**body,'revision':canonical_sha256(body)}


def segment_distance(p, segment):
    a,b=segment; dx,dy=b[0]-a[0],b[1]-a[1]; n=dx*dx+dy*dy
    f=max(0.,min(1.,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/n)) if n else 0.
    return math.hypot(p[0]-a[0]-f*dx,p[1]-a[1]-f*dy)


class RoomMatcher:
    """Bounded global search (no old pose prior) followed by local refinement."""
    def __init__(self, outline):
        self.outline=outline; self.bounds=outline['bounds_m']; self.cell=.06
        x0,x1,y0,y1=self.bounds
        self.x0,self.y0=x0-.5,y0-.5
        self.nx=math.ceil((x1-x0+1)/self.cell)+1; self.ny=math.ceil((y1-y0+1)/self.cell)+1
        if self.nx*self.ny>60000: raise ValueError('ROOM_DISTANCE_FIELD_BUDGET')
        self.field=[min(segment_distance((self.x0+x*self.cell,self.y0+y*self.cell),s)
                        for s in outline['segments']) for y in range(self.ny) for x in range(self.nx)]

    def possible(self, pose):
        x0,x1,y0,y1=self.bounds
        if not x0<=pose[0]<=x1 or not y0<=pose[1]<=y1:return False
        for polygon in self.outline.get('solids',[]):
            sides=[(b[0]-a[0])*(pose[1]-a[1])-(b[1]-a[1])*(pose[0]-a[0])
                   for a,b in zip(polygon,polygon[1:]+polygon[:1])]
            if all(v>=0 for v in sides) or all(v<=0 for v in sides):return False
        return True

    def score(self, points, pose):
        c,s=math.cos(pose[2]),math.sin(pose[2]); errors=[]
        for px,py in points:
            x,y=pose[0]+c*px-s*py,pose[1]+s*px+c*py
            ix,iy=round((x-self.x0)/self.cell),round((y-self.y0)/self.cell)
            errors.append(self.field[iy*self.nx+ix] if 0<=ix<self.nx and 0<=iy<self.ny else 1.)
        # Capped mean still accounts for every sampled return; don't keep only
        # convenient inliers and declare missing/occluded objects calibrated.
        return sum(min(v,.5) for v in errors)/len(errors),sum(v<=.15 for v in errors)/len(errors)

    def match(self, points):
        if not 24 <= len(points) <= 160 or any(len(p)!=2 or not all(math.isfinite(v) and abs(v)<=1000 for v in p) for p in points):
            raise ValueError('SCAN_MATCH_POINT_BUDGET')
        headings={int((math.atan2(p[1],p[0])+math.pi)/(math.tau/8))%8 for p in points}
        if len(headings)<5: return {'status':'INSUFFICIENT_ANGULAR_COVERAGE','pose':None}
        x0,x1,y0,y1=self.bounds; candidates=[]; step=.20
        nx,ny=math.ceil((x1-x0)/step),math.ceil((y1-y0)/step)
        if nx*ny*36>150000: raise ValueError('GLOBAL_SEARCH_BUDGET')
        # Limit coarse scoring to uniform original-point selection, not reindexing rays.
        sampled=points[::max(1,math.ceil(len(points)/48))]
        for iy in range(ny+1):
            y=min(y1,y0+iy*step)
            for ix in range(nx+1):
                x=min(x1,x0+ix*step)
                if not self.possible([x,y,0]):continue
                for k in range(36):
                    pose=[x,y,-math.pi+k*math.tau/36]
                    score,_=self.score(sampled,pose); candidates.append((score,pose))
        candidates.sort(key=lambda v:v[0]); seeds=[]
        for _,pose in candidates:
            if all(math.dist(pose[:2],p[:2])>.35 or abs(angle(pose[2]-p[2]))>.30 for p in seeds): seeds.append(pose)
            if len(seeds)==8: break
        refined=[]
        for seed in seeds:
            pose=list(seed)
            for delta,turn in ((.10,.08),(.05,.04),(.025,.02)):
                for _ in range(6):
                    opts=[[pose[0]+dx,pose[1]+dy,angle(pose[2]+dt)]
                          for dx,dy,dt in ((0,0,0),(delta,0,0),(-delta,0,0),(0,delta,0),(0,-delta,0),(0,0,turn),(0,0,-turn))]
                    opts=[p for p in opts if self.possible(p)]
                    best=min(opts,key=lambda p:self.score(points,p)[0])
                    if best==pose: break
                    pose=best
            score,inliers=self.score(points,pose);refined.append({'pose':pose,'mean_error_m':score,'inlier_fraction':inliers})
        if not refined:return {'status':'NO_PLAUSIBLE_POSE','pose':None}
        refined.sort(key=lambda c:c['mean_error_m']); best=refined[0]
        rival=next((c for c in refined[1:] if math.dist(c['pose'][:2],best['pose'][:2])>.35 or abs(angle(c['pose'][2]-best['pose'][2]))>.30),None)
        margin=rival['mean_error_m']-best['mean_error_m'] if rival else None
        status='GEOMETRIC_CANDIDATE' if best['mean_error_m']<=.12 and best['inlier_fraction']>=.70 else 'POOR_FIT'
        if status=='GEOMETRIC_CANDIDATE' and (margin is None or margin<.025):status='AMBIGUOUS'
        return {**best,'status':status,'alternative_margin_m':margin,'alternatives':refined[:4],
                'alignment_verified':False,'motion_authorized':False}


class SessionLocalization:
    """A new session/reposition epoch invalidates old coordinates immediately."""
    def __init__(self): self.epoch=0; self.context=None; self.binding=None

    def begin(self, session_id, source_revision, scene_revision):
        self.epoch+=1;self.context=(session_id,source_revision,scene_revision);self.binding=None
        return self.epoch

    def invalidate(self):
        self.epoch+=1;self.binding=None
        return self.epoch

    def accept(self, epoch, result, odom_sensor_pose, stamp_ns):
        if epoch!=self.epoch or self.context is None:raise ValueError('LOCALIZATION_CONTEXT_CHANGED')
        self.binding=None
        if result['status']!='GEOMETRIC_CANDIDATE':return False
        self.binding={'room_from_odom':compose(result['pose'],inverse(odom_sensor_pose)),
                      'stamp_ns':stamp_ns,'epoch':epoch,'context':self.context}
        return True

    def goal(self, goal_xy, *, epoch, session_id, source_revision, scene_revision, stamp_ns):
        if (not self.binding or epoch!=self.epoch or self.context!=(session_id,source_revision,scene_revision)
            or not 0<=stamp_ns-self.binding['stamp_ns']<=500_000_000):
            raise ValueError('LOCALIZATION_MISSING_STALE_OR_CHANGED')
        if len(goal_xy)!=2 or not all(type(v) in (int,float) and math.isfinite(v) and abs(v)<=100 for v in goal_xy):
            raise ValueError('GOAL_COORDINATES_INVALID')
        return {'odom_goal_candidate_m':compose(inverse(self.binding['room_from_odom']),[*goal_xy,0])[:2],
                'epoch':self.epoch,'alignment_verified':False,'motion_authorized':False,
                'basis':'GEOMETRIC_PHOTO_TWIN_CANDIDATE_NOT_EXECUTION_CALIBRATION'}
