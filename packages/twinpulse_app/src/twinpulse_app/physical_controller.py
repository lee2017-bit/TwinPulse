# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Explicit physical operations with a fixed reviewed SSH command and no auto-connect.

PC cannot certify a physical stop. Robot-local qualification/freshness/lease is
authoritative. Injectable process factory is for isolated tests, not an API option.
"""
import json
import math
import queue
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from copy import deepcopy

from .command_broker import BrokerError
from .robot_evidence_recovery import RobotEvidenceRecovery
from .session_journal import SessionJournal
from .robot_registry import RobotEndpoint
from twinpulse_core.ros_observations import valid_snapshot, valid_scan_preview
from twinpulse_core.mission_contract import scope_document, document_hash, bootstrap_packet
from twinpulse_core.demo_contract import operation_for_action

REMOTE = '/home/twinpulse/.local/share/twinpulse/robot/current/teleop.sh'
MODES = {'prepare','off','lidar','scan','qualify','qualify_scan','control','control_scan','mission','localize'}
ADAPTIVE_SCHEMAS={'observed-mission-scope-'+str(n)+'.0' for n in range(1,8)}
INPUTS = {'forward','backward','left','right','stop','close','watch','qualify','finish_stop','force_stop'}


def valid_mission_decision(value, event_t, *, adaptive=False):
    finite=lambda x:type(x) in (int,float) and math.isfinite(x)
    keys={'allowed','reason','linear_m_s','angular_rad_s','physical_authority','navigation'}
    if (not isinstance(value,dict) or not keys<=set(value)<=keys|{'clear_radius_m','required_radius_m','published_source_age_s'}
            or value['allowed'] is not True or value['physical_authority'] is not False
            or value['reason'] not in (('STOP','CLEAR_IN_SCAN_ENVELOPE','CURRENT_LOCALIZATION_REQUIRED',
                'REVISION_CHANGED_STOP_BEFORE_REPLAN','OBSTACLE_STOP_BEFORE_REPLAN',
                'SURVEY_RETURN_FOR_HELD_OUT_VIEWS','PHOTO_FIT_WHEELS_IDLE','PHOTO_CANDIDATE_RECHECK_CURRENT_SENSOR',
                'SURVEY_RECHECK_CURRENT_SENSOR','SURVEY_COMPLETE_NO_GOAL_COMMAND',
                'ARMED_AWAITING_FRESH_REVIEWED_TICK') if adaptive else ('STOP','CLEAR_IN_SCAN_ENVELOPE'))
            or not all(finite(value[k]) for k in ('linear_m_s','angular_rad_s'))
            or abs(value['linear_m_s'])>.03 or abs(value['angular_rad_s'])>.2):return False
    moving=bool(value['linear_m_s'] or value['angular_rad_s'])
    if moving!=(value['reason']=='CLEAR_IN_SCAN_ENVELOPE'):return False
    if moving and (not finite(value.get('published_source_age_s')) or not 0<=value['published_source_age_s']<.25):return False
    if not moving and 'published_source_age_s' in value:return False
    if moving and (not {'clear_radius_m','required_radius_m'}<=set(value)
                   or not all(finite(value[k]) for k in ('clear_radius_m','required_radius_m'))
                   or value['clear_radius_m']<=value['required_radius_m']):return False
    for key in ('clear_radius_m','required_radius_m'):
        if key in value and (not finite(value[key]) or not 0<=value[key]<=30):return False
    nav=value['navigation']
    if (not isinstance(nav,dict) or set(nav)!={'pose_xy_yaw','pose_sample_s','scan_sample_s',
            'odom_stamp_ns','scan_stamp_ns','evidence_sha256','clear_radius_m','alignment_verified'}
            or nav['alignment_verified'] is not False):return False
    if (type(nav['pose_xy_yaw']) is not list or len(nav['pose_xy_yaw'])!=3
            or any(not finite(x) or abs(x)>1002 for x in nav['pose_xy_yaw'])
            or not all(finite(nav[k]) and 0<=nav[k]<=event_t for k in ('pose_sample_s','scan_sample_s'))
            or not all(type(nav[k]) is int and 0<nav[k]<2**63 for k in ('odom_stamp_ns','scan_stamp_ns'))
            or not finite(nav['clear_radius_m']) or not 0<=nav['clear_radius_m']<=30
            or not isinstance(nav['evidence_sha256'],str)
            or not re.fullmatch('[a-f0-9]{64}',nav['evidence_sha256'])):return False
    return True


def valid_event(event, *, adaptive=False):
    """Strict bounded evidence shape; remote text cannot introduce log fields."""
    if not isinstance(event,dict) or set(event)!={'schema','robot_session_id','event_index','clock_domain','t','kind','data'}:
        return False
    finite=lambda x:type(x) in (int,float) and math.isfinite(x)
    if (event['schema'] not in {'robot-session-1.0','robot-session-1.1'} or event['clock_domain']!='robot_monotonic'
            or not isinstance(event['robot_session_id'],str) or not re.fullmatch('[a-z0-9-]{1,80}',event['robot_session_id'])
            or type(event['event_index']) is not int or not 1<=event['event_index']<=(131072 if event['schema']=='robot-session-1.1' else 4096)
            or not finite(event['t']) or event['t']<0):return False
    required={'session_started':{'mode','boot_id','release_id'},'accepted':{'sequence','action','source_age_s'},
              'armed':{'sequence'},'published':{'sequence','action','linear_m_s','angular_rad_s','source_age_s'},
              'release_requested':{'sequence'},'close_requested':{'sequence'},'idle_confirmed':{'sequence'},
              'stop_requested':{'sequence','action'},
              'motion_paused':{'reason','motion_generation'},
              'observation':{'sample','guard'},'navigation':{'snapshot'},'scan_preview':{'scan'},'scan_display_fault':{'reason'},
              'mission_started':{'mission_id','request_sha256'},'mission_finished':{'mission_id','status'},
              'mission_decision':{'tick','mission_id','status','decision'}}
    if adaptive and event['kind']=='cold_start_diagnostics':
        data=event['data']
        keys={'stage','view_count','map_revision','alignment_status','alignment_revision','reason'}
        if not isinstance(data,dict) or set(data) not in (keys,keys|{'error_stage','error_type'}):return False
        if 'error_stage' in data:
            if data['error_stage'] not in (None,'PHOTO_ALIGNMENT'):return False
            if (data['error_type'] is not None and (not isinstance(data['error_type'],str)
                    or not re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,79}',data['error_type']))):return False
            if (data['error_stage'] is None)!=(data['error_type'] is None):return False
        return (data['stage'] in {'OUTBOUND','RETURN','ALIGN','NAVIGATE','VERIFY_SURVEY','SURVEY_COMPLETE'} and type(data['view_count']) is int
            and 0<=data['view_count']<=128
            and all(v is None or isinstance(v,str) and re.fullmatch('[a-f0-9]{64}',v) for v in (data['map_revision'],data['alignment_revision']))
            and all(isinstance(data[k],str) and re.fullmatch('[A-Z0-9_]{1,120}',data[k]) for k in ('alignment_status','reason')))
    if adaptive and event['kind']=='cold_start_view':
        data=event['data']
        if not isinstance(data,dict) or set(data)!={'sequence','stamp_ns','pose','points','origins'}:return False
        def points(rows,size,limit):
            return isinstance(rows,list) and len(rows)<=limit and all(isinstance(p,list) and len(p)==size and all(finite(x) and abs(x)<=20 for x in p) for p in rows)
        return (type(data['sequence']) is int and 0<data['sequence']<2**31
            and type(data['stamp_ns']) is int and 0<data['stamp_ns']<2**63
            and points([data['pose']],3,1) and points(data['points'],2,160) and points(data['origins'],2,160)
            and 24<=len(data['points'])==len(data['origins'])<=160)
    if not isinstance(event['kind'],str):return False
    data=event['data'];keys=required.get(event['kind'])
    if keys is None or not isinstance(data,dict) or set(data)!=keys:return False
    if event['kind']=='scan_display_fault':
        return isinstance(data['reason'],str) and data['reason'] in {'NONE','NOT_RECEIVED','STAMP_FORMAT','SOURCE_TIME','RAY_COUNT','ANGLE_ENDPOINT','DISPLAY_METADATA','MESSAGE_SHAPE'}
    if event['kind']=='mission_decision' and data['status'] not in ('RUNNING','ARRIVED'):return False
    if event['kind']=='mission_finished' and data['status'] not in ('MISSION_ARRIVED','MISSION_CANCELLED','COMMAND_SEGMENT_STOPPED','FORCE_STOPPED','FAILED'):return False
    for key,value in data.items():
        if key=='decision':
            if not valid_mission_decision(value,event['t'],adaptive=adaptive):return False
        elif key=='tick':
            if type(value) is not int or not 1<=value<=1000:return False
        elif key in {'mission_id','request_sha256'}:
            if not isinstance(value,str) or not re.fullmatch('[a-f0-9]{'+('32' if key=='mission_id' else '64')+'}',value):return False
        elif key=='scan':
            if not valid_scan_preview(value) or value['receipt_s']>event['t']:return False
        elif key=='snapshot':
            if not valid_snapshot(value) or value['t']>event['t']:return False
        elif key=='sample':
            if not isinstance(value,dict) or not {'t','encoders','torque','source_age_s'}<=set(value)<= {'t','encoders','torque','source_age_s','voltage_v'}:return False
            if not finite(value['t']) or not finite(value['source_age_s']) or type(value['torque']) is not bool:return False
            if not isinstance(value['encoders'],list) or len(value['encoders'])!=2 or any(type(n) is not int or not -(2**31)<=n<2**31 for n in value['encoders']):return False
            if value.get('voltage_v') is not None and not finite(value['voltage_v']):return False
        elif key=='sequence':
            if type(value) is not int or not 1<=value<2147483647:return False
        elif key=='motion_generation':
            if type(value) is not int or not 0<=value<2147483647:return False
        elif key in {'source_age_s','linear_m_s','angular_rad_s'}:
            if not finite(value):return False
        elif not isinstance(value,str) or not re.fullmatch('[A-Za-z0-9_.-]{1,80}',value):return False
    return True


def trial_summary(report, job_id):
    # Display-only historical evidence. Never read by robot authorization logic.
    return {'job_id':job_id, 'historical':True,
            **{k:report[k] for k in ('boot_id','release_id','status','stop_assessment',
                'stop_diagnostics','cleanup_confirmed','cleanup_stage','cleanup_error') if k in report}}


def rejected_consumed_trial(report):
    # A pre-trial rejection is not a new measurement. Preserve the actual trial
    # separately, while the rejected operation remains FAILED in its own report.
    return (report.get('reason') == 'TRIAL_ALREADY_CONSUMED_REVIEW_REQUIRED'
            and report.get('cleanup_confirmed') is True
            and not report.get('stop_assessment') and not report.get('stop_diagnostics'))


def worker_command(root, mode, *, endpoint:RobotEndpoint|None=None, robot_binding:dict|None=None):
    if mode not in MODES: raise ValueError('Unsupported operation')
    from .robot_adapters import instance_binding,legacy_binding,require_adapter
    if endpoint is not None and not isinstance(endpoint,RobotEndpoint):raise ValueError('ROBOT_ENDPOINT_INVALID')
    if robot_binding is None and endpoint is not None:
        from dataclasses import asdict
        robot_binding=instance_binding({'id':'0'*32,'adapter_id':'turtlebot3_burger_v1','endpoint':asdict(endpoint.checked())})
    selected = require_adapter(legacy_binding() if robot_binding is None else robot_binding, operation='control')
    if endpoint is not None:
        if not isinstance(endpoint, RobotEndpoint) or endpoint.checked()!=selected:
            raise ValueError('ROBOT_COMMAND_BINDING_CHANGED')
    if mode == 'prepare':
        from .runtime_paths import script_command
        return script_command(root, 'robot-prepare') + [
                '--disable-torque','--operator-confirmed-flat-clear-floor',
                '--host',selected.host,'--user',selected.user,'--port',str(selected.port),
                '--domain-id',str(selected.ros_domain_id)]
    ssh = shutil.which('ssh.exe' if os.name=='nt' else 'ssh')
    key = Path.home()/'.ssh/twinpulse-burger/id_ed25519_automation'
    known = Path.home()/'.ssh/known_hosts'
    if not ssh or not key.is_file() or not known.is_file(): raise ValueError('PC_SSH_PREREQUISITE_MISSING')
    return [ssh,'-T','-i',str(key),'-o','IdentitiesOnly=yes','-o','BatchMode=yes',
            '-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(known),
            '-o','ConnectTimeout=5','-o','ServerAliveInterval=2','-o','ServerAliveCountMax=2',
            '-o','ForwardAgent=no','-o','ClearAllForwardings=yes','-o','PermitLocalCommand=no',
            '-o','ProxyCommand=none','-o','ProxyJump=none',
            '-p',str(selected.port),selected.user+'@'+selected.host,'exec bash '+REMOTE+' '+mode]


class PhysicalController:
    def __init__(self, root, *, factory=subprocess.Popen, command=worker_command,
                 clock=time.monotonic, wall=lambda:time.time()*1000, mission_admission=None,
                 evidence_exporter=None, archive_root=None):
        self.source_root = Path(root)
        self.root, self.factory, self.command = Path(archive_root) if archive_root is not None else Path(root), factory, command
        self.real_transport = factory is subprocess.Popen and command is worker_command
        if evidence_exporter is not None and command is worker_command:
            raise ValueError('TEST_EVIDENCE_EXPORTER_REQUIRES_TEST_COMMAND')
        self.evidence_exporter=evidence_exporter
        self.mission_evidence=None
        self.clock,self.wall=clock,wall
        self.mission_admission=mission_admission
        self.lock=threading.RLock()
        self.owner=self.job=None
        self.child=None
        self.thread=None
        self.mode=None
        self.closed=False
        self.used=set()
        self.sequence=0
        self.challenge=None
        self.challenge_at=0.
        self.input_at=0.
        self.stop_requested=False
        self.close_pending=False
        self.terminal_action=None
        self.stop_at=0.
        self.writes=queue.Queue(maxsize=2)
        self.pending_input=None
        self.release_pending=None
        self.journal=[]
        self.journal_event_count=0
        self.journal_overflow=False
        self.journal_sink=None
        self.state={'state':'NOT_STARTED','real_transport':self.real_transport,'physical_verified':False}
        self.last_trial=None
        self.mission_scope=None
        self.reference_sender=None;self.reference_nonce=None
        self.localization_query=None;self.localization_observation=None;self.localization_received=None
        self.localization_receiver=None
        self.goal_handoff_sender=None;self.goal_handoff_value=None;self.goal_handoff_receipt=None
        self.goal_handoff_reservation=None;self.goal_handoff_nonce=None
        self.localization_records=[];self.localization_bytes=0
        self.mission_bootstrapped=False
        self.adaptive_visual=None
        self.adaptive_telemetry=None;self.telemetry_received_s=None
        self.mission_context=None
        self.mission_request_hash=None;self.correction_proposal=None;self.correction_reply=None;self.correction_receipt=None
        self.diagnostics=None
        self.evidence_recovery=RobotEvidenceRecovery(self.root)
        from .robot_adapters import legacy_binding
        self._instance = legacy_binding()
        self._job_binding = None
        # Local saved reports only; startup never connects to or commands a robot.
        reports=self.root/'artifacts/manual-control'
        if reports.is_dir():
            for path in sorted(reports.glob('*/robot-report.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:100]:
                try:
                    if path.stat().st_size>512*1024:continue
                    report=json.loads(path.read_text(encoding='utf-8'))
                    if report.get('mode') in {'qualify','qualify_scan'} and not rejected_consumed_trial(report):
                        self.last_trial=trial_summary(report,path.parent.name);break
                except (OSError,ValueError,AttributeError):continue

    def bind_instance(self, binding):
        from .robot_adapters import checked_binding
        with self.lock:
            if self.thread and self.thread.is_alive() or self.evidence_recovery.thread and self.evidence_recovery.thread.is_alive():
                raise BrokerError('physical_busy','Wait for the operation or evidence transfer before selecting a robot.',status=409)
            binding=checked_binding(binding) if binding is not None else None
            if binding==self._instance:return
            self._instance=binding
            self.challenge=None;self.challenge_at=0.;self.last_trial=None
            self.mission_admission=None
            self.state={key:value for key,value in self.state.items() if key not in {'voltage_v','manual_speed','motion_lease_policy'}}
            self.state['physical_verified']=False
            # Keep original job/uncertain state for Stop, history and transfer.
            # It cannot establish readiness for the newly selected instance.

    def operation_active(self):
        """Same busy condition as snapshot, without copying historical journals."""
        with self.lock:return bool(self.thread and self.thread.is_alive())

    def snapshot(self,owner):
        with self.lock:
            log=self.journal_sink.status() if self.journal_sink else None
            robot=[e['data']['event'] for e in self.journal if e['kind']=='robot_event']
            observations=[e['data']['sample'] for e in robot if e['kind']=='observation']
            evidence={'pc_received':sum(e['kind']=='input_received' for e in self.journal),
                'pipe_written':sum(e['kind']=='pipe_written' for e in self.journal),
                'robot_accepted':sum(e['kind']=='accepted' for e in robot),
                'robot_published':sum(e['kind']=='published' for e in robot),
                'observations':len(observations),
                'last_observation':observations[-1] if observations else None,
                'floor_pose_measured':False, 'physical_success':None}
            if self.mode in {'control','control_scan'}:
                evidence.update(count_scope='RECENT_MEMORY_WINDOW',total_saved_event_count=self.journal_event_count)
            decisions=[e['data'] for e in robot if e['kind']=='mission_decision']
            scans=[e for e in self.journal if e['kind']=='robot_event' and e['data']['event']['kind']=='scan_preview']
            scan_faults=[e['data']['event']['data']['reason'] for e in self.journal
                         if e['kind']=='robot_event' and e['data']['event']['kind']=='scan_display_fault']
            preview=None
            if scans:
                last=scans[-1];event=last['data']['event'];scan=event['data']['scan']
                preview={**scan,'receipt_age_s':max(0.,self.clock()-last['t']),
                         'source_age_at_emit_s':max(0.,event['t']-scan['sample_s']),
                         'transport_delay_measured':False}
            return {**self.state,'robot_binding':deepcopy(self._job_binding),
                    'selected_robot_binding':deepcopy(self._instance),
                    'selected_instance_matches_job':self._instance==self._job_binding,
                    'session_storage':log,'session_evidence':evidence,
                    'scan_preview':preview if owner==self.owner else None,
                    'scan_display_fault':scan_faults[-1] if scan_faults and owner==self.owner else None,
                    'mission_readiness':{'start_available':self.command is not worker_command or self.mission_admission is not None,
                        'basis':'TEST_TRANSPORT_ONLY' if self.command is not worker_command else 'TRUSTED_ADMISSION_RECHECK_REQUIRED' if self.mission_admission else 'LIVE_MISSION_RELEASE_NOT_CONFIGURED',
                        'physical_ready':False},
                    'mission_scope':self.mission_scope if owner==self.owner else None,
                    'mission_progress':decisions[-1] if decisions else None,
                    'adaptive_visual':self.adaptive_visual if owner==self.owner else None,
                    'adaptive_telemetry':self.adaptive_telemetry if owner==self.owner else None,
                    'telemetry_received_s':self.telemetry_received_s if owner==self.owner else None,
                    'job_id':self.job if owner==self.owner else None,
                    'sequence':self.sequence,
                    'mode':self.mode,'owned':owner==self.owner,
                    'busy':bool(self.thread and self.thread.is_alive()),'last_trial':self.last_trial,
                    'evidence_recovery':self.evidence_recovery.snapshot(owner)}

    def resume_evidence(self, owner, job_id, request_id):
        with self.lock:
            if self.closed:
                raise BrokerError('controller_closed','Console closed',status=409)
            return self.evidence_recovery.start(owner,job_id,request_id,
                operation_busy=bool(self.thread and self.thread.is_alive()))

    def start(self,owner,mode,request_id,confirmed,scope=None,app_context=None,*,reference=None):
        with self.lock:
            if self.closed: raise BrokerError('controller_closed','Console closed',status=409)
            if mode not in MODES or confirmed is not True or not isinstance(request_id,str) or not re.fullmatch('[a-f0-9]{32}',request_id):
                raise BrokerError('physical_confirmation','Exact operation and current floor/battery/operator confirmation required',status=400)
            if mode in {'mission','localize'}:
                # Live requests require a server-owned reviewed registration.
                # No HTTP flag or saved test PASS can create that registration.
                # A fixed injected local transport is used only by offline tests.
                adaptive=isinstance(scope,dict) and scope.get('schema') in ADAPTIVE_SCHEMAS
                try:
                    if adaptive:
                        from twinpulse_core.adaptive_mission_contract import adaptive_scope
                        scope=adaptive_scope(scope)
                    else:scope=scope_document(scope)
                except (ValueError,TypeError):raise BrokerError('mission_scope_invalid','Bounded odom scope required',status=400)
                if (mode=='localize')!=(scope.get('phase')=='IDLE_LOCALIZATION_ONLY'):
                    raise BrokerError('localization_scope_invalid','Idle entry cannot execute a mission.',status=400)
                if mode=='localize':
                    from twinpulse_core.reference_transport import checked_reference,ReferenceSender
                    reference=checked_reference(reference,scope)
                    sender=ReferenceSender(reference)
                elif reference is not None:raise BrokerError('localization_scope_invalid','Unexpected full reference.',status=400)
                if self.command is worker_command:
                    from .mission_admission import QualifiedMissionAdmission
                    from .observed_release_registration import ObservedReleaseRegistration
                    expected=ObservedReleaseRegistration if adaptive else QualifiedMissionAdmission
                    if not isinstance(self.mission_admission,expected):
                        raise BrokerError('mission_live_locked','Live mission release/calibration not configured',status=409)
                    try:self.mission_admission(scope)
                    except ValueError as exc:raise BrokerError('mission_admission_rejected',str(exc),status=409) from exc
            elif scope is not None:raise BrokerError('mission_scope_invalid','Scope only belongs to a mission',status=400)
            if app_context is not None:
                valid_revision=lambda value:value is None or isinstance(value,str) and re.fullmatch('[a-f0-9]{64}',value) is not None
                valid_profile=lambda value:value is None or isinstance(value,str) and re.fullmatch('[A-Za-z0-9_.-]{1,128}',value) is not None
                if (not isinstance(app_context,dict) or set(app_context)!={'app_scene_revision','app_robot_profile_id','capture_status'}
                        or not isinstance(app_context['capture_status'],str)
                        or app_context['capture_status'] not in {'CAPTURED','UNAVAILABLE'}
                        or not valid_revision(app_context['app_scene_revision'])
                        or not valid_profile(app_context['app_robot_profile_id'])
                        or app_context['capture_status']=='UNAVAILABLE'
                        and (app_context['app_scene_revision'] is not None or app_context['app_robot_profile_id'] is not None)):
                    raise BrokerError('session_context_invalid','App evidence context is invalid',status=400)
            if request_id in self.used:
                if self.job==request_id and self.owner==owner and mode==self.mode and scope==self.mission_scope:return self.snapshot(owner)
                raise BrokerError('operation_consumed','Operation already used',status=409)
            if self.thread and self.thread.is_alive(): raise BrokerError('physical_busy','Owned operation still running',status=409)
            if self.evidence_recovery.thread and self.evidence_recovery.thread.is_alive():
                raise BrokerError('evidence_recovery_busy','Evidence transfer still running',status=409)
            if len(self.used)>=256: raise BrokerError('console_limit','Restart idle console',status=409)
            from .robot_adapters import require_adapter
            require_adapter(self._instance,operation='control')
            self._job_binding=deepcopy(self._instance)
            self.used.add(request_id)
            self.owner,self.job,self.mode=owner,request_id,mode
            # Evidence only: an App scene/profile is not calibrated to the physical robot.
            self.app_context=dict(app_context) if app_context is not None else None
            self.mission_scope=scope;self.mission_bootstrapped=False
            self.reference_sender=sender if mode=='localize' else None;self.reference_nonce=None
            self.localization_query=None;self.localization_observation=None;self.localization_received=None
            self.localization_receiver=None
            self.goal_handoff_sender=None;self.goal_handoff_value=None;self.goal_handoff_receipt=None
            self.goal_handoff_reservation=None;self.goal_handoff_nonce=None
            self.localization_records=[];self.localization_bytes=0
            self.adaptive_visual=None
            self.adaptive_telemetry=None;self.telemetry_received_s=None
            self.mission_evidence=None
            self.mission_context=None
            self.mission_request_hash=None;self.correction_proposal=None;self.correction_reply=None;self.correction_receipt=None
            self.sequence=0; self.challenge=None; self.stop_requested=False
            self.close_pending=False
            self.terminal_action=None
            self.child=None;self.writes=queue.Queue(maxsize=2)
            self.pending_input=None
            self.release_pending=None
            self.journal=[];self.journal_overflow=False;self.journal_event_count=0
            self.journal_sink=SessionJournal(self.root/'artifacts/manual-control'/self.job/'session.jsonl',
                                            max_bytes=64*1024*1024 if mode in {'control','control_scan'} else 8*1024*1024)
            self.input_at=self.clock()
            self.state={'state':'STARTING','real_transport':self.real_transport,'physical_verified':False}
            trace = self.diagnostics.begin('robot_operation_' + mode, durable=False,
                robot_session_id=request_id,evidence_kind='robot_session',evidence_id=request_id) if self.diagnostics else None
            self.thread=threading.Thread(target=self._run,args=(trace,),name='PhysicalRobotOperation',daemon=True)
            self.thread.start()
            return self.snapshot(owner)

    def input(self,owner,job,sequence,action,expires):
        with self.lock:
            if owner!=self.owner or job!=self.job or not self.thread or not self.thread.is_alive():
                raise BrokerError('physical_session','Active owned operation required',status=409)
            if (type(sequence) is not int or not 0<sequence<2147483647 or action not in INPUTS
                    or sequence<=self.sequence and action not in {'stop','close','finish_stop','force_stop'}):
                raise BrokerError('physical_input','Invalid or old input',status=409)
            operation_id=operation_for_action(action)
            self._record('input_received', sequence=sequence, action=action,
                         **({'operation_id':operation_id} if operation_id else {}))
            if action not in {'stop','close','finish_stop','force_stop'}:
                if type(expires) not in (int,float) or not math.isfinite(expires) or not 0<expires-self.wall()<=300:
                    if self.mode in {'control','control_scan'}:self._pause_manual('INPUT_STALE')
                    else:self._cancel()
                    raise BrokerError('physical_expired','Expired input: stop requested',status=409)
                self.input_at=self.clock()
            # A rejected stale packet must not advance the accepted sequence
            # and poison later current input. Stop still accepts old sequence.
            self.sequence=max(sequence,self.sequence)
            if action=='close': self._cancel(operator=True); return self.snapshot(owner)
            if action in {'finish_stop','force_stop'}:
                self._cancel(operator=True,action=action);return self.snapshot(owner)
            if self.stop_requested: raise BrokerError('physical_stopping','Stop already requested',status=409)
            if self.mode in {'mission','localize'}:
                if action=='stop':self._cancel(operator=True);return self.snapshot(owner)
                if action!='watch':
                    self._cancel()
                    raise BrokerError('mission_direction_rejected','Mission selects directions locally; cancelled',status=409)
            if self.mode in {'off','prepare'}:
                if action!='watch': raise BrokerError('physical_mode','Operation is not a motion session',status=409)
                return self.snapshot(owner)
            if self.mode=='lidar':
                if action=='stop':self._cancel()
                elif action!='watch':raise BrokerError('physical_mode','LiDAR-only session',status=409)
                return self.snapshot(owner)
            if self.mode=='scan' and action not in {'watch','stop'}:
                self._cancel()
                raise BrokerError('physical_mode','Scan-only session cannot drive',status=409)
            if self.mode in {'qualify','qualify_scan'} and action not in {'watch','qualify','stop'}:
                raise BrokerError('physical_mode','Diagnostic-only session',status=409)
            if self.mode in {'control','control_scan'} and action=='qualify':raise BrokerError('physical_mode','Manual-only session',status=409)
            # Exact-plan transfer is still the same wheel-disabled worker.
            # Keep its original watch/input gate alive; never grant directions
            # or renew a lease merely because a transfer is pending.
            handoff_watch=(action=='watch' and self.mode=='localize'
                and self.state.get('state')=='HANDOFF_PENDING'
                and self.goal_handoff_value is not None and self.goal_handoff_sender is not None
                and isinstance(self.goal_handoff_nonce,str)
                and re.fullmatch('[a-f0-9]{24}',self.goal_handoff_nonce) is not None)
            if self.state.get('state') not in {'READY','TESTING'} and not handoff_watch:
                if action=='watch':return self.snapshot(owner)
                raise BrokerError('physical_not_ready','Wait for robot-local preflight',status=409)
            if action=='stop':
                self.pending_input=None
                self.challenge=None
                self.release_pending=sequence
                self.state={**self.state,'state':'RELEASING'}
                self._send({'sequence':sequence,'action':action,'challenge':None,'age_ms':0})
            else:
                self.pending_input=(sequence,action,self.clock()+(expires-self.wall())/1000)
                self._flush_input()
            return self.snapshot(owner)

    def reply_correction(self,owner,job,proposal_revision,binding=None,*,reason=None):
        from twinpulse_core.mission_correction_contract import correction_reply
        with self.lock:
            proposal=self.correction_proposal
            if (owner!=self.owner or job!=self.job or self.mode!='mission' or self.stop_requested
                    or not self.thread or not self.thread.is_alive() or proposal is None
                    or proposal['revision']!=proposal_revision or self.correction_reply is not None
                    or self.clock()-self.correction_received_s>=1.):
                raise ValueError('CORRECTION_PC_REPLY_STALE_OR_NOT_OWNED')
            reply=correction_reply(proposal,self.mission_scope,binding,reason=reason)
            self.correction_reply=reply
            self._send(reply)
            return reply

    def _pause_manual(self,reason):
        """Revoke movement without closing the owned SSH/sensor session."""
        if self.stop_requested:return
        self.pending_input=None;self.challenge=None
        if self.state.get('state')=='RELEASING':return
        self.sequence+=1;self.release_pending=self.sequence
        self.state={**self.state,'state':'RELEASING','pause_reason':reason}
        self._send({'sequence':self.sequence,'action':'stop','challenge':None,'age_ms':0})
        self._record('motion_pause_requested',reason=reason,sequence=self.sequence)

    def _flush_input(self):
        if self.stop_requested or not self.pending_input or not self.challenge:return
        sequence,action,expires=self.pending_input
        remaining=expires-self.clock()
        if remaining<=0:
            if self.mode in {'control','control_scan'}:self._pause_manual('INPUT_STALE')
            else:self._cancel()
            return
        if self.clock()-self.challenge_at>=.15:
            self.challenge=None
            return  # Wait for a new robot challenge; retain original input expiry.
        self._send({'sequence':sequence,'action':action,'challenge':self.challenge,
                    'age_ms':max(0.,250-remaining*1000)})
        self.pending_input=None;self.challenge=None

    def query_localization(self,owner,job,query_id):
        with self.lock:
            if (owner!=self.owner or job!=self.job or self.mode!='localize' or self.stop_requested
                    or not self.thread or not self.thread.is_alive() or self.state.get('state')!='READY'
                    or self.goal_handoff_reservation is not None or self.goal_handoff_value is not None
                    or self.state.get('localization_input_sequence',0)<=0):
                raise BrokerError('localization_not_ready','Owned wheel-disabled localization worker required.',status=409)
            from twinpulse_core.reference_transport import hex_id
            if not hex_id(query_id,32) or self.localization_query and self.localization_observation is None:
                raise BrokerError('localization_query_busy','Only one fresh query may be pending.',status=409)
            self.localization_query={'id':query_id,'started_s':self.clock()}
            self.localization_observation=None;self.localization_received=None
            self.localization_receiver=None
            self._send({'action':'localization_query','query_id':query_id})

    def handoff_goal(self,owner,job,preview):
        from twinpulse_core.reference_transport import goal_handoff,ReferenceSender
        from twinpulse_core.current_goal_preview import review_source_matches
        preview=deepcopy(preview)
        with self.lock:
            if (owner!=self.owner or job!=self.job or self.mode!='localize' or self.stop_requested
                    or not self.thread or not self.thread.is_alive() or self.state.get('state')!='READY'
                    or self.localization_observation is None or self.goal_handoff_value is not None
                    or self.goal_handoff_reservation is not None):
                raise ValueError('GOAL_HANDOFF_NOT_OWNED_IDLE')
            scope=self.mission_scope;observation=self.localization_observation;thread=self.thread
            if not review_source_matches(preview['binding']['context'],self.localization_observation['context'],
                    new_session=preview['schema']=='current-goal-preview-2.0'):
                raise ValueError('GOAL_HANDOFF_SOURCE_CHANGED')
            reservation=object();self.goal_handoff_reservation=reservation
        try:
            # Admission/hash/encoding and durable evidence can be slow. They
            # must not own the input/Force STOP lock or discard fresh watches.
            self.mission_admission(scope)
            value=goal_handoff(scope,job,preview)
            sender=ReferenceSender(value)
            out=self.root/'artifacts/manual-control'/job
            with (out/'goal-handoff.json').open('xb') as stream:
                stream.write(sender.raw);stream.flush();os.fsync(stream.fileno())
            with self.lock:
                # A slow save cannot resurrect a stopped/replaced worker or
                # transfer an observation changed while the lock was released.
                if (self.goal_handoff_reservation is not reservation or owner!=self.owner or job!=self.job
                        or self.mode!='localize' or self.stop_requested or self.thread is not thread
                        or not thread.is_alive() or self.state.get('state')!='READY'
                        or self.mission_scope is not scope or self.localization_observation is not observation):
                    raise ValueError('GOAL_HANDOFF_SOURCE_CHANGED_OR_STOPPED')
                self.goal_handoff_value=value;self.goal_handoff_sender=sender
                self.goal_handoff_nonce=uuid.uuid4().hex[:24]
                self._record('goal_handoff_requested',plan_id=preview['plan_id'],payload=sender.descriptor)
                self._send({'action':'goal_handoff_begin','nonce':self.goal_handoff_nonce,'payload':sender.descriptor})
                self.state={**self.state,'state':'HANDOFF_PENDING'}
        finally:
            with self.lock:
                if self.goal_handoff_reservation is reservation:self.goal_handoff_reservation=None

    def _send(self,value):
        try:
            if value.get('action') in INPUTS and not self.journal_overflow:
                self._record('pipe_enqueue_requested',sequence=value['sequence'],action=value['action'],
                             source_age_ms=value['age_ms'])
            self.writes.put_nowait((json.dumps(value)+'\n').encode())
        except queue.Full:
            self._cancel();raise BrokerError('physical_transport','Command delivery unconfirmed',status=409)

    def _receive_adaptive_visual(self,value):
        from .remote_observed_adapter import checked_remote_visual
        with self.lock:
            scope=self.mission_scope;job=self.job;context=self.mission_context
            receipt=self.correction_receipt
            if not scope or scope.get('schema') not in ADAPTIVE_SCHEMAS:
                raise ValueError('UNEXPECTED_ADAPTIVE_VISUAL')
            if self.stop_requested:return
            binding=(receipt or {}).get('binding')
        started=self.clock()
        visual=checked_remote_visual(value,job,scope,context,binding=binding)
        with self.lock:
            if self.stop_requested:return
            if (self.job!=job or self.mission_scope is not scope or self.mission_context is not context
                    or self.correction_receipt is not receipt):
                raise ValueError('OBSERVED_REMOTE_VISUAL_SOURCE_CHANGED')
            self.adaptive_visual=visual
            self._record('adaptive_visual',revision=visual['revision'],validation_s=max(0.,self.clock()-started))

    def _receive_adaptive_telemetry(self,value):
        from twinpulse_core.mission_telemetry import checked_telemetry
        with self.lock:
            scope=self.mission_scope;job=self.job;context=self.mission_context
            if not scope or scope.get('schema') not in ADAPTIVE_SCHEMAS:
                raise ValueError('UNEXPECTED_ADAPTIVE_TELEMETRY')
            if self.stop_requested:return
        checked=checked_telemetry(value,job,scope,context)
        with self.lock:
            if self.stop_requested:return
            if self.job!=job or self.mission_scope is not scope or self.mission_context is not context:
                raise ValueError('MISSION_TELEMETRY_SOURCE_CHANGED')
            previous=self.adaptive_telemetry
            if previous and checked['emitted_s']<=previous['emitted_s']:
                raise ValueError('MISSION_TELEMETRY_CLOCK_OR_REPLAY')
            self.adaptive_telemetry=checked;self.telemetry_received_s=self.clock()
            self._record('adaptive_telemetry',telemetry=checked)

    def _record(self, kind, **data):
        # Never store challenges, auth/session cookies, or transport commands.
        # PC receipt/sending is not evidence of robot execution or floor motion.
        with self.lock:
            persistent=self.mode in {'control','control_scan'}
            if (self.journal_event_count>=262144 if persistent else len(self.journal)>=8192):
                self.journal_overflow=True
                self.state['recording_error']='JOURNAL_EVENT_BUDGET'
                self._cancel()
                return
            if persistent and len(self.journal)>=8192:del self.journal[:4096]
            self.journal_event_count+=1
            self.journal.append({'schema':'control-session-1.1' if persistent else 'control-session-1.0','job_id':self.job,
                'event_index':self.journal_event_count,'clock_domain':'pc_monotonic',
                't':self.clock(),'kind':kind,'real_transport':self.real_transport,'data':data})
            if self.journal_sink and not self.journal_sink.append(self.journal[-1]):
                self._cancel()

    def _cancel(self, *, operator=False,action='close'):
        # An explicit close must reach the robot before stdin is closed. EOF is
        # still a transport failure, never proof that a user-requested stop ran.
        # Failure/shutdown cancellation may escalate a pending close to EOF.
        if self.stop_requested:
            if operator:
                # A queued graceful stop may be superseded, never downgraded.
                if self.terminal_action!='finish_stop' or action=='finish_stop':return
            elif not self.close_pending:return
            self.close_pending=False
        else:
            self.stop_at=self.clock()
        self.stop_requested=True
        self.localization_observation=None;self.localization_received=None
        self.pending_input=None
        self.challenge=None
        self.close_pending=(operator and self.mode in {'control','control_scan','qualify','qualify_scan','mission','localize','lidar'}
                            and self.state.get('state') in {'READY','HANDOFF_PENDING','PREPARING','RELEASING','TESTING','LIDAR_RUNNING','STOPPING'})
        self.terminal_action=action if self.close_pending else None
        if self.state.get('state')!='FINISHED':
            self.state={**self.state,'state':'STOPPING','stop_request':self.terminal_action,'physical_verified':False}
        # Never block HTTP/watchdog on a stalled OS pipe. Owned writer closes input;
        # monitor terminates only this SSH child if its writer cannot finish.
        try:
            while True:self.writes.get_nowait()
        except queue.Empty:pass
        if self.close_pending:
            self.writes.put_nowait((json.dumps({'sequence':self.sequence,'action':action,
                                               'challenge':None,'age_ms':0})+'\n').encode())
        else:self.writes.put_nowait(None)

    def _receive_localization(self,value,robot_session):
        """Validate bulk evidence without blocking fresh watch or Force STOP.

        Only the stdout reader calls this. Capture immutable request identity,
        then recheck it and stop state before publishing. Validation time stays
        inside the freshness bound; this is not a faster-clock substitution.
        """
        from twinpulse_core.reference_transport import checked_observation,encode,descriptor,MAX_REFERENCE
        from twinpulse_core.current_goal_preview import current_binding
        from twinpulse_core.observation_stream import checked_context
        phase_started=time.perf_counter()
        with self.lock:
            query=self.localization_query;job=self.job;scope=self.mission_scope;mission_context=self.mission_context
            if (self.mode!='localize' or query is None
                    or (self.localization_observation is not None and not self.stop_requested)
                    or value.get('query_id')!=query['id']):
                raise ValueError('UNEXPECTED_LOCALIZATION_OBSERVATION')
        raw=encode(value,MAX_REFERENCE);raw_descriptor=descriptor(raw)
        with self.lock:
            if self.job!=job or self.localization_query is not query:return
            if self.localization_bytes+len(raw)>8*1024*1024:raise ValueError('IDLE_LOCALIZATION_RECORDING_BUDGET')
            self.localization_records.append((query['id'],raw));self.localization_bytes+=len(raw)
            self._record('localization_observation_received',query_id=query['id'],payload=raw_descriptor)
            if self.stop_requested:
                # A timeout/Stop can precede a packet already on stdout. Keep
                # bounded raw evidence and continue reading the final cleanup
                # receipt; never validate it as a current pose or renew input.
                self._record('localization_late_after_stop',query_id=query['id'],payload=raw_descriptor)
                return
        evidence=checked_observation(value,query['id']);context=checked_context({k:evidence[k]
            for k in ('project_id','session_id','boot_id','release_id','source_revision','origin')})
        decoded_at=time.perf_counter()
        received=self.clock();rtt=received-query['started_s']
        processing=value['issued_s']-value['received_s']
        if (not 0<=rtt<.2 or not 0<=processing<=rtt or value['issued_s']<evidence['sample_s']
                or context['project_id']!=scope['project_id']
                or context['origin']!='live_ros' or context['source_revision']!=context['release_id']
                or any(context[k]!=mission_context[k] for k in ('boot_id','release_id'))
                or context['session_id']!=robot_session
                or any(evidence.get(k) is not False for k in ('motion_authorized','physical_demo_ready'))
                or evidence.get('alignment_revision')!=scope['alignment']['report_revision']
                or evidence.get('room_from_map')!=scope['alignment']['room_from_map']):
            with self.lock:
                self._record('localization_validation_rejected',query_id=query['id'],
                    reason='IDLE_OBSERVATION_SOURCE_OR_TRANSPORT_CHANGED',round_trip_upper_s=rtt,
                    robot_processing_s=processing,decode_elapsed_s=decoded_at-phase_started,
                    transport_time_valid=bool(0<=rtt<.2 and 0<=processing<=rtt),
                    context_valid=bool(context['project_id']==scope['project_id']
                        and context['origin']=='live_ros' and context['source_revision']==context['release_id']
                        and all(context[k]==mission_context[k] for k in ('boot_id','release_id'))
                        and context['session_id']==robot_session),
                    reference_valid=bool(evidence.get('alignment_revision')==scope['alignment']['report_revision']
                        and evidence.get('room_from_map')==scope['alignment']['room_from_map']),
                    authority_absent=all(evidence.get(k) is False for k in ('motion_authorized','physical_demo_ready')))
            raise ValueError('IDLE_OBSERVATION_SOURCE_OR_TRANSPORT_CHANGED')
        # Query receipt + full PC round trip upper-bounds robot time. Preserve
        # processing elapsed through commit, without comparing absolute clocks.
        anchor=value['received_s']+rtt
        try:current_binding(evidence,context,anchor,scope['goal']['room_revision'])
        except ValueError as exc:
            with self.lock:
                self._record('localization_validation_rejected',query_id=query['id'],reason=str(exc)[:160],
                    evidence_age_upper_s=anchor-evidence['sample_s'],round_trip_upper_s=rtt,
                    decode_elapsed_s=decoded_at-phase_started,
                    binding_elapsed_s=time.perf_counter()-decoded_at)
            raise
        bound_at=time.perf_counter()
        with self.lock:
            if (self.job!=job or self.localization_query is not query or self.stop_requested
                    or self.mode!='localize' or self.mission_scope is not scope):return
            elapsed=self.clock()-received
            if elapsed<0 or not 0<=anchor+elapsed-evidence['sample_s']<.2-1e-9:
                self._record('localization_validation_rejected',query_id=query['id'],
                    reason='GOAL_PREVIEW_CURRENT_EVIDENCE_STALE',
                    evidence_age_upper_s=anchor+elapsed-evidence['sample_s'],round_trip_upper_s=rtt,
                    decode_elapsed_s=decoded_at-phase_started,binding_elapsed_s=bound_at-decoded_at,
                    commit_wait_s=time.perf_counter()-bound_at)
                raise ValueError('GOAL_PREVIEW_CURRENT_EVIDENCE_STALE')
            self.localization_received={'pc_s':received,'robot_upper_s':anchor,'round_trip_s':rtt}
            self.localization_observation={'evidence':evidence,'context':context}
            self._record('localization_observation',query_id=query['id'],payload=raw_descriptor,
                issued_s=value['issued_s'],received_s=value['received_s'],
                sample_s=evidence['sample_s'],round_trip_upper_s=rtt,
                current_pose_valid_at_receipt=True)

    def _run(self,trace=None):
        if trace is None:
            return self._run_impl()
        work=trace.child('robot_transport_and_existing_journal')
        try:
            self._run_impl(trace)
        except BaseException as error:
            work.finish('failed',error=error);trace.finish('failed',error=error)
            raise
        finally:
            with self.lock: state=dict(self.state)
            trace.bind(boot_id=state.get('boot_id'),release_id=state.get('release_id'))
            code=state.get('reason')
            result=state.get('result','UNKNOWN')
            failed=(state.get('state') in {'FAILED','REJECTED','CONNECTION_LOST'} or
                state.get('operation_status')=='FAILED' or
                any(marker in result for marker in ('FAIL','REJECT','ERROR','TIMEOUT','EXPIRED')))
            if failed:
                failure=trace.child('robot_primary_failure')
                failure.finish('failed',error_code=code,error_type=state.get('error_type'))
            if state.get('cleanup_error'):
                cleanup=trace.child(state.get('cleanup_stage','robot_cleanup'),role='cleanup')
                cleanup.finish('failed',error_code=state['cleanup_error'],role='cleanup')
            status=('failed' if failed or state.get('cleanup_error') else
                    'cancelled' if self.terminal_action in {'close','finish_stop','force_stop'} and state.get('cleanup_confirmed') is True else
                    'succeeded' if state.get('state')=='FINISHED' and state.get('cleanup_confirmed') is True and
                        result in {'QUALIFIED','PREPARED','STOPPED','MOTOR_OFF_VERIFIED','MISSION_ARRIVED'} else 'unknown')
            work.finish(status);trace.finish(status,error_code=code)

    def _run_impl(self,trace=None):
        out=self.root/'artifacts/manual-control'/self.job
        finished=False
        robot_report=None
        robot_session=None;robot_event_index=0;robot_event_time=-1.
        started=self.clock()
        writer_thread=None
        created=False
        try:
            out.mkdir(parents=True,exist_ok=False)
            created=True
            with (out/'robot-binding.json').open('x',encoding='utf-8') as target:
                json.dump(self._job_binding,target,sort_keys=True,allow_nan=False)
            self.journal_sink.start()
            # The physical adapter is available only for the default project.
            # Older journals without this field remain explicitly unattributed.
            project_id=self.mission_scope['project_id'] if self.mission_scope and self.mission_scope.get('schema') in ADAPTIVE_SCHEMAS else 'default'
            start_data={'mode':self.mode,'project_id':project_id}
            if self.app_context is not None:start_data['app_context']=self.app_context
            self._record('pc_session_started',**start_data)
            if self.mode in {'mission','localize'}:
                self._record('mission_scope',scope=self.mission_scope,scope_sha256=document_hash(self.mission_scope))
            if self.reference_sender:
                with (out/'survey-reference.json').open('xb') as target:target.write(self.reference_sender.raw)
            command=(self.command(self.source_root,self.mode,robot_binding=self._job_binding)
                     if self.command is worker_command else self.command(self.source_root,self.mode))
            if self.command is worker_command and self.mode == 'prepare' and self.root != self.source_root:
                command += ['--output-root', str(self.root/'artifacts')]
            with (out/'stderr.log').open('wb') as errors:
                with self.lock:
                    if self.stop_requested or self.closed:raise ValueError('CANCELLED_BEFORE_START')
                self.child=self.factory(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=errors,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                child=self.child
                writes=self.writes
                def writer():
                    try:
                        while child.poll() is None:
                            try:data=writes.get(timeout=.1)
                            except queue.Empty:continue
                            if data is None:break
                            packet=json.loads(data)
                            with self.lock:
                                if self.stop_requested and packet['action']!=self.terminal_action:continue
                            write_started=self.clock()
                            child.stdin.write(data);child.stdin.flush()
                            write_duration=max(0.,self.clock()-write_started)
                            with self.lock:
                                if self.child is not child:return
                                if packet['action']=='mission_request':
                                    self._record('mission_request_sent',request_sha256=document_hash(packet['request']))
                                elif packet['action']=='reference_chunk':
                                    handoff=packet['nonce']==getattr(self,'goal_handoff_nonce',None)
                                    sender=self.goal_handoff_sender if handoff else self.reference_sender
                                    self._record('goal_handoff_chunk_sent' if handoff else 'reference_chunk_sent',
                                        index=packet['index'],payload=sender.descriptor)
                                elif packet['action']=='goal_handoff_begin':
                                    self._record('goal_handoff_begin_sent',payload=packet['payload'])
                                elif packet['action']=='localization_query':
                                    self._record('localization_query_sent',query_id=packet['query_id'],pipe_write_s=write_duration)
                                elif packet['action']=='localization_next':
                                    self._record('localization_ack_sent',query_id=packet['query_id'],index=packet['index'],pipe_write_s=write_duration)
                                elif packet['action']=='correction_reply':
                                    self._record('correction_reply_sent',reply_revision=packet['revision'],
                                        proposal_revision=packet['proposal_revision'],reason=packet['reason'])
                                else:
                                    operation_id=operation_for_action(packet['action'])
                                    self._record('pipe_written',sequence=packet['sequence'],action=packet['action'],
                                                 source_age_ms=packet['age_ms'],
                                                 pipe_write_s=write_duration,
                                                 **({'operation_id':operation_id} if operation_id else {}))
                                    if packet['action'] in {'close','finish_stop','force_stop'}:
                                        self.state['stop_delivery']='PIPE_WRITTEN'
                    except (OSError,ValueError):pass
                    finally:
                        try:child.stdin.close()
                        except (OSError,ValueError):pass
                writer_thread=threading.Thread(target=writer,daemon=True)
                writer_thread.start()
                with self.lock:
                    if self.stop_requested:self._cancel()
                def monitor():
                    while child.poll() is None:
                        time.sleep(.05)
                        with self.lock:
                            if self.child is not child:return
                            if self.journal_sink.status()['error']:self._cancel()
                            if self.stop_requested and self.clock()-self.stop_at>20:
                                child.terminate();return
                            if self.state.get('state')!='FINISHED' and (self.closed or not self.close_pending and self.clock()-self.input_at>.5):
                                if self.mode in {'control','control_scan'} and not self.closed:
                                    if self.state.get('pause_reason')!='OPERATOR_PRESENCE_EXPIRED':self._pause_manual('OPERATOR_PRESENCE_EXPIRED')
                                else:self._cancel()
                            limit=330 if self.mode=='prepare' else None if self.mode in {'control','control_scan'} else 135
                            if limit is not None and self.clock()-started>limit:
                                child.terminate()  # Only this owned local child; never other robot processes.
                                return
                threading.Thread(target=monitor,daemon=True).start()
                while True:
                    line=self.child.stdout.readline(65537)
                    if not line:break
                    if len(line)>65536:raise ValueError('REMOTE_OUTPUT_BUDGET')
                    if self.mode=='prepare':continue
                    try:value=json.loads(line)
                    except ValueError:continue  # ROS logs are not protocol messages.
                    if not isinstance(value,dict):continue
                    state=value.get('state')
                    if state=='LOCALIZATION_CHUNK':
                        with self.lock:
                            query=self.localization_query;receiver=self.localization_receiver
                            if (self.stop_requested and self.mode=='localize' and query is not None
                                    and set(value)=={'state','query_id','chunk'} and value['query_id']==query['id']):
                                self._record('localization_partial_after_stop',query_id=query['id'],state=state)
                                continue  # No further ACK; preserve final cleanup receipt.
                            if (self.mode!='localize' or query is None or receiver is None or self.stop_requested
                                    or set(value)!={'state','query_id','chunk'} or value['query_id']!=query['id']):
                                raise ValueError('UNEXPECTED_LOCALIZATION_CHUNK')
                        value=receiver.accept(value['chunk'])
                        if value is None:
                            with self.lock:
                                if not self.stop_requested and self.localization_query is query:
                                    self._send({'action':'localization_next','query_id':query['id'],'index':receiver.index})
                            continue
                        state=value.get('state') if type(value) is dict else None
                        if state!='LOCALIZATION_OBSERVATION':raise ValueError('LOCALIZATION_TRANSFER_SHAPE')
                    if state=='LOCALIZATION_OBSERVATION':
                        self._receive_localization(value,robot_session)
                        continue
                    if state=='ADAPTIVE_VISUAL':
                        self._receive_adaptive_visual(value.get('visual'))
                        continue
                    if state=='ADAPTIVE_TELEMETRY':
                        if set(value)!={'state','telemetry'}:raise ValueError('MISSION_TELEMETRY_PACKET')
                        self._receive_adaptive_telemetry(value['telemetry'])
                        continue
                    with self.lock:
                        state=value.get('state')
                        if state=='GOAL_HANDOFF_NEXT':
                            if (self.mode!='localize' or self.stop_requested or not self.goal_handoff_sender
                                    or set(value)!={'state','nonce','index'} or value['nonce']!=self.goal_handoff_nonce):
                                raise ValueError('GOAL_HANDOFF_ACK_CHANGED')
                            self._send(self.goal_handoff_sender.chunk(value['nonce'],value['index']))
                            continue
                        if state=='GOAL_HANDOFF_ACCEPTED':
                            pending=self.goal_handoff_value
                            if (self.mode!='localize' or self.stop_requested or pending is None
                                    or set(value)!={'state','plan_id','payload','scope'}
                                    or value['scope']!=pending['scope'] or value['plan_id']!=pending['preview']['plan_id']
                                    or value['payload']!=self.goal_handoff_sender.descriptor
                                    or self.goal_handoff_sender.index*self.goal_handoff_sender.chunk_size<len(self.goal_handoff_sender.raw)):
                                raise ValueError('GOAL_HANDOFF_RECEIPT_CHANGED')
                            self.goal_handoff_receipt=deepcopy(value)
                            self.mission_scope=pending['scope'];self.mode='mission'
                            self.localization_observation=None;self.localization_received=None
                            self._record('goal_handoff_accepted',plan_id=value['plan_id'],payload=value['payload'])
                            self._record('mission_scope',scope=self.mission_scope,scope_sha256=document_hash(self.mission_scope))
                            self.state={**self.state,'state':'READY'}
                            continue
                        if state=='LOCALIZATION_BEGIN':
                            from twinpulse_core.reference_transport import ReferenceReceiver,OBSERVATION_CHUNK
                            query=self.localization_query
                            if (self.stop_requested and self.mode=='localize' and query is not None
                                    and set(value)=={'state','query_id','payload'} and value['query_id']==query['id']):
                                self._record('localization_partial_after_stop',query_id=query['id'],state=state)
                                continue  # Never start/continue a stopped transfer.
                            if (self.mode!='localize' or query is None or self.stop_requested
                                    or self.localization_receiver is not None or self.localization_observation is not None
                                    or set(value)!={'state','query_id','payload'} or value['query_id']!=query['id']):
                                raise ValueError('UNEXPECTED_LOCALIZATION_BEGIN')
                            self.localization_receiver=ReferenceReceiver(value['payload'],query['id'][:24],chunk_size=OBSERVATION_CHUNK)
                            self._send({'action':'localization_next','query_id':query['id'],'index':0})
                            continue
                        if state=='MISSION_CONTEXT':
                            if self.mode not in {'mission','localize'} or self.mission_bootstrapped:raise ValueError('UNEXPECTED_MISSION_CONTEXT')
                            if self.stop_requested:continue
                            if self.mission_scope.get('schema') in ADAPTIVE_SCHEMAS:
                                registration=self.mission_admission(self.mission_scope) if self.command is worker_command else None
                                if registration and (value.get('release_id')!=registration['source_id'] or value.get('calibration_sha256')!=registration['calibration_sha256']):
                                    raise ValueError('OBSERVED_REMOTE_RELEASE_OR_CALIBRATION_CHANGED')
                                from twinpulse_core.adaptive_mission_contract import adaptive_bootstrap
                                packet=adaptive_bootstrap(value,self.job,self.mission_scope)
                            else:packet=bootstrap_packet(value,self.job,self.mission_scope)
                            self.mission_bootstrapped=True
                            self.mission_request_hash=document_hash(packet['request'])
                            self.mission_context={k:value[k] for k in ('boot_id','release_id')}
                            self.reference_nonce=value['nonce'] if self.reference_sender else None
                            self._send(packet)
                        elif state=='REFERENCE_NEXT':
                            if (self.mode!='localize' or not self.reference_sender or not self.mission_bootstrapped
                                    or set(value)!={'state','nonce','index'} or value['nonce']!=self.reference_nonce):
                                raise ValueError('UNEXPECTED_REFERENCE_ACK')
                            if not self.stop_requested:self._send(self.reference_sender.chunk(value['nonce'],value['index']))
                        elif state=='SESSION_EVENT':
                            event=value.get('event')
                            if len(line)>32768 or not valid_event(event,adaptive=bool(self.mission_scope and self.mission_scope.get('schema') in ADAPTIVE_SCHEMAS)):
                                raise ValueError('INVALID_SESSION_EVENT')
                            if ((robot_session is not None and event['robot_session_id']!=robot_session)
                                    or event['event_index']!=robot_event_index+1 or event['t']<robot_event_time):
                                raise ValueError('SESSION_EVIDENCE_DISCONTINUITY')
                            robot_session,robot_event_index,robot_event_time=event['robot_session_id'],event['event_index'],event['t']
                            self._record('robot_event',event=event)
                        elif state=='ADAPTIVE_CORRECTION_PROPOSAL':
                            from twinpulse_core.mission_correction_contract import checked_proposal
                            if (self.mode!='mission' or self.correction_proposal is not None
                                    or set(value)!={'state','proposal'} or self.stop_requested):
                                raise ValueError('UNEXPECTED_CORRECTION_PROPOSAL')
                            self.correction_proposal=checked_proposal(value['proposal'],self.mission_scope,self.job,self.mission_request_hash)
                            self.correction_received_s=self.clock()
                            self._record('correction_proposal_received',proposal_revision=self.correction_proposal['revision'],
                                fit=self.correction_proposal['fit'])
                        elif state=='ADAPTIVE_CORRECTION_ACCEPTED':
                            reply=self.correction_reply
                            if (reply is None or self.correction_receipt is not None
                                    or set(value)!={'state','proposal_revision','reply_revision','binding','reason'}
                                    or value['reply_revision']!=reply['revision'] or value['proposal_revision']!=reply['proposal_revision']
                                    or value['binding']!=reply['binding'] or value['reason']!=reply['reason']):
                                raise ValueError('CORRECTION_REMOTE_RECEIPT_CHANGED')
                            self.correction_receipt=value
                            self._record('correction_robot_receipt',**{k:v for k,v in value.items() if k!='state'})
                        elif state in {'READY','PREPARING','TESTING','LIDAR_RUNNING'}:
                            if self.mode=='localize' and state=='READY':
                                acknowledged=value.get('input_sequence')
                                if type(acknowledged) is not int or acknowledged<0:
                                    raise ValueError('IDLE_LOCALIZATION_INPUT_ACK_INVALID')
                                self.state['localization_input_sequence']=acknowledged
                            if self.release_pending is not None:
                                acknowledged=value.get('input_sequence')
                                if state!='READY' or type(acknowledged) is not int or acknowledged<self.release_pending:
                                    continue  # Ignore READY already in flight before this release.
                                self.release_pending=None
                            if not self.stop_requested:self.state={**self.state,'state':state}
                            if value.get('pause_reason') in {'INPUT_DEADLINE_EXPIRED','OPERATOR_PRESENCE_EXPIRED','HOLD_LIMIT_EXCEEDED','LOCAL_OUTPUT_TIMEOUT','ARMING','OPERATOR_STOP','INPUT_CHALLENGE','INPUT_EXPIRED'}:
                                self.pending_input=None
                                self.state['pause_reason']=value['pause_reason']
                            elif 'pause_reason' in value and value['pause_reason'] is None:
                                self.state['pause_reason']=None
                            if type(value.get('motion_generation')) is int:
                                self.state['motion_generation']=value['motion_generation']
                            if value.get('motion_lease_policy') in {'fresh-intent-1.0','bounded-hold-1.0'}:
                                self.state['motion_lease_policy']=value['motion_lease_policy']
                            if value.get('session_policy') in {'until-stop-1.0','bounded-60s-1.0'}:
                                self.state['session_policy']=value['session_policy']
                            if value.get('manual_speed')=={'linear_m_s':.05,'angular_rad_s':.30}:
                                self.state['manual_speed']=value['manual_speed']
                            challenge=value.get('challenge')
                            if isinstance(challenge,str) and re.fullmatch('[a-f0-9]{24}',challenge):
                                self.challenge,self.challenge_at=challenge,self.clock()
                                self._flush_input()
                            if type(value.get('voltage_v')) in (int,float) and math.isfinite(value['voltage_v']):
                                self.state['voltage_v']=value['voltage_v']
                        elif state=='FINISHED':
                            report=value.get('report')
                            if not isinstance(report,dict):raise ValueError('INVALID_REPORT')
                            robot_report=report
                            if trace:trace.bind(boot_id=report.get('boot_id'),release_id=report.get('release_id'))
                            # Produced by the fixed worker; preserve evidence separately from readiness.
                            (out/'robot-report.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
                            self._record('robot_finished',status=report.get('status'),reason=report.get('reason'),
                                         robot_session_id=report.get('robot_session_id'),cleanup_confirmed=report.get('cleanup_confirmed') is True)
                            if self.mode in {'qualify','qualify_scan'} and not rejected_consumed_trial(report):
                                self.last_trial=trial_summary(report,self.job)
                            session_fields={key:self.state[key] for key in ('session_policy','motion_lease_policy','manual_speed',
                                'localization_error','localization_cleanup_error')
                                            if key in self.state}
                            self.state={**session_fields,'state':'FINISHED','result':str(report.get('status','UNKNOWN'))[:80],
                                'cleanup_confirmed':report.get('cleanup_confirmed') is True,
                                'real_transport':self.real_transport,
                                'physical_verified':self.real_transport and report.get('physical_validation')=='ACTUAL_ROBOT' and report.get('status')=='QUALIFIED',
                                'reason':str(report.get('reason',''))[:160]}
                            for field in ('cleanup_stage','cleanup_error','operation_status'):
                                if field in report:self.state[field]=str(report[field])[:160]
                            from twinpulse_core.cleanup_diagnostics import checked_notes
                            self.state['native_cleanup_errors']=checked_notes(report.get('cleanup_errors',[]))
                            if self.mode=='lidar':
                                self.state['lidar_result']={key:report.get(key) is True for key in
                                    ('operator_cancelled','data_quiet_after_stop','port_restored')}
                                attempts=report.get('stop_attempts')
                                self.state['lidar_result']['stop_write_complete']=any(
                                    isinstance(item,dict) and item.get('write_complete') is True
                                    for item in (attempts if isinstance(attempts,list) else []))
                                self.state['lidar_result']['physical_rotor_stopped']=False
                            if self.mode in {'scan','control_scan','qualify_scan','mission','localize'}:
                                self.state['sensor_cleanup_confirmed']=report.get('sensor_cleanup_confirmed') is True
                            detail=report.get('stop_diagnostics')
                            if isinstance(detail,dict):
                                self.state['stop_diagnostics']={k:v for k,v in detail.items()
                                    if k in {'passed','stable_ms','required_stable_ms','window_ms','band_ticks','reason','forward_observed'}}
                            assessment=report.get('stop_assessment')
                            if isinstance(assessment,dict):
                                self.state['stop_assessment']={k:v for k,v in assessment.items()
                                    if k in {'policy_id','status','reason','checks','metrics','limits','chassis_stop'}}
                            finished=True
                            self._cancel()  # Close only stdin, preserve final observed receipt.
                        elif state=='REJECTED':self.state={**self.state,'state':'REJECTED','reason':str(value.get('reason',''))[:160]}
                code=self.child.wait(timeout=5)
                with self.lock:
                    if self.mode=='prepare':
                        self.state={'state':'FINISHED','result':'PREPARED' if code==0 else 'PREPARATION_FAILED',
                            'real_transport':self.real_transport,'physical_verified':False}
                        finished=True
                    elif not finished:self.state={**self.state,'state':'CONNECTION_LOST','cleanup_confirmed':False}
        except Exception as exc:
            code=str(exc)
            if not re.fullmatch('[A-Z0-9_]{1,160}',code):code=type(exc).__name__
            with self.lock:
                localization_errors={key:self.state[key] for key in ('localization_error','localization_cleanup_error')
                    if key in self.state}
                self.state={**localization_errors,'state':'FAILED','reason':code,'error_type':type(exc).__name__,
                    'cleanup_confirmed':False,'real_transport':self.real_transport,'physical_verified':False}
        finally:
            with self.lock:
                if self.child and self.child.poll() is None:
                    self._cancel()
            if self.child:
                try:self.child.wait(timeout=20)
                except subprocess.TimeoutExpired:self.child.terminate()
            if writer_thread:writer_thread.join(timeout=1.)
            if self.child and self.child.stdout:
                try:self.child.stdout.close()
                except (OSError,ValueError,AttributeError):pass
            if (self.real_transport or self.evidence_exporter is not None) and robot_report is not None and created:
                try:
                    from .robot_evidence_export import export_finished_session
                    exporter=self.evidence_exporter or export_finished_session
                    export_result=(exporter(robot_report,out/'robot-evidence',robot_binding=self._job_binding)
                        if self.evidence_exporter is None else exporter(robot_report,out/'robot-evidence'))
                    with self.lock:self.state['evidence_export']=export_result['status']
                    if self.mode=='mission' and 'mission_evidence' in robot_report:
                        from .robot_evidence_export import load_mission_evidence
                        if (self.mission_context is None or any(robot_report.get(k)!=self.mission_context[k]
                                for k in ('boot_id','release_id'))):
                            raise ValueError('MISSION_EVIDENCE_BOOTSTRAP_CONTEXT_CHANGED')
                        evidence=load_mission_evidence(out/'robot-evidence',robot_report,
                            self.mission_scope,self.job,self.mission_request_hash)
                        binding=(self.correction_receipt or {}).get('binding')
                        fit=evidence.get('photo_alignment') or {}
                        if fit.get('goal_binding')!=binding:
                            raise ValueError('MISSION_EVIDENCE_CORRECTION_RECEIPT_CHANGED')
                        with self.lock:
                            self.mission_evidence=evidence
                            self.state['mission_evidence_status']='VERIFIED_HISTORICAL'
                except Exception as exc:
                    with self.lock:
                        self.state['evidence_export']='INCOMPLETE'
                        self.state['evidence_export_error']=type(exc).__name__
                        if self.mode=='mission' and 'mission_evidence' in robot_report:
                            code=str(exc)
                            self.state['mission_evidence_status']='REJECTED'
                            self.state['mission_evidence_error']=code if re.fullmatch('[A-Z0-9_]{1,120}',code) else 'MISSION_EVIDENCE_LOAD_FAILED'
            if self.mode=='mission' and robot_report is not None and self.mission_evidence is None:
                with self.lock:
                    self.state.setdefault('mission_evidence_status',robot_report.get('mission_evidence_status','NOT_AVAILABLE'))
                    if robot_report.get('mission_evidence_error'):
                        self.state.setdefault('mission_evidence_error',robot_report['mission_evidence_error'])
            saved=self.journal_sink.close() if self.journal_sink else False
            with self.lock:
                self.state['session_log_complete']=finished and saved and not self.journal_overflow and not (writer_thread and writer_thread.is_alive())
                self.localization_observation=None;self.localization_received=None
                self.state['session_event_count']=self.journal_event_count
                self.state['session_storage']=self.journal_sink.status() if self.journal_sink else None
                if not saved:self.state['physical_verified']=False
                result={**self.state,'robot_binding':deepcopy(self._job_binding)}
                self.challenge=None
            if created:
                try:
                    for query_id,raw in self.localization_records:
                        with (out/('localization-'+query_id+'.json')).open('xb') as target:target.write(raw)
                    with (out/'result.json').open('x',encoding='utf-8') as target:
                        json.dump(result,target,indent=2,allow_nan=False)
                except OSError:
                    with self.lock:self.state['report_saved']=False
                try:
                    # Historical read-only index; failure never grants or changes motion authority.
                    from .session_history import index_project_session
                    index_project_session(self.root,project_id,self.job)
                except (OSError,ValueError,BrokerError):
                    with self.lock:self.state['session_index_saved']=False

    def close(self):
        with self.lock:
            self.closed=True
            if self.thread and self.thread.is_alive():
                # Do not turn an already queued graceful close into EOF. The
                # worker must be allowed to report its final stop/cleanup.
                self._cancel(operator=True,action='close')
        if self.thread:
            self.thread.join(timeout=18)
            if self.thread.is_alive():
                with self.lock:self._cancel() # Bounded failure escalation only.
                self.thread.join(timeout=4)
