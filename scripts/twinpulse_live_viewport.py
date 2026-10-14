# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Latest-only Kit buffer capture and separate outbound display I/O thread.

USD and viewport scheduling occur only on Kit's main thread. Display failures
never renew a control lease, issue a motion command, or change bridge watchdogs.
"""
import base64
import asyncio
import ctypes
from io import BytesIO
import math
from threading import Event, Lock, Thread
import time


class LiveViewportPublisher:
    # USD Build acknowledgement precedes asynchronous Hydra/GPU presentation.
    # Never label the immediately previous render buffer as the new revision.
    # Count subsequent Kit updates, not a wall-clock sleep or photo heuristic.
    RENDER_WARMUP_UPDATES = 5

    def __init__(self, bridge):
        self.bridge = bridge
        self.lock = Lock(); self.stop_event = Event(); self.thread = None
        self.raw = None; self.camera = None; self.camera_result = None
        self.capture = None; self.started_capture = 0.; self.last_capture = 0.
        self.capture_handle = None; self.capture_wait = None
        self.capture_ticket = 0; self.retired_captures = set()
        self.capture_timeouts = 0; self.capture_recoveries = 0
        self.sequence = 0; self.camera_sequence = 0
        self.last_error = None; self.sent = 0; self.dropped = 0
        self.transport_error = None
        self.render_identity = None; self.render_updates = 0; self.render_epoch = 0

    def _begin_render_epoch(self, identity):
        with self.lock:
            self.render_identity = identity; self.render_updates = 0; self.render_epoch += 1
            if self.raw is not None: self.dropped += 1
            self.raw = None

    def _queue_capture(self, epoch, metadata, width, height, data):
        with self.lock:
            if epoch != self.render_epoch:
                self.dropped += 1
                return False  # A callback scheduled before Build/camera transition.
            if self.raw is not None: self.dropped += 1
            self.raw = (metadata,width,height,data,epoch)
            return True

    def start(self):
        self.thread = Thread(target=self._io, name='TwinPulseViewportIO', daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread: self.thread.join(timeout=3.)
        self.thread = None
        if self.capture_wait and not self.capture_wait.done():self.capture_wait.cancel()

    def _retire_completed_capture(self, now):
        """Recover a consumed delegate whose GPU callback never arrived.

        Keep at most two unacknowledged retired GPU deliveries. A delegate
        still waiting for the viewport is never requeued repeatedly.
        """
        if self.capture is None or now-self.started_capture<=3:return False
        self.last_error='viewport_capture_timeout'
        completed=self.capture_wait is not None and self.capture_wait.done()
        if not completed or len(self.retired_captures)>=2:return False
        if not self.capture_wait.cancelled():self.capture_wait.exception()
        self.retired_captures.add(self.capture_ticket)
        self.capture=None;self.capture_handle=None;self.capture_wait=None
        self.capture_timeouts+=1;self.capture_recoveries+=1
        return True

    def update(self, snapshot):
        from omni.kit.viewport.utility import capture_viewport_to_buffer, get_active_viewport
        identity = (snapshot.engine_session_id,snapshot.stage_epoch,snapshot.applied_revision,
                    getattr(self.bridge.adapter,'display_build_id',None))
        transition = identity != self.render_identity
        if transition: self._begin_render_epoch(identity)
        with self.lock: camera = self.camera; self.camera = None
        if camera:
            result = {'request_id':camera['request_id'],'state':'failed','code':'camera_identity_stale'}
            if ((camera['engine_session_id'],camera['stage_epoch'],camera['applied_revision']) ==
                    (snapshot.engine_session_id,snapshot.stage_epoch,snapshot.applied_revision)):
                try:
                    self._camera_action(camera['action'])
                    self.camera_sequence += 1
                    self._begin_render_epoch(identity); transition = True
                    result.update(state='completed',code='camera_applied')
                except Exception as exc:
                    result['code'] = 'camera_'+type(exc).__name__[:60]
            with self.lock: self.camera_result = result
        now = time.monotonic()
        if not transition: self.render_updates += 1
        # A single pending GPU capture: no accumulating futures or render jobs.
        if self.capture is not None:
            if not self._retire_completed_capture(now):return
        if len(self.retired_captures)>=2:
            self.last_error='viewport_capture_stalled';return
        if transition or self.render_updates < self.RENDER_WARMUP_UPDATES:
            return
        if now-self.last_capture < .14 or snapshot.applied_revision is None or not self.bridge.connected:
            return
        viewport = get_active_viewport()
        if viewport is None: self.last_error = 'viewport_missing'; return
        viewport.resolution = (960,640)
        self.sequence += 1
        metadata = {'frame_id':self.sequence,'engine_session_id':snapshot.engine_session_id,
                    'stage_epoch':snapshot.stage_epoch,'applied_revision':snapshot.applied_revision,
                    'captured_at_ms':time.time()*1000,'camera_sequence':self.camera_sequence}
        self.started_capture = self.last_capture = now
        # Mark pending before schedule_capture; callback may be synchronous.
        self.capture = True
        self.capture_ticket += 1
        ticket=self.capture_ticket
        render_epoch = self.render_epoch
        def on_capture(buffer, size, width, height, byte_format):
            try:
                if ticket!=self.capture_ticket or render_epoch!=self.render_epoch:
                    self.dropped+=1;return
                if not 64 <= width <= 1280 or not 64 <= height <= 960 or size != width*height*4:
                    raise ValueError('unsupported RGBA dimensions')
                pointer = ctypes.pythonapi.PyCapsule_GetPointer
                pointer.restype = ctypes.c_void_p
                pointer.argtypes = [ctypes.py_object,ctypes.c_char_p]
                data = ctypes.string_at(pointer(buffer,None),size)
                if self._queue_capture(render_epoch,metadata,width,height,data):
                    self.last_error = None
            except Exception as exc:
                self.last_error = 'viewport_buffer_'+type(exc).__name__[:60]
            finally:
                self.retired_captures.discard(ticket)
                if ticket==self.capture_ticket:
                    self.capture = None;self.capture_handle=None
                    if self.capture_wait and not self.capture_wait.done():self.capture_wait.cancel()
                    self.capture_wait=None
        try:
            handle=capture_viewport_to_buffer(viewport,on_capture,is_hdr=False)
            # Keep the public capture handle alive and observe completion.
            # A synchronous callback may already have cleared this ticket.
            if self.capture is not None and ticket==self.capture_ticket:
                self.capture_handle=handle
                if handle is None:
                    self.capture=None;self.last_error='viewport_capture_not_scheduled'
                elif hasattr(handle,'wait_for_result'):
                    self.capture_wait=asyncio.ensure_future(handle.wait_for_result(completion_frames=0))
        except Exception as exc:
            self.capture = None; self.last_error = 'viewport_schedule_'+type(exc).__name__[:60]

    @staticmethod
    def _camera_action(action):
        import omni.usd
        from pxr import Gf, UsdGeom
        from omni.kit.viewport.utility import get_active_viewport
        path = '/World/TwinPulse/Presentation/Camera'
        stage = omni.usd.get_context().get_stage()
        camera = UsdGeom.Camera(stage.GetPrimAtPath(path))
        if not camera: raise ValueError('owned camera missing')
        transform = camera.ComputeLocalToWorldTransform(0)
        eye = transform.ExtractTranslation()
        bound = UsdGeom.BBoxCache(0,[UsdGeom.Tokens.default_]).ComputeWorldBound(
            stage.GetPrimAtPath('/World/TwinPulse/Environment')).ComputeAlignedRange()
        stored = camera.GetPrim().GetCustomDataByKey('twinpulseViewerTarget')
        target = Gf.Vec3d(*stored) if stored is not None else bound.GetMidpoint()
        if stored is None: target[2] = min(target[2],.5)
        offset = eye-target
        if action.startswith('orbit_'):
            angle = math.radians(15 if action=='orbit_left' else -15)
            offset = Gf.Vec3d(offset[0]*math.cos(angle)-offset[1]*math.sin(angle),
                             offset[0]*math.sin(angle)+offset[1]*math.cos(angle),offset[2])
            eye = target+offset
        elif action.startswith('zoom_'):
            factor = .85 if action=='zoom_in' else 1/.85
            distance = offset.GetLength()
            eye = target+offset*(min(40.,max(.5,distance*factor))/max(distance,.001))
        else:
            direction = transform.TransformDir(Gf.Vec3d(1,0,0) if action in {'pan_left','pan_right'} else Gf.Vec3d(0,1,0))
            delta = direction*(-.25 if action in {'pan_left','pan_down'} else .25)
            eye += delta; target += delta
        up = Gf.Vec3d(0,1,0) if abs(offset[0])+abs(offset[1])<.01 else Gf.Vec3d(0,0,1)
        camera.ClearXformOpOrder()
        camera.AddTransformOp().Set(Gf.Matrix4d().SetLookAt(eye,target,up).GetInverse())
        camera.GetPrim().SetCustomDataByKey('twinpulseViewerTarget',target)
        get_active_viewport().camera_path = path

    def _io(self):
        from PIL import Image
        while not self.stop_event.wait(.08):
            if not self.bridge.connected: continue
            with self.lock:
                raw = self.raw; self.raw = None
                result = self.camera_result
            try:
                # snapshot() touches USD; use only the shared identity on this thread.
                with self.bridge._lock:
                    epoch = self.bridge._shared_stage_epoch
                frame = None
                if raw:
                    meta,width,height,data,capture_epoch = raw
                    if capture_epoch != self.render_epoch:
                        self.dropped += 1;continue
                    if time.time()*1000-meta['captured_at_ms']>900 or meta['stage_epoch']!=epoch:
                        self.dropped += 1; continue
                    image = Image.frombytes('RGBA',(width,height),data).convert('RGB')
                    output = BytesIO(); image.save(output,format='JPEG',quality=75)
                    encoded = output.getvalue()
                    if len(encoded)>180000: raise ValueError('frame byte budget')
                    frame = {k:v for k,v in meta.items() if k not in {'engine_session_id','stage_epoch'}}
                    frame.update(width=width,height=height,jpeg_base64=base64.b64encode(encoded).decode('ascii'))
                response = self.bridge._post('/v1/engine/viewport',{
                    'engine_session_id':self.bridge.adapter.engine_session_id,'stage_epoch':epoch,
                    'frame':frame,'camera_result':result})
                if frame: self.sent += 1
                with self.lock:
                    if self.camera_result == result: self.camera_result = None
                    command = response.get('camera')
                    if command and (not result or command['request_id']!=result['request_id']): self.camera = command
                self.transport_error = None
            except Exception as exc:
                self.transport_error = 'viewport_transport_'+type(exc).__name__[:60]
                # Display I/O has no access to heartbeat success or lease renewal.
