# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Device-free manual-control rehearsal, with an unconditional physical gate.

The deployed robot has no qualified teleop adapter/physical-stop acceptance.
No request, imported report, mode flag or all-green snapshot can enable it here.
This module imports no SSH/serial/ROS transport. Timing tests are NOT robot tests.
"""
import math
import secrets
from threading import Event, RLock, Thread
import time

from .command_broker import BrokerError


class ManualController:
    DIRECTIONS = {'forward': (.03, 0), 'backward': (-.03, 0),
                  'left': (0, .20), 'right': (0, -.20)}
    ACTIONS = set(DIRECTIONS) | {'stop', 'stop_all', 'lidar_start', 'lidar_stop', 'close'}

    def __init__(self, *, clock=time.monotonic, wall=lambda: time.time() * 1000):
        self.clock, self.wall = clock, wall
        self._lock = RLock()
        self._closed = Event()
        self._thread = None
        self._owner = self._session = None
        self._sequence = 0
        self._armed = False
        self._v = self._w = 0.
        self._x = self._y = self._yaw = 0.
        self._direction = None
        self._deadline = self._gesture_deadline = self._session_deadline = 0.
        self._lidar_deadline = 0.
        self._last = clock()
        self._reason = 'NOT_STARTED'

    def start_watchdog(self):
        if self._thread is None:
            self._thread = Thread(target=self._watch, daemon=True, name='ManualRehearsalWatchdog')
            self._thread.start()

    def _watch(self):
        while not self._closed.wait(.025):
            with self._lock: self._tick()

    def _stop(self, reason, *, latch=False, all_outputs=False):
        self._v = self._w = 0.
        self._direction = None
        self._deadline = self._gesture_deadline = 0.
        self._reason = reason
        if latch: self._armed = False
        if all_outputs: self._lidar_deadline = 0.

    def _tick(self):
        now = self.clock()
        if now < self._last:
            self._stop('CLOCK_FAULT', latch=True, all_outputs=True)
            self._last = now
            return
        if self._direction:
            until = min(now, self._deadline, self._gesture_deadline, self._session_deadline)
            dt = max(0., until - self._last)
            self._x += self._v * math.cos(self._yaw) * dt
            self._y += self._v * math.sin(self._yaw) * dt
            self._yaw += self._w * dt
        self._last = now
        if self._armed and now >= self._session_deadline:
            self._stop('SESSION_EXPIRED', latch=True, all_outputs=True)
        elif self._direction and now >= min(self._deadline, self._gesture_deadline):
            self._stop('INPUT_EXPIRED', latch=True, all_outputs=True)
        if self._lidar_deadline and now >= self._lidar_deadline:
            self._lidar_deadline = 0.
            self._reason = 'LIDAR_TIME_LIMIT'

    def snapshot(self, owner):
        with self._lock:
            self._tick()
            owned = self._owner == owner
            return {'schema_version': 'manual-controller-1.0', 'mode': 'PC_REHEARSAL_ONLY',
                    'physical_motion_authorized': False, 'physical_lidar_authorized': False,
                    'physical_blockers': ['PHYSICAL_STOP_NOT_QUALIFIED', 'TELEOP_ADAPTER_NOT_QUALIFIED',
                                          'LIDAR_MANUAL_LIFECYCLE_NOT_QUALIFIED'],
                    'session_id': self._session if owned else None, 'owned': owned,
                    'armed': self._armed if owned else False, 'sequence': self._sequence,
                    'linear_m_s': self._v, 'angular_rad_s': self._w,
                    'pose': {'x_m': self._x, 'y_m': self._y, 'yaw_rad': self._yaw},
                    'lidar_running': bool(self._lidar_deadline),
                    'lidar_remaining_s': round(max(0., self._lidar_deadline - self.clock()), 1),
                    'reason': self._reason, 'limits': {'input_ms': 350, 'hold_s': 2, 'session_s': 60, 'lidar_s': 8}}

    def begin(self, owner, mode, confirmed):
        with self._lock:
            self._tick()
            if self._closed.is_set(): raise BrokerError('controller_closed', 'Console closed.', status=409)
            if mode != 'rehearsal':
                raise BrokerError('physical_control_unqualified', 'Physical controls are not qualified.', status=409)
            if confirmed is not True:
                raise BrokerError('rehearsal_confirmation_required', 'Explicit PC-only confirmation required.', status=409)
            if self._armed and self._owner != owner:
                raise BrokerError('controller_owned', 'Another session owns the rehearsal.', status=409)
            self._stop('ARMED_REHEARSAL', all_outputs=True)
            self._owner, self._session = owner, secrets.token_hex(16)
            self._sequence, self._armed = 0, True
            self._x = self._y = self._yaw = 0.
            self._session_deadline = self.clock() + 60
            return self.snapshot(owner)

    def command(self, owner, session, sequence, action, expires_at_ms):
        with self._lock:
            self._tick()
            if self._closed.is_set(): raise BrokerError('controller_closed', 'Console closed.', status=409)
            if self._owner != owner or self._session != session:
                raise BrokerError('controller_session', 'Fresh owned session required.', status=409)
            if type(sequence) is not int or not self._sequence < sequence <= 2147483647:
                raise BrokerError('controller_sequence', 'Old or invalid input rejected.', status=409)
            if not isinstance(action, str) or action not in self.ACTIONS:
                raise BrokerError('controller_action', 'Unknown control.', status=400)
            self._sequence = sequence
            # A newer STOP invalidates delayed older motion packets; stop has no freshness prerequisite.
            if action in {'stop', 'stop_all', 'close', 'lidar_stop'}:
                if action == 'lidar_stop': self._lidar_deadline = 0.
                else: self._stop('OPERATOR_STOP', latch=action != 'stop', all_outputs=action != 'stop')
                if action == 'close': self._session = None
                return self.snapshot(owner)
            if (type(expires_at_ms) not in (int, float) or not math.isfinite(expires_at_ms)
                    or not 0 < expires_at_ms - self.wall() <= 300):
                self._stop('STALE_INPUT', latch=True, all_outputs=True)
                raise BrokerError('controller_stale_input', 'Input expired.', status=409)
            if not self._armed: raise BrokerError('controller_disarmed', 'Re-enable rehearsal explicitly.', status=409)
            now = self.clock()
            if action == 'lidar_start':
                if not self._lidar_deadline: self._lidar_deadline = now + 8
                self._reason = 'LIDAR_REHEARSAL'
            else:
                # Direction changes do not extend the same uninterrupted gesture.
                if self._direction is None: self._gesture_deadline = now + 2
                self._direction = action
                self._v, self._w = self.DIRECTIONS[action]
                self._deadline = now + min(.350, (expires_at_ms - self.wall()) / 1000)
                self._reason = 'HELD_INPUT'
            return self.snapshot(owner)

    def close(self):
        self._closed.set()
        with self._lock: self._stop('CONSOLE_CLOSED', latch=True, all_outputs=True)
        if self._thread: self._thread.join(timeout=1)
