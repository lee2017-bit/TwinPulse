# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Bounded causal scan-to-submap frontend. Diagnostic coordinates, never authority.

No photo priors, future frames, ROS/device imports or pose-graph/SLAM claims.
The odom projection and scan-corrected hypothesis remain separate products.
"""
from collections import Counter, deque
from copy import deepcopy
import math

from .observation_stream import ObservationWindow, UNVERIFIED_TIMING
from .room_localization import compose, inverse, angle, deskew
from .sensor_map_localization import EndpointMatcher
from .revisions import canonical_sha256

LIMITS = {'pending_scans':8, 'cells':18000, 'keyframes':128, 'trajectory':512,
          'events':65536, 'range_m':8., 'extent_m':12., 'cell_m':.10,
          'derived_interval_ns':500_000_000, 'scan_wait_ns':500_000_000}


def supported_cloud(points):
    return len(points)>=24 and len({int((math.atan2(y,x)+math.pi)/(math.tau/8))%8 for x,y in points})>=5


def local_match(matcher, points, predicted, *, refine_subcell=False):
    """Small fixed search, not a global matcher on every input callback."""
    if type(refine_subcell) is not bool:raise ValueError('LOCAL_MATCH_REFINEMENT_INVALID')
    if not supported_cloud(points):return {'status':'INSUFFICIENT_ANGULAR_COVERAGE','pose':None}
    options=[]
    for dx in (-.15,-.075,0,.075,.15):
        for dy in (-.15,-.075,0,.075,.15):
            for dt in (-.15,-.075,0,.075,.15):
                pose=[predicted[0]+dx,predicted[1]+dy,angle(predicted[2]+dt)]
                if matcher.possible(pose):options.append((matcher.score(points,pose)[0],pose))
    if not options:return {'status':'LOST','pose':None}
    _,pose=min(options,key=lambda p:p[0])
    # Keep saved/replay refinement unchanged by default. Current control needs
    # subcell resolution: a12.5mm optimizer step near a15mm arrival radius can
    # flip goal bearing across consecutive fresh scans. Continue the SAME
    # bounded search at half steps, without changing fit/jump/ambiguity gates.
    stages=((.025,.025),(.0125,.0125))+(((.00625,.00625),(.003125,.003125)) if refine_subcell else ())
    for delta,turn in stages:
        for _ in range(4):
            candidates=[[pose[0]+dx,pose[1]+dy,angle(pose[2]+dt)] for dx,dy,dt in
                ((0,0,0),(delta,0,0),(-delta,0,0),(0,delta,0),(0,-delta,0),(0,0,turn),(0,0,-turn))]
            candidates=[p for p in candidates if matcher.possible(p)]
            best=min(candidates,key=lambda p:matcher.score(points,p)[0])
            if best==pose:break
            pose=best
    error,inliers=matcher.score(points,pose)
    # A flat translational/angular cost direction is not observable tracking.
    contrasts=[max(matcher.score(points,[pose[0]+dx,pose[1]+dy,angle(pose[2]+dt)])[0]
                   for dx,dy,dt in axis)-error for axis in
               (((.15,0,0),(-.15,0,0)),((0,.15,0),(0,-.15,0)),((0,0,.15),(0,0,-.15)))]
    status='TRACKING_CANDIDATE' if error<=.12 and inliers>=.70 else 'LOST'
    if status=='TRACKING_CANDIDATE' and min(contrasts)<.008:status='AMBIGUOUS'
    if math.dist(pose[:2],predicted[:2])>.25 or abs(angle(pose[2]-predicted[2]))>.25:status='INNOVATION_REJECTED'
    result={'status':status,'pose':pose,'mean_error_m':error,'inlier_fraction':inliers,
            'observability_contrast_m':contrasts}
    if refine_subcell:result.update(current_refinement_step_m=.003125,current_refinement_step_rad=.003125)
    return result


class EvidenceGrid:
    """Time-stamped ray evidence. Absent/invalid/far returns never clear cells."""
    def __init__(self):self.cells={};self.version=0

    def insert(self, rays, stamp, source_revision='unspecified'):
        update={}
        cell=LIMITS['cell_m']
        for origin,end in rays:
            if max(abs(v) for v in origin+end)>LIMITS['extent_m']:raise ValueError('MAP_EXTENT_BUDGET')
            a=tuple(math.floor(v/cell) for v in origin);b=tuple(math.floor(v/cell) for v in end)
            steps=max(abs(b[i]-a[i]) for i in (0,1))
            # Every chosen cell lies on an actually observed, valid finite ray.
            for k in range(steps):
                at=tuple(round(a[i]+(b[i]-a[i])*k/max(steps,1)) for i in (0,1))
                update.setdefault(at,'free')
            update[b]='occupied'
        if len(self.cells.keys() | update.keys())>LIMITS['cells']:raise ValueError('MAP_CELL_BUDGET')
        for key,state in update.items():
            row=self.cells.setdefault(key,{'occupied':0,'free':0,'stamp_ns':stamp})
            row[state]+=1;row['stamp_ns']=stamp;row['source_revision']=source_revision
        if update:self.version+=1

    def rows(self):
        rows=[];size=LIMITS['cell_m']
        for (x,y),r in sorted(self.cells.items()):
            # Conflicting observed cells stay unknown, not convenient free space.
            state='occupied' if r['occupied']>=r['free'] else 'free' if r['occupied']==0 else 'unknown'
            rows.append([(x+.5)*size,(y+.5)*size,state,r['stamp_ns'],r['occupied'],r['free'],r['source_revision']])
        return rows

    def endpoints(self):
        return [[r[0],r[1]] for r in self.rows() if r[4]>0 and r[2]=='occupied']


class AutomaticMapping:
    def __init__(self, context, offset, *, reference=None):
        self.window=ObservationWindow(context);self.context=deepcopy(self.window.context)
        if len(offset)!=3 or not all(type(v) in (int,float) and math.isfinite(v) and abs(v)<1 for v in offset):
            raise ValueError('NOMINAL_EXTRINSIC_INVALID')
        self.offset=list(offset);self.reference=deepcopy(reference)
        if reference:
            if reference['project_id']!=context['project_id']:raise ValueError('MAP_PROJECT_MISMATCH')
            if reference['source_revision']==context['source_revision']:raise ValueError('MAP_QUERY_SOURCE_REUSE')
            if not reference['reference_eligible']:raise ValueError('MAP_NOT_ELIGIBLE_FOR_REVISIT')
        self.pending=deque();self.counts=Counter();self.reasons=Counter();self.transitions=deque(maxlen=64)
        self.odom_grid=EvidenceGrid();self.corrected_grid=EvidenceGrid();self.keyframes=[]
        if reference:
            checked_saved_map(reference,context['project_id'])
            for row in reference['cells']:
                key=(math.floor(row[0]/LIMITS['cell_m']),math.floor(row[1]/LIMITS['cell_m']))
                self.corrected_grid.cells[key]={'stamp_ns':row[3],'occupied':row[4],'free':row[5],'source_revision':row[6]}
            self.corrected_grid.version=1
        self.trace=deque(maxlen=LIMITS['trajectory']);self.anchor=None;self.transform=None
        self.state='LOCALIZING' if reference else 'BOOTSTRAPPING';self.pose=None;self.last_odom=None
        self.last_processed_stamp=None;self.last_derived=None;self.last_global=None;self.match=None
        self.matcher=None;self.matcher_revision=None;self.cache_builds=0
        self.supports=[];self.revisits=0;self.loop_status='NOT_ESTABLISHED'
        self.last_sequence=-1;self.last_receipt=-1;self.finished=False;self.failed=None

    def _state(self, state, reason):
        if state!=self.state or not self.transitions or self.transitions[-1]['reason']!=reason:
            self.transitions.append({'sequence':self.last_sequence,'state':state,'reason':reason})
        self.state=state

    def consume(self, event):
        if self.finished:raise ValueError('AUTOMATIC_INPUT_AFTER_FINISH')
        self.counts['raw_events_seen']+=1
        if self.counts['raw_events_seen']>LIMITS['events']:raise ValueError('AUTOMATIC_EVENT_BUDGET')
        self.last_sequence=event['sequence']
        if event.get('status')=='REJECTED':
            self.reasons[event['reason']]+=1;self.counts['raw_rejected']+=1
            self.transform=None;self.pose=None;self.supports=[];self._state('LOST',event['reason']);return
        receipt=event['receipt_monotonic_ns'];self.last_receipt=receipt
        if self.reference and self.reference['boot_id']==self.context['boot_id'] and receipt<=self.reference['last_receipt_monotonic_ns']:
            raise ValueError('MAP_REFERENCE_NOT_BEFORE_QUERY')
        accepted=self.window.receive(event['topic'],event['data'],event['sequence'],receipt)
        if accepted is None:
            reason=self.window.faults[event['topic']];self.reasons[reason]+=1
            self.transform=None;self.pose=None;self.supports=[];self._state('LOST',reason)
            if self.window.clock_fault or self.window.epoch_fault:raise ValueError(reason)
            return
        if event['topic']=='scan':
            self.counts['scans_seen']+=1
            if len(self.pending)==LIMITS['pending_scans']:
                self.pending.popleft();self.counts['derived_dropped']+=1
                self._state('LOST','DERIVED_PENDING_OVERRUN');self.transform=None;self.pose=None;self.supports=[]
            self.pending.append(accepted)
        if event['topic']=='odom':
            from .room_localization import planar_pose
            current=planar_pose(event['data']);stamp=event['data']['stamp_ns']
            if self.last_odom and (math.dist(current[:2],self.last_odom[1][:2])>.4 or
                                  abs(angle(current[2]-self.last_odom[1][2]))>.5):
                self.transform=None;self.pose=None;self.supports=[];self._state('LOST','ODOM_DISCONTINUITY')
            self.last_odom=(stamp,current)
        if event['topic']=='/tf':
            from .room_localization import planar_pose
            for tf in event['data']['transforms']:
                if (tf['frame_id'],tf['child_frame_id'])!=self.window.frames.get('odom'):continue
                try:expected=self.window.pose_at(tf['stamp_ns'])
                except ValueError:
                    self.counts['tf_unpaired']+=1;continue
                measured=planar_pose({'position_m':tf['translation_m'],'quaternion_xyzw':tf['quaternion_xyzw']})
                self.counts['tf_odom_compared']+=1
                if math.dist(expected[:2],measured[:2])>.001 or abs(angle(expected[2]-measured[2]))>.001:
                    self.failed='ODOM_DYNAMIC_TF_CONFLICT';self.transform=None;self.pose=None
                    self._state('LOST',self.failed);raise ValueError(self.failed)
        while self.pending:
            scan=self.pending[0];end=scan['data']['stamp_ns']+round((len(scan['data']['ranges_m'])-1)*scan['data']['time_increment']*1e9)
            if self.last_odom is None or self.last_odom[0]<end:
                if receipt-scan['receipt_monotonic_ns']>LIMITS['scan_wait_ns']:
                    self.pending.popleft();self.reasons['ODOM_TIME_UNBRACKETED']+=1;continue
                break
            self.pending.popleft()
            try:self._scan(scan)
            except ValueError as exc:
                if 'BUDGET' in str(exc):raise
                self.counts['scans_rejected']+=1;self.reasons[str(exc)]+=1
                self.pose=None;self.transform=None;self.supports=[];self._state('LOST',str(exc))

    def _field(self):
        if self.reference:
            revision=self.reference['revision'];points=self.reference['endpoint_cells']
        else:
            revision=self.corrected_grid.version;points=self.corrected_grid.endpoints()
        if len(points)<24:return None
        if revision!=self.matcher_revision:
            bounds=[min(p[0] for p in points)-.25,max(p[0] for p in points)+.25,
                    min(p[1] for p in points)-.25,max(p[1] for p in points)+.25]
            self.matcher=EndpointMatcher({'endpoint_cells':points,'bounds_m':bounds})
            self.matcher_revision=revision;self.cache_builds+=1
        return self.matcher

    def _scan(self, event):
        scan=event['data']
        if scan['frame_id']!='base_scan':raise ValueError('NOMINAL_SCAN_FRAME_UNSUPPORTED')
        if self.window.frames.get('odom') not in {('odom','base_link'),('odom','base_footprint')}:
            raise ValueError('NOMINAL_ODOM_FRAME_UNSUPPORTED')
        clipped={**scan,'ranges_m':[v if v is not None and v<=LIMITS['range_m'] else None for v in scan['ranges_m']]}
        class Timeline:
            def at(_,stamp):return self.window.pose_at(stamp)
        points,sensor=deskew(clipped,Timeline(),self.offset)
        self.counts['scans_paired']+=1
        if not supported_cloud(points):raise ValueError('INSUFFICIENT_ANGULAR_COVERAGE')
        if self.anchor is None:self.anchor=inverse(sensor)
        odom_pose=compose(self.anchor,sensor)
        # Deskewed endpoints and individual ray origins use the same already-received poses.
        rays=[];step=max(1,math.ceil(len(clipped['ranges_m'])/160));j=0
        for i in range(0,len(clipped['ranges_m']),step):
            if clipped['ranges_m'][i] is None:continue
            beam_sensor=compose(self.window.pose_at(scan['stamp_ns']+round(i*scan['time_increment']*1e9)),self.offset)
            local_origin=compose(inverse(sensor),beam_sensor)[:2]
            rays.append((local_origin,points[j]));j+=1
        self.odom_grid.insert([(compose(odom_pose,[*a,0])[:2],compose(odom_pose,[*b,0])[:2]) for a,b in rays],scan['stamp_ns'],self.context['source_revision'])
        due=self.last_derived is None or scan['stamp_ns']-self.last_derived>=LIMITS['derived_interval_ns']
        if not due:
            self.counts['derived_skipped']+=1
            # The expensive matcher may be downsampled; current pose prediction
            # must not freeze at its last half-second update.
            self.pose=compose(self.transform,sensor) if self.transform is not None else None
            return
        self.last_derived=scan['stamp_ns'];self.counts['derived_processed']+=1
        if self.transform is None and not self.reference and not self.keyframes:
            self.transform=self.anchor;self._state('BOOTSTRAPPING','SESSION_LOCAL_ORIGIN_NOT_GLOBAL_POSE')
        else:
            matcher=self._field()
            if matcher is None:raise ValueError('SUBMAP_TOO_SMALL')
            if self.transform is None:
                if self.last_global is not None and scan['stamp_ns']-self.last_global<2_000_000_000:
                    self.pose=None;self._state('AMBIGUOUS' if self.state=='AMBIGUOUS' else 'LOST','GLOBAL_SEARCH_COOLDOWN');return
                self.last_global=scan['stamp_ns'];self.match=matcher.match(points)
                if self.match['status']!='GEOMETRIC_CANDIDATE':
                    self.pose=None;self._state('AMBIGUOUS' if self.match['status']=='AMBIGUOUS' else 'LOST',self.match['status']);return
            else:self.match=local_match(matcher,points,compose(self.transform,sensor))
            if self.match['status'] not in {'GEOMETRIC_CANDIDATE','TRACKING_CANDIDATE'}:
                self.transform=None;self.pose=None;self.supports=[];self._state('AMBIGUOUS' if self.match['status']=='AMBIGUOUS' else 'LOST',self.match['status']);return
            self.transform=compose(self.match['pose'],inverse(sensor))
            pose=self.match['pose']
            if not self.supports or math.dist(pose[:2],self.supports[-1][:2])>=.10 or abs(angle(pose[2]-self.supports[-1][2]))>=.15:
                self.supports.append(pose);self.supports=self.supports[-8:]
            self._state('TRACKING_CANDIDATE' if len(self.supports)>=3 else 'LOCALIZING','SPATIALLY_SEPARATED_SUPPORT' if len(self.supports)>=3 else 'MORE_INDEPENDENT_MOTION_REQUIRED')
        corrected=compose(self.transform,sensor);self.pose=corrected
        self.trace.append({'stamp_ns':scan['stamp_ns'],'sequence':event['sequence'],'odom_pose':odom_pose,'corrected_pose':corrected,'state':self.state})
        self.counts['trajectory_overwritten']=max(0,self.counts['derived_processed']-LIMITS['trajectory'])
        # Match against past map before inserting current evidence. A revisit is not pose-graph optimization.
        revisited=any(scan['stamp_ns']-k['stamp_ns']>5_000_000_000 and math.dist(corrected[:2],k['pose'][:2])<.25
                      and abs(angle(corrected[2]-k['pose'][2]))<.25 for k in self.keyframes)
        if revisited and self.state=='TRACKING_CANDIDATE':
            self.revisits+=1;self.loop_status='FRONTEND_REVISIT_SUPPORTED_NOT_POSE_GRAPH'
        self.corrected_grid.insert([(compose(corrected,[*a,0])[:2],compose(corrected,[*b,0])[:2]) for a,b in rays],scan['stamp_ns'],self.context['source_revision'])
        if not self.keyframes or math.dist(corrected[:2],self.keyframes[-1]['pose'][:2])>=.15 or abs(angle(corrected[2]-self.keyframes[-1]['pose'][2]))>=.2:
            if len(self.keyframes)>=LIMITS['keyframes']:raise ValueError('MAP_KEYFRAME_BUDGET')
            self.keyframes.append({'stamp_ns':scan['stamp_ns'],'sequence':event['sequence'],'pose':corrected,'points':points,'state':self.state})
        self.last_processed_stamp=scan['stamp_ns']

    def finish(self):
        if not self.finished:
            self.reasons['ODOM_TIME_UNBRACKETED']+=len(self.pending);self.counts['scans_rejected']+=len(self.pending)
            self.pending.clear();self.finished=True
        return self.snapshot()

    def snapshot(self, *, include_map=False):
        result={'schema':'automatic-mapping-1.0','context':self.context,'state':self.state,
            'pose_candidate':deepcopy(self.pose),'counts':dict(self.counts),'reasons':dict(self.reasons),
            'transitions':list(self.transitions),'last_sequence':self.last_sequence,'last_receipt_monotonic_ns':self.last_receipt,
            'pending_scans':len(self.pending),'match':deepcopy(self.match),'trajectory':list(self.trace),
            'keyframe_count':len(self.keyframes),'cache_builds':self.cache_builds,'loop_status':self.loop_status,
            'input_health':self.window.summary(),
            'timing_basis':UNVERIFIED_TIMING,'mapping_method':'BOUNDED_SCAN_SUBMAP_FRONTEND_NOT_GLOBAL_SLAM',
            'limits':LIMITS,'raw_recording_dropped':0,'raw_recording_scope':'VERIFIED_ORIGINAL_NOT_REWRITTEN',
            'alignment_verified':False,'motion_authorized':False,'physical_demo_ready':False,
            'reference_eligible':bool(self.finished and not self.failed and len(self.supports)>=3 and self.revisits>=2),
            'finished':self.finished,'failure':self.failed,'as_built_mount_verified':False}
        if include_map:
            result.update(odom_cells=self.odom_grid.rows(),corrected_cells=self.corrected_grid.rows(),keyframes=deepcopy(self.keyframes),
                          unobserved_cells='UNKNOWN_NOT_STORED',cell_size_m=LIMITS['cell_m'])
        return result

    def saved_map(self):
        if not self.finished:raise ValueError('MAP_SOURCE_NOT_COMPLETE')
        body={'schema':'automatic-map-1.0','project_id':self.context['project_id'],
            'source_revision':self.context['source_revision'],'boot_id':self.context['boot_id'],
            'last_receipt_monotonic_ns':self.last_receipt,'reference_eligible':self.snapshot()['reference_eligible'],
            'offset':self.offset,'endpoint_cells':self.corrected_grid.endpoints(),
            'cells':self.corrected_grid.rows(),'keyframes':self.keyframes,'odom_cells':self.odom_grid.rows(),
            'loop_status':self.loop_status,'timing_basis':UNVERIFIED_TIMING,
            'reference_revision':self.reference['revision'] if self.reference else None,
            'alignment_verified':False,'motion_authorized':False,'physical_demo_ready':False}
        return {**body,'revision':canonical_sha256(body)}


def checked_saved_map(value, project_id):
    value=deepcopy(value);revision=value.pop('revision',None)
    if canonical_sha256(value)!=revision:raise ValueError('AUTOMATIC_MAP_HASH_MISMATCH')
    if value.get('schema')!='automatic-map-1.0' or value.get('project_id')!=project_id:raise ValueError('AUTOMATIC_MAP_PROJECT_OR_SCHEMA')
    if any(value.get(k) is not False for k in ('alignment_verified','motion_authorized','physical_demo_ready')):
        raise ValueError('AUTOMATIC_MAP_AUTHORITY_REJECTED')
    if type(value.get('reference_eligible')) is not bool or value.get('timing_basis')!=UNVERIFIED_TIMING:raise ValueError('AUTOMATIC_MAP_PROVENANCE')
    if len(value.get('cells',[]))>LIMITS['cells'] or len(value.get('keyframes',[]))>LIMITS['keyframes']:raise ValueError('AUTOMATIC_MAP_BUDGET')
    for row in value.get('cells',[]):
        if (not isinstance(row,list) or len(row)!=7 or
            any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>12.1 for v in row[:2]) or
            row[2] not in {'occupied','free','unknown'} or any(type(v) is not int or v<0 for v in row[3:6]) or
            not isinstance(row[6],str)):
            raise ValueError('AUTOMATIC_MAP_CELL_INVALID')
    value['revision']=revision
    return value
