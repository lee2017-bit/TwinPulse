# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Actual broker receipts with deterministic engine and disk fault injection."""
from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch

from tests.integration.test_dependency_scene_changes import partial_source,edit,item,relation,preview
from tests.integration.test_a2_room_recipe import NoGateway
from twinpulse_app import ApplicationService,CommandBroker,ProductWorkflow,ProjectStore
from twinpulse_app.project_store import ProjectRecord
from twinpulse_app.scene_changes import SceneChangeStore
from twinpulse_core import SimulationSnapshot,CommandReceipt,InputArtifactStore
from twinpulse_core import canonical_sha256


def workflow(root,broker=None):
    store=ProjectStore.for_project(root,'default')
    if not store.path.exists():
        source=partial_source()
        InputArtifactStore(store.input_root()).save(source.input_revision,())
        store.save(ProjectRecord('default',source.input_revision,site_draft=source))
    app=ApplicationService(NoGateway(),project_store=store,project_id='default')
    broker=broker or CommandBroker()
    product=ProductWorkflow(app,broker,mode='simulation_offline',generation_settings_getter=lambda:{'request_schema':'offline-1.0'})
    source=app.site_draft
    product.resume_saved_scene('default',source.site.scene.revision,source.input_revision.digest)
    return product


def attach(product,revision=None):
    broker=product._broker;broker.register_engine('engine','stage');broker.acquire_lease('owner')
    broker.record_snapshot(SimulationSnapshot(engine_session_id='engine',stage_epoch='stage',project_id='default',
        applied_revision=revision or product._site_artifact.revision,run_id=None,sequence=1,runtime_state='built',
        safety_state=None,safety_reason=None,permitted_commands=('build_site_scene','get_state'),
        capabilities=('simulation','site_scene_build_v2')))


def claim(broker):
    deadline=time.monotonic()+3
    while time.monotonic()<deadline:
        state=broker.public_state('owner')
        command=broker.claim(state['engine_session_id'],state['stage_epoch'])
        if command:return command
        time.sleep(.01)
    raise AssertionError('No owned Build was dispatched')


def acknowledge(broker,command,*,receipt=True):
    old=broker.public_state('owner')['snapshot']
    broker.record_snapshot(SimulationSnapshot.from_dict({**old,'sequence':old['sequence']+1,
        'applied_revision':command.expected_applied_revision,'runtime_state':'built'}))
    if receipt:
        broker.record_receipt(CommandReceipt(command_id=command.command_id,command_type=command.command_type,
            project_id=command.project_id,engine_session_id=command.engine_session_id,stage_epoch=command.stage_epoch,
            status='succeeded',applied_revision=command.expected_applied_revision))


def restoration(product):
    store=product._application.scene_change_store();source=store.source
    return preview(store.load(),source,'restore',edit('restore','item_0',
        tool_call=item('item_0',[0,0,.91],(.5,.3,.02)),placement=relation('item_0','support')))


