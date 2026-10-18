# SPDX-License-Identifier: Apache-2.0
"""Owned Isaac kinematic fleet. SIM source is explicit, not motor/PhysX evidence."""
import math
import time


def observe_startup(robot,created,dt,capture_pending):
    if not created and not robot.get('startup_ready',False):
        eligible=robot.get('render_observed',False) and not capture_pending and 0<dt<.25
        robot['startup_samples']=robot.get('startup_samples',0)+1 if eligible else 0
        robot['startup_ready']=robot['startup_samples']>=2


def bind_intent(robot,incoming,now_ms,*,received_at=None,now=None):
    """Monotonic per-epoch input, immutable expiry; no USD or transport work."""
    if not incoming:
        # A task or an explicit no-input snapshot breaks manual coverage.
        # Retain the sequence fence, never a renewable old manual interval.
        robot.update(last_intent=None,intent_active_since=None)
        return None
    sequence=incoming.get('sequence');previous=robot.get('intent_sequence')
    if type(sequence) is not int or sequence<=0:return None
    if previous is None or sequence>previous:
        old=robot.get('last_intent')
        if received_at is not None and now is not None:
            # Same-direction renewals may cover a tick continuously, but a
            # first input, direction change or expiry gap must never backdate
            # motion to the previous Kit update. Use I/O receipt, not dequeue.
            old_expiry=now+(old['expires_at_ms']-now_ms)/1000 if old else None
            if (not old or old['direction']!=incoming['direction'] or
                    received_at>old_expiry or robot.get('intent_active_since') is None):
                robot['intent_active_since']=received_at
        robot['intent_sequence']=sequence;robot['last_intent']=dict(incoming)
        failed=robot.get('stale_intent_sequence')
        if robot.get('reason')=='INPUT_STALE':
            if incoming['expires_at_ms']>now_ms and type(failed) is int and sequence>failed:
                robot.update(reason=None,stale_intent_sequence=None)
            elif incoming['expires_at_ms']<=now_ms:
                robot['stale_intent_sequence']=max(sequence,failed or 0)
    # Same/lower sequence cannot change its original timestamp or direction.
    return robot.get('last_intent')


def integrate_motion(pose,direction,elapsed,boxes,remaining=None):
    """SIM only: preserve eligible elapsed time, collision-check <=50ms steps.

    A main-thread gap >= the existing 500ms transport watchdog is not replayed.
    The caller still checks the original input expiry/task deadline first.
    """
    if not math.isfinite(elapsed) or elapsed<0 or elapsed>=.5:
        return list(pose),0.,'INPUT_STALE',0
    current=list(pose);travel=0.;steps=0
    speed=.05 if direction in {'forward','backward'} else .30
    while elapsed>1e-12 and (remaining is None or travel<remaining):
        step=min(.05,elapsed);elapsed-=step
        distance=speed*step
        if remaining is not None:distance=min(distance,max(0.,remaining-travel))
        candidate=list(current)
        if direction in {'forward','backward'}:
            sign=1 if direction=='forward' else -1
            candidate[0]+=sign*distance*math.cos(candidate[2]);candidate[1]+=sign*distance*math.sin(candidate[2])
        else:candidate[2]+=distance*(1 if direction=='left' else -1)
        steps+=1
        if any(FleetRuntime._gap(candidate,box)<.10+.05*.05 and
               FleetRuntime._gap(candidate,box)<FleetRuntime._gap(current,box)-1e-8 for box in boxes):
            return current,travel,'OBSTACLE_STOP',steps
        current=candidate;travel+=distance
    return current,travel,None,steps


