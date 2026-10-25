# SPDX-License-Identifier: Apache-2.0
"""Run a declared-start model plan as ordinary finite robot commands.

Each step is sent exactly like a typed finite command (same parser, admission,
robot-side guards, Stop). No task token, no pinned map: the plan is model-only
and never authorizes motion. A non-COMPLETED step, any Stop/pause/new motion,
an epoch change between steps or a timeout halts the run; the next step is
never sent after one of those.
"""
import json
import math
from pathlib import Path
import threading
import time
from uuid import uuid4

from twinpulse_core.declared_route import plan_survey, compile_moves, move_text, plan_pose, next_move, heading_move, replan_legs
from .command_broker import BrokerError

DONE_REASONS={'TASK_COMPLETED','TASK_WHEEL_ODOM_TARGET_REACHED'}
TERMINAL={'COMPLETED','FAILED','CANCELLED','ARRIVED','ESTIMATE_REACHED'}
ACK_TIMEOUT_S=10.
PHYSICAL_SETTLE_S=1.5
MAX_RECOVERIES=2
RECOVERY_BACKOFF_M=.25
RECOVERY_KEEPOUT_M=.05  # point obstacle; the route clearance supplies the berth


def step_timeout_s(step):
    # Physical field speed is 0.03 m/s; allow arming/watch and robot-side settling.
    return (step['amount']/.025 if step['direction']=='forward' else step['amount']/.15)+20.


def _pose3(value):
    return (isinstance(value,list) and len(value)==3
        and all(type(v) in (int,float) and math.isfinite(v) for v in value))


