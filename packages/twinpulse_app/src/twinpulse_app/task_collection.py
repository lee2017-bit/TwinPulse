# SPDX-License-Identifier: Apache-2.0
"""Read-only task observation provenance. No motion, model or repair writes."""
from copy import deepcopy
import hashlib,json,math,re,time
from pathlib import Path
from twinpulse_core.revisions import canonical_sha256
from twinpulse_core.physical_task_observation import checked_observation,wheel_se2
from twinpulse_core.room_localization import compose,inverse


class TaskCollection:
    def __init__(self,root,project_id,physical_root=None):
        self.root=Path(root).resolve();self.project_id=project_id;self.physical_root=Path(physical_root).resolve() if physical_root else None

    def _read(self,path,maximum=2*1024*1024):
        path=Path(path)
        if not path.resolve().is_relative_to(self.root) or any(p.is_symlink() or getattr(p,'is_junction',lambda:False)() for p in (path,*path.parents)):raise ValueError('COLLECTION_PATH_INVALID')
        raw=path.read_bytes()
        if len(raw)>maximum:raise ValueError('COLLECTION_FILE_BOUND')
        return json.loads(raw),hashlib.sha256(raw).hexdigest()

    def task(self,identity):
        if not isinstance(identity,str) or not re.fullmatch('[a-f0-9]{32}',identity):raise ValueError('COLLECTION_TASK_ID')
        job,digest=self._read(self.root/identity/'task.json');value=deepcopy(job);record=value.pop('record_sha256',None)
        if record!=canonical_sha256(value) or job.get('task_id')!=identity or job.get('project_id')!=self.project_id:raise ValueError('COLLECTION_TASK_CHANGED')
        if job.get('state') not in {'COMPLETED','PARTIAL','FAILED','CANCELLED','INTERRUPTED'}:raise ValueError('COLLECTION_TASK_STILL_ACTIVE')
        return job,digest

    def listing(self):
        result=[]
        if not self.root.is_dir():return result
        for folder in sorted(self.root.iterdir(),key=lambda p:p.name):
            if not folder.is_dir() or folder.is_symlink() or not re.fullmatch('[a-f0-9]{32}',folder.name):continue
            try:
                job,digest=self.task(folder.name);count=sum(e.get('kind')=='observation' for e in job.get('events',[]))
                if count:result.append(dict(task_id=folder.name,state=job['state'],reason=job.get('reason'),kind=job['robot_kind'],view_count=count,
                    ended_at_ms=job.get('ended_at_ms'),source_record_sha256=digest,source_captured=bool(job.get('environment_source'))))
            except (OSError,ValueError,KeyError,TypeError):continue
            if len(result)>200:raise ValueError('COLLECTION_LIST_BOUND')
        return sorted(result,key=lambda r:r.get('ended_at_ms') or 0,reverse=True)

    def load(self,identity):
        job,task_sha=self.task(identity);events=[e for e in job.get('events',[]) if e.get('kind')=='observation']
        if not 3<=len(events)<=512:raise ValueError('COLLECTION_THREE_VIEWS_REQUIRED')
        capture=job.get('environment_source')
        if not isinstance(capture,dict) or not {'source_sha256','meters_per_unit','source_up_axis','units_basis','environment_sha256','scene_revision'}<=set(capture):
            raise ValueError('COLLECTION_ENVIRONMENT_SOURCE_MISSING: Capture a new survey with this version.')
        if capture['scene_revision']!=job['scene_binding'][2]:raise ValueError('COLLECTION_CAPTURE_BINDING_CHANGED')
        frames=[];files=[];origin=None;pin=None;packet_shas=set()
        for n,event in enumerate(events,1):
            path=self.root/identity/f'observation-{n:04d}.json';obs,digest=self._read(path);files.append(dict(name=path.name,sha256=digest))
            if any(obs.get(k)!=job.get(k) for k in ('robot_id','operation_id','connection_epoch')):raise ValueError('COLLECTION_OBSERVATION_CONTEXT')
            if obs.get('binding')!=job['scene_binding']:raise ValueError('COLLECTION_SCENE_BINDING')
            if obs.get('body_pose')!=event.get('pose'):raise ValueError('COLLECTION_EVENT_POSE_CHANGED')
            owner=[job[k] for k in ('robot_id','operation_id','connection_epoch')]
            if job['robot_kind']=='physical':
                packet=checked_observation(obs.get('packet'));ctx=packet['context'];cfg=packet['config']
                if [ctx.get(k) for k in ('robot_id','operation_id','connection_epoch')]!=owner or ctx.get('project_id')!=self.project_id:
                    raise ValueError('COLLECTION_PACKET_OWNER')
                if packet['sha256']!=event.get('observation_sha256') or packet['scan']['raw_sha256']!=event.get('scan_sha256'):raise ValueError('COLLECTION_PACKET_CHANGED')
                native=wheel_se2(packet['pose']);tf=[cfg[k] for k in ('sensor_x_m','sensor_y_m','sensor_yaw_rad')]
                if wheel_se2(obs.get('native_pose'))!=native:raise ValueError('COLLECTION_NATIVE_POSE_CHANGED')
                raw=[compose(inverse(tf),[*point,0.])[:2] for point in packet['points_base']]
                identity_scan=[packet['scan'][k] for k in ('stream_id','frame_sequence','raw_sha256')]
                source_pin=(ctx,packet['pose_epoch'],packet['config_sha256'],packet['pose']['frame_id'])
                stamp=packet['scan']['timing']['receipt_end_s'];packet_shas.add(packet['sha256'])
                extras=dict(pose_epoch=packet['pose_epoch'],config_sha256=packet['config_sha256'],packet_sha256=packet['sha256'],
                    original_native_timing=packet['scan']['timing'],original_config=cfg,boot_id=ctx['boot_id'],release_id=ctx['release_id'],
                    points_basis='CANONICAL_NATIVE_BASE_RETURNS_INVERSE_RECORDED_EXTRINSIC',independent_body=False,native_frame_id=packet['pose']['frame_id'])
            elif job['robot_kind']=='sim':
                scan=obs.get('scan') or {};p=obs.get('body_pose') or {}
                if scan.get('source')!='isaac_usd_surface_rays' or scan.get('point_frame')!='sensor_local' or canonical_sha256(scan)!=event.get('scan_sha256'):
                    raise ValueError('COLLECTION_ACTUAL_SIM_SCAN_REQUIRED')
                native=list(p['position_m']);tf=[-.032,0.,0.];raw=scan['points']
                identity_scan=[scan['stream_id'],scan['frame_sequence'],scan['captured_at_ms']];source_pin=tuple(owner)
                stamp=scan['captured_at_ms'];extras=dict(independent_body=False,points_basis='ACTUAL_SIM_SENSOR_LOCAL_RAYS')
            else:raise ValueError('COLLECTION_ROBOT_KIND')
            if event.get('scan_identity')!=identity_scan:raise ValueError('COLLECTION_EVENT_SCAN_CHANGED')
            if origin is None:origin=native;pin=source_pin
            if source_pin!=pin:raise ValueError('COLLECTION_NATIVE_FRAME_OR_CONFIG_CHANGED')
            frames.append(dict(identity=identity_scan,points=raw,native_pose=native,local_pose=compose(inverse(origin),native),extrinsic=tf,
                source_owner=owner,source_sha256=digest,stamp=stamp,source_kind='PHYSICAL' if job['robot_kind']=='physical' else 'SIM',**extras))
        physical=self._verify_physical_packets(job,packet_shas) if job['robot_kind']=='physical' else None
        value=dict(schema='robot-task-collection-1.0',task_id=identity,project_id=self.project_id,robot_id=job['robot_id'],robot_kind=job['robot_kind'],
            original_state=job['state'],original_reason=job.get('reason'),task_record_sha256=task_sha,environment_source=capture,
            scene_binding=job['scene_binding'],observation_files=files,frames=frames,physical_archive=physical,
            physical_authority=False,whole_room_coverage_verified=False)
        value['sha256']=canonical_sha256(value);return value

    def _verify_physical_packets(self,job,expected):
        if self.physical_root is None:raise ValueError('COLLECTION_PHYSICAL_ARCHIVE_UNAVAILABLE')
        folder=self.physical_root/'physical-live'/job['operation_id'];path=folder/'receipt.json'
        if any(p.is_symlink() for p in (folder,path,folder.parent)):raise ValueError('COLLECTION_ARCHIVE_PATH')
        if not path.is_file():raise ValueError('COLLECTION_DISCONNECT_TO_SEAL_RECORDING')
        from .physical_motion_analysis import read_archive
        checked=read_archive(folder,job['operation_id'],self.project_id,time.monotonic()+45.)
        if any(checked['first'].get(k)!=job.get(k) for k in ('robot_id','connection_epoch')):raise ValueError('COLLECTION_ARCHIVE_OWNER')
        if checked['receipt'].get('complete') is not True or checked['receipt'].get('error'):
            raise ValueError('COLLECTION_ARCHIVE_INCOMPLETE_REVIEW_ONLY')
        receipt=json.loads(path.read_bytes());found=set();segments=[]
        if not isinstance(receipt.get('segments'),list) or not 1<=len(receipt['segments'])<=1024:raise ValueError('COLLECTION_ARCHIVE_SEGMENTS')
        total=0
        for part in receipt['segments']:
            if not re.fullmatch('events-[0-9]{5}.jsonl',str(part.get('path'))):raise ValueError('COLLECTION_ARCHIVE_MEMBER')
            member=folder/part['path']
            if member.is_symlink():raise ValueError('COLLECTION_ARCHIVE_MEMBER')
            raw=member.read_bytes();total+=len(raw)
            if total>2*1024**3 or len(raw)!=part['bytes'] or hashlib.sha256(raw).hexdigest()!=part['sha256']:raise ValueError('COLLECTION_ARCHIVE_SHA')
            for line in raw.splitlines():
                if len(line)>256*1024:raise ValueError('COLLECTION_ARCHIVE_LINE_BOUND')
                e=json.loads(line);packet=(e.get('data') or {}).get('task_local_observation')
                if not packet:continue
                if any(e.get(k)!=job.get(k) for k in ('robot_id','operation_id','connection_epoch','project_id')):raise ValueError('COLLECTION_ARCHIVE_CONTEXT')
                if packet.get('sha256') in expected:checked_observation(packet);found.add(packet['sha256'])
            segments.append(deepcopy(part))
        if found!=expected:raise ValueError('COLLECTION_PACKETS_NOT_IN_ORIGINAL_STREAM')
        return dict(receipt_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),complete=receipt.get('complete'),error=receipt.get('error'),
            segments=segments,packets_bound=len(found),source_bytes=total)
