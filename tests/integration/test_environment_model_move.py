# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
"""Device-free supplementary contracts; fake completion, never live model/UI acceptance."""
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from twinpulse_app.command_broker import BrokerError
from twinpulse_app.library_asset_store import atomic_json
from twinpulse_core import canonical_sha256
from twinpulse_core.environment_source import move_environment
from twinpulse_core.execution_diagnostics import TraceContext
from twinpulse_provider.budgeted_pipeline import BudgetedPipeline
from twinpulse_provider.generation_policy import GenerationPolicy
from twinpulse_provider.nebius_pipeline import ChatCompletion
from tests.integration import test_environment_import as imported


OWNER = 'model-test-owner'
MODULE = 'twinpulse_app.environment_workspace'


class EnvironmentModelMoveTests(unittest.TestCase):
    @contextmanager
    def workspace(self, *, value=None, hook=None):
        """Real App/review/trace/parser; only completion and route selection are fake."""
        with imported.EnvironmentImportTests().reviewed_workspace() as (space, app, workflow, draft):
            route = {'supplementary_route': 'fake-no-network'}
            provider = object.__new__(BudgetedPipeline)
            provider.policy = GenerationPolicy()
            provider.planner_model_id = 'supplementary-fake-planner'
            provider.route_sha256 = canonical_sha256(route)
            provider.stage_output_token_caps = {'planner': 1000}
            provider.planner_template_no_thinking = False
            provider._transport = SimpleNamespace(record_validation=Mock())
            provider.diagnostic_for = Mock(return_value={'status': 'supplementary-fake-completion'})
            calls = []
            output = value if value is not None else self.output()

            async def complete(stage, body, token, config):
                self.assertIsInstance(token.diagnostics, TraceContext)
                calls.append((deepcopy(body), token.diagnostics))
                if hook:
                    hook(space, app, workflow, draft, token)
                return ChatCompletion('fake-response', provider.planner_model_id,
                                      json.dumps(output), 'stop', {}, 'fake-attempt')

            provider._complete_stage = complete
            space.registry = object()
            deferred = SimpleNamespace(start=lambda: None, is_alive=lambda: False)
            with (patch(MODULE + '.Thread', return_value=deferred),
                  patch('twinpulse_app.stage_routing.build_configured_stage_service',
                        return_value=SimpleNamespace(_provider=provider, _config=object())),
                  patch('twinpulse_app.stage_routing.StageRoutingSettings',
                        return_value=SimpleNamespace(load=lambda: route))):
                try:
                    yield space, app, workflow, draft, provider, calls
                finally:
                    space.shutdown()

    def output(self, **changes):
        return dict(schema_version='environment-move-1.0', mode='move',
                    object_id=imported.source()['meshes'][1]['id'], translation_m=[.1, 0, 0],
                    explanation='Move the selected object 10 cm along X.', **changes)

    def start(self, space):
        state = space.snapshot(OWNER)
        response = space.action(dict(action='model_move_preview', request_id='model-request',
            object_id=imported.source()['meshes'][1]['id'], text='Move 10 cm along X',
            expected_scene_revision=state['scene_revision']), OWNER)
        self.assertEqual(response['proposal']['status'], 'running')
        return space.proposal, space.proposal_token

    def run_model(self, space):
        job, token = self.start(space)
        space._model_move(job, token)
        return job, token

    def review(self, space):
        return space.action(dict(action='model_review', request_id='review-request',
            job_id=space.proposal['job_id'], expected_scene_revision=space.proposal['source_revision']), OWNER)

    def advance_revision(self, space, app, workflow, draft):
        history = app.scene_change_store().load()
        _, site = history.replay(draft)
        moved = move_environment(site.scene.environment, imported.source()['meshes'][1]['id'], [.05, 0, 0])
        edit = history.preview(draft, operation_id='intervening-edit', mode='change',
                               target_call_id='imported_space', tool_call=imported.plan(moved).calls[0].to_dict())
        workflow._publish_scene_change(app.scene_change_store(),
            app.scene_change_store().apply(edit['operation'], edit['preview_digest']))

    def test_real_trace_and_parser_publish_persisted_suggestion_without_preview_or_apply(self):
        with self.workspace() as (space, app, workflow, draft, provider, calls):
            original = app.scene_change_store().load()
            job, token = self.run_model(space)
            self.assertEqual(job['status'], 'ready', job.get('error'))
            self.assertFalse(token.is_cancelled)
            self.assertEqual(len(calls), 1)
            sent = json.loads(calls[0][0]['messages'][-1]['content'])
            self.assertEqual(sent, dict(object_id=job['_object_id'], text=job['_text']))
            self.assertEqual(set(sent), {'object_id', 'text'})
            self.assertNotIn('preview', job)
            self.assertFalse(space.previews)
            self.assertEqual(app.scene_change_store().load(), original)
            folder = space.root / 'model-proposals' / job['job_id']
            request = json.loads((folder / 'request.json').read_text(encoding='utf-8'))
            self.assertEqual(request['images_sent'], 0)
            self.assertIs(request['mesh_sent'], False)
            self.assertEqual(json.loads((folder / 'job.json').read_text(encoding='utf-8'))['status'], 'ready')
            self.assertNotIn(OWNER,(folder / 'job.json').read_text(encoding='utf-8'))
            self.assertNotIn('_owner',json.loads((folder / 'job.json').read_text(encoding='utf-8')))
            self.assertTrue(app.diagnostics.flush())
            trace = calls[0][1]
            manifest = json.loads((app.diagnostics.root / trace.execution_id / 'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['metadata']['request_id'], 'model-request')
            self.assertEqual(manifest['metadata']['operation_id'], job['job_id'])
            events = [json.loads(line) for path in (app.diagnostics.root / trace.execution_id).glob('events*.jsonl')
                      for line in path.read_text(encoding='utf-8').splitlines()]
            self.assertTrue(any(event.get('status') == 'succeeded' for event in events))
            # Repeated ordinary GET is observation only, without compilation.
            with patch.object(workflow, 'preview_scene_edit', side_effect=AssertionError('compile on GET')):
                for _ in range(3):
                    self.assertNotIn('preview', space.snapshot(OWNER)['proposal'])
            self.assertEqual(len(calls), 1)

    def test_initial_mkdir_failure_is_failed_without_dispatch_or_escaping(self):
        with self.workspace() as (space, app, workflow, draft, provider, calls):
            job, token = self.start(space)
            folder = space.root / 'model-proposals' / job['job_id']
            original = Path.mkdir

            def mkdir(path, *args, **kwargs):
                if path == folder:
                    raise OSError('original proposal mkdir failure')
                return original(path, *args, **kwargs)

            with patch.object(Path, 'mkdir', mkdir):
                space._model_move(job, token)
            self.assertEqual(job['status'], 'failed')
            self.assertIn('original proposal mkdir failure', job['error'])
            self.assertFalse(token.is_cancelled)
            self.assertEqual(calls, [])
            self.assertNotIn('suggestion', job)

    def test_initial_trace_failure_is_preserved_and_never_dispatches(self):
        with self.workspace() as (space, app, workflow, draft, provider, calls):
            job, token = self.start(space)
            with patch.object(app.diagnostics, 'begin', side_effect=OSError('original begin failure')):
                space._model_move(job, token)
            self.assertEqual(job['status'], 'failed')
            self.assertIn('original begin failure', job['error'])
            self.assertFalse(token.is_cancelled)
            self.assertEqual(calls, [])

    def test_diagnostic_or_result_storage_failure_never_publishes_ready(self):
        for target in ('provider-diagnostic.json', 'result.json', 'job.json', 'trace-finish'):
            with self.subTest(target=target), self.workspace() as (space, app, workflow, draft, provider, calls):
                job, token = self.start(space)

                def save(path, value):
                    if path.name == target:
                        raise OSError('injected ' + target)
                    return atomic_json(path, value)

                with patch(MODULE + '.atomic_json', side_effect=save):
                    if target == 'trace-finish':
                        with patch.object(TraceContext, 'finish', side_effect=OSError('injected trace finish')):
                            space._model_move(job, token)
                    else:
                        space._model_move(job, token)
                self.assertEqual(job['status'], 'failed', job)
                self.assertNotIn('suggestion', job)
                self.assertNotIn('preview', job)
                self.assertFalse(token.is_cancelled)
                self.assertEqual(len(calls), 1)

    def test_invalid_provider_output_and_clarification_fail_without_cancelling_or_retry(self):
        for changes, fragment in (({'translation_m': [3, 0, 0]}, 'DELTA_INVALID'),
                                  ({'object_id': 'wrong-object'}, 'OUTPUT_INVALID'),
                                  ({'mode': 'clarify', 'translation_m': None}, 'Clarification required')):
            value = self.output()
            value.update(changes)
            with self.subTest(changes=changes), self.workspace(value=value) as (space, app, workflow, draft, provider, calls):
                job, token = self.run_model(space)
                self.assertEqual(job['status'], 'failed', job)
                self.assertIn(fragment, job['error'])
                self.assertFalse(token.is_cancelled)
                self.assertNotIn('suggestion', job)
                self.assertEqual(len(calls), 1)

    def test_primary_provider_error_survives_secondary_diagnostic_storage_failure(self):
        value = self.output()
        value['translation_m'] = [9, 0, 0]
        with self.workspace(value=value) as (space, app, workflow, draft, provider, calls):
            def save(path, value):
                if path.name == 'provider-diagnostic.json':
                    raise OSError('secondary diagnostic failure')
                return atomic_json(path, value)
            with patch(MODULE + '.atomic_json', side_effect=save):
                job, token = self.run_model(space)
            self.assertEqual(job['status'], 'failed')
            self.assertIn('DELTA_INVALID', job['error'])
            self.assertIn('secondary diagnostic failure', ' '.join(job['diagnostic_storage_errors']))
            self.assertFalse(token.is_cancelled)

    def test_completion_rechecks_project_source_revision_and_cancel_fences(self):
        for changed in ('project', 'source', 'revision', 'cancel', 'replaced', 'closed'):
            def change(space, app, workflow, draft, token):
                if changed == 'project':
                    workflow._broker.project_id = 'different-project'
                elif changed == 'source':
                    workflow._site_artifact.scene.environment['source_sha256'] = 'b' * 64
                elif changed == 'revision':
                    self.advance_revision(space, app, workflow, draft)
                elif changed == 'cancel':
                    token.cancel()
                elif changed == 'replaced':
                    space.proposal = dict(space.proposal, job_id='replacement')
                else:
                    space.closed = True

            with self.subTest(changed=changed), self.workspace(hook=change) as (space, app, workflow, draft, provider, calls):
                job, token = self.run_model(space)
                if changed == 'replaced':
                    self.assertNotEqual(space.proposal['job_id'], job['job_id'])
                    self.assertNotEqual(space.proposal['status'], 'ready')
                    persisted = json.loads((space.root / 'model-proposals' / job['job_id'] / 'job.json').read_text(encoding='utf-8'))
                    self.assertEqual(persisted['status'], 'failed')
                else:
                    self.assertEqual(job['status'], 'cancelled' if changed == 'cancel' else 'failed', job)
                    self.assertNotIn('suggestion', job)
                self.assertEqual(token.is_cancelled, changed == 'cancel')
                self.assertEqual(len(calls), 1)

    def test_owner_review_and_cancel_are_scoped_and_cancel_revokes_pinned_apply(self):
        with self.workspace() as (space, app, workflow, draft, provider, calls):
            job, token = self.run_model(space)
            self.assertNotIn('proposal', space.snapshot('another-owner'))
            for action in ('model_review', 'model_cancel'):
                body = dict(action=action, request_id='wrong-owner', job_id=job['job_id'])
                if action == 'model_review':
                    body['expected_scene_revision'] = job['source_revision']
                with self.subTest(action=action), self.assertRaises((ValueError, BrokerError)):
                    space.action(body, 'another-owner')
            self.assertFalse(token.is_cancelled)
            reviewed = self.review(space)
            preview = reviewed['preview']
            identity, digest = preview['operation']['operation_id'], preview['preview_digest']
            self.assertEqual(space.pinned_environment_operation(identity, digest, OWNER)[1], digest)
            with self.assertRaises(BrokerError):
                space.pinned_environment_operation(identity, digest, 'another-owner')
            self.assertEqual(app.scene_change_store().load().operations, ())
            space.action(dict(action='model_cancel', request_id='cancel-request', job_id=job['job_id']), OWNER)
            self.assertTrue(token.is_cancelled)
            self.assertNotIn('preview', job)
            with self.assertRaises((ValueError, BrokerError)):
                space.pinned_environment_operation(identity, digest, OWNER)
            with self.assertRaises((ValueError, BrokerError)):
                self.review(space)
            self.assertEqual(len(calls), 1)

    def test_pinned_apply_rechecks_project_source_revision_after_review(self):
        for changed in ('project', 'source', 'revision'):
            with self.subTest(changed=changed), self.workspace() as (space, app, workflow, draft, provider, calls):
                job, token = self.run_model(space)
                preview = self.review(space)['preview']
                if changed == 'project':
                    workflow._broker.project_id = 'different-project'
                elif changed == 'source':
                    workflow._site_artifact.scene.environment['source_sha256'] = 'b' * 64
                else:
                    self.advance_revision(space, app, workflow, draft)
                with self.assertRaises((ValueError, BrokerError)):
                    space.pinned_environment_operation(preview['operation']['operation_id'], preview['preview_digest'], OWNER)
                self.assertFalse(token.is_cancelled)
                self.assertEqual(len(calls), 1)

    def test_apply_claim_blocks_later_cancel_and_review_without_retracting_admission(self):
        with self.workspace() as (space, app, workflow, draft, provider, calls):
            job, token = self.run_model(space)
            preview = self.review(space)['preview']
            identity, digest = preview['operation']['operation_id'], preview['preview_digest']
            # Observation is not admission; wrong identity must not latch it.
            space.pinned_environment_operation(identity, digest, OWNER)
            self.assertFalse(job.get('_apply_admitted', False))
            for owner, sha in (('another-owner', digest), (OWNER, '0' * 64)):
                with self.subTest(owner=owner, digest=sha), self.assertRaises(BrokerError):
                    space.pinned_environment_operation(identity, sha, owner, claim=True)
                self.assertFalse(job.get('_apply_admitted', False))
            operation, returned_digest = space.pinned_environment_operation(identity, digest, OWNER, claim=True)
            self.assertEqual(canonical_sha256(operation), returned_digest)
            self.assertTrue(job['_apply_admitted'])
            with self.assertRaises(BrokerError) as caught:
                space.action(dict(action='model_cancel', request_id='cancel-after-claim', job_id=job['job_id']), OWNER)
            self.assertEqual(caught.exception.code, 'environment_apply_admitted')
            with self.assertRaisesRegex(ValueError, 'ENVIRONMENT_APPLY_ALREADY_ADMITTED'):
                self.review(space)
            self.assertFalse(token.is_cancelled)
            self.assertEqual(job['status'], 'ready')
            self.assertIn(identity, space.previews)
            # This tests admission, not a dispatched Isaac transaction or Apply success.
            self.assertEqual(app.scene_change_store().load().operations, ())

    def test_cancel_before_apply_claim_revokes_capability_without_admitting(self):
        with self.workspace() as (space, app, workflow, draft, provider, calls):
            job, token = self.run_model(space)
            preview = self.review(space)['preview']
            space.action(dict(action='model_cancel', request_id='cancel-before-claim', job_id=job['job_id']), OWNER)
            with self.assertRaises(BrokerError):
                space.pinned_environment_operation(preview['operation']['operation_id'],
                                                  preview['preview_digest'], OWNER, claim=True)
            self.assertFalse(job.get('_apply_admitted', False))
            self.assertTrue(token.is_cancelled)
            self.assertEqual(job['status'], 'cancelled')

    def test_real_diagnostic_sink_failure_cannot_be_silent_ready(self):
        with self.workspace() as (space, app, workflow, draft, provider, calls):
            job, token = self.start(space)
            # ExecutionStore deliberately catches IO errors. Exercise that real
            # degraded receipt instead of only making begin/finish raise.
            with patch.object(app.diagnostics, '_directory', side_effect=OSError('diagnostic sink unavailable')):
                space._model_move(job, token)
                self.assertTrue(app.diagnostics.health['diagnostics_degraded'])
            self.assertEqual(job['status'], 'failed', 'A swallowed diagnostic write failure must not publish ready.')
            self.assertNotIn('suggestion', job)
            self.assertFalse(token.is_cancelled)


if __name__ == '__main__':
    unittest.main()
