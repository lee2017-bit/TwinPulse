# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Bounded text selection, not visual recognition or a new robot simulator."""
import re


def sim_robot_selection(text):
    if not isinstance(text, str):
        raise ValueError('SIM_ROBOT_REQUEST_INVALID')
    # Conservative, bounded text rules only: a robot omission is not permission
    # to select a model, and an image is never evidence of a robot selection.
    robot = (r'(?:(?<![a-z0-9])(?:robots?|turtlebot3(?:\s+burger)?|burger3?|go1|go2|quadruped|humanoid|'
             r'manipulator|drone|quadcopter|ur5|husky|jackal|turtlebot4|waffle|spot|fetch)(?![a-z0-9])|'
             r'로봇|터틀봇\s*3?(?:\s*burger)?|버거3?|사족|휴머노이드|드론|매니퓰레이터)')
    modifiers = r'(?:(?:a|an|any|the|existing|supported|simulated|sim|robot)\s+){0,3}'
    omitted = re.search(
        r'\b(?:no|without|exclude|omit)\s+' + modifiers + robot +
        r'|\b(?:do not|don\x27t|never)\s+(?:add|include|use|spawn|place|select)\s+' + modifiers + robot +
        r'|' + robot + r'(?:\s*로봇)?\s*(?:은|는|을|를)?\s*(?:(?:추가|사용|생성|배치)하지\s*(?:마|않)|넣지\s*(?:마|않)|(?:추가\s*)?없이|없음|제외|빼)'
        r'|' + robot + r'(?:\s+robot)?\s+(?:is\s+)?not\s+(?:needed|required|wanted)',
        text, re.IGNORECASE)
    if omitted:
        return _environment_only()
    unsupported = re.search(r'\b(go1|go2|quadruped|humanoid|manipulator|drone|quadcopter|ur5|husky|jackal|turtlebot4|waffle)\b|사족|휴머노이드|드론|매니퓰레이터', text, re.IGNORECASE)
    ambiguous_brand = re.search(r'\b(Spot|Fetch)\b',text) or re.search(r'\b(spot|fetch) robot\b|\brobot (spot|fetch)\b',text,re.IGNORECASE)
    unsupported = unsupported or ambiguous_brand
    if unsupported:
        return {'asset_id': None, 'code': 'SIM_ROBOT_ALTERNATIVE_REQUIRED',
                'reason': 'The requested robot type is not supported by this room SIM adapter. Choose the existing TurtleBot3 Burger alternative; no unsupported model will be executed.'}
    supported = r'(?:(?<![a-z0-9])(?:turtlebot3(?:\s+burger)?|burger3?)(?![a-z0-9])|버거3?|터틀봇\s*3(?:\s*burger)?)'
    explicit = bool(re.search(
        r'\b(?:with|for|use|using|add|include|place|spawn|select|prepare)\s+' + modifiers + supported +
        r'|' + supported + r'\s*(?:로봇)?\s*(?:(?:을|를)?\s*(?:추가|사용|준비|선택|배치|생성|넣어)|(?:으로|로)\s*(?:사용|준비|선택|배치|생성))',
        text, re.IGNORECASE))
    if not explicit:
        return _environment_only()
    return {'asset_id': 'turtlebot3_burger', 'code': 'SIM_BURGER_EXPLICIT',
            'reason': 'Using the requested existing TurtleBot3 Burger.'}


def _environment_only():
    return {'asset_id': None, 'code': 'SIM_ENVIRONMENT_ONLY',
            'reason': 'Creating the environment only; no SIM robot was selected or inferred from a photo. You can request a SIM robot and goal separately after reviewing the current Twin.'}