class DeclaredRouteRunner:
    def __init__(self,fleet,root,*,clock=time.monotonic,sleep=time.sleep,poll_s=.25,on_result=None):
        self.fleet,self.root,self.clock,self.sleep,self.poll_s=fleet,Path(root),clock,sleep,poll_s
        self.on_result=on_result;self.lock=threading.Lock();self.current=None;self.cancelled=threading.Event()
        # Any Stop/drive/focus/disconnect through the fleet (UI button, chat, API) cancels the route.
        fleet.declared_route_cancel=self.cancel

    def active(self):
        with self.lock:return bool(self.current and self.current['state']=='RUNNING')

    def cancel(self):self.cancelled.set()

    def _row(self,robot_id):
        return next((r for r in self.fleet.snapshot()['robots'] if r['robot_id']==robot_id),None)

    def _start_pose(self,row,scene):
        if row['kind']=='physical':
            declared=row.get('display_pose') or {}
            if declared.get('scene_revision')!=scene['binding'][2] or not _pose3(declared.get('position_m')):
                raise BrokerError('declared_route_start_required','Set the robot position and heading on this Twin first.',status=409)
            return list(declared['position_m']),'operator_declared_display_pose'
        start=(row.get('pose') or {}).get('position_m')
        if not _pose3(start):raise BrokerError('declared_route_pose_required','A current SIM pose is required.',status=409)
        return list(start),'sim_engine_pose'

    def plan(self,robot_id,*,budget_m=None):
        scene=self.fleet.navigation_scene
        if not scene:raise BrokerError('declared_route_scene_required','Display the imported Twin before planning a route.',status=409)
        row=self._row(robot_id)
        if row is None:raise BrokerError('declared_route_robot_unknown','Select a registered robot.',status=409)
        if row.get('control_state') not in {'READY','PAUSED'}:
            raise BrokerError('declared_route_robot_busy','Stop and prepare the robot before a route.',status=409)
        start,basis=self._start_pose(row,scene)
        try:
            plan=plan_survey(start,scene['geometry'],scene.get('observed_cells'),kind=row['kind'],budget_m=budget_m or (8. if row['kind']=='physical' else 6.))
            steps=compile_moves(start,plan['polyline'],final_yaw=start[2])
        except (ValueError,KeyError,TypeError) as exc:
            raise BrokerError('declared_route_unplannable',str(exc)[:160],status=409) from None
        return dict(plan_id=uuid4().hex,robot_id=robot_id,kind=row['kind'],start_basis=basis,
            scene_revision=scene['binding'][2],steps=[dict(s,text=move_text(s)) for s in steps],**plan)

    def start(self,plan,owner,*,context=None):
        """Run a plan the user confirmed; refuse if robot, Twin or start pose changed since."""
        with self.lock:
            if self.current and self.current['state']=='RUNNING':
                raise BrokerError('declared_route_active','A route is already running.',status=409)
            scene=self.fleet.navigation_scene;row=self._row(plan['robot_id'])
            if not scene or scene['binding'][2]!=plan['scene_revision'] or row is None:
                raise BrokerError('declared_route_changed','The Twin or robot changed; ask for the route again.',status=409)
            start,_=self._start_pose(row,scene)
            if math.dist(start[:2],plan['start'][:2])>.02 or abs(math.remainder(start[2]-plan['start'][2],math.tau))>.02:
                raise BrokerError('declared_route_changed','The robot start pose changed; ask for the route again.',status=409)
            if row.get('control_state') not in {'READY','PAUSED'}:
                raise BrokerError('declared_route_robot_busy','Stop and prepare the robot before a route.',status=409)
            self.cancelled.clear()
            self.current=dict(plan=plan,state='RUNNING',completed_steps=0,reason=None,waypoint_scans=[],
                started_at=time.time(),context=context)
            self._save()
        threading.Thread(target=self._run,args=(owner,),daemon=True,name='DeclaredRoute').start()
        return plan

    def _save(self):
        folder=self.root/'declared-routes';folder.mkdir(parents=True,exist_ok=True)
        path=folder/(self.current['plan']['plan_id']+'.json')
        tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(self.current,indent=1,sort_keys=True),encoding='utf-8');tmp.replace(path)

    def _finish(self,state,reason):
        with self.lock:
            if self.current['state']!='RUNNING':return
            self.current.update(state=state,reason=reason,finished_at=time.time());self._save()
            result=json.loads(json.dumps(self.current))
        if self.on_result:
            try:self.on_result(result)
            except Exception:pass  # the saved record is authoritative; never re-enter _finish

    def _stop(self,robot_id,owner,epochs):
        try:
            self.fleet.action(dict(action='stop',request_id=uuid4().hex,robot_id=robot_id,
                connection_epoch=epochs[0],motion_epoch=epochs[1],payload={}),owner)
            return 'STOP_SENT'
        except BrokerError as exc:return 'STOP_REJECTED:'+exc.code

    def _measured(self,row):
        """Wheel-odometry pose (physical rows) or engine pose (SIM rows) as x, y, yaw."""
        pose=(row or {}).get('pose') or {}
        if all(isinstance(pose.get(k),(int,float)) for k in ('x','y','yaw')):return [pose['x'],pose['y'],pose['yaw']]
        value=pose.get('position_m')
        if not _pose3(value):raise ValueError('ROUTE_POSE_UNAVAILABLE')
        return list(value)

    def _step(self,owner,robot_id,step,previous):
        """Send one finite command exactly like a typed one; return (outcome, row, epochs)."""
        row=self._row(robot_id)
        if row is None:return ('FAILED','ROBOT_REMOVED'),None,(None,None)
        epochs=(row.get('connection_epoch'),row.get('motion_epoch'))
        # Continuity: after a step the robot must still be exactly where its
        # COMPLETED left it. Physical rows report the completion's own
        # zero/readback as OPERATOR_STOP, so only SIM rows can use the reason;
        # epochs are authoritative for both (any Stop/Prepare/drive issues a new one).
        if previous is not None and (epochs!=previous or row['kind']!='physical' and row.get('reason') not in DONE_REASONS):
            return ('STOPPED','ROBOT_CHANGED_BETWEEN_STEPS:'+str(row.get('reason'))),row,epochs
        if previous is not None and 'applied_motion_epoch' in row:
            until=self.clock()+10.
            while row.get('applied_motion_epoch')!=row.get('motion_epoch'):
                if self.cancelled.is_set() or self.clock()>until:return ('STOPPED','PREVIOUS_STOP_NOT_APPLIED'),row,epochs
                self.sleep(self.poll_s);row=self._row(robot_id) or {}
                if (row.get('connection_epoch'),row.get('motion_epoch'))!=previous:
                    return ('STOPPED','ROBOT_CHANGED_BETWEEN_STEPS:'+str(row.get('reason'))),row,epochs
        if row.get('control_state') not in {'READY','PAUSED'}:return ('STOPPED','ROBOT_NOT_READY:'+str(row.get('control_state'))),row,epochs
        if self.cancelled.is_set():return ('CANCELLED','ROUTE_CANCELLED'),row,epochs
        request=uuid4().hex;text=move_text(step)
        try:self.fleet.action(dict(action='command',request_id=request,robot_id=robot_id,connection_epoch=epochs[0],
                motion_epoch=epochs[1],payload=dict(text=text)),owner)
        except BrokerError as exc:return ('FAILED','STEP_REJECTED:'+exc.code),row,epochs
        with self.lock:self.current.setdefault('sent',[]).append(text);self._save()
        sent=self.clock();deadline=sent+step_timeout_s(step);acknowledged=False
        while True:
            self.sleep(self.poll_s)
            row=self._row(robot_id);command=(row or {}).get('command') or {}
            if row:epochs=(row.get('connection_epoch'),row.get('motion_epoch'))
            if command.get('request_id')==request:acknowledged=True
            if command.get('request_id')==request and command.get('state') in TERMINAL:break
            # 2026-10-25: a step sent the instant the previous one completed was
            # never acknowledged. Fail fast; never resend automatically.
            unacknowledged=not acknowledged and self.clock()-sent>ACK_TIMEOUT_S
            if self.cancelled.is_set() or self.clock()>deadline or unacknowledged:
                cancelled=self.cancelled.is_set()  # before our own Stop trips the cancel hook
                stop=self._stop(robot_id,owner,epochs)
                return ('CANCELLED' if cancelled else 'FAILED',
                    ('ROUTE_CANCELLED' if cancelled else 'STEP_NOT_ACKNOWLEDGED' if unacknowledged else 'STEP_TIMEOUT')+':'+stop),row,epochs
        if command['state']!='COMPLETED':return ('STEP_'+command['state'],str(command.get('reason'))),row,epochs
        if row.get('kind')=='physical':self.sleep(PHYSICAL_SETTLE_S)  # robot finishes its zero/readback
        return ('COMPLETED',None),self._row(robot_id) or row,epochs

    def _run(self,owner):
        """Odometry-closed waypoint following: every step is re-aimed from the measured pose.

        The step list on the card is the nominal preview. On a robot-side
        proximity stop during a forward step the robot backs off 15 cm and the
        rest of the route is re-planned around a keepout at the stop (at most
        MAX_RECOVERIES times). All other failures stop the route.
        """
        plan=self.current['plan'];robot_id=plan['robot_id'];previous=None;epochs=(None,None)
        scene=self.fleet.navigation_scene or {}
        try:
            row=self._row(robot_id);origin=self._measured(row)
            start=plan['start'];goals=[*plan['waypoints'],start[:2]]
            queue=[(list(q),i) for i,leg in enumerate(plan.get('legs') or [plan['polyline']]) for q in leg]
            reached=0;forward=0.;budget=plan['length_m']*1.5+1.;discs=[];recoveries=0
            while True:
                pose=plan_pose(start,origin,self._measured(row));step=None
                while queue and step is None:
                    step=next_move(pose,queue[0][0])
                    if step is None:
                        point,leg=queue.pop(0)
                        if not queue or queue[0][1]!=leg:
                            reached=leg+1;scan=(row or {}).get('scan') or {}
                            with self.lock:
                                self.current['waypoint_scans'].append(dict(stop=leg,pose=[round(v,4) for v in pose],
                                    scan_sha256=scan.get('raw_sha256') or scan.get('sha256'),frame_sequence=scan.get('frame_sequence')))
                                self._save()
                if step is None:
                    step=heading_move(pose,start[2])
                    if step is None:break
                if step['direction']=='forward':
                    forward+=step['amount']
                    if forward>budget:return self._finish('STOPPED','ROUTE_DISTANCE_BUDGET_EXCEEDED')
                outcome,row,epochs=self._step(owner,robot_id,step,previous)
                if (outcome==('STEP_FAILED','FIELD_PROXIMITY_10CM') and step['direction']=='forward'
                        and recoveries<MAX_RECOVERIES):
                    recoveries+=1
                    blocked=plan_pose(start,origin,self._measured(row))
                    discs.append((blocked[0]+.25*math.cos(blocked[2]),blocked[1]+.25*math.sin(blocked[2]),RECOVERY_KEEPOUT_M))  # proximity fires within ~.23 m
                    with self.lock:
                        self.current.setdefault('recoveries',[]).append(dict(at=[round(v,4) for v in blocked],keepout_m=RECOVERY_KEEPOUT_M))
                        self._save()
                    outcome,row,epochs=self._step(owner,robot_id,dict(direction='backward',amount=RECOVERY_BACKOFF_M),None)
                    if outcome[0]!='COMPLETED':return self._finish('STOPPED','RECOVERY_'+outcome[0]+':'+str(outcome[1]))
                    previous=epochs;pose=plan_pose(start,origin,self._measured(row))
                    # A stop that sits inside the new keepout is skipped; the start is always kept.
                    remaining=[g for g in goals[reached:-1] if all(math.dist(g[:2],d[:2])>d[2]+.5 for d in discs)]+[goals[-1]]
                    try:legs=replan_legs(pose,remaining,scene.get('geometry') or {},scene.get('observed_cells'),kind=plan['kind'],discs=discs)
                    except (ValueError,KeyError,TypeError) as exc:return self._finish('STOPPED','RECOVERY_REPLAN_FAILED:'+str(exc)[:80])
                    goals=goals[:reached]+remaining
                    queue=[(list(q),reached+i) for i,leg in enumerate(legs) for q in leg]
                    continue
                if outcome[0]!='COMPLETED':
                    if outcome[0].startswith('STEP_'):return self._finish('STOPPED',outcome[0]+':'+str(outcome[1]))
                    return self._finish(outcome[0],str(outcome[1]))
                previous=epochs
                with self.lock:self.current['completed_steps']+=1;self._save()
            with self.lock:self.current['end_pose_odometry']=[round(v,4) for v in plan_pose(start,origin,self._measured(row))]
            self._finish('COMPLETED','ALL_STOPS_AND_RETURN_COMPLETED')
        except Exception as exc:  # never leave a RUNNING record or an unstopped step behind
            stop=self._stop(robot_id,owner,epochs)
            self._finish('FAILED','RUNNER_ERROR:'+type(exc).__name__+':'+stop)
