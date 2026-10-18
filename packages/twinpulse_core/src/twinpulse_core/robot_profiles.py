# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Versioned, application-owned robot profiles.

The multimodal planner may select a profile identifier.  It never authors wheel,
mass, inertia, support-contact, or safety parameters.
"""

from __future__ import annotations

from .models import RobotProfile, SupportWheelSpec


COMPACT_2WD_PROFILE_ID = "agv_compact_2wd_caster_v2"
LEGACY_PROFILE_ALIASES = {"agv_compact_diff_v1": COMPACT_2WD_PROFILE_ID}


def compact_2wd_caster_profile() -> RobotProfile:
    return RobotProfile(
        id=COMPACT_2WD_PROFILE_ID,
        chassis_dimensions_m=(0.60, 0.40, 0.20),
        mass_kg=10.0,
        wheel_radius_m=0.12,
        wheel_track_m=0.46,
        wheel_width_m=0.06,
        max_linear_speed_mps=0.25,
        max_angular_speed_rps=0.7853981634,
        support_wheels=(
            SupportWheelSpec("front_caster", (0.24, 0.0), 0.04, 0.25),
            SupportWheelSpec("rear_caster", (-0.24, 0.0), 0.04, 0.25),
        ),
        center_of_mass_m=(0.0, 0.0, -0.03),
        diagonal_inertia_kg_m2=(0.1667, 0.3333, 0.4333),
        max_safe_roll_pitch_deg=8.0,
    )


def resolve_robot_profile(profile_id: str) -> RobotProfile:
    canonical_id = LEGACY_PROFILE_ALIASES.get(profile_id, profile_id)
    if canonical_id == COMPACT_2WD_PROFILE_ID:
        return compact_2wd_caster_profile()
    raise KeyError(profile_id)


def accepted_robot_profile_ids() -> frozenset[str]:
    return frozenset({COMPACT_2WD_PROFILE_ID, *LEGACY_PROFILE_ALIASES})
