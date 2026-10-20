"""No-device regressions for the recorded arm/expiry failures and nonce generations."""
from pathlib import Path
import sys
import tempfile
import threading
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'twinpulse_core/src'))
from control_timing import INPUT_TTL_S
from teleop_contract import InputGate, MotionPaused
from robot_journal import RobotJournal
from teleop_worker import InputStream, ProtocolOutbox
import queue


class ContinuousTests(unittest.TestCase):
    def setUp(self):self.now=1.;self.gate=InputGate(lambda:self.now,continuous=True,persistent=True,recoverable=True)
    def packet(self,sequence=1,age=0,action='forward',challenge=None):
        return dict(sequence=sequence,action=action,age_ms=age,challenge=challenge or self.gate.challenge())
    def test_actual_g_h_timing_preparation_does_not_consume_future_motion(self):
        for age,arm in ((152.670355,.109484059),(186.361634,.117652177)):
            self.setUp();self.gate.accept(self.packet(age=age));self.gate.suspend_for_arm()
            self.now+=arm;self.gate.suspend_for_arm();self.gate.check()
            self.assertFalse(self.gate.active);self.assertFalse(self.gate.closed)
            self.now+=.001;self.gate.accept(self.packet(sequence=2));self.assertTrue(self.gate.active)
    def test_input_gap_pauses_and_watch_does_not_renew_direction(self):
        for gap in (INPUT_TTL_S,.5,1.):
            self.setUp();self.gate.accept(self.packet());self.now+=gap
            with self.assertRaises(MotionPaused):self.gate.check()
            self.assertFalse(self.gate.closed);self.assertFalse(self.gate.active)
            self.gate.accept(self.packet(sequence=2,action='watch'));self.gate.discard_idle_watch()
            self.assertFalse(self.gate.active)
    def test_revoked_high_sequence_does_not_poison_current_generation(self):
        old=self.gate.challenge();self.gate.accept(self.packet());self.gate.pause('OPERATOR_STOP')
        with self.assertRaisesRegex(ValueError,'CHALLENGE'):self.gate.accept(self.packet(sequence=999,challenge=old))
        self.assertEqual(self.gate.sequence,1);self.gate.accept(self.packet(sequence=2))
    def test_low_sequence_stop_always_revokes(self):
        self.gate.accept(self.packet(sequence=10));self.gate.accept(self.packet(sequence=1,action='stop'))
        self.assertFalse(self.gate.active);self.assertEqual(self.gate.sequence,10)
    def test_recording_delay_cannot_refresh_source_creation(self):
        self.gate.accept(self.packet(age=100));created=self.gate.source_created;self.now+=INPUT_TTL_S
        self.assertGreaterEqual(self.now-created,INPUT_TTL_S)
        with self.assertRaises(MotionPaused):self.gate.check()
    def test_legacy_bounded_policy_remains_terminal(self):
        self.gate=InputGate(lambda:self.now);self.gate.accept(self.packet());self.now+=INPUT_TTL_S
        with self.assertRaisesRegex(ValueError,'DEADLINE'):self.gate.check()
        self.assertTrue(self.gate.closed)
    def test_queued_graceful_close_is_not_overwritten_by_eof(self):
        stream=InputStream.__new__(InputStream);stream.messages=queue.Queue();stream.failed=threading.Event()
        stream.failure_reason='INPUT_EOF';stream.failed.set();stream.messages.put(dict(action='close'))
        self.assertEqual(stream.receive()['action'],'close')
        with self.assertRaisesRegex(ValueError,'INPUT_EOF'):stream.receive()
    def test_slow_disk_is_buffering_not_a_new_motion_deadline(self):
        entered=threading.Event();release=threading.Event()
        class Stream:
            def write(self,line):entered.set();release.wait(2);return len(line)
            def flush(self):pass
            def close(self):pass
        journal=RobotJournal(None,clock=lambda:self.now,opener=lambda _:Stream(),buffered=True)
        try:
            journal.append(dict(kind='observation'));self.assertTrue(entered.wait(1));self.now+=5.274820004
            journal.check();self.assertEqual(journal.status()['recording_state'],'BUFFERING');self.assertIsNone(journal.status()['error'])
        finally:release.set();journal.close()
    def test_delayed_protocol_does_not_destroy_manual_session_or_restamp_nonce(self):
        entered=threading.Event();release=threading.Event();sent=[]
        def writer(value):entered.set();release.wait(1);sent.append(value)
        box=ProtocolOutbox(writer,clock=lambda:self.now,buffered=True)
        value=dict(state='READY',challenge=dict(nonce='old',issued_s=self.now))
        try:
            box.send(value);self.assertTrue(entered.wait(1));self.now+=.5;box.check()
            self.assertIsNone(box.status()['error']);self.assertEqual(box.status()['delivery_state'],'BUFFERING')
        finally:release.set();box.close()
        self.assertEqual(sent,[value]);self.assertEqual(sent[0]['challenge']['issued_s'],1.)


if __name__=='__main__':unittest.main()
