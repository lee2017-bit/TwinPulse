# SPDX-License-Identifier: Apache-2.0
"""Owned Isaac kinematic fleet. SIM source is explicit, not motor/PhysX evidence."""
import math
import time
from twinpulse_core.robot_survey import SIM_BODY_RADIUS_M,SIM_STOP_SKIN_M,SIM_STOP_SUBSTEP_TRAVEL_M


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
        if any(FleetRuntime._gap(candidate,box)<SIM_STOP_SKIN_M+SIM_STOP_SUBSTEP_TRAVEL_M and
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
        self.planner=None;self.frame_scan=None;self.navigation_geometry_epoch=0
        self.sensor_sections={};self.sensor_geometry_epoch=-1
        self.host_timing={}
        self.navigation_scene=None;self.navigation_scene_epoch=None
        self.scene_produced_at=None
        self.scan_worker=None;self.scan_cursor=None;self.scan_job=None;self.scan_join=None
        self.route_key=None;self.route_error=None

    def close(self):
        errors=[]
        try:
            if self.scan_worker:self.scan_join=self.scan_worker.close()
        except Exception as exc:errors.append(dict(owner='scan_worker',error=type(exc).__name__))
        try:
            if self.planner:self.planner.shutdown(wait=False,cancel_futures=True)
        except Exception as exc:errors.append(dict(owner='planner',error=type(exc).__name__))
        try:
            if self.bounds_notice is not None:self.bounds_notice.Revoke();self.bounds_notice=None
        except Exception as exc:errors.append(dict(owner='bounds_notice',error=type(exc).__name__))
        return {**(self.scan_join or dict(closed=not errors,worker_alive=None if errors else False)),
                'cleanup_errors':errors}

    def _scan_token(self,identity,robot):
        return (self.identity,self.navigation_geometry_epoch,identity,robot['epoch'],robot['motion_epoch'],
                robot.get('model_generation'),robot.get('scan_generation',0))

    def _collect_scan(self,requests):
        if not self.scan_worker:return
        result=self.scan_worker.poll()
        if result is None:return
        sample=self.scan_job;self.scan_job=None
        if sample is None:return
        identity=sample['robot_id'];robot=self.robots.get(identity)
        request=next((r for r in requests if r['robot_id']==identity),None)
        # Stop/OFF/reconnect/new model/revision may have happened while the
        # worker ran. No result can renew authority or be restamped as current.
        if (not robot or not request or not request.get('lidar') or request.get('visual_only') or
            request['connection_epoch']!=robot['epoch'] or request['motion_epoch']!=robot['motion_epoch'] or
            result['token']!=self._scan_token(identity,robot)):return
        diagnostic={**sample['diagnostic'],**{k:v for k,v in result.items() if k not in {'token','points'}},
                    'captured_at_ms':sample['captured_at_ms'],'position_m':sample['position_m']}
        robot['scan_diagnostic']=diagnostic
        worst=robot.get('scan_worst')
        if worst is None or diagnostic['wall_s']>worst['wall_s']:robot['scan_worst']=dict(diagnostic)
        robot['scan_compute_s']=result['wall_s']
        error=result['error']
        if not 0<=time.time()*1000-sample['captured_at_ms']<350:error=error or 'LIDAR_SAMPLE_EXPIRED'
        robot['scan_error']=error
        robot['scan']=None if error else dict(points=result['points'],source='isaac_usd_surface_rays',
            position_m=sample['position_m'],height_m=sample['height_m'],sensor_frame=sample['sensor_frame'],
            geometry=sample['geometry'],captured_at_ms=sample['captured_at_ms'])
        robot['scan_token']=result['token']

    def _schedule_scan(self,stage,requests,now):
        if self.scan_worker is not None and self.scan_worker.busy:return
        if not requests:return
        ids=[r['robot_id'] for r in requests]
        offset=(ids.index(self.scan_cursor)+1)%len(ids) if self.scan_cursor in ids else 0
        for request in requests[offset:]+requests[:offset]:
            identity=request['robot_id'];robot=self.robots.get(identity)
            if not robot or not request.get('lidar') or request.get('visual_only') or now-robot['scan_at']<.2:continue
            from twinpulse_app.lidar_scene_geometry import sensor_pose,scene_section
            started=time.monotonic();cpu=time.thread_time();stamp=time.time()*1000
            diagnostic={};self.scan_cursor=identity;robot['scan_at']=now
            try:
                sensor,height,path=sensor_pose(stage,self.ROOT+'/Robot_'+identity)
                diagnostic.update(sensor_pose_wall_s=time.monotonic()-started,sensor_pose_cpu_s=time.thread_time()-cpu)
                geometry_epoch=(self.identity,self.navigation_geometry_epoch)
                if geometry_epoch!=self.sensor_geometry_epoch:
                    self.sensor_sections={};self.sensor_geometry_epoch=geometry_epoch
                key=round(height,9);hit=key in self.sensor_sections
                began=time.monotonic();cpu=time.thread_time()
                if not hit:self.sensor_sections[key]=scene_section(stage,height)
                section,geometry=self.sensor_sections[key]
                diagnostic.update(section_wall_s=time.monotonic()-began,section_cpu_s=time.thread_time()-cpu,
                    section_cache_hit=hit,height_key=key,geometry_epoch=self.navigation_geometry_epoch,
                    segments=geometry['segments'],triangles=geometry['triangles'],prepared_monotonic_s=time.monotonic())
                if self.scan_worker is None:
                    try:from twinpulse_scan_worker import ScanWorker
                    except ModuleNotFoundError:from scripts.twinpulse_scan_worker import ScanWorker
                    self.scan_worker=ScanWorker()
                token=self._scan_token(identity,robot)
                sample=dict(robot_id=identity,captured_at_ms=stamp,position_m=list(sensor),height_m=height,
                    sensor_frame=path,geometry={k:v for k,v in geometry.items() if k!='surfaces'},diagnostic=diagnostic)
                if self.scan_worker.submit(token,section,sensor):self.scan_job=sample
            except ValueError as exc:robot['scan']=None;robot['scan_error']=str(exc)
            robot['scan_prepare_s']=time.monotonic()-started
            robot['scan_prepare']=diagnostic
            return # Global one-slot worker, no per-robot queued jobs.

    def _navigation_scene(self,stage):
        imported=getattr(self,'environment_navigation',None)
        if imported is not None:
            return imported['targets'],imported['bounds'],imported['obstacles']
        from pxr import UsdGeom,Usd
        cache=UsdGeom.BBoxCache(Usd.TimeCode.Default(),[UsdGeom.Tokens.default_,UsdGeom.Tokens.render,UsdGeom.Tokens.guide])
        targets=[];floors=[];boxes=[]
        root=stage.GetPrimAtPath('/World/TwinPulse/Environment')
        for prim in Usd.PrimRange(root):
            if not (prim.IsA(UsdGeom.Mesh) or prim.IsA(UsdGeom.Cube) or prim.IsA(UsdGeom.Cylinder)):continue
            r=cache.ComputeWorldBound(prim).ComputeAlignedRange()
            if r.IsEmpty():continue
            lo,hi=r.GetMin(),r.GetMax();box=[float(lo[0]),float(lo[1]),float(hi[0]),float(hi[1])]
            if hi[2]<=.08 and box[2]-box[0]>1 and box[3]-box[1]>1:floors.append(box)
            if lo[2]<=.18<=hi[2] and hi[2]>.08 and box[0]<box[2] and box[1]<box[3]:boxes.append(box)
        visual=stage.GetPrimAtPath('/World/TwinPulse/Presentation/RoomModels')
        if visual:
            for prim in visual.GetChildren():
                kind=prim.GetCustomDataByKey('catalogKind');members=prim.GetCustomDataByKey('currentGeometryIds')
                if not kind or not members:continue
                ranges=[]
                for identity in members:
                    geometry=stage.GetPrimAtPath('/World/TwinPulse/Environment/'+identity)
                    if geometry:
                        r=cache.ComputeWorldBound(geometry).ComputeAlignedRange()
                        if not r.IsEmpty():ranges.append(r)
                if ranges:
                    bounds=[min(float(r.GetMin()[0]) for r in ranges),min(float(r.GetMin()[1]) for r in ranges),
                            max(float(r.GetMax()[0]) for r in ranges),max(float(r.GetMax()[1]) for r in ranges)]
                    targets.append(dict(id=prim.GetName().removeprefix('Item_'),kind=kind,label=kind+' '+prim.GetName().removeprefix('Item_'),bounds=bounds))
        if not floors:raise ValueError('NAVIGATION_FLOOR_BOUNDS_MISSING')
        if len(boxes)>128:raise ValueError('NAVIGATION_SCENE_BUDGET')
        bounds=max(floors,key=lambda b:(b[2]-b[0])*(b[3]-b[1]))
        return targets,bounds,boxes

    def _navigate(self,robot,task,stage,identity):
        from twinpulse_core.sim_fleet_navigation import approach_plan,next_leg
        navigation=robot.get('navigation')
        if navigation is None:
            navigation=dict(request_id=task['task_id'],state='PLANNING',target_kind=task['target_kind'],reason=None)
            robot['navigation']=navigation;robot['navigation_index']=0;robot['navigation_geometry_epoch']=self.navigation_geometry_epoch
            try:
                # _refresh_bounds already copied current USD geometry on this
                # update. A goal must not traverse USD again on Kit's thread.
                # The epoch check below still invalidates a changed scene.
                scene=self.navigation_scene
                if scene is None or self.navigation_scene_epoch!=(self.identity,self.navigation_geometry_epoch):
                    raise ValueError('NAVIGATION_SCENE_GEOMETRY_UNAVAILABLE')
                targets,bounds,boxes=scene['targets'],scene['bounds'],scene['obstacles']
                if not any(target['kind']==task['target_kind'] for target in targets):
                    raise ValueError('NAVIGATION_TARGET_MISSING')
                discs=[(*other['pose'][:2],.105) for key,other in self.robots.items() if key!=identity]
                if self.planner is None:
                    from concurrent.futures import ThreadPoolExecutor
                    self.planner=ThreadPoolExecutor(max_workers=1,thread_name_prefix='sim-object-plan')
                # Only pure copied geometry crosses this boundary; no USD or
                # mutation on the worker, and no wait on Kit's main thread.
                robot['navigation_future']=self.planner.submit(approach_plan,list(robot['pose']),task['target_kind'],targets,bounds,boxes,discs,
                    observed_cells=(self.environment_navigation['cells'] if getattr(self,'environment_navigation',None) is not None else None))
            except ValueError as exc:
                navigation.update(state='FAILED',reason=str(exc));return None,0.,str(exc)
        if robot.get('navigation_geometry_epoch')!=self.navigation_geometry_epoch:
            navigation.update(state='FAILED',reason='NAVIGATION_SCENE_CHANGED');return None,0.,'NAVIGATION_SCENE_CHANGED'
        future=robot.get('navigation_future')
        if navigation['state']=='PLANNING':
            if future is None or not future.done():return None,0.,None
            try:plan=future.result()
            except ValueError as exc:
                navigation.update(state='FAILED',reason=str(exc));return None,0.,str(exc)
            except Exception as exc:
                reason='NAVIGATION_PLANNER_ERROR_'+type(exc).__name__
                navigation.update(state='FAILED',reason=reason);return None,0.,reason
            navigation.update({key:value for key,value in plan.items() if key in {'target_id','target_label','goal_xy','waypoints','path_length_m','clearance_m'}})
            navigation['state']='RUNNING'
        direction,remaining,index=next_leg(robot['pose'],navigation['waypoints'],robot['navigation_index'])
        robot['navigation_index']=index
        navigation['waypoint_index']=index
        navigation['remaining_m']=sum(math.dist(a,b) for a,b in zip([robot['pose'][:2],*navigation['waypoints'][index:]],navigation['waypoints'][index:]))
        if direction is None:
            navigation.update(state='ARRIVED',reason='NAVIGATION_ARRIVED');return None,0.,'NAVIGATION_ARRIVED'
        return direction,remaining,None

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
        root='/World/TwinPulse/Environment';visual='/World/TwinPulse/Presentation/RoomModels'
        for value in list(notice.GetResyncedPaths())+list(notice.GetChangedInfoOnlyPaths()):
            text=str(value.GetPrimPath())
            if text=='/' or text==root or text.startswith(root+'/') or root.startswith(text+'/') or text==visual or text.startswith(visual+'/') or visual.startswith(text+'/'):
                self.bounds_dirty=True;self.navigation_geometry_epoch+=1;break

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
            boxes=self._bounds(stage)
            if not self.bounds_watch and boxes!=self.obstacles:self.navigation_geometry_epoch+=1
            self.obstacles=boxes;self.scan_at=now;self.bounds_dirty=False;self.bounds_rebuilds+=1
        key=(self.identity,self.navigation_geometry_epoch)
        if self.navigation_scene_epoch!=key:
            self.navigation_scene=None;self.navigation_scene_epoch=key
            try:
                targets,bounds,boxes=self._navigation_scene(stage)
                self.navigation_scene=dict(epoch=self.navigation_geometry_epoch,targets=targets,bounds=bounds,obstacles=boxes)
                if self.environment_navigation is not None:
                    from twinpulse_core.navigation_grid import encode_navigation_grid
                    root=stage.GetPrimAtPath('/World/TwinPulse/Environment')
                    self.navigation_scene.update(schema='scene-navigation-2.0',
                        source_sha256=root.GetCustomDataByKey('twinpulseEnvironmentSource'),scene_revision=self.identity[2],
                        units_basis=root.GetCustomDataByKey('twinpulseEnvironmentUnitsBasis'),
                        meters_per_unit=root.GetCustomDataByKey('twinpulseEnvironmentMetersPerUnit'),
                        grid=encode_navigation_grid(self.environment_navigation['cells']))
            except ValueError:pass # Missing geometry cannot authorize a route.

    def receive(self,value,received_at=None):
        self.desired=value;self.received_at=time.monotonic() if received_at is None else received_at
        # Called only by Kit's main thread. Consume each bounded I/O snapshot's
        # admission boundary even when only the final snapshot is rendered.
        if value and self.identity and value.get('applied_revision')==self.identity[2]:
            now=time.monotonic();now_ms=time.time()*1000
            for request in value['robots']:
                robot=self.robots.get(request['robot_id'])
                if robot and robot['epoch']==request['connection_epoch'] and robot['motion_epoch']==request['motion_epoch']:
                    enabled=request.get('lidar',False)
                    if enabled!=robot.get('scan_enabled',False):
                        robot['scan_generation']=robot.get('scan_generation',0)+1;robot['scan_enabled']=enabled
                        if not enabled:robot['scan']=None
                    bind_intent(robot,request.get('intent'),now_ms,received_at=self.received_at,now=now)
                    if not robot.get('startup_ready',False):
                        robot.update(last_intent=None,intent_active_since=None)
                        task=request.get('task')
                        if task:robot['warm_rejected_task']=task['task_id']

    def _bounds(self,stage):
        from pxr import UsdGeom, Usd
        root=stage.GetPrimAtPath('/World/TwinPulse/Environment')
        if not root:return []
        self.environment_navigation=None
        if root.GetCustomDataByKey('twinpulseEnvironmentSource'):
            from twinpulse_app.lidar_scene_geometry import mesh_triangles
            from twinpulse_core.environment_navigation import navigation_cells
            meshes=[]
            for obj in root.GetChildren():
                geom=stage.GetPrimAtPath(str(obj.GetPath())+'/geometry')
                triangles=mesh_triangles(geom)
                meshes.append(dict(id=obj.GetName(),category=obj.GetCustomDataByKey('environmentCategory'),
                    label=obj.GetCustomDataByKey('environmentLabel'),points_m=[list(p) for t in triangles for p in t],
                    triangles=[[i,i+1,i+2] for i in range(0,len(triangles)*3,3)],
                    synthetic_keepout=bool(obj.GetCustomDataByKey('syntheticKeepout'))))
            self.environment_navigation=navigation_cells(meshes)
            return self.environment_navigation['manual_boxes']
        cache=UsdGeom.BBoxCache(Usd.TimeCode.Default(),[UsdGeom.Tokens.default_]);boxes=[]
        for prim in Usd.PrimRange(root):
            if prim.IsA(UsdGeom.Mesh) or prim.IsA(UsdGeom.Cube) or prim.IsA(UsdGeom.Cylinder):
                if len(boxes)>=512:break
                bounds=cache.ComputeWorldBound(prim).ComputeAlignedRange();lo,hi=bounds.GetMin(),bounds.GetMax()
                # Retained motion-guard slice; independent of the model-mounted
                # geometric sensing plane. This change does not relax driving.
                if lo[2] <= .18 <= hi[2] and hi[2]>.08:
                    boxes.append((float(lo[0]),float(lo[1]),float(hi[0]),float(hi[1])))
        return boxes

    @staticmethod
    def _gap(pose,box):
        x,y,_=pose;a,b,c,d=box
        return math.hypot(max(a-x,0,x-c),max(b-y,0,y-d))-SIM_BODY_RADIUS_M

    def update(self,snapshot):
        import omni.usd
        from pxr import Gf, UsdGeom
        stage=omni.usd.get_context().get_stage()
        if stage is None:return
        now=time.monotonic();dt=max(0,now-self.updated_at);self.updated_at=now
        identity=(snapshot.engine_session_id,snapshot.stage_epoch,snapshot.applied_revision)
        if identity!=self.identity:
            self.identity=identity;self.robots={};self.report=[];self.anchors=[];self.desired=None
            self.navigation_scene=None;self.navigation_scene_epoch=None;self.scene_produced_at=None
            if stage.GetPrimAtPath(self.ROOT):stage.RemovePrim(self.ROOT)
            self.route_key=None
            self._watch_environment(stage)
        fleet=self.desired
        if not snapshot.applied_revision or not fleet or fleet.get('applied_revision')!=snapshot.applied_revision:return
        if not stage.GetPrimAtPath('/World/TwinPulse'):return
        bounds_started=time.monotonic();self._refresh_bounds(stage,now)
        bounds_elapsed=max(0.,time.monotonic()-bounds_started)
        self.scene_produced_at=now
        rows=fleet['robots'];wanted={row['robot_id'] for row in rows}
        for identity in set(self.robots)-wanted:
            stage.RemovePrim(self.ROOT+'/Robot_'+identity);del self.robots[identity]
        self.sequence+=1;report=[]
        self._collect_scan(rows)
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
                bounds=UsdGeom.BBoxCache(0,[UsdGeom.Tokens.default_,UsdGeom.Tokens.render]).ComputeRelativeBound(model,placement.GetPrim()).ComputeAlignedRange()
                robot['model_local_corners']=None if bounds.IsEmpty() else [list(bounds.GetCorner(i)) for i in range(8)]
                self.robots[identity]=robot
            model_elapsed=max(0.,time.monotonic()-model_started) if created else 0.
            # Do not count the first report's dt: it predates authoring.
            observe_startup(robot,created,dt,self.snapshot_capture_pending)
            if robot['motion_epoch']!=request['motion_epoch']:
                future=robot.pop('navigation_future',None)
                if future:future.cancel()
                robot['navigation']=None
                active_dt=0.
                robot.update(motion_epoch=request['motion_epoch'],reason=None,task=None,travel=0.,intent_sequence=None,
                             last_intent=None,stale_intent_sequence=None,intent_active_since=None,warm_rejected_task=None)
                robot.pop('first_fault',None)
                robot['scan']=None;robot['scan_generation']=robot.get('scan_generation',0)+1
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
                future=robot.pop('navigation_future',None)
                if future:future.cancel()
                robot['navigation']=None
                robot.update(task=None,travel=0.)
            if request.get('visual_only'):
                # Pure visualization. No intent, synthetic sensor, physical
                # pose/connection report or permission is manufactured here.
                robot.update(pose=list(request['position_m']),task=None,travel=0.,scan=None,reason=None)
                placement=UsdGeom.Xform(stage.GetPrimAtPath(path));ops=placement.GetOrderedXformOps()
                ops[0].Set(Gf.Vec3d(robot['pose'][0],robot['pose'][1],0.));ops[1].Set(math.degrees(robot['pose'][2]))
                continue
            if task and robot['task']!=task['task_id']:
                future=robot.pop('navigation_future',None)
                if future:future.cancel()
                robot['navigation']=None
                if reason not in {'ISAAC_UPDATE_STALLED','ISAAC_TRANSPORT_STALE'}:
                    robot.update(task=task['task_id'],travel=0.,reason=None);reason=None
                active_dt=0.
            navigation_started=time.monotonic()
            if (dt>=.5 or time.monotonic()-now>=.5) and (intent or task):reason='ISAAC_UPDATE_STALLED'
            if not robot.get('startup_ready',False):
                # No buffering, renewal or later replay of premature commands.
                direction=None;intent=None;task=None
            elif now-self.received_at<.5 and not reason:
                if task:
                    if time.time()*1000>=task['deadline_ms']:reason='TASK_TIMEOUT'
                    elif task.get('kind')=='navigate':
                        direction,nav_remaining,reason=self._navigate(robot,task,stage,identity)
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
            navigation_elapsed=max(0.,time.monotonic()-navigation_started)
            if direction and time.monotonic()-self.received_at>=.5:
                reason='ISAAC_TRANSPORT_STALE';direction=None
            substeps=0;integrated_s=0.
            if direction:
                boxes=list(self.obstacles)
                for other_id,other in self.robots.items():
                    if other_id!=identity:
                        x,y,_=other['pose'];boxes.append((x-.105,y-.105,x+.105,y+.105))
                new,distance,stopped,substeps=integrate_motion(robot['pose'],direction,active_dt,boxes,
                    nav_remaining if task and task.get('kind')=='navigate' else max(0.,task['amount']-robot['travel']) if task else None)
                robot['pose']=new;robot['travel']+=distance
                integrated_s=distance/(.05 if direction in {'forward','backward'} else .30)
                if stopped:reason='ISAAC_UPDATE_STALLED' if stopped=='INPUT_STALE' and active_dt>=.5 else stopped
                elif task and task.get('kind')!='navigate' and robot['travel']>=task['amount']-1e-12:reason='TASK_COMPLETED'
            if reason=='INPUT_STALE' and robot.get('stale_intent_sequence') is None:
                robot['stale_intent_sequence']=robot.get('intent_sequence')
            work=dict(bounds_s=round(bounds_elapsed,6),model_authoring_s=round(model_elapsed,6),bounds_rebuilds=self.bounds_rebuilds,
                scan_s=round(robot.get('scan_compute_s',0.),6),scan_error=robot.get('scan_error'),
                navigation_s=round(navigation_elapsed,6),update_s=round(time.monotonic()-now,6),host=dict(self.host_timing))
            if reason in {'ISAAC_UPDATE_STALLED','ISAAC_TRANSPORT_STALE'} and not robot.get('first_fault'):
                # The report is latest-only, but the FIRST trigger is immutable
                # for this motion epoch. A later 32ms update must not overwrite
                # the original 500ms gap and its preceding work.
                from copy import deepcopy
                robot['first_fault']=dict(schema='fleet-first-fault-1.0',reason=reason,
                    observed_monotonic_s=now,observed_at_ms=time.time()*1000,elapsed_s=dt,
                    current_work=deepcopy(work),previous_work=deepcopy(robot.get('previous_work')),
                    motion_epoch=request['motion_epoch'],task_id=task.get('task_id') if task else None)
            robot['reason']=reason
            placement=UsdGeom.Xform(stage.GetPrimAtPath(path));ops=placement.GetOrderedXformOps()
            ops[0].Set(Gf.Vec3d(robot['pose'][0],robot['pose'][1],0.));ops[1].Set(math.degrees(robot['pose'][2]))
            # Read authored USD transform back: telemetry reflects the actual scene.
            matrix=placement.ComputeLocalToWorldTransform(0);p=matrix.ExtractTranslation()
            measured=[float(p[0]),float(p[1]),math.radians(float(ops[1].Get()))]
            if robot.get('scan_token')!=self._scan_token(identity,robot):robot['scan']=None
            if not request['lidar']:
                robot['scan']=None
                if robot.get('scan_enabled',False):robot['scan_generation']=robot.get('scan_generation',0)+1
            robot['scan_enabled']=request['lidar']
            work.update(scan_s=0.,scan_worker=robot.get('scan_diagnostic'),scan_worker_worst=robot.get('scan_worst'),
                scan_prepare_s=robot.get('scan_prepare_s',0.),scan_error=robot.get('scan_error'),update_s=round(time.monotonic()-now,6))
            robot['previous_work']=work
            report.append(dict(robot_id=identity,connection_epoch=robot['epoch'],motion_epoch=robot['motion_epoch'],
                sequence=self.sequence,position_m=measured,scan=robot['scan'],reason=reason,task_id=robot['task'],
                runtime_timing=dict(elapsed_s=round(dt,6),integrated_s=round(integrated_s,6),substeps=substeps),
                runtime_startup=dict(model_authored=True,render_observed=robot.get('render_observed',False),
                    snapshot_capture_pending=self.snapshot_capture_pending,post_author_updates=robot.get('startup_samples',0),ready=robot.get('startup_ready',False)),
                runtime_work=work,runtime_fault=robot.get('first_fault'),
                navigation=dict(robot['navigation']) if robot.get('navigation') else None,
                intent_sequence=robot.get('stale_intent_sequence') if reason=='INPUT_STALE' else robot.get('intent_sequence')))
            robot['selected']=request.get('selected',False)
        self.report=report
        try:self._draw_route(stage,fleet.get('route'))
        except Exception as exc:self.route_error=type(exc).__name__  # display only; never stops the fleet
        try:self._draw_lidar_layer(stage,fleet.get('lidar_layer'))
        except Exception as exc:self.route_error=type(exc).__name__  # display only; never stops the fleet
        self._schedule_scan(stage,rows,now)
        for row in report:
            robot=self.robots[row['robot_id']]
            row['runtime_work'].update(scan_prepare_s=robot.get('scan_prepare_s',0.),
                scan_prepare=robot.get('scan_prepare'),update_s=round(time.monotonic()-now,6))

    # Seven-segment strokes for stop numbers drawn on the floor (unit box 0..1 x 0..2).
    SEGMENTS=dict(a=((0,2),(1,2)),b=((1,2),(1,1)),c=((1,1),(1,0)),d=((0,0),(1,0)),e=((0,0),(0,1)),f=((0,1),(0,2)),g=((0,1),(1,1)))
    DIGITS={'0':'abcdef','1':'bc','2':'abged','3':'abgcd','4':'fgbc','5':'afgcd','6':'afgedc','7':'abc','8':'abcdefg','9':'abcdfg'}

    def _draw_route(self,stage,route):
        """Declared-route overlay: planned path, numbered stops, odometry trace, per-stop LiDAR, candidates.

        Display only (declared start + wheel odometry, not localized). It never
        feeds navigation bounds, scans or any robot report.
        """
        from pxr import Gf, UsdGeom
        path=self.ROOT+'/Route'
        if not route:
            if getattr(self,'route_key',None) is not None and stage.GetPrimAtPath(path):stage.RemovePrim(path)
            self.route_key=None;return
        if route.get('unchanged'):return  # backend sends the full overlay on change and every 2 s
        # The revision changes on every runner update (the trace length alone stops
        # changing at its cap); the key is adopted only after a complete draw so a
        # mid-draw exception cannot freeze a partial overlay.
        key=(route['plan_id'],route.get('revision'),route.get('state'),route.get('reached'),str(route.get('reached_stops')),len(route.get('live_scan') or []),
             len(route.get('trace') or []),len(route.get('scans') or []),
             str(route.get('candidates')),len(route.get('polyline') or []),str(route.get('keepouts')))
        if key==getattr(self,'route_key',None) and stage.GetPrimAtPath(path):return
        if getattr(self,'route_key',None) is None or self.route_key[0]!=route['plan_id'] or not stage.GetPrimAtPath(path):
            if stage.GetPrimAtPath(path):stage.RemovePrim(path)
        self._draw_route_prims(stage,route,path)
        self.route_key=key;self.route_error=None

    def _draw_lidar_layer(self,stage,layer):
        """Session LiDAR layer: stop-scan and during-drive returns of finished routes plus LiDAR-moved object markers.

        Display only (declared start + wheel odometry, not registered); it outlives the route overlay until the
        user clears it and never feeds navigation bounds, scans or any robot report.
        """
        from pxr import Gf, UsdGeom
        path=self.ROOT+'/LidarLayer'
        if not layer:
            if stage.GetPrimAtPath(path):stage.RemovePrim(path)
            self.layer_key=None;return
        if layer.get('unchanged'):return
        key=(layer.get('scene_revision'),layer.get('revision'))
        if key==getattr(self,'layer_key',None) and stage.GetPrimAtPath(path):return
        root=UsdGeom.Xform.Define(stage,path).GetPrim()
        root.SetCustomDataByKey('source',layer.get('label') or 'DECLARED_START_PLUS_ODOMETRY_DISPLAY_ONLY_NOT_REGISTERED')
        root.SetCustomDataByKey('motionAuthorized',False);root.SetCustomDataByKey('routes',int(layer.get('routes') or 0))
        for name,points,color,width,z in (('StopPoints',layer.get('stop_points') or [],(.2,.9,1.),.05,.17),
                                          ('DrivePoints',layer.get('drive_points') or [],(.75,.7,.3),.035,.15)):
            prim=path+'/'+name
            if not points:
                if stage.GetPrimAtPath(prim):stage.RemovePrim(prim)
                continue
            cloud=UsdGeom.Points.Define(stage,prim)
            cloud.CreatePointsAttr([Gf.Vec3f(float(p[0]),float(p[1]),z) for p in points])
            cloud.CreateWidthsAttr([width]*len(points))
            cloud.CreateDisplayColorAttr([Gf.Vec3f(*color)])
        moved=layer.get('moved') or [];prim=path+'/MovedObjects'
        if moved:
            def ring(x,y,r,n=24):return [(x+r*math.cos(i*math.tau/n),y+r*math.sin(i*math.tau/n)) for i in range(n+1)]
            strokes=[ring(m['position_xy_m'][0],m['position_xy_m'][1],.22) for m in moved]
            curve=UsdGeom.BasisCurves.Define(stage,prim)
            curve.CreateTypeAttr('linear');curve.CreateCurveVertexCountsAttr([len(s) for s in strokes])
            curve.CreatePointsAttr([Gf.Vec3f(float(p[0]),float(p[1]),.2) for s in strokes for p in s])
            curve.CreateWidthsAttr([.05]);curve.SetWidthsInterpolation('constant')
            curve.CreateDisplayColorAttr([Gf.Vec3f(.75,.35,1.)])
            curve.GetPrim().SetCustomDataByKey('source','OBJECT_MOVED_TO_LIDAR_ESTIMATE_UNVERIFIED')
        elif stage.GetPrimAtPath(prim):stage.RemovePrim(prim)
        self.layer_key=key

    def _draw_route_prims(self,stage,route,path):
        from pxr import Gf, UsdGeom
        root=UsdGeom.Xform.Define(stage,path).GetPrim()
        for k,v in (('planId',route['plan_id']),('poseStatus',route.get('label') or 'NOT_LOCALIZED'),('state',str(route.get('state')))):
            root.SetCustomDataByKey(k,v)
        root.SetCustomDataByKey('motionAuthorized',False)
        def curves(name,strokes,color,width,z):
            strokes=[s for s in strokes if len(s)>=2]
            prim=path+'/'+name
            if not strokes:
                if stage.GetPrimAtPath(prim):stage.RemovePrim(prim)
                return
            curve=UsdGeom.BasisCurves.Define(stage,prim)
            curve.CreateTypeAttr('linear')
            curve.CreateCurveVertexCountsAttr([len(s) for s in strokes])
            curve.CreatePointsAttr([Gf.Vec3f(float(p[0]),float(p[1]),z) for s in strokes for p in s])
            curve.CreateWidthsAttr([width]);curve.SetWidthsInterpolation('constant')
            curve.CreateDisplayColorAttr([Gf.Vec3f(*color)])
        def ring(x,y,r,n=24):return [(x+r*math.cos(i*math.tau/n),y+r*math.sin(i*math.tau/n)) for i in range(n+1)]
        def digit(text,x,y,h=.4):
            out=[];w=h/2;ox=x-(len(text)*(w+.06)-.06)/2
            for i,ch in enumerate(text):
                for seg in self.DIGITS.get(ch,''):
                    (a,b),(c,d)=self.SEGMENTS[seg];bx=ox+i*(w+.06)
                    out.append([(bx+a*w,y+b*h/2-h/2),(bx+c*w,y+d*h/2-h/2)])
            return out
        reached=route.get('reached') or 0
        done_set=set(route['reached_stops']) if isinstance(route.get('reached_stops'),list) else set(range(reached))
        skipped_set=set(route.get('skipped_stops') or [])
        curves('Path',[route.get('polyline') or []],(1.,.72,.15),.06,.02)
        curves('Trace',[route.get('trace') or []],(.1,.85,.45),.05,.03)
        stops_todo=[];stops_done=[];stops_skipped=[];labels=[]
        for i,(x,y) in enumerate(route.get('waypoints') or []):
            (stops_done if i in done_set else stops_skipped if i in skipped_set else stops_todo).append(ring(x,y,.2))
            labels+=digit(str(i+1),x,y+.5)
        sx,sy=route['start'][:2]
        curves('Stops',stops_todo,(1.,.55,.1),.06,.025)
        curves('StopsReached',stops_done,(.1,.85,.45),.06,.026)
        curves('StopsSkipped',stops_skipped,(.6,.6,.6),.04,.026)
        curves('StopNumbers',labels,(.1,.1,.1),.06,.04)
        curves('Start',[ring(sx,sy,.2),[(sx,sy),(sx+.3*math.cos(route['start'][2]),sy+.3*math.sin(route['start'][2]))]],(.9,.9,.9),.035,.025)
        curves('Keepouts',[ring(d[0],d[1],d[2]) for d in route.get('keepouts') or []],(.9,.25,.25),.02,.02)
        curves('Candidates',[ring(c['position_xy_m'][0],c['position_xy_m'][1],c['radius_m']+.05) for c in route.get('candidates') or []],(1.,.15,.6),.05,.05)
        live=route.get('live_scan') or []
        prim=path+'/LiveScan'
        if live and route.get('state')=='RUNNING':
            cloud=UsdGeom.Points.Define(stage,prim)
            cloud.CreatePointsAttr([Gf.Vec3f(float(p[0]),float(p[1]),.16) for p in live])
            cloud.CreateWidthsAttr([.045]*len(live))
            cloud.CreateDisplayColorAttr([Gf.Vec3f(1.,.95,.3)])
            cloud.GetPrim().SetCustomDataByKey('source','LIVE_LIDAR_AT_ODOMETRY_POSE_NOT_REGISTERED')
        elif stage.GetPrimAtPath(prim):stage.RemovePrim(prim)
        points=[p for s in route.get('scans') or [] for p in s.get('points') or []]
        prim=path+'/StopScans'
        if points:
            cloud=UsdGeom.Points.Define(stage,prim)
            cloud.CreatePointsAttr([Gf.Vec3f(float(p[0]),float(p[1]),.18) for p in points])
            cloud.CreateWidthsAttr([.06]*len(points))
            cloud.CreateDisplayColorAttr([Gf.Vec3f(.2,.9,1.)])
            cloud.GetPrim().SetCustomDataByKey('source','PHYSICAL_LIDAR_AT_ODOMETRY_POSE_NOT_REGISTERED' if route.get('kind')=='physical' else 'SIM_LIDAR')
        elif stage.GetPrimAtPath(prim):stage.RemovePrim(prim)

    def frame_anchors(self,viewport):
        self.frame_scan=None
        if not self.robots:return []
        from pxr import Gf, UsdGeom
        import omni.usd
        stage=omni.usd.get_context().get_stage();camera=UsdGeom.Camera(stage.GetPrimAtPath(str(viewport.camera_path)))
        if not camera:return []
        frustum=camera.GetCamera(0).frustum;view=frustum.ComputeViewMatrix();projection=frustum.ComputeProjectionMatrix();out=[]
        def project(world):
            if view.Transform(world)[2]>=0:return None
            p=(view*projection).Transform(world);return [float((p[0]+1)/2),float((1-p[1])/2)]
        for identity,robot in self.robots.items():
            corners=robot.get('model_local_corners')
            if not corners:continue
            matrix=UsdGeom.Xform(stage.GetPrimAtPath(self.ROOT+'/Robot_'+identity)).ComputeLocalToWorldTransform(0)
            points=[project(matrix.Transform(Gf.Vec3d(*p))) for p in corners]
            points=[p for p in points if p is not None]
            if not points:continue
            a,b=min(p[0] for p in points),min(p[1] for p in points);c,d=max(p[0] for p in points),max(p[1] for p in points)
            u,v=(a+c)/2,(b+d)/2
            if 0<=u<=1 and 0<=v<=1 and a<c and b<d:
                out.append(dict(robot_id=identity,screen_anchor_uv=[u,v],
                    screen_bounds_uv=[max(0.,a),max(0.,b),min(1.,c),min(1.,d)],visible=True))
            scan=robot.get('scan')
            if robot.get('selected') and scan and 0<=time.time()*1000-scan.get('captured_at_ms',0)<350:
                x,y,yaw=scan['position_m'];height=scan['height_m'];origin=project(Gf.Vec3d(x,y,height));hits=[]
                for px,py in scan['points'][::2]:
                    hit=project(Gf.Vec3d(x+px*math.cos(yaw)-py*math.sin(yaw),y+px*math.sin(yaw)+py*math.cos(yaw),height))
                    if hit and all(0<=n<=1 for n in hit):hits.append(hit)
                if origin and all(0<=n<=1 for n in origin):
                    self.frame_scan=dict(robot_id=identity,connection_epoch=robot['epoch'],motion_epoch=robot['motion_epoch'],origin_uv=origin,points_uv=hits[:90],
                        captured_at_ms=scan['captured_at_ms'],source='isaac_usd_surface_rays',physical_authority=False,
                        height_m=height)
        return out