class FleetRuntime:
    ROOT='/World/TwinPulse/Fleet'

    def __init__(self):
        self.identity=None;self.robots={};self.desired=None;self.received_at=0.;self.updated_at=time.monotonic()
        self.report=[];self.anchors=[];self.sequence=0;self.obstacles=[];self.scan_at=0.
        self.bounds_notice=None;self.bounds_dirty=True;self.bounds_watch=False;self.bounds_rebuilds=0
        self.snapshot_capture_pending=False;self.model_generation=0

    def render_tokens(self):
        return (self.identity,{key:(row['epoch'],row.get('model_generation')) for key,row in self.robots.items()})

    def rendered(self,identity,tokens):
        # Called on Kit's main thread after the matching GPU callback completed.
        if identity!=self.identity:return
        for key,token in tokens.items():
            row=self.robots.get(key)
            if row and (row['epoch'],row.get('model_generation'))==token:row['render_observed']=True

    def _environment_changed(self,notice,_sender):
        # Fleet transforms and camera updates do not change static environment
        # collision geometry. Manual edits of that environment still invalidate.
        root='/World/TwinPulse/Environment'
        for value in list(notice.GetResyncedPaths())+list(notice.GetChangedInfoOnlyPaths()):
            text=str(value.GetPrimPath())
            if text=='/' or text==root or text.startswith(root+'/') or root.startswith(text+'/'):
                self.bounds_dirty=True;break

    def _watch_environment(self,stage):
        if self.bounds_notice is not None:self.bounds_notice.Revoke()
        self.bounds_notice=None;self.bounds_watch=False;self.bounds_dirty=True
        try:
            from pxr import Tf,Usd
            self.bounds_notice=Tf.Notice.Register(Usd.Notice.ObjectsChanged,self._environment_changed,stage)
            self.bounds_watch=True
        except (ImportError,AttributeError):
            # Without a working invalidation subscription retain the old
            # bounded polling path, never silently keep stale collision bounds.
            pass

    def _refresh_bounds(self,stage,now):
        if self.bounds_dirty or not self.bounds_watch and now-self.scan_at>.2:
            self.obstacles=self._bounds(stage);self.scan_at=now;self.bounds_dirty=False;self.bounds_rebuilds+=1

    def receive(self,value,received_at=None):
        self.desired=value;self.received_at=time.monotonic() if received_at is None else received_at
        # Called only by Kit's main thread. Consume each bounded I/O snapshot's
        # admission boundary even when only the final snapshot is rendered.
        if value and self.identity and value.get('applied_revision')==self.identity[2]:
            now=time.monotonic();now_ms=time.time()*1000
            for request in value['robots']:
                robot=self.robots.get(request['robot_id'])
                if robot and robot['epoch']==request['connection_epoch'] and robot['motion_epoch']==request['motion_epoch']:
                    bind_intent(robot,request.get('intent'),now_ms,received_at=self.received_at,now=now)
                    if not robot.get('startup_ready',False):
                        robot.update(last_intent=None,intent_active_since=None)
                        task=request.get('task')
                        if task:robot['warm_rejected_task']=task['task_id']

    def _bounds(self,stage):
        from pxr import UsdGeom, Usd
        root=stage.GetPrimAtPath('/World/TwinPulse/Environment')
        if not root:return []
        cache=UsdGeom.BBoxCache(Usd.TimeCode.Default(),[UsdGeom.Tokens.default_]);boxes=[]
        for prim in Usd.PrimRange(root):
            if prim.IsA(UsdGeom.Mesh) or prim.IsA(UsdGeom.Cube) or prim.IsA(UsdGeom.Cylinder):
                if len(boxes)>=512:break
                bounds=cache.ComputeWorldBound(prim).ComputeAlignedRange();lo,hi=bounds.GetMin(),bounds.GetMax()
                # Ground is not an obstacle; native 2D sensor is at 0.18m.
                if lo[2] <= .18 <= hi[2] and hi[2]>.08:
                    boxes.append((float(lo[0]),float(lo[1]),float(hi[0]),float(hi[1])))
        return boxes

    @staticmethod
    def _gap(pose,box):
        x,y,_=pose;a,b,c,d=box
        return math.hypot(max(a-x,0,x-c),max(b-y,0,y-d))-.105

    def _scan(self,pose,boxes):
        x,y,yaw=pose;points=[]
        for index in range(180):
            angle=index*math.pi/90;dx,dy=math.cos(angle+yaw),math.sin(angle+yaw);distance=8.
            for a,b,c,d in boxes:
                enter,leave=0.,distance
                for origin,delta,lo,hi in ((x,dx,a,c),(y,dy,b,d)):
                    if abs(delta)<1e-9:
                        if not lo<=origin<=hi:leave=-1.;break
                    else:
                        first,last=(lo-origin)/delta,(hi-origin)/delta
                        if first>last:first,last=last,first
                        enter=max(enter,first);leave=min(leave,last)
                if leave>=enter>=0:distance=min(distance,enter)
            if distance<8:points.append([round(distance*math.cos(angle),4),round(distance*math.sin(angle),4)])
        return dict(points=points,source='isaac_usd_aabb_rays')

    def update(self,snapshot):
        import omni.usd
        from pxr import Gf, UsdGeom
        stage=omni.usd.get_context().get_stage()
        if stage is None:return
        now=time.monotonic();dt=max(0,now-self.updated_at);self.updated_at=now
        identity=(snapshot.engine_session_id,snapshot.stage_epoch,snapshot.applied_revision)
        if identity!=self.identity:
            self.identity=identity;self.robots={};self.report=[];self.anchors=[];self.desired=None
            if stage.GetPrimAtPath(self.ROOT):stage.RemovePrim(self.ROOT)
            self._watch_environment(stage)
        fleet=self.desired
        if not snapshot.applied_revision or not fleet or fleet.get('applied_revision')!=snapshot.applied_revision:return
        if not stage.GetPrimAtPath('/World/TwinPulse'):return
        bounds_started=time.monotonic();self._refresh_bounds(stage,now)
        bounds_elapsed=max(0.,time.monotonic()-bounds_started)
        rows=fleet['robots'];wanted={row['robot_id'] for row in rows}
        for identity in set(self.robots)-wanted:
            stage.RemovePrim(self.ROOT+'/Robot_'+identity);del self.robots[identity]
        self.sequence+=1;report=[]
        for request in rows:
            identity=request['robot_id'];path=self.ROOT+'/Robot_'+identity
            robot=self.robots.get(identity)
            active_dt=dt
            created=robot is None or robot['epoch']!=request['connection_epoch'] or not stage.GetPrimAtPath(path)
            model_started=time.monotonic()
            if created:
                active_dt=0. # New authority cannot act on time before admission.
                if stage.GetPrimAtPath(path):stage.RemovePrim(path)
                placement=UsdGeom.Xform.Define(stage,path)
                marker=placement.GetPrim();marker.SetCustomDataByKey('robotId',identity)
                marker.SetCustomDataByKey('source','PHYSICAL_MARKER_OPERATOR_ESTIMATE_NOT_LOCALIZED' if request.get('visual_only') else 'ISAAC_KINEMATIC_SIM_NOT_PHYSICAL')
                from twinpulse_app.simulation_assets import ASSET_ROOT, burger_inventory
                burger_inventory()
                model=stage.DefinePrim(path+'/Model','Xform')
                model.GetReferences().AddReference(str(ASSET_ROOT/'turtlebot3_burger.usda'))
                model.GetVariantSet('Physics').SetVariantSelection('none')
                placement.AddTranslateOp();placement.AddRotateZOp()
                robot=dict(epoch=request['connection_epoch'],pose=list(request['position_m']),task=None,travel=0.,scan=None,
                           motion_epoch=request['motion_epoch'],reason=None,scan_at=0.,intent_sequence=None,
                           last_intent=None,stale_intent_sequence=None,intent_active_since=None,
                           startup_samples=0,startup_ready=False)
                self.model_generation+=1
                robot.update(model_generation=self.model_generation,render_observed=False)
                self.robots[identity]=robot
            model_elapsed=max(0.,time.monotonic()-model_started) if created else 0.
            # Do not count the first report's dt: it predates authoring.
            observe_startup(robot,created,dt,self.snapshot_capture_pending)
            if robot['motion_epoch']!=request['motion_epoch']:
                active_dt=0.
                robot.update(motion_epoch=request['motion_epoch'],reason=None,task=None,travel=0.,intent_sequence=None,
                             last_intent=None,stale_intent_sequence=None,intent_active_since=None,warm_rejected_task=None)
            intent=bind_intent(robot,request.get('intent'),time.time()*1000,received_at=self.received_at,now=now)
            task=request.get('task');direction=None;reason=robot['reason']
            if not robot.get('startup_ready',False):
                # Consume the sequence fence, but discard all premature intent.
                # A later ready tick cannot replay this same sequence/task ID.
                robot.update(last_intent=None,intent_active_since=None)
                if task:robot['warm_rejected_task']=task['task_id']
                intent=None;task=None
            elif task and task['task_id']==robot.get('warm_rejected_task'):
                task=None
            if not task and robot['task'] is not None:
                robot.update(task=None,travel=0.)
            if request.get('visual_only'):
                # Pure visualization. No intent, synthetic sensor, physical
                # pose/connection report or permission is manufactured here.
                robot.update(pose=list(request['position_m']),task=None,travel=0.,scan=None,reason=None)
                placement=UsdGeom.Xform(stage.GetPrimAtPath(path));ops=placement.GetOrderedXformOps()
                ops[0].Set(Gf.Vec3d(robot['pose'][0],robot['pose'][1],0.));ops[1].Set(math.degrees(robot['pose'][2]))
                continue
            if task and robot['task']!=task['task_id']:
                if reason not in {'ISAAC_UPDATE_STALLED','ISAAC_TRANSPORT_STALE'}:
                    robot.update(task=task['task_id'],travel=0.,reason=None);reason=None
                active_dt=0.
            if (dt>=.5 or time.monotonic()-now>=.5) and (intent or task):reason='ISAAC_UPDATE_STALLED'
            if not robot.get('startup_ready',False):
                # No buffering, renewal or later replay of premature commands.
                direction=None;intent=None;task=None
            elif now-self.received_at<.5 and not reason:
                if task:
                    if time.time()*1000>=task['deadline_ms']:reason='TASK_TIMEOUT'
                    elif robot['travel']>=task['amount']:reason='TASK_COMPLETED'
                    else:direction=task['direction']
                elif intent:
                    if time.time()*1000>=intent['expires_at_ms']:reason='INPUT_STALE'
                    else:
                        direction=intent['direction']
                        # Retain the full-gap watchdog; a fresh input cannot
                        # conceal a >=500ms main-thread stall or replay it.
                        if active_dt<.5:
                            active_dt=min(active_dt,max(0.,now-robot['intent_active_since']))
            elif now-self.received_at>=.5 and (intent or task):reason='ISAAC_TRANSPORT_STALE'
            if direction and time.monotonic()-self.received_at>=.5:
                reason='ISAAC_TRANSPORT_STALE';direction=None
            substeps=0;integrated_s=0.
            if direction:
                boxes=list(self.obstacles)
                for other_id,other in self.robots.items():
                    if other_id!=identity:
                        x,y,_=other['pose'];boxes.append((x-.105,y-.105,x+.105,y+.105))
                new,distance,stopped,substeps=integrate_motion(robot['pose'],direction,active_dt,boxes,
                    max(0.,task['amount']-robot['travel']) if task else None)
                robot['pose']=new;robot['travel']+=distance
                integrated_s=distance/(.05 if direction in {'forward','backward'} else .30)
                if stopped:reason='ISAAC_UPDATE_STALLED' if stopped=='INPUT_STALE' and active_dt>=.5 else stopped
                elif task and robot['travel']>=task['amount']-1e-12:reason='TASK_COMPLETED'
            if reason=='INPUT_STALE' and robot.get('stale_intent_sequence') is None:
                robot['stale_intent_sequence']=robot.get('intent_sequence')
            robot['reason']=reason
            placement=UsdGeom.Xform(stage.GetPrimAtPath(path));ops=placement.GetOrderedXformOps()
            ops[0].Set(Gf.Vec3d(robot['pose'][0],robot['pose'][1],0.));ops[1].Set(math.degrees(robot['pose'][2]))
            # Read authored USD transform back: telemetry reflects the actual scene.
            matrix=placement.ComputeLocalToWorldTransform(0);p=matrix.ExtractTranslation()
            measured=[float(p[0]),float(p[1]),math.radians(float(ops[1].Get()))]
            if request['lidar'] and now-robot['scan_at']>=.2:
                robot['scan']=self._scan(measured,self.obstacles);robot['scan_at']=now
            if not request['lidar']:robot['scan']=None
            report.append(dict(robot_id=identity,connection_epoch=robot['epoch'],motion_epoch=robot['motion_epoch'],
                sequence=self.sequence,position_m=measured,scan=robot['scan'],reason=reason,task_id=robot['task'],
                runtime_timing=dict(elapsed_s=round(dt,6),integrated_s=round(integrated_s,6),substeps=substeps),
                runtime_startup=dict(model_authored=True,render_observed=robot.get('render_observed',False),
                    snapshot_capture_pending=self.snapshot_capture_pending,post_author_updates=robot.get('startup_samples',0),ready=robot.get('startup_ready',False)),
                runtime_work=dict(bounds_s=round(bounds_elapsed,6),model_authoring_s=round(model_elapsed,6),bounds_rebuilds=self.bounds_rebuilds),
                intent_sequence=robot.get('stale_intent_sequence') if reason=='INPUT_STALE' else robot.get('intent_sequence')))
        self.report=report

    def frame_anchors(self,viewport):
        if not self.robots:return []
        from pxr import Gf, UsdGeom
        import omni.usd
        stage=omni.usd.get_context().get_stage();camera=UsdGeom.Camera(stage.GetPrimAtPath(str(viewport.camera_path)))
        if not camera:return []
        frustum=camera.GetCamera(0).frustum;view=frustum.ComputeViewMatrix();projection=frustum.ComputeProjectionMatrix();out=[]
        for identity,robot in self.robots.items():
            x,y,_=robot['pose'];world=Gf.Vec3d(x,y,.05)
            camera_point=view.Transform(world)
            if camera_point[2]>=0:continue
            projected=(view*projection).Transform(world);u,v=(projected[0]+1)/2,(1-projected[1])/2
            if 0<=u<=1 and 0<=v<=1:
                out.append(dict(robot_id=identity,screen_anchor_uv=[float(u),float(v)],
                    screen_bounds_uv=[max(0,float(u)-.025),max(0,float(v)-.08),min(1,float(u)+.025),float(v)],visible=True))
        return out
