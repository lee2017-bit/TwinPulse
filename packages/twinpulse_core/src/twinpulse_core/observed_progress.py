# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Conservative position-progress guard, not motor load or physical qualification.

Only successful native nonzero publications activate the window. Both measured
odom and current scan-localized pose must progress; stale data is handled by the
existing mission guard before this checker. Zero/replan/turn changes reset it.
"""
import math
from .room_localization import angle


class ObservedProgressGuard:
    def __init__(self):
        self.reset()

    def reset(self):
        self.kind = None; self.anchor = None; self.started = None; self.last_output = None

    def published(self, now, v, w, odom, mapped):
        kind = ('LINEAR', math.copysign(1, v)) if v else ('ROTATION', math.copysign(1, w)) if w else None
        if kind is None:
            self.reset(); return
        if (kind != self.kind or self.last_output is None or not 0 <= now-self.last_output < .25):
            self.kind = kind; self.started = now; self.anchor = (tuple(odom), tuple(mapped))
        self.last_output = now

    def check(self, now, odom, mapped):
        if self.last_output is None: return
        if not 0 <= now-self.last_output < .25:
            self.reset(); return
        if now-self.started < 3.: return
        if self.kind[0] == 'LINEAR':
            enough = all(math.dist(current[:2], initial[:2]) >= .01
                         for current, initial in zip((odom, mapped), self.anchor))
        else:
            enough = all(abs(angle(current[2]-initial[2])) >= .05
                         for current, initial in zip((odom, mapped), self.anchor))
        if not enough: raise ValueError('OBSERVED_PROGRESS_STALLED')
        self.started = now; self.anchor = (tuple(odom), tuple(mapped))
