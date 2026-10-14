# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Bounded text selection, not visual recognition or a new robot simulator."""
import re


def sim_robot_selection(text):
    if not isinstance(text, str):
        raise ValueError('SIM_ROBOT_REQUEST_INVALID')
    unsupported = re.search(r'\b(go1|go2|quadruped|humanoid|manipulator|drone|quadcopter|ur5|husky|jackal|turtlebot4|waffle)\b|사족|휴머노이드|드론|매니퓰레이터', text, re.IGNORECASE)
    ambiguous_brand = re.search(r'\b(Spot|Fetch)\b',text) or re.search(r'\b(spot|fetch) robot\b|\brobot (spot|fetch)\b',text,re.IGNORECASE)
    unsupported = unsupported or ambiguous_brand
    if unsupported:
        return {'asset_id': None, 'code': 'SIM_ROBOT_ALTERNATIVE_REQUIRED',
                'reason': 'The requested robot type is not supported by this room SIM adapter. Choose the existing TurtleBot3 Burger alternative; no unsupported model will be executed.'}
    explicit = bool(re.search(r'\b(burger3?|turtlebot3)\b|버거', text, re.IGNORECASE))
    return {'asset_id': 'turtlebot3_burger', 'code': 'SIM_BURGER_EXPLICIT' if explicit else 'SIM_SUPPORTED_WHEELED_DEFAULT',
            'reason': ('Using the requested existing TurtleBot3 Burger.' if explicit else
                       'No supported robot model was specified. Using the existing supported TurtleBot3 Burger wheeled model, not an inferred match to a photo.')}
