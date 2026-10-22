# SPDX-License-Identifier: Apache-2.0
"""No devices: lossless producer/PC/cold capacity and completed-trial scope."""
import inspect
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as S
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
for name in ('twinpulse_app','twinpulse_core','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
sys.path.insert(0,str(ROOT/'packages/twinpulse_robot_safety'))
from twinpulse_core.robot_control_timing import EVENT_ARCHIVE_BYTES,EVENT_ARCHIVE_SEGMENTS
from twinpulse_app.physical_live_session import StreamEvidence
from twinpulse_app import physical_live_history
from fleet_worker import SegmentedWriter,FleetWorker
from fleet_control import RobotControl


class ArchiveBudgetTests(unittest.TestCase):
    def test_same_finite_budget_in_both_writers_and_reader(self):
        self.assertEqual(EVENT_ARCHIVE_BYTES,768*1024*1024)
        self.assertEqual(inspect.signature(StreamEvidence).parameters['maximum_bytes'].default,EVENT_ARCHIVE_BYTES)
        self.assertEqual(inspect.signature(SegmentedWriter).parameters['maximum_bytes'].default,EVENT_ARCHIVE_BYTES)
        self.assertEqual(physical_live_history.EVENT_ARCHIVE_BYTES,EVENT_ARCHIVE_BYTES)
        self.assertGreaterEqual(EVENT_ARCHIVE_SEGMENTS,(EVENT_ARCHIVE_BYTES+4*1024*1024-1)//(4*1024*1024))
        journals=[]
        class Journal:
            def __init__(self,*_,**kw):journals.append(kw)
        class Native:
            def __init__(self,*_):pass
        with tempfile.TemporaryDirectory() as folder,patch('fleet_worker.RobotJournal',Journal),patch('fleet_worker.ProtocolOutbox',lambda *_a,**_k:None),patch('fleet_worker.checked_context',lambda x:x):
            owner=FleetWorker({},folder,lambda *_:None,native_factory=Native,control_factory=lambda *_a,**_k:None)
            self.assertEqual(journals[0]['max_bytes'],owner.disk.maximum_bytes)

    def test_small_explicit_budget_still_rejects_losslessly(self):
        with tempfile.TemporaryDirectory() as folder:
            writer=StreamEvidence(Path(folder)/'original',maximum_bytes=4)
            self.assertTrue(writer.append(b'1234'))
            self.assertFalse(writer.append(b'5'))
            result=writer.close(cleanup_confirmed=True)
            self.assertEqual(result['accepted'],1)
            self.assertEqual(result['saved'],1)
            self.assertFalse(result['complete'])
            self.assertIn('CAPACITY',result['error'])
            self.assertEqual((Path(folder)/'original/events-00000.jsonl').read_bytes(),b'1234')

    def test_completed_trial_is_not_repeated_as_active(self):
        with tempfile.TemporaryDirectory() as folder:
            native=S(latest_frame=lambda:None)
            owner=RobotControl({},Path(folder),lambda *_:None,native,clock=lambda:1.)
            owner._field_blockers=lambda:[]
            trial=dict(trial_id='kept',status='PASS',result={'original':'retained'})
            owner.field_trial=trial;owner.field_trials=[trial];owner.field_receipt={'stop':'original'}
            complete=owner._field_snapshot()
            self.assertIsNone(complete['active_trial'])
            self.assertEqual(complete['trials'],[trial])
            self.assertEqual(complete['stop_receipt'],{'stop':'original'})
            for status in ('RUNNING','PENDING_PERSISTENCE'):
                trial['status']=status
                self.assertEqual(owner._field_snapshot()['active_trial'],trial)


if __name__=='__main__':unittest.main()
