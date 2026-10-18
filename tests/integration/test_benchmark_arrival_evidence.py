# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Adversarial offline checks; never actual model, navigation or quality PASS."""
from copy import deepcopy
import unittest
from scripts.benchmark_arrival_evidence import validate_arrival
from scripts.benchmark_protocol import canonical_sha,text_sha


def evidence():
    text='Go to desk';packet=dict(goal=dict(expected='arrival',text=text,sha256=text_sha(text)))
    plan=dict(plan_id='goal-plan',mode='SIM',physical_authority=False,scene_revision='scene',goal=[1.,1.])
    base=dict(engine_session_id='engine',stage_epoch='epoch',sequence=10,run_id='preview',runtime_state='completed',
        applied_revision='scene',telemetry_available=True,safety_state=None,position_m=[0.,0.,0.],distance_to_goal_m=0.)
    arrival={**base,'sequence':20,'run_id':'goal-plan','position_m':[1.,1.,0.]}
    operation=dict(command_id='new',command_type='run',status='succeeded',expected_applied_revision='scene',
        engine_session_id='engine',stage_epoch='epoch')
    returning={**plan,'plan_id':'return','goal':[0.,0.]}
    running={**arrival,'run_id':'return','sequence':30,'runtime_state':'running'}
    paused={**running,'sequence':40,'runtime_state':'paused','position_m':[.9,.9,0.]}
    stable={**paused,'sequence':50}
    proof=dict(schema_version='benchmark-arrival-1.0',case_sha256=canonical_sha(packet),goal_sha256=text_sha(text),goal_text=text,
        before=dict(cursor=10,request_id='preview-request',snapshot=base,operations=[]),
        review=dict(request_id='goal-request',text=text,scene_revision='scene',plan=plan,target=None),
        event=dict(sequence=11,type='simulation_route_reviewed',payload=dict(plan_id='goal-plan',scene_revision='scene')),
        arrival=arrival,operations=[operation])
    return packet,dict(initial_preview_plan=dict(plan_id='preview'),semantic_goal_evidence=proof,semantic_arrival=arrival,
        stop_test_input='Go to X=0 Y=0',stop=paused,stop_test_evidence=dict(before=arrival,
            review=dict(plan=returning,text='Go to X=0 Y=0'),running=running,paused=paused,stable=stable))


class ArrivalEvidenceTests(unittest.TestCase):
    def test_current_semantic_goal_run_and_moving_stop_are_bound(self):
        packet,browser=evidence();old=deepcopy(browser)
        self.assertEqual(validate_arrival(packet,browser)['status'],'PASS')
        self.assertEqual(browser,old)

    def test_old_completion_false_distance_missing_or_wrong_run_receipts_fail(self):
        changes=(lambda b:b['semantic_goal_evidence']['review'].update(request_id='preview-request'),
            lambda b:b['semantic_goal_evidence']['event'].update(sequence=10),
            lambda b:b['semantic_goal_evidence']['review']['plan'].update(plan_id='preview'),
            lambda b:b['semantic_arrival'].update(run_id='preview'),
            lambda b:b['semantic_arrival'].update(position_m=[.5,.5,0.]),
            lambda b:b['semantic_arrival'].update(sequence=10),
            lambda b:b['semantic_arrival'].update(stage_epoch='other'),
            lambda b:b['semantic_goal_evidence'].update(operations=[]),
            lambda b:b['semantic_goal_evidence']['operations'][0].update(status='failed'),
            lambda b:b['stop_test_evidence']['running'].update(runtime_state='completed'),
            lambda b:b['stop_test_evidence']['stable'].update(position_m=[.8,.9,0.]),
            lambda b:b.pop('semantic_goal_evidence'))
        for change in changes:
            with self.subTest(change=change):
                packet,browser=evidence();change(browser)
                with self.assertRaisesRegex(ValueError,'EVIDENCE_INVALID'):validate_arrival(packet,browser)
