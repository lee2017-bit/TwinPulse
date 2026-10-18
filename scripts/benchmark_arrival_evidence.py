# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only actual navigation proof. A completed old preview is not an arrival.

This validates recorded current request/event/plan/run/pose/receipt identity,
not photo quality, global path optimality or physical robot authority.
"""
import math
from scripts.benchmark_protocol import canonical_sha,text_sha


def validate_arrival(packet,browser):
    def require(value):
        if not value:raise ValueError('BENCHMARK_ARRIVAL_EVIDENCE_INVALID')
    def sample(value,plan,before,state):
        require(isinstance(value,dict) and isinstance(before,dict))
        require(value.get('run_id')==plan['plan_id'] and value.get('applied_revision')==plan['scene_revision']
            and value.get('runtime_state')==state and value.get('telemetry_available') is True and not value.get('safety_state'))
        require(all(value.get(k) and value.get(k)==before.get(k) for k in ('engine_session_id','stage_epoch')))
        require(type(value.get('sequence')) is int and type(before.get('sequence')) is int and value['sequence']>before['sequence'])
        require(isinstance(value.get('position_m'),list) and len(value['position_m'])==3
            and all(type(v) in (int,float) and math.isfinite(v) for v in value['position_m']))
    proof=browser.get('semantic_goal_evidence');require(isinstance(proof,dict) and proof.get('schema_version')=='benchmark-arrival-1.0')
    require(proof.get('case_sha256')==canonical_sha(packet) and proof.get('goal_sha256')==packet['goal']['sha256']
        and text_sha(proof.get('goal_text',''))==packet['goal']['sha256'])
    before,review,event=proof.get('before'),proof.get('review'),proof.get('event')
    require(all(isinstance(v,dict) for v in (before,review,event)))
    require(review.get('request_id') and review['request_id']!=before.get('request_id')
        and review.get('text')==proof['goal_text'] and isinstance(review.get('plan'),dict))
    plan=review['plan'];require(plan.get('mode')=='SIM' and plan.get('physical_authority') is False)
    require(review.get('scene_revision')==plan.get('scene_revision') and plan.get('plan_id'))
    require(type(before.get('cursor')) is int and type(event.get('sequence')) is int and event['sequence']>before['cursor']
        and event.get('type')=='simulation_route_reviewed')
    payload=event.get('payload');require(isinstance(payload,dict))
    require(payload.get('plan_id')==plan['plan_id'] and payload.get('scene_revision')==plan['scene_revision'])
    preview=browser.get('initial_preview_plan');require(isinstance(preview,dict) and plan['plan_id']!=preview.get('plan_id'))
    arrival=proof.get('arrival');require(arrival==browser.get('semantic_arrival'))
    sample(arrival,plan,before.get('snapshot'),'completed')
    require(isinstance(plan.get('goal'),list) and len(plan['goal'])==2 and
        all(type(v) in (int,float) and math.isfinite(v) for v in plan['goal']))
    distance=math.dist(arrival['position_m'][:2],plan['goal'])
    require(distance<=.040001 and type(arrival.get('distance_to_goal_m')) in (int,float)
        and abs(arrival['distance_to_goal_m']-distance)<=.002)
    if review.get('target'):
        diagnosis=payload.get('goal_diagnostic');require(isinstance(diagnosis,dict))
        require(diagnosis.get('target_id')==review['target'].get('id') and diagnosis.get('selected_point')==plan['goal'])
    prior=before.get('operations');after=proof.get('operations')
    require(isinstance(prior,list) and isinstance(after,list))
    known={op.get('command_id') for op in prior}
    runs=[op for op in after if op.get('command_type')=='run' and op.get('command_id') not in known]
    require(len(runs)==1 and runs[0].get('status')=='succeeded'
        and runs[0].get('expected_applied_revision')==plan['scene_revision'])
    require(all(runs[0].get(k)==arrival.get(k) for k in ('engine_session_id','stage_epoch')))
    stop=browser.get('stop_test_evidence');require(isinstance(stop,dict) and isinstance(stop.get('review'),dict))
    returning=stop['review'].get('plan');require(isinstance(returning,dict) and returning.get('plan_id')!=plan['plan_id']
        and returning.get('scene_revision')==plan['scene_revision'] and returning.get('physical_authority') is False)
    require(stop.get('before')==arrival and stop['review'].get('text')==browser.get('stop_test_input'))
    sample(stop.get('running'),returning,arrival,'running')
    sample(stop.get('paused'),returning,stop['running'],'paused')
    sample(stop.get('stable'),returning,stop['paused'],'paused')
    require(browser.get('stop')==stop['paused'] and stop['stable']['position_m']==stop['paused']['position_m'])
    return dict(status='PASS',semantic_plan_id=plan['plan_id'],arrival_distance_m=distance,
        current_request_bound=True,current_run_bound=True,moving_stop_bound=True,physical_authority=False)
