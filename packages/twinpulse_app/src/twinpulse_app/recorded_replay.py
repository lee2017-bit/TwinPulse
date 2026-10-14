# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Receipt-time pacing for historical replay, never live acquisition timing.

Only the next event is held. No growing replay queue, skipped events, fabricated
timestamps, or authority to change live/mission deadlines is provided here.
"""
import math


class RecordedReplayPacer:
    MAX_SPAN_NS = 600_000_000_000

    def __init__(self, wall_start):
        self.wall_start = wall_start
        self.first = None
        self.last = None
        self.events = 0
        self.delivered_events = 0
        self.waited_s = 0.
        self.maximum_lateness_s = 0.
        self.late_over_200ms = 0
        self.late_over_250ms = 0

    def target(self, receipt):
        if type(receipt) is not int or receipt < 0:
            raise ValueError('RECORDED_REPLAY_RECEIPT_REQUIRED')
        if self.last is not None and receipt < self.last:
            raise ValueError('RECORDED_REPLAY_RECEIPT_BACKWARD')
        if self.first is None:
            self.first = receipt
        if receipt - self.first > self.MAX_SPAN_NS:
            raise ValueError('RECORDED_REPLAY_SPAN_BUDGET')
        self.last = receipt
        self.events += 1
        return self.wall_start + (receipt - self.first) / 1e9

    def waited(self, elapsed):
        if not math.isfinite(elapsed) or elapsed < 0:
            raise ValueError('RECORDED_REPLAY_WALL_CLOCK')
        self.waited_s += elapsed

    def delivered(self, target, now):
        late=max(0.,now-target)
        self.delivered_events+=1
        self.maximum_lateness_s = max(self.maximum_lateness_s, late)
        self.late_over_200ms+=int(late>.2)
        self.late_over_250ms+=int(late>.25)

    def summary(self, now):
        return {'mode': 'recorded_1x', 'basis': 'ORIGINAL_ROBOT_RECEIPT_MONOTONIC_NOT_ACQUISITION',
                'events': self.events, 'delivered_events': self.delivered_events,
                'late_over_200ms_events':self.late_over_200ms,'late_over_250ms_events':self.late_over_250ms,
                'receipt_span_s': (self.last - self.first) / 1e9 if self.last is not None else 0.,
                'pacing_wait_s': self.waited_s, 'maximum_lateness_s': self.maximum_lateness_s,
                'processing_elapsed_s': max(0., now - self.wall_start - self.waited_s),
                'pending_event_bound': 1, 'motion_authorized': False, 'timing_verified': False}
