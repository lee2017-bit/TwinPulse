# SPDX-License-Identifier: Apache-2.0
"""Project scoped robot sessions. The engine, never this service, measures SIM motion.

Motion intents, connection heartbeats and recording have separate lifetimes.
No constructor, snapshot or restored record activates physical equipment.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
from threading import RLock, Event
import time
from uuid import uuid4

from .command_broker import BrokerError
from twinpulse_core.robot_lineage import twin_context, context_relation


def _id(value):
    return isinstance(value, str) and re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', value)


def _stamp():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def parse_robot_command(text):
    """Bounded unit-bearing commands; None means ordinary scene chat.

    This deterministic path also handles Stop when a model is unavailable.
    Free text never becomes executable code or an unbounded velocity stream.
    """
    if not isinstance(text, str) or len(text) > 2000:
        raise BrokerError('robot_text_invalid', 'Use a short robot instruction.', status=400)
    value=text.strip().lower()
    # A scene brief can mention robots, room dimensions and left/right furniture.
    # Those words are not a request to drive the focused robot.
    if (re.search(r'방|환경|가구|공간|장면|\b(?:room|environment|scene|furniture)\b',value)
            and re.search(r'만들|생성|배치|놓아|놓고|create|build|generate|place|arrange',value)):
        return None
    from twinpulse_core.sim_fleet_navigation import destination_intent
    try:destination=destination_intent(value)
    except ValueError as exc:raise BrokerError('robot_target_ambiguous',str(exc),status=409) from exc
    if destination is not None:return destination
    if (re.search(r'침대|의자|책상|소파|가구|벽|\b(?:bed|chair|desk|sofa|table|wall)\b',value)
            and not re.search(r'로봇|robot|turtlebot',value)):
        return None
    if re.fullmatch(r'(?:모든\s*로봇\s*|전체\s*|all\s+(?:robots\s+)?)(?:정지|멈춰|stop)(?:해줘|해|줘)?[.!?]*', value):
        return {'action':'stop_all'}
    if re.fullmatch(r'(?:멈춰|정지|스톱|stop|pause)(?:\s*(?:robot|로봇))?[.!?]*', value):
        return {'action':'stop'}
    if re.search(r'(?:멈춰|정지|스톱|\bstop|\bpause)(?:해줘|해|줘)?[.!?]*$',value):
        return {'action':'stop'} # A named Stop must not fall through to a model.
    if re.search(r'(?:라이다|라이더|lidar|스캔|scan)', value):
        if re.search(r'한\s*바퀴|한바퀴|360|full\s*(?:turn|rotation)|one\s*(?:turn|rotation)',value):
            return {'action':'task','direction':'left','amount':2*math.pi,'scan':True}
        if re.search(r'꺼|끄|중지|off|disable', value):return {'action':'lidar','enabled':False}
        if re.search(r'켜|시작|on|enable|start', value):return {'action':'lidar','enabled':True}
    if re.search(r'상태|배터리|battery|status',value):return {'action':'status'}
    if re.search(r'로그|기록.*(?:보여|분석)|\b(?:logs?|recording)\b',value):return {'action':'logs'}
    direction=next((d for pattern,d in ((r'앞|전진|forward|ahead','forward'),(r'뒤|후진|backward|back','backward'),
        (r'왼|좌회전|left','left'),(r'오른|우회전|right','right')) if re.search(pattern,value)),None)
    if direction:
        turn=direction in {'left','right'}
        match=re.search(r'(\d+(?:\.\d+)?)\s*(cm|센티미터|mm|밀리미터|m(?![a-z])|미터|degrees?|deg|도|°|radians?|rad)',value)
        if match:
            amount=float(match[1]);unit=match[2]
            angular=unit in {'도','°','degree','degrees','deg','rad','radian','radians'}
            if turn!=angular:raise BrokerError('robot_command_unit','Use distance for travel and angle for rotation.',status=400)
            amount*=math.pi/180 if unit in {'도','°','degree','degrees','deg'} else .01 if unit in {'cm','센티미터'} else .001 if unit in {'mm','밀리미터'} else 1
            if not 0<amount<=(2*math.pi if turn else 2):
                raise BrokerError('robot_command_extent','Use up to 2 metres or one full turn per instruction.',status=400)
            return {'action':'task','direction':direction,'amount':amount,'scan':False}
        raise BrokerError('robot_command_extent_required','Specify a distance or angle, for example forward 10cm or left 90 degrees.',status=409)
    return None


class RobotFleet:
    def __init__(self, broker, root, *, devices=None, clock=time.monotonic, wall=time.time, conversation_session_id=None):
        self.broker,self.root,self.devices=broker,Path(root),devices
        self.conversation_session_id=conversation_session_id
        self.clock,self.wall=clock,wall
        self.physical=getattr(devices,'physical_fleet',None)
        self.lock=RLock();self.robots={};self.revision=0;self.focused=None;self.last_command=None
        self.requests={};self.operations={};self.recorders={};self._engine=None;self._engine_at=None;self.physical_history={}
        self.command_contexts={}
        self.pending_requests=set();self.closed=False;self.finalizing=set()
        self.close_done=Event();self.persistence_receipt=None
        self.physical_display_poses={}
        self.physical_tracking_anchors={}
        from .fleet_recorder import FleetSnapshotWriter
        self.snapshot_writer=FleetSnapshotWriter()
        self.definitions=self.root/'robot-fleet.json'
        if self.definitions.exists():
            value=json.loads(self.definitions.read_text(encoding='utf-8'))
            self.physical_display_poses={key:deepcopy(pose) for key,pose in value.get('physical_display_poses',{}).items()
                if _id(key) and self._valid_display_pose(pose)}
            history=value.get('physical_history',{})
            self.physical_history={key:item for key,item in history.items() if _id(key) and _id(item)} if isinstance(history,dict) else {}
            for item in value.get('robots',[])[:16]:
                if item.get('kind')=='sim' and _id(item.get('robot_id')):
                    self.robots[item['robot_id']]=self._robot(item['robot_id'],item['label'],item['position_m'])
                    self.robots[item['robot_id']]['last_operation_id']=item.get('last_operation_id') if _id(item.get('last_operation_id')) else None
                    self.robots[item['robot_id']]['_registration']=deepcopy(item.get('registration'))
            self.focused=value.get('focused_robot_id') if value.get('focused_robot_id') in self.robots else None

    def _robot(self, identity,label,pose,kind='sim'):
        return dict(robot_id=identity,label=label,kind=kind,connection_state='DISCONNECTED',connection_epoch=None,
            motion_epoch=None,applied_motion_epoch=None,control_state='UNPREPARED',lidar_state='OFF',recording_state='IDLE',operation_id=None,last_operation_id=None,
            reason=None,battery=dict(voltage_v=None,percent=None,source='simulated' if kind=='sim' else 'unknown',age_ms=None),
            pose=dict(position_m=list(pose),frame_id='isaac_world',source='user_spawn',aligned=kind=='sim') if kind=='sim' else None,
            telemetry_age_ms=None,telemetry_sequence=0,capabilities=dict(drive=kind=='sim',lidar=kind=='sim'),scan=None,scan_receipt=None,
            live_heartbeat=False,setup=None,field=None,cleanup_confirmed=False,controller_state=None,sensor_frame=None,command=None,
            telemetry_diagnostic=None,native_diagnostic=None,project_id=None,display_pose=None,
            source_twin_context=None,
            _connected=False,_connecting=False,_at=None,_intent=None,_task=None,_sequence=0,_spawn=list(pose),_recorded_at=-math.inf,_registration=None)

    def _persist(self):
        value=dict(schema_version='robot-fleet-definitions-1.0',focused_robot_id=self.focused,
            physical_history=self.physical_history,
            physical_display_poses=deepcopy(self.physical_display_poses),
            robots=[dict(robot_id=r['robot_id'],label=r['label'],kind=r['kind'],position_m=r['_spawn'],last_operation_id=r['last_operation_id'],
                         **({'registration':deepcopy(r['_registration'])} if r['_registration'] else {}))
                    for r in self.robots.values() if r['kind']=='sim'])
        self.snapshot_writer.submit(self.definitions,json.dumps(value,ensure_ascii=False,allow_nan=False).encode('utf-8'))

    def registration_receipts(self,conversation_session_id):
        # Durable definition outbox, not telemetry or an operation/drive lease.
        # Legacy definitions have no receipt; never invent an old menu action.
        with self.lock:
            return [deepcopy(row['_registration']) for row in self.robots.values()
                    if row['kind']=='sim' and isinstance(row['_registration'],dict)
                    and isinstance(row['_registration'].get('source_twin_context'),dict)
                    and row['_registration']['source_twin_context'].get('project_id')==self.broker.project_id
                    and row['_registration'].get('source_twin_context',{}).get('conversation_session_id')==conversation_session_id]

    def _physical_values(self):
        service=getattr(self.devices,'registry_service',None)
        if service is None:return [],[]
        return (service.registry.snapshot()['robots'],
                self.physical.snapshot().get('robots',[]) if self.physical is not None else [])

    def _physical_rows(self,values):
        registered,sessions=values
        for value in registered:
            if value['id'] not in self.robots:
                self.robots[value['id']]=self._robot(value['id'],value['label'],[0,0,0],'physical')
                self.robots[value['id']]['reason']='PHYSICAL_SESSION_NOT_CONNECTED'
                self.robots[value['id']]['last_operation_id']=self.physical_history.get(value['id'])
            self.robots[value['id']]['label']=value['label']
            self.robots[value['id']]['display_pose']=deepcopy(self.physical_display_poses.get(value['id']))
            if self.physical is not None and self.robots[value['id']]['setup'] is None:
                from .robot_adapters import instance_binding
                binding=instance_binding(value)
                self.robots[value['id']]['capabilities'].update(profile=True)
                self.robots[value['id']]['setup']=dict(runtime_state='NOT_CONNECTED',
                    binding_sha256=binding['sha256'],blockers=['CONNECT_REQUIRED'],
                    profile=self.physical.profile_for_view(value['id']),qualification=None)
            elif self.physical is not None and self.robots[value['id']]['connection_epoch'] is None:
                self.robots[value['id']]['setup']['profile']=self.physical.profile_for_view(value['id'])
            if self.physical is not None and self.robots[value['id']]['connection_epoch'] is None:
                self.robots[value['id']]['field']=dict(mode='SUPERVISED_FIELD_TEST',armed=False,remaining_s=0,
                    config=self.physical.field_config_for_view(value['id']),blockers=['CONNECT_REQUIRED'],
                    stop_receipt=None,tracking=None,active_trial=None,trials=[])
        if self.physical is not None:
            for value in sessions:
                row=self.robots.get(value['robot_id'])
                if row is not None:
                    if row['connection_epoch']!=value.get('connection_epoch') or row['motion_epoch']!=value.get('motion_epoch'):
                        row['_sequence']=0
                    for key in value:
                        if key in row and not key.startswith('_'):row[key]=deepcopy(value[key])
                    if value.get('project_id')!=self.broker.project_id:
                        row['capabilities']['drive']=False
                        if row.get('setup') is not None:
                            row['setup']['blockers']=list(row['setup'].get('blockers',[]))+['CONNECTED_OPERATION_BELONGS_TO_OTHER_PROJECT']
                    operation=value.get('operation_id')
                    if _id(operation) and self.physical_history.get(row['robot_id'])!=operation:
                        self.physical_history[row['robot_id']]=row['last_operation_id']=operation
                        try:self._persist() # Historical reference only; never a connection/drive lease.
                        except OSError:row.update(recording_state='INCOMPLETE',reason='HISTORY_INDEX_WRITE_FAILED')

    def _twin_context(self,row=None,engine=None):
        return twin_context(self.broker.project_id,self.conversation_session_id,
            self.broker.supervisor_state() if engine is None else engine,
            kind='sim' if row and row['kind']=='sim' else 'physical',
            anchor=row.get('display_pose') if row and row['kind']=='physical' else None)

    def _event(self,row,kind,*,observed_twin_context=None,**values):
        operation=row.get('operation_id')
        if operation is None:return
        if self.snapshot_writer.error:
            if row['reason']!='SNAPSHOT_WRITE_FAILED':
                row['motion_epoch']=uuid4().hex;row['_sequence']=0
            row['_intent']=row['_task']=None;row['control_state']='PAUSED';row['reason']='SNAPSHOT_WRITE_FAILED'
            row['recording_state']='INCOMPLETE'
            self.operations[operation]['manifest']['missing']=[self.snapshot_writer.error]
        if self.operations[operation]['manifest'].get('ended_at'):return
        events=self.operations[operation]['events']
        event=dict(event_sequence=len(events)+1,utc=_stamp(),monotonic_s=self.clock(),kind=kind,
            operation_id=operation,project_id=self.broker.project_id,conversation_session_id=self.conversation_session_id,
            twin_context=deepcopy(observed_twin_context) if observed_twin_context is not None else self._twin_context(row),robot_id=row['robot_id'],
            connection_epoch=row['connection_epoch'],motion_epoch=row['motion_epoch'],**values)
        if len(events)>=20000:
            row['_intent']=row['_task']=None;row['control_state']='PAUSED';row['reason']='RECORDING_CAPACITY'
            self.operations[operation]['manifest']['missing']=['RECORDING_CAPACITY']
            return
        events.append(event)
        try:self.recorders[operation].append(event)
        except OSError as exc:
            row['_intent']=row['_task']=None;row['control_state']='PAUSED';row['reason']='RECORDING_FAILED'
            row['recording_state']='INCOMPLETE';self.operations[operation]['manifest']['missing']=[str(exc)]

    def _capture_operation(self,identity):
        record=self.operations[identity]
        return dict(record,events=list(record['events']),manifest=deepcopy(record['manifest']))

    def _save_operation(self,row,identity=None):
        identity=identity or row.get('operation_id')
        if identity is None or identity not in self.operations:return
        record=self.operations[identity]
        record['manifest'].update(event_count=len(record['events']),
            saved_at=_stamp(),completeness='FINALIZED' if record['manifest'].get('complete') else 'IN_PROGRESS',
            telemetry_source='actual USD transform readback; kinematic, not physical wheel/body evidence')
        try:self.snapshot_writer.submit(self.root/'robot-operations'/(identity+'.json'),self._capture_operation(identity),
                estimated_bytes=self.recorders[identity].bytes+1024*1024)
        except OSError as error:
            if row.get('operation_id')==identity:
                self._pause(row,'RECORDING_FAILED');row['recording_state']='INCOMPLETE'
            record['manifest']['missing']=[str(error)];record['manifest']['complete']=False

    def _begin(self,row,connection,source_context,request_id=None):
        operation=uuid4().hex
        from .fleet_recorder import FleetRecorder
        from .runtime_paths import resource_root
        directory=self.root/'robot-operations';directory.mkdir(parents=True,exist_ok=True)
        manifest_path=resource_root()/'source-manifest.json'
        pin=manifest_path if manifest_path.is_file() else Path(__file__)
        record=dict(schema_version='robot-operation-1.0',operation_id=operation,
            robot_id=row['robot_id'],project_id=self.broker.project_id,events=[],
            manifest=dict(source='isaac_kinematic_sim' if row['kind']=='sim' else 'physical',complete=False,
                          source_twin_context=deepcopy(source_context),lineage_status='RECORDED',
                          physical_motion_verified=False,started_at=_stamp(),missing=[],
                          source_files={pin.name:hashlib.sha256(pin.read_bytes()).hexdigest()}))
        recorder=FleetRecorder(directory/(operation+'.events.jsonl'))
        with self.lock:
            valid=not self.closed and row['_connecting'] and row['connection_epoch']==connection
            if valid:
                row.update(_connected=True,_connecting=False,operation_id=operation,last_operation_id=operation,
                           source_twin_context=deepcopy(source_context))
                self.recorders[operation]=recorder;self.operations[operation]=record
                self._event(row,'connection_requested',observed_twin_context=source_context,request_id=request_id);self._save_operation(row)
        if not valid:recorder.close() # A late connection must not restore closed authority.

    def _pause(self,row,reason=None):
        had=row['_intent'] is not None or row['_task'] is not None
        command=row.get('command')
        if command and command.get('state') in {'ACCEPTED','PLANNING','RUNNING'}:
            command.update(state='ARRIVED' if reason=='NAVIGATION_ARRIVED' else 'COMPLETED' if reason=='TASK_COMPLETED'
                else 'CANCELLED' if reason in {'OPERATOR_STOP','FOCUS_CHANGED','DISCONNECTED','LIDAR_OFF','ISAAC_SCENE_CHANGED'} else 'FAILED',reason=reason)
        row['_intent']=row['_task']=None;row['motion_epoch']=uuid4().hex;row['_sequence']=0
        row['control_state']='PAUSED';row['reason']=reason
        self.revision+=1
        if had:self._event(row,'stop_requested',reason=reason)

    def _fresh(self,row):
        return row['_at'] is not None and 0<=self.clock()-row['_at']<1

    def snapshot(self,*,refresh_physical=True):
        physical=self._physical_values() if refresh_physical else ([],[])
        with self.lock:
            self._physical_rows(physical)
            return self._snapshot_locked()

    def _snapshot_locked(self):
        values=[]
        # One current engine observation for this entire public snapshot.
        # Reacquiring the broker lock per robot also gave rows mixed identities.
        engine=self.broker.supervisor_state()
        for row in self.robots.values():
            if (self.snapshot_writer.error and row['kind']=='sim' and row['_connected']
                    and row['reason']!='SNAPSHOT_WRITE_FAILED'):
                self._pause(row,'SNAPSHOT_WRITE_FAILED');row['recording_state']='INCOMPLETE'
            if row['kind']=='sim' and row['_connected'] and not self._fresh(row):
                if row['_intent'] or row['_task']:self._pause(row,'TELEMETRY_STALE')
                if row['connection_state']!='DEGRADED':self.revision+=1
                row['connection_state']='DEGRADED'
            public={k:deepcopy(v) for k,v in row.items() if not k.startswith('_')}
            current=self._twin_context(row,engine)
            public['current_twin_context']=current
            public['twin_context_relation']=context_relation(public.get('source_twin_context'),current)
            if row['kind']=='sim':
                age=None if row['_at'] is None else max(0,(self.clock()-row['_at'])*1000)
                public['telemetry_age_ms']=age;public['battery']['age_ms']=age
            values.append(public)
        return dict(schema_version='robot-fleet-1.0',revision=self.revision,focused_robot_id=self.focused,
            robots=values,last_command=deepcopy(self.last_command),capabilities=dict(sim=True,physical=self.physical is not None),
            policy=dict(linear_m_s=.05,angular_rad_s=.30,input_expiry_ms=250))

    def action(self,body,owner):
        keys={'action','request_id','robot_id','connection_epoch','motion_epoch','payload'}
        if not isinstance(body,dict) or set(body)!=keys or not _id(body.get('request_id')) or not isinstance(body.get('payload'),dict):
            raise BrokerError('fleet_shape','Invalid robot request.',status=400)
        encoded=json.dumps(body,sort_keys=True,ensure_ascii=False,allow_nan=False)
        request=body['request_id']
        with self.lock:
            if self.closed and body['action'] not in {'stop','stop_all','disconnect'}:
                raise BrokerError('fleet_closed','Robot fleet is closed.',status=409)
            if request in self.pending_requests:
                raise BrokerError('fleet_request_pending','This request is still being completed.',status=409)
            self.pending_requests.add(request)
            # Reading/closing an unrelated physical service must not delay SIM
            # Stop or current intent delivery. Registry GET refreshes that list.
            target=self.robots.get(body['robot_id'] or self.focused)
            if body['action']=='command' and isinstance(body['payload'].get('text'),str):
                named=[row for row in self.robots.values() if row['label'].casefold() in body['payload']['text'].casefold()]
                if len(named)==1:target=named[0]
            sim_only=(body['action']=='register_sim' or target is not None and target['kind']=='sim')
        effects=[]
        try:
            if sim_only and body['action'] in {'connect','prepare','drive','command'} and callable(getattr(self.devices,'snapshot',None)):
                parsed=parse_robot_command(body['payload'].get('text','')) if body['action']=='command' else None
                if not parsed or parsed['action'] not in {'stop','stop_all','status','logs'}:
                    active_query=getattr(self.devices,'operation_active',None)
                    active=active_query() if callable(active_query) else self.devices.snapshot().get('active')
                    if active:
                        raise BrokerError('fleet_physical_active','Stop the active physical operation before a SIM control action.',status=409)
            physical=([],[]) if sim_only else self._physical_values()
            self._action(body,owner,encoded,physical,effects)
            for effect in effects:effect() # Disconnect/close/SSH service work cannot hold the SIM/Stop lock.
            return self.snapshot(refresh_physical=not sim_only)
        except Exception:
            with self.lock:
                self.requests.pop(request,None)
                target=self.robots.get(body['robot_id'])
                if body['action']=='connect' and target and target['kind']=='sim' and target['_connecting']:
                    target.update(_connecting=False,connection_state='DISCONNECTED',reason='CONNECTION_RECORDING_FAILED')
            raise
        finally:
            with self.lock:self.pending_requests.discard(request)

    def _action(self,body,owner,encoded,physical,effects):
        with self.lock:
            request=body['request_id'];known=self.requests.get(request)
            if body['action']=='register_sim':
                receipt=next((r['_registration'] for r in self.robots.values()
                    if r['_registration'] and r['_registration'].get('request_id')==request),None)
                if receipt:
                    if receipt['body_sha256']!=hashlib.sha256(encoded.encode('utf-8')).hexdigest():
                        raise BrokerError('fleet_request_conflict','Request ID already has different content.',status=409)
                    return # A restored registration retry neither adds nor reconnects.
            if known:
                if known!=encoded:raise BrokerError('fleet_request_conflict','Request ID already has different content.',status=409)
                return
            if len(self.requests)>8192:self.requests.pop(next(iter(self.requests)))
            action=body['action'];payload=body['payload'];identity=body['robot_id']
            if action=='command':
                if set(payload)!={'text'}:raise BrokerError('fleet_shape','Expected text.',status=400)
                matches=[r['robot_id'] for r in self.robots.values() if r['label'].casefold() in payload['text'].casefold()]
                if len(matches)>1:raise BrokerError('fleet_target_ambiguous','Name one robot or select it in the Twin.',status=409)
                if matches:identity=matches[0]
                parsed=parse_robot_command(payload['text'])
                if parsed is None:raise BrokerError('robot_command_unknown','Use a robot action with distance, angle, sensor or status.',status=409)
                action=parsed.pop('action');payload=parsed
                if identity is None:identity=self.focused
            if action=='register_sim':
                if set(payload)!={'label','position_m'} or len(self.robots)>=16:
                    raise BrokerError('fleet_registration','Use a label and position, with at most 16 robots.',status=400)
                label=payload['label'];pose=payload['position_m']
                if (not isinstance(label,str) or not 1<=len(label.strip())<=80 or any(ord(c)<32 for c in label)
                        or not isinstance(pose,list) or len(pose)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>100 for v in pose)):
                    raise BrokerError('fleet_registration','Invalid robot name or spawn pose.',status=400)
                previous_focus=self.focused
                identity=uuid4().hex;self.robots[identity]=self._robot(identity,label.strip(),pose);self.focused=identity
                self.robots[identity]['_registration']=dict(schema='sim-registration-1.0',request_id=request,
                    body_sha256=hashlib.sha256(encoded.encode('utf-8')).hexdigest(),robot_id=identity,label=label.strip(),
                    model_id='turtlebot3_burger',position_m=list(pose),registered_at=_stamp(),source_twin_context=self._twin_context(self.robots[identity]))
                try:self._persist()
                except OSError:
                    self.robots.pop(identity,None);self.focused=previous_focus
                    raise
            elif action=='stop_all':
                requested=self._twin_context()
                for row in self.robots.values():
                    if row['kind']=='sim':
                        self._pause(row,'OPERATOR_STOP');self._event(row,'stop_all_request',request_id=request)
                if self.physical is not None:
                    effects.append(lambda requested=requested:self._physical_stop_all(owner,request_id=request,request_twin_context=requested))
            else:
                self._physical_rows(physical)
                if identity not in self.robots:raise BrokerError('fleet_selection_required','Select the robot to control.',status=409)
                row=self.robots[identity]
                if action=='navigate' and row['kind']!='sim':
                    raise BrokerError('physical_target_navigation_unavailable','Object destinations are currently SIM-only. Physical navigation needs a verified world binding and robot navigation adapter; no motion was sent.',status=409)
                if action=='focus':
                    if self.focused in self.robots and self.focused!=identity:
                        previous=self.robots[self.focused]
                        if previous['kind']=='physical' and self.physical is not None:
                            effects.append(lambda target=previous['robot_id']:self.physical.release_manual(target,owner))
                        elif previous['_task'] is None:self._pause(previous,'FOCUS_CHANGED')
                    if row['kind']=='physical' and self.physical is not None:effects.append(lambda:self.physical.focus(identity,owner))
                    self.focused=identity;self._persist()
                elif action in {'stop','status','logs'}:
                    if action=='stop':
                        if row['kind']=='physical':
                            if self.physical is None:raise BrokerError('fleet_physical_stop_unavailable','No physical control connection exists in this observation build. No physical Stop was sent.',status=409)
                            requested=self._twin_context(row)
                            effects.append(lambda requested=requested:self.physical.stop(identity,owner,request_id=request,request_twin_context=requested))
                        else:
                            self._pause(row,'OPERATOR_STOP');self._event(row,'stop_request',request_id=request);self._save_operation(row)
                elif action=='set_twin_pose':
                    if row['kind']!='physical':raise BrokerError('fleet_marker_physical','Estimated markers are for registered physical robots.',status=400)
                    pose=payload.get('position_m')
                    if set(payload)!={'position_m'} or not isinstance(pose,list) or len(pose)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>100 for v in pose):
                        raise BrokerError('fleet_marker_pose','Use finite X/Y/yaw values within the scene bounds.',status=400)
                    engine=self.broker.supervisor_state();scene=(engine.get('snapshot') or {}).get('applied_revision')
                    if not engine.get('engine_connected') or not scene:
                        raise BrokerError('fleet_scene_required','Display a current Twin before placing an estimated marker.',status=409)
                    row['display_pose']=dict(position_m=list(pose),source='operator_estimate_not_localized',
                        scene_revision=scene,frame_id='isaac_world',aligned=False,visual_epoch=uuid4().hex)
                    self.physical_display_poses[identity]=deepcopy(row['display_pose']);self._persist()
                    self.physical_tracking_anchors.pop(identity,None)
                elif row['kind']=='physical':
                    if self.physical is None:raise BrokerError('fleet_physical_unavailable','Physical adapter is unavailable. No SIM command was sent.',status=409)
                    operation=(row.get('operation_id') if row['connection_state']!='DISCONNECTED' else None) or uuid4().hex
                    if action not in {'connect','disconnect','profile','field_setup'} and row.get('project_id')!=self.broker.project_id:
                        raise BrokerError('physical_project_changed','Return to the connection project, or Disconnect and reconnect in this conversation.',status=409)
                    requested=self._twin_context(row)
                    if action=='connect':effects.append(lambda requested=requested:self.physical.check_connection(identity,owner,request_id=request,operation_id=operation,project_id=requested['project_id'],source_twin_context=requested))
                    elif action=='disconnect':effects.append(lambda requested=requested:self.physical.disconnect(identity,owner,request_id=request,request_twin_context=requested))
                    elif action=='profile':
                        if set(payload)!={'profile'}:raise BrokerError('fleet_shape','Expected a reviewed measured profile.',status=400)
                        effects.append(lambda:self.physical.save_profile(identity,owner,payload['profile']))
                    elif action=='field_setup':
                        if set(payload)!={'config'}:raise BrokerError('fleet_shape','Expected field configuration.',status=400)
                        effects.append(lambda:self.physical.save_field_config(identity,owner,deepcopy(payload['config'])))
                    elif action in {'field_arm','field_test','field_review'}:
                        if self.focused!=identity:raise BrokerError('fleet_focus_changed','Select this robot before field testing.',status=409)
                        effects.append(lambda:self.physical.field_action(identity,owner,action,deepcopy(payload),
                            request_id=request,connection_epoch=body['connection_epoch'],motion_epoch=body['motion_epoch'],request_twin_context=requested))
                    elif action in {'prepare','qualify'}:
                        callback=self.physical.prepare_control if action=='prepare' else self.physical.qualify
                        effects.append(lambda:callback(identity,owner,payload=deepcopy(payload),request_id=request,
                            connection_epoch=body['connection_epoch'],request_twin_context=requested))
                    elif action=='lidar':
                        if set(payload)!={'enabled'} or type(payload['enabled']) is not bool:raise BrokerError('fleet_shape','Expected sensor enabled boolean.',status=400)
                        effects.append(lambda:self.physical.lidar(identity,owner,enabled=payload['enabled'],request_id=request,connection_epoch=body['connection_epoch'],request_twin_context=requested))
                    elif action in {'drive','task'}:
                        if self.focused!=identity:raise BrokerError('fleet_focus_changed','Select this robot before moving.',status=409)
                        if payload.get('direction') not in {'forward','backward','left','right'}:
                            raise BrokerError('fleet_direction','Invalid movement direction.',status=400)
                        if action=='drive':
                            if set(payload)!={'direction','sequence','expires_at_ms'} or type(payload['sequence']) is not int or payload['sequence']<=row['_sequence']:
                                raise BrokerError('fleet_sequence','Old or invalid movement input.',status=409)
                            expires=payload['expires_at_ms']
                            if type(expires) not in (int,float) or not math.isfinite(expires) or not 0<expires-self.wall()*1000<=300:
                                raise BrokerError('fleet_input_expired','Movement input expired; robot paused.',status=409)
                            row['_sequence']=payload['sequence']
                        elif body['action']!='command':raise BrokerError('fleet_task_text_required','Use a finite chat movement instruction.',status=400)
                        connection=body['connection_epoch'] if body['action']!='command' else row['connection_epoch']
                        motion=body['motion_epoch'] if body['action']!='command' else row['motion_epoch']
                        effects.append(lambda connection=connection,motion=motion:self.physical.drive(identity,owner,action=action,payload=deepcopy(payload),
                            request_id=request,connection_epoch=connection,motion_epoch=motion,request_twin_context=requested))
                    else:raise BrokerError('fleet_action_unknown','Unknown robot action.',status=400)
                elif action=='connect':
                    state=self.broker.supervisor_state();snap=state.get('snapshot') or {}
                    if not state.get('engine_connected') or not snap.get('applied_revision'):
                        raise BrokerError('fleet_scene_required','Display a current Twin in Isaac before connecting a SIM robot.',status=409)
                    if not row['_connected'] and not row['_connecting']:
                        row.update(_connecting=True,connection_state='CONNECTING',connection_epoch=uuid4().hex,motion_epoch=uuid4().hex,
                            control_state='UNPREPARED',reason=None,_at=None,telemetry_sequence=0,
                            applied_motion_epoch=None,recording_state='RECORDING',scan=None,_recorded_at=-math.inf,_engine_ready=False)
                        source_context=self._twin_context(row,state);connection=row['connection_epoch']
                        effects.append(lambda connection=connection,source_context=source_context:self._begin(row,connection,source_context,request))
                elif action=='disconnect':
                    self._pause(row,'DISCONNECTED');row.update(_connected=False,_connecting=False,connection_state='DISCONNECTED',lidar_state='OFF')
                    self._event(row,'disconnected',request_id=request)
                    effects.append(lambda operation=row.get('operation_id'):self._finalize(row,'DISCONNECTED',operation))
                elif action=='prepare':
                    self._ready(row,body,epoch=False);row.update(control_state='READY',reason=None);self._event(row,'prepared',request_id=request)
                elif action=='lidar':
                    self._ready(row,body,epoch=body['action']!='command')
                    if set(payload)!={'enabled'} or type(payload['enabled']) is not bool:raise BrokerError('fleet_shape','Expected sensor enabled boolean.',status=400)
                    if not payload['enabled']:self._pause(row,'LIDAR_OFF')
                    row['lidar_state']='STARTING' if payload['enabled'] else 'OFF';row['scan']=None
                    self._event(row,'lidar_requested',enabled=payload['enabled'],request_id=request)
                elif action in {'drive','task','navigate'}:
                    if action in {'task','navigate'} and body['action']!='command':
                        raise BrokerError('fleet_task_text_required','Use a bounded robot command.',status=400)
                    self._ready(row,body,epoch=body['action']!='command')
                    if self.focused!=identity:
                        raise BrokerError('fleet_focus_changed','Select this robot and wait for selection confirmation before moving.',status=409)
                    if row['control_state'] not in {'READY','DRIVING','PAUSED'}:raise BrokerError('fleet_prepare_required','Prepare the selected robot first.',status=409)
                    direction=payload.get('direction')
                    if action!='navigate' and direction not in {'forward','backward','left','right'}:raise BrokerError('fleet_direction','Invalid direction.',status=400)
                    if action=='drive':
                        if set(payload)!={'direction','sequence','expires_at_ms'} or type(payload['sequence']) is not int or payload['sequence']<=row['_sequence']:
                            raise BrokerError('fleet_sequence','Old or invalid movement input.',status=409)
                        expires=payload['expires_at_ms']
                        if type(expires) not in (int,float) or not math.isfinite(expires) or not 0<expires-self.wall()*1000<=300:
                            self._pause(row,'INPUT_STALE');raise BrokerError('fleet_input_expired','Movement input expired; robot paused.',status=409)
                        row['_sequence']=payload['sequence'];row['_task']=None
                        if row.get('command') and row['command']['state'] in {'ACCEPTED','PLANNING','RUNNING'}:
                            row['command'].update(state='CANCELLED',reason='MANUAL_OVERRIDE')
                        row['_intent']=dict(direction=direction,expires_at_ms=expires,sequence=payload['sequence'])
                    elif action=='navigate':
                        row['_task']=dict(task_id=request,kind='navigate',target_kind=payload['target_kind'],
                            deadline_ms=self.wall()*1000+120000)
                        row['_intent']=None
                        row['command']=dict(request_id=request,text=body['payload']['text'],kind='navigate',
                            state='ACCEPTED',target_kind=payload['target_kind'],reason=None)
                    else:
                        row['_task']=dict(task_id=request,direction=direction,amount=payload['amount'],scan=payload.get('scan',False),
                            start_pose=deepcopy(row['pose']['position_m']),deadline_ms=self.wall()*1000+min(120000,payload['amount']/(.30 if direction in {'left','right'} else .05)*1000+5000))
                        if payload.get('scan'):row['lidar_state']='STARTING'
                        row['_intent']=None
                        row['command']=dict(request_id=request,text=body['payload']['text'],kind='finite',state='RUNNING',reason=None)
                    row.update(control_state='DRIVING',reason=None,recording_state='RECORDING')
                    request_context=self._twin_context(row)
                    if len(self.command_contexts)>=8192:self.command_contexts.pop(next(iter(self.command_contexts)))
                    self.command_contexts[request]=request_context
                    self._event(row,'command_accepted',observed_twin_context=request_context,command_id=request,action=action,parameters=deepcopy(payload))
                else:raise BrokerError('fleet_action_unknown','Unknown robot action.',status=400)
            self.requests[request]=encoded;self.revision+=1
            row=self.robots.get(identity) or {}
            self.last_command=dict(request_id=request,operation_id=row.get('operation_id'),robot_id=identity,status='accepted',
                message='Physical request queued; follow robot-local ACK, live telemetry and cleanup evidence. Acceptance is not proof of completed motion.' if row.get('kind')=='physical' else 'Robot request accepted; actual motion is confirmed by engine telemetry.')
            # action() publishes one final snapshot after effects complete.
            # Do not copy every scan twice while holding the engine/Stop lock.

    def _physical_stop_all(self,owner,*,request_id=None,request_twin_context=None):
        errors=[]
        for row in self.physical.snapshot(owner).get('robots',[]):
            if row.get('owned'):
                try:self.physical.stop(row['robot_id'],owner,request_id=request_id,request_twin_context=request_twin_context)
                except BrokerError as error:errors.append(error.code)
        if errors:raise BrokerError('fleet_stop_delivery_incomplete','Stop attempted for every owned robot; some deliveries are unconfirmed: '+','.join(errors[:4]),status=409)

    @staticmethod
    def _valid_display_pose(pose):
        return (isinstance(pose,dict) and set(pose)=={'position_m','source','scene_revision','frame_id','aligned','visual_epoch'}
            and pose['source']=='operator_estimate_not_localized' and pose['aligned'] is False and pose['frame_id']=='isaac_world'
            and isinstance(pose['scene_revision'],str) and _id(pose['visual_epoch'])
            and isinstance(pose['position_m'],list) and len(pose['position_m'])==3
            and all(type(v) in (int,float) and math.isfinite(v) and abs(v)<=100 for v in pose['position_m']))

    def _ready(self,row,body,*,epoch):
        if not row['_connected'] or not self._fresh(row):raise BrokerError('fleet_connection_required','Wait for fresh robot telemetry.',status=409)
        if row['kind']=='sim' and row.get('_engine_ready') is not True:
            raise BrokerError('fleet_model_warming','Wait for measured post-model Isaac updates before preparing or moving.',status=409)
        if epoch and body.get('connection_epoch')!=row['connection_epoch']:
            raise BrokerError('fleet_connection_changed','Robot connection changed. Refresh the selected robot.',status=409)
        if body['action']=='drive' and body.get('motion_epoch')!=row['motion_epoch']:
            raise BrokerError('fleet_motion_changed','Motion was stopped. Begin a fresh direction input.',status=409)

    def engine_exchange(self,engine_id,stage_epoch,body):
        state=self.broker.supervisor_state();snap=state.get('snapshot') or {}
        binding=(engine_id,stage_epoch,snap.get('applied_revision'))
        if (not state.get('engine_connected') or binding[:2]!=(state.get('engine_session_id'),state.get('stage_epoch'))
                or not isinstance(body,dict) or set(body)!={'engine_session_id','stage_epoch','report'}
                or (body['engine_session_id'],body['stage_epoch'])!=binding[:2]):
            raise BrokerError('fleet_engine_stale','Fleet engine identity is not current.',status=409)
        report=body['report']
        if not isinstance(report,dict) or set(report)!={'applied_revision','robots'} or report['applied_revision']!=binding[2] or not isinstance(report['robots'],list) or len(report['robots'])>16:
            raise BrokerError('fleet_report_shape','Invalid bounded engine report.',status=400)
        observed_context=self._twin_context(dict(kind='sim'),state)
        with self.lock:
            if self.closed:return dict(fleet=dict(project_id=self.broker.project_id,applied_revision=binding[2],robots=[]))
            if self._engine is not None and self._engine!=binding:
                for row in self.robots.values():
                    if row['_connected']:
                        self._pause(row,'ISAAC_SCENE_CHANGED');row['_at']=None
                        row['telemetry_sequence']=0;row['applied_motion_epoch']=None
                        row['_engine_ready']=False
                        row['connection_epoch']=uuid4().hex;row['connection_state']='CONNECTING';row['scan']=None
                        if row['lidar_state']=='STREAMING':row['lidar_state']='STARTING'
            self._engine=binding;self._engine_at=self.clock()
            for value in report['robots']:
                if not isinstance(value,dict):continue
                row=self.robots.get(value.get('robot_id'))
                if row is None or row['kind']!='sim' or not row['_connected'] or value.get('connection_epoch')!=row['connection_epoch']:continue
                pose=value.get('position_m');sequence=value.get('sequence')
                if (type(sequence) is not int or sequence<=row['telemetry_sequence'] or not isinstance(pose,list) or len(pose)!=3
                    or any(type(v) not in (float,int) or not math.isfinite(v) or abs(v)>1000 for v in pose)):continue
                row['_at']=self.clock();row['telemetry_sequence']=sequence;row['connection_state']='CONNECTED'
                row['applied_motion_epoch']=value.get('motion_epoch')
                startup=value.get('runtime_startup')
                ready=(isinstance(startup,dict) and startup.get('model_authored') is True and startup.get('render_observed') is True
                    and startup.get('snapshot_capture_pending') is False and startup.get('ready') is True
                    and type(startup.get('post_author_updates')) is int and startup['post_author_updates']>=2)
                if row.get('_engine_ready') and not ready and row['control_state'] in {'READY','DRIVING','PAUSED'}:
                    self._pause(row,'ISAAC_MODEL_WARMING_UP')
                row['_engine_ready']=ready
                row['sim_readiness']=deepcopy(startup) if isinstance(startup,dict) else dict(ready=False,reason='NOT_RECORDED')
                if not ready and row['control_state']=='UNPREPARED':row['reason']='ISAAC_MODEL_WARMING_UP'
                elif ready and row['reason']=='ISAAC_MODEL_WARMING_UP':row['reason']=None
                row['pose']=dict(position_m=pose,frame_id='isaac_world',source='isaac_usd_kinematic',aligned=True)
                row['_spawn']=list(pose) # Preserve last measured model pose across scene rebuild/reopen.
                row['battery']=dict(voltage_v=None,percent=None,source='simulated',age_ms=0)
                scan=value.get('scan')
                if scan and row['lidar_state'] in {'STARTING','STREAMING'}:
                    points=scan.get('points',[]) if isinstance(scan,dict) else []
                    if len(points)<=360 and all(isinstance(p,list) and len(p)==2 and all(type(v) in (float,int) and math.isfinite(v) for v in p) for p in points):
                        row['scan']=dict(points=points,source='isaac_usd_surface_rays' if scan.get('source')=='isaac_usd_surface_rays' else 'isaac_usd_aabb_rays',
                            height_m=scan.get('height_m'),sensor_frame=scan.get('sensor_frame'),geometry=deepcopy(scan.get('geometry')),
                            sensor_xy_yaw_world=deepcopy(scan.get('position_m')),point_frame='sensor_local',
                            captured_at_ms=scan.get('captured_at_ms'),twin_context=self._twin_context(row,state),
                            stream_id=row['connection_epoch'],frame_sequence=sequence);row['lidar_state']='STREAMING'
                reason=value.get('reason')
                navigation=value.get('navigation')
                if row.get('_task',{} ) and row['_task'].get('kind')=='navigate' and isinstance(navigation,dict):
                    from twinpulse_core.sim_fleet_navigation import checked_navigation_report
                    checked=checked_navigation_report(navigation,row['_task']['task_id'])
                    if checked is not None and value.get('motion_epoch')==row['motion_epoch']:
                        before=row['command'].get('state')
                        row['command'].update(checked)
                        if before!=checked['state']:
                            self._event(row,'navigation_state',command=deepcopy(row['command']),observed_twin_context=observed_context)
                timing=value.get('runtime_timing')
                timing=deepcopy(timing) if (isinstance(timing,dict) and set(timing)=={'elapsed_s','integrated_s','substeps'}
                    and all(type(timing[k]) in (int,float) and math.isfinite(timing[k]) and 0<=timing[k]<=86400 for k in ('elapsed_s','integrated_s'))
                    and type(timing['substeps']) is int and 0<=timing['substeps']<=10) else None
                work=value.get('runtime_work')
                work=deepcopy(work) if isinstance(work,dict) and set(work)=={'bounds_s','model_authoring_s','bounds_rebuilds'} and all(
                    type(work[k]) in (int,float) and math.isfinite(work[k]) and 0<=work[k]<=86400 for k in ('bounds_s','model_authoring_s')) and type(work['bounds_rebuilds']) is int and work['bounds_rebuilds']>=0 else None
                intent=row['_intent'];reported_input=value.get('intent_sequence')
                superseded=(reason=='INPUT_STALE' and timing is not None and timing['elapsed_s']<.5 and value.get('motion_epoch')==row['motion_epoch']
                    and intent is not None and type(reported_input) is int and reported_input>0
                    and reported_input<intent['sequence'] and self.wall()*1000<intent['expires_at_ms'])
                if superseded:
                    self._event(row,'superseded_input_report',reason=reason,reported_input_sequence=reported_input,
                        current_input_sequence=intent['sequence'],observed_twin_context=observed_context)
                if not superseded and (reason in {'OBSTACLE_STOP','INPUT_STALE','ISAAC_UPDATE_STALLED','ISAAC_TRANSPORT_STALE','TASK_COMPLETED','TASK_TIMEOUT','MOVEMENT_STALLED','NAVIGATION_ARRIVED'} or isinstance(reason,str) and reason.startswith('NAVIGATION_')) and value.get('motion_epoch')==row['motion_epoch']:
                    self._event(row,'motion_result',reason=reason,position_m=pose,command_id=value.get('task_id'),
                        runtime_timing=timing,observed_twin_context=observed_context,request_twin_context=deepcopy(self.command_contexts.get(value.get('task_id'))))
                    self._pause(row,reason);self._save_operation(row)
                if self.clock()-row['_recorded_at']>=.5:
                    self._event(row,'engine_observation',position_m=pose,source='isaac_usd_kinematic',reason=reason,
                        scan=deepcopy(row['scan']),runtime_timing=timing,runtime_startup=deepcopy(row['sim_readiness']),runtime_work=work,telemetry_sequence=sequence,applied_motion_epoch=value.get('motion_epoch'),observed_twin_context=observed_context)
                    row['_recorded_at']=self.clock()
                self.operations[row['operation_id']]['manifest']['last_engine_binding']=dict(engine_session_id=engine_id,
                    stage_epoch=stage_epoch,scene_revision=binding[2],telemetry_sequence=sequence)
                self.revision+=1  # Fence older GET/POST snapshots, including task-result epochs.
            desired=[]
            for row in self.robots.values():
                if row['kind']=='sim' and row['_connected']:
                    desired.append(dict(robot_id=row['robot_id'],label=row['label'],connection_epoch=row['connection_epoch'],
                        motion_epoch=row['motion_epoch'],position_m=row['_spawn'],intent=deepcopy(row['_intent']),task=deepcopy(row['_task']),selected=row['robot_id']==self.focused,
                        lidar=row['lidar_state'] in {'STARTING','STREAMING'},control_state=row['control_state']))
                elif row['kind']=='physical' and len(desired)<16 and row.get('display_pose') is not None:
                    pose=row['display_pose']
                    if pose['scene_revision']==binding[2]:
                        position=list(pose['position_m'])
                        tracking=(row.get('field') or {}).get('tracking') or {}
                        key=(row.get('operation_id'),row.get('connection_epoch'),tracking.get('epoch'),pose['visual_epoch'],binding)
                        anchor=self.physical_tracking_anchors.get(row['robot_id'])
                        current=tracking.get('pose')
                        valid=(row.get('live_heartbeat') is True and tracking.get('status')=='ESTIMATED'
                            and isinstance(current,list) and len(current)==3 and all(type(v) in (float,int) and math.isfinite(v) for v in current))
                        if valid and anchor is None:
                            anchor=dict(key=key,origin=list(current),position=position)
                            self.physical_tracking_anchors[row['robot_id']]=anchor
                        if valid and anchor and anchor['key']==key:
                            origin=anchor['origin'];yaw=position[2]-origin[2]
                            dx,dy=current[0]-origin[0],current[1]-origin[1]
                            position=[position[0]+math.cos(yaw)*dx-math.sin(yaw)*dy,
                                position[1]+math.sin(yaw)*dx+math.cos(yaw)*dy,position[2]+current[2]-origin[2]]
                            anchor['position']=list(position)
                        elif anchor:position=list(anchor['position'])
                        if row.get('field') is not None:
                            row['field']['twin_tracking']=dict(status='ESTIMATED' if valid and anchor and anchor['key']==key else 'STALE_REANCHOR_REQUIRED',
                                position_m=position,source='native_relative_with_operator_anchor',aligned=False,
                                accuracy='UNQUALIFIED',scene_revision=binding[2])
                        desired.append(dict(robot_id=row['robot_id'],label=row['label'],visual_only=True,
                            connection_epoch=pose['visual_epoch'],motion_epoch=pose['visual_epoch'],
                            position_m=position,intent=None,task=None,lidar=False,control_state='UNPREPARED'))
            return dict(fleet=dict(project_id=self.broker.project_id,applied_revision=binding[2],robots=desired))

    def operation(self,identity,owner=None):
        if not _id(identity):raise BrokerError('fleet_operation_invalid','Invalid operation ID.',status=400)
        with self.lock:
            row=next((r for r in self.robots.values() if r.get('operation_id')==identity),None)
            if row:self._save_operation(row)
            captured=self._capture_operation(identity) if identity in self.operations else None
        if captured is not None:
            from .fleet_recorder import materialize_operation
            return materialize_operation(captured)
        # Historical disk/physical reads cannot block another robot's Stop.
        path=self.root/'robot-operations'/(identity+'.json')
        if not path.is_file():
            if self.physical is not None and owner is not None:
                return self.physical.operation(identity,owner,project_id=self.broker.project_id)
            raise BrokerError('fleet_operation_missing','Robot operation not found.',status=404)
        if path.stat().st_size>33*1024*1024:raise BrokerError('fleet_operation_missing','Robot operation exceeded the bounded reader.',status=409)
        record=json.loads(path.read_text(encoding='utf-8'))
        record.setdefault('manifest',{}).setdefault('lineage_status','LEGACY_UNKNOWN')
        journal=path.with_suffix('.events.jsonl')
        if not record.get('manifest',{}).get('complete') and journal.is_file():
            if journal.stat().st_size>32*1024*1024:raise BrokerError('fleet_journal_capacity','Saved journal exceeds reader capacity.',status=409)
            events=[];missing=['APP_EXIT_NOT_FINALIZED']
            for line in journal.read_text(encoding='utf-8').splitlines():
                try:event=json.loads(line)
                except ValueError:missing.append('INCOMPLETE_JOURNAL_LINE');break
                if event.get('event_sequence')!=len(events)+1:missing.append('JOURNAL_SEQUENCE_GAP');break
                events.append(event)
            record['events']=events
            record['manifest'].update(complete=False,completeness='RECOVERED_INCOMPLETE',missing=missing,
                event_count=len(events),journal_sha256=hashlib.sha256(journal.read_bytes()).hexdigest())
        return record

    def close(self,*,reason='APP_CLOSED'):
        with self.lock:
            already=self.closed
            if not already:self.closed=True
        if already:
            self.close_done.wait()
            return self.persistence_receipt
        try:
            with self.lock:
                rows=[]
                for row in self.robots.values():
                    if row['kind']=='physical':continue # Workspace owns these across project lifetimes.
                    self._pause(row,reason);row['_connected']=row['_connecting']=False
                    self._event(row,'project_switched' if reason=='PROJECT_SWITCH' else 'app_closed');rows.append((row,row.get('operation_id')))
            for row,operation in rows:self._finalize(row,reason,operation)
            with self.lock:
                try:self._persist()
                except OSError:pass # Writer error is preserved; crash-recovered records cannot be COMPLETE.
            self.persistence_receipt=self.snapshot_writer.close()
        except Exception:
            self.persistence_receipt=dict(complete=False,error='SIM_RETIRE_FAILED')
        finally:self.close_done.set()
        return self.persistence_receipt

    def _finalize(self,row,reason,identity):
        if identity is None:return
        with self.lock:
            manifest=self.operations[identity]['manifest']
            if manifest.get('ended_at') or identity in self.finalizing:return
            self.finalizing.add(identity);recorder=self.recorders[identity]
        receipt=recorder.close()
        journal=self.root/'robot-operations'/(identity+'.events.jsonl')
        try:digest=hashlib.sha256(journal.read_bytes()).hexdigest()
        except OSError:digest=None
        with self.lock:
            if not receipt['complete']:manifest['missing'].append(receipt['error'] or 'RECORDING_NOT_DRAINED')
            if digest is None:manifest['missing'].append('JOURNAL_UNREADABLE_AT_CLOSE')
            manifest.update(complete=not bool(manifest.get('missing')),ended_at=_stamp(),end_reason=reason,
                journal=dict(**receipt,path=journal.name,sha256=digest))
            if row.get('operation_id')==identity:
                row['recording_state']='COMPLETE' if manifest['complete'] else 'INCOMPLETE'
            self._save_operation(row,identity)
            self.finalizing.discard(identity)
