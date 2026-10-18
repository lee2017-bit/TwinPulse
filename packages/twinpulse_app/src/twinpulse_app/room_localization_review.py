# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Product path: saved scan -> global pose candidate -> Twin/odom goal.

Never feeds the physical mission adapter or replaces a measured calibration.
Every request binds project, scene bytes, raw bytes, frame and reposition epoch.
"""
from copy import deepcopy
import json
import re
from pathlib import Path
import threading
from uuid import uuid4

from twinpulse_core.revisions import canonical_sha256
from twinpulse_core.scan_observation import build_observation_map
from twinpulse_core.observation_model_comparison import compare_observation_model
from twinpulse_core.sensor_map_localization import locate_in_sensor_map
from twinpulse_core.sensor_photo_link import photo_wall_anchors, link_sensor_to_photo, preview_link_goal
from twinpulse_core.room_localization import (RoomMatcher, SessionLocalization,
    compose, inverse, deskew, scene_outline)
from .bedroom_review import load_bedroom_source
from .robot_geometry_evidence import load_geometry_evidence
from .saved_mapping_evidence import load_saved_mapping
from .command_broker import BrokerError


class RoomLocalizationReview:
    def __init__(self, root, project_id, *, source_loader=load_bedroom_source,
                 evidence_loader=load_saved_mapping, geometry_loader=load_geometry_evidence):
        self.root=Path(root).resolve() if root is not None else None;self.project_id=project_id
        self.source_loader=source_loader;self.evidence_loader=evidence_loader;self.geometry_loader=geometry_loader
        self.lock=threading.RLock();self.work=threading.Lock();self.localization=SessionLocalization()
        self.last=None;self.map=None;self.observation=None;self.sensor_match=None;self.photo_link=None

    def _scene(self, revision):
        if self.project_id!='default':raise ValueError('DEFAULT_PHOTO_ROOM_PROJECT_REQUIRED')
        draft,manifest,_=self.source_loader()
        if revision!=manifest['manifest_sha256']:raise ValueError('ROOM_SOURCE_CHANGED')
        return draft,manifest

    def snapshot(self):
        with self.lock:
            return {'epoch':self.localization.epoch,'result':deepcopy(self.last),
                    'motion_authorized':False,'physical_demo_ready':False}

    def invalidate(self):
        with self.lock:
            self.localization.invalidate();self.last=None;self.observation=None;self.sensor_match=None;self.photo_link=None
            return self.snapshot()

    def observation_map(self, job_id):
        """No photo room is consulted, matched, edited or authorized here."""
        if self.root is None:raise BrokerError('observation_map_rejected','SAVED_SESSION_ROOT_UNAVAILABLE',status=409)
        if not self.work.acquire(blocking=False):
            raise BrokerError('localization_busy','A saved scan review is already running',status=409)
        try:
            with self.lock:
                self.localization.invalidate();self.last=None;self.observation=None;self.sensor_match=None;self.photo_link=None
                request_epoch=self.localization.epoch
            evidence=self.evidence_loader(self.root,self.project_id,job_id)
            geometry=self.geometry_loader()
            base=geometry['base_footprint_to_base_link_xyz_m'];mount=geometry['base_link_to_scan_xyz_m']
            child=evidence['odom'][0]['child_frame_id']
            if child not in {'base_footprint','base_link'}:raise ValueError('NOMINAL_EXTRINSIC_FRAME_UNSUPPORTED')
            if evidence['scans'][0]['frame_id']!='base_scan':raise ValueError('NOMINAL_SCAN_FRAME_UNSUPPORTED')
            offset=[mount[0]+(base[0] if child=='base_footprint' else 0),
                    mount[1]+(base[1] if child=='base_footprint' else 0),0.]
            body=build_observation_map(evidence['scans'],evidence['timeline'],offset)
            body.update(job_id=job_id,project_id=self.project_id,source_revision=evidence['source_revision'],
                boot_id=evidence['boot_id'],release_id=evidence['release_id'],
                nominal_geometry_revision=geometry['revision'],
                sensor_extrinsic='NOMINAL_MODEL_NOT_AS_BUILT',diagnostics=evidence['diagnostics'])
            with self.lock:
                if request_epoch!=self.localization.epoch:raise ValueError('LOCALIZATION_INVALIDATED_DURING_REVIEW')
                body['epoch']=request_epoch;body['report_id']=job_id+'-'+uuid4().hex
                body['revision']=canonical_sha256(body)
                output=self.root/'artifacts/session-observation-map'
                if output.parent.is_symlink() or output.is_symlink() or not output.resolve().is_relative_to(self.root):
                    raise ValueError('OBSERVATION_OUTPUT_PATH_UNSAFE')
                output.mkdir(parents=True,exist_ok=True)
                encoded=json.dumps(body,sort_keys=True,allow_nan=False)
                if len(encoded.encode('utf-8'))>4*1024*1024:raise ValueError('OBSERVATION_REPORT_SIZE_BUDGET')
                with (output/(body['report_id']+'.json')).open('x',encoding='utf-8') as stream:stream.write(encoded)
                self.observation=body
                return deepcopy(body)
        except (OSError,ValueError,KeyError,TypeError) as exc:
            with self.lock:self.observation=None
            raise BrokerError('observation_map_rejected',str(exc)[:180],status=409) from exc
        finally:self.work.release()

    def locate_sensor_map(self, job_id, observation_revision, query_job_id, frame):
        """No photo scene, physical binding, deployment or runtime authority."""
        if not self.work.acquire(blocking=False):
            raise BrokerError('localization_busy','A saved scan review is already running',status=409)
        try:
            with self.lock:
                observed=deepcopy(self.observation);epoch=self.localization.epoch
                self.localization.binding=None;self.last=None;self.sensor_match=None;self.photo_link=None
            if not observed or observed['job_id']!=job_id or observed['revision']!=observation_revision or observed['epoch']!=epoch:
                raise ValueError('SENSOR_MATCH_CURRENT_OBSERVATION_REQUIRED')
            reference=self.evidence_loader(self.root,self.project_id,job_id)
            query=reference if query_job_id==job_id else self.evidence_loader(self.root,self.project_id,query_job_id)
            geometry=self.geometry_loader()
            if reference['source_revision']!=observed['source_revision']:raise ValueError('SAVED_RAW_SOURCE_CHANGED')
            if geometry['revision']!=observed['nominal_geometry_revision']:raise ValueError('NOMINAL_SENSOR_GEOMETRY_CHANGED')
            def offset(value):
                child=value['odom'][0]['child_frame_id']
                if child not in {'base_footprint','base_link'}:raise ValueError('NOMINAL_EXTRINSIC_FRAME_UNSUPPORTED')
                mount=geometry['base_link_to_scan_xyz_m'];base=geometry['base_footprint_to_base_link_xyz_m']
                return [mount[0]+(base[0] if child=='base_footprint' else 0),mount[1]+(base[1] if child=='base_footprint' else 0),0.]
            body=locate_in_sensor_map(reference,query,frame,offset(reference),offset(query))
            for name,value in ((job_id,reference),(query_job_id,query)):
                if self.evidence_loader(self.root,self.project_id,name)['source_revision']!=value['source_revision']:
                    raise ValueError('SAVED_RAW_SOURCE_CHANGED')
            if self.geometry_loader()['revision']!=geometry['revision']:raise ValueError('NOMINAL_SENSOR_GEOMETRY_CHANGED')
            with self.lock:
                if epoch!=self.localization.epoch or self.observation is None or self.observation['revision']!=observation_revision:
                    raise ValueError('SENSOR_MATCH_INVALIDATED_DURING_REVIEW')
                body.update(job_id=job_id,query_job_id=query_job_id,project_id=self.project_id,observation_revision=observation_revision,
                    reference_source_revision=reference['source_revision'],query_source_revision=query['source_revision'],
                    reference_boot_id=reference['boot_id'],query_boot_id=query['boot_id'],reference_release_id=reference['release_id'],
                    query_release_id=query['release_id'],nominal_geometry_revision=geometry['revision'],epoch=epoch,
                    report_id=job_id+'-'+uuid4().hex)
                body['revision']=canonical_sha256(body)
                output=self.root/'artifacts/sensor-map-localization'
                if output.parent.is_symlink() or output.is_symlink() or not output.resolve().is_relative_to(self.root):
                    raise ValueError('SENSOR_MATCH_OUTPUT_PATH_UNSAFE')
                output.mkdir(parents=True,exist_ok=True)
                encoded=json.dumps(body,sort_keys=True,allow_nan=False)
                if len(encoded.encode('utf-8'))>4*1024*1024:raise ValueError('SENSOR_MATCH_REPORT_SIZE_BUDGET')
                with (output/(body['report_id']+'.json')).open('x',encoding='utf-8') as stream:stream.write(encoded)
                self.sensor_match=body
                return deepcopy(body)
        except (OSError,ValueError,KeyError,TypeError) as exc:
            raise BrokerError('sensor_map_localization_rejected',str(exc)[:180],status=409) from exc
        finally:self.work.release()

    def _sensor_photo_context(self, revision, sensor_revision):
        with self.lock:
            sensor=deepcopy(self.sensor_match);observed=deepcopy(self.observation);epoch=self.localization.epoch
        if (not sensor or sensor['revision']!=sensor_revision or sensor['epoch']!=epoch or not observed or
            observed['revision']!=sensor['observation_revision'] or observed['epoch']!=epoch):
            raise ValueError('LINK_CURRENT_SENSOR_POSITION_REQUIRED')
        if sensor['status']!='SENSOR_MAP_GEOMETRIC_CANDIDATE':raise ValueError('SENSOR_POSITION_NOT_UNIQUE')
        draft,manifest=self._scene(revision);geometry=self.geometry_loader()
        for prefix,job in (('reference',sensor['job_id']),('query',sensor['query_job_id'])):
            evidence=self.evidence_loader(self.root,self.project_id,job)
            if evidence['source_revision']!=sensor[prefix+'_source_revision']:raise ValueError('SAVED_RAW_SOURCE_CHANGED')
        if geometry['revision']!=sensor['nominal_geometry_revision']:raise ValueError('NOMINAL_SENSOR_GEOMETRY_CHANGED')
        height=geometry['base_link_to_scan_xyz_m'][2]+geometry['base_footprint_to_base_link_xyz_m'][2]
        context=photo_wall_anchors(draft.site.scene.to_dict()['objects'],height)
        context.update(room_revision=revision,scene_revision=draft.site.scene.revision,sensor_revision=sensor_revision,
                       project_id=self.project_id,epoch=epoch,nominal_geometry_revision=geometry['revision'],
                       correspondence_kind='OPERATOR_SELECTED_APPROXIMATE_VISUAL_NOT_SURVEYED',motion_authorized=False)
        context['revision']=canonical_sha256(context)
        with self.lock:
            if epoch!=self.localization.epoch or not self.sensor_match or self.sensor_match['revision']!=sensor_revision:
                raise ValueError('LINK_INVALIDATED_DURING_CONTEXT')
        return context,sensor

    def photo_link_context(self, revision, sensor_revision):
        if not self.work.acquire(blocking=False):raise BrokerError('localization_busy','A saved scan review is already running',status=409)
        try:return self._sensor_photo_context(revision,sensor_revision)[0]
        except (OSError,ValueError,KeyError,TypeError) as exc:
            with self.lock:self.photo_link=None
            raise BrokerError('sensor_photo_link_rejected',str(exc)[:180],status=409) from exc
        finally:self.work.release()

    def link_photo(self, revision, sensor_revision, context_revision, pairs):
        if not self.work.acquire(blocking=False):raise BrokerError('localization_busy','A saved scan review is already running',status=409)
        try:
            with self.lock:self.photo_link=None;self.last=None;self.localization.binding=None
            context,sensor=self._sensor_photo_context(revision,sensor_revision)
            if context['revision']!=context_revision:raise ValueError('LINK_WALL_CONTEXT_CHANGED')
            body=link_sensor_to_photo(sensor,context,pairs)
            again,_=self._sensor_photo_context(revision,sensor_revision)
            if again['revision']!=context_revision:raise ValueError('LINK_CONTEXT_CHANGED_DURING_REVIEW')
            with self.lock:
                if self.localization.epoch!=sensor['epoch'] or not self.sensor_match or self.sensor_match['revision']!=sensor_revision:
                    raise ValueError('LINK_INVALIDATED_DURING_REVIEW')
                body.update(room_revision=revision,scene_revision=context['scene_revision'],sensor_revision=sensor_revision,
                    context_revision=context_revision,reference_map_revision=sensor['reference_map_revision'],
                    reference_source_revision=sensor['reference_source_revision'],query_source_revision=sensor['query_source_revision'],
                    job_id=sensor['job_id'],query_job_id=sensor['query_job_id'],project_id=self.project_id,epoch=sensor['epoch'],
                    nominal_geometry_revision=sensor['nominal_geometry_revision'],report_id=sensor['job_id']+'-'+uuid4().hex)
                body['revision']=canonical_sha256(body)
                output=self.root/'artifacts/sensor-photo-link'
                if output.parent.is_symlink() or output.is_symlink() or not output.resolve().is_relative_to(self.root):
                    raise ValueError('LINK_OUTPUT_PATH_UNSAFE')
                output.mkdir(parents=True,exist_ok=True)
                encoded=json.dumps(body,sort_keys=True,allow_nan=False)
                if len(encoded.encode('utf-8'))>1024*1024:raise ValueError('LINK_REPORT_SIZE_BUDGET')
                with (output/(body['report_id']+'.json')).open('x',encoding='utf-8') as stream:stream.write(encoded)
                self.photo_link=body
                return deepcopy(body)
        except (OSError,ValueError,KeyError,TypeError) as exc:
            with self.lock:self.photo_link=None
            raise BrokerError('sensor_photo_link_rejected',str(exc)[:180],status=409) from exc
        finally:self.work.release()

    def photo_link_goal(self, revision, link_revision, goal):
        if not self.work.acquire(blocking=False):raise BrokerError('localization_busy','A saved scan review is already running',status=409)
        try:
            with self.lock:link=deepcopy(self.photo_link)
            if not link or link['revision']!=link_revision:raise ValueError('LINK_CURRENT_REPORT_REQUIRED')
            context,_=self._sensor_photo_context(revision,link['sensor_revision'])
            if context['revision']!=link['context_revision']:raise ValueError('LINK_WALL_CONTEXT_CHANGED')
            result=preview_link_goal(link,goal)
            with self.lock:
                if not self.photo_link or self.photo_link['revision']!=link_revision or self.localization.epoch!=link['epoch']:
                    raise ValueError('LINK_INVALIDATED_DURING_GOAL')
            return {**result,'link_revision':link_revision,'query_job_id':link['query_job_id']}
        except (OSError,ValueError,KeyError,TypeError) as exc:
            with self.lock:self.photo_link=None
            raise BrokerError('sensor_photo_goal_rejected',str(exc)[:180],status=409) from exc
        finally:self.work.release()

    def compare_model(self, revision, job_id, observation_revision):
        """Compare a current saved map; never bind a goal or modify a scene."""
        if not self.work.acquire(blocking=False):
            raise BrokerError('localization_busy','A saved scan review is already running',status=409)
        try:
            with self.lock:
                observed=deepcopy(self.observation)
                epoch=self.localization.epoch
                self.localization.binding=None;self.last=None;self.sensor_match=None;self.photo_link=None
            if not observed or observed['job_id']!=job_id or observed['revision']!=observation_revision or observed['epoch']!=epoch:
                raise ValueError('COMPARISON_CURRENT_OBSERVATION_REQUIRED')
            draft,manifest=self._scene(revision)
            evidence=self.evidence_loader(self.root,self.project_id,job_id)
            geometry=self.geometry_loader()
            if evidence['source_revision']!=observed['source_revision']:raise ValueError('SAVED_RAW_SOURCE_CHANGED')
            if geometry['revision']!=observed['nominal_geometry_revision']:raise ValueError('NOMINAL_SENSOR_GEOMETRY_CHANGED')
            height=geometry['base_link_to_scan_xyz_m'][2]+geometry['base_footprint_to_base_link_xyz_m'][2]
            body=compare_observation_model(observed,draft.site.scene.to_dict()['objects'],height)
            self._scene(revision)
            # Recheck bytes after search, not just the cached diagnostic identity.
            if self.evidence_loader(self.root,self.project_id,job_id)['source_revision']!=observed['source_revision']:
                raise ValueError('SAVED_RAW_SOURCE_CHANGED')
            if self.geometry_loader()['revision']!=geometry['revision']:raise ValueError('NOMINAL_SENSOR_GEOMETRY_CHANGED')
            with self.lock:
                if epoch!=self.localization.epoch or self.observation is None or self.observation['revision']!=observation_revision:
                    raise ValueError('COMPARISON_INVALIDATED_DURING_REVIEW')
                body.update(job_id=job_id,project_id=self.project_id,room_revision=revision,
                    scene_revision=draft.site.scene.revision,source_revision=observed['source_revision'],
                    observation_revision=observation_revision,nominal_geometry_revision=geometry['revision'],epoch=epoch,
                    report_id=job_id+'-'+uuid4().hex)
                body['revision']=canonical_sha256(body)
                output=self.root/'artifacts/observation-model-comparison'
                if output.parent.is_symlink() or output.is_symlink() or not output.resolve().is_relative_to(self.root):
                    raise ValueError('COMPARISON_OUTPUT_PATH_UNSAFE')
                output.mkdir(parents=True,exist_ok=True)
                encoded=json.dumps(body,sort_keys=True,allow_nan=False)
                if len(encoded.encode('utf-8'))>1024*1024:raise ValueError('COMPARISON_REPORT_SIZE_BUDGET')
                with (output/(body['report_id']+'.json')).open('x',encoding='utf-8') as stream:stream.write(encoded)
                return deepcopy(body)
        except (OSError,ValueError,KeyError,TypeError) as exc:
            raise BrokerError('observation_comparison_rejected',str(exc)[:180],status=409) from exc
        finally:self.work.release()

    def analyse(self, revision, job_id, frame):
        if type(frame) is not int or not 0<=frame<8192:raise ValueError('SCAN_FRAME_INDEX_INVALID')
        if self.root is None:raise ValueError('SAVED_SESSION_ROOT_UNAVAILABLE')
        if not self.work.acquire(blocking=False):
            raise BrokerError('localization_busy','A saved scan review is already running',status=409)
        try:
            with self.lock:
                self.localization.invalidate();self.last=None;self.sensor_match=None;self.photo_link=None
                request_epoch=self.localization.epoch
            draft,manifest=self._scene(revision)
            evidence=self.evidence_loader(self.root,self.project_id,job_id)
            if frame>=len(evidence['scans']):raise ValueError('SCAN_FRAME_NOT_RECORDED')
            geometry=self.geometry_loader()
            base=geometry['base_footprint_to_base_link_xyz_m'];scan=geometry['base_link_to_scan_xyz_m']
            child=evidence['odom'][0]['child_frame_id']
            if child not in {'base_footprint','base_link'}:raise ValueError('NOMINAL_EXTRINSIC_FRAME_UNSUPPORTED')
            if evidence['scans'][frame]['frame_id']!='base_scan':raise ValueError('NOMINAL_SCAN_FRAME_UNSUPPORTED')
            child_to_scan=[scan[0]+(base[0] if child=='base_footprint' else 0),
                           scan[1]+(base[1] if child=='base_footprint' else 0),0.]
            outline=scene_outline(draft.site.scene.to_dict()['objects'],scan[2]+base[2])
            if self.map is None or self.map.outline['revision']!=outline['revision']:
                self.map=RoomMatcher(outline)
            scan_frame=evidence['scans'][frame]
            # Collect independent pairing/deskew failures for every frame, not
            # an early failure that conceals all the other recorded samples.
            failures=[];paired=0;selected=None
            for i,item in enumerate(evidence['scans']):
                try:
                    points,pose=deskew(item,evidence['timeline'],child_to_scan)
                    paired+=1
                    if i==frame:selected=(points,pose)
                except ValueError as exc:failures.append({'frame':i,'raw_sequence':item['raw_sequence'],'reason':str(exc)})
            result={'status':'TIME_PAIRING_REJECTED','pose':None} if selected is None else self.map.match(selected[0])
            room_from_odom=None;room_pose=None;points_room=[];trajectory=[]
            if selected is not None and result.get('pose') is not None:
                room_from_odom=compose(result['pose'],inverse(selected[1]))
                child_pose=compose(room_from_odom,evidence['timeline'].at(scan_frame['stamp_ns']))
                room_pose=compose(child_pose,[base[0],base[1],0]) if child=='base_footprint' else child_pose
                points_room=[compose(result['pose'],[*p,0])[:2] for p in selected[0]]
                stride=max(1,len(evidence['odom'])//500)
                trajectory=[{'stamp_ns':row['stamp_ns'],
                    'pose':compose(room_from_odom,evidence['timeline'].at(row['stamp_ns']))}
                    for row in evidence['odom'][::stride]]
            body={'schema':'room-localization-review-1.0','job_id':job_id,'room_revision':revision,
                'scene_revision':draft.site.scene.revision,'source_revision':evidence['source_revision'],
                'boot_id':evidence['boot_id'],'release_id':evidence['release_id'],'frame':frame,
                'frame_count':len(evidence['scans']),'stamp_ns':scan_frame['stamp_ns'],
                'elapsed_s':(scan_frame['stamp_ns']-evidence['scans'][0]['stamp_ns'])/1e9,
                'duration_s':(evidence['scans'][-1]['stamp_ns']-evidence['scans'][0]['stamp_ns'])/1e9,
                'match':result,'sensor_pose_room_candidate':result.get('pose'),
                'robot_pose_room_candidate':room_pose,'room_from_odom_candidate':room_from_odom,
                'scan_points_room_candidate':points_room,'trajectory_candidate':trajectory,
                'outline':outline,'timing':{'paired_frames':paired,'rejected_frames':len(failures),'failures':failures[:128],
                    'basis':'DECLARED_ROS_HEADER_NOT_VERIFIED_FIRST_RAY','acquisition_timing_verified':False},
                'diagnostics':evidence['diagnostics'],'nominal_geometry_revision':geometry['revision'],
                'alignment_verified':False,'motion_authorized':False,'physical_demo_ready':False,
                'geometry_status':'PHOTO_APPROXIMATION_NOT_SURVEYED',
                'pose_basis':'GLOBAL_SCAN_MATCH_PLUS_WHEEL_ODOM_AND_NOMINAL_EXTRINSIC_NOT_MEASURED_FLOOR_POSE'}
            self._scene(revision)  # Re-check bytes after the potentially long computation.
            with self.lock:
                if request_epoch!=self.localization.epoch:raise ValueError('LOCALIZATION_INVALIDATED_DURING_REVIEW')
                epoch=self.localization.begin(job_id,evidence['source_revision'],draft.site.scene.revision)
                if selected:self.localization.accept(epoch,result,selected[1],scan_frame['stamp_ns'])
                body['epoch']=epoch;body['goal_candidate_available']=self.localization.binding is not None
                body['report_id']=job_id+'-'+uuid4().hex
                body['revision']=canonical_sha256(body);self.last=body
                # Exclusive derived report, never replaces measured originals.
                output=self.root/'artifacts/room-localization-review'
                if output.parent.is_symlink() or output.is_symlink() or not output.resolve().is_relative_to(self.root):
                    self.invalidate();raise ValueError('LOCALIZATION_OUTPUT_PATH_UNSAFE')
                output.mkdir(parents=True,exist_ok=True)
                with (output/(body['report_id']+'.json')).open('x',encoding='utf-8') as stream:
                    json.dump(body,stream,sort_keys=True,allow_nan=False)
                return deepcopy(body)
        except (OSError,ValueError,KeyError,TypeError) as exc:
            with self.lock:self.localization.invalidate();self.last=None
            raise BrokerError('localization_review_rejected',str(exc)[:180],status=409) from exc
        finally:self.work.release()

    def goal(self, revision, result_revision, epoch, goal):
        with self.lock:
            if not self.last or self.last['revision']!=result_revision or type(epoch) is not int:
                raise BrokerError('localization_stale','Review the current scan again',status=409)
            # Revalidate source identity at use; cached coordinates never outlive
            # a changed recording, room, process restart or explicit reposition.
            try:
                draft,manifest=self._scene(revision)
                current=self.evidence_loader(self.root,self.project_id,self.last['job_id'])
                if current['source_revision']!=self.last['source_revision']:
                    raise ValueError('SAVED_RAW_SOURCE_CHANGED')
                if self.geometry_loader()['revision']!=self.last['nominal_geometry_revision']:
                    raise ValueError('NOMINAL_SENSOR_GEOMETRY_CHANGED')
            except (OSError,ValueError,KeyError,TypeError) as exc:
                self.invalidate()
                raise BrokerError('localization_stale',str(exc)[:180],status=409) from exc
            try:
                if not self.last['goal_candidate_available']:
                    raise ValueError('LOCALIZATION_'+self.last['match']['status'])
                bounds=self.last['outline']['bounds_m']
                if len(goal)!=2 or not bounds[0]<=goal[0]<=bounds[1] or not bounds[2]<=goal[1]<=bounds[3]:
                    raise ValueError('GOAL_OUTSIDE_ROOM')
                candidate=self.localization.goal(goal,epoch=epoch,session_id=self.last['job_id'],
                    source_revision=current['source_revision'],scene_revision=draft.site.scene.revision,
                    stamp_ns=self.last['stamp_ns'])
            except (ValueError,TypeError) as exc:raise BrokerError('localization_goal_rejected',str(exc),status=409) from exc
            return {**candidate,'twin_goal_xy_m':goal,'result_revision':result_revision,
                    'job_id':self.last['job_id'],'scope':'SAVED_FRAME_ONLY_NOT_CURRENT_ROBOT',
                    'mission_request':None}

    def visual_descriptor(self, revision, result_revision):
        with self.lock:
            try:self._scene(revision)
            except (OSError,ValueError,KeyError,TypeError) as exc:
                self.invalidate()
                raise BrokerError('localization_stale',str(exc)[:180],status=409) from exc
            if not self.last or self.last['revision']!=result_revision or self.last['robot_pose_room_candidate'] is None:
                raise BrokerError('localization_stale','Review a saved scan with a pose candidate first',status=409)
            return {'report_id':self.last['report_id'],'revision':result_revision}


def checked_localization_visual(descriptor, draft, *, root=None):
    from .bedroom_review import ROOT
    root=Path(root or ROOT).resolve()
    if (type(descriptor) is not dict or set(descriptor)!={'report_id','revision'} or
        type(descriptor['report_id']) is not str or not re.fullmatch('[a-f0-9]{32}-[a-f0-9]{32}',descriptor['report_id']) or
        type(descriptor['revision']) is not str or not re.fullmatch('[a-f0-9]{64}',descriptor['revision'])):
        raise ValueError('LOCALIZATION_VISUAL_DESCRIPTOR')
    path=root/'artifacts/room-localization-review'/(descriptor['report_id']+'.json')
    if (path.is_symlink() or path.parent.is_symlink() or not path.resolve().is_relative_to(root) or
        path.stat().st_size>1024*1024):raise ValueError('LOCALIZATION_VISUAL_PATH_OR_SIZE')
    body=json.loads(path.read_text(encoding='utf-8'))
    body_revision=body.pop('revision')
    if body_revision!=descriptor['revision'] or canonical_sha256(body)!=body_revision:
        raise ValueError('LOCALIZATION_VISUAL_HASH')
    if (body['schema']!='room-localization-review-1.0' or
        body['scene_revision']!=draft.site.scene.revision or body['report_id']!=descriptor['report_id'] or
        body['alignment_verified'] is not False or body['motion_authorized'] is not False or
        body['physical_demo_ready'] is not False):raise ValueError('LOCALIZATION_VISUAL_CONTEXT')
    evidence=load_saved_mapping(root,'default',body['job_id'])
    geometry=load_geometry_evidence()
    if (body['source_revision']!=evidence['source_revision'] or
        body['nominal_geometry_revision']!=geometry['revision']):raise ValueError('LOCALIZATION_VISUAL_SOURCE_CHANGED')
    scan=evidence['scans'][body['frame']]
    if body['stamp_ns']!=scan['stamp_ns'] or body['frame_count']!=len(evidence['scans']):
        raise ValueError('LOCALIZATION_VISUAL_FRAME_CHANGED')
    base=geometry['base_footprint_to_base_link_xyz_m'];mount=geometry['base_link_to_scan_xyz_m']
    child=evidence['odom'][0]['child_frame_id']
    offset=[mount[0]+(base[0] if child=='base_footprint' else 0),mount[1]+(base[1] if child=='base_footprint' else 0),0.]
    points,odom_sensor=deskew(scan,evidence['timeline'],offset)
    sensor_pose=body['match']['pose']
    transform=compose(sensor_pose,inverse(odom_sensor))
    robot_pose=compose(transform,evidence['timeline'].at(scan['stamp_ns']))
    if child=='base_footprint':robot_pose=compose(robot_pose,[base[0],base[1],0])
    # Recompute display coordinates from original sensor/odom bytes. Never use
    # uploaded coordinates as engine geometry or execution instructions.
    expected_points=[compose(sensor_pose,[*p,0])[:2] for p in points]
    stride=max(1,len(evidence['odom'])//500)
    expected_trace=[{'stamp_ns':row['stamp_ns'],'pose':compose(transform,evidence['timeline'].at(row['stamp_ns']))}
                    for row in evidence['odom'][::stride]]
    if (body['robot_pose_room_candidate']!=robot_pose or body['scan_points_room_candidate']!=expected_points or
        body['trajectory_candidate']!=expected_trace):raise ValueError('LOCALIZATION_VISUAL_REPROJECTION_CHANGED')
    return {**body,'revision':body_revision,'scan_height_m':mount[2]+base[2]}
