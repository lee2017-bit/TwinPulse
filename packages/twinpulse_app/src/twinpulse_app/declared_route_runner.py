# SPDX-License-Identifier: Apache-2.0
"""Run a declared-start model plan as ordinary finite robot commands.

Each step is sent exactly like a typed finite command (same parser, admission,
robot-side guards, Stop). No task token, no pinned map: the plan is model-only
and never authorizes motion. A non-COMPLETED step, an external Stop/pause or a
timeout halts the run; the next step is never sent after one of those.
"""
import json
import math
from pathlib import Path
import threading
import time
from uuid import uuid4

from twinpulse_core.declared_route import plan_survey, compile_moves, move_text, SCOPE
from .command_broker import BrokerError

DONE_REASONS={None,'TASK_COMPLETED','TASK_WHEEL_ODOM_TARGET_REACHED'}
TERMINAL={'COMPLETED','FAILED','CANCELLED','ARRIVED','ESTIMATE_REACHED'}


def step_timeout_s(step):
    # Physical field speed is 0.03 m/s; allow arming/watch and robot-side settling.
    return (step['amount']/.025 if step['direction']=='forward' else step['amount']/.15)+20.


class DeclaredRouteRunner:
    def __init__(self,fleet,root,*,clock=time.monotonic,sleep=time.sleep,poll_s=.25,on_result=None):
        self.fleet,self.root,self.clock,self.sleep,self.poll_s=fleet,Path(root),clock,sleep,poll_s
        self.on_result=on_result;self.lock=threading.Lock();self.current=None;self.cancelled=threading.Event()

    def active(self):
        with self.lock:return bool(self.current and self.current['state']=='RUNNING')

    def cancel(self):self.cancelled.set()

    def _row(self,robot_id):
        return next((r for r in self.fleet.snapshot()['robots'] if r['robot_id']==robot_id),None)

    def plan(self,robot_id,*,budget_m=6.):
        scene=self.fleet.navigation_scene
        if not scene:raise BrokerError('declared_route_scene_required','Display the imported Twin before planning a route.',status=409)
        row=self._row(robot_id)
        if row is None:raise BrokerError('declared_route_robot_unknown','Select a registered robot.',status=409)
        if row.get('control_state') not in {'READY','PAUSED'}:
            raise BrokerError('declared_route_robot_busy','Stop and prepare the robot before a route.',status=409)
        if row['kind']=='physical':
            declared=row.get('display_pose')
            if not declared or declared.get('scene_revision')!=scene['binding'][2]:
                raise BrokerError('declared_route_start_required','Set the robot position and heading on this Twin first.',status=409)
            start=list(declared['position_m']);basis='operator_declared_display_pose'
        else:
            start=list((row.get('pose') or {}).get('position_m') or []);basis='sim_engine_pose'
            if len(start)!=3:raise BrokerError('declared_route_pose_required','A current SIM pose is required.',status=409)
        try:plan=plan_survey(start,scene['geometry'],scene.get('observed_cells'),kind=row['kind'],budget_m=budget_m)
        except ValueError as exc:raise BrokerError('declared_route_unplannable',str(exc)[:160],status=409) from None
        steps=compile_moves(start,plan['polyline'],final_yaw=start[2])
        return dict(plan_id=uuid4().hex,robot_id=robot_id,kind=row['kind'],start_basis=basis,
            scene_revision=scene['binding'][2],steps=[dict(s,text=move_text(s)) for s in steps],**plan)

    def start(self,robot_id,owner,*,budget_m=6.):
        with self.lock:
            if self.current and self.current['state']=='RUNNING':
                raise BrokerError('declared_route_active','A route is already running.',status=409)
            plan=self.plan(robot_id,budget_m=budget_m)
            self.cancelled.clear()
            self.current=dict(plan=plan,state='RUNNING',completed_steps=0,reason=None,waypoint_scans=[],started_at=time.time())
            self._save()
        threading.Thread(target=self._run,args=(owner,),daemon=True,name='DeclaredRoute').start()
        return plan

    def _save(self):
        folder=self.root/'declared-routes';folder.mkdir(parents=True,exist_ok=True)
        path=folder/(self.current['plan']['plan_id']+'.json')
        tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(self.current,indent=1,sort_keys=True),encoding='utf-8');tmp.replace(path)

    def _finish(self,state,reason):
        with self.lock:
            self.current.update(state=state,reason=reason,finished_at=time.time());self._save()
            result=json.loads(json.dumps(self.current))
        if self.on_result:self.on_result(result)

    def _run(self,owner):
        plan=self.current['plan'];robot_id=plan['robot_id']
        # Waypoint k is reached after the forward legs that end at polyline vertex waypoints[k].
        try:
            for index,step in enumerate(plan['steps']):
                if self.cancelled.is_set():return self._finish('CANCELLED','ROUTE_CANCELLED')
                row=self._row(robot_id)
                if row is None:return self._finish('FAILED','ROBOT_REMOVED')
                if row.get('reason') not in DONE_REASONS or row.get('control_state') not in {'READY','PAUSED'}:
                    return self._finish('STOPPED','ROBOT_NOT_READY:'+str(row.get('reason') or row.get('control_state')))
                request=uuid4().hex
                body=dict(action='command',request_id=request,robot_id=robot_id,connection_epoch=row['connection_epoch'],
                    motion_epoch=row['motion_epoch'],payload=dict(text=step['text']))
                try:self.fleet.action(body,owner)
                except BrokerError as exc:return self._finish('FAILED','STEP_REJECTED:'+exc.code)
                deadline=self.clock()+step_timeout_s(step)
                while True:
                    self.sleep(self.poll_s)
                    row=self._row(robot_id);command=(row or {}).get('command') or {}
                    if command.get('request_id')==request and command.get('state') in TERMINAL:break
                    if self.cancelled.is_set() or self.clock()>deadline:
                        try:self.fleet.action(dict(action='stop',request_id=uuid4().hex,robot_id=robot_id,
                            connection_epoch=(row or {}).get('connection_epoch'),motion_epoch=(row or {}).get('motion_epoch'),payload={}),owner)
                        except BrokerError:pass
                        return self._finish('CANCELLED' if self.cancelled.is_set() else 'FAILED',
                            'ROUTE_CANCELLED' if self.cancelled.is_set() else 'STEP_TIMEOUT')
                if command['state']!='COMPLETED':
                    return self._finish('STOPPED','STEP_'+command['state']+':'+str(command.get('reason')))
                with self.lock:
                    self.current['completed_steps']=index+1
                    scan=(row or {}).get('scan') or {}
                    if step['direction']=='forward' and row and row.get('lidar_state')=='STREAMING':
                        self.current['waypoint_scans'].append(dict(step=index,scan_sha256=scan.get('raw_sha256') or scan.get('sha256'),
                            frame_sequence=scan.get('frame_sequence')))
                    self._save()
            self._finish('COMPLETED','ALL_STEPS_COMPLETED')
        except Exception as exc:  # never leave a RUNNING record behind
            self._finish('FAILED','RUNNER_ERROR:'+type(exc).__name__)
