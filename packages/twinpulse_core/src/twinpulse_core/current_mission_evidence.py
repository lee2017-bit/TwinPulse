# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Current sensor matching/observed grid for an owned mission, not admission.

No commands or devices. A caller must separately review actual timing, frames,
release, stop qualification and scope. A saved pose is never an initial pose.
"""
from collections import deque
import math
from .automatic_mapping import EvidenceGrid,local_match
from .sensor_map_localization import EndpointMatcher
from .room_localization import compose,inverse,angle
from .local_navigation import LocalScan,finite
from .revisions import canonical_sha256
from copy import deepcopy


class IdleCurrentEvidence:
    """Fresh localization sampling while the owning link keeps wheels disabled.

    No device initialization, motor commands, old pose injection or new lease.
    Slow global matching may initialize the tracker, but cannot return a fresh
    preview from old observations. Any failure drops cached pose/grid evidence.
    """
    def __init__(self,tracker,window,binding,*,snapshot,disabled,clock):
        self.tracker=tracker;self.window=window;self.binding=binding
        self.snapshot=snapshot;self.disabled=disabled;self.clock=clock
        self.closed=False;self.last=None

    def sample(self):
        self.last=None
        if self.closed:raise ValueError('IDLE_LOCALIZATION_CLOSED')
        try:
            if self.disabled() is not True:raise ValueError('IDLE_LOCALIZATION_WHEELS_NOT_DISABLED')
            self.check_source()
            snapshot=self.snapshot();started=self.clock()
            value=self.tracker.update_window(self.window,snapshot,self.binding,started)
            # Account for actual processing time, not just callback entry.
            now=self.clock()
            sample_s=min(snapshot['odom']['sample_s'],snapshot['scan']['sample_s'])
            if not finite(now) or now<started or not 0<=now-sample_s<.2-1e-9:
                raise ValueError('IDLE_LOCALIZATION_CURRENT_EVIDENCE_STALE')
            if self.disabled() is not True:raise ValueError('IDLE_LOCALIZATION_WHEELS_NOT_DISABLED')
            self.check_source()
            if value['state']!='TRACKING_CANDIDATE':
                raise ValueError('IDLE_LOCALIZATION_'+value['state'])
            value={**value,'sample_s':sample_s,'motion_authorized':False,'physical_demo_ready':False}
            self.last=deepcopy(value)
            return value
        except Exception:
            self.tracker.transform=None;self.tracker.innovations.clear();self.last=None
            raise

    def check_source(self):
        for key in ('project_id','source_revision','session_id','boot_id','release_id','origin'):
            if key in self.tracker.context and self.window.context.get(key)!=self.tracker.context[key]:
                raise ValueError('IDLE_LOCALIZATION_SOURCE_CHANGED')

    def close(self):
        self.closed=True;self.last=None
        self.tracker.transform=None;self.tracker.innovations.clear()

    def handoff(self):
        # Only the owning worker uses the tracker as a warm matching seed for
        # its next fresh tick. No cached preview/pose or idle operation survives.
        self.closed=True;self.last=None


class CurrentMissionEvidence:
    def __init__(self,reference,photo,context,room_revision,*,local_survey=False):
        self.reference=reference;self.photo=photo;self.context=dict(context);self.room_revision=room_revision
        self.local_survey=local_survey;self.session_anchor=None
        self.causal_innovation_window=False
        if local_survey:self.bounds=[-.9,.9,-.9,.9];self.matcher=None;self.photo=None
        else:
            points=reference['endpoint_cells']
            if reference.get('schema')=='session-survey-map-1.0' and 'tracking_endpoints' in reference:
                if reference.get('tracking_endpoint_basis')!='ACCEPTED_SURVEY_DESKEWED_RETURNS_ODOMETRY_PROJECTED':
                    raise ValueError('MISSION_TRACKING_ENDPOINT_BASIS_INVALID')
                points=reference['tracking_endpoints']
                self.causal_innovation_window=True
            self.bounds=[min(p[0] for p in points)-.1,max(p[0] for p in points)+.1,
                         min(p[1] for p in points)-.1,max(p[1] for p in points)+.1]
            self.matcher=EndpointMatcher({'endpoint_cells':points,'bounds_m':self.bounds},interpolate=True)
        self.transform=None;self.previous=None;self.trace=deque(maxlen=512)
        self.innovations=deque(maxlen=4)
        self.sequence=0
        self.capture=None
        self.footprint_radius_m=.18

    def update(self,pose,scan,now):
        if not isinstance(scan,LocalScan):raise ValueError('MISSION_PLANAR_RAYS_REQUIRED')
        basis='synthetic_model' if scan.provenance=='synthetic_raycast' else 'measured_sensor_extrinsic'
        if (scan.frame_id!='base_link' or scan.transform_basis!=basis or pose.provenance!=scan.provenance
                or not finite(now) or not finite(scan.oldest_sample_s) or not 0<=now-scan.oldest_sample_s<.2
                or not finite(pose.sample_s) or not 0<=now-pose.sample_s<.2
                or not 72<=len(scan.ranges_m)<=720
                or any(not finite(r) or not 0<r<=8 for r in scan.ranges_m)):
            self.transform=None;self.innovations.clear();raise ValueError('MISSION_CURRENT_SENSOR_INVALID')
        count=len(scan.ranges_m)
        points=[[r*math.cos(i*math.tau/count),r*math.sin(i*math.tau/count)] for i,r in enumerate(scan.ranges_m)]
        return self._update_points(pose,points,[[0.,0.]]*len(points),now,scan.oldest_sample_s)

    def update_window(self,window,snapshot,binding,now):
        """Common ROS source, reviewed offset and per-beam odom interpolation.

        Preserve sensor origins; translated rays are NOT uniform base rays.
        Missing brackets or mismatched source stamps remain rejection reasons.
        Actual timing qualification is the owner's separate admission duty.
        """
        from .navigation_binding import navigation_inputs
        pose,_=navigation_inputs(snapshot,binding,now)
        self.footprint_radius_m=max(.18,binding.footprint_radius_m)
        if any(window.context.get(k)!=self.context[k] for k in ('project_id','source_revision')):
            raise ValueError('MISSION_COMMON_SOURCE_CHANGED')
        scan=window.latest['scan']
        if scan is None or scan['data']['stamp_ns']!=snapshot['scan']['source_stamp_ns']:
            raise ValueError('MISSION_COMMON_SCAN_SOURCE_CHANGED')
        data=scan['data'];child_to_scan=compose(binding.child_to_base,binding.base_to_scan)
        current_inverse=inverse(pose.xy_yaw);points=[];origins=[]
        # Verify the complete rolling scan interval before selecting beams.
        end=data['stamp_ns']+round((len(data['ranges_m'])-1)*data['time_increment']*1e9)
        window.pose_at(end)
        step=max(1,math.ceil(len(data['ranges_m'])/160))
        for i in range(0,len(data['ranges_m']),step):
            r=data['ranges_m'][i]
            if not finite(r) or not 0<r<=8:raise ValueError('MISSION_CURRENT_SENSOR_INVALID')
            stamp=data['stamp_ns']+round(i*data['time_increment']*1e9)
            sensor=compose(window.pose_at(stamp),child_to_scan)
            a=data['angle_min']+i*data['angle_increment']
            origins.append(compose(current_inverse,sensor)[:2])
            points.append(compose(current_inverse,compose(sensor,[r*math.cos(a),r*math.sin(a),0.]))[:2])
        return self._update_points(pose,points,origins,now,snapshot['scan']['sample_s'])

    def _update_points(self,pose,points,origins,now,oldest_s):
        if len(points)<24:raise ValueError('MISSION_CURRENT_CLOUD_COVERAGE')
        count=len(points)
        sampled=points[::max(1,math.ceil(count/160))]
        if self.local_survey:
            if self.session_anchor is None:self.session_anchor=inverse(pose.xy_yaw)
            candidate=compose(self.session_anchor,pose.xy_yaw)
            match={'status':'SESSION_LOCAL_OBSERVED','pose':candidate};state='SESSION_LOCAL_OBSERVED'
        elif self.transform is None:
            match=self.matcher.match(sampled)
            state='TRACKING_CANDIDATE' if match['status']=='GEOMETRIC_CANDIDATE' else match['status']
        else:
            predicted=compose(self.transform,pose.xy_yaw)
            match=local_match(self.matcher,sampled,predicted,refine_subcell=True);state=match['status']
        candidate=match.get('pose') if state in {'TRACKING_CANDIDATE','SESSION_LOCAL_OBSERVED'} else None
        if candidate is not None and self.transform is not None and not self.local_survey:
            # Continuous field sampling removes nearest-cell score jumps;
            # retain the bounded innovation filter. Original fit,
            # inlier, observability and jump gates before this bounded filter.
            # Smooth map-from-odom innovations, NOT moving robot poses. The
            # endpoint field can alternate between adjacent local minima as
            # the scan rotates. Filtering poses would lag real odom motion;
            # filtering these transforms preserves that motion at this tick.
            # Only already-gated matches within200ms enter this causal window.
            smoothed=candidate
            if self.causal_innovation_window:
                # The new window applies only to this session's raw-return
                # survey reference. Existing persisted cell-map tracking keeps
                # its accepted single-innovation behavior and serialization.
                if self.innovations and now<=self.innovations[-1][0]:self.innovations.clear()
                while self.innovations and now-self.innovations[0][0]>=.2:self.innovations.popleft()
                self.innovations.append((now,compose(candidate,inverse(pose.xy_yaw))))
                changes=[[row[1][0]-self.transform[0],row[1][1]-self.transform[1],
                          angle(row[1][2]-self.transform[2])] for row in self.innovations]
                mean=[self.transform[i]+sum(row[i] for row in changes)/len(changes) for i in range(3)]
                smoothed=compose(mean,pose.xy_yaw)
                match={**match,'innovation_basis':'CAUSAL_MAP_FROM_ODOM_MAX_4_WITHIN_200MS',
                       'innovation_sample_count':len(changes)}
            residual=[smoothed[0]-predicted[0],smoothed[1]-predicted[1],angle(smoothed[2]-predicted[2])]
            candidate=[predicted[i]+max(-.0025,min(.0025,.15*residual[i])) for i in range(3)]
            candidate[2]=angle(candidate[2])
        if not self.local_survey:
            match={**match,'field_sampling':'60MM_BILINEAR_CHAMFER_NOT_METRIC_CALIBRATION'}
        if candidate is None:self.transform=None;self.innovations.clear()
        else:
            if self.transform is None:self.innovations.clear()
            self.transform=compose(candidate,inverse(pose.xy_yaw))
        grid=EvidenceGrid();cloud=[]
        if candidate is not None:
            rays=[(compose(candidate,[*origin,0.])[:2],compose(candidate,[*p,0.])[:2]) for origin,p in zip(origins,points)]
            # Only this fresh scan clears cells; a historical map never clears
            # a newly occupied/missing area for the current command.
            grid.insert(rays,round(oldest_s*1e9),self.context['source_revision'])
            transform=self.photo.get('room_from_map') if self.photo else None
            if transform:
                # The visual transport allows at most160 endpoints. Select
                # uniformly from original rays ONLY for display; the fresh
                # occupancy grid and diagnostic capture keep every input ray.
                display_step=max(1,math.ceil(len(rays)/160))
                cloud=[compose(transform,[*end,0.])[:2] for _,end in rays[::display_step]]
                self.trace.append(compose(transform,candidate))
        rows=grid.rows();self.sequence+=1
        # Same validated/deskewed rays as the current guard, in the body frame.
        # Diagnostic collection must not manufacture evenly spaced sensor rays.
        self.capture={'sequence':self.sequence,'stamp_ns':round(oldest_s*1e9),
            'pose':list(candidate) if candidate is not None else None,
            'points':deepcopy_points(points),'origins':deepcopy_points(origins)}
        # Timestamps/counters alone do not invalidate a geometrically equal route.
        revision=canonical_sha256([r[:3] for r in rows])
        return {**self.context,'room_revision':self.room_revision,'sample_s':now,
            'state':state,'pose_map':candidate,'bounds':self.bounds,'cells':rows,'cell_size_m':.1,
            'map_revision':revision,'alignment_revision':self.photo.get('report_revision') if self.photo else None,
            'planning_revision_policy':'FRESH_FOOTPRINT_DEPENDENCY_V1',
            'footprint_radius_m':self.footprint_radius_m,
            'room_from_map':self.photo.get('room_from_map') if self.photo else None,
            'alignment_status':self.photo.get('status') if self.photo else 'NOT_AVAILABLE',
            'scan_room':cloud,'trajectory_room':list(self.trace),'match':match,
            'motion_authorized':False,'physical_demo_ready':False}


def deepcopy_points(rows):
    return [list(p) for p in rows]
