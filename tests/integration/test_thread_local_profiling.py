# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Local instrumentation tests; no inference, engine, files or hardware."""
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
import math
import sys
from threading import Event, Thread
import time
import unittest
from unittest.mock import patch

from twinpulse_core.execution_diagnostics import profile_call


class Capture:
    span_id = 'a' * 32

    def __init__(self):
        self.store = self
        self.events = []
        self.references = []

    @contextmanager
    def span(self, stage, **metadata):
        yield self

    def bind(self, **values):
        self.references.append(values)

    def emit(self, child, kind, values):
        self.events.append(dict(type=kind, span_id=child.span_id, metadata=values))


def cpu_leaf():
    return sum(i * i for i in range(8000))


def nested_work():
    return sum(cpu_leaf() for _ in range(4))


class ThreadLocalProfileTests(unittest.TestCase):
    def checked(self, trace):
        final = trace.references[-1]
        self.assertEqual(final['profile_status'], 'VALID', trace.references)
        self.assertTrue(final['profile_valid'])
        self.assertGreater(len(trace.events), 0)
        self.assertLessEqual(len(trace.events), 30)
        for event in trace.events:
            row = event['metadata']
            self.assertTrue(row['profile_valid'])
            self.assertTrue(math.isfinite(row['self_s']))
            self.assertLessEqual(row['self_s'], row['cumulative_s'] + 1e-6)
            self.assertLessEqual(row['cumulative_s'], final['profiled_elapsed_s'] + 1e-6)
        return final

    def test_nested_actual_cpu_preserves_result_and_hook(self):
        trace = Capture()
        self.assertEqual(profile_call(trace, 'compile', nested_work, enabled=True), nested_work())
        self.checked(trace)
        self.assertIsNone(sys.getprofile())
        self.assertTrue(any(e['metadata']['function'] == 'cpu_leaf' for e in trace.events))
        self.assertTrue(all(type(e['metadata']['source_line']) is int for e in trace.events))

    def test_foreign_cprofile_tool_is_not_replaced_or_disabled(self):
        import cProfile
        foreign = cProfile.Profile()
        trace, calls = Capture(), []
        foreign.enable()
        try:
            self.assertEqual(profile_call(trace, 'compile', lambda: calls.append(1) or 7, enabled=True), 7)
            if hasattr(sys, 'monitoring'):
                self.assertEqual(sys.monitoring.get_tool(sys.monitoring.PROFILER_ID), 'cProfile')
                self.assertEqual(trace.references[-1]['error_code'], 'PROFILE_SETUP_FAILED')
            else:
                self.assertIs(sys.getprofile(), foreign)
        finally:
            foreign.disable()
        self.assertEqual(calls, [1])
        self.assertEqual(trace.events, [])
        self.assertTrue(foreign.getstats())
        another = Capture()
        profile_call(another, 'next', nested_work, enabled=True)
        self.checked(another)

    def test_sleep_wall_and_cpu_are_separate_not_zero_wait(self):
        rows = {}
        for basis in ('wall', 'thread_cpu'):
            trace = Capture()
            profile_call(trace, 'waiting', time.sleep, .045, enabled=True, timer_basis=basis)
            self.checked(trace)
            rows[basis] = next(e['metadata']['cumulative_s'] for e in trace.events
                               if 'sleep' in e['metadata']['function'])
        self.assertGreater(rows['wall'], .035)
        self.assertLess(rows['thread_cpu'], rows['wall'])

    def test_unrelated_busy_thread_does_not_pollute_clock_or_rows(self):
        ready, stop = Event(), Event()

        def unrelated_background_work():
            ready.wait(2)
            while not stop.is_set():
                sum(i * i for i in range(350))

        worker = Thread(target=unrelated_background_work)
        worker.start()
        try:
            def measured():
                ready.set()
                time.sleep(.025)
                return nested_work()
            trace = Capture()
            self.assertEqual(profile_call(trace, 'compile', measured, enabled=True), nested_work())
            self.checked(trace)
            self.assertFalse(any('unrelated_background' in e['metadata']['function'] for e in trace.events))
        finally:
            stop.set()
            worker.join(2)
        self.assertFalse(worker.is_alive())

    def test_two_simultaneous_calls_never_wait_for_profile_or_global_tool_conflicts(self):
        entered, release = Event(), Event()
        def one():
            trace = Capture()
            def measured():
                entered.set()
                release.wait(3)
                return nested_work()
            value = profile_call(trace, 'compile', measured, enabled=True)
            return trace, value, sys.getprofile()
        with ThreadPoolExecutor(max_workers=2) as pool:
            future = pool.submit(one)
            self.assertTrue(entered.wait(2))
            trace = Capture()
            try:
                value = profile_call(trace, 'parallel', nested_work, enabled=True)
            finally:
                release.set()
            first, first_value, hook = future.result(timeout=4)
        self.checked(first)
        self.assertEqual(first_value, value)
        self.assertIsNone(hook)
        self.assertEqual(trace.references[-1]['error_code'], 'PROFILE_TOOL_BUSY')
        self.assertEqual(trace.events, [])

    def test_existing_hook_is_preserved_and_nested_profile_skips_without_replay(self):
        trace, calls = Capture(), []
        hook = lambda frame, event, arg: None
        sys.setprofile(hook)
        try:
            self.assertEqual(profile_call(trace, 'compile', lambda: calls.append(1) or 7, enabled=True), 7)
            self.assertIs(sys.getprofile(), hook)
        finally:
            sys.setprofile(None)
        self.assertEqual(calls, [1])
        self.assertEqual(trace.references[-1]['error_code'], 'PROFILE_OTHER_TOOL_ACTIVE')
        self.assertEqual(trace.events, [])
        outer, inner = Capture(), Capture()
        profile_call(outer, 'outer', lambda: profile_call(inner, 'inner', nested_work, enabled=True), enabled=True)
        self.checked(outer)
        self.assertEqual(inner.references[-1]['profile_status'], 'SKIPPED')

    def test_original_exception_and_exactly_once_execution_survive_stats_failure(self):
        trace, calls = Capture(), []
        original = ValueError('private original failure')
        def fail():
            calls.append(1)
            raise original
        with patch('pstats.Stats', side_effect=OSError('private sink failure')):
            with self.assertRaises(ValueError) as caught:
                profile_call(trace, 'compile', fail, enabled=True)
        self.assertIs(caught.exception, original)
        self.assertEqual(calls, [1])
        self.assertEqual(trace.references[-1]['error_code'], 'PROFILE_STATS_FAILED')
        self.assertNotIn('private', str(trace.references))
        self.assertIsNone(sys.getprofile())

    def test_setup_failure_does_not_fail_or_replay_product(self):
        trace, calls = Capture(), []
        from twinpulse_core import execution_diagnostics
        with patch.object(execution_diagnostics, 'get_ident', side_effect=ValueError('private setup')):
            self.assertEqual(profile_call(trace, 'compile', lambda: calls.append(1) or 3, enabled=True), 3)
        self.assertEqual(calls, [1])
        self.assertEqual(trace.references[-1]['error_code'], 'PROFILE_SETUP_FAILED')
        self.assertIsNone(sys.getprofile())
        another = Capture()
        profile_call(another, 'next', nested_work, enabled=True)
        self.checked(another)  # Failure released the optional profiler slot.

    def test_invalid_row_outside_top_thirty_invalidates_whole_profile(self):
        trace = Capture()
        stats = {(f'safe{i}.py', 1, 'fn'): (1, 1, .0, .0, {}) for i in range(40)}
        stats[('invalid.py', 1, 'bad')] = (1, 1, .0, -.1, {})
        with patch('pstats.Stats') as mocked:
            mocked.return_value.stats = stats
            profile_call(trace, 'compile', lambda: 4, enabled=True)
        self.assertEqual(len(trace.events), 30)
        self.assertFalse(any(e['metadata']['function'] == 'bad' for e in trace.events))
        self.assertEqual(trace.references[-1]['profile_status'], 'INVALID')
        self.assertTrue(all(e['metadata']['profile_valid'] is False for e in trace.events))


if __name__ == '__main__':
    unittest.main()
