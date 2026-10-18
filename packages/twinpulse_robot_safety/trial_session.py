# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""D2 dry-run approval/state contract. Not connected to any robot command path.

No CLI can arm, enable or execute motion using this module. This proves workflow
rules before wiring the still-unqualified physical trial adapter.
"""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Binding:
    boot_id: str
    release_id: str
    session_id: str
    trial_id: str


class TrialSession:
    def __init__(self, binding):
        if not isinstance(binding, Binding) or not all(vars(binding).values()):
            raise ValueError('Complete boot/release/session/trial binding required')
        self.binding = binding
        self.state = 'PREPARING'
        self.events = []
        self.last_time = -1.0
        self.ready_time = None
        self.approval_time = None

    def _time(self, now):
        if not math.isfinite(now) or now < 0 or now < self.last_time:
            raise ValueError('Monotonic finite clock required')
        self.last_time = now

    def ready(self, now, *, artifacts_verified, fake_tests_passed):
        self._time(now)
        if self.state != 'PREPARING' or not artifacts_verified or not fake_tests_passed:
            raise ValueError('Preparation incomplete; not Ready')
        self.ready_time, self.state = now, 'READY_FOR_OPERATOR'
        self.events.append({'event': self.state, 'at': now})

    def approve_operator(self, now, binding, *, watching, area_clear):
        self._time(now)
        if (self.state != 'READY_FOR_OPERATOR' or binding != self.binding
                or now - self.ready_time > 300 or not watching or not area_clear):
            raise ValueError('Fresh bound operator confirmation required')
        self.approval_time, self.state = now, 'APPROVED_DRY_RUN'
        self.events.append({'event': self.state, 'at': now})

    def consume_dry_run(self, now, binding, *, fresh_idle, preflight_age_s):
        self._time(now)
        if self.state != 'APPROVED_DRY_RUN':
            raise ValueError('Approval missing, cancelled or already consumed')
        # A failed immediate check also consumes this approval: no delayed retry.
        self.state = 'CONSUMED'
        accepted = (binding == self.binding and now - self.approval_time <= 15
                    and fresh_idle and math.isfinite(preflight_age_s)
                    and 0 <= preflight_age_s <= 1)
        self.events.append({'event': 'WOULD_RUN' if accepted else 'BLOCKED', 'at': now})
        return {'would_allow_fixed_trial': bool(accepted), 'motion_authorized': False,
                'mode': 'DRY_RUN_CONTRACT_ONLY', 'linear_m_s': .03, 'angular_rad_s': 0,
                'publish_window_ms': 600, 'timeout_deadline_ms': 700,
                'post_timeout_window_ms': 500, 'stationary_band_ticks': 2,
                'stationary_required_ms': 200}

    def cancel(self, now):
        self._time(now)
        if self.state == 'CONSUMED':
            raise ValueError('Already consumed; cancellation cannot reset a trial')
        self.state = 'CANCELLED'
        self.events.append({'event': 'CANCELLED', 'at': now})
