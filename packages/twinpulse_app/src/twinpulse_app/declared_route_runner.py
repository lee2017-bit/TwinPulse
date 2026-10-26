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

from twinpulse_core.declared_route import (plan_survey, plan_through, compile_moves, move_text, plan_pose, next_move, heading_move, replan_legs,
    unexplained_scan_discs, scan_world_points, cluster_candidates, HEADING_TOLERANCE_RAD, REAIM_TOLERANCE_RAD)
from .command_broker import BrokerError

DONE_REASONS={'TASK_COMPLETED','TASK_WHEEL_ODOM_TARGET_REACHED'}
TERMINAL={'COMPLETED','FAILED','CANCELLED','ARRIVED','ESTIMATE_REACHED'}
ACK_TIMEOUT_S=10.
PHYSICAL_SETTLE_S=1.5
MAX_RECOVERIES=2
RECOVERY_BACKOFF_M=.25
RECOVERY_KEEPOUT_M=.25  # leaves/baskets are wider than the proximity cone (review 2026-10-25)
MAX_STEPS_FACTOR=3
OTHER_ROBOT_KEEPOUT_M=.35  # SIM body radius + engine stop skin, see twinpulse_fleet_runtime.integrate_motion
TRACE_SPACING_M=.04
MAX_TRACE_POINTS=800
MAX_DRIVE_POINTS=2500  # display-only during-drive LiDAR returns kept per route
OVERLAY_LABEL='DECLARED_START_PLUS_WHEEL_ODOMETRY_NOT_LOCALIZED'


def step_timeout_s(step):
    # Physical field speed is 0.03 m/s; allow arming/watch and robot-side settling.
    return (step['amount']/.025 if step['direction']=='forward' else step['amount']/.15)+20.


def _pose3(value):
    return (isinstance(value,list) and len(value)==3
        and all(type(v) in (int,float) and math.isfinite(v) for v in value))


