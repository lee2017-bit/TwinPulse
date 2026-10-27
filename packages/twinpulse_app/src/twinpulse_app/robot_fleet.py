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
from twinpulse_core.robot_control_timing import INPUT_TTL_MS


def _id(value):
    return isinstance(value, str) and re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', value)


def _stamp():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def immediate_stop_text(text):
    try:return isinstance(text,str) and (parse_robot_command(text) or {}).get('action') in {'stop','stop_all'}
    except BrokerError:return False


def parse_robot_command(text):
    """Bounded unit-bearing commands; None means ordinary scene chat.

    This deterministic path also handles Stop when a model is unavailable.
    Free text never becomes executable code or an unbounded velocity stream.
    """
    if not isinstance(text, str) or len(text) > 2000:
        raise BrokerError('robot_text_invalid', 'Use a short robot instruction.', status=400)
    value=text.strip().lower()
    from twinpulse_core.robot_task_plan import immediate_stop, without_in_place
    if immediate_stop(value):return {'action':'stop'}
    # A scene brief can mention robots, room dimensions and left/right furniture.
    # Those words are not a request to drive the focused robot.
    if (re.search(r'방|환경|가구|공간|장면|\b(?:room|environment|scene|furniture)\b',value)
            and re.search(r'만들|생성|배치|놓아|놓고|create|build|generate|place|arrange',without_in_place(value))):
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


SIM_OBSTACLE_LIMIT=8

def checked_sim_obstacle(payload,index):
    """Validate one SIM-world test obstacle: label, floor centre (x, y) and box size (w, d, h) in metres."""
    if not isinstance(payload,dict) or set(payload)!={'label','position_m','size_m'}:
        raise BrokerError('fleet_shape','Expected label, position_m [x, y] and size_m [w, d, h].',status=400)
    label=payload['label']
    if not isinstance(label,str) or not 1<=len(label.strip())<=80:raise BrokerError('fleet_shape','Label must be 1-80 characters.',status=400)
    position=payload['position_m'];size=payload['size_m']
    if (not isinstance(position,list) or len(position)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>50 for v in position)
            or not isinstance(size,list) or len(size)!=3 or any(type(v) not in (int,float) or not .1<=v<=3. for v in size)):
        raise BrokerError('fleet_shape','Position needs two finite metres; size needs three values between 0.1 and 3 m.',status=400)
    if index>=SIM_OBSTACLE_LIMIT:raise BrokerError('fleet_shape','At most %d SIM obstacles.'%SIM_OBSTACLE_LIMIT,status=409)
    return dict(id='simobs_%d_%s'%(index,uuid4().hex[:8]),label=label.strip(),position_m=[round(float(position[0]),3),round(float(position[1]),3)],
        size_m=[round(float(v),3) for v in size],source='SIM_WORLD_TEST_OBSTACLE_NOT_IN_TWIN')


