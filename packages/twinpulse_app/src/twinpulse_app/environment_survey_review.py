# SPDX-License-Identifier: Apache-2.0
"""Collected room observations -> reviewed alignment -> explicit common edit.

No connections, motor commands, external model calls or cold-restored authority.
"""
from copy import deepcopy
import hashlib,json,math,re,time
from threading import RLock,Thread,Event
from uuid import uuid4
from twinpulse_core.environment_alignment import wall_references,finite_pose,body_points
from twinpulse_core.environment_survey import review_collection
from twinpulse_core.revisions import canonical_sha256
from twinpulse_core.room_localization import compose,inverse
from .library_asset_store import atomic_json
from .command_broker import BrokerError
from .task_collection import TaskCollection

class EnvironmentSurveyReview:
    def __init__(self,workspace,fleet):
        self.workspace=workspace;self.fleet=fleet;self.root=workspace.root/'survey-reviews'
        self.collections=TaskCollection(workspace.root.parent/'robot-tasks',workspace.workflow._broker.project_id,
            getattr(fleet.physical,'state_root',None))
        self.lock=RLock();self.stop=Event();self.thread=None;self.job=None;self.result=None
        self.collection=None;self.visible=False;self.owner=None;self.digest=None;self.registration=None
        saved=self.root/'last-review.json'
        if saved.is_file() and not saved.is_symlink() and saved.stat().st_size<32*1024*1024:
            try:
                value=json.loads(saved.read_bytes());identity=value['job_id']
                if not re.fullmatch('[a-f0-9]{32}',identity):raise ValueError('SURVEY_SAVED_ID')
                folder=self.root/identity
                result=json.loads((folder/'result.json').read_bytes())
                collection=json.loads((folder/'collection.json').read_bytes())
                if value['result_sha256']!=self.file_sha(folder/'result.json') or value['collection_sha256']!=self.file_sha(folder/'collection.json'):
                    raise ValueError('SURVEY_SAVED_CHANGED')
                self.result=result;self.collection=collection;self.digest=value['result_sha256']
                self.job=dict(job_id=identity,status='SAVED',reason='Saved geometric estimate; no live registration restored.')
            except (OSError,ValueError,KeyError):pass

    @staticmethod
    def file_sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

    def context(self):
        w=self.workspace.workflow
        with w._lock:
            env,rev=self.workspace._current_review(w._application.site_draft)
            return env,dict(project_id=w._broker.project_id,scene_revision=rev,source_sha256=env['source_sha256'],environment_sha256=canonical_sha256(env))

    def snapshot(self):
        try:env,ctx=self.context();refs=wall_references(env)
        except BrokerError:ctx=None;refs=[]
        with self.lock:
            current=bool(self.result and self.result['context']==ctx)
            if not current:self.visible=False;self.registration=None
            return dict(context=ctx,references=refs,collections=self.collections.listing(),job=deepcopy(self.job),
                review=deepcopy(self.result),review_digest=self.digest,visible=self.visible and current,
                registration_active=bool(self.registration and current),physical_authority=False,world_registration_verified=False)

    def action(self,body,owner):
        if not isinstance(body,dict) or not isinstance(body.get('request_id'),str) or not re.fullmatch('[A-Za-z0-9_-]{1,100}',body['request_id']):raise ValueError('SURVEY_REQUEST')
        action=body.get('action')
        if action in {'hide','cancel','clear_registration'}:
            if set(body)!={'action','request_id'}:raise ValueError('SURVEY_ACTION_SHAPE')
            with self.lock:
                if action=='cancel' and (not self.job or self.job['status']!='CHECKING'):raise ValueError('SURVEY_ONLY_PENDING_CHECK_CAN_CANCEL')
                self.visible=False
                if action!='hide':self.registration=None
                if action=='cancel':
                    self.stop.set()
                    if self.job:
                        atomic_json(self.root/self.job['job_id']/'revoked.json',dict(cancelled=True))
                        self.job.update(status='CANCELLED',reason='Explicitly cancelled.')
            return self.snapshot()
        if action in {'show','use_registration'}:
            if set(body)!={'action','request_id','review_digest'}:raise ValueError('SURVEY_ACTION_SHAPE')
            _,ctx=self.context()
            with self.lock:
                self._ready(body['review_digest'],ctx)
                if action=='show':self.visible=True
                else:
                    if self.result['source']!='CURRENT':raise ValueError('SURVEY_LIVE_REGISTRATION_REQUIRES_CURRENT_CHECK')
                    frame=self.current_frame(self.result['robot_id']);last=self.collection['frames'][-1]
                    if self.source_pin(frame)!=self.source_pin(last) or math.dist(frame['native_pose'][:2],last['native_pose'][:2])>.005 or abs(math.atan2(math.sin(frame['native_pose'][2]-last['native_pose'][2]),math.cos(frame['native_pose'][2]-last['native_pose'][2])))>.01:
                        raise ValueError('SURVEY_ROBOT_MOVED_OR_SOURCE_CHANGED')
                    self.registration=dict(context=ctx,pin=self.source_pin(frame),world_from_native=self.result['world_from_native'],
                        review_digest=self.digest,job_id=self.result['job_id'],robot_id=self.result['robot_id'],height_m=self.result['height_m'])
                    self.visible=True
            return self.snapshot()
        if action=='preview_obstacle':return self.preview(body,owner)
        fields={'action','request_id','expected_scene_revision','source','task_id','robot_id','initial_pose','reference_id','reference_length_m','reference_basis','height_m','compare_current_reviewed'}
        if action!='check' or set(body)!=fields or body['source'] not in {'TASK','CURRENT'}:raise ValueError('SURVEY_CHECK_SHAPE')
        env,ctx=self.context()
        if body['expected_scene_revision']!=ctx['scene_revision']:raise ValueError('SURVEY_SCENE_CHANGED')
        finite_pose(body['initial_pose'])
        with self.lock:
            if self.thread and self.thread.is_alive():raise ValueError('SURVEY_CHECK_BUSY')
            self.stop=Event();self.owner=owner;self.visible=False;self.registration=None;self.result=None;self.digest=None
            self.job=dict(job_id=uuid4().hex,status='CHECKING',reason=None)
            self.thread=Thread(target=self.run,args=(deepcopy(body),deepcopy(env),ctx,self.job['job_id']),daemon=True,name='TwinPulseSurveyReview')
            self.thread.start()
        return self.snapshot()

    def _ready(self,digest,ctx):
        if not self.result or digest!=self.digest or self.result['context']!=ctx or self.result['status']!='GEOMETRIC_REVIEW' or self.stop.is_set():raise ValueError('SURVEY_REVIEW_STALE_OR_HELD')
        folder=self.root/self.result['job_id']
        if (self.file_sha(folder/'result.json')!=digest or (folder/'revoked.json').exists()
                or json.loads((folder/'collection.json').read_bytes())!=self.collection):raise ValueError('SURVEY_REVIEW_CHANGED')
        if self.result['source']=='TASK' and self.collections.load(self.collection['task_id'])!=self.collection:
            raise ValueError('SURVEY_ORIGINAL_COLLECTION_CHANGED')

    @staticmethod
    def source_pin(frame):
        return dict(owner=frame['source_owner'],pose_epoch=frame.get('pose_epoch'),config_sha256=frame.get('config_sha256'),
            boot_id=frame.get('boot_id'),release_id=frame.get('release_id'),native_frame_id=frame.get('native_frame_id'),extrinsic=frame['extrinsic'])

    def current_frame(self,robot_id):
        snapshot_started=self.fleet.clock();snapshot_wall_ms=time.time()*1000
        row=next((r for r in self.fleet.snapshot()['robots'] if r['robot_id']==robot_id),None)
        if not row or row['connection_state']!='CONNECTED' or row['lidar_state']!='STREAMING' or row['control_state'] not in {'READY','PAUSED'}:raise ValueError('SURVEY_STOPPED_CURRENT_SENSOR_REQUIRED')
        owner=[row[k] for k in ('robot_id','operation_id','connection_epoch')]
        if row['kind']=='physical':
            from .physical_task_map import PhysicalTaskMap
            row=dict(row,_task_snapshot_started_at=snapshot_started)
            local=PhysicalTaskMap(*owner,clock=self.fleet.clock);value=local.accept(row);local.scene(row,self.fleet.clock)
            p=value['packet'];cfg=p['config'];tf=[cfg[k] for k in ('sensor_x_m','sensor_y_m','sensor_yaw_rad')]
            native=__import__('twinpulse_core.physical_task_observation',fromlist=['wheel_se2']).wheel_se2(p['pose'])
            return dict(identity=value['scan_identity'],points=[compose(inverse(tf),[*point,0.])[:2] for point in p['points_base']],
                native_pose=native,local_pose=[0.,0.,0.],extrinsic=tf,source_owner=owner,source_sha256=p['sha256'],
                stamp=snapshot_wall_ms-row['task_observation_age_ms'],source_kind='PHYSICAL',pose_epoch=p['pose_epoch'],config_sha256=p['config_sha256'],
                boot_id=p['context']['boot_id'],release_id=p['context']['release_id'],native_frame_id=p['pose']['frame_id'],packet=p)
        scan=row.get('scan') or {}
        if scan.get('source')!='isaac_usd_surface_rays' or scan.get('point_frame')!='sensor_local' or not 0<=time.time()*1000-scan['captured_at_ms']<700:raise ValueError('SURVEY_ACTUAL_CURRENT_SIM_SCAN_REQUIRED')
        return dict(identity=[scan['stream_id'],scan['frame_sequence'],scan['captured_at_ms']],points=scan['points'],native_pose=row['pose']['position_m'],
            local_pose=[0.,0.,0.],extrinsic=[-.032,0.,0.],source_owner=owner,source_sha256=canonical_sha256(scan),stamp=scan['captured_at_ms'],source_kind='SIM')

    def run(self,body,env,ctx,identity):
        folder=self.root/identity
        try:
            if any(p.is_symlink() or getattr(p,'is_junction',lambda:False)() for p in (folder,*folder.parents)):raise ValueError('SURVEY_STORAGE_PATH')
            folder.mkdir(parents=True)
            if body['source']=='TASK':
                collection=self.collections.load(body['task_id']);capture=collection['environment_source']
                if any(capture[k]!=env[k] for k in ('source_sha256','meters_per_unit','source_up_axis','units_basis')):raise ValueError('SURVEY_ORIGINAL_SOURCE_OR_UNITS_CHANGED')
                if capture['environment_sha256']!=ctx['environment_sha256'] and body['compare_current_reviewed'] is not True:raise ValueError('SURVEY_CROSS_REVISION_REVIEW_REQUIRED')
            else:
                frames=[];deadline=time.monotonic()+12
                while len(frames)<3 and not self.stop.is_set():
                    frame=self.current_frame(body['robot_id'])
                    if not frames or frame['identity']!=frames[-1]['identity']:frames.append(frame)
                    if time.monotonic()>deadline:raise ValueError('SURVEY_THREE_NEW_CURRENT_FRAMES_REQUIRED')
                    self.stop.wait(.1)
                if not frames:raise ValueError('SURVEY_CANCELLED')
                origin=frames[0]['native_pose']
                for f in frames:
                    f['local_pose']=compose(inverse(origin),f['native_pose'])
                    if math.dist(origin[:2],f['native_pose'][:2])>.005 or abs(f['local_pose'][2])>.01:raise ValueError('SURVEY_CURRENT_INITIALIZATION_MOVED')
                collection=dict(robot_kind='physical' if frames[0]['source_kind']=='PHYSICAL' else 'sim',frames=frames)
            atomic_json(folder/'collection.json',collection)
            result=review_collection(env,collection['frames'],body['initial_pose'],body['reference_id'],body['reference_length_m'],body['reference_basis'],body['height_m'],cancel=self.stop.is_set)
            result.update(job_id=identity,context=ctx,source=body['source'],robot_id=body['robot_id'] if body['source']=='CURRENT' else collection['robot_id'],
                collection_source_revision=(collection.get('environment_source') or {}).get('scene_revision'),
                comparison_current_reviewed=body['compare_current_reviewed'],physical_state_root=str(self.collections.physical_root) if self.collections.physical_root else None)
            atomic_json(folder/'result.json',result)
            manifest=dict(job_id=identity,result_sha256=self.file_sha(folder/'result.json'),collection_sha256=self.file_sha(folder/'collection.json'))
            _,current=self.context()
            with self.lock:
                if self.stop.is_set() or current!=ctx:raise ValueError('SURVEY_CANCELLED_OR_SCENE_CHANGED')
                atomic_json(self.root/'last-review.json',manifest)
                self.result=result;self.collection=collection;self.digest=manifest['result_sha256'];self.job.update(status=result['status'],reason=None)
        except Exception as exc:
            with self.lock:
                if self.job and self.job['job_id']==identity:self.job.update(status='CANCELLED' if self.stop.is_set() else 'HELD',reason=str(exc)[:400])
            try:atomic_json(folder/'failure.json',dict(error=str(exc)[:700]))
            except OSError:pass

    def preview(self,body,owner):
        expected={'action','request_id','review_digest','candidate_id','kind','label','height_m','candidate_ref','duplicate_reviewed'}
        if set(body)!=expected or body['duplicate_reviewed'] is not True:raise ValueError('SURVEY_OBSTACLE_REVIEW_REQUIRED')
        w=self.workspace.workflow
        with w._lock,self.lock:
            _,ctx=self.context();self._ready(body['review_digest'],ctx)
            if self.result['source']!='TASK':raise ValueError('SURVEY_SAVED_MULTIPOSITION_COLLECTION_REQUIRED')
            c=next((c for c in self.result['obstacle_candidates'] if c['candidate_id']==body['candidate_id']),None)
            if c is None:raise ValueError('SURVEY_CANDIDATE_MISSING')
            height=body['height_m']
            if type(height) not in (int,float) or not math.isfinite(height) or not .05<=height<=2.5:raise ValueError('SURVEY_REVIEWED_HEIGHT_REQUIRED')
            obstacle=dict(kind=body['kind'],label=body['label'],position_xy_m=c['position_xy_m'],dimensions_m=[*c['observed_extent_xy_m'],height],yaw_deg=0.,uncertainty_m=c['uncertainty_m'])
            request=dict(action='photo_candidate_preview' if body['candidate_ref'] else 'add_overlay_preview',request_id=body['request_id'],expected_scene_revision=ctx['scene_revision'],obstacle=obstacle)
            request.update(dict(candidate_ref=body['candidate_ref'],duplicate_reviewed=True) if body['candidate_ref'] else dict(photo=None))
            response=self.workspace.action(request,owner);preview=response['preview'];folder=self.root/self.result['job_id']
            binding=dict(schema_version='environment-survey-binding-1.0',policy='review_survey_obstacle',job_id=self.result['job_id'],
                context=w.scene_sensor_review.context(),collection_sha256=self.file_sha(folder/'collection.json'),result_sha256=self.digest,
                candidate_id=c['candidate_id'],preview_sha256=preview['preview_digest'],physical_authority=False)
            self.workspace.previews[preview['operation']['operation_id']]['_survey_binding']=binding
            return dict(self.snapshot(),preview=preview)

    def registration_for(self,row):
        """Session transform only, not motor permission. Live native checks stay separate."""
        with self.lock:
            token=self.registration;r=deepcopy(token)
        if not r:return None
        _,ctx=self.context()
        from twinpulse_core.physical_task_observation import wheel_se2
        pin=dict(owner=[row[k] for k in ('robot_id','operation_id','connection_epoch')],pose_epoch=(row.get('task_local_state') or {}).get('pose_epoch'),
            config_sha256=canonical_sha256((row.get('field') or {}).get('config')),boot_id=row.get('device_boot_id'),release_id=row.get('device_release_id'),native_frame_id=(row.get('pose') or {}).get('frame_id'),extrinsic=r['pin']['extrinsic'])
        if (row.get('task_local_state') or {}).get('fault') or (row.get('task_local_state') or {}).get('pose_valid') is not True:
            raise ValueError('SURVEY_CURRENT_ODOMETRY_INVALID')
        if ctx!=r['context'] or row['robot_id']!=r['robot_id'] or row['connection_state']!='CONNECTED' or pin!=r['pin']:raise ValueError('SURVEY_REGISTRATION_SOURCE_CHANGED')
        pose=wheel_se2(row['pose']);r['world_pose']=compose(r['world_from_native'],pose);r['_token']=token;return r

    def visual_pose(self,row,scene_revision):
        """Fleet-lock safe projection: no review/workflow lock, file or API read.

        The actual fleet model/label owns the body; the review layer owns only
        scan points at their acquisition pose. This grants no control rights.
        """
        token=self.registration
        if not token or token['robot_id']!=row['robot_id'] or token['context']['scene_revision']!=scene_revision:return None
        state=row.get('task_local_state') or {};age=row.get('pose_age_ms');captured=row.get('_physical_projection_at')
        now=self.fleet.clock()
        if (row.get('connection_state')!='CONNECTED' or not row.get('live_heartbeat') or state.get('fault')
                or state.get('pose_valid') is not True or type(age) not in (int,float) or type(captured) not in (int,float)
                or not 0<=now-captured or not 0<=age+(now-captured)*1000<700):return None
        from twinpulse_core.physical_task_observation import wheel_se2
        cfg=(row.get('field') or {}).get('config') or {}
        pin=dict(owner=[row[k] for k in ('robot_id','operation_id','connection_epoch')],pose_epoch=state.get('pose_epoch'),
            config_sha256=canonical_sha256(cfg),boot_id=row.get('device_boot_id'),release_id=row.get('device_release_id'),
            native_frame_id=(row.get('pose') or {}).get('frame_id'),extrinsic=[cfg.get(k) for k in ('sensor_x_m','sensor_y_m','sensor_yaw_rad')])
        if pin!=token['pin']:return None
        try:pose=compose(token['world_from_native'],wheel_se2(row.get('pose')))
        except (ValueError,TypeError,KeyError):return None
        return dict(position_m=pose,visual_epoch=token['job_id'],source='session_geometric_wheel_estimate',accuracy='UNQUALIFIED') if self.registration is token else None

    def overlay(self):
        # A hidden review must not wait behind an unrelated geometry edit.
        # Recheck under the review lock below if a Show raced this fast path.
        if not self.visible:return None
        _,ctx=self.context()
        with self.lock:
            if not self.visible or not self.result or self.result['context']!=ctx:return None
            result=deepcopy(self.result);frame=deepcopy(self.collection['frames'][-1]);registration=self.registration;digest=self.digest
        # Never hold the review lock across fleet/workflow/broker reads. Apply
        # admission owns workflow -> review; reversing it here would deadlock.
        pose=result['frame_validations'][-1]['world_pose'];source='SAVED'
        if registration:
                try:
                    row=next((r for r in self.fleet.snapshot()['robots'] if r['robot_id']==registration['robot_id']),None)
                    if not row or row['lidar_state']!='STREAMING':return None
                    if row['kind']=='physical':
                        checked=self.registration_for(row)
                        if not checked:return None
                        pose=checked['world_pose']
                        # Packet points retain their OWN acquisition pose. A
                        # moving body must not drag an older stationary scan.
                        from twinpulse_core.physical_task_observation import checked_observation,wheel_se2
                        packet=checked_observation(row.get('task_local_observation'))
                        age=row.get('task_observation_age_ms');heartbeat=row.get('telemetry_age_ms')
                        if type(heartbeat) not in (int,float) or not 0<=heartbeat<700:return None
                        points_pose=compose(checked['world_from_native'],wheel_se2(packet['pose']))
                        tf=checked['pin']['extrinsic'];raw=[compose(inverse(tf),[*p,0.])[:2] for p in packet['points_base']]
                        usable=type(age) in (int,float) and 0<=age<700
                        frame=dict(stamp=time.time()*1000-max(heartbeat,age if usable else heartbeat),extrinsic=tf,source_owner=checked['pin']['owner'],points=raw if usable else [])
                    else:
                        frame=self.current_frame(registration['robot_id'])
                        if self.source_pin(frame)!=registration['pin']:return None
                        pose=compose(registration['world_from_native'],frame['native_pose']);points_pose=pose
                    source='CURRENT'
                except (ValueError,BrokerError):return None
        else:points_pose=pose
        points=body_points(frame['points'],frame['extrinsic']) if frame['points'] else [];sample=points[::max(1,math.ceil(len(points)/180))][:180]
        state=self.workspace.workflow._broker.supervisor_state();snap=state.get('snapshot') or {}
        if not state['engine_connected'] or snap.get('project_id')!=ctx['project_id'] or snap.get('applied_revision')!=ctx['scene_revision']:return None
        with self.lock:
            if not self.visible or self.digest!=digest or self.registration is not registration or self.stop.is_set():return None
            return dict(review_id=result['job_id'],source=source,body_pose=pose,sensor_pose=compose(points_pose,frame['extrinsic']),height_m=result['height_m'],scene_revision=ctx['scene_revision'],
                points_body=sample,points_pose=points_pose,show_body=source!='CURRENT',status='GEOMETRIC_REVIEW',physical_authority=False,original_captured_at_ms=frame['stamp'],source_owner=frame['source_owner'])

    def close(self):
        self.stop.set();self.visible=False;self.registration=None
        if self.thread:self.thread.join(timeout=8)
        if self.thread and self.thread.is_alive():raise RuntimeError('SURVEY_REVIEW_JOIN_UNCONFIRMED')
