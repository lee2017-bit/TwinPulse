# SPDX-License-Identifier: Apache-2.0
"""Synthetic, device-free gate unit tests; never actual model/installed acceptance."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from scripts import verify_roomplan_preparation_gate as gate


RELEASE = 'supplementary-synthetic-release'
SOURCE, USD, REVISION, GRID = ('a' * 64, 'b' * 64, 'c' * 64, 'd' * 64)
MOVED, UNDONE = 'e' * 64, 'f' * 64
MODEL = 'nvidia/nemotron-3-super-120b-a12b'
PROJECT = 'chat_synthetic_contract_only'


def fixture_records():
    """Known-valid shape for unit tests; no claim these fabricated bytes are live evidence."""
    records = {'base_gate': dict(schema='robot-focused-evidence-gate-1.0', status=gate.READY,
        issues=[], release_id=RELEASE, source_sha256=SOURCE)}
    environment = dict(project_id=PROJECT, source_sha256=USD, status='imported', scene_revision=REVISION)
    for role, steps in gate.REQUIRED.items():
        records[role] = dict(phase='ai-edit' if role == 'ai_edit' else role, status='PASS',
            versions=dict(engine=dict(release_id=RELEASE)), errors=[], hardware_actions=0,
            user_agent='Synthetic unit fixture Electron/0', response_gate=dict(status='PASS', issues=[]),
            steps=[dict(name=name, status='PASS') for name in steps],
            responses=[dict(method='GET', status=200, path='/v1/product/environment', body=deepcopy(environment))])
    records['cold']['selected_project'] = PROJECT
    records['cold']['responses'][0]['body']['scene_revision'] = UNDONE
    registered = dict(robot_id='robot', operation_id='operation', connection_epoch='connection',
        source_twin_context=dict(project_id=PROJECT, scene_revision=UNDONE))
    sim = records['sim']
    sim['registered'] = registered
    sim['arrival'] = {**registered, 'command': dict(state='ARRIVED', target_id=gate.SOFA)}
    sim['shared_map'] = dict(status='AVAILABLE', kind='imported', source_sha256=USD,
        units_basis='selected_for_sim', physical_accuracy='UNQUALIFIED', meters_per_unit=1,
        geometry_revision=GRID, scene_revision=UNDONE)
    sim['responses'].append(dict(method='GET', status=200, path='/v1/product/robot-fleet',
                                body=dict(navigation_scene=deepcopy(sim['shared_map']))))
    sim['continuous_display'] = []
    for index in range(301):
        view = dict(at=100000 + index * 200, frame_id=1 + index, captured_at_ms=99950 + index * 200,
            frame_age_ms=50, live=True, canvas_visible=True, stop_visible=True, pad_visible=True,
            robot_badge_visible=True, intersection_px2=0, scene_revision=UNDONE, stage_epoch='stage')
        sim['continuous_display'].append(dict(view=view, control_state='DRIVING', motion_epoch='held-epoch', sequence=index))
    sim['continuous'] = dict(first=deepcopy(sim['continuous_display'][0]['view']),
        last=deepcopy(sim['continuous_display'][-1]['view']), samples=301, duration_ms=60000)
    sim['stop_receipts'] = []
    for index in range(8):
        request = dict(action='stop', request_id='stop-' + str(index), robot_id='robot',
                       connection_epoch='connection', motion_epoch='old-' + str(index), payload={})
        receipt = {**registered, 'motion_epoch': 'new-' + str(index), 'control_state': 'PAUSED'}
        ack = {**receipt, 'applied_motion_epoch': receipt['motion_epoch']}
        sim['stop_receipts'].append(dict(request=request, receipt=receipt, engine_ack=ack))
        sim['responses'] += [dict(method='POST', path='/v1/product/robot-fleet', status=200,
            request=deepcopy(request), body=dict(robots=[deepcopy(receipt)])),
            dict(method='GET', path='/v1/product/robot-fleet', status=200, body=dict(robots=[deepcopy(ack)]))]
    prompt = dict(object_id=gate.CHAIR, text='Move 10 cm along world +X.')
    suggestion = dict(translation_m=[.1, 0, 0], explanation='Relative +X move.')
    job = dict(job_id='job', request_id='request', status='ready', source_revision=REVISION,
        model_id=MODEL, error=None, suggestion=suggestion, _project=PROJECT,
        _source_sha256=USD, _object_id=gate.CHAIR, _text=prompt['text'])
    records['model_job'] = job
    records['model_request'] = dict(project_id=PROJECT, source_sha256=USD, scene_revision=REVISION,
        request_id='request', prompt=prompt, images_sent=0, mesh_sent=False, model_id=MODEL)
    records['model_result'] = dict(schema_version='environment-move-1.0', mode='move',
        object_id=gate.CHAIR, **suggestion)
    usage = dict(prompt_tokens=100, completion_tokens=20, total_tokens=120)
    attempt = dict(model_id=MODEL, attempt_id='attempt', status='received', finish_reason='stop', usage=usage)
    records['model_diagnostic'] = dict(request_id='request', model_id=MODEL, status='proposal_ready',
        input_kind='selected_object_move_text_only', attempts=[attempt], finish_reason='stop', usage=usage,
        budget=dict(requests=1, cumulative_requests=1, automatic_retry=False, in_flight=None,
                    stop_reason='ENVIRONMENT_MOVE_PROPOSAL_READY'))
    records['model_ledger'] = dict(schema_version='product-usage-1.0', approval='synthetic-contract-only',
        requests=[dict(attempt_id='attempt', model_id=MODEL, status='received', usage=usage,
                       started_at='2026-10-23T00:00:00Z', finished_at='2026-10-23T00:00:01Z')])
    ai = records['ai_edit']
    ai['edit_origin'] = dict(project_id=PROJECT, source_sha256=USD, scene_revision=REVISION)
    ai['edit_transactions'] = []
    ai['model_proposal'] = {k:deepcopy(v) for k,v in job.items() if not k.startswith('_')}
    for request in (dict(action='model_move_preview', request_id='request', object_id=gate.CHAIR,
                         text=prompt['text'], expected_scene_revision=REVISION),
                    dict(action='model_review', request_id='review', job_id='job', expected_scene_revision=REVISION)):
        ai['responses'].append(dict(method='POST', path='/v1/product/environment/action', status=200, request=request))
    proof_rows = []
    for index, (identity, parent, result) in enumerate((('model-edit', REVISION, MOVED), ('undo-edit', MOVED, UNDONE))):
        preview_digest = ('1' if index == 0 else '2') * 64
        preview = dict(parent_revision=parent, result_revision=result, preview_digest=preview_digest,
                       operation=dict(operation_id=identity, mode='change' if index == 0 else 'undo',
                                      parent_revision=parent, result_revision=result))
        if index == 0:
            ai['responses'][-1]['body'] = {**deepcopy(environment), 'scene_revision':parent, 'preview':preview}
        else:
            ai['responses'].append(dict(method='POST', path='/v1/product/environment/action', status=200,
                request=dict(action='undo_preview', request_id='undo', expected_scene_revision=parent),
                body={**deepcopy(environment), 'scene_revision':parent, 'preview':preview}))
        apply_index = len(ai['responses'])
        ai['responses'] += [dict(method='POST', path='/v1/product/scene-edit/apply', status=202,
                                request=dict(schema_version='scene-edit-apply-2.0', environment_preview_id=identity, preview_digest=preview_digest),
                                body=dict(operation_id=identity, state='PREPARED', parent_revision=parent,
                                          result_revision=result, preview_digest=preview_digest, error=None)),
            dict(method='GET', path='/v1/product/scene-edit/transaction', status=200,
                 body=dict(operation_id=identity, state='COMMITTED', durable_committed=True,
                           engine_acknowledged=True, current_frame=True, parent_revision=parent, result_revision=result, error=None)),
            dict(method='GET', path='/v1/product/environment', status=200,
                 body={**deepcopy(environment), 'scene_revision':result})]
        proof_rows.append((apply_index, identity, parent, result, preview_digest, index))
    for i, response in enumerate(ai['responses']):
        response['at'] = 100000 + i * 100
    for start, identity, parent, result, preview_digest, index in proof_rows:
        ai['edit_transactions'].append(dict(expected=dict(mode='change' if index == 0 else 'undo',
            operation_id=identity, parent_revision=parent, result_revision=result, preview_digest=preview_digest,
            project_id=PROJECT, source_sha256=USD),
            apply=deepcopy(ai['responses'][start]), committed=deepcopy(ai['responses'][start + 1]),
            environment=deepcopy(ai['responses'][start + 2]), ui=dict(caption=gate.EDIT_COMMITTED_CAPTION,
                undo_enabled=True, preview_visible=False, frame=dict(live=True, scene_revision=result,
                    stage_epoch='stage', frame_id=100 + index, frame_age_ms=50))))
    return records


class RoomplanPreparationGateTests(unittest.TestCase):
    def materialize(self, root, records=None):
        records = fixture_records() if records is None else records
        refs = {}
        for role, value in records.items():
            raw = json.dumps(value).encode()
            path = role + '.json'
            (root / path).write_bytes(raw)
            refs[role] = dict(path=path, sha256=sha256(raw).hexdigest())
        return dict(release_id=RELEASE, source_sha256=SOURCE, source_usd_sha256=USD, refs=refs)

    def evaluate(self, mutate):
        records = fixture_records()
        mutate(records)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            return gate.verify(self.materialize(root, records), root)

    def test_synthetic_complete_contract_passes_only_the_gate_unit_test(self):
        result = self.evaluate(lambda records: None)
        self.assertEqual(result['status'], gate.READY, result['issues'])
        self.assertEqual(result['physical_outcomes'], 'NOT_RUN_ROBOT_OFF')
        self.assertEqual(len(result['evidence']), len(gate.ROLES))

    def test_every_required_step_is_mandatory(self):
        for role, names in gate.REQUIRED.items():
            for name in names:
                def remove(records):
                    records[role]['steps'] = [s for s in records[role]['steps'] if s['name'] != name]
                with self.subTest(role=role, name=name):
                    result = self.evaluate(remove)
                    self.assertEqual(result['status'], 'NOT_READY')
                    self.assertIn('MISSING_OR_FAILED_STEP:' + role + ':' + name, result['issues'])

    def test_wrong_release_base_gate_source_and_missing_model_ledger_reject(self):
        for role in ('base_gate', 'import', 'ai_edit', 'sim', 'cold'):
            def change(records):
                if role == 'base_gate':
                    records[role]['release_id'] = 'older'
                else:
                    records[role]['versions']['engine']['release_id'] = 'older'
            with self.subTest(role=role):
                self.assertEqual(self.evaluate(change)['status'], 'NOT_READY')
        self.assertEqual(self.evaluate(lambda records: records['base_gate'].update(source_sha256='0' * 64))['status'], 'NOT_READY')
        self.assertEqual(self.evaluate(lambda records: records.pop('model_ledger'))['status'], 'NOT_READY')

    def test_project_and_original_revision_cannot_be_mixed_across_journeys(self):
        for mutate in (lambda r: r['cold'].update(selected_project='other-project'),
                       lambda r: r['cold']['responses'][0]['body'].update(scene_revision='0' * 64),
                       lambda r: r['import']['responses'][0]['body'].update(source_sha256='0' * 64),
                       lambda r: r['sim']['registered']['source_twin_context'].update(project_id='other-project')):
            self.assertEqual(self.evaluate(mutate)['status'], 'NOT_READY')

    def test_undo_is_a_new_revision_and_original_revision_cannot_be_reused_as_live(self):
        rows = fixture_records()
        chain = gate.edit_revision_chain(rows['ai_edit'], REVISION)
        self.assertEqual(chain, dict(initial_revision=REVISION, moved_revision=MOVED,
                                    undone_revision=UNDONE, operation_ids=['model-edit', 'undo-edit']))
        self.assertEqual(len({REVISION, MOVED, UNDONE}), 3)
        for mutate in (lambda r: r['sim']['shared_map'].update(scene_revision=REVISION),
                       lambda r: r['sim']['registered']['source_twin_context'].update(scene_revision=REVISION),
                       lambda r: r['cold']['responses'][0]['body'].update(scene_revision=REVISION)):
            self.assertEqual(self.evaluate(mutate)['status'], 'NOT_READY')

    def test_numeric_preview_requires_explicit_mode_and_exact_selected_object_translation(self):
        row = fixture_records()['ai_edit']
        preview = next(r for r in row['responses'] if r.get('request', {}).get('action') == 'model_review')
        preview['request'] = dict(action='move_preview', request_id='numeric', object_id=gate.CHAIR,
                                  translation_m=[.1, 0, 0], expected_scene_revision=REVISION)
        self.assertIsNone(gate.edit_revision_chain(row, REVISION))
        expected = dict(initial_revision=REVISION, moved_revision=MOVED, undone_revision=UNDONE,
                        operation_ids=['model-edit', 'undo-edit'])
        self.assertEqual(gate.edit_revision_chain(row, REVISION, first_preview_action='move_preview'), expected)
        self.assertIsNone(gate.edit_revision_chain(row, REVISION, first_preview_action='any-action'))
        for key, value in [('object_id', 'wrong'), ('translation_m', [.2, 0, 0]), ('action', 'model_review')]:
            altered = deepcopy(row)
            request = next(r['request'] for r in altered['responses'] if r.get('request', {}).get('action') == 'move_preview')
            request[key] = value
            with self.subTest(key=key):
                self.assertIsNone(gate.edit_revision_chain(altered, REVISION, first_preview_action='move_preview'))
        for key, value in [('current_frame', False), ('parent_revision', UNDONE), ('result_revision', REVISION)]:
            altered = deepcopy(row)
            commit = next(r['body'] for r in altered['responses'] if r.get('body', {}).get('state') == 'COMMITTED')
            commit[key] = value
            with self.subTest(key=key):
                self.assertIsNone(gate.edit_revision_chain(altered, REVISION, first_preview_action='move_preview'))
        for change in ('wrong-preview', 'missing-ack', 'wrong-undo-parent'):
            altered = deepcopy(row)
            if change == 'wrong-preview':
                response = next(r for r in altered['responses'] if r.get('request', {}).get('action') == 'move_preview')
                response['body']['preview']['preview_digest'] = '0' * 64
            elif change == 'missing-ack':
                commit = next(r['body'] for r in altered['responses'] if r.get('body', {}).get('state') == 'COMMITTED')
                commit['engine_acknowledged'] = False
            else:
                altered['edit_transactions'][1]['expected']['parent_revision'] = REVISION
            with self.subTest(change=change):
                self.assertIsNone(gate.edit_revision_chain(altered, REVISION, first_preview_action='move_preview'))

    def test_apply_and_undo_require_ordered_matching_operation_parent_and_commit(self):
        def transaction(rows, index):
            return [r['body'] for r in rows['ai_edit']['responses'] if r.get('body', {}).get('state') == 'COMMITTED'][index]
        for mutate in (lambda r: transaction(r, 0).update(parent_revision=UNDONE),
                       lambda r: transaction(r, 1).update(parent_revision=REVISION),
                       lambda r: transaction(r, 1).update(result_revision=REVISION),
                       lambda r: transaction(r, 1).update(operation_id='other-operation'),
                       lambda r: transaction(r, 1).update(current_frame=False),
                       lambda r: r['ai_edit']['responses'].reverse()):
            self.assertEqual(self.evaluate(mutate)['status'], 'NOT_READY')

    def test_empty_or_malformed_records_are_not_ready_and_do_not_escape(self):
        for role in gate.ROLES:
            with self.subTest(role=role):
                self.assertEqual(self.evaluate(lambda rows: rows.update({role:{}}))['status'], 'NOT_READY')
        self.assertEqual(self.evaluate(lambda rows: rows['sim'].update(continuous_display=None))['status'], 'NOT_READY')

    def test_null_observation_body_is_empty_metadata_without_mutating_the_original(self):
        records = fixture_records()
        null = dict(method='GET', path='/v1/product/scene-edit/transaction', status=200, body=None)
        for role in gate.REQUIRED:
            records[role]['responses'].insert(0, deepcopy(null))
        original = deepcopy(records)
        self.assertEqual(gate.responses(records['ai_edit'])[0]['body'], {})
        self.assertIsNone(records['ai_edit']['responses'][0]['body'])
        with TemporaryDirectory() as directory:
            root = Path(directory)
            result = gate.verify(self.materialize(root, records), root)
        self.assertEqual(result['status'], gate.READY, result['issues'])
        self.assertEqual(records, original)

    def test_null_explicit_apply_or_required_commit_remains_not_ready(self):
        for field in ('apply', 'commit', 'preview'):
            def change(records):
                rows = records['ai_edit']['responses']
                if field == 'apply':
                    selected = next(r for r in rows if r.get('path') == '/v1/product/scene-edit/apply')
                elif field == 'preview':
                    selected = next(r for r in rows if r.get('request', {}).get('action') == 'model_review')
                else:
                    selected = next(r for r in rows if r.get('body', {}).get('state') == 'COMMITTED')
                selected['body'] = None
            with self.subTest(field=field):
                self.assertEqual(self.evaluate(change)['status'], 'NOT_READY')

    def test_old_first_commit_cannot_substitute_for_a_staged_undo(self):
        # Mirrors a recorder window ending after Undo STAGED: an earlier
        # COMMITTED label/GET for the first operation is not Undo evidence.
        def change(records):
            rows = records['ai_edit']['responses']
            earlier = deepcopy(next(r for r in rows if r.get('body', {}).get('state') == 'COMMITTED'))
            rows[:] = [r for r in rows if not (r.get('body', {}).get('state') == 'COMMITTED'
                                               and r['body'].get('operation_id') == 'undo-edit')]
            rows.append(earlier)
            rows.append(dict(method='GET', path='/v1/product/scene-edit/transaction', status=200, body=None))
        result = self.evaluate(change)
        self.assertEqual(result['status'], 'NOT_READY')
        self.assertIn('MODEL_APPLY_UNDO_PARENT_CHAIN_UNPROVEN', result['issues'])

    def test_recorder_claims_require_exact_original_post_get_environment_and_live_ui(self):
        mutations = {
            'no recorder claims': lambda r: r['ai_edit'].pop('edit_transactions'),
            'one recorder claim': lambda r: r['ai_edit']['edit_transactions'].pop(),
            'null apply claim': lambda r: r['ai_edit']['edit_transactions'][1].update(apply=None),
            'changed request digest': lambda r: r['ai_edit']['edit_transactions'][1]['apply']['request'].update(preview_digest='0' * 64),
            'other operation claim': lambda r: r['ai_edit']['edit_transactions'][1]['committed']['body'].update(operation_id='other'),
            'nonGET commit claim': lambda r: r['ai_edit']['edit_transactions'][1]['committed'].update(method='POST'),
            'non200 commit claim': lambda r: r['ai_edit']['edit_transactions'][1]['committed'].update(status=202),
            'null commit claim': lambda r: r['ai_edit']['edit_transactions'][1].update(committed=None),
            'no following environment': lambda r: r['ai_edit']['edit_transactions'][1].pop('environment'),
            'old following environment': lambda r: r['ai_edit']['edit_transactions'][1]['environment']['body'].update(scene_revision=MOVED),
            'null UI': lambda r: r['ai_edit']['edit_transactions'][1].update(ui=None),
            'no canvas': lambda r: r['ai_edit']['edit_transactions'][1]['ui'].pop('frame'),
            'stale canvas': lambda r: r['ai_edit']['edit_transactions'][1]['ui']['frame'].update(frame_age_ms=1000),
            'old canvas': lambda r: r['ai_edit']['edit_transactions'][1]['ui']['frame'].update(scene_revision=MOVED),
            'not live': lambda r: r['ai_edit']['edit_transactions'][1]['ui']['frame'].update(live=False),
            'old caption': lambda r: r['ai_edit']['edit_transactions'][1]['ui'].update(caption='Edit BUILDING'),
            'locked undo': lambda r: r['ai_edit']['edit_transactions'][1]['ui'].update(undo_enabled=False),
            'preview still visible': lambda r: r['ai_edit']['edit_transactions'][1]['ui'].update(preview_visible=True),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                self.assertEqual(self.evaluate(mutate)['status'], 'NOT_READY')

    def test_matching_but_invalid_original_commit_or_environment_is_rejected(self):
        # Change both the claim and matching original, proving the gate checks
        # HTTP semantics as well as equality with a saved recorder claim.
        for field, change in (
            ('committed', lambda row: row.update(method='POST')),
            ('committed', lambda row: row.update(status=202)),
            ('committed', lambda row: row.update(path='/unrelated')),
            ('committed', lambda row: row['body'].update(error='original failure')),
            ('environment', lambda row: row.update(method='POST')),
            ('environment', lambda row: row.update(status=202)),
            ('environment', lambda row: row.update(path='/unrelated')),
            ('environment', lambda row: row['body'].update(scene_revision=MOVED)),
            ('apply', lambda row: row['request'].update(preview_digest='0' * 64)),
        ):
            def mutate(records):
                claim = records['ai_edit']['edit_transactions'][1][field]
                original = next(row for row in records['ai_edit']['responses'] if row.get('at') == claim['at'])
                change(original)
                change(claim)
            with self.subTest(field=field, change=change):
                self.assertEqual(self.evaluate(mutate)['status'], 'NOT_READY')

    def test_original_failed_ui_is_never_promoted_by_ignoring_null_observations(self):
        def change(records):
            records['ai_edit'].update(status='FAIL', response_gate={'status':'FAIL', 'issues':['original 409']})
            records['ai_edit']['responses'].append(dict(method='GET', path='/v1/product/scene-edit/transaction', status=200, body=None))
        result = self.evaluate(change)
        self.assertEqual(result['status'], 'NOT_READY')
        self.assertIn('UI_NOT_WHOLE_PASS:ai_edit', result['issues'])

    def test_short_hold_stale_frames_gap_epoch_scene_and_offgrid_map_reject(self):
        mutations = {
            'short hold': lambda s: s['continuous'].update(duration_ms=59999),
            'short display': lambda s: s['continuous_display'][-1]['view'].update(at=159999),
            'stale': lambda s: s['continuous_display'][100]['view'].update(frame_age_ms=1000),
            'gap': lambda s: s['continuous_display'][100]['view'].update(at=121001),
            'paused': lambda s: s['continuous_display'][100].update(control_state='PAUSED'),
            'epoch': lambda s: s['continuous_display'][100].update(motion_epoch='changed'),
            'scene': lambda s: s['continuous_display'][100]['view'].update(scene_revision='0' * 64),
            'stage': lambda s: s['continuous_display'][100]['view'].update(stage_epoch='changed'),
            'offgrid': lambda s: s['shared_map'].update(geometry_revision='0' * 64),
            'map stale': lambda s: s['shared_map'].update(status='UNAVAILABLE'),
            'map source': lambda s: s['shared_map'].update(source_sha256='0' * 64),
            'measured promotion': lambda s: s['shared_map'].update(physical_accuracy='MEASURED'),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                self.assertEqual(self.evaluate(lambda records: mutate(records['sim']))['status'], 'NOT_READY')

    def test_exact_stop_original_receipt_new_epoch_and_sofa_identity_are_required(self):
        mutations = [lambda s: s.update(stop_receipts=[]),
            lambda s: s['stop_receipts'][0]['engine_ack'].update(applied_motion_epoch='old-0'),
            lambda s: s['stop_receipts'][0]['request'].update(request_id='not-original'),
            lambda s: s['arrival']['command'].update(target_id='different-sofa')]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                self.assertEqual(self.evaluate(lambda records: mutate(records['sim']))['status'], 'NOT_READY')

    def test_model_counter_alone_fake_ledger_usage_or_other_selected_id_cannot_pass(self):
        mutations = [lambda r: r.update(model_ledger={}),
            lambda r: r['model_diagnostic'].update(attempts=[]),
            lambda r: r['model_diagnostic'].update(request_id='different-request'),
            lambda r: r['model_ledger']['requests'][0].update(attempt_id='different-attempt'),
            lambda r: r['model_ledger']['requests'][0].update(usage={}),
            lambda r: r['model_ledger']['requests'][0].update(status='outcome_unknown'),
            lambda r: r['model_request']['prompt'].update(mesh=[1, 2, 3]),
            lambda r: r['model_request'].update(images_sent=1),
            lambda r: r['model_result'].update(object_id='another-chair'),
            lambda r: r['model_result'].update(translation_m=[.2, 0, 0]),
            lambda r: r['model_job'].update(source_revision='0' * 64),
            lambda r: r['model_job'].update(_owner='synthetic-do-not-save'),
            lambda r: r['ai_edit']['responses'][-1]['body'].update(current_frame=False)]
        for index, mutate in enumerate(mutations):
            def change(records):
                records['ai_edit']['provider_calls'] = 1
                mutate(records)
            with self.subTest(index=index):
                self.assertEqual(self.evaluate(change)['status'], 'NOT_READY')

    def test_expected_stop_rejection_requires_response_gate_and_zero_original_errors(self):
        def allowed(records):
            records['sim']['status'] = 'PASS_WITH_EXPECTED_STOP_REJECTION'
        self.assertEqual(self.evaluate(allowed)['status'], gate.READY)
        for field, value in (('response_gate', {'status':'FAIL'}), ('errors', ['original failure']),
                             ('failed_requests', [{'error':'aborted'}]), ('video_error', 'recording failed')):
            def rejected(records):
                allowed(records)
                records['sim'][field] = value
            with self.subTest(field=field):
                self.assertEqual(self.evaluate(rejected)['status'], 'NOT_READY')

    def test_sha_tampering_absolute_paths_and_traversal_are_rejected_without_repair(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self.materialize(root)
            original = (root / 'sim.json').read_bytes()
            (root / 'sim.json').write_bytes(original + b' ')
            result = gate.verify(manifest, root)
            self.assertIn('EVIDENCE_HASH_MISMATCH:sim', result['issues'])
            self.assertEqual((root / 'sim.json').read_bytes(), original + b' ')
            for path in ('../sim.json', str(root / 'sim.json'), 'C:/outside.json', 'nested/../../sim.json'):
                changed = deepcopy(manifest)
                changed['refs']['sim']['path'] = path
                self.assertEqual(gate.verify(changed, root)['status'], 'NOT_READY')

    def test_cli_is_read_only_and_does_not_overwrite_an_old_gate(self):
        script = Path(gate.__file__).resolve()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self.materialize(root)
            path = root / 'manifest.json'
            path.write_text(json.dumps(manifest), encoding='utf-8')
            before = {p.name:sha256(p.read_bytes()).hexdigest() for p in root.iterdir()}
            output = root / 'gate.json'
            completed = subprocess.run([sys.executable, '-I', str(script), '--manifest', str(path), '--output', str(output)],
                                       capture_output=True, text=True, timeout=10)
            self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
            self.assertEqual(json.loads(output.read_text())['status'], gate.READY)
            self.assertEqual({p.name:sha256(p.read_bytes()).hexdigest() for p in root.iterdir() if p != output}, before)
            saved = output.read_bytes()
            repeated = subprocess.run([sys.executable, '-I', str(script), '--manifest', str(path), '--output', str(output)],
                                     capture_output=True, text=True, timeout=10)
            self.assertNotEqual(repeated.returncode, 0)
            self.assertEqual(output.read_bytes(), saved)


if __name__ == '__main__':
    unittest.main()