def lidar_layer_payload(layer,scene_revision,*,limit=None):
    """Session LiDAR display layer for the floor map / Isaac (declared start + odometry; never navigation input)."""
    if not layer or layer['scene_revision']!=scene_revision:return None
    out={k:layer[k] for k in ('scene_revision','moved','routes','revision','label')}
    for key in ('stop_points','drive_points'):
        points=layer[key];step=max(1,-(-len(points)//limit)) if limit else 1
        out[key]=points[::step]
    return out


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
        self.consumed_display_epochs={}  # robot_id -> visual_epoch a route already started from (saved; reload drops that pose)
        self._frame_lineage=set()  # (declared, current) revision pairs proven to share one Twin frame (immutable)
        self.physical_tracking_anchors={}
        self.navigation_scene=None
        self.task_service=None
        # Availability is transient; the last accepted immutable epoch is not.
        # Keep this pin through missing/malformed reports to prevent a later
        # heartbeat from adopting a different mask under the same epoch.
        self._navigation_pin=None
        self.physical_navigation_reviews={} # Session-only; saved estimates never restore route authority.
        self.lidar_layer=None # Session-only display layer of route LiDAR points (declared start + odometry); never navigation input.
        self.sim_obstacles=[] # Session-only test obstacles that exist in the Isaac SIM world only (never in the Twin model or saved).
        from .fleet_recorder import FleetSnapshotWriter
        self.snapshot_writer=FleetSnapshotWriter()
        self.definitions=self.root/'robot-fleet.json'
        if self.definitions.exists():
            value=json.loads(self.definitions.read_text(encoding='utf-8'))
            consumed=value.get('consumed_display_epochs')
            self.consumed_display_epochs={k:v for k,v in consumed.items() if _id(k) and _id(v)} if isinstance(consumed,dict) else {}
            # 2026-10-28: the runner's used set is session-only, so a restart must not restore a start a route already left.
            self.physical_display_poses={key:deepcopy(pose) for key,pose in value.get('physical_display_poses',{}).items()
                if _id(key) and self._valid_display_pose(pose) and self.consumed_display_epochs.get(key)!=pose['visual_epoch']}
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
            telemetry_age_ms=None,pose_age_ms=None,telemetry_sequence=0,capabilities=dict(drive=kind=='sim',lidar=kind=='sim'),scan=None,scan_receipt=None,
            live_heartbeat=False,setup=None,field=None,cleanup_confirmed=False,controller_state=None,sensor_frame=None,command=None,
            telemetry_diagnostic=None,native_diagnostic=None,motion_observation=None,project_id=None,display_pose=None,
            timing_values=None,timing_profile_sha256=None,output_timing=None,
            task_local_observation=None,task_local_state=None,task_observation_age_ms=None,stop_receipt=None,device_boot_id=None,device_release_id=None,
            source_twin_context=None,
            # Link/owner diagnostics from the physical session (phys09 review); the merge below copies
            # only keys that exist here, so a new session field must be declared in this template.
            link_detail=None,remote_stderr_tail=None,recording_failure_reason=None,control_owner_state=None,
            last_reported_lidar_state=None,lidar_state_source=None,robot_storage=None,
            _connected=False,_connecting=False,_at=None,_intent=None,_task=None,_sequence=0,_spawn=list(pose),_recorded_at=-math.inf,_registration=None)

    def _persist(self):
        value=dict(schema_version='robot-fleet-definitions-1.0',focused_robot_id=self.focused,
            physical_history=self.physical_history,
            physical_display_poses=deepcopy(self.physical_display_poses),consumed_display_epochs=dict(self.consumed_display_epochs),
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

    def _physical_values(self, *, include_saved=False):
        projection_began=self.clock()
        service=getattr(self.devices,'registry_service',None)
        if service is None:return [],[]
        registered=service.registry.registration_snapshot()['robots']
        if include_saved and self.physical is not None:
            with self.lock:
                cold={identity for identity,row in self.robots.items() if row['kind']=='physical' and row['connection_epoch'] is None}
                cold.update(row['id'] for row in registered if row['id'] not in self.robots)
            # Optional saved-view reads happen before taking the fleet mutex.
            # They are not part of a control POST or its response projection.
            for row in registered:
                if row['id'] in cold:
                    row['_saved_profile']=self.physical.profile_for_view(row['id'])
                    row['_saved_field']=self.physical.field_config_for_view(row['id'])
        sessions=self.physical.snapshot().get('robots',[]) if self.physical is not None else []
        for row in sessions:row['_fleet_projection_began_at']=projection_began
        return registered,sessions

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
                    profile=deepcopy(value.get('_saved_profile')),qualification=None)
            elif self.physical is not None and self.robots[value['id']]['connection_epoch'] is None:
                if '_saved_profile' in value:self.robots[value['id']]['setup']['profile']=deepcopy(value['_saved_profile'])
            if (self.physical is not None and self.robots[value['id']]['connection_epoch'] is None
                    and ('_saved_field' in value or self.robots[value['id']]['field'] is None)):
                self.robots[value['id']]['field']=dict(mode='SUPERVISED_FIELD_TEST',armed=False,remaining_s=0,
                    config=deepcopy(value.get('_saved_field')),blockers=['CONNECT_REQUIRED'],
                    stop_receipt=None,tracking=None,active_trial=None,trials=[])
        if self.physical is not None:
            for value in sessions:
                row=self.robots.get(value['robot_id'])
                if row is not None:
                    # Unknown capture time cannot be refreshed by this merge.
                    # Stop/Disconnect projections without a marker remain
                    # usable for control receipts, not fresh visual tracking.
                    row['_physical_projection_at']=value.get('_fleet_projection_began_at')
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
        physical=self._physical_values(include_saved=True) if refresh_physical else ([],[])
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
            if row['kind']=='physical':
                pose=row.get('display_pose') or {}
                public['display_pose_current']=bool(pose) and self.same_twin_frame(pose.get('scene_revision'),(engine.get('snapshot') or {}).get('applied_revision'))
                view=getattr(self,'declared_route_start_view',None)
                try:public['route_start_estimate']=view(public) if view else None
                except Exception:public['route_start_estimate']=None  # display only
            public['current_twin_context']=current
            public['twin_context_relation']=context_relation(public.get('source_twin_context'),current)
            if row['kind']=='sim':
                age=None if row['_at'] is None else max(0,(self.clock()-row['_at'])*1000)
                public['telemetry_age_ms']=age;public['battery']['age_ms']=age
            values.append(public)
        return dict(schema_version='robot-fleet-1.0',revision=self.revision,focused_robot_id=self.focused,sim_obstacles=deepcopy(self.sim_obstacles),
            robots=values,last_command=deepcopy(self.last_command),capabilities=dict(sim=True,physical=self.physical is not None),
            navigation_scene=self._navigation_summary(engine),route=self._route_summary(),
            policy=dict(linear_m_s=.05,angular_rad_s=.30,input_expiry_ms=INPUT_TTL_MS))

    def floor_map(self):
        """Top-down floor for placing a robot or route stops by click (display scale, never localization)."""
        with self.lock:
            scene=self.navigation_scene
            if not scene:return dict(status='UNAVAILABLE',scene_revision=None,bounds=None,free_cells=[],cell_m=.1,obstacles=[],robots=[])
            free=[[round(c[0],2),round(c[1],2)] for c in (scene.get('observed_cells') or []) if c[2]=='free']
            step=max(1,-(-len(free)//4000));free=free[::step]
            robots=[dict(robot_id=r['robot_id'],label=r['label'],kind=r['kind'],
                position_m=((r.get('display_pose') or {}).get('position_m') if r['kind']=='physical' else (r.get('pose') or {}).get('position_m')))
                for r in self.robots.values()]
            return dict(status='AVAILABLE',scene_revision=scene['binding'][2],bounds=scene['geometry'].get('bounds'),free_cells=free,cell_m=.1,
                obstacles=scene['geometry'].get('obstacles') or [],robots=robots,label='FLOOR_MAP_DISPLAY_SCALE_NOT_LOCALIZATION',
                lidar_layer=lidar_layer_payload(getattr(self,'lidar_layer',None),scene['binding'][2],limit=2500),sim_obstacles=deepcopy(getattr(self,'sim_obstacles',[])))

    LIDAR_LAYER_LABEL='DECLARED_START_PLUS_ODOMETRY_DISPLAY_ONLY_NOT_REGISTERED'
    LIDAR_LAYER_CAP=6000

    def absorb_route_layer(self,overlay):
        """Keep a finished route's stop scans and drive points on the Twin until the user clears them (display only)."""
        if not overlay:return
        with self.lock:
            layer=self.lidar_layer
            if not layer or layer['scene_revision']!=overlay.get('scene_revision'):
                layer=dict(scene_revision=overlay.get('scene_revision'),stop_points=[],drive_points=[],moved=[],routes=0,revision=0,label=self.LIDAR_LAYER_LABEL)
            def merge(existing,points):
                seen={(round(p[0]/.05),round(p[1]/.05)) for p in existing}
                for p in points:
                    key=(round(p[0]/.05),round(p[1]/.05))
                    if key in seen:continue
                    seen.add(key);existing.append([round(p[0],3),round(p[1],3)])
                del existing[:-self.LIDAR_LAYER_CAP]
            merge(layer['stop_points'],[p for scan in overlay.get('scans') or [] for p in scan.get('points') or []])
            merge(layer['drive_points'],overlay.get('drive_scan') or [])
            layer['routes']+=1;layer['revision']+=1;layer['updated_at']=self.clock()
            self.lidar_layer=layer

    def note_lidar_move(self,object_id,label,position_xy_m,distance_m):
        """Mark an object the operator (or auto-apply) moved to a LiDAR estimate; the marker is display only."""
        with self.lock:
            layer=self.lidar_layer
            if not layer:
                scene=self.navigation_scene
                layer=self.lidar_layer=dict(scene_revision=scene['binding'][2] if scene else None,stop_points=[],drive_points=[],moved=[],routes=0,revision=0,label=self.LIDAR_LAYER_LABEL)
            layer['moved']=[m for m in layer['moved'] if m['object_id']!=object_id][-32:]+[dict(object_id=object_id,label=label,
                position_xy_m=[round(position_xy_m[0],3),round(position_xy_m[1],3)],distance_m=round(distance_m,3),basis='lidar_estimate_unverified')]
            layer['revision']+=1;layer['updated_at']=self.clock()

    def clear_lidar_layer(self):
        with self.lock:self.lidar_layer=None

    def _route_summary(self):
        """Declared-route progress for the web UI (display only; the chat card owns the decision)."""
        route=getattr(self,'route_overlay',None)
        if not route:return None
        scene=self.navigation_scene
        keys=('plan_id','robot_id','kind','state','reason','reached','reached_stops','skipped_stops','completed_steps','planned_steps',
              'current_step','recoveries','started_at','finished_at','revision','label','start','waypoints','polyline','pose','keepouts')
        summary={k:deepcopy(route.get(k)) for k in keys}
        summary.update(total_stops=len(route.get('waypoints') or []),trace=list(route.get('trace') or [])[-200:],
            live_scan=list(route.get('live_scan') or [])[:180],first_leg_straight_m=((route.get('plan') or {}).get('first_leg_straight_m')),
            candidates=len(route.get('candidates') or []),
            scene_current=bool(scene and scene['binding'][2]==route.get('scene_revision')))
        return summary

    def _navigation_summary(self,engine):
        scene=self.navigation_scene;geometry=scene['geometry'] if scene else {}
        binding=(engine.get('engine_session_id'),engine.get('stage_epoch'),(engine.get('snapshot') or {}).get('applied_revision'))
        current=bool(scene and engine.get('engine_connected') and scene['binding']==binding and 0<=self.clock()-scene['produced_at']<.5)
        return dict(status='AVAILABLE' if current else 'UNAVAILABLE',kind=('imported' if geometry.get('schema')=='scene-navigation-2.0' else 'legacy') if current else None,
            source_sha256=geometry.get('source_sha256') if current else None,
            units_basis=geometry.get('units_basis') if current else None,meters_per_unit=geometry.get('meters_per_unit') if current else None,
            geometry_revision=geometry.get('grid',{}).get('sha256') if current else None,
            scene_revision=binding[2] if current else None,physical_accuracy='UNQUALIFIED')

    def action(self,body,owner,*,_task_token=None):
        keys={'action','request_id','robot_id','connection_epoch','motion_epoch','payload'}
        if not isinstance(body,dict) or set(body)!=keys or not _id(body.get('request_id')) or not isinstance(body.get('payload'),dict):
            raise BrokerError('fleet_shape','Invalid robot request.',status=400)
        encoded=json.dumps(body,sort_keys=True,ensure_ascii=False,allow_nan=False)
        request=body['request_id']
        cancel_route=getattr(self,'declared_route_cancel',None)
        if cancel_route is not None and (body['action'] in {'stop','stop_all','disconnect','drive'}
                or body['action']=='focus' and body.get('robot_id')!=self.focused or body['action']=='command'
                and immediate_stop_text(body['payload'].get('text'))):
            cancel_route()  # before any delivery: the route must not send another step
        with self.lock:
            self._task_admission(body,_task_token)
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
            pinned_stop=body['action'] in {'stop','stop_all','disconnect'}
            ingress=(target['robot_id'],target.get('connection_epoch'),target.get('motion_epoch')) if target and target['kind']=='physical' else None
        effects=[]
        try:
            if sim_only and body['action'] in {'connect','prepare','drive','command'} and callable(getattr(self.devices,'snapshot',None)):
                parsed=parse_robot_command(body['payload'].get('text','')) if body['action']=='command' else None
                if not parsed or parsed['action'] not in {'stop','stop_all','status','logs'}:
                    active_query=getattr(self.devices,'operation_active',None)
                    active=active_query() if callable(active_query) else self.devices.snapshot().get('active')
                    if active:
                        raise BrokerError('fleet_physical_active','Stop the active physical operation before a SIM control action.',status=409)
            physical=([],[]) if sim_only or pinned_stop else self._physical_values()
            self._action(body,owner,encoded,physical,effects,ingress=ingress,task_token=_task_token)
            for effect in effects:effect() # Disconnect/close/SSH service work cannot hold the SIM/Stop lock.
            # Reuse the display-free projection after effects. Optional saved
            # settings are refreshed by GET, never synchronously by a drive ACK.
            after=(([],[]) if sim_only else ([],self.physical.snapshot().get('robots',[]))
                   if pinned_stop and self.physical is not None else self._physical_values())
            with self.lock:
                self._physical_rows(after)
                return self._snapshot_locked()
        except Exception:
            with self.lock:
                self.requests.pop(request,None)
                target=self.robots.get(body['robot_id'])
                if body['action']=='connect' and target and target['kind']=='sim' and target['_connecting']:
                    target.update(_connecting=False,connection_state='DISCONNECTED',reason='CONNECTION_RECORDING_FAILED')
            raise
        finally:
            with self.lock:self.pending_requests.discard(request)

    def _task_admission(self,body,token):
        service=self.task_service
        if service is None:return
        if token is not None:
            if body['action'] in {'stop','stop_all'}:return # Stop survives revoked/closed authority.
            service.admit(token)
            row=self.robots.get(body['robot_id'])
            if row is not None and body['action'] not in {'stop','stop_all'} and (
                    body['connection_epoch']!=row['connection_epoch'] or body['motion_epoch']!=row['motion_epoch']):
                raise BrokerError('robot_task_child_epoch_changed','Task input was superseded by a Stop or another motion.',status=409)
            if body['action']=='command':service.admit_motion(body,row,self.navigation_scene)
            return
        parsed=None
        if body['action']=='command':
            try:parsed=parse_robot_command(body['payload'].get('text',''))
            except BrokerError:pass
        action=(parsed or {}).get('action',body['action'])
        if action in {'stop','stop_all','disconnect','focus','drive'}:
            service.revoke('EXTERNAL_'+action.upper())
        if service.owns_execution() and action not in {'stop','stop_all','disconnect','status','logs'}:
            raise BrokerError('robot_task_active','Stop the robot task before a new control action.',status=409)

    def _action(self,body,owner,encoded,physical,effects,*,ingress=None,task_token=None):
        with self.lock:
            # Second check closes the external-Stop race during transport/registry reads.
            self._task_admission(body,task_token)
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
            elif action=='sim_obstacle':
                # SIM-world test obstacle: a box the Isaac SIM LiDAR and proximity stop can see but the Twin model does
                # not know, so a SIM route meets a real mismatch (the physical "box on leg 1" rehearsal). Session-only.
                self.sim_obstacles=self.sim_obstacles+[checked_sim_obstacle(payload,len(self.sim_obstacles))]
            elif action=='clear_sim_obstacles':
                if payload not in (None,{}):raise BrokerError('fleet_shape','No payload.',status=400)
                self.sim_obstacles=[]
            elif action=='clear_lidar_layer':
                if payload not in (None,{}):raise BrokerError('fleet_shape','No payload.',status=400)
                self.lidar_layer=None  # display layer only; nothing moves
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
                    if row['control_state'] in {'DRIVING','ARMING'}:
                        raise BrokerError('physical_anchor_requires_stop','Stop the robot before changing its estimated Twin anchor.',status=409)
                    row['display_pose']=dict(position_m=list(pose),source='operator_estimate_not_localized',
                        scene_revision=scene,frame_id='isaac_world',aligned=False,visual_epoch=uuid4().hex)
                    self.physical_display_poses[identity]=deepcopy(row['display_pose']);self._persist()
                    self.physical_tracking_anchors.pop(identity,None)
                    self.physical_navigation_reviews.pop(identity,None)
                    tracking=(row.get('field') or {}).get('tracking') or {};native_pose=tracking.get('pose')
                    if (row.get('connection_epoch') and row.get('live_heartbeat') is True and tracking.get('status')=='ESTIMATED'
                            and isinstance(native_pose,list) and len(native_pose)==3
                            and all(type(v) in (int,float) and math.isfinite(v) for v in native_pose)):
                        binding=(engine['engine_session_id'],engine['stage_epoch'],scene)
                        self.physical_navigation_reviews[identity]=(row['connection_epoch'],row['display_pose']['visual_epoch'],tracking.get('epoch'))
                        self.physical_tracking_anchors[identity]=dict(key=(row.get('operation_id'),row['connection_epoch'],
                            tracking.get('epoch'),row['display_pose']['visual_epoch'],binding),origin=list(native_pose),position=list(pose))
                elif row['kind']=='physical':
                    if self.physical is None:raise BrokerError('fleet_physical_unavailable','Physical adapter is unavailable. No SIM command was sent.',status=409)
                    operation=(row.get('operation_id') if row['connection_state']!='DISCONNECTED' else None) or uuid4().hex
                    if action not in {'connect','disconnect','profile','field_setup'} and row.get('project_id')!=self.broker.project_id:
                        raise BrokerError('physical_project_changed','Return to the connection project, or Disconnect and reconnect in this conversation.',status=409)
                    requested=self._twin_context(row)
                    # Preserve the ingress intent, not the later pool snapshot.
                    # In particular a delayed chat command must not acquire the
                    # new epoch created by a concurrently completed Stop.
                    admitted=ingress if ingress and ingress[0]==identity else (identity,None,None)
                    connection=body['connection_epoch'] or admitted[1]
                    motion=body['motion_epoch'] or admitted[2]
                    if action in {'drive','task','navigate','prepare','qualify','lidar','field_arm','field_test'} and (not connection or not motion):
                        raise BrokerError('fleet_intent_binding_required','Refresh the selected connection before a new control request.',status=409)
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
                        effects.append(lambda connection=connection,motion=motion:callback(identity,owner,payload=deepcopy(payload),request_id=request,
                            connection_epoch=connection,motion_epoch=motion,request_twin_context=requested))
                    elif action=='lidar':
                        if set(payload)!={'enabled'} or type(payload['enabled']) is not bool:raise BrokerError('fleet_shape','Expected sensor enabled boolean.',status=400)
                        effects.append(lambda connection=connection,motion=motion:self.physical.lidar(identity,owner,enabled=payload['enabled'],request_id=request,connection_epoch=connection,motion_epoch=motion,request_twin_context=requested))
                    elif action=='navigate':
                        if self.focused!=identity:raise BrokerError('fleet_focus_changed','Select this robot before moving.',status=409)
                        geometry=deepcopy(self.navigation_scene);anchor=deepcopy(self.physical_tracking_anchors.get(identity))
                        estimate=deepcopy(row.get('display_pose'));tracking=deepcopy((row.get('field') or {}).get('tracking'))
                        effects.append(lambda:self._physical_destination(identity,owner,request,payload['target_kind'],
                            body['payload']['text'],requested,geometry,anchor,estimate,tracking,connection,motion))
                    elif action in {'drive','task'}:
                        if self.focused!=identity:raise BrokerError('fleet_focus_changed','Select this robot before moving.',status=409)
                        if payload.get('direction') not in {'forward','backward','left','right'}:
                            raise BrokerError('fleet_direction','Invalid movement direction.',status=400)
                        if action=='drive':
                            if set(payload)!={'direction','sequence','expires_at_ms'} or type(payload['sequence']) is not int or payload['sequence']<=row['_sequence']:
                                raise BrokerError('fleet_sequence','Old or invalid movement input.',status=409)
                            expires=payload['expires_at_ms']
                            ttl=(row.get('timing_values') or {}).get('input_ttl_ms',INPUT_TTL_MS)
                            if type(expires) not in (int,float) or not math.isfinite(expires) or not 0<expires-self.wall()*1000<=ttl:
                                raise BrokerError('fleet_input_expired','Movement input expired; robot paused.',status=409)
                            row['_sequence']=payload['sequence']
                        elif body['action']!='command':raise BrokerError('fleet_task_text_required','Use a finite chat movement instruction.',status=400)
                        physical_payload=deepcopy(payload)
                        if action=='task':physical_payload['text']=body['payload']['text']
                        task_guard=(self.task_service._physical_motion_guard(self.task_service.motion_pin)
                            if task_token is not None and self.task_service is not None and action=='task' else None)
                        effects.append(lambda connection=connection,motion=motion,physical_payload=physical_payload,task_guard=task_guard:self.physical.drive(identity,owner,action=action,payload=physical_payload,
                            request_id=request,connection_epoch=connection,motion_epoch=motion,request_twin_context=requested,
                            **({'admission_guard':task_guard} if task_guard is not None else {})))
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
                    if body['action']=='command' and body.get('motion_epoch') is not None and body['motion_epoch']!=row['motion_epoch']:
                        # A runner-sent step bound to an epoch a Stop has since replaced.
                        raise BrokerError('fleet_motion_epoch_changed','Robot was stopped; this step was not sent.',status=409)
                    if self.focused!=identity:
                        raise BrokerError('fleet_focus_changed','Select this robot and wait for selection confirmation before moving.',status=409)
                    if row['control_state'] not in {'READY','DRIVING','PAUSED'}:raise BrokerError('fleet_prepare_required','Prepare the selected robot first.',status=409)
                    direction=payload.get('direction')
                    if action!='navigate' and direction not in {'forward','backward','left','right'}:raise BrokerError('fleet_direction','Invalid direction.',status=400)
                    if action=='drive':
                        if set(payload)!={'direction','sequence','expires_at_ms'} or type(payload['sequence']) is not int or payload['sequence']<=row['_sequence']:
                            raise BrokerError('fleet_sequence','Old or invalid movement input.',status=409)
                        expires=payload['expires_at_ms']
                        if type(expires) not in (int,float) or not math.isfinite(expires) or not 0<expires-self.wall()*1000<=INPUT_TTL_MS:
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

    def _physical_destination(self,identity,owner,request,kind,text,requested,scene,anchor,estimate,tracking,connection,motion):
        # Bounded pure planning must not own the fleet/Stop lock.
        from twinpulse_core.physical_object_navigation import route_from_plan,transform_pose
        from twinpulse_core.sim_fleet_navigation import approach_plan
        if not scene or not 0<=self.clock()-scene['produced_at']<.5:
            raise BrokerError('physical_navigation_scene_stale','Display the current Twin before requesting a destination.',status=409)
        binding=scene['binding'];geometry=scene['geometry']
        if binding!=tuple(requested.get(k) for k in ('engine_session_id','stage_epoch','scene_revision')):
            raise BrokerError('physical_navigation_context_changed','Current Twin context differs from the captured map. Submit a new command.',status=409)
        if (not connection or not estimate or not tracking or self.physical_navigation_reviews.get(identity)!=(connection,estimate['visual_epoch'],tracking.get('epoch'))
                or estimate['scene_revision']!=binding[2] or not anchor
                or anchor['key']!=(self.robots[identity].get('operation_id'),connection,tracking.get('epoch'),estimate['visual_epoch'],binding)):
            raise BrokerError('physical_navigation_anchor_required','Stop, review Estimated Twin marker X/Y/yaw and place a fresh anchor with current LiDAR tracking.',status=409)
        try:
            start=transform_pose(tracking['pose'],anchor['origin'],estimate['position_m'])
            plan=approach_plan(start,kind,geometry['targets'],geometry['bounds'],geometry['obstacles'],
                observed_cells=scene.get('observed_cells'))
            route=route_from_plan(plan,dict(origin=anchor['origin'],world=estimate['position_m']),tracking,
                requested['context_id'],estimate['visual_epoch'])
        except (ValueError,KeyError,TypeError) as exc:
            raise BrokerError('physical_navigation_plan_rejected',str(exc)[:160],status=409) from None
        def current():
            latest=self.navigation_scene;row=self.robots.get(identity)
            # A frozen route is tied to a scene VERSION, not a GPU frame lease.
            # Physical collision/pose/input guards run on the robot. An Isaac
            # rendering hitch must not itself renew or revoke those controls.
            return bool(not self.closed and latest and latest['binding']==binding
                and latest['geometry']==geometry and self.broker.project_id==requested['project_id']
                and row and row.get('operation_id')==anchor['key'][0] and row.get('connection_epoch')==connection
                and row.get('project_id')==requested['project_id']
                and (row.get('display_pose') or {}).get('visual_epoch')==estimate['visual_epoch']
                and ((row.get('field') or {}).get('tracking') or {}).get('epoch')==tracking['epoch']
                and (self.physical_tracking_anchors.get(identity) or {}).get('key')==anchor['key'])
        if not current():raise BrokerError('physical_navigation_scene_changed','The Twin or anchor changed while planning. Submit a new command.',status=409)
        self.physical.navigate(identity,owner,payload=dict(kind='estimated_object_route',route=route,text=text),
            guard=current,request_id=request,connection_epoch=connection,motion_epoch=motion,request_twin_context=requested)

    def _physical_stop_all(self,owner,*,request_id=None,request_twin_context=None):
        errors=[]
        for row in self.physical.snapshot(owner).get('robots',[]):
            if row.get('owned'):
                try:self.physical.stop(row['robot_id'],owner,request_id=request_id,request_twin_context=request_twin_context)
                except BrokerError as error:errors.append(error.code)
        if errors:raise BrokerError('fleet_stop_delivery_incomplete','Stop attempted for every owned robot; some deliveries are unconfirmed: '+','.join(errors[:4]),status=409)

    def consume_display_pose(self,identity,visual_epoch):
        """A declared start is valid for one run. Save that, so an App restart (which empties the route runner's
        session-only used set) never restores it; the display_pose shape (Stop's Twin anchor) is unchanged."""
        with self.lock:
            if (self.physical_display_poses.get(identity) or {}).get('visual_epoch')==visual_epoch:
                self.consumed_display_epochs[identity]=visual_epoch;self._persist()

    def twin_imported(self):
        """Import space (adopt) makes a new Twin frame: every declared start and carried route end is void, even
        for a byte-identical file (its first revision can equal an earlier one). Robots must be placed again."""
        try:
            with self.lock:
                for identity,pose in self.physical_display_poses.items():self.consumed_display_epochs[identity]=pose['visual_epoch']
                self.physical_display_poses={};self.physical_tracking_anchors.clear();self.physical_navigation_reviews.clear()
                for row in self.robots.values():
                    if row['kind']=='physical':row['display_pose']=None
                self._persist()
        finally:  # a failed save must not leave a carried route end on the new import
            reset=getattr(self,'declared_route_reset',None)
            if reset:reset()

    def same_twin_frame(self,declared,revision):
        """The marker's Twin frame is the current one: the same revision, or one reached only through Twin edits
        of the same import (object edits keep the frame; a new import, source or units does not). Unknown is False."""
        if declared==revision:return isinstance(revision,str)
        query=getattr(self.broker,'navigation_frame_lineage',None)
        if query is None or not isinstance(declared,str) or not isinstance(revision,str):return False
        if (declared,revision) in self._frame_lineage:return True
        same=bool(query(declared,revision))
        if same:
            if len(self._frame_lineage)>=256:self._frame_lineage.clear()
            self._frame_lineage.add((declared,revision))
        return same

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
        if not isinstance(report,dict) or not {'applied_revision','robots'}<=set(report) or set(report)-{'applied_revision','robots','scene_geometry','produced_monotonic_s'} or report['applied_revision']!=binding[2] or not isinstance(report['robots'],list) or len(report['robots'])>16:
            raise BrokerError('fleet_report_shape','Invalid bounded engine report.',status=400)
        observed_context=self._twin_context(dict(kind='sim'),state)
        source_query=getattr(self.broker,'navigation_source',None)
        expected_source=source_query(binding[2]) if source_query is not None else None
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
            from twinpulse_core.sim_fleet_navigation import checked_scene_geometry
            geometry=checked_scene_geometry(report.get('scene_geometry'))
            produced=report.get('produced_monotonic_s')
            valid=bool(geometry and type(produced) in (float,int) and math.isfinite(produced) and 0<=produced<=self.clock()
                and (geometry.get('schema')!='scene-navigation-2.0' or geometry['scene_revision']==binding[2])
                and (expected_source is None or geometry.get('schema')=='scene-navigation-2.0'
                     and all(geometry.get(k)==v for k,v in expected_source.items())))
            old=self.navigation_scene;pin=self._navigation_pin
            if valid and pin and pin['binding']==binding:
                if (geometry['epoch']<pin['geometry']['epoch'] or
                        pin['geometry'].get('schema')=='scene-navigation-2.0' and geometry.get('schema')!='scene-navigation-2.0' or
                        geometry['epoch']==pin['geometry']['epoch'] and geometry!=pin['geometry']):
                    valid=False  # Reject rollback, same-epoch mutation and downgrade.
            if valid:
                # Decode only changed immutable geometry, not every heartbeat.
                from twinpulse_core.navigation_grid import decode_navigation_grid
                cells=(old.get('observed_cells') if old and old['binding']==binding and old['geometry']==geometry
                    else decode_navigation_grid(geometry['grid'],geometry['bounds']) if 'grid' in geometry else None)
                self.navigation_scene=dict(binding=binding,geometry=geometry,produced_at=produced,observed_cells=cells)
                self._navigation_pin=dict(binding=binding,geometry=geometry)
            else:self.navigation_scene=None
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
                from twinpulse_core.fleet_diagnostics import checked_work,checked_fault
                work=checked_work(work)
                fault=checked_fault(value.get('runtime_fault'))
                if fault and fault['motion_epoch']!=value.get('motion_epoch'):fault=None
                intent=row['_intent'];reported_input=value.get('intent_sequence')
                superseded=(reason=='INPUT_STALE' and timing is not None and timing['elapsed_s']<.5 and value.get('motion_epoch')==row['motion_epoch']
                    and intent is not None and type(reported_input) is int and reported_input>0
                    and reported_input<intent['sequence'] and self.wall()*1000<intent['expires_at_ms'])
                if superseded:
                    self._event(row,'superseded_input_report',reason=reason,reported_input_sequence=reported_input,
                        current_input_sequence=intent['sequence'],observed_twin_context=observed_context)
                if not superseded and (reason in {'OBSTACLE_STOP','INPUT_STALE','ISAAC_UPDATE_STALLED','ISAAC_TRANSPORT_STALE','TASK_COMPLETED','TASK_TIMEOUT','MOVEMENT_STALLED','NAVIGATION_ARRIVED'} or isinstance(reason,str) and reason.startswith('NAVIGATION_')) and value.get('motion_epoch')==row['motion_epoch']:
                    self._event(row,'motion_result',reason=reason,position_m=pose,command_id=value.get('task_id'),
                        runtime_timing=timing,runtime_work=work,runtime_fault=fault,observed_twin_context=observed_context,request_twin_context=deepcopy(self.command_contexts.get(value.get('task_id'))))
                    self._pause(row,reason);self._save_operation(row)
                if self.clock()-row['_recorded_at']>=.5:
                    self._event(row,'engine_observation',position_m=pose,source='isaac_usd_kinematic',reason=reason,
                        scan=deepcopy(row['scan']),runtime_timing=timing,runtime_startup=deepcopy(row['sim_readiness']),runtime_work=work,runtime_fault=fault,telemetry_sequence=sequence,applied_motion_epoch=value.get('motion_epoch'),observed_twin_context=observed_context)
                    row['_recorded_at']=self.clock()
                self.operations[row['operation_id']]['manifest']['last_engine_binding']=dict(engine_session_id=engine_id,
                    stage_epoch=stage_epoch,scene_revision=binding[2],telemetry_sequence=sequence)
                self.revision+=1  # Fence older GET/POST snapshots, including task-result epochs.
            desired=[]
            for row in self.robots.values():
                spatial=getattr(self.task_service,'spatial_review',None)
                registration=getattr(spatial,'registration',None)
                if row['kind']=='physical' and registration and registration['robot_id']==row['robot_id']:
                    # Session-only display uses the same native transform as
                    # common tasks, never the legacy ICP/operator anchor. Do
                    # not duplicate the review ghost or persist this authority.
                    display=spatial.visual_pose(row,binding[2])
                    if display and len(desired)<16:
                        if row.get('field') is not None:row['field']['twin_tracking']=dict(status='ESTIMATED',position_m=display['position_m'],
                            source=display['source'],aligned=False,accuracy='UNQUALIFIED',scene_revision=binding[2])
                        desired.append(dict(robot_id=row['robot_id'],label=row['label'],visual_only=True,
                            connection_epoch=display['visual_epoch'],motion_epoch=display['visual_epoch'],position_m=display['position_m'],
                            intent=None,task=None,lidar=False,control_state='UNPREPARED'))
                    continue
                if row['kind']=='sim' and row['_connected']:
                    desired.append(dict(robot_id=row['robot_id'],label=row['label'],connection_epoch=row['connection_epoch'],
                        motion_epoch=row['motion_epoch'],position_m=row['_spawn'],intent=deepcopy(row['_intent']),task=deepcopy(row['_task']),selected=row['robot_id']==self.focused,
                        lidar=row['lidar_state'] in {'STARTING','STREAMING'},control_state=row['control_state']))
                elif row['kind']=='physical' and len(desired)<16 and row.get('display_pose') is not None:
                    pose=row['display_pose']
                    route=getattr(self,'route_overlay',None)
                    if (self.same_twin_frame(pose['scene_revision'],binding[2]) and route and route['robot_id']==row['robot_id'] and route.get('pose')
                            and route.get('state')=='RUNNING'  # a finished route must not freeze the ghost at its last pose
                            and route['scene_revision']==binding[2] and route['connection_epoch']==row.get('connection_epoch')):
                        # Declared start + wheel odometry from the route runner: display only, never localization.
                        if row.get('field') is not None:row['field']['twin_tracking']=dict(status='ESTIMATED',position_m=list(route['pose']),
                            source='declared_start_wheel_odometry',aligned=False,accuracy='UNQUALIFIED',scene_revision=binding[2])
                        desired.append(dict(robot_id=row['robot_id'],label=row['label'],visual_only=True,
                            connection_epoch=pose['visual_epoch'],motion_epoch=pose['visual_epoch'],
                            position_m=list(route['pose']),intent=None,task=None,lidar=False,control_state='UNPREPARED'))
                    elif self.same_twin_frame(pose['scene_revision'],binding[2]):
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
            route=getattr(self,'route_overlay',None)
            route=self._route_payload(dict(route)) if route and route['scene_revision']==binding[2] else None
            layer=lidar_layer_payload(self.lidar_layer,binding[2]);sent=getattr(self,'_layer_sent',None)
            if layer and sent==(layer['scene_revision'],layer['revision']):layer=dict(revision=layer['revision'],unchanged=True)  # Kit keeps its copy
            elif layer:self._layer_sent=(layer['scene_revision'],layer['revision'])
            else:self._layer_sent=None
            return dict(fleet=dict(project_id=self.broker.project_id,applied_revision=binding[2],robots=desired,route=route,lidar_layer=layer,sim_obstacles=deepcopy(self.sim_obstacles)))

    def _route_payload(self,route):
        """Full overlay on change and at least every 2 s; otherwise a stub Kit ignores (trace up to 800 points at ~20 Hz)."""
        key=(route['plan_id'],route.get('revision'));now=self.clock();sent=getattr(self,'_route_sent',None)
        if sent and sent[0]==key and 0<=now-sent[1]<2.:
            return dict(plan_id=route['plan_id'],revision=route.get('revision'),scene_revision=route['scene_revision'],unchanged=True)
        self._route_sent=(key,now)
        return route

    def operation(self,identity,owner=None):
        if not _id(identity):raise BrokerError('fleet_operation_invalid','Invalid operation ID.',status=400)
        with self.lock:
            # Reading/exporting a log must not enqueue another full disk
            # snapshot. Append-only events and explicit lifecycle saves own
            # persistence; the returned capture is independently hashed below.
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
        if self.task_service:self.task_service.close()
        with self.lock:
            already=self.closed
            if not already:self.closed=True
        if already:
            self.close_done.wait()
            return self.persistence_receipt
        cancel_route=getattr(self,'declared_route_cancel',None)
        if cancel_route is not None:
            try:cancel_route()  # a running declared route must not send another step to a closing fleet
            except Exception:pass
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
            # The writer thread must still end, or the next project open waits on it forever.
            try:self.snapshot_writer.close()
            except Exception:pass
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
