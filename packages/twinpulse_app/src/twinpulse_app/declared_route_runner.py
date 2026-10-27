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
    unexplained_scan_discs, scan_world_points, cluster_candidates, HEADING_TOLERANCE_RAD, REAIM_TOLERANCE_RAD, PHYSICAL_ROUTE_CLEARANCE_M)
from twinpulse_core.robot_survey import PLANNING_CLEARANCE_M
from .command_broker import BrokerError

DONE_REASONS={'TASK_COMPLETED','TASK_WHEEL_ODOM_TARGET_REACHED'}
TERMINAL={'COMPLETED','FAILED','CANCELLED','ARRIVED','ESTIMATE_REACHED'}
ACK_TIMEOUT_S=10.
PHYSICAL_SETTLE_S=1.5
MAX_RECOVERIES=2
RECOVERY_BACKOFF_M=.25
RECOVERY_KEEPOUT_M=.25  # leaves/baskets are wider than the proximity cone (review 2026-10-25)
SIM_RECOVERY_OFFSET_M=.45  # SIM contact stop: body .105 + skin .10 = the obstacle face is ~.2 m ahead
SIM_RECOVERY_KEEPOUT_M=.40
SIM_RECOVERY_BACKOFF_M=.40  # the robot came from there; .25 left its start inside the keepout's clearance band (GRID_EDGE_BLOCKED)
MAX_STEPS_FACTOR=3
OTHER_ROBOT_KEEPOUT_M=.35  # SIM body radius + engine stop skin, see twinpulse_fleet_runtime.integrate_motion
TRACE_SPACING_M=.04
MAX_TRACE_POINTS=800
MAX_DRIVE_POINTS=2500  # display-only during-drive LiDAR returns kept per route
PROXIMITY_STOP_REASONS={'FIELD_PROXIMITY_10CM','OBSTACLE_STOP'}  # physical field guard / Isaac SIM body-contact stop
OVERLAY_LABEL='DECLARED_START_PLUS_WHEEL_ODOMETRY_NOT_LOCALIZED'
# Route-end carry-over (2026-10-27 build 59): the next start is the last COMPLETED route's end, because the
# robot cannot be put back exactly on the tape. Declared start + wheel odometry, never localization.
CARRY_BASIS='route_end_odometry_estimate'
CARRY_LABEL='ROUTE_END_ESTIMATE_DECLARED_START_PLUS_WHEEL_ODOMETRY_NOT_LOCALIZED'
# Engineering bound, NOT a measured confidence: 2026-10-25 a 6.42 m route ended 14.9 cm off the tape while
# wheel odometry said 1.5 cm (SPRINT_PATH_B_SPEC.md). Heading drift is unmeasured (placeholder).
ODOM_DRIFT_M_PER_M=.025
ODOM_DRIFT_RAD_PER_M=.01
# A carried plan widens the planner berth by its uncertainty, so the next route keeps the reserve a fresh
# declaration gets; an estimate beyond that reserve is refused.
CARRY_MAX_UNCERTAINTY_M=round(PHYSICAL_ROUTE_CLEARANCE_M-PLANNING_CLEARANCE_M,3)
CARRY_MAX_UNCERTAINTY_RAD=.10
CARRY_IDLE_M=.03  # wheels/LiDAR tracker after the route ended (a Bootstrap stop trial drives <= 1.8 cm)
CARRY_IDLE_RAD=.05
# Moved by hand: the stationary LiDAR ring must still match the ring at the route end (change check, no pose fit).
# Synthetic rooms, 1-3 cm + 1-3 % range noise: a still robot repeats >= .79, a 15 cm / 5 deg move <= .77.
RING_BIN_RAD=math.radians(4)
RING_MIN_BINS=25
RING_TOL_M=.05
RING_TOL_REL=.03
RING_MIN_AGREEMENT=.75
RING_SAME_FRAME_MS=1000  # the route end's own frame only < 1 s after the end: a re-plan at the finish (Run checks again)


def step_timeout_s(step):
    # Physical field speed is 0.03 m/s; allow arming/watch and robot-side settling.
    return (step['amount']/.025 if step['direction']=='forward' else step['amount']/.15)+20.


