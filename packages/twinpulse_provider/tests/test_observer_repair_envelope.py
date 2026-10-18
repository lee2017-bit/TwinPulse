# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Rejected envelopes retain repair context; no live inference or credentials."""
import asyncio
from copy import deepcopy
import io
import json
import time
import unittest
import urllib.error

from packages.twinpulse_provider.tests.test_nebius_pipeline import (
    OBSERVER_MODEL, PLANNER_MODEL, completion, config, observation, request,
)
from twinpulse_provider import CancellationToken, InvalidProviderResponseError, ProviderRequestError
from twinpulse_provider.nebius_pipeline import (
    NebiusChatCompletionsPipelineProvider, ObservationArtifact,
    UrllibChatCompletionsTransport, parse_chat_completion,
)


class ObserverRepairEnvelopeTests(unittest.TestCase):
    def run_repair(self, first, *, expected_roles):
        bodies = []
        class Transport:
            async def complete(self, body, token, cfg):
                bodies.append(deepcopy(body))
                if len(bodies) == 1:
                    if isinstance(first, Exception): raise first
                    return parse_chat_completion(first)
                return completion('repaired', OBSERVER_MODEL, observation())
        provider = NebiusChatCompletionsPipelineProvider(Transport(), observer_model_id=OBSERVER_MODEL,
            planner_model_id=PLANNER_MODEL, site_plan_version='2.2', max_repairs=1)
        original = provider.build_observer_body(request())
        before = deepcopy(original)
        state = dict(request_id='offline', repair_count=0, attempts=[], sequence=0)
        provider._diagnostic = state
        _, value = asyncio.run(provider._validated_stage('observer', original,
            lambda c: ObservationArtifact.from_mapping(json.loads(c.content)),
            CancellationToken(), config(), state, time.monotonic()+30))
        self.assertEqual([m['role'] for m in bodies[1]['messages']], expected_roles)
        self.assertEqual(original, before)
        self.assertEqual(state['repair_count'], 1)
        self.assertEqual(value.to_dict(), observation())
        return bodies, state

    def test_length_retains_rejected_content_usage_and_error_code(self):
        payload = dict(id='partial', model=OBSERVER_MODEL, choices=[dict(
            finish_reason='length', message=dict(content='{"schema_version": "1.0",'))],
            usage=dict(prompt_tokens=500, completion_tokens=10000, total_tokens=10500))
        with self.assertRaises(InvalidProviderResponseError) as caught:
            parse_chat_completion(payload)
        self.assertEqual(caught.exception.code, 'PROVIDER_OUTPUT_TRUNCATED')
        self.assertEqual(caught.exception.partial_completion.content,payload['choices'][0]['message']['content'])
        self.assertFalse(caught.exception.repairable)
        bodies=[]
        class Transport:
            async def complete(self,body,token,cfg):
                bodies.append(deepcopy(body))
                return parse_chat_completion(payload)
        provider=NebiusChatCompletionsPipelineProvider(Transport(),observer_model_id=OBSERVER_MODEL,
            planner_model_id=PLANNER_MODEL,site_plan_version='2.2',max_repairs=1)
        state=dict(request_id='offline',repair_count=0,attempts=[],sequence=0)
        provider._diagnostic=state
        with self.assertRaises(InvalidProviderResponseError):
            asyncio.run(provider._validated_stage('observer',provider.build_observer_body(request()),
                lambda c:None,CancellationToken(),config(),state,time.monotonic()+30))
        self.assertEqual(len(bodies),1)
        self.assertEqual(state['repair_count'],0)
        self.assertEqual(state['stop_reason'],'output_limit_reached')
        self.assertEqual(state['attempts'][0]['validation_code'], 'PROVIDER_OUTPUT_TRUNCATED')
        self.assertEqual(state['attempts'][0]['usage'], payload['usage'])

    def test_no_response_content_merges_feedback_without_fabricating_assistant(self):
        bodies, _ = self.run_repair(InvalidProviderResponseError('Chat Completions response is not valid JSON'),
                                   expected_roles=['system','user'])
        self.assertEqual(len(bodies[1]['messages'][1]['content']), 3)
        self.assertEqual(bodies[1]['messages'][1]['content'][1]['type'], 'image_url')

    def test_unsupported_content_shape_is_repairable_not_an_envelope_error(self):
        self.run_repair(dict(id='schema-not-data',model=OBSERVER_MODEL,choices=[dict(
            finish_reason='stop',message=dict(content='{"type":"object"}'))]),
            expected_roles=['system','user','assistant','user'])

    def test_malformed_finish_reason_is_a_typed_nonrepairable_envelope_error(self):
        for value in ([],{},None,'tool_calls'):
            with self.subTest(value=value), self.assertRaises(InvalidProviderResponseError):
                parse_chat_completion(dict(choices=[dict(finish_reason=value)]))

    def test_kind_failure_has_exact_field_and_observer_only_feedback(self):
        value=deepcopy(observation())
        value['entities'][0]['kind']='bed'
        payload=dict(id='invalid-kind',model=OBSERVER_MODEL,choices=[dict(
            finish_reason='stop',message=dict(content=json.dumps(value)))])
        bodies,state=self.run_repair(payload,expected_roles=['system','user','assistant','user'])
        issue=state['attempts'][0]['scene_contract']['issues'][0]
        self.assertEqual(issue['code'],'OBSERVER_ENTITY_KIND_INVALID')
        self.assertEqual(issue['path'],'$.entities[0].kind')
        self.assertIn('static_obstacle',issue['allowed'])
        feedback=json.loads(bodies[1]['messages'][-1]['content'])
        self.assertNotIn('Use the required floor_call slot',feedback['contract_repair'])
        self.assertIn('observation JSON',feedback['constraints'])
        self.assertNotIn('0.1m',feedback['constraints'])

    def test_invalid_id_is_distinct_from_invalid_kind(self):
        value=deepcopy(observation());value['entities'][0]['id']='invalid id'
        with self.assertRaises(InvalidProviderResponseError) as caught:
            ObservationArtifact.from_mapping(value)
        self.assertEqual(caught.exception.code,'OBSERVER_ENTITY_ID_INVALID')
        self.assertEqual(caught.exception.contract_report['issues'][0]['path'],'$.entities[0].id')

    def test_truncated_wrong_identity_never_repairs(self):
        class Transport:
            calls = 0
            async def complete(self, body, token, cfg):
                self.calls += 1
                return parse_chat_completion(dict(id='partial', model='wrong-model',
                    choices=[dict(finish_reason='length', message=dict(content='{"unfinished":'))]))
        transport = Transport()
        provider = NebiusChatCompletionsPipelineProvider(transport,observer_model_id=OBSERVER_MODEL,
            planner_model_id=PLANNER_MODEL,site_plan_version='2.2',max_repairs=1)
        state = dict(request_id='offline',repair_count=0,attempts=[],sequence=0)
        provider._diagnostic = state
        with self.assertRaises(InvalidProviderResponseError) as caught:
            asyncio.run(provider._validated_stage('observer',provider.build_observer_body(request()),
                lambda c: None,CancellationToken(),config(),state,time.monotonic()+30))
        self.assertEqual(transport.calls, 1)
        self.assertEqual(caught.exception.code, 'PROVIDER_MODEL_MISMATCH')

    def test_http400_is_rejected_not_unknown(self):
        def opener(req, timeout):
            raise urllib.error.HTTPError(req.full_url,400,'bad request',{},io.BytesIO(b'{}'))
        provider = NebiusChatCompletionsPipelineProvider(
            UrllibChatCompletionsTransport(lambda:'synthetic-not-a-secret',opener=opener),
            observer_model_id=OBSERVER_MODEL,planner_model_id=PLANNER_MODEL)
        with self.assertRaises(ProviderRequestError) as caught:
            asyncio.run(provider._complete_stage('observer',provider.build_observer_body(request()),
                                                CancellationToken(),config()))
        self.assertEqual(caught.exception.http_status, 400)
        self.assertEqual(provider._diagnostic['attempts'][0]['status'], 'rejected')
        self.assertEqual(provider._diagnostic['attempts'][0]['http_status'], 400)


if __name__ == '__main__': unittest.main()