class SceneEditTransactionTests(unittest.TestCase):
    def test_cold_explicit_recovery_restores_read_review_without_implicit_build_or_input_replacement(self):
        with TemporaryDirectory() as folder:
            product=self.make_workflow(Path(folder));attach(product)
            transaction=product.scene_edit_transaction;transaction.timeout_s=.05
            value=restoration(product);transaction.start('owner',value['operation'],value['preview_digest'])
            command=claim(product._broker);acknowledge(product._broker,command,receipt=False)
            transaction.worker.join(3);self.assertEqual(transaction.value['state'],'ENGINE_STATE_UNKNOWN')
            # A new real workflow is intentionally NOT resumed by this helper.
            app=ApplicationService(NoGateway(),project_store=ProjectStore.for_project(Path(folder),'default'),project_id='default')
            cold=ProductWorkflow(app,product._broker,mode='simulation_offline',generation_settings_getter=lambda:{'request_schema':'offline-1.0'})
            self.products.append(cold)
            self.assertIsNone(cold._input);self.assertEqual(cold._phase,'restore_review_required')
            self.assertTrue(cold.scene_edit_transaction.locked());self.assertIsNone(product._broker.claim('engine','stage'))
            product._broker.register_engine('engine','recovery-stage')
            product._broker.acquire_lease('owner')
            product._broker.record_snapshot(SimulationSnapshot(engine_session_id='engine',stage_epoch='recovery-stage',
                project_id='default',applied_revision=command.expected_applied_revision,run_id=None,
                sequence=1,runtime_state='built',safety_state=None,safety_reason=None,
                permitted_commands=('build_site_scene','get_state'),capabilities=('simulation','site_scene_build_v2')))
            cold.scene_edit_transaction.recover('owner')
            cold.scene_edit_transaction.worker.join(.05)
            self.assertTrue(cold.scene_edit_transaction.worker.is_alive(),cold.scene_edit_transaction.value.get('error'))
            recovery=claim(product._broker);acknowledge(product._broker,recovery)
            cold.scene_edit_transaction.worker.join(3)
            self.assertEqual(cold.scene_edit_transaction.value['state'],'ROLLED_BACK')
            self.assertEqual(cold._phase,'draft_ready')
            self.assertEqual(cold._input.revision,app.site_draft.input_revision.digest)
            self.assertEqual(cold._scene_changes.current_scene_revision,recovery.expected_applied_revision)
            self.assertIsNone(product._broker.claim('engine','recovery-stage'));self.flush_products()

    def test_unknown_without_either_ack_does_not_replay_history_or_dispatch(self):
        with TemporaryDirectory() as folder:
            product=self.make_workflow(Path(folder));attach(product)
            transaction=product.scene_edit_transaction
            transaction.value=dict(state='ENGINE_STATE_UNKNOWN',receipt=None,compensation_receipt=None)
            with patch('twinpulse_app.scene_edit_transaction.SceneChangeHistory.from_dict',
                    side_effect=AssertionError('No ACK to reconcile')):
                transaction.reconcile('owner')
            self.assertEqual(transaction.value['state'],'ENGINE_STATE_UNKNOWN')
            self.assertIsNone(product._broker.claim('engine','stage'))
            self.flush_products()

    def test_new_apply_admission_precedes_staging_dispatch_and_store_write(self):
        with TemporaryDirectory() as folder:
            product=self.make_workflow(Path(folder));attach(product)
            value=restoration(product);transaction=product.scene_edit_transaction
            store=product._application.scene_change_store()
            with patch('twinpulse_app.scene_changes.admit_new_scene_change',
                    side_effect=ValueError('PHOTO_PLACEMENT_ANCESTOR_PENETRATION')) as admission:
                with self.assertRaisesRegex(ValueError,'ANCESTOR_PENETRATION'):
                    transaction.start('owner',value['operation'],value['preview_digest'])
                self.assertIsNone(transaction.value)
                self.assertFalse(product._broker.has_pending_operations())
                with self.assertRaisesRegex(ValueError,'ANCESTOR_PENETRATION'):
                    store.apply(value['operation'],value['preview_digest'])
                self.assertEqual(admission.call_count,2)
                self.assertFalse(store.path.exists())
            self.flush_products()

    def make_workflow(self,root,broker=None):
        product=workflow(root,broker)
        self.products.append(product)
        return product

    def setUp(self):
        self.products=[]

    def flush_products(self):
        for product in self.products:
            worker=product.scene_edit_transaction.worker
            if worker:worker.join(3)
            self.assertTrue(product._application.diagnostics.flush())

    def test_local_preparation_outlives_lease_then_refreshes_same_idle_engine_before_dispatch(self):
        now=[0.]
        with TemporaryDirectory() as folder:
            broker=CommandBroker(clock=lambda:now[0]);product=self.make_workflow(Path(folder),broker)
            attach(product);value=restoration(product);transaction=product.scene_edit_transaction
            original=product._register_scene_change
            def slow_preparation(*args):
                result=original(*args);now[0]+=4.;broker.engine_heartbeat('engine','stage')
                self.assertFalse(broker.public_state('owner')['lease_owned'])
                return result
            with patch.object(product,'_register_scene_change',side_effect=slow_preparation):
                transaction.start('owner',value['operation'],value['preview_digest'])
                command=claim(broker);acknowledge(broker,command);transaction.worker.join(3)
            self.assertEqual(transaction.value['state'],'COMMITTED');self.assertEqual(broker.lease_ttl_s,3.)
            self.assertIsNone(broker.claim('engine','stage'));self.flush_products()
            detail=product._application.diagnostics.detail(transaction.value['execution_id'])
            self.assertTrue(any(row.get('metadata',{}).get('control_lease_owned_before_refresh') is False
                for row in detail['spans']))

    def test_lease_refresh_diagnostics_are_bounded_typed_fields_not_secrets(self):
        from twinpulse_core.execution_diagnostics import metadata
        self.assertEqual(metadata(dict(control_lease_refresh_phase='before_dispatch',
            control_lease_owned_before_refresh=False,expected_engine_identity_current=True)),
            dict(control_lease_refresh_phase='before_dispatch',control_lease_owned_before_refresh=False,
                expected_engine_identity_current=True))
        for value in ('secret-token',1,None,[]):
            self.assertEqual(metadata(dict(control_lease_owned_before_refresh=value,
                expected_engine_identity_current=value)),{})
        self.assertEqual(metadata(dict(control_lease_refresh_phase='arbitrary-secret',control_lease_id='secret')), {})

    def test_permit_wait_refreshes_after_lease_expiry_without_extending_global_ttl(self):
        from threading import Event
        now=[0.];waiting=Event();release=Event();first=[True]
        with TemporaryDirectory() as folder:
            broker=CommandBroker(clock=lambda:now[0]);product=self.make_workflow(Path(folder),broker)
            attach(product);value=restoration(product);transaction=product.scene_edit_transaction
            old=broker.public_state('owner')['snapshot']
            broker.record_snapshot(SimulationSnapshot.from_dict({**old,'sequence':2,'permitted_commands':[]}))
            original=transaction._refresh_lease
            def observed_refresh(*args,**kwargs):
                result=original(*args,**kwargs)
                if first[0]:
                    first[0]=False;waiting.set();self.assertTrue(release.wait(3))
                return result
            with patch.object(transaction,'_refresh_lease',side_effect=observed_refresh):
                try:
                    transaction.start('owner',value['operation'],value['preview_digest'])
                    self.assertTrue(waiting.wait(3));now[0]=4.;broker.engine_heartbeat('engine','stage')
                    self.assertFalse(broker.public_state('owner')['lease_owned'])
                    broker.record_snapshot(SimulationSnapshot.from_dict({**old,'sequence':3,'permitted_commands':['build_site_scene','get_state']}))
                    release.set();command=claim(broker);acknowledge(broker,command);transaction.worker.join(3)
                finally:release.set();self.flush_products()
            self.assertEqual(transaction.value['state'],'COMMITTED');self.assertEqual(broker.lease_ttl_s,3.)
            self.flush_products()

    def test_preparation_expiry_never_takes_control_from_a_different_owner(self):
        now=[0.]
        with TemporaryDirectory() as folder:
            broker=CommandBroker(clock=lambda:now[0]);product=self.make_workflow(Path(folder),broker)
            attach(product);value=restoration(product);transaction=product.scene_edit_transaction
            before=product._site_artifact.revision;original=product._register_scene_change
            def takeover(*args):
                result=original(*args);now[0]=4.;broker.engine_heartbeat('engine','stage');broker.acquire_lease('other')
                return result
            with patch.object(product,'_register_scene_change',side_effect=takeover):
                transaction.start('owner',value['operation'],value['preview_digest']);transaction.worker.join(3)
            self.assertEqual(transaction.value['state'],'ENGINE_STATE_UNKNOWN')
            self.assertIn('Another product session owns control',transaction.value['error'])
            self.assertIsNone(transaction.value['command_id']);self.assertIsNone(broker.claim('engine','stage'))
            self.assertTrue(broker.public_state('other')['lease_owned'])
            self.assertEqual(product._site_artifact.revision,before);self.flush_products()

    def test_preparation_never_reacquires_an_unexpected_replacement_engine(self):
        now=[0.]
        with TemporaryDirectory() as folder:
            broker=CommandBroker(clock=lambda:now[0]);product=self.make_workflow(Path(folder),broker)
            attach(product);value=restoration(product);transaction=product.scene_edit_transaction
            old=broker.public_state('owner')['snapshot'];original=product._register_scene_change
            def replacement(*args):
                result=original(*args);now[0]=4.;broker.register_engine('other-engine','other-stage');broker.acquire_lease('other')
                broker.record_snapshot(SimulationSnapshot.from_dict({**old,'engine_session_id':'other-engine',
                    'stage_epoch':'other-stage','sequence':1}));return result
            with patch.object(product,'_register_scene_change',side_effect=replacement):
                transaction.start('owner',value['operation'],value['preview_digest']);transaction.worker.join(3)
            self.assertEqual(transaction.value['state'],'ENGINE_STATE_UNKNOWN')
            self.assertIn('SCENE_EDIT_ENGINE_IDENTITY_CHANGED',transaction.value['error'])
            self.assertTrue(broker.public_state('other')['lease_owned'])
            self.assertIsNone(transaction.value['command_id']);self.assertIsNone(broker.claim('other-engine','other-stage'))
            self.flush_products()

    def test_commit_waits_for_bound_ack_then_current_frame_and_duplicate_is_idempotent(self):
        with TemporaryDirectory() as folder:
            product=self.make_workflow(Path(folder));attach(product);value=restoration(product)
            transaction=product.scene_edit_transaction
            transaction.start('owner',value['operation'],value['preview_digest'])
            command=claim(product._broker)
            self.assertEqual(product._application.scene_change_store().load().operations,())
            self.assertTrue(transaction.locked())
            acknowledge(product._broker,command);transaction.worker.join(3)
            self.assertFalse(transaction.worker.is_alive())
            state=transaction.snapshot('owner');self.assertEqual(state['state'],'COMMITTED')
            self.assertEqual(len(state['execution_id']),32)
            self.assertTrue(product._application.diagnostics.flush())
            detail=product._application.diagnostics.detail(state['execution_id'])
            stages={span['stage']:span for span in detail['spans']}
            self.assertEqual(stages['scene_edit_engine_ack']['status'],'succeeded')
            self.assertEqual(stages['scene_edit_validate_and_save']['status'],'succeeded')
            root=next(s for s in detail['spans'] if s['span_id']==detail['manifest']['root_span_id'])
            self.assertEqual(root['metadata']['parent_state_sha256'],value['operation']['parent_state_sha256'])
            self.assertEqual(root['metadata']['command_id'],command.command_id)
            refs=product._broker.artifact_diagnostic_refs(product._site_artifact.artifact_id)
            self.assertEqual(refs['scene_edit_execution_id'],state['execution_id'])
            self.assertFalse(state['current_frame']);self.assertTrue(state['durable_committed'])
            product._broker.record_current_frame('engine','stage',command.expected_applied_revision,'frame','f'*64)
            self.assertTrue(transaction.snapshot('owner')['current_frame'])
            self.assertEqual(transaction.start('owner',value['operation'],value['preview_digest'])['command_id'],command.command_id)
            self.assertIsNone(product._broker.claim('engine','stage'))
            reopened=self.make_workflow(Path(folder),product._broker)
            self.assertEqual(reopened._broker.artifact_diagnostic_refs(reopened._site_artifact.artifact_id)['scene_edit_execution_id'],state['execution_id'])
            self.assertEqual(reopened._site_artifact.revision,command.expected_applied_revision)
            self.assertEqual(reopened.scene_edit_transaction.snapshot('owner')['state'],'COMMITTED')
            store=reopened._application.scene_change_store()
            undo=store.load().preview(store.source,operation_id='undo_archive',mode='undo')
            reopened.scene_edit_transaction.start('owner',undo['operation'],undo['preview_digest'])
            undo_command=claim(product._broker);acknowledge(product._broker,undo_command)
            reopened.scene_edit_transaction.worker.join(3)
            historical=reopened.scene_edit_transaction.start('owner',value['operation'],value['preview_digest'])
            self.assertTrue(historical['historical']);self.assertEqual(historical['command_id'],command.command_id)
            self.assertIsNone(product._broker.claim('engine','stage'))
            self.flush_products()

    def test_disk_failure_requires_compensation_ack_before_rollback(self):
        with TemporaryDirectory() as folder:
            product=self.make_workflow(Path(folder));attach(product);value=restoration(product)
            original=product._site_artifact.revision;transaction=product.scene_edit_transaction
            with patch.object(SceneChangeStore,'apply',side_effect=OSError('Injected durable write failure')):
                transaction.start('owner',value['operation'],value['preview_digest'])
                first=claim(product._broker);acknowledge(product._broker,first)
                compensation=claim(product._broker)
                self.assertEqual(compensation.expected_applied_revision,original)
                self.assertTrue(transaction.locked())
                self.assertNotEqual(transaction.snapshot()['state'],'ROLLED_BACK')
                acknowledge(product._broker,compensation);transaction.worker.join(3)
            self.assertEqual(transaction.snapshot()['state'],'ROLLED_BACK')
            self.assertFalse(transaction.snapshot('owner')['current_frame'])
            product._broker.record_current_frame('engine','stage',compensation.expected_applied_revision,'rollback-frame','c'*64)
            restored=transaction.snapshot('owner')
            self.assertTrue(restored['current_frame']);self.assertTrue(restored['compensation_acknowledged'])
            self.assertEqual(restored['displayed_revision'],original)
            self.assertEqual(product._application.scene_change_store().load().operations,())
            self.flush_products()

    def test_prior_journal_versions_remain_readable_without_inventing_feedback(self):
        with TemporaryDirectory() as folder:
            product=self.make_workflow(Path(folder));attach(product);value=restoration(product)
            transaction=product.scene_edit_transaction
            transaction.start('owner',value['operation'],value['preview_digest'])
            command=claim(product._broker);acknowledge(product._broker,command);transaction.worker.join(3)
            self.assertEqual(transaction.value['schema_version'],'scene-edit-transaction-1.2')
            current=dict(transaction.value)
            for version in ('scene-edit-transaction-1.1','scene-edit-transaction-1.0'):
                legacy={key:item for key,item in current.items() if key not in {'sha256','feedback_lineage'} and
                    (version!='scene-edit-transaction-1.0' or key!='execution_id')}
                legacy['schema_version']=version;legacy['sha256']=canonical_sha256(legacy)
                transaction.path.write_text(json.dumps(legacy),encoding='utf-8')
                reopened=self.make_workflow(Path(folder),product._broker)
                state=reopened.scene_edit_transaction.snapshot('owner')
                self.assertEqual(state['state'],'COMMITTED');self.assertIsNone(state['feedback_lineage'])
                self.assertIsNone(product._broker.claim('engine','stage'))
            self.flush_products()

    def test_ack_loss_restart_is_unknown_poll_dispatches_nothing_explicit_recovery_acks(self):
        with TemporaryDirectory() as folder:
            product=self.make_workflow(Path(folder));attach(product);value=restoration(product)
            transaction=product.scene_edit_transaction;transaction.timeout_s=.1
            transaction.start('owner',value['operation'],value['preview_digest'])
            command=claim(product._broker);acknowledge(product._broker,command,receipt=False)
            transaction.worker.join(3)
            self.assertEqual(transaction.snapshot()['state'],'ENGINE_STATE_UNKNOWN')
            reopened=self.make_workflow(Path(folder),product._broker)
            self.assertEqual(reopened.scene_edit_transaction.snapshot('owner')['state'],'ENGINE_STATE_UNKNOWN')
            self.assertIsNone(product._broker.claim('engine','stage'))
            with self.assertRaisesRegex(Exception,'transaction'):
                product._broker.submit('owner',dict(client_request_id='unsafe-run',command_type='run',expected_applied_revision=command.expected_applied_revision))
            # A claimed command cannot be cancelled or presumed complete. Only
            # an explicitly reconnected idle engine can accept recovery.
            product._broker.register_engine('engine','recovery-stage')
            product._broker.acquire_lease('owner')
            product._broker.record_snapshot(SimulationSnapshot(engine_session_id='engine',stage_epoch='recovery-stage',
                project_id='default',applied_revision=command.expected_applied_revision,run_id=None,
                sequence=1,runtime_state='built',safety_state=None,safety_reason=None,
                permitted_commands=('build_site_scene','get_state'),capabilities=('simulation','site_scene_build_v2')))
            reopened.scene_edit_transaction.recover('owner')
            compensation=claim(product._broker);acknowledge(product._broker,compensation)
            reopened.scene_edit_transaction.worker.join(3)
            self.assertEqual(reopened.scene_edit_transaction.snapshot()['state'],'ROLLED_BACK')
            self.assertFalse(reopened.scene_edit_transaction.snapshot('owner')['current_frame'])
            product._broker.record_current_frame('engine','recovery-stage',compensation.expected_applied_revision,'recover-frame','d'*64)
            self.assertTrue(reopened.scene_edit_transaction.snapshot('owner')['current_frame'])
            self.flush_products()

    def test_process_interruption_after_durable_ack_reconciles_without_second_build(self):
        with TemporaryDirectory() as folder:
            product=self.make_workflow(Path(folder));attach(product);value=restoration(product)
            transaction=product.scene_edit_transaction
            with patch.object(transaction,'_commit',side_effect=SystemExit('Injected process interruption')):
                transaction.start('owner',value['operation'],value['preview_digest'])
                command=claim(product._broker);acknowledge(product._broker,command);transaction.worker.join(3)
            self.assertEqual(product._application.scene_change_store().load().operations,())
            reopened=self.make_workflow(Path(folder),product._broker)
            self.assertEqual(reopened.scene_edit_transaction.snapshot('owner')['state'],'COMMITTED')
            self.assertEqual(reopened._site_artifact.revision,command.expected_applied_revision)
            self.assertIsNone(product._broker.claim('engine','stage'))
            self.flush_products()

    def test_matching_dead_owner_lock_recovery_never_removes_live_or_legacy_lock(self):
        import json,os
        from twinpulse_core import canonical_sha256
        from twinpulse_app.scene_changes import _process_identity
        with TemporaryDirectory() as folder:
            product=self.make_workflow(Path(folder));value=restoration(product)
            store=product._application.scene_change_store();lock=store.path.with_name(store.path.name+'.lock')
            owner=dict(schema_version='scene-change-lock-1.0',project_id='default',
                source_sha256=canonical_sha256(store.source.to_dict()),operation_id='restore',
                preview_digest=value['preview_digest'],pid=os.getpid(),process_identity=_process_identity(os.getpid()),owner_nonce='b'*32)
            lock.write_text(json.dumps(owner))
            with self.assertRaisesRegex(ValueError,'still alive'):
                store.recover_interrupted_lock(value['operation'],value['preview_digest'])
            self.assertTrue(lock.exists())
            with patch('twinpulse_app.scene_changes._process_identity',return_value=None):
                self.assertTrue(store.recover_interrupted_lock(value['operation'],value['preview_digest']))
            lock.write_text('')
            with self.assertRaisesRegex(ValueError,'legacy'):
                store.recover_interrupted_lock(value['operation'],value['preview_digest'])
            self.assertTrue(lock.exists());self.flush_products()

    def test_poll_reconcile_and_recover_have_one_owner_without_broker_lock_inversion(self):
        from threading import Event,Thread
        with TemporaryDirectory() as folder:
            product=self.make_workflow(Path(folder));attach(product);value=restoration(product)
            transaction=product.scene_edit_transaction
            with patch.object(transaction,'_commit',side_effect=SystemExit('Interrupted before CAS')):
                transaction.start('owner',value['operation'],value['preview_digest'])
                command=claim(product._broker);acknowledge(product._broker,command);transaction.worker.join(3)
            reopened=self.make_workflow(Path(folder),product._broker)
            transaction=reopened.scene_edit_transaction
            entered,release=Event(),Event();original=transaction._commit
            def held_commit(*args):
                entered.set();self.assertTrue(release.wait(3));return original(*args)
            with patch.object(transaction,'_commit',side_effect=held_commit):
                poll=Thread(target=lambda:transaction.snapshot('owner'),daemon=True);poll.start()
                self.assertTrue(entered.wait(3))
                started=time.monotonic()
                with self.assertRaisesRegex(Exception,'owned'):
                    transaction.recover('owner')
                self.assertLess(time.monotonic()-started,.5)
                with self.assertRaisesRegex(Exception,'transaction'):
                    product._broker.submit('owner',dict(client_request_id='race-build',command_type='build_site_scene',
                        artifact_id=reopened._site_artifact.artifact_id,expected_applied_revision=reopened._site_artifact.revision))
                release.set();poll.join(3);self.assertFalse(poll.is_alive())
            self.assertEqual(transaction.snapshot()['state'],'COMMITTED')
            self.assertEqual(reopened._application.scene_change_store().load().current_scene_revision,command.expected_applied_revision)
            self.assertIsNone(product._broker.claim('engine','stage'));self.flush_products()


if __name__=='__main__':unittest.main()
