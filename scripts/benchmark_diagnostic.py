# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only expected-goal proof checks; never navigation or generation PASS."""
import math
from scripts.benchmark_protocol import canonical_sha,text_sha

REJECTIONS=frozenset({'SIM_TARGET_NOT_FOUND','SIM_GOAL_COORDINATES_REQUIRE_X_Y_PAIRS',
    'SIM_GOAL_USE_FROM_X_Y_TO_X_Y','SIM_GOAL_USE_FROM_X_Y_TO_OBJECT',
    'GOAL_PREVIEW_OUTSIDE_ROOM','START_OR_GOAL_BLOCKED','NO_PATH','REVIEWED_ROUTE_BLOCKED',
    'SNAPPED_ENDPOINT_BLOCKED','GRID_EDGE_BLOCKED','SIM_TARGET_NO_REACHABLE_APPROACH'})


def validate_diagnostic(packet,receipt):
    """Validate saved UI/API snapshots, not a hand-written 'expected PASS' flag."""
    def require(condition):
        if not condition:raise ValueError('BENCHMARK_DIAGNOSTIC_EVIDENCE_INVALID')
    require(type(packet) is dict and type(packet.get('goal')) is dict)
    require(type(receipt) is dict and receipt.get('schema_version')=='benchmark-goal-diagnostic-1.0')
    expected=packet['goal'].get('expected');require(expected in ('rejection','clarification'))
    require(type(packet['goal'].get('sha256')) is str)
    require(receipt.get('case_sha256')==canonical_sha(packet) and receipt.get('goal_sha256')==packet['goal']['sha256'])
    before,after=receipt.get('before'),receipt.get('after')
    require(type(before) is dict and type(after) is dict)
    require(type(before.get('cursor')) is int and before['cursor']>=0)
    require(before.get('scene_revision') and all(before.get(k)==after.get(k) and before.get(k) is not None
        for k in ('scene_revision','plan_sha256','input_revision','operations','snapshot')))
    require(type(before['operations']) is list and before['operations'])
    sample=before['snapshot']
    require(type(sample) is dict)
    require(sample.get('runtime_state')=='completed' and sample.get('telemetry_available') is True
        and sample.get('applied_revision')==before['scene_revision'] and sample.get('run_id'))
    position=sample.get('position_m')
    require(type(position) is list and len(position)==3
        and all(type(v) in (int,float) and math.isfinite(v) for v in position))
    event=after.get('event');require(type(event) is dict)
    payload=event.get('payload');require(type(payload) is dict)
    require(type(after.get('goal_text')) is str and type(receipt.get('request_id')) is str)
    require(type(event.get('sequence')) is int and event['sequence']>before['cursor']
        and payload.get('request_id')==receipt.get('request_id') and bool(receipt.get('request_id'))
        and payload.get('scene_revision')==before['scene_revision']
        and after.get('simulation_plan') is None and after.get('physical_authority') is False
        and text_sha(after.get('goal_text',''))==packet['goal']['sha256'])
    if expected=='clarification':
        card=after.get('card');require(type(card) is dict)
        choices=card.get('choices')
        require(type(choices) is list and all(type(c) is dict and type(c.get('id')) is str for c in choices))
        require(event.get('type')=='simulation_goal_clarification' and payload.get('card_id')==card.get('id')
            and card.get('kind')=='simulation_target' and card.get('state')=='waiting'
            and card.get('related_plan_digest')==before['scene_revision']
            and len([c for c in choices if c.get('enabled') is True and c.get('id','').startswith('object_')])>=2)
        code='SIM_TARGET_CLARIFICATION'
    else:
        code=payload.get('goal_error_code')
        require(event.get('type')=='simulation_goal_rejected' and payload.get('code')=='simulation_goal_rejected'
            and code in REJECTIONS and not after.get('card'))
        if code=='SIM_TARGET_NO_REACHABLE_APPROACH':
            diagnostic=payload.get('goal_diagnostic');require(type(diagnostic) is dict)
            require(diagnostic.get('termination_code')=='NO_ACCEPTED_EXTERIOR_CANDIDATE')
    return dict(status='PASS',expected_outcome=expected,code=code,
        evidence_sha256=canonical_sha(receipt),semantic_goal_arrival=False,physical_authority=False)
