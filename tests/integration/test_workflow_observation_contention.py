# SPDX-License-Identifier: Apache-2.0
"""No-device UI observation/refresh contracts, never real credentials/models."""
from threading import Event,Thread
from unittest.mock import patch
import unittest
import tests.integration.test_r5_product_api as fixtures
from twinpulse_app.command_broker import BrokerError

class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.R5ProductApiTests();self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown);self.workflow=self.fixture.workflow
    def test_hot_snapshot_does_not_call_file_or_credential_getter(self):
        with patch.object(self.workflow,'_provider_state_getter',side_effect=AssertionError('hot credential read')):
            value=self.workflow.snapshot()
        self.assertTrue(value['provider']['configured'])
        self.assertEqual(value['provider']['state_basis'],'startup_or_explicit_settings_refresh_not_authentication')
    def test_blocked_refresh_does_not_block_snapshot_or_admit_new_generation(self):
        entered=Event();release=Event();done=Event();errors=[];old=self.workflow._gateway_factory
        def factory():entered.set();release.wait(3);return old()
        self.workflow._gateway_factory=factory
        def refresh():
            try:self.workflow.provider_settings_changed()
            except Exception as error:errors.append(error)
        worker=Thread(target=refresh);worker.start();self.assertTrue(entered.wait(1))
        reader=Thread(target=lambda:(self.workflow.snapshot(),done.set()));reader.start()
        try:
            self.assertTrue(done.wait(.3),'provider I/O held the workflow snapshot lock')
            self.assertEqual(self.workflow.snapshot()['provider']['configuration_state'],'refreshing')
            with self.assertRaises(BrokerError) as failure:self.workflow.start_generation()
            self.assertEqual(failure.exception.code,'provider_configuration_unconfirmed')
        finally:release.set();worker.join(2);reader.join(2)
        self.assertEqual(errors,[])
        self.assertEqual(self.workflow.snapshot()['provider']['configuration_state'],'observed')
    def test_observation_failure_preserves_gateway_and_original_exception_but_blocks_new_model(self):
        original=self.workflow._application._generation_gateway;error=OSError('controlled observation unavailable')
        with patch.object(self.workflow,'_provider_state_getter',side_effect=error):
            with self.assertRaises(OSError) as failure:self.workflow.provider_settings_changed()
        self.assertIs(failure.exception,error);self.assertIs(self.workflow._application._generation_gateway,original)
        self.assertEqual(self.workflow.snapshot()['provider']['configuration_state'],'unconfirmed')
        with self.assertRaises(BrokerError) as blocked:self.workflow.start_generation()
        self.assertEqual(blocked.exception.code,'provider_configuration_unconfirmed')
        self.workflow.provider_settings_changed()
        self.assertEqual(self.workflow.snapshot()['provider']['configuration_state'],'observed')
    def test_late_refresh_cannot_overwrite_a_newer_applied_gateway(self):
        entered=Event();release=Event();errors=[];old=self.workflow._gateway_factory;count=[0];made=[]
        def factory():
            count[0]+=1;index=count[0]
            if index==1:entered.set();release.wait(3)
            result=old();made.append((index,result));return result
        self.workflow._gateway_factory=factory
        def first():
            try:self.workflow.provider_settings_changed()
            except Exception as error:errors.append(error)
        worker=Thread(target=first);worker.start();self.assertTrue(entered.wait(1))
        try:self.workflow.provider_settings_changed()
        finally:release.set();worker.join(2)
        self.assertEqual(len(errors),1);self.assertEqual(errors[0].code,'provider_refresh_superseded')
        self.assertIs(self.workflow._application._generation_gateway,next(g for i,g in made if i==2))
        self.assertEqual(self.workflow.snapshot()['provider']['configuration_state'],'observed')
    def test_legacy_saved_settings_callback_failure_is_explicit_not_old_gateway_success(self):
        old=self.workflow._application._generation_gateway
        with patch.object(self.workflow,'_provider_state_getter',side_effect=OSError('controlled observation unavailable')):
            status,_,_=self.fixture.request('/v1/product/provider-settings',
                {'base_url':'https://api.openai.com/v1/','model_id':'new-test-model','reasoning_effort':'medium','api_key':'fake-local-test-only'},
                headers=self.fixture.product_headers)
        self.assertEqual(status,500);self.assertEqual(self.fixture.settings_store.load().model_id,'new-test-model')
        self.assertIs(self.workflow._application._generation_gateway,old)
        status,value,_=self.fixture.request('/v1/product/workflow',headers={'Cookie':self.fixture.cookie})
        self.assertEqual(status,200);self.assertFalse(value['provider']['configured'])
        self.assertEqual(value['provider']['configuration_state'],'unconfirmed')
        status,value,_=self.fixture.request('/v1/product/generation',{},headers=self.fixture.product_headers)
        self.assertEqual(status,409);self.assertEqual(value['error']['code'],'provider_configuration_unconfirmed')

    def test_startup_observation_failure_is_unknown_not_a_backend_startup_exception(self):
        from twinpulse_app.product_workflow_service import ProductWorkflow
        error=OSError('controlled startup observation unavailable')
        with patch.object(self.workflow,'_provider_state_getter',side_effect=error) as getter:
            other=ProductWorkflow(self.workflow._application,self.fixture.broker,
                generation_settings_getter=self.workflow._generation_settings_getter,
                provider_state_getter=getter,gateway_factory=self.workflow._gateway_factory)
        value=other.snapshot()['provider'];self.assertFalse(value['configured']);self.assertFalse(value['connected'])
        self.assertEqual(value['configuration_state'],'unconfirmed');self.assertEqual(value['observation_error_type'],'OSError')
        other._provider_state_getter=lambda:{'configured':True,'label':'Recovered saved configuration'}
        self.assertEqual(other.provider_settings_changed()['provider']['configuration_state'],'observed')

    def test_candidate_gateway_cancel_failure_preserves_exact_application_and_workflow_state(self):
        from unittest.mock import Mock
        app=self.workflow._application;old=app._generation_gateway;candidate=Mock();error=OSError('controlled candidate cancel failure')
        candidate.cancel_active.side_effect=error
        # Non-null identity sentinels are unit-only; they never enter a saved
        # project, rendered scene, model or device. The failed helper must not
        # inspect or clear them before candidate cancellation succeeds.
        prior_prepared=app._prepared;prior_derived=app._derived_selection
        app._prepared=object();app._derived_selection=object()
        self.workflow._acknowledged_identity=('unit-input','unit-approval')
        state={key:getattr(app,key) for key in ('_generation_gateway','_derived_selection','_prepared','_epoch','_phase','_last_event')}
        acknowledged=self.workflow._acknowledged_identity
        self.workflow._gateway_factory=lambda:candidate
        with self.assertRaises(OSError) as failure:self.workflow.provider_settings_changed()
        self.assertIs(failure.exception,error);self.assertIs(app._generation_gateway,old)
        for key,value in state.items():self.assertIs(getattr(app,key),value)
        self.assertIs(self.workflow._acknowledged_identity,acknowledged)
        app._prepared=prior_prepared;app._derived_selection=prior_derived
        self.workflow._acknowledged_identity=None
        self.assertEqual(self.workflow.snapshot()['provider']['configuration_state'],'unconfirmed')

    def test_sim_conversation_does_not_take_whole_workflow_snapshot_for_real_room_build(self):
        from twinpulse_app.conversation_service import ConversationService
        conversation=ConversationService(self.workflow,self.fixture.static/'isolation-conversation.json')
        with patch.object(self.workflow,'snapshot',side_effect=AssertionError('unneeded SIM workflow snapshot')):
            self.assertIsNone(conversation.snapshot()['room_build'])

if __name__=='__main__':unittest.main()
