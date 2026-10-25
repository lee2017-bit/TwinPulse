# SPDX-License-Identifier: Apache-2.0
"""Owned native stationary observations in a wheel-estimated local frame.

No USD registration, device connection, motor command or restored authority.
The existing supervised robot-side collision/Stop guards remain independent.
"""
from copy import deepcopy
import math
import time
from twinpulse_core.automatic_mapping import EvidenceGrid
from twinpulse_core.physical_task_observation import checked_observation,wheel_se2,BASIS,number
from twinpulse_core.revisions import canonical_sha256
from twinpulse_core.room_localization import compose,inverse


class PhysicalTaskMap:
    def __init__(self,robot_id,operation_id,connection_epoch,*,clock=time.monotonic):
        self.identity=(robot_id,operation_id,connection_epoch)
        self.context=None;self.origin=None;self.grid=EvidenceGrid();self.latest=None
        self.seen=set();self.last_pose=None;self.observations=0
        self.clock=clock;self.accepted_at=None;self.accepted_age_ms=None

    def _context(self,row):
        if (row.get('robot_id'),row.get('operation_id'),row.get('connection_epoch'))!=self.identity:
            raise ValueError('TASK_LOCAL_CONNECTION_CHANGED')
        state=row.get('task_local_state') or {}
        if state.get('fault'):raise ValueError(state['fault'])
        if state.get('pose_valid') is not True:raise ValueError('TASK_LOCAL_CURRENT_ODOM_REQUIRED')
        if self.context and (state.get('pose_epoch')!=self.context['pose_epoch']
                or row.get('device_boot_id')!=self.context['boot_id'] or row.get('device_release_id')!=self.context['release_id']):
            raise ValueError('TASK_LOCAL_POSE_EPOCH_OR_DEVICE_CHANGED')

    def pose(self,row):
        self._context(row);native=wheel_se2(row.get('pose'))
        if self.context and row['pose']['frame_id']!=self.context['frame_id']:raise ValueError('TASK_LOCAL_ODOM_FRAME_CHANGED')
        return compose(inverse(self.origin),native) if self.origin is not None else native

    def accept(self,row):
        self._context(row)
        if row.get('control_state')!='PAUSED':raise ValueError('TASK_LOCAL_STATIONARY_REQUIRED')
        age=row.get('task_observation_age_ms');limit=(row.get('timing_values') or {}).get('native_receipt_ms',350)
        if not number(age) or not 0<=age<=limit:raise ValueError('TASK_LOCAL_OBSERVATION_STALE')
        # Conservative PC projection-start clock, before fleet.snapshot work.
        # Never subtract snapshot/validation/grid/storage work from source age
        # by assigning the acceptance END time as if it were a new receipt.
        observed_at=row.get('_task_snapshot_started_at');now=self.clock()
        if not number(observed_at) or not 0<=observed_at<=now:raise ValueError('TASK_LOCAL_PC_SOURCE_CLOCK_REQUIRED')
        if not 0<=now-observed_at+age/1000<=limit/1000:raise ValueError('TASK_LOCAL_OBSERVATION_STALE')
        value=checked_observation(row.get('task_local_observation'));ctx=value['context']
        if (tuple(ctx.get(k) for k in ('robot_id','operation_id','connection_epoch'))!=self.identity
                or ctx.get('boot_id')!=row.get('device_boot_id') or ctx.get('release_id')!=row.get('device_release_id')
                or value['pose_epoch']!=(row.get('task_local_state') or {}).get('pose_epoch')
                or value['config_sha256']!=canonical_sha256((row.get('field') or {}).get('config'))):
            raise ValueError('TASK_LOCAL_OBSERVATION_CONTEXT_CHANGED')
        if value['timing_limits']!={k:(row.get('timing_values') or {}).get(k) for k in value['timing_limits']}:
            raise ValueError('TASK_LOCAL_TIMING_POLICY_CHANGED')
        # A real finite completion can emit control_pause before the new PC
        # Stop fence has been read back and a post-Stop ring has arrived.
        # Preserve its old packet; do not rebase it or call it a source change.
        if value['motion_epoch']!=row.get('motion_epoch') or row.get('applied_motion_epoch')!=row.get('motion_epoch'):
            raise ValueError('TASK_LOCAL_POST_STOP_RING_PENDING')
        scan=value['scan'];key=(scan['stream_id'],scan['frame_sequence'],scan['raw_sha256'])
        if key in self.seen:raise ValueError('TASK_LOCAL_NEW_RING_PENDING')
        if self.latest and scan['stream_id']==self.latest['packet']['scan']['stream_id'] and scan['frame_sequence']<=self.latest['packet']['scan']['frame_sequence']:
            raise ValueError('TASK_LOCAL_SCAN_ROLLED_BACK')
        native=wheel_se2(value['pose'])
        pin=dict(boot_id=ctx['boot_id'],release_id=ctx['release_id'],pose_epoch=value['pose_epoch'],
            frame_id=value['pose']['frame_id'],stream_id=scan['stream_id'],config_sha256=value['config_sha256'])
        if self.context is not None and pin!=self.context:raise ValueError('TASK_LOCAL_SOURCE_OR_CONFIG_CHANGED')
        if self.context is None:self.context=pin;self.origin=list(native)
        pose=compose(inverse(self.origin),native)
        rays=[];sensor=value['sensor_origin_base'];world_sensor=compose(pose,[*sensor,0.])[:2]
        for point in value['points_base']:
            if .02<=math.dist(point,sensor)<=8:
                rays.append((list(world_sensor),compose(pose,[*point,0.])[:2]))
        if len(rays)<24:raise ValueError('TASK_LOCAL_VALID_RAYS_REQUIRED')
        stamp=round(scan['timing']['receipt_end_s']*1e9)
        fresh=EvidenceGrid();fresh.insert(rays,stamp,value['sha256'])
        self.grid.insert(rays,stamp,value['sha256']);self.seen.add(key);self.observations+=1
        self.latest=dict(packet=value,pose=pose,fresh_cells=fresh.rows(),scan_identity=list(key),
            cumulative_cells=self.grid.rows(),source=BASIS)
        self.accepted_at=observed_at;self.accepted_age_ms=age
        return deepcopy(self.latest)

    def scene(self,row,clock):
        self._context(row)
        if self.latest is None:raise ValueError('TASK_LOCAL_OBSERVATION_REQUIRED')
        # Historical cells can select return/coverage candidates, but every
        # outbound primitive is checked separately against the newest ring.
        cells=self.grid.rows()
        limit=(row.get('timing_values') or {}).get('native_receipt_ms',350)/1000
        produced=self.accepted_at-self.accepted_age_ms/1000
        if not 0<=clock()-produced<=limit:raise ValueError('TASK_LOCAL_FRESH_RING_REQUIRED_BEFORE_MOTION')
        return dict(binding=['physical-local',*self.identity,self.context['pose_epoch']],produced_at=produced,
            geometry=dict(epoch=1,targets=[],bounds=[-4.9,-4.9,4.9,4.9],obstacles=[]),
            observed_cells=cells,fresh_cells=deepcopy(self.latest['fresh_cells']),
            observation_sha256=self.latest['packet']['sha256'],context=deepcopy(self.context),
            _task_peers=[],scope=BASIS)

    def summary(self):
        rows=self.grid.rows()
        return dict(observations=self.observations,free_cells=sum(r[2]=='free' for r in rows),
            occupied_cells=sum(r[2]=='occupied' for r in rows),unknown_cells=sum(r[2]=='unknown' for r in rows),
            grid_sha256=canonical_sha256(rows),cell_size_m=.1,source=BASIS,model_prior_is_measurement=False,
            whole_room_verified=False,independent_body=False,world_aligned=False)