class DeclaredRouteRunner:
    def __init__(self,fleet,root,*,clock=time.monotonic,sleep=time.sleep,poll_s=.25,on_result=None,on_progress=None):
        self.fleet,self.root,self.clock,self.sleep,self.poll_s=fleet,Path(root),clock,sleep,poll_s
        self.on_result,self.on_progress=on_result,on_progress;self.lock=threading.Lock();self.current=None;self.cancelled=threading.Event()
        # Any Stop/drive/focus/disconnect through the fleet (UI button, chat, API) cancels the route.
        fleet.declared_route_cancel=self.cancel
        self.used_declarations=set()  # a declared start is valid for one run only
        # Display-only Twin overlay (route, odometry trace, per-stop LiDAR, candidates).
        # Replaced as a whole on each change so the fleet can read it without our lock.
        self.anchor=None;fleet.route_overlay=None

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
            if declared.get('visual_epoch') in self.used_declarations:
                raise BrokerError('declared_route_start_required','The robot has moved since this position was set. Set its position and heading on the Twin again.',status=409)
            return list(declared['position_m']),'operator_declared_display_pose'
        start=(row.get('pose') or {}).get('position_m')
        if not _pose3(start):raise BrokerError('declared_route_pose_required','A current SIM pose is required.',status=409)
        return list(start),'sim_engine_pose'

    def plan(self,robot_id,*,budget_m=None,stops=None):
        scene=self.fleet.navigation_scene
        if not scene:raise BrokerError('declared_route_scene_required','Display the imported Twin before planning a route.',status=409)
        row=self._row(robot_id)
        if row is None:raise BrokerError('declared_route_robot_unknown','Select a registered robot.',status=409)
        if row.get('control_state') not in {'READY','PAUSED'}:
            raise BrokerError('declared_route_robot_busy','Stop and prepare the robot before a route.',status=409)
        if row['kind']=='physical' and not (row.get('capabilities') or {}).get('drive',True):
            # 2026-10-26: Run route before Arm + Bootstrap stop produced an unacknowledged first step.
            blockers=((row.get('field') or {}).get('blockers') or [])
            raise BrokerError('declared_route_field_not_ready','The physical robot cannot drive yet: '
                +(', '.join(blockers) if blockers else 'field session not ready')+'. In the robot card open Physical setup, confirm supervision and Arm, then run the Bootstrap stop trial, then ask again.',status=409)
        start,basis=self._start_pose(row,scene)
        # SIM: other connected SIM robots stand on the same floor and the engine
        # stops for them, so the plan keeps a berth around each (2026-10-26 sim14/15).
        robot_discs=[(r['pose']['position_m'][0],r['pose']['position_m'][1],OTHER_ROBOT_KEEPOUT_M)
            for r in self.fleet.snapshot()['robots'] if row['kind']=='sim' and r['robot_id']!=robot_id and r.get('kind')=='sim'
            and r.get('connection_state')=='CONNECTED' and _pose3((r.get('pose') or {}).get('position_m'))]
        # Physical: one stationary LiDAR ring at the declared start adds returns
        # the scanned model cannot explain (leaves, fan base, basket) as keepouts.
        scan_review=dict(used=False,discs=[],reason='NOT_PHYSICAL_OR_NO_SCAN')
        points=((row.get('scan') or {}).get('points') or []) if row['kind']=='physical' and row.get('lidar_state')=='STREAMING' else []
        try:
            if points:  # a malformed native row must not become a 500
                scan_review=unexplained_scan_discs(start,points,scene.get('observed_cells'))
                scan_review.update(stream_id=(row.get('scan') or {}).get('stream_id'),frame_sequence=(row.get('scan') or {}).get('frame_sequence'),points=len(points))
            if stops:plan=plan_through(start,stops,scene['geometry'],scene.get('observed_cells'),kind=row['kind'],discs=[*scan_review['discs'],*robot_discs])
            else:plan=plan_survey(start,scene['geometry'],scene.get('observed_cells'),kind=row['kind'],
                budget_m=budget_m or (8. if row['kind']=='physical' else 6.),discs=[*scan_review['discs'],*robot_discs])
            steps=compile_moves(start,plan['polyline'],final_yaw=start[2])
        except (ValueError,KeyError,TypeError) as exc:
            raise BrokerError('declared_route_unplannable',str(exc)[:160],status=409) from None
        return dict(plan_id=uuid4().hex,robot_id=robot_id,kind=row['kind'],start_basis=basis,
            scan_keepouts={k:v for k,v in scan_review.items() if k!='discs'},other_sim_robots=len(robot_discs),
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
            if row['kind']=='physical':self.used_declarations.add((row.get('display_pose') or {}).get('visual_epoch'))
            self.current=dict(plan=plan,state='RUNNING',completed_steps=0,reason=None,waypoint_scans=[],
                reached_stops=[],skipped_stops=[],started_at=time.time(),context=context)
            # 2026-10-26 physical run: the start ring saw the box (3 keepouts) but the stop ring gave
            # only 2 returns, so no candidate reached the finish card. Start-scan returns count too.
            seed=[list(d) for d in plan.get('keepouts') or []] if plan['kind']=='physical' and (plan.get('scan_keepouts') or {}).get('used') else []
            if seed:self.current['_unexplained']=[seed]
            try:self._save()
            except OSError as exc:
                # 2026-10-25: a full disk here left a phantom RUNNING route that
                # refused every later route until the App restarted.
                self.current=None
                raise BrokerError('declared_route_record_failed','The route record could not be saved (%s). Free disk space and ask for the route again; nothing moved.'%type(exc).__name__,status=507) from None
            self.anchor=None
            self.fleet.route_overlay=dict(plan_id=plan['plan_id'],robot_id=plan['robot_id'],kind=plan['kind'],
                scene_revision=plan['scene_revision'],connection_epoch=row.get('connection_epoch'),label=OVERLAY_LABEL,
                state='RUNNING',reason=None,start=[round(v,4) for v in plan['start']],waypoints=[[round(v,4) for v in w[:2]] for w in plan['waypoints']],
                polyline=[[round(v,4) for v in plan['start'][:2]]]+[[round(v,4) for v in p[:2]] for p in plan['polyline']],
                reached=0,reached_stops=[],skipped_stops=[],completed_steps=0,planned_steps=len(plan['steps']),current_step=None,
                recoveries=0,started_at=self.current['started_at'],finished_at=None,revision=0,pose=None,trace=[],scans=[],
                candidates=cluster_candidates(seed) if seed else [])
        threading.Thread(target=self._run,args=(owner,),daemon=True,name='DeclaredRoute').start()
        return plan

    def _save(self):
        folder=self.root/'declared-routes';folder.mkdir(parents=True,exist_ok=True)
        path=folder/(self.current['plan']['plan_id']+'.json')
        tmp=path.with_suffix('.tmp')
        try:tmp.write_text(json.dumps(self.current,indent=1,sort_keys=True),encoding='utf-8');tmp.replace(path)
        except OSError:
            try:tmp.unlink()
            except OSError:pass
            raise

    def _overlay(self,**changes):
        overlay=self.fleet.route_overlay
        if overlay and self.current and overlay['plan_id']==self.current['plan']['plan_id']:
            self.fleet.route_overlay={**overlay,**changes,'revision':overlay.get('revision',0)+1}

    def _progress(self,event,**fields):
        """Display-only progress for chat/UI; never affects motion."""
        if not self.on_progress or not self.current:return
        plan=self.current['plan']
        try:self.on_progress(dict(event=event,plan_id=plan['plan_id'],robot_id=plan['robot_id'],total_stops=len(plan['waypoints']),
            completed_steps=self.current['completed_steps'],context=self.current.get('context'),**fields))
        except Exception:pass

    def _track(self,row):
        """Move the Twin ghost along the odometry pose in the plan frame (display only)."""
        if self.anchor is None or not row:return
        try:pose=plan_pose(*self.anchor,self._measured(row))
        except ValueError:return
        overlay=self.fleet.route_overlay or {};trace=overlay.get('trace') or []
        pose=[round(v,4) for v in pose]
        if not trace or math.dist(trace[-1],pose[:2])>=TRACE_SPACING_M:trace=(trace+[pose[:2]])[-MAX_TRACE_POINTS:]
        # Live ring at the odometry pose so the Twin shows what the robot sees now (not registration).
        points=(row.get('scan') or {}).get('points') or []
        sign=((self.current or {}).get('plan') or {}).get('scan_keepouts',{}).get('lateral_sign') or 1
        live=scan_world_points(pose,points,sign,max_points=180) if points and row.get('lidar_state')=='STREAMING' else []
        # During-drive returns are kept as a display layer (odometry smears them; decisions use stop scans only).
        drive=overlay.get('drive_scan') or []
        if live:
            seen={(round(p[0]/.1),round(p[1]/.1)) for p in drive};fresh=[]
            for p in live:
                key=(round(p[0]/.1),round(p[1]/.1))
                if key not in seen:seen.add(key);fresh.append(p)
            if fresh:drive=(drive+fresh)[-MAX_DRIVE_POINTS:]
        self._overlay(pose=pose,trace=trace,live_scan=live,drive_scan=drive)

    def _observe_stop(self,stop,pose,row):
        """Project this stop's LiDAR ring onto the Twin and collect returns the model lacks."""
        scan=(row or {}).get('scan') or {};points=scan.get('points') or []
        if not points:return dict(points_world=0,unexplained=0)
        scene=self.fleet.navigation_scene or {}
        review=unexplained_scan_discs(pose,points,scene.get('observed_cells'))
        sign=review.get('lateral_sign') if review.get('used') else (self.current['plan'].get('scan_keepouts') or {}).get('lateral_sign') or 1
        world=scan_world_points(pose,points,sign)
        overlay=self.fleet.route_overlay or {}
        scans=(overlay.get('scans') or [])+[dict(stop=stop,points=world,lateral_sign=sign,agreement=review.get('agreement'))]
        discs=[d for s in self.current.setdefault('_unexplained',[]) for d in s]+[list(d) for d in review['discs']]
        self.current['_unexplained'].append([list(d) for d in review['discs']])
        candidates=cluster_candidates(discs)
        self._overlay(scans=scans,candidates=candidates)
        return dict(points_world=len(world),unexplained=len(review['discs']),agreement=review.get('agreement'),lateral_sign=sign)

    def _finish(self,state,reason):
        with self.lock:
            if self.current['state']!='RUNNING':return
            overlay=self.fleet.route_overlay
            if overlay and overlay['plan_id']==self.current['plan']['plan_id']:
                self.current['candidates']=overlay.get('candidates') or []
                self.current['stop_scans']=overlay.get('scans') or []
                absorb=getattr(self.fleet,'absorb_route_layer',None)
                if absorb:
                    try:absorb(overlay)
                    except Exception:pass  # display layer only
            self.current.pop('_unexplained',None)
            self.current.update(state=state,reason=reason,finished_at=time.time())
            try:self._save()
            except OSError as exc:
                # Memory state is final either way; a full disk must not leave a
                # phantom RUNNING route or swallow the finish message.
                self.current['save_error']=type(exc).__name__
            self._overlay(state=state,reason=reason,completed_steps=self.current['completed_steps'],finished_at=self.current['finished_at'],current_step=None)
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
        except Exception as exc:return 'STOP_ERROR:'+type(exc).__name__  # the route must still reach _finish

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
        after_stop=previous=='AFTER_STOP'  # recovery: the proximity pause just issued its own Stop
        if after_stop:previous=None
        # Continuity: after a step the robot must still be exactly where its
        # COMPLETED left it. Physical rows report the completion's own
        # zero/readback as OPERATOR_STOP, so only SIM rows can use the reason;
        # epochs are authoritative for both (any Stop/Prepare/drive issues a new one).
        if previous is not None and (epochs!=previous or row['kind']!='physical' and row.get('reason') not in DONE_REASONS):
            return ('STOPPED','ROBOT_CHANGED_BETWEEN_STEPS:'+str(row.get('reason'))),row,epochs
        if (previous is not None or after_stop) and 'applied_motion_epoch' in row:
            previous=previous or epochs
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
        self._overlay(current_step=text,completed_steps=self.current['completed_steps'])
        sent=self.clock();deadline=sent+step_timeout_s(step);acknowledged=False
        while True:
            self.sleep(self.poll_s)
            row=self._row(robot_id);command=(row or {}).get('command') or {}
            if row:epochs=(row.get('connection_epoch'),row.get('motion_epoch'))
            self._track(row)
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
        after=self._row(robot_id) or row
        self._track(after)
        # The completion's own zero/readback may rotate the epoch during settle;
        # adopt it unless a user Stop (cancel hook) happened meanwhile.
        if after.get('kind')=='physical' and not self.cancelled.is_set() and ((after.get('command') or {}).get('request_id')==request):
            epochs=(after.get('connection_epoch'),after.get('motion_epoch'))
        return ('COMPLETED',None),after,epochs

    def _run(self,owner):
        """Odometry-closed waypoint following: every step is re-aimed from the measured pose.

        The step list on the card is the nominal preview. On a robot-side
        proximity stop during a forward step the robot backs off 25 cm and the
        rest of the route is re-planned around a keepout at the stop (at most
        MAX_RECOVERIES times). All other failures stop the route.
        """
        plan=self.current['plan'];robot_id=plan['robot_id'];previous=None;epochs=(None,None)
        scene=self.fleet.navigation_scene or {}
        try:
            row=self._row(robot_id);origin=self._measured(row)
            start=plan['start'];total=len(plan['waypoints'])
            # Goals keep their original stop number (None = the return to start) so a
            # stop skipped after a recovery never renumbers the rest (2026-10-26).
            goals=[(list(w[:2]),i) for i,w in enumerate(plan['waypoints'])]+[(list(start[:2]),None)]
            self.anchor=(start,origin);self._track(row)
            legs=plan.get('legs') or [plan['polyline']]
            queue=[(list(q),i,goals[i][1] if i<len(goals) else None) for i,leg in enumerate(legs) for q in leg]
            reached=0;forward=0.;budget=plan['length_m']*1.5+1.;discs=[tuple(d) for d in plan.get('keepouts') or []];recoveries=0
            steps_left=MAX_STEPS_FACTOR*len(plan['steps'])+10;last_turn=False
            while True:
                try:pose=plan_pose(start,origin,self._measured(row))
                except ValueError:return self._finish('STOPPED','ROUTE_POSE_UNAVAILABLE:'+self._stop(robot_id,owner,epochs))
                # Hysteresis: right after a re-aim turn accept a wider heading band, or a
                # ~2 deg overshoot per turn ping-pongs left/right forever (2026-10-26 run 4).
                tolerance=REAIM_TOLERANCE_RAD if last_turn else HEADING_TOLERANCE_RAD
                step=None
                while queue and step is None:
                    step=next_move(pose,queue[0][0],tolerance_rad=tolerance)
                    if step is None:
                        point,leg,stop_index=queue.pop(0)
                        if not queue or queue[0][1]!=leg:
                            reached+=1;scan=(row or {}).get('scan') or {}
                            record_stop=total if stop_index is None else stop_index
                            with self.lock:
                                observed=self._observe_stop(record_stop,pose,row)
                                self.current['waypoint_scans'].append(dict(stop=record_stop,is_return=stop_index is None,pose=[round(v,4) for v in pose],
                                    scan_sha256=scan.get('raw_sha256') or scan.get('sha256'),frame_sequence=scan.get('frame_sequence'),**observed))
                                if stop_index is not None:self.current['reached_stops'].append(stop_index)
                                self._save()
                            self._overlay(reached=len(self.current['reached_stops']),reached_stops=list(self.current['reached_stops']))
                            self._progress('return_reached' if stop_index is None else 'stop_reached',stop=stop_index,
                                reached=len(self.current['reached_stops']),unexplained=observed.get('unexplained',0))
                if step is None:
                    step=heading_move(pose,start[2],tolerance_rad=tolerance)
                    if step is None:break
                last_turn=step['direction'] in ('left','right')
                if step['direction']=='forward':
                    forward+=step['amount']
                    if forward>budget:return self._finish('STOPPED','ROUTE_DISTANCE_BUDGET_EXCEEDED')
                steps_left-=1
                if steps_left<0:return self._finish('STOPPED','ROUTE_STEP_BUDGET_EXCEEDED')
                outcome,row,epochs=self._step(owner,robot_id,step,previous)
                if (outcome==('STEP_FAILED','FIELD_PROXIMITY_10CM') and step['direction']=='forward'
                        and recoveries<MAX_RECOVERIES):
                    recoveries+=1
                    blocked=plan_pose(start,origin,self._measured(row))
                    discs.append((blocked[0]+.25*math.cos(blocked[2]),blocked[1]+.25*math.sin(blocked[2]),RECOVERY_KEEPOUT_M))  # proximity fires within ~.23 m
                    with self.lock:
                        self.current.setdefault('recoveries',[]).append(dict(at=[round(v,4) for v in blocked],keepout_m=RECOVERY_KEEPOUT_M))
                        self._save()
                    self._overlay(recoveries=recoveries)
                    self._progress('recovery',at=[round(v,4) for v in blocked],recoveries=recoveries)
                    if row and row.get('kind')=='physical':self.sleep(PHYSICAL_SETTLE_S)
                    # Wait for the proximity pause's Stop to be applied before backing off.
                    outcome,row,epochs=self._step(owner,robot_id,dict(direction='backward',amount=RECOVERY_BACKOFF_M),'AFTER_STOP')
                    if outcome[0]!='COMPLETED':return self._finish('STOPPED','RECOVERY_'+outcome[0]+':'+str(outcome[1]))
                    previous=epochs;pose=plan_pose(start,origin,self._measured(row))
                    # A stop that sits inside the new keepout is skipped (and reported); the start is always kept.
                    pending=goals[reached:-1]
                    remaining=[g for g in pending if all(math.dist(g[0],d[:2])>d[2]+.65 for d in discs)]+[goals[-1]]
                    skipped=[g[1] for g in pending if g not in remaining]
                    scene=self.fleet.navigation_scene or {}
                    if not scene or scene['binding'][2]!=plan['scene_revision']:return self._finish('STOPPED','RECOVERY_SCENE_CHANGED')
                    try:legs=replan_legs(pose,[g[0] for g in remaining],scene.get('geometry') or {},scene.get('observed_cells'),kind=plan['kind'],discs=discs)
                    except (ValueError,KeyError,TypeError) as exc:return self._finish('STOPPED','RECOVERY_REPLAN_FAILED:'+str(exc)[:80])
                    goals=goals[:reached]+remaining
                    with self.lock:
                        self.current['skipped_stops']=sorted(set(self.current['skipped_stops'])|set(skipped));self._save()
                    self._overlay(polyline=[[round(pose[0],4),round(pose[1],4)]]+[[round(q[0],4),round(q[1],4)] for leg in legs for q in leg],
                        keepouts=[[round(d[0],3),round(d[1],3),d[2]] for d in discs],skipped_stops=list(self.current['skipped_stops']))
                    queue=[(list(q),reached+i,remaining[i][1]) for i,leg in enumerate(legs) for q in leg]
                    continue
                if outcome[0]!='COMPLETED':
                    if outcome[0].startswith('STEP_'):return self._finish('STOPPED',outcome[0]+':'+str(outcome[1]))
                    return self._finish(outcome[0],str(outcome[1]))
                previous=epochs
                with self.lock:self.current['completed_steps']+=1;self._save()
                self._overlay(completed_steps=self.current['completed_steps'],current_step=None)
            with self.lock:self.current['end_pose_odometry']=[round(v,4) for v in plan_pose(start,origin,self._measured(row))]
            self._finish('COMPLETED','ALL_STOPS_AND_RETURN_COMPLETED')
        except OSError as exc:  # route record not writable (disk full): halt, never continue unrecorded
            stop=self._stop(robot_id,owner,epochs)
            self._finish('FAILED','ROUTE_RECORD_WRITE_FAILED:'+type(exc).__name__+':'+stop)
        except Exception as exc:  # never leave a RUNNING record or an unstopped step behind
            stop=self._stop(robot_id,owner,epochs)
            self._finish('FAILED','RUNNER_ERROR:'+type(exc).__name__+':'+stop)
