# SPDX-License-Identifier: Apache-2.0
"""Device-free compact snapshot contracts; no engine, provider or robot execution."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import RLock
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from twinpulse_app.scene_edit_transaction import SceneEditTransaction


def journal(state='COMMITTED'):
    return dict(state=state, operation=dict(operation_id='edit', unused_large_call={'geometry': list(range(1000))}),
        preview_digest='a' * 64, before_history=dict(current_scene_revision='before', operations=[{'large': list(range(1000))}]),
        after_history=dict(current_scene_revision='after', operations=[{'large': list(range(1000))}]),
        command_id='build', compensation_command_id='rollback', engine_session_id='engine', stage_epoch='stage',
        receipt={'original': ['not projected']}, compensation_receipt=None, error=None, execution_id='b' * 32,
        feedback_lineage={'nested': {'source': ['original']}}, sensor_binding={'nested': {'points': [1, 2]}},
        sensor_origin_binding={'nested': {'origin': [3, 4]}})


def build_view(revision='after', command='build'):
    return dict(status='succeeded', applied_revision=revision, command_id=command, engine_session_id='engine', stage_epoch='stage')


def transaction(value=None, current=None):
    owner = object.__new__(SceneEditTransaction)
    owner.lock = RLock()
    owner.ownership = RLock()
    owner.storage_error = None
    owner.value = journal() if value is None else value
    owner.worker = None
    owner.broker = SimpleNamespace(public_state=Mock(return_value={'build_view': current or build_view()}))
    owner.reconcile = Mock()
    return owner


def original_projection(value, current):
    """Pre-optimization wire result, independent of the new capture structure."""
    value = deepcopy(value)
    restored = value['state'] == 'ROLLED_BACK'
    displayed = value['before_history']['current_scene_revision'] if restored else value['after_history']['current_scene_revision']
    command = value['compensation_command_id'] if restored else value['command_id']
    frame = bool(current and current['status'] == 'succeeded' and current.get('applied_revision') == displayed
        and current.get('command_id') == command
        and (current.get('engine_session_id'), current.get('stage_epoch')) == (value['engine_session_id'], value['stage_epoch']))
    return dict(state=value['state'], operation_id=value['operation']['operation_id'], preview_digest=value['preview_digest'],
        parent_revision=value['before_history']['current_scene_revision'], result_revision=value['after_history']['current_scene_revision'],
        command_id=value['command_id'], engine_acknowledged=value['receipt'] is not None,
        durable_committed=value['state'] == 'COMMITTED', current_frame=frame, error=value['error'],
        execution_id=value.get('execution_id'), feedback_lineage=deepcopy(value.get('feedback_lineage')),
        sensor_binding=deepcopy(value.get('sensor_binding')), sensor_origin_binding=deepcopy(value.get('sensor_origin_binding')),
        displayed_revision=displayed, compensation_acknowledged=value['compensation_receipt'] is not None, physical_authority=False)


class SceneEditSnapshotProjectionTests(unittest.TestCase):
    def test_wire_result_and_exact_current_frame_predicate_are_unchanged(self):
        for state in ('STAGED', 'BUILDING', 'ENGINE_ACKNOWLEDGED', 'COMMITTED', 'ROLLED_BACK', 'ENGINE_STATE_UNKNOWN'):
            for current in (None, build_view(), build_view('before', 'rollback'),
                            {**build_view(), 'status': 'running'}, {**build_view(), 'command_id': 'other'},
                            {**build_view(), 'engine_session_id': 'other'}, {**build_view(), 'stage_epoch': 'other'},
                            {**build_view(), 'applied_revision': 'other'}):
                with self.subTest(state=state, current=current):
                    value = journal(state)
                    if state == 'ROLLED_BACK':
                        value['compensation_receipt'] = {}
                    owner = transaction(value)
                    owner.broker.public_state.return_value = {'build_view': current}
                    self.assertEqual(owner.snapshot(), original_projection(value, current))

    def test_large_journal_operation_and_receipts_are_never_walked_or_copied(self):
        class NoCopy:
            def __deepcopy__(self, memo):
                raise AssertionError('large journal subtree copied')
            def __bool__(self):
                raise AssertionError('receipt truth value used instead of presence')
        class LookupOnly(dict):
            def __deepcopy__(self, memo):
                raise AssertionError('large parent mapping copied')
            def __iter__(self):
                raise AssertionError('large parent mapping walked')
        value = journal()
        value['operation'] = LookupOnly(operation_id='edit', tool_call=NoCopy())
        value['before_history'] = LookupOnly(current_scene_revision='before', operations=NoCopy())
        value['after_history'] = LookupOnly(current_scene_revision='after', operations=NoCopy())
        value['receipt'] = NoCopy()
        owner = transaction(value)
        self.assertEqual(owner.snapshot('owner')['operation_id'], 'edit')
        self.assertTrue(owner.snapshot()['engine_acknowledged'])

    def test_every_poll_is_fresh_and_small_nested_results_are_independent(self):
        owner = transaction()
        first = owner.snapshot()
        first['feedback_lineage']['nested']['source'].append('returned mutation')
        first['sensor_binding']['nested']['points'].append(99)
        first['sensor_origin_binding']['nested']['origin'].append(99)
        self.assertEqual(owner.value['feedback_lineage']['nested']['source'], ['original'])
        self.assertEqual(owner.value['sensor_binding']['nested']['points'], [1, 2])
        self.assertEqual(owner.value['sensor_origin_binding']['nested']['origin'], [3, 4])
        owner.value['error'] = 'new error'
        owner.value['receipt'] = None
        owner.value['feedback_lineage']['nested']['source'].append('fresh source')
        second = owner.snapshot()
        self.assertEqual(second['error'], 'new error')
        self.assertFalse(second['engine_acknowledged'])
        self.assertEqual(second['feedback_lineage']['nested']['source'], ['original', 'fresh source'])
        self.assertNotIn('fresh source', first['feedback_lineage']['nested']['source'])

    def test_capture_owns_lock_but_owner_reconcile_and_broker_keep_original_lock_order(self):
        owner = transaction(journal('STAGED'))
        copies = []
        class LockedSmall:
            def __deepcopy__(self, memo):
                self_test.assertTrue(owner.lock._is_owned())
                copies.append(owner.value['state'])
                return {'captured_state': owner.value['state']}
        self_test = self
        owner.value['feedback_lineage'] = LockedSmall()
        def reconcile(session):
            self.assertEqual(session, 'owner')
            self.assertFalse(owner.lock._is_owned())
            with owner.lock:
                owner.value['state'] = 'COMMITTED'
                owner.value['operation']['operation_id'] = 'reconciled-edit'
        def state(session):
            self.assertEqual(session, 'owner')
            self.assertFalse(owner.lock._is_owned())
            return {'build_view': build_view()}
        owner.reconcile.side_effect = reconcile
        owner.broker.public_state.side_effect = state
        snapshot = owner.snapshot('owner')
        self.assertEqual(copies, ['STAGED', 'COMMITTED'])
        self.assertEqual(snapshot['operation_id'], 'reconciled-edit')
        self.assertEqual(snapshot['feedback_lineage'], {'captured_state': 'COMMITTED'})
        self.assertTrue(snapshot['durable_committed'])

    def test_live_worker_and_empty_value_preserve_reconcile_admission(self):
        owner = transaction()
        owner.worker = SimpleNamespace(is_alive=Mock(return_value=True))
        owner.snapshot('owner')
        owner.reconcile.assert_not_called()
        owner.broker.public_state.assert_called_once_with('owner')
        owner.value = None
        owner.broker.public_state.reset_mock()
        self.assertIsNone(owner.snapshot('owner'))
        owner.broker.public_state.assert_not_called()
        owner.reconcile.assert_not_called()

    def test_replacement_during_broker_read_cannot_mix_operation_or_current_frame(self):
        owner = transaction()
        replacement = journal()
        replacement['operation']['operation_id'] = 'new-edit'
        replacement['command_id'] = 'new-build'
        replacement['feedback_lineage']['nested']['source'] = ['new source']
        def observe(session):
            with owner.lock:
                owner.value = replacement
            return {'build_view': build_view(command='new-build')}
        owner.broker.public_state.side_effect = observe
        first = owner.snapshot()
        self.assertEqual(first['operation_id'], 'edit')
        self.assertFalse(first['current_frame'])
        self.assertEqual(first['feedback_lineage']['nested']['source'], ['original'])
        second = owner.snapshot()
        self.assertEqual(second['operation_id'], 'new-edit')
        self.assertTrue(second['current_frame'])
        self.assertEqual(second['feedback_lineage']['nested']['source'], ['new source'])

    def test_reconcile_broker_and_small_copy_exceptions_still_propagate(self):
        for target in ('reconcile', 'broker', 'small_copy'):
            with self.subTest(target=target):
                owner = transaction()
                error = RuntimeError('original ' + target)
                if target == 'reconcile':
                    owner.reconcile.side_effect = error
                elif target == 'broker':
                    owner.broker.public_state.side_effect = error
                else:
                    class BrokenSmall:
                        def __deepcopy__(self, memo):
                            raise error
                    owner.value['sensor_binding'] = BrokenSmall()
                with self.assertRaises(RuntimeError) as caught:
                    owner.snapshot('owner')
                self.assertIs(caught.exception, error)
                self.assertFalse(owner.lock._is_owned())

    def test_storage_error_short_circuit_is_unchanged(self):
        owner = transaction()
        owner.storage_error = 'original_storage_failure'
        self.assertEqual(owner.snapshot('owner'), dict(state='ENGINE_STATE_UNKNOWN',
            error='Scene transaction journal is unavailable.', storage_error='original_storage_failure', physical_authority=False))
        owner.reconcile.assert_not_called()
        owner.broker.public_state.assert_not_called()

    def test_terminal_snapshot_preserves_in_memory_and_saved_original_journal(self):
        owner = transaction()
        del owner.reconcile  # Exercise actual terminal reconciliation, without devices.
        original = deepcopy(owner.value)
        with TemporaryDirectory() as directory:
            owner.path = Path(directory) / 'project.scene-edit-transaction.json'
            raw = json.dumps(original).encode()
            owner.path.write_bytes(raw)
            before = sha256(raw).hexdigest()
            owner._save = Mock(side_effect=AssertionError('snapshot wrote journal'))
            for _ in range(3):
                self.assertTrue(owner.snapshot('owner')['durable_committed'])
            self.assertEqual(owner.value, original)
            self.assertEqual(sha256(owner.path.read_bytes()).hexdigest(), before)
            owner._save.assert_not_called()


if __name__ == '__main__':
    unittest.main()
