# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
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
    def test_native_buffered_sink_flush_policy_does_not_change_default_journals(self):
        for flush_each in (True,False):
            class Counted(Sink):
                def __init__(self):super().__init__();self.flushes=0;self.closed=False
                def flush(self):self.flushes+=1
                def close(self):self.closed=True
            sink=Counted();journal=RobotJournal(None,opener=lambda _:sink,flush_each=flush_each)
            journal.append(dict(kind='original'));status=journal.close()
            self.assertEqual(sink.flushes,1 if flush_each else 0)
            self.assertTrue(sink.closed);self.assertFalse(status['writer_alive'])
            self.assertEqual((status['accepted'],status['saved']),(1,1))

    def test_slow_final_close_waits_for_actual_writer_not_just_saved_count(self):
        class SlowClose(Sink):
            def close(self):time.sleep(2.1)
        sink=SlowClose();journal=RobotJournal(None,opener=lambda _:sink)
        journal.append(dict(kind='original',sequence=1))
        status=journal.close(timeout=15.)
        self.assertEqual((status['accepted'],status['saved']),(1,1))
        self.assertFalse(status['writer_alive']);self.assertIsNone(status['error'])

    def test_fleet_buffer_retains_large_burst_but_pending_byte_bound_remains_fatal(self):
        release=threading.Event();sink=Sink(release);now=[0.]
        journal=RobotJournal(None,capacity=2048,max_pending_bytes=8192,buffered=True,
            clock=lambda:now[0],opener=lambda _:sink)
        try:
            journal.append({'kind':'first'});self.assertTrue(sink.entered.wait(1))
            for i in range(200):journal.append({'kind':'command','i':i})
            now[0]=1.945;journal.check()
            self.assertIsNone(journal.status()['error'])
            self.assertTrue(journal.status()['buffering'] if 'buffering' in journal.status() else journal.buffering)
            with self.assertRaisesRegex(ValueError,'PENDING_BYTE_BUDGET'):
                journal.append({'kind':'large','payload':'x'*8192})
        finally:release.set();result=journal.close()
        self.assertEqual(result['accepted'],result['saved'])
        self.assertEqual(result['error'],'SESSION_JOURNAL_PENDING_BYTE_BUDGET')

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