def _pose3(value):
    return (isinstance(value,list) and len(value)==3
        and all(type(v) in (int,float) and math.isfinite(v) for v in value))


def _moved(a,b):
    return math.dist(a[:2],b[:2])>CARRY_IDLE_M or abs(math.remainder(a[2]-b[2],math.tau))>CARRY_IDLE_RAD


def ring_ranges(points):
    """Median range per 4-degree bearing (sensor frame, .3-4 m)."""
    bins={}
    for p in points or []:
        if not (isinstance(p,(list,tuple)) and len(p)==2 and all(type(v) in (int,float) and math.isfinite(v) for v in p)):continue
        r=math.hypot(*p)
        if .3<r<=4.:bins.setdefault(int((math.atan2(p[1],p[0])+math.pi)/RING_BIN_RAD),[]).append(r)
    return {k:sorted(v)[len(v)//2] for k,v in bins.items()}


def ring_agreement(before,after):
    """Share of bearings whose range repeats; None when too few bearings overlap to judge."""
    common=before.keys()&after.keys()
    if len(common)<RING_MIN_BINS:return None
    return sum(abs(before[k]-after[k])<=RING_TOL_M+RING_TOL_REL*before[k] for k in common)/len(common)


class DeclaredRouteRunner:
    def __init__(self,fleet,root,*,clock=time.monotonic,sleep=time.sleep,poll_s=.25,on_result=None,on_progress=None):
        self.fleet,self.root,self.clock,self.sleep,self.poll_s=fleet,Path(root),clock,sleep,poll_s
        self.on_result,self.on_progress=on_result,on_progress;self.lock=threading.Lock();self.current=None;self.cancelled=threading.Event()
        # Counts every cancel; a plan records it and start() refuses a plan that a later Stop
        # invalidated, so starting a route can never erase a Stop pressed after the plan.
        self.cancel_lock=threading.Lock();self.cancels=0
        # Any Stop/drive/focus/disconnect through the fleet (UI button, chat, API) cancels the route.
        fleet.declared_route_cancel=self.cancel
        self.used_declarations=set()  # a declared start is valid for one run only (RobotFleet saves it too)
        # robot_id -> end pose of its last COMPLETED physical route. Session-only: every run, a Stop/drive/
        # reconnect, wheel or LiDAR-seen motion and an App restart drop it.
        self.end_estimates={}
        fleet.declared_route_start_view=self.start_view;fleet.declared_route_reset=self.end_estimates.clear
        # Display-only Twin overlay (route, odometry trace, per-stop LiDAR, candidates).
        # Replaced as a whole on each change so the fleet can read it without our lock.
        self.anchor=None;fleet.route_overlay=None

    def active(self):
        with self.lock:return bool(self.current and self.current['state']=='RUNNING')

    def cancel(self):
        with self.cancel_lock:self.cancels+=1;self.cancelled.set()

    def _row(self,robot_id):
        return next((r for r in self.fleet.snapshot()['robots'] if r['robot_id']==robot_id),None)

    def _same_frame(self,revision,scene):
        # The Twin's frame, not its content revision: object edits (an auto-applied LiDAR box) keep it.
        same=getattr(self.fleet,'same_twin_frame',None)
        return revision==scene['binding'][2] or bool(same and same(revision,scene['binding'][2]))

    def _declared(self,row,scene):
        """(placed on this Twin's frame, and no route started from it yet) for the operator's manual start."""
        declared=row.get('display_pose') or {}
        placed=bool(_pose3(declared.get('position_m')) and self._same_frame(declared.get('scene_revision'),scene))
        return placed,placed and declared.get('visual_epoch') not in self.used_declarations

    def _start_pose(self,row,scene):
        if row['kind']=='physical':
            placed,fresh=self._declared(row,scene)
            if fresh:return list(row['display_pose']['position_m']),'operator_declared_display_pose'  # a fresh manual declaration always wins
            carried,why=self._carried_start(row,scene)
            if carried is not None:return carried,CARRY_BASIS
            note=' The last route end pose cannot be used: %s.'%why if why else ''
            if not placed:
                raise BrokerError('declared_route_start_required','Set the robot position and heading on this Twin first.'+note,status=409)
            raise BrokerError('declared_route_start_required','The robot has moved since this position was set. Set its position and heading on the Twin again.'+note,status=409)
        start=(row.get('pose') or {}).get('position_m')
        if not _pose3(start):raise BrokerError('declared_route_pose_required','A current SIM pose is required.',status=409)
        return list(start),'sim_engine_pose'

    def _carried_start(self,row,scene):
        """Declared start + wheel odometry at the last COMPLETED route's end, if nothing could have moved the robot
        since. Returns (pose, None) or (None, reason); never a measured or localized pose."""
        est=self.end_estimates.get(row['robot_id'])
        if est is None:return None,None
        with self.cancel_lock:stopped=self.cancels!=est['cancels']
        if stopped:return None,'Stop, manual drive, a focus change or Disconnect was used after that route was planned'
        if self._pins(row)!=est['pins']:return None,'the robot connection changed since the route ended'
        if row.get('live_heartbeat') is not True:return None,'no live robot telemetry'
        unc=est['uncertainty']
        if unc['position_m']>CARRY_MAX_UNCERTAINTY_M or unc['yaw_rad']>CARRY_MAX_UNCERTAINTY_RAD:
            return None,'its odometry uncertainty (about %.0f cm / %.1f deg after %.1f m driven) is above the %.0f cm / %.1f deg limit'%(
                unc['position_m']*100,math.degrees(unc['yaw_rad']),est['public']['driven_m'],CARRY_MAX_UNCERTAINTY_M*100,math.degrees(CARRY_MAX_UNCERTAINTY_RAD))
        if not self._same_frame(est['revision'],scene):return None,'the Twin was re-imported or its source or frame changed'
        try:odom=self._measured(row)
        except ValueError:return None,'no wheel odometry'
        if _moved(odom,est['odom_end']):
            return None,'the wheels moved %.0f cm / %.1f deg after the route ended'%(100*math.dist(odom[:2],est['odom_end'][:2]),
                math.degrees(abs(math.remainder(odom[2]-est['odom_end'][2],math.tau))))
        then=est['tracking'];now=(row.get('field') or {}).get('tracking') or {}
        if then and now.get('status')=='ESTIMATED' and now.get('epoch')==then['epoch'] and _pose3(now.get('pose')) and _moved(now['pose'],then['pose']):
            return None,'LiDAR tracking shows the robot moved after the route ended'
        # Lifted or carried: wheel odometry does not see it, the surroundings do. The end frame itself counts only just
        # after the end: native_stream re-emits its last complete frame with a fresh receipt while partial frames arrive.
        scan=row.get('scan') or {};age=(row.get('scan_receipt') or {}).get('age_ms')
        if (row.get('lidar_state')!='STREAMING' or not est['ring'] or (scan.get('stream_id'),scan.get('frame_sequence'))==est['scan_id']
                and not (type(age) in (int,float) and 0<=age<RING_SAME_FRAME_MS and 0<=(self.clock()-est['at'])*1000<RING_SAME_FRAME_MS)):
            return None,'no new LiDAR scan to compare with the route end'
        agreement=ring_agreement(est['ring'],ring_ranges(scan.get('points')))
        if agreement is None or agreement<RING_MIN_AGREEMENT:
            return None,'the LiDAR view differs from the route end (%s of bearings repeat), so the robot may have been moved'%(
                'too few' if agreement is None else '%.0f%%'%(100*agreement))
        return plan_pose(est['start'],est['origin'],odom),None

    @staticmethod
    def _pins(row):
        return dict(connection_epoch=row.get('connection_epoch'),operation_id=row.get('operation_id'),
            device_boot_id=row.get('device_boot_id'),odom_frame_id=(row.get('pose') or {}).get('frame_id'))

    def _end_estimate(self,plan,row,origin,measured,driven_m):
        base=plan.get('start_uncertainty') or dict(position_m=0.,yaw_rad=0.)  # chained carries accumulate
        end=plan_pose(plan['start'],origin,measured);lever=math.dist(plan['start'][:2],end[:2])  # the start's heading error turns the end about it
        unc=dict(position_m=round(base['position_m']+base['yaw_rad']*lever+ODOM_DRIFT_M_PER_M*driven_m,3),yaw_rad=round(base['yaw_rad']+ODOM_DRIFT_RAD_PER_M*driven_m,4),
            relative_to='operator_declared_start',basis='ENGINEERING_BOUND_NOT_MEASURED_CONFIDENCE')
        tracking=(row.get('field') or {}).get('tracking') or {};scan=row.get('scan') or {}
        ring=ring_ranges(scan.get('points')) if row.get('lidar_state')=='STREAMING' else {}
        refused=('above the %.0f cm / %.1f deg limit'%(CARRY_MAX_UNCERTAINTY_M*100,math.degrees(CARRY_MAX_UNCERTAINTY_RAD))
            if unc['position_m']>CARRY_MAX_UNCERTAINTY_M or unc['yaw_rad']>CARRY_MAX_UNCERTAINTY_RAD else
            'no LiDAR ring at the end to check later that the robot was not moved' if len(ring)<RING_MIN_BINS else None)
        public=dict(label=CARRY_LABEL,from_plan_id=plan['plan_id'],pose=[round(v,4) for v in end],
            uncertainty=unc,driven_m=round(driven_m,3),carry_over=refused is None,carry_refused=refused)
        return dict(public=public,at=self.clock(),start=list(plan['start']),origin=list(origin),odom_end=list(measured),uncertainty=unc,cancels=plan['cancels'],
            pins=self._pins(row),revision=plan['scene_revision'],ring=ring,scan_id=(scan.get('stream_id'),scan.get('frame_sequence')),
            tracking=dict(epoch=tracking['epoch'],pose=list(tracking['pose'])) if tracking.get('status')=='ESTIMATED' and _pose3(tracking.get('pose')) else None)

    def start_view(self,row):
        """Robot card: the carried start and whether the next route may use it (display only)."""
        est=self.end_estimates.get((row or {}).get('robot_id'));scene=self.fleet.navigation_scene
        if est is None or row.get('kind')!='physical':return None
        pose,why=self._carried_start(row,scene) if scene else (None,'no current Twin')
        manual=bool(scene) and self._declared(row,scene)[1]  # also after a refused carry: that is when the card asks for it
        if manual:pose,why=None,'the position set by hand is used instead'
        return dict(est['public'],usable=pose is not None,overridden=manual,reason=why,pose=[round(v,4) for v in pose] if pose else est['public']['pose'])

    def readiness(self,robot_id):
        """The guards every route plan passes first (scene shown, robot known, stopped/prepared, physical field
        ready, start pose declared). Callers that would spend a planner model call check this before the call."""
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
        return scene,row,start,basis

    def plan(self,robot_id,*,budget_m=None,stops=None):
        with self.cancel_lock:cancels=self.cancels  # before any readiness read: a Stop during planning also counts
        scene,row,start,basis=self.readiness(robot_id)
        # SIM: other connected SIM robots stand on the same floor and the engine
        # stops for them, so the plan keeps a berth around each (2026-10-26 sim14/15).
        robot_discs=[(r['pose']['position_m'][0],r['pose']['position_m'][1],OTHER_ROBOT_KEEPOUT_M)
            for r in self.fleet.snapshot()['robots'] if row['kind']=='sim' and r['robot_id']!=robot_id and r.get('kind')=='sim'
            and r.get('connection_state')=='CONNECTED' and _pose3((r.get('pose') or {}).get('position_m'))]
        # Physical: one stationary LiDAR ring at the declared start adds returns
        # the scanned model cannot explain (leaves, fan base, basket) as keepouts.
        scan_review=dict(used=False,discs=[],reason='NOT_PHYSICAL_OR_NO_SCAN')
        points=((row.get('scan') or {}).get('points') or []) if row['kind']=='physical' and row.get('lidar_state')=='STREAMING' else []
        carried=self.end_estimates.get(robot_id) if basis==CARRY_BASIS else None
        if basis==CARRY_BASIS and carried is None:raise BrokerError('declared_route_changed','The robot start pose changed; ask for the route again.',status=409)
        margin=carried['uncertainty']['position_m'] if carried else 0.
        try:
            if points:  # a malformed native row must not become a 500
                scan_review=unexplained_scan_discs(start,points,scene.get('observed_cells'))
                scan_review.update(stream_id=(row.get('scan') or {}).get('stream_id'),frame_sequence=(row.get('scan') or {}).get('frame_sequence'),points=len(points))
        except (ValueError,KeyError,TypeError) as exc:
            raise BrokerError('declared_route_unplannable',str(exc)[:160],status=409) from None
        # The carried start must still explain the current LiDAR ring on the current Twin (same rule as the start keepouts).
        if carried and not scan_review.get('used'):
            raise BrokerError('declared_route_start_required','The current LiDAR scan does not match the Twin at the last route end pose (agreement %s). '
                'Set the robot position and heading on this Twin first.'%scan_review.get('agreement'),status=409)
        try:
            for _ in range(3):
                if stops:plan=plan_through(start,stops,scene['geometry'],scene.get('observed_cells'),kind=row['kind'],discs=[*scan_review['discs'],*robot_discs],margin_m=margin)
                else:plan=plan_survey(start,scene['geometry'],scene.get('observed_cells'),kind=row['kind'],
                    budget_m=budget_m or (8. if row['kind']=='physical' else 6.),discs=[*scan_review['discs'],*robot_discs],margin_m=margin)
                if not carried:break
                # A start heading error turns the whole route about the start: add yaw x the farthest planned point.
                need=carried['uncertainty']['position_m']+carried['uncertainty']['yaw_rad']*max((math.dist(start[:2],q[:2]) for q in plan['polyline']),default=0.)
                if need<=margin+.001:break
                margin=math.ceil(need*1000)/1000
            else:raise ValueError('DECLARED_ROUTE_CARRIED_MARGIN_UNSETTLED')
            steps=compile_moves(start,plan['polyline'],final_yaw=start[2])
        except (ValueError,KeyError,TypeError) as exc:
            raise BrokerError('declared_route_unplannable',str(exc)[:160]+(' (planned with a %.0f cm wider berth for the carried start; Set position plans with the normal berth)'
                %(margin*100) if carried else ''),status=409) from None
        estimate=dict(start_estimate=dict(carried['public']),start_uncertainty=dict(carried['uncertainty']),start_margin_m=margin) if carried else {}
        return dict(plan_id=uuid4().hex,robot_id=robot_id,kind=row['kind'],start_basis=basis,cancels=cancels,**estimate,
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
            start,basis=self._start_pose(row,scene)
            if (basis!=plan['start_basis'] or math.dist(start[:2],plan['start'][:2])>.02
                    or abs(math.remainder(start[2]-plan['start'][2],math.tau))>.02):
                raise BrokerError('declared_route_changed','The robot start pose changed; ask for the route again.',status=409)
            if row.get('control_state') not in {'READY','PAUSED'}:
                raise BrokerError('declared_route_robot_busy','Stop and prepare the robot before a route.',status=409)
            with self.cancel_lock:
                # 2026-10-27 review: a Stop pressed after the route card (or while Run was queued behind
                # the chat lock) left the robot PAUSED, which start() accepts, and the clear below erased
                # it, so step 1 drove a full leg after the Stop. Refuse instead; the user asks again.
                if plan.get('cancels')!=self.cancels:
                    raise BrokerError('declared_route_stopped','Stop was pressed after this route was planned, so it will not run. Ask for the route again; nothing moved.',status=409)
                self.cancelled.clear()
            if row['kind']=='physical' and basis=='operator_declared_display_pose':
                epoch=(row.get('display_pose') or {}).get('visual_epoch');self.used_declarations.add(epoch)
                consume=getattr(self.fleet,'consume_display_pose',None)
                try:
                    if consume:consume(plan['robot_id'],epoch)
                except OSError as exc:
                    raise BrokerError('declared_route_record_failed','The used start could not be saved (%s). Free disk space, set the position again and ask for the route again; nothing moved.'%type(exc).__name__,status=507) from None
            self.end_estimates.pop(plan['robot_id'],None)  # every run consumes the last end estimate; only a COMPLETED run sets a new one
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
            driven=0.;last=list(origin)  # odometry path length; sizes the route-end estimate's uncertainty
            margin=plan.get('start_margin_m',0.)  # a carried start keeps its wider berth in recovery re-plans
            while True:
                try:measured=self._measured(row);pose=plan_pose(start,origin,measured)
                except ValueError:return self._finish('STOPPED','ROUTE_POSE_UNAVAILABLE:'+self._stop(robot_id,owner,epochs))
                driven+=math.dist(measured[:2],last[:2]);last=measured
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
                # A SIM robot meets an unmodelled object as an engine OBSTACLE_STOP (body + stop skin), the physical
                # robot as its own FIELD_PROXIMITY_10CM pause: both recover the same way (2026-10-26 SIM-world test box).
                if (outcome[0]=='STEP_FAILED' and outcome[1] in PROXIMITY_STOP_REASONS and step['direction']=='forward'
                        and recoveries<MAX_RECOVERIES):
                    recoveries+=1
                    at=self._measured(row);driven+=math.dist(at[:2],last[:2]);last=at
                    blocked=plan_pose(start,origin,at)
                    # Physical proximity fires ~.23 m before contact; the SIM engine stops at body contact (radius + skin),
                    # so its keepout sits further ahead and wider to cover a whole unmodelled box (2026-10-26 SIM box test).
                    offset,radius=(.25,RECOVERY_KEEPOUT_M) if (row or {}).get('kind')=='physical' else (SIM_RECOVERY_OFFSET_M,SIM_RECOVERY_KEEPOUT_M)
                    discs.append((blocked[0]+offset*math.cos(blocked[2]),blocked[1]+offset*math.sin(blocked[2]),radius))
                    with self.lock:
                        self.current.setdefault('recoveries',[]).append(dict(at=[round(v,4) for v in blocked],keepout_m=radius))
                        self._save()
                    self._overlay(recoveries=recoveries)
                    self._progress('recovery',at=[round(v,4) for v in blocked],recoveries=recoveries)
                    if row and row.get('kind')=='physical':self.sleep(PHYSICAL_SETTLE_S)
                    # Wait for the proximity pause's Stop to be applied before backing off.
                    backoff=RECOVERY_BACKOFF_M if (row or {}).get('kind')=='physical' else SIM_RECOVERY_BACKOFF_M  # SIM: clear the wider keepout's clearance band
                    outcome,row,epochs=self._step(owner,robot_id,dict(direction='backward',amount=backoff),'AFTER_STOP')
                    if outcome[0]!='COMPLETED':return self._finish('STOPPED','RECOVERY_'+outcome[0]+':'+str(outcome[1]))
                    previous=epochs;pose=plan_pose(start,origin,self._measured(row))
                    # A stop that sits inside the new keepout is skipped (and reported); the start is always kept.
                    pending=goals[reached:-1]
                    remaining=[g for g in pending if all(math.dist(g[0],d[:2])>d[2]+.65 for d in discs)]+[goals[-1]]
                    skipped=[g[1] for g in pending if g not in remaining]
                    scene=self.fleet.navigation_scene or {}
                    if not scene or scene['binding'][2]!=plan['scene_revision']:return self._finish('STOPPED','RECOVERY_SCENE_CHANGED')
                    try:legs=replan_legs(pose,[g[0] for g in remaining],scene.get('geometry') or {},scene.get('observed_cells'),kind=plan['kind'],discs=discs,home=start[:2],margin_m=margin)
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
            with self.lock:
                measured=self._measured(row);driven+=math.dist(measured[:2],last[:2])
                self.current['end_pose_odometry']=[round(v,4) for v in plan_pose(start,origin,measured)]
                if plan['kind']=='physical':
                    # Set before the finish callback: the auto re-plan after Twin edits plans from it right away.
                    try:estimate=self._end_estimate(plan,row,origin,measured,driven)
                    except (KeyError,TypeError,ValueError):estimate=None  # no carry-over; the completed route stays completed
                    if estimate:self.current['end_estimate']=estimate['public'];self.end_estimates[robot_id]=estimate
            self._finish('COMPLETED','ALL_STOPS_AND_RETURN_COMPLETED')
        except OSError as exc:  # route record not writable (disk full): halt, never continue unrecorded
            stop=self._stop(robot_id,owner,epochs)
            self._finish('FAILED','ROUTE_RECORD_WRITE_FAILED:'+type(exc).__name__+':'+stop)
        except Exception as exc:  # never leave a RUNNING record or an unstopped step behind
            stop=self._stop(robot_id,owner,epochs)
            self._finish('FAILED','RUNNER_ERROR:'+type(exc).__name__+':'+stop)
