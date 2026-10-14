# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Device-free protocol contract used by the robot-local manual controller.

Robot-issued challenges bound input age without assuming PC/robot clock sync.
Never refresh a delayed command's lifetime. No transport or device imports.
"""
import math
import secrets
import time

DIRECTIONS = {'forward': (.03, 0.), 'backward': (-.03, 0.),
              'left': (0., .20), 'right': (0., -.20)}
MANUAL_DIRECTIONS = {'forward': (.05, 0.), 'backward': (-.05, 0.),
                     'left': (0., .30), 'right': (0., -.30)}
TERMINAL_STOPS = {'finish_stop', 'force_stop'}


class RequestedStop(Exception):
    def __init__(self, action, sequence):
        super().__init__(action)
        self.action,self.sequence=action,sequence


def finish_segment(link, incoming, gate, last_output_s, segment_s, *, record, clock=time.monotonic,
                   safety=lambda:None):
    """No new output. Finish ONLY the remaining issued command slice, never a route.

    Caller must halt in finally/on return. Faults/EOF interrupt the wait and force
    requests supersede it. This is not a torque ramp or certified emergency stop.
    """
    now=clock()
    end=now if last_output_s is None else min(last_output_s+segment_s,gate.deadline,gate.hold_end,
                                             float('inf') if gate.persistent else gate.started+60.)
    if not math.isfinite(end) or not 0<segment_s<=.1:raise ValueError('STOP_SEGMENT_INVALID')
    previous=now
    while True:
        now=clock()
        if not math.isfinite(now) or now<previous:raise ValueError('STOP_CLOCK_FAULT')
        previous=now
        for _ in range(8):
            packet=incoming.receive()
            if packet is None:break
            # Queued movement/watch is discarded, never executed or renewed.
            if not isinstance(packet,dict):raise ValueError('INPUT_SHAPE')
            if packet.get('action') in {'force_stop','close'}:
                action,_=gate.accept(packet)
                record('accepted',sequence=packet['sequence'],action=action,source_age_s=0.)
                return 'FORCE_STOPPED'
        link.fresh();safety()
        now=clock()
        if not math.isfinite(now) or now<previous:raise ValueError('STOP_CLOCK_FAULT')
        previous=now
        if now>=end:return 'COMMAND_SEGMENT_STOPPED'
        link.spin(min(.005,end-now))


class InputGate:
    def __init__(self, clock=time.monotonic, *, continuous=False, persistent=False):
        self.clock = clock
        self.started = clock()
        self.sequence = 0
        self.challenges = {}
        self.deadline = self.hold_end = 0.
        self.active = False
        self.closed = False
        self.last_action = None
        self.continuous = continuous is True
        self.persistent = persistent is True
        self.presence_at = None

    def challenge(self):
        now = self.clock()
        self.challenges = {k: v for k, v in self.challenges.items() if now - v < .25}
        nonce = secrets.token_hex(12)
        self.challenges[nonce] = now
        return nonce

    def suspend_for_sensor_warmup(self):
        """Expire the accepted one-shot intent before blocking sensor preparation.

        Wheels are still disabled. A new, short-lived watch challenge must be
        accepted after warmup before the fixed trial can enable torque.
        """
        if self.closed or not self.active or self.last_action != 'qualify':
            raise ValueError('QUALIFICATION_PREP_STATE_INVALID')
        self.active = False
        self.deadline = self.hold_end = 0.
        self.challenges.clear()

    def discard_warmup_watch(self):
        """Consume a valid watch without arming an idle sensor-warmup lease.

        Only the wheels-disabled preparation loop may call this. The next
        watch still needs a new robot challenge before motor enable.
        """
        if self.closed or not self.active or self.last_action != 'watch':
            raise ValueError('SENSOR_WARMUP_WATCH_STATE_INVALID')
        self.active = False
        self.deadline = self.hold_end = 0.
        self.challenges.clear()

    def discard_idle_watch(self):
        """Validated idle presence is not a wheel-command lease.

        Caller must have observed outputs disabled. Keep nonce freshness and
        session lifetime, but do not start the 250ms motion deadline while idle.
        A direction still requires its own fresh nonce and post-arm input.
        """
        if self.closed or not self.active or self.last_action != 'watch':
            raise ValueError('IDLE_WATCH_STATE_INVALID')
        self.active = False
        self.deadline = self.hold_end = 0.

    def accept(self, packet):
        if not isinstance(packet, dict) or set(packet) != {'sequence', 'action', 'challenge', 'age_ms'}:
            raise ValueError('INPUT_SHAPE')
        seq, action = packet['sequence'], packet['action']
        if type(seq) is not int or not self.sequence < seq < 2147483647:
            raise ValueError('INPUT_SEQUENCE')
        if not isinstance(action, str) or action not in {*DIRECTIONS, 'watch', 'qualify', 'stop', 'close', *TERMINAL_STOPS}:
            raise ValueError('INPUT_ACTION')
        self.sequence = seq
        if action in {'stop', 'close', *TERMINAL_STOPS}:
            self.active = False
            if action != 'stop': self.closed = True
            return action, 0.
        self.check()
        if self.closed: raise ValueError('SESSION_CLOSED')
        challenge = packet['challenge']
        if not isinstance(challenge, str) or challenge not in self.challenges:
            raise ValueError('INPUT_CHALLENGE')
        extra = packet['age_ms']
        if type(extra) not in (int,float) or not math.isfinite(extra) or not 0<=extra<250:
            raise ValueError('INPUT_AGE')
        # Conservative sum: time already spent before relay plus the robot nonce
        # round trip. A queued PC request cannot receive a new 250ms lifetime.
        age = self.clock() - self.challenges.pop(challenge) + extra/1000
        if not 0 <= age < .25: raise ValueError('INPUT_EXPIRED')
        self.presence_at = self.clock()
        if not self.active or (self.last_action == 'watch' and action != 'watch') or (self.continuous and action in DIRECTIONS):
            self.hold_end = self.clock() + (60. if action == 'watch' else 2.)
        self.last_action = action
        self.active = True
        self.deadline = self.clock() + .25 - age
        return action, age

    def check(self):
        now = self.clock()
        reason = ('SESSION_EXPIRED' if not self.persistent and now-self.started >= 60 else
                  'INPUT_DEADLINE_EXPIRED' if self.active and now >= self.deadline else
                  'HOLD_LIMIT_EXCEEDED' if self.active and now >= self.hold_end else
                  'OPERATOR_PRESENCE_EXPIRED' if self.persistent and self.presence_at is not None and now-self.presence_at>=.5 else None)
        if reason:
            self.closed = True
            raise ValueError(reason)


def settling(rows, timeout_s):
    return settling_details(rows, timeout_s)['passed']


def settling_details(rows, timeout_s):
    """Original fixed 2-tick anchor / 200ms stability within 500ms, full samples.

