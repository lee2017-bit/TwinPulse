# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Fresh control receipt and one project-local static preview, kept separately."""
from __future__ import annotations

import base64
import binascii
from collections import deque
import hashlib
from io import BytesIO
import math
import re
from threading import RLock
import time

from .command_broker import BrokerError


class ViewportService:
    def __init__(self, broker, *, clock=time.monotonic, wall_clock=time.time):
        self.broker = broker
        self.clock, self.wall_clock = clock, wall_clock
        self.lock = RLock()
        self.latest = None
        self.last_preview = None
        self.sequence = -1
        self.identity = None
        self.received = 0.0
        self.arrivals = deque(maxlen=40)
        # Small metadata-only history permits a camera click on the displayed
        # frame while a newer render arrives. Never retain old image bytes.
        self.observed_frames = deque(maxlen=64)
        self.browser_failures = {}
        self.camera = None
        self.camera_result = None
        self.requests = {}
        self.last_camera_at = -math.inf
        self.static_preview_loader=None
        self.restored_preview_binding=None

    def _current(self):
        state = self.broker.supervisor_state()
        snap = state.get('snapshot') or {}
        identity = (state.get('engine_session_id'), state.get('stage_epoch'), snap.get('applied_revision'))
        return state, identity

    def exchange(self, engine_id, stage_epoch, body):
        if set(body) != {'engine_session_id', 'stage_epoch', 'frame', 'camera_result'}:
            raise BrokerError('viewport_shape_invalid', 'Viewport request shape is invalid', status=400)
        state, identity = self._current()
        if not state['engine_connected'] or identity[:2] != (engine_id, stage_epoch):
            raise BrokerError('viewport_identity_stale', 'Viewport engine identity is no longer current', status=409)
        with self.lock:
            if identity != self.identity:
                self.latest = None; self.sequence = -1; self.arrivals.clear(); self.observed_frames.clear()
                self.camera = None; self.camera_result = None; self.identity = identity
            frame = body['frame']
            if frame is not None:
                required = {'frame_id', 'applied_revision', 'captured_at_ms', 'width', 'height', 'jpeg_base64', 'camera_sequence'}
                if not isinstance(frame, dict) or not required<=set(frame) or set(frame)-required-{'robot_anchors','lidar_overlay'}:
                    raise BrokerError('viewport_frame_invalid', 'Viewport frame shape is invalid', status=400)
                anchors=frame.get('robot_anchors',[])
                if (not isinstance(anchors,list) or len(anchors)>16 or any(not isinstance(a,dict)
                        or set(a)!={'robot_id','screen_anchor_uv','screen_bounds_uv','visible'}
                        or not isinstance(a['robot_id'],str) or re.fullmatch(r'[a-zA-Z0-9_-]{1,100}',a['robot_id']) is None or type(a['visible']) is not bool
                        or any(not isinstance(a[key],list) or len(a[key])!=size or
                               any(type(n) not in (int,float) or not math.isfinite(n) or not 0<=n<=1 for n in a[key])
                               for key,size in (('screen_anchor_uv',2),('screen_bounds_uv',4))) for a in anchors)):
                    raise BrokerError('viewport_robot_anchors_invalid','Invalid bounded robot screen coordinates.',status=400)
                scan=frame.get('lidar_overlay')
                if scan is not None:
                    if (not isinstance(scan,dict) or not {'robot_id','origin_uv','points_uv','captured_at_ms','source','physical_authority'}<=set(scan)
                            or set(scan)-{'robot_id','origin_uv','points_uv','captured_at_ms','source','physical_authority','height_m','connection_epoch','motion_epoch'}
                            or not isinstance(scan['robot_id'],str) or re.fullmatch(r'[a-zA-Z0-9_-]{1,100}',scan['robot_id']) is None
                            or scan['source'] not in {'isaac_usd_aabb_rays','isaac_usd_surface_rays'} or scan['physical_authority'] is not False
                            or (scan['source']=='isaac_usd_surface_rays' and (type(scan.get('height_m')) not in (int,float) or not math.isfinite(scan['height_m']) or not 0<scan['height_m']<2))
                            or (scan['source']=='isaac_usd_surface_rays' and any(not isinstance(scan.get(k),str) or re.fullmatch(r'[a-zA-Z0-9_-]{1,100}',scan[k]) is None for k in ('connection_epoch','motion_epoch')))
                            or type(scan['captured_at_ms']) not in (int,float) or not math.isfinite(scan['captured_at_ms'])
                            or type(frame['captured_at_ms']) not in (int,float) or not -50<=frame['captured_at_ms']-scan['captured_at_ms']<=350
                            or not isinstance(scan['points_uv'],list) or len(scan['points_uv'])>90
                            or any(not isinstance(p,list) or len(p)!=2 or any(type(n) not in (int,float) or not math.isfinite(n) or not 0<=n<=1 for n in p)
                                   for p in [scan['origin_uv'],*scan['points_uv']])):
                        raise BrokerError('viewport_scan_invalid','Invalid frame-bound SIM scan overlay.',status=400)
                seq = frame['frame_id']
                stamp = frame['captured_at_ms']
                if (type(seq) is not int or seq <= self.sequence or seq > 2**53-1
                        or type(stamp) not in (int, float) or not math.isfinite(stamp)
                        or not -100 <= self.wall_clock()*1000-stamp <= 1000
                        or type(frame['camera_sequence']) is not int or frame['camera_sequence'] < 0
                        or frame['applied_revision'] is None or frame['applied_revision'] != identity[2]
                        or type(frame['width']) is not int or type(frame['height']) is not int
                        or not 64 <= frame['width'] <= 1280 or not 64 <= frame['height'] <= 960
                        or not isinstance(frame['jpeg_base64'], str) or len(frame['jpeg_base64']) > 240000):
                    raise BrokerError('viewport_frame_stale_or_invalid', 'Frame identity, dimensions or capture time is invalid', status=409)
                try:
                    from PIL import Image
                    data = base64.b64decode(frame['jpeg_base64'], validate=True)
                    with Image.open(BytesIO(data)) as image:
                        if image.format != 'JPEG' or image.size != (frame['width'], frame['height']):
                            raise ValueError('dimensions')
                        image.verify()
                except (ValueError, OSError, binascii.Error) as exc:
                    raise BrokerError('viewport_image_invalid', 'Invalid bounded JPEG frame', status=400) from exc
                # Recheck after decoding: a concurrent stage transition must not revive a frame.
                if self._current()[1] != identity:
                    raise BrokerError('viewport_identity_stale', 'Stage changed during frame reception', status=409)
                self.latest = {k:v for k,v in frame.items() if k != 'jpeg_base64'}
                self.latest.update(data=data, sha256=hashlib.sha256(data).hexdigest(),
                                   engine_session_id=engine_id, stage_epoch=stage_epoch)
                self.last_preview = dict(self.latest)
                self.sequence = seq; self.received = self.clock(); self.arrivals.append(self.received)
                self.observed_frames.append((seq, stamp, self.received))
                self.broker.record_current_frame(engine_id,stage_epoch,identity[2],seq,self.latest['sha256'])
            result = body['camera_result']
            if result is not None:
                if (not isinstance(result, dict) or set(result) != {'request_id','state','code'}
                        or not isinstance(result['state'], str) or result['state'] not in {'completed','failed'}
                        or not isinstance(result['code'], str) or len(result['code']) > 80):
                    raise BrokerError('viewport_camera_result_invalid', 'Invalid camera result', status=400)
                if self.camera and result['request_id'] == self.camera['request_id']:
                    self.camera_result = dict(result); self.camera = None
            command = self.camera
            if command and self.clock()-command['accepted_at'] > 2.0:
                self.camera_result = {'request_id':command['request_id'],'state':'failed','code':'camera_delivery_expired'}
                self.camera = command = None
            return {'camera': {k:v for k,v in command.items() if k != 'accepted_at'} if command else None}

    def report_browser_failure(self, owner, body):
        """Untrusted display observation, not an engine/robot safety verdict."""
        required={'frame_id','engine_session_id','stage_epoch','applied_revision','error_code'}
        codes={'viewport_http_error','viewport_image_invalid','viewport_decode_failed','viewport_draw_failed','viewport_decode_expired','viewport_image_expired'}
        if (type(body) is not dict or set(body) not in (required,required|{'timings'}) or type(body['frame_id']) is not int
                or body['frame_id']<0 or any(type(body[k]) is not str or not 1<=len(body[k])<=128
                    for k in ('engine_session_id','stage_epoch','applied_revision'))
                or type(body['error_code']) is not str or body['error_code'] not in codes):
            raise BrokerError('viewport_observation_invalid','Use a bounded display failure code',status=400)
        timings=body.get('timings',{})
        timing_keys={'metadata_ms','image_ms','decode_ms','poll_ms','frame_age_ms','schedule_lag_ms'}
        if 'timings' in body and (type(timings) is not dict or set(timings)!=timing_keys or
                any(type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=60000 for value in timings.values())):
            raise BrokerError('viewport_observation_invalid','Use bounded numeric browser timings',status=400)
        state,identity=self._current()
        with self.lock:
            if (not state['engine_connected'] or identity!=self.identity or
                    tuple(body[k] for k in ('engine_session_id','stage_epoch','applied_revision'))!=identity or
                    not any(seq==body['frame_id'] and self.clock()-received<5 for seq,_,received in self.observed_frames)):
                # A display failure describes the frame fetched earlier. A
                # concurrent Build may legitimately supersede it before this
                # optional diagnostic arrives. Do not record it against the new
                # scene, revive old pixels as live, or turn that race into a
                # product action error. All body/owner checks still precede it.
                return {'execution_id':None,'physical_authority':False,'source':'browser_reported',
                        'disposition':'discarded','reason':'scene_superseded'}
            key=(owner,*identity,body['error_code'])
            if key in self.browser_failures:return self.browser_failures[key]
            result={'execution_id':None,'physical_authority':False,'source':'browser_reported','disposition':'recorded'}
            store=self.broker.diagnostics
            if store is not None:
                command=self.broker.public_state(owner).get('build_view') or {}
                try:
                    trace=store.begin('browser_view_observation',durable=False,component='browser',
                        engine_session_id=identity[0],stage_epoch=identity[1],draft_revision=identity[2],
                        frame_id=body['frame_id'],error_code=body['error_code'],
                        command_execution_id=command.get('command_execution_id') or command.get('execution_id'),
                        command_id=command.get('command_id'),measurement_source='browser_reported',
                        **{'browser_'+key:value for key,value in timings.items()})
                    trace.child('browser_image_display').finish('failed',error_code=body['error_code'])
                    trace.finish('failed',error_code=body['error_code'])
                    result['execution_id']=trace.execution_id
                except (OSError,ValueError):
                    store.note_storage_error()  # Optional diagnosis never changes engine/control state.
            # One record per typed cause/owner/scene, not one per 7 Hz frame.
            self.browser_failures[key]=result
            while len(self.browser_failures)>64:self.browser_failures.pop(next(iter(self.browser_failures)))
            return result

    def status(self, *, restore_preview=True, probe=None):
        began=time.perf_counter()
        state, identity = self._current()
        after_broker=time.perf_counter()
        if probe is not None:probe['tp_view_broker']=(after_broker-began)*1000
        # Disk restoration is optional history, not part of the live frame
        # transport. Never enter the conversation/disk path from image_packet,
        # image or camera while holding the viewport mutex.
        with self.lock:
            first_wait=time.perf_counter()-after_broker
            needs_restore=restore_preview and self.latest is None
        before_restore=time.perf_counter()
        restored=self.static_preview_loader() if needs_restore and self.static_preview_loader else None
        after_restore=time.perf_counter()
        if probe is not None:probe['tp_view_restore']=(after_restore-before_restore)*1000
        with self.lock:
            after_lock=time.perf_counter()
            if probe is not None:probe['tp_view_wait']=(first_wait+after_lock-after_restore)*1000
            if self.latest is None and restored is not None:
                binding,frame=restored
                if binding!=self.restored_preview_binding or (frame is not None and self.last_preview is None):
                    self.last_preview=frame
                    self.restored_preview_binding=binding
            frame = self.latest
            if self.camera and (identity != self.identity or not state['engine_connected']
                                or self.clock()-self.camera['accepted_at'] > 2.0):
                self.camera_result = {'request_id':self.camera['request_id'],'state':'failed',
                                      'code':'camera_identity_stale' if identity != self.identity or not state['engine_connected']
                                      else 'camera_delivery_expired'}
                self.camera = None
            age = self.clock()-self.received
            current = bool(state['engine_connected'] and frame and identity == self.identity and age < 1.0
                           and self.wall_clock()*1000-frame['captured_at_ms'] < 1000)
            fps = ((len(self.arrivals)-1)/(self.arrivals[-1]-self.arrivals[0])
                   if len(self.arrivals)>1 and self.arrivals[-1]>self.arrivals[0] else 0.0)
            status = 'live' if current and fps >= 5 else 'degraded' if current else 'stale' if frame else 'waiting'
            public = {k:v for k,v in frame.items() if k != 'data'} if current else None
            if public:
                public['url'] = f"/v1/product/viewport/frame/{frame['frame_id']}"
                # Display UVs only, sub-.002px rounding at the maximum image
                # size. Never round clocks, poses, geometry or identities.
                # Keep the existing 8192-byte atomic receipt contract even
                # with sixteen robots and ninety selected scan hits.
                if 'robot_anchors' in public:
                    public['robot_anchors']=[{**a,**{key:[round(n,6) for n in a[key]] for key in ('screen_anchor_uv','screen_bounds_uv')}} for a in public['robot_anchors']]
                if public.get('lidar_overlay'):
                    scan=public['lidar_overlay']
                    public['lidar_overlay']={**scan,'origin_uv':[round(n,6) for n in scan['origin_uv']],
                        'points_uv':[[round(n,6) for n in point] for point in scan['points_uv']]}
            # A static preview cannot carry live tracking/scan authority.
            # Do not duplicate transient point data in every JPEG header.
            last = {k:v for k,v in self.last_preview.items() if k not in {'data','robot_anchors','lidar_overlay'}} if self.last_preview else None
            if last:
                last.update(url=f"/v1/product/viewport/preview/{last['sha256']}",
                            preview_only=True,physical_authority=False)
            result={'state':status,'frame':public,'fps':round(fps,2),'age_ms':round(age*1000) if frame else None,
                    'last_frame':last,
                    'camera_result':self.camera_result,'camera_pending':bool(self.camera),
                    'detail':('Fresh Isaac render; physics execution is separate.' if current else
                              'Waiting for fresh frames from the current Isaac stage.'),
                    'physical_authority':False}
            if probe is not None:probe['tp_view_copy']=(time.perf_counter()-after_lock)*1000
            return result

    def preview_image(self, digest):
        """One bounded static image, never a current-frame/camera receipt.

        The service belongs to one authenticated project/backend. A replaced
        preview cannot be fetched by an earlier hash; no cross-project cache.
        """
        with self.lock:
            if not self.last_preview or digest != self.last_preview['sha256']:
                raise BrokerError('viewport_preview_expired','This preview is no longer retained',status=409)
            return self.last_preview['data']

    def image(self, frame_id):
        with self.lock:
            state = self.status(restore_preview=False)
            if not state['frame'] or str(state['frame']['frame_id']) != frame_id:
                raise BrokerError('viewport_frame_expired', 'This frame is no longer current', status=409)
            return self.latest['data']

    def image_packet(self, *, probe=None):
        """Return one coherent latest receipt/JPEG pair, never an old cache."""
        began=time.perf_counter()
        with self.lock:
            if probe is not None:probe['tp_image_wait']=(time.perf_counter()-began)*1000
            state=self.status(restore_preview=False,probe=probe)
            return state,self.latest['data'] if state['frame'] else None

    def camera_action(self, body):
        if (not isinstance(body, dict) or set(body) != {'request_id','frame_id','action'}
                or not isinstance(body['request_id'], str) or not 1 <= len(body['request_id']) <= 80
                or type(body['frame_id']) is not int
                or not isinstance(body['action'], str)
                or body['action'] not in {'orbit_left','orbit_right','zoom_in','zoom_out','pan_left','pan_right','pan_up','pan_down'}):
            raise BrokerError('viewport_camera_invalid', 'Choose a registered camera action', status=400)
        with self.lock:
            previous = self.requests.get(body['request_id'])
            if previous:
                if previous != body: raise BrokerError('viewport_request_conflict', 'Request ID is bound to another camera action',status=409)
                return self.status(restore_preview=False)
            status = self.status(restore_preview=False)
            observed = any(seq == body['frame_id'] and self.clock()-received < 1.0
                           and self.wall_clock()*1000-stamp < 1000
                           for seq,stamp,received in self.observed_frames)
            if not status['frame'] or not observed:
                raise BrokerError('viewport_frame_expired','Camera action requires a fresh frame from the current stage',status=409)
            if self.camera or self.clock()-self.last_camera_at < .2:
                raise BrokerError('viewport_camera_busy','Wait for the current camera action',status=409)
            self.requests[body['request_id']] = dict(body)
            if len(self.requests)>32: self.requests.pop(next(iter(self.requests)))
            self.camera = {**body,'engine_session_id':self.identity[0],'stage_epoch':self.identity[1],
                           'applied_revision':self.identity[2],'accepted_at':self.clock()}
            self.last_camera_at = self.clock(); self.camera_result = None
            return self.status(restore_preview=False)
