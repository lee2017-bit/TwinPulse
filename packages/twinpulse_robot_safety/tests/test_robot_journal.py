# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from robot_journal import RobotJournal

class Sink:
    def __init__(self,gate=None,fail=False):self.lines=[];self.entered=threading.Event();self.gate=gate;self.fail=fail
    def write(self,line):
        self.entered.set()
        if self.gate:self.gate.wait(2)
        if self.fail:raise OSError('fake disk failure')
        self.lines.append(line);return len(line)
    def flush(self):pass
    def close(self):pass

class JournalTests(unittest.TestCase):
    def test_blocked_disk_never_blocks_producer_and_fault_stays_latched(self):
        gate=threading.Event();sink=Sink(gate);now=[0.]
        journal=RobotJournal(None,clock=lambda:now[0],opener=lambda _:sink)
        try:
            journal.append({'kind':'accepted','sequence':1});self.assertTrue(sink.entered.wait(1))
            journal.append({'kind':'published','sequence':1});now[0]=.201
            with self.assertRaisesRegex(ValueError,'WRITE_STALLED'):journal.check()
            status=journal.close(timeout=.001)
            self.assertTrue(status['writer_alive']);self.assertEqual(status['error'],'SESSION_JOURNAL_WRITE_STALLED')
        finally:gate.set();journal.close()

    def test_exact_order_and_frozen_event_saved_to_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'session.jsonl';journal=RobotJournal(path)
            event={'kind':'accepted','sequence':1};journal.append(event);event['sequence']=9
            journal.append({'kind':'published','sequence':1});status=journal.close()
            self.assertEqual(status['saved'],2);self.assertIsNone(status['error'])
            self.assertEqual([json.loads(line)['sequence'] for line in path.read_text().splitlines()],[1,1])

    def test_overflow_disk_failure_and_byte_budget_are_explicit(self):
        gate=threading.Event();sink=Sink(gate);journal=RobotJournal(None,capacity=1,opener=lambda _:sink)
        try:
            journal.append({'kind':'first'});self.assertTrue(sink.entered.wait(1))
            journal.append({'kind':'second'})
            with self.assertRaisesRegex(ValueError,'QUEUE_FULL'):journal.append({'kind':'third'})
        finally:gate.set();journal.close()
        journal=RobotJournal(None,max_bytes=1,opener=lambda _:Sink())
        with self.assertRaisesRegex(ValueError,'BYTE_BUDGET'):journal.append({'kind':'large'})
        journal.close()
        journal=RobotJournal(None,opener=lambda _:Sink(fail=True));journal.append({'kind':'fail'})
        self.assertEqual(journal.close()['error'],'SESSION_JOURNAL_WRITE_FAILED')

if __name__=='__main__':unittest.main()