Missing or stale sensor coverage is never stability. Encoder units not floor pose.
"""
    result = {'passed': False, 'stable_ms': None, 'required_stable_ms': 200,
              'window_ms': 500, 'band_ticks': 2, 'reason': 'SENSOR_COVERAGE_INVALID'}
    if len(rows) < 2 or not math.isfinite(timeout_s): return result
    relevant = [r for r in rows if r['t'] <= timeout_s + .5]
    if not relevant or any(not math.isfinite(r['t']) for r in relevant): return result
    if any(b['t'] <= a['t'] for a, b in zip(relevant, relevant[1:])): return result
    before = [r for r in relevant if r['t'] <= timeout_s]
    after = [r for r in relevant if r['t'] > timeout_s]
    if not before or not after: return result
    covered = before[-1:] + after
    if (timeout_s - before[-1]['t'] >= .2 or timeout_s + .5 - after[-1]['t'] >= .2
            or any(b['t'] - a['t'] >= .2 for a, b in zip(covered, covered[1:]))): return result
    anchor, changed = relevant[0]['encoders'], relevant[0]['t']
    for row in relevant:
        if any(abs(a-b) > 2 for a, b in zip(anchor, row['encoders'])):
            anchor, changed = row['encoders'], row['t']
    stable = timeout_s + .5 - changed
    return {**result, 'passed': stable >= .2, 'stable_ms': stable * 1000,
            'last_anchor_change_s': changed, 'window_end_s': timeout_s + .5,
            'reason': 'STABLE' if stable >= .2 else 'ENCODER_SETTLING_SHORT'}
