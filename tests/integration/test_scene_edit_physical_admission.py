# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Shared admission barriers only. No board, sensor, transport or motor runs."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
from types import SimpleNamespace
import hashlib
import unittest
from unittest.mock import patch

import tests.integration.test_scene_edit_transaction as fixture
from twinpulse_app.api import LocalApiServer
from twinpulse_app.command_broker import BrokerError
from twinpulse_app.robot_readiness import RobotReadiness
from tests.integration.test_robot_readiness_app import precollection_fixture


class PhysicalState:
    real_transport=False
    def __init__(self):self.state={'busy':False,'state':'NOT_STARTED'};self.calls=[]
    def snapshot(self,owner):return deepcopy(self.state)
    def close(self):pass


class SceneEditPhysicalAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.product=fixture.workflow(Path(self.temp.name))
        fixture.attach(self.product);self.physical=PhysicalState()
        self.server=LocalApiServer(self.product._broker,product_bootstrap_secret='p'*32,engine_bootstrap_secret='e'*32,
            product_workflow=self.product,physical_controller=self.physical,session_history_root=Path(self.temp.name))
        self.transaction=self.product.scene_edit_transaction;self.value=fixture.restoration(self.product)

    def tearDown(self):
        if self.transaction.worker:self.transaction.worker.join(3)
        self.product._application.diagnostics.flush()
        self.server.stop();self.server._httpd.server_close()
        self.temp.cleanup()

    def apply(self):return self.transaction.start('owner',self.value['operation'],self.value['preview_digest'])

    def test_saved_sim_edit_uses_verified_precollection_receipt_without_clearing_real_uncertainty(self):
        paths=precollection_fixture(Path(self.temp.name));before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        readiness=RobotReadiness(self.temp.name,runner=lambda:self.fail('No physical collection allowed'))
        self.server.robot_readiness=readiness
        conversation=self.server.conversation
        # Explicit saved selection is required, not a requested/unsaved SIM mode.
        for mode,persisted in ((None,False),('REAL',True),('SIM',False)):
            conversation._state['mode']=mode
            if persisted:conversation._persist()
            with self.assertRaises(BrokerError):self.apply()
            self.assertIsNone(self.transaction.value);self.assertIsNone(self.product._broker.claim('engine','stage'))
        conversation._persist()
        with patch.object(self.product,'_phase','restore_review_required'):
            with self.assertRaises(BrokerError):self.apply()
        self.assertIsNone(self.transaction.value)
        self.apply();command=fixture.claim(self.product._broker);fixture.acknowledge(self.product._broker,command)
        self.transaction.worker.join(3);self.assertEqual(self.transaction.snapshot('owner')['state'],'COMMITTED')
        self.assertTrue(readiness.blocks_robot_operation());self.assertEqual(readiness.snapshot(None)['status'],'REMOTE_STATE_UNKNOWN')
        self.assertEqual(before,{p:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
        self.assertEqual(self.physical.calls,[])

    def test_sim_scope_is_durable_on_reopen_and_revoked_on_failed_or_real_transition(self):
        from twinpulse_app.conversation_service import ConversationService
        conversation=self.server.conversation
        self.assertFalse(conversation.saved_sim_scene_edit_scope('default'))
        conversation._state['mode']='SIM';self.assertFalse(conversation.saved_sim_scene_edit_scope('default'))
        conversation._persist();self.assertTrue(conversation.saved_sim_scene_edit_scope('default'))
        reopened=ConversationService(self.product,conversation.path)
        self.assertTrue(reopened.saved_sim_scene_edit_scope('default'))
        self.assertFalse(reopened.saved_sim_scene_edit_scope('other-project'))
        reopened._state['mode']='REAL';self.assertFalse(reopened.saved_sim_scene_edit_scope('default'))
        reopened._state['mode']='SIM';reopened._restore_error={'code':'conversation_save_failed'}
        self.assertFalse(reopened.saved_sim_scene_edit_scope('default'))

    def test_linked_real_preview_cannot_open_localization_while_readiness_running_or_unknown(self):
        readiness=RobotReadiness(self.temp.name,runner=lambda:self.fail('No physical collection allowed'))
        self.server.robot_readiness=readiness;self.server.chat_robot_preparation.readiness=readiness
        navigation=self.server.conversation.navigation;factory=self.server.automatic_mission.adapter_factory
        self.assertFalse(self.transaction.locked())
        with patch.object(self.server.chat_robot_preparation,'snapshot',return_value={'owned':True,'state':'LINKED'}),\
                patch.object(self.server.automatic_mission,'preview_goal') as preview_goal,\
                patch.object(factory,'preview_current') as native_query,\
                patch.object(self.physical,'start',create=True) as physical_start:
            for status in ('RUNNING','REMOTE_STATE_UNKNOWN','LOCAL_RECORD_UNREADABLE'):
                readiness._state['status']=status
                with self.assertRaises(BrokerError) as rejected:navigation.prepare('owner','Go near the support.')
                self.assertEqual(rejected.exception.code,'readiness_busy_or_uncertain')
            preview_goal.assert_not_called();native_query.assert_not_called();physical_start.assert_not_called()
        self.assertIsNone(self.transaction.value);self.assertEqual(self.physical.calls,[])

    def test_verified_sim_document_does_not_exempt_live_worker_transfer_or_cleanup(self):
        precollection_fixture(Path(self.temp.name))
        readiness=RobotReadiness(self.temp.name,runner=lambda:self.fail('No physical collection allowed'))
        self.server.robot_readiness=readiness
        self.server.conversation._state['mode']='SIM';self.server.conversation._persist()
        for state in ({'busy':True,'state':'READY'},
                {'busy':False,'state':'FINISHED','cleanup_confirmed':False},
                {'busy':False,'state':'UNKNOWN'}, {'busy':False,'state':'STOPPING'}):
            self.physical.state=state
            with self.assertRaises(BrokerError):self.apply()
            self.assertIsNone(self.transaction.value)
        self.physical.state={'busy':False,'state':'NOT_STARTED'}
        self.physical.evidence_recovery=SimpleNamespace(thread=SimpleNamespace(is_alive=lambda:True))
        with self.assertRaises(BrokerError):self.apply()
        self.physical.evidence_recovery=None
        readiness._resume_thread=SimpleNamespace(is_alive=lambda:True)
        with self.assertRaises(BrokerError):self.apply()
        readiness._resume_thread=None
        self.server.automatic_mission.worker=SimpleNamespace(is_alive=lambda:True,join=lambda **kw:None)
        with self.assertRaises(BrokerError):self.apply()
        self.server.automatic_mission.worker=None
        self.assertIsNone(self.transaction.value);self.assertIsNone(self.product._broker.claim('engine','stage'))
        self.assertEqual(self.physical.calls,[])

    def test_global_busy_and_uncertain_sources_reject_before_journal_or_build(self):
        for state in ({'busy':True,'state':'READY','owned':False},
                {'busy':False,'state':'CONNECTION_LOST','cleanup_confirmed':False},
                {'busy':False,'state':'FINISHED','cleanup_confirmed':False}):
            self.physical.state=state
            with self.assertRaises(BrokerError):self.apply()
            self.assertIsNone(self.transaction.value)
            self.assertIsNone(self.product._broker.claim('engine','stage'))
        self.physical.state={'busy':False,'state':'NOT_STARTED'}
        self.server.robot_readiness=SimpleNamespace(blocks_robot_operation=lambda:True)
        with self.assertRaises(BrokerError):self.apply()
        self.server.robot_readiness=None
        self.server.automatic_mission.worker=SimpleNamespace(is_alive=lambda:True,join=lambda **kw:None)
        with self.assertRaises(BrokerError):self.apply()
        self.server.automatic_mission.worker=None
        self.assertEqual(self.physical.calls,[])

    def test_same_start_mutex_closes_both_race_orders_and_unknown_recovery(self):
        entered=Event();finished=Event();failures=[]
        original=self.transaction.admission
        def admission(owner):entered.set();return original(owner)
        self.transaction.admission=admission
        def applying():
            try:self.apply()
            except BrokerError as error:failures.append(error.code)
            finally:finished.set()
        with self.server._robot_start_lock:
            worker=Thread(target=applying);worker.start();self.assertTrue(entered.wait(2))
            # The already admitted physical owner wins. Apply cannot stage its
            # intent until this common mutex is released and busy rechecked.
            self.server._scene_edit_physical_guard()
            self.physical.state={'busy':True,'state':'READY','owned':False}
        self.assertTrue(finished.wait(2));worker.join(2)
        self.assertEqual(failures,['scene_edit_robot_busy']);self.assertIsNone(self.transaction.value)
        self.physical.state={'busy':False,'state':'FINISHED','cleanup_confirmed':True}
        self.transaction.timeout_s=.08;self.apply()
        with self.server._robot_start_lock:
            with self.assertRaises(BrokerError):self.server._scene_edit_physical_guard()
            with self.assertRaises(BrokerError):self.server.chat_robot_preparation._independent_busy()
        navigation=self.server.conversation.navigation
        factory=self.server.automatic_mission.adapter_factory
        with patch.object(self.server.automatic_mission,'preview_goal') as preview_goal,patch.object(factory,'preview_current') as native_query:
            with self.assertRaises(BrokerError):navigation.prepare('owner','Go near the support.')
            preview_goal.assert_not_called();native_query.assert_not_called()
        command=fixture.claim(self.product._broker);fixture.acknowledge(self.product._broker,command,receipt=False)
        self.transaction.worker.join(3);self.assertEqual(self.transaction.value['state'],'ENGINE_STATE_UNKNOWN')
        with self.assertRaises(BrokerError):self.product.apply_scene_edit(self.value['operation'],self.value['preview_digest'])
        self.assertEqual(self.product._application.scene_change_store().load().operations,())
        with patch.object(factory,'preview_current') as native_query:
            with self.assertRaises(BrokerError):navigation.prepare('owner','Localize for a fresh goal.')
            native_query.assert_not_called()
        self.physical.state={'busy':True,'state':'READY','owned':False}
        with self.assertRaises(BrokerError):self.transaction.recover('owner')
        for _ in range(3):self.transaction.snapshot('owner')
        self.assertIsNone(self.product._broker.claim('engine','stage'))
        self.assertEqual(self.physical.calls,[])

    def test_legacy_save_only_busy_unknown_idle_and_duplicate_contracts(self):
        apply_legacy=lambda:self.product.apply_scene_edit(self.value['operation'],self.value['preview_digest'])
        self.physical.state={'busy':True,'state':'READY','owned':False}
        with self.assertRaises(BrokerError):apply_legacy()
        self.assertEqual(self.product._application.scene_change_store().load().operations,())
        self.assertIsNone(self.product._broker.claim('engine','stage'))
        self.physical.state={'busy':False,'state':'CONNECTION_LOST','cleanup_confirmed':False}
        with self.assertRaises(BrokerError):apply_legacy()
        self.physical.state={'busy':False,'state':'NOT_STARTED'}
        # The original engine/view-only split is unchanged: one durable legacy
        # edit and repeat return, zero Build, no transactional commit invented.
        first=apply_legacy();again=apply_legacy()
        self.assertEqual(first['site_draft']['revision'],again['site_draft']['revision'])
        self.assertEqual(len(self.product._application.scene_change_store().load().operations),1)
        self.assertIsNone(self.transaction.value);self.assertIsNone(self.product._broker.claim('engine','stage'))
        store=self.product._application.scene_change_store()
        undo=store.load().preview(store.source,operation_id='legacy-unknown',mode='undo')
        with patch.object(self.transaction,'locked',return_value=True):
            with self.assertRaises(BrokerError):self.product.apply_scene_edit(undo['operation'],undo['preview_digest'])
        self.assertEqual(len(store.load().operations),1)
        self.assertIsNone(self.product._broker.claim('engine','stage'));self.assertEqual(self.physical.calls,[])


if __name__=='__main__':unittest.main()
