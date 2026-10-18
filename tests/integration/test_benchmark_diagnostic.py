# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Saved diagnostic evidence validation, not an actual Isaac/model trial."""
from copy import deepcopy
import unittest
from scripts.benchmark_diagnostic import validate_diagnostic
from scripts.benchmark_protocol import canonical_sha,text_sha


def proof(expected='rejection'):
    text='Go to imaginary object'
    packet=dict(case_id='diagnostic',goal=dict(expected=expected,text=text,sha256=text_sha(text)))
    before=dict(scene_revision='scene',plan_sha256='plan',input_revision='input',cursor=10,
        operations=[dict(operation_id='old-run',command_type='run')],
        snapshot=dict(runtime_state='completed',telemetry_available=True,applied_revision='scene',run_id='sim',position_m=[1.,2.,0.]))
    event=dict(sequence=12,type='simulation_goal_rejected',payload=dict(request_id='request',
        scene_revision='scene',code='simulation_goal_rejected',goal_error_code='SIM_TARGET_NOT_FOUND'))
    after={**deepcopy(before), 'event':event,'simulation_plan':None,'physical_authority':False,'goal_text':text,'card':None}
    if expected=='clarification':
        event.update(type='simulation_goal_clarification',payload=dict(request_id='request',scene_revision='scene',card_id='card'))
        after['card']=dict(id='card',kind='simulation_target',state='waiting',related_plan_digest='scene',
            choices=[dict(id='object_'+str(i),enabled=True) for i in range(2)])
    receipt=dict(schema_version='benchmark-goal-diagnostic-1.0',case_sha256=canonical_sha(packet),
        goal_sha256=packet['goal']['sha256'],request_id='request',before=before,after=after)
    return packet,receipt


class DiagnosticEvidenceTests(unittest.TestCase):
    def test_rejection_and_question_are_separate_from_arrival(self):
        for expected in ('rejection','clarification'):
            packet,receipt=proof(expected);before=deepcopy(receipt)
            result=validate_diagnostic(packet,receipt)
            self.assertEqual(result['status'],'PASS');self.assertFalse(result['semantic_goal_arrival'])
            self.assertFalse(result['physical_authority']);self.assertEqual(receipt,before)

    def test_false_success_stale_input_new_run_or_lost_pose_never_pass(self):
        for edit in (lambda r:r.update(case_sha256='wrong'),lambda r:r['after']['event'].update(sequence=10),
                     lambda r:r['after'].update(simulation_plan={'route':[]}),
                     lambda r:r['after']['operations'].append({'command_type':'run'}),
                     lambda r:r['after']['snapshot'].update(telemetry_available=False),
                     lambda r:r['after'].update(goal_text='other goal'),
                     lambda r:r['after']['event']['payload'].update(request_id='old')):
            packet,receipt=proof();edit(receipt)
            with self.assertRaisesRegex(ValueError,'EVIDENCE_INVALID'):validate_diagnostic(packet,receipt)

    def test_internal_stale_or_budget_failure_is_not_an_expected_rejection(self):
        for code in ('PLANNER_INTERNAL_ERROR','GRID_BUDGET_EXCEEDED','simulation_scene_stale','SIM_START_REQUIRED'):
            packet,receipt=proof();receipt['after']['event']['payload']['goal_error_code']=code
            with self.assertRaises(ValueError):validate_diagnostic(packet,receipt)
        packet,receipt=proof();receipt['after']['event']['payload'].update(
            goal_error_code='SIM_TARGET_NO_REACHABLE_APPROACH',goal_diagnostic={'termination_code':'PLANNER_BUDGET_EXHAUSTED'})
        with self.assertRaises(ValueError):validate_diagnostic(packet,receipt)

    def test_answered_or_single_choice_question_not_accepted(self):
        for edit in (lambda c:c.update(state='answered'),lambda c:c.update(choices=[c['choices'][0]]),
                     lambda c:c.update(related_plan_digest='old')):
            packet,receipt=proof('clarification');edit(receipt['after']['card'])
            with self.assertRaises(ValueError):validate_diagnostic(packet,receipt)

    def test_malformed_saved_evidence_is_a_typed_failure(self):
        for edit in (lambda r:r.update(before=[]),lambda r:r.update(after='bad'),
                     lambda r:r['before'].update(cursor='10'),lambda r:r['before'].update(cursor=True),
                     lambda r:r['before'].update(snapshot=[]),
                     lambda r:r['after'].update(event=[]),
                     lambda r:r['after']['event'].update(payload=[]),
                     lambda r:r['after'].update(goal_text=[])):
            packet,receipt=proof();edit(receipt)
            with self.assertRaisesRegex(ValueError,'EVIDENCE_INVALID'):validate_diagnostic(packet,receipt)
        for choices in (None,['not an object'],[dict(id=12,enabled=True)]):
            packet,receipt=proof('clarification');receipt['after']['card']['choices']=choices
            with self.assertRaisesRegex(ValueError,'EVIDENCE_INVALID'):validate_diagnostic(packet,receipt)


if __name__=='__main__':unittest.main()
