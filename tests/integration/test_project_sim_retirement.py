# SPDX-License-Identifier: Apache-2.0
"""Supplementary switch drain/ACK/late-writer fences; no engine or robot I/O."""
import json
from pathlib import Path
import tempfile
from threading import Event, Thread
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from tests.integration import test_robot_fleet as fixtures
from twinpulse_app.command_broker import BrokerError
from twinpulse_app.persistent_workspace import PersistentWorkspace
from twinpulse_core import SimulationSnapshot


class ProjectSIMRetirementTests(unittest.TestCase):
    def setup_workspace(self,fleet):
        old=SimpleNamespace(context_id='old',broker=SimpleNamespace(project_id='old-project'),robot_fleet=fleet)
        target=SimpleNamespace(context_id='new',broker=Mock(),manual_controller=Mock())
        workspace=PersistentWorkspace(old,Mock())
        ticket=dict(switch_id='switch',target_context_id='new',project_id='new-project',new_stage_epoch='new-stage')
        event=Event();workspace.pending=dict(ticket=ticket,api=target,event=event,error=None)
        snapshot=SimulationSnapshot('engine','new-stage','new-project',None,None,1,'idle',None,None,(),())
        return workspace,old,target,dict(switch_id='switch',ticket=ticket,snapshot=snapshot.to_dict())

    def test_ack_is_fast_and_duplicate_identical_while_drain_is_blocked(self):
        entered=Event();release=Event()
        def close(**kw):entered.set();release.wait(3);return dict(complete=True)
        fleet=SimpleNamespace(close=Mock(side_effect=close),snapshot_writer=SimpleNamespace(thread=SimpleNamespace(is_alive=lambda:False)),recorders={})
        workspace,old,target,body=self.setup_workspace(fleet)
        start=time.monotonic();result=workspace.acknowledge(old,SimpleNamespace(engine_session_id='engine'),body)
        self.assertLess(time.monotonic()-start,.5);self.assertTrue(entered.wait(1))
        self.assertEqual(result['status'],'switched')
        self.assertEqual(workspace.acknowledge(old,SimpleNamespace(engine_session_id='engine'),body),result)
        fleet.close.assert_called_once_with(reason='PROJECT_SWITCH')
        self.assertIs(workspace.active,target)
        # A real reopen cannot instantiate a writer while the retired one lives.
        with patch('twinpulse_app.persistent_workspace.time.monotonic',side_effect=[0,4,4]):
            with self.assertRaisesRegex(BrokerError,'still draining'):workspace._wait_sim_retirement('old-project')
        release.set();self.assertTrue(workspace.sim_retirements[0]['done'].wait(1))
        workspace._wait_sim_retirement('old-project')

    def test_done_close_timeout_still_blocks_live_writer(self):
        fleet=SimpleNamespace(snapshot_writer=SimpleNamespace(thread=SimpleNamespace(is_alive=lambda:True)),recorders={})
        workspace=PersistentWorkspace(SimpleNamespace(context_id='a'),Mock());done=Event();done.set()
        workspace.sim_retirements=[dict(project_id='same',fleet=fleet,done=done)]
        with patch('twinpulse_app.persistent_workspace.time.monotonic',side_effect=[0,4,4]):
            with self.assertRaises(BrokerError):workspace._wait_sim_retirement('same')

    def test_actual_sim_journal_finalized_as_switch_without_physical_close(self):
        f=fixtures.FleetTests();f.setUp();self.addCleanup(f.tearDown)
        robot=f.connected();operation=f.fleet.robots[robot]['operation_id'];before=f.fleet.operation(operation)['events']
        physical=SimpleNamespace(close=Mock());f.fleet.physical=physical
        receipt=f.fleet.close(reason='PROJECT_SWITCH');self.assertTrue(receipt['complete'])
        self.assertEqual(f.fleet.close(),receipt);physical.close.assert_not_called()
        record=json.loads((Path(f.temp.name)/'robot-operations'/(operation+'.json')).read_text())
        self.assertTrue(record['manifest']['complete']);self.assertEqual(record['manifest']['end_reason'],'PROJECT_SWITCH')
        self.assertEqual(record['events'][:len(before)],before)
        self.assertEqual(record['events'][-1]['kind'],'project_switched')

    def test_shutdown_does_not_start_new_target_watchdog(self):
        fleet=SimpleNamespace(close=Mock(return_value=dict(complete=True)))
        workspace,old,target,body=self.setup_workspace(fleet);workspace.closing=True
        workspace.acknowledge(old,SimpleNamespace(engine_session_id='engine'),body)
        target.manual_controller.start_watchdog.assert_not_called()

    def test_close_admission_exception_never_leaves_permanent_waiter(self):
        f=fixtures.FleetTests();f.setUp();self.addCleanup(f.tearDown);f.connected()
        with patch.object(f.fleet,'_event',side_effect=ValueError('Synthetic admission fault')):
            receipt=f.fleet.close(reason='PROJECT_SWITCH')
        self.assertFalse(receipt['complete']);self.assertTrue(f.fleet.close_done.is_set())
        self.assertEqual(f.fleet.close(),receipt)
        for recorder in f.fleet.recorders.values():recorder.close()
        f.fleet.snapshot_writer.close()

    def test_shutdown_begun_during_retirement_start_does_not_start_watchdog(self):
        fleet=SimpleNamespace(close=Mock(return_value=dict(complete=True)))
        workspace,old,target,body=self.setup_workspace(fleet)
        with patch('twinpulse_app.persistent_workspace.Thread.start',side_effect=lambda:setattr(workspace,'closing',True)):
            workspace.acknowledge(old,SimpleNamespace(engine_session_id='engine'),body)
        target.manual_controller.start_watchdog.assert_not_called()


if __name__=='__main__':unittest.main()
