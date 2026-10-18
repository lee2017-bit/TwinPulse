# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""One explicit offline pair, existing automatic mission workers, isolated ledgers.

No physical factory is accepted. The default private synthetic world comes from
the photo approximation and is explicitly not validation of the user's room.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import threading
import time
from uuid import uuid4
from twinpulse_core.automatic_mission_comparison import checked_conditions,compare_automatic_missions
from twinpulse_core.automatic_photo_alignment import structural_section
from twinpulse_core.revisions import canonical_sha256
from .automatic_demo_service import AutomaticDemoService
from .automatic_mission_service import AutomaticMissionService
from .automatic_photo_store import load_automatic_room
from .command_broker import BrokerError
from .offline_mission_adapter import OfflineMissionAdapter


class AutomaticComparisonService:
    def __init__(self,automatic,*,world_loader=None):
        self.automatic=automatic;self.world_loader=world_loader
        self.lock=threading.RLock();self.worker=None;self.job=None;self.closed=False;self.active=None
        self.cancelled=threading.Event()

    def snapshot(self,owner):
        with self.lock:
            if self.job and self.job['owner']!=owner:raise BrokerError('comparison_not_owned','Comparison belongs to another session',status=409)
            return {'job':deepcopy({k:v for k,v in (self.job or {}).items() if k!='owner'}) or None,
                    'scope':'OUTPUT_REACTIVE_SYNTHETIC_NOT_ROBOT','motion_authorized':False}

    def start(self,owner,start,goal):
        with self.lock:
            if self.closed:raise BrokerError('comparison_closed','Comparison service is closed',status=409)
            if self.worker and self.worker.is_alive():raise BrokerError('comparison_busy','A comparison is running',status=409)
            if self.automatic.root is None:raise BrokerError('comparison_unavailable','Project storage is unavailable',status=409)
            if self.automatic.worker and self.automatic.worker.is_alive():raise BrokerError('automatic_busy','Wait for mapping to finish',status=409)
            try:
                room=load_automatic_room(self.automatic.root,self.automatic.project_id)
                effective=self.automatic.photo_store.current(room);geometry=self.automatic.geometry_loader()
                height=geometry['base_footprint_to_base_link_xyz_m'][2]+geometry['base_link_to_scan_xyz_m'][2]
                section=structural_section(effective['objects'],height)
                world=(self.world_loader(room,effective) if self.world_loader else
                       {'segments':[[w['a'],w['b']] for w in section['walls']]})
                body={'schema':'automatic-mission-conditions-1.0','project_id':room['project_id'],
                    'room_revision':effective['effective_revision'],'world_revision':canonical_sha256(world),
                    'start':start,'goal':goal,'seed':0,'dynamics':'static_kinematic_raycast_v1',
                    'geometry_revision':canonical_sha256(geometry),'duration_s':45.,'footprint_radius_m':.18,'collision_penalty':100}
                conditions=checked_conditions({**body,'revision':canonical_sha256(body)})
                if not 3<=len(world['segments'])<=64:raise ValueError('COMPARISON_WORLD_BUDGET')
                if any(len(line)!=2 or any(len(p)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>12 for v in p) for p in line) for line in world['segments']):
                    raise ValueError('COMPARISON_WORLD_GEOMETRY')
            except (ValueError,KeyError,TypeError,OSError) as exc:
                cause=str(exc);cause=cause if re.fullmatch('[A-Z0-9_]{1,120}',cause) else 'COMPARISON_INPUT_REJECTED'
                raise BrokerError('comparison_input_rejected',cause,status=409) from exc
            identity=uuid4().hex;self.cancelled.clear()
            self.job={'owner':owner,'job_id':identity,'state':'PREPARING','arm':None,'result':None,'error':None,'conditions':conditions}
            self.worker=threading.Thread(target=self._run,args=(room,effective,geometry,world),name='tp-offline-comparison',daemon=True)
            self.worker.start();return self.snapshot(owner)

    def stop(self,owner,identity):
        with self.lock:
            self.snapshot(owner)
            if not self.job or self.job['job_id']!=identity:raise BrokerError('comparison_not_owned','Exact owned comparison required',status=409)
            if not self.worker or not self.worker.is_alive():return self.snapshot(owner)
            if self.job['state']=='SAVING':return self.snapshot(owner)
            self.cancelled.set();self.job['state']='STOPPING'
            if self.active and self.active.job:self.active.stop('comparison',self.active.job['job_id'],True)
            return self.snapshot(owner)

    def _run(self,room,effective,geometry,world):
        out=self.automatic.root/'artifacts/automatic-comparison'/self.job['job_id'];arms={};sources={}
        try:
            if out.resolve()!=out or any(p.is_symlink() for p in out.parents):raise ValueError('COMPARISON_OUTPUT_PATH_UNSAFE')
            out.mkdir(parents=True,exist_ok=False)
            # Only declared local project data and current photo ledger, never credentials.
            base=self.automatic.root/'projects'/self.automatic.project_id
            ledger=self.automatic.photo_store.folder
            paths=[]
            for folder in (base,ledger):
                if folder.exists():
                    for p in folder.rglob('*'):
                        if p.is_symlink():raise ValueError('COMPARISON_SOURCE_SYMLINK')
                        if p.is_file() and (p.suffix.lower() in {'.json','.png','.jpg','.jpeg'}):paths.append(p)
            if len(paths)>256 or sum(p.stat().st_size for p in paths)>32*1024*1024:raise ValueError('COMPARISON_SOURCE_BUDGET')
            sources={str(p.relative_to(self.automatic.root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
            # Clone both before either executes; no result-derived world/reset injection.
            for name in ('baseline','corrected'):
                branch=out/name;branch.mkdir()
                for p in paths:
                    target=branch/p.relative_to(self.automatic.root);target.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copyfile(p,target)
            for name,policy in (('baseline','align_only'),('corrected','correct_walls')):
                if self.cancelled.is_set():break
                with self.lock:self.job.update(state='RUNNING',arm=name)
                branch=out/name;adapters=[]
                automatic=AutomaticDemoService(branch,self.automatic.project_id,geometry_loader=lambda:deepcopy(geometry))
                def factory(prior,r,e,goal):
                    adapter=OfflineMissionAdapter(prior,r,e,goal,segments=world['segments'],
                        start=self.job['conditions']['start'],conditions=self.job['conditions'])
                    adapters.append(adapter);return adapter
                factory.supports_local_correction=True
                mission=AutomaticMissionService(automatic,adapter_factory=factory)
                try:
                    with self.lock:self.active=mission
                    goal={'mode':'SURVEY_THEN_NAVIGATE','xy':self.job['conditions']['goal'],
                          'room_revision':self.job['conditions']['room_revision'],'duration_s':45.}
                    mission.start('comparison',None,goal,policy)
                    end=time.monotonic()+100
                    while mission.worker.is_alive() and time.monotonic()<end:
                        if self.cancelled.is_set() and mission.stop_action is None:mission.stop('comparison',mission.job['job_id'],True)
                        mission.worker.join(.1)
                    if mission.worker.is_alive():raise ValueError('COMPARISON_ARM_WORKER_TIMEOUT')
                    job=mission.snapshot('comparison')['job'];adapter=adapters[0] if adapters else None
                    path=branch/'artifacts/automatic-mission'/self.automatic.project_id/f"{job['job_id']}.json"
                    report=json.loads(path.read_text());digest=report.pop('revision')
                    if canonical_sha256(report)!=digest:raise ValueError('COMPARISON_MISSION_REPORT_HASH')
                    if not adapter or adapter.velocity!=(0.,0.) or not adapter.halted:raise ValueError('COMPARISON_FINAL_ZERO_UNCONFIRMED')
                    samples=[[20.,*self.job['conditions']['start']],*adapter.samples]
                    arms[name]={'policy':policy,'conditions_revision':self.job['conditions']['revision'],
                        'state':job['state'],'error':job.get('error'),'cleanup_error':job.get('cleanup_error'),
                        'report_revision':digest,'report_path':str(path.relative_to(out)),
                        'distance_m':sum(math.dist(a[1:3],b[1:3]) for a,b in zip(samples,samples[1:])),
                        'source_elapsed_s':adapter.t-20.,'pc_runtime_s':job['elapsed_s'],
                        'goal_error_m':math.dist(adapter.world[:2],goal['xy']),
                        'collision_episodes':adapter.collision_episodes,'collision_samples':adapter.collision_samples,
                        'trajectory':samples[::max(1,math.ceil(len(samples)/512))],
                        'geometry_corrected':bool(job.get('photo_correction')),'physical_validation':'NOT_RUN',
                        'provenance':adapter.provenance,'final_output':[0.,0.]}
                    with (out/(name+'-synthetic-raw.json')).open('x',encoding='utf-8') as stream:
                        json.dump({'scope':'OUTPUT_REACTIVE_SYNTHETIC_NOT_ROBOT','observations':adapter.raw,
                            'commands':adapter.sent,'samples':samples},stream,allow_nan=False)
                    arms[name]['raw_path']=name+'-synthetic-raw.json'
                    arms[name]['raw_sha256']=hashlib.sha256((out/arms[name]['raw_path']).read_bytes()).hexdigest()
                finally:
                    mission.close();automatic.close()
                    with self.lock:self.active=None
                # A failed arm is a result, not a reason to suppress the independent reset arm.
            changed=[p for p,h in sources.items() if hashlib.sha256((self.automatic.root/p).read_bytes()).hexdigest()!=h]
            if changed:raise ValueError('COMPARISON_SOURCE_CHANGED')
            current_room=load_automatic_room(self.automatic.root,self.automatic.project_id)
            if current_room!=room or self.automatic.photo_store.current(current_room)!=effective:
                raise ValueError('COMPARISON_SOURCE_CHANGED')
            if self.cancelled.is_set():
                with self.lock:self.job.update(state='CANCELLED',result=None)
            else:
                result=compare_automatic_missions(self.job['conditions'],arms)
                with self.lock:self.job.update(state='SAVING',result=result)
        except Exception as exc:
            reason=str(exc);reason=reason if re.fullmatch('[A-Z0-9_]{1,120}',reason) else 'COMPARISON_PROCESSING_FAILED'
            with self.lock:self.job.update(state='FAILED',error=reason,error_type=type(exc).__name__,error_errno=getattr(exc,'errno',None),result=None)
        finally:
            with self.lock:body=deepcopy({k:v for k,v in self.job.items() if k!='owner'})
            if body['state']=='SAVING':body['state']='COMPLETED'
            body.update(schema='automatic-comparison-session-1.0',arms=arms,source_sha256=sources,
                        motion_authorized=False,physical_validation='NOT_RUN')
            body['revision']=canonical_sha256(body)
            try:
                with (out/'comparison.json').open('x',encoding='utf-8') as stream:json.dump(body,stream,allow_nan=False)
                with self.lock:
                    self.job['report_revision']=body['revision']
                    if self.job['state']=='SAVING':self.job['state']='COMPLETED'
            except OSError as exc:
                with self.lock:
                    self.job.update(state='FAILED',report_error='COMPARISON_REPORT_SAVE_FAILED',report_errno=exc.errno,
                                    report_error_type=type(exc).__name__)
                    if not self.job.get('error'):self.job.update(error='COMPARISON_REPORT_SAVE_FAILED',error_type=type(exc).__name__,error_errno=exc.errno)

    def reopen(self,owner,identity,revision):
        with self.lock:
            self.snapshot(owner)
            if not self.job or self.job['job_id']!=identity or self.job.get('report_revision')!=revision:
                raise BrokerError('comparison_report_not_owned','Exact owned saved comparison required',status=409)
            if self.worker and self.worker.is_alive():raise BrokerError('comparison_busy','Wait for comparison saving',status=409)
            folder=self.automatic.root/'artifacts/automatic-comparison'/identity
            body=json.loads((folder/'comparison.json').read_text());stored=body.pop('revision')
            if stored!=revision or canonical_sha256(body)!=revision:raise ValueError('COMPARISON_REPORT_HASH_CHANGED')
            for arm in body['arms'].values():
                for key in ('raw_path','report_path'):
                    path=folder/arm[key]
                    if path.is_symlink() or not path.resolve().is_relative_to(folder):raise ValueError('COMPARISON_ARTIFACT_PATH')
                if hashlib.sha256((folder/arm['raw_path']).read_bytes()).hexdigest()!=arm['raw_sha256']:
                    raise ValueError('COMPARISON_RAW_HASH_CHANGED')
                mission=json.loads((folder/arm['report_path']).read_text());digest=mission.pop('revision')
                if digest!=arm['report_revision'] or canonical_sha256(mission)!=digest:raise ValueError('COMPARISON_MISSION_REPORT_HASH')
            return {'report':{**body,'revision':stored},'motion_authorized':False,'physical_demo_ready':False}

    def close(self):
        self.closed=True;self.cancelled.set()
        if self.active:self.active.close()
        if self.worker:self.worker.join(2.)
