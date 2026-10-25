# SPDX-License-Identifier: Apache-2.0
"""Project-local alignment review, separate from ALL robot/navigation authority."""
from copy import deepcopy
import json,math,re,time
from threading import RLock,Thread,Event
from uuid import uuid4
from twinpulse_core.environment_alignment import StructuralMatcher,body_points,finite_pose,reference_check,wall_references
from twinpulse_core.revisions import canonical_sha256
from twinpulse_core.room_localization import compose
from twinpulse_provider import CancellationToken
from .library_asset_store import atomic_json
from .command_broker import BrokerError

class AlignmentReview:
    def __init__(self,workspace,fleet):
        self.workspace=workspace;self.fleet=fleet;self.lock=RLock();self.job=None;self.visible=False
        self.thread=None;self.stop=Event();self.token=CancellationToken();self.result=None;self.packet=None
        self.root=workspace.root/'alignment-reviews';self.saved_path=self.root/'last-review.json'
        self.metadata_key=None;self.metadata=None;self.review_digest=None;self.owner=None;self.saved_result=None;self.revoked=False
        self.context_hash_key=None;self.context_hash=None
        if self.saved_path.is_file() and not self.saved_path.is_symlink() and self.saved_path.stat().st_size<2*1024*1024:
            try:
                saved=json.loads(self.saved_path.read_bytes())
                if saved.get('schema')=='environment-alignment-review-1.0' and saved.get('physical_authority') is False:
                    self.result=saved;self.saved_result=deepcopy(saved);self.review_digest=canonical_sha256(saved)
                    identity=saved['job_id']
                    if not re.fullmatch('[a-f0-9]{32}',identity):raise ValueError('ALIGNMENT_SAVED_JOB_ID')
                    self.revoked=(self.root/identity/'revoked.json').exists()
                    self.job=dict(status='CANCELLED' if self.revoked else 'SAVED',job_id=identity,reason='Saved review only; live tracking is not restored.')
            except (OSError,ValueError,KeyError):pass

    def context(self):
        w=self.workspace.workflow
        with w._lock:
            source=w._application.site_draft
            env,revision=self.workspace._current_review(source)
            if self.context_hash_key!=(revision,env['source_sha256']):
                self.context_hash=canonical_sha256(env);self.context_hash_key=(revision,env['source_sha256'])
            return env,dict(project_id=w._broker.project_id,scene_revision=revision,source_sha256=env['source_sha256'],environment_sha256=self.context_hash)

    def snapshot(self):
        try:
            env,context=self.context();key=context['environment_sha256']
            if key!=self.metadata_key:self.metadata=wall_references(env);self.metadata_key=key
            current=self.result is None or all(self.result['context'].get(k)==v for k,v in context.items())
        except BrokerError:context=None;current=False
        with self.lock:
            if not current:self.visible=False;self.packet=None
            return dict(schema='environment-alignment-state-1.0',context=context,references=deepcopy(self.metadata or []),
                job=deepcopy(self.job),review=deepcopy(self.result),review_digest=self.review_digest,visible=self.visible and current,
                physical_authority=False,world_registration_verified=False)

    def action(self,body,owner):
        if not isinstance(body,dict) or not isinstance(body.get('request_id'),str) or not re.fullmatch('[A-Za-z0-9_-]{1,100}',body['request_id']):raise ValueError('ALIGNMENT_REQUEST')
        action=body.get('action')
        if action in {'hide','cancel'}:
            if set(body)!={'action','request_id'}:raise ValueError('ALIGNMENT_ACTION_SHAPE')
            with self.lock:
                self.visible=False
                if action=='cancel':
                    # Revoke before releasing the publish lock. Late work must
                    # not recreate a packet or become showable after Cancel.
                    self.revoked=True;self.stop.set();self.token.cancel();self.packet=None
                    if self.job:
                        self.job.update(status='CANCELLED',reason='Explicitly cancelled.')
                        folder=self.root/self.job['job_id']
                        if folder.is_dir():atomic_json(folder/'revoked.json',dict(job_id=self.job['job_id'],revoked=True))
            return self.snapshot()
        if action=='show':
            if set(body)!={'action','request_id','review_digest'}:raise ValueError('ALIGNMENT_ACTION_SHAPE')
            _,context=self.context()
            with self.lock:
                if (self.revoked or self.job and self.job['status'] in {'HELD','CANCELLED'} or not self.result
                        or body['review_digest']!=self.review_digest or self.result['context']!=context
                        or self.result['status']!='GEOMETRIC_REVIEW'):raise BrokerError('alignment_review_not_current','Check a current scan before showing an aligned review.',status=409)
                if self.packet is None:
                    saved=self.saved_result
                    if not saved or saved['context']!=context:raise ValueError('ALIGNMENT_SAVED_RESULT_REQUIRED')
                    identity=saved['job_id']
                    if not re.fullmatch('[a-f0-9]{32}',identity):raise ValueError('ALIGNMENT_SAVED_JOB_ID')
                    path=self.root/identity/'input.json'
                    if path.is_symlink() or path.stat().st_size>2*1024*1024:raise ValueError('ALIGNMENT_SAVED_INPUT_BOUND')
                    inputs=json.loads(path.read_bytes())
                    if canonical_sha256(inputs)!=saved['input_bundle_sha256']:raise ValueError('ALIGNMENT_SAVED_INPUT_CHANGED')
                    self.make_packet(saved,body_points(inputs['frames'][-1]['points'],inputs['extrinsic'],inputs['angle_sign']),
                        inputs['extrinsic'],saved['sensor_height_m'],inputs['frames'][-1],source='SAVED')
                self.visible=True
            return self.snapshot()
        required={'action','request_id','expected_scene_revision','source','robot_id','operation_id','start_sequence','initial_pose','reference_id','reference_length_m','reference_basis','height_m'}
        if action!='check' or set(body)!=required:raise ValueError('ALIGNMENT_ACTION_SHAPE')
        env,context=self.context()
        if body['expected_scene_revision']!=context['scene_revision']:raise ValueError('ALIGNMENT_SCENE_CHANGED')
        if body['source'] not in {'CURRENT','SAVED'}:raise ValueError('ALIGNMENT_SOURCE')
        if type(body['height_m']) not in (int,float) or not math.isfinite(body['height_m']) or not .05<=body['height_m']<=1.:raise ValueError('ALIGNMENT_SENSOR_HEIGHT')
        seed=finite_pose(body['initial_pose']);reference=reference_check(env,body['reference_id'],body['reference_length_m'],body['reference_basis'])
        if body['source']=='CURRENT':
            row=self.row(body['robot_id'],owner)
            if row['kind']!='sim' and body['reference_basis']=='SIM_ONLY':raise ValueError('ALIGNMENT_PHYSICAL_REFERENCE_REQUIRED')
            if row['control_state'] not in {'PAUSED','READY'}:raise ValueError('ALIGNMENT_STOP_FIRST')
        else:
            physical=self.fleet.physical
            if physical is None:raise ValueError('ALIGNMENT_ARCHIVE_UNAVAILABLE')
            physical._history_owner(owner,context['project_id'])
            if not re.fullmatch('[a-f0-9]{32}',str(body['operation_id'])) or type(body['start_sequence']) is not int or body['start_sequence']<0:raise ValueError('ALIGNMENT_ARCHIVE_IDENTITY')
            if body['reference_basis']=='SIM_ONLY':raise ValueError('ALIGNMENT_PHYSICAL_REFERENCE_REQUIRED')
            if self.fleet.devices and self.fleet.devices.physical_runtime_active():raise ValueError('ALIGNMENT_ARCHIVE_REQUIRES_IDLE_ROBOTS')
        with self.lock:
            if self.thread and self.thread.is_alive():raise BrokerError('alignment_review_busy','Cancel the current check before starting another.',status=409)
            self.stop=Event();self.token=CancellationToken();self.visible=False;self.packet=None;self.owner=owner;self.review_digest=None;self.revoked=False;self.saved_result=None
            self.job=dict(job_id=uuid4().hex,status='CHECKING',reason=None);self.result=None
            self.thread=Thread(target=self.run,args=(deepcopy(body),env,context,seed,reference,owner,self.job['job_id']),name='TwinPulseAlignmentReview',daemon=True);self.thread.start()
        return self.snapshot()

    def row(self,identity,owner):
        row=next((r for r in self.fleet.snapshot()['robots'] if r['robot_id']==identity),None)
        if not row or row['connection_state']!='CONNECTED' or row['lidar_state']!='STREAMING' or not row.get('scan'):raise ValueError('ALIGNMENT_FRESH_SCAN_REQUIRED')
        if row['kind']=='physical':
            age=(row.get('scan_receipt') or {}).get('age_ms')
            if type(age) not in (int,float) or not 0<=age<700:raise ValueError('ALIGNMENT_SCAN_STALE')
        elif not 0<=time.time()*1000-row['scan']['captured_at_ms']<700:raise ValueError('ALIGNMENT_SCAN_STALE')
        return row

    def current_frame(self,identity,owner):
        row=self.row(identity,owner);scan=row['scan']
        if row['kind']=='sim':
            if scan.get('point_frame')!='sensor_local' or scan.get('source')!='isaac_usd_surface_rays':raise ValueError('ALIGNMENT_SIM_FRAME')
            tf=[-.032,0.,0.];sign=1;basis='BUILTIN_BURGER_NOMINAL_SCAN_FRAME_NOT_AS_BUILT'
        else:
            config=(row.get('field') or {}).get('config',{})
            if not {'sensor_x_m','sensor_y_m','sensor_yaw_rad','angle_sign'}<=set(config):raise ValueError('ALIGNMENT_TF_REQUIRED')
            tf=[config[k] for k in ('sensor_x_m','sensor_y_m','sensor_yaw_rad')];sign=config['angle_sign'];basis='CURRENT_RECORDED_FIELD_CONFIG_NOT_AS_BUILT'
        raw=scan['points'];stamp=scan.get('captured_at_ms');identity=[row['robot_id'],row['operation_id'],row['connection_epoch']]
        if row['kind']=='physical':stamp=time.time()*1000-row['scan_receipt']['age_ms']
        # A fleet report sequence can advance without a NEW SIM acquisition.
        # Keep that distinction: duplicate capture time is not held-out data.
        acquisition=scan.get('captured_at_ms') if row['kind']=='sim' else scan.get('frame_sequence')
        frame=dict(identity=[scan.get('stream_id'),acquisition,scan.get('raw_sha256') or canonical_sha256(raw)],
            points=raw,source_owner=identity,stamp=stamp,control_state=row['control_state'],scan_source=scan['source'],
            height_m=scan.get('height_m'),reported_frame_sequence=scan.get('frame_sequence'),
            timestamp_basis='PC_RECEIPT_AGE_NOT_SENSOR_PRODUCER' if row['kind']=='physical' else 'SIM_SENSOR_CAPTURE')
        return frame,tf,sign,basis

    def run(self,body,env,context,seed,reference,owner,job_id):
        try:
            if any(p.is_symlink() or getattr(p,'is_junction',lambda:False)() for p in (self.root,*self.root.parents)):raise ValueError('ALIGNMENT_REVIEW_PATH')
            self.root.mkdir(parents=True,exist_ok=True);folder=self.root/job_id;folder.mkdir()
            matcher=StructuralMatcher(env,body['height_m'],[r['id'] for r in wall_references(env)])
            if body['source']=='SAVED':
                from .runtime_paths import resource_root,script_command
                from .library_process import run_finite
                command=script_command(resource_root(),'alignment-archive')+['--state-root',str(self.fleet.physical.state_root),'--operation',body['operation_id'],
                    '--project',context['project_id'],'--output',str(folder/'archive.json'),'--start-sequence',str(body['start_sequence'])]
                run_finite(command,folder,self.token,timeout=70,external=False)
                archive=json.loads((folder/'archive.json').read_bytes());frames=archive['frames'];tf=archive['extrinsic'];sign=archive['angle_sign'];basis=archive['tf_basis']
                provenance={k:archive[k] for k in ('recorded_twin_context','receipt_sha256','segments','selection','start_sequence','receipt_complete')}
            else:
                frames=[];deadline=time.monotonic()+12.;provenance={};first_tf=None
                while len(frames)<3:
                    if self.stop.is_set():raise ValueError('ALIGNMENT_CANCELLED')
                    frame,tf,sign,basis=self.current_frame(body['robot_id'],owner)
                    if frame.get('height_m') is not None and abs(frame['height_m']-body['height_m'])>.001:raise ValueError('ALIGNMENT_SENSOR_HEIGHT_MISMATCH')
                    if frame['control_state'] not in {'READY','PAUSED'}:raise ValueError('ALIGNMENT_INITIALIZATION_MOVED')
                    if frames and frame['source_owner']!=frames[0]['source_owner']:raise ValueError('ALIGNMENT_CONNECTION_CHANGED')
                    if first_tf is None:first_tf=(deepcopy(tf),sign,basis)
                    elif first_tf!=(tf,sign,basis):raise ValueError('ALIGNMENT_INITIAL_TF_CHANGED')
                    if not frames or frame['identity']!=frames[-1]['identity']:frames.append(frame)
                    if time.monotonic()>deadline:raise ValueError('ALIGNMENT_THREE_FRAMES_REQUIRED')
                    self.stop.wait(.1)
                provenance=dict(source_owner=frames[0]['source_owner'])
            inputs=dict(frames=frames,extrinsic=tf,angle_sign=sign)
            atomic_json(folder/'input.json',inputs)
            points=[body_points(f['points'],tf,sign) for f in frames]
            selections=[matcher.structural_indices(f['points'],seed,tf,sign) for f in frames]
            match=matcher.fit(points[0],seed,raw_sensor_points=frames[0]['points'],extrinsic=tf,angle_sign=sign,indices=selections[0]['indices'])
            temporal=[matcher.validation(p,selection['indices'],match['body_pose'],frame['points'],tf,sign)
                for p,selection,frame in zip(points[1:],selections[1:],frames[1:]) if selection['indices']]
            if len(temporal)!=2:raise ValueError('ALIGNMENT_TEMPORAL_WALL_COVERAGE')
            good=match['status']=='GEOMETRIC_REVIEW' and all(matcher.passes(s) for s in temporal) and reference['status']=='REFERENCE_CONSISTENT'
            result=dict(schema='environment-alignment-review-1.0',job_id=job_id,context=context,status='GEOMETRIC_REVIEW' if good else 'HELD',
                source=body['source'],sensor_kind='SIM' if basis.startswith('BUILTIN_') else 'PHYSICAL',reference=reference,match=match,temporal_validation=temporal,pre_fit_selections=selections,
                all_returns_diagnostic=matcher.score(points[0],list(range(len(points[0]))),match['body_pose']),
                sensor_height_m=body['height_m'],sensor_height_basis='EXPLICIT_NOMINAL_REVIEW_HEIGHT_NOT_AS_BUILT',
                extrinsic=tf,angle_sign=sign,tf_basis=basis,tf_sha256=canonical_sha256(dict(extrinsic=tf,angle_sign=sign,basis=basis)),
                input_frames=[{k:v for k,v in f.items() if k!='points'} for f in frames],input_points_sha256=canonical_sha256([f['points'] for f in frames]),
                provenance=provenance,input_bundle_sha256=canonical_sha256(inputs),physical_authority=False,world_registration_verified=False,geometry_changed=False)
            atomic_json(folder/'result.json',result)
            self.publish(result,points[-1],tf,body['height_m'],context,frame=frames[-1],persist=True)
            if body['source']=='CURRENT' and good:
                previous=frames[-1];pose=match['body_pose'];source_owner=previous['source_owner']
                while not self.stop.wait(.15):
                    frame,new_tf,new_sign,new_basis=self.current_frame(body['robot_id'],owner)
                    if frame['source_owner']!=source_owner or new_tf!=tf or new_sign!=sign or new_basis!=basis:raise ValueError('ALIGNMENT_CONNECTION_OR_TF_CHANGED')
                    if frame.get('height_m') is not None and abs(frame['height_m']-body['height_m'])>.001:raise ValueError('ALIGNMENT_SENSOR_HEIGHT_MISMATCH')
                    if frame['identity']==previous['identity']:continue
                    previous=frame;points=body_points(frame['points'],tf,sign)
                    selection=matcher.structural_indices(frame['points'],pose,tf,sign)
                    match=matcher.fit(points,pose,raw_sensor_points=frame['points'],extrinsic=tf,angle_sign=sign,initial=False,indices=selection['indices'])
                    if match['status']=='GEOMETRIC_REVIEW':pose=match['body_pose']
                    result=deepcopy(result);result.update(status=match['status'],match=match,latest_selection=selection,latest_frame={k:v for k,v in frame.items() if k!='points'})
                    self.publish(result,points,tf,body['height_m'],context,frame=frame,persist=False)
        except Exception as error:
            with self.lock:
                self.visible=False;self.packet=None
                if self.job and self.job['job_id']==job_id:self.job.update(status='CANCELLED' if self.stop.is_set() else 'HELD',reason=str(error)[:300])

    def publish(self,result,points,tf,height,context,*,frame,persist):
        _,current=self.context()
        if self.stop.is_set() or current!=context:raise ValueError('ALIGNMENT_CONTEXT_CHANGED')
        if result['source']=='SAVED' and self.fleet.devices and self.fleet.devices.physical_runtime_active():raise ValueError('ALIGNMENT_ARCHIVE_REQUIRES_IDLE_ROBOTS')
        with self.lock:
            if self.stop.is_set() or self.revoked:raise ValueError('ALIGNMENT_CANCELLED')
            if persist:
                atomic_json(self.saved_path,result);self.review_digest=canonical_sha256(result);self.saved_result=deepcopy(result)
            self.make_packet(result,points,tf,height,frame)
            self.result=result;self.job.update(status='TRACKING' if result['source']=='CURRENT' and result['status']=='GEOMETRIC_REVIEW' else result['status'],reason=None)

    def make_packet(self,result,points,tf,height,frame,*,source=None):
        pose=result['match']['body_pose'];self.packet=dict(review_id=result['job_id'],source=source or result['source'],body_pose=pose,
            sensor_pose=compose(pose,tf),height_m=height,points_body=points[::max(1,len(points)//180)][:180],
            scene_revision=result['context']['scene_revision'],status=result['status'],physical_authority=False,
            original_captured_at_ms=frame.get('stamp'),source_owner=frame.get('source_owner'))

    def overlay(self):
        state=self.workspace.workflow._broker.supervisor_state()
        snap=state.get('snapshot') or {};revision=snap.get('applied_revision')
        with self.lock:packet=deepcopy(self.packet) if self.visible else None
        if (not state['engine_connected'] or not packet or packet['status']!='GEOMETRIC_REVIEW'
                or revision!=packet['scene_revision'] or snap.get('project_id')!=self.workspace.workflow._broker.project_id):return None
        if packet['source']=='CURRENT':
            try:
                owner=packet['source_owner'];row=self.row(owner[0],self.owner)
                if [row['robot_id'],row['operation_id'],row['connection_epoch']]!=owner:return None
                # Original source age, never the time of this metadata read.
                stamp=packet['original_captured_at_ms']
                if type(stamp) not in (int,float) or not 0<=time.time()*1000-stamp<1000:return None
            except (ValueError,KeyError,TypeError,BrokerError):return None
        return packet

    def close(self):
        with self.lock:self.stop.set();self.token.cancel();self.visible=False;self.packet=None
        if self.thread:self.thread.join(timeout=4)
        if self.thread and self.thread.is_alive():raise RuntimeError('ALIGNMENT_REVIEW_JOIN_UNCONFIRMED')
