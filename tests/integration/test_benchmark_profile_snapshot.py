# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only ranking policy; historical raw profiles are never rewritten."""
from copy import deepcopy
import unittest
from scripts.run_model_combination_benchmark import profile_snapshot


class ProfileSnapshotTests(unittest.TestCase):
    def event(self, identity='good', **changes):
        meta=dict(source_file='compile.py', function='compile', calls=1, self_s=.01, cumulative_s=.02,
                  profile_valid=True, profiler_kind='thread_filtered_cprofile',
                  profile_id=identity, timer_basis='thread_cpu')
        meta.update(changes)
        return dict(span_id=identity, type='profile_row', metadata=meta)

    def test_old_valid_looking_rows_and_whole_invalid_span_are_unranked(self):
        events=[self.event(),self.event('legacy',profile_valid=None),
                self.event('bad',self_s=1),self.event('bad',self_s=.01)]
        original=deepcopy(events);result=profile_snapshot(dict(events=events))
        self.assertEqual(events,original)
        self.assertEqual(result['excluded_rows'],3)
        self.assertEqual(result['invalid_profiles'],1)
        self.assertEqual(len(result['rows']),1)
        self.assertEqual(result['rows'][0]['calls'],1)

    def test_truncated_nonfinite_or_unbound_evidence_never_ranks(self):
        result=profile_snapshot(dict(events=[self.event()],events_truncated=True))
        self.assertEqual(result['rows'],[])
        self.assertEqual(profile_snapshot(dict(events=[self.event()],health=dict(diagnostics_degraded=True)))['rows'],[])
        for changes in (dict(self_s=float('nan')),dict(profile_id='other'),dict(cumulative_s=-1)):
            self.assertEqual(profile_snapshot(dict(events=[self.event(**changes)]))['rows'],[])

    def test_valid_profiles_aggregate_only_same_timer_and_report_missing(self):
        events=[self.event(),self.event('next'),self.event('wall',timer_basis='wall')]
        rows=profile_snapshot(dict(events=events))
        self.assertEqual(rows['status'],'VALID')
        self.assertEqual(len(rows['rows']),2)
        self.assertEqual(rows['rows'][0]['calls'],2)
        self.assertEqual(profile_snapshot(dict(events=[]))['status'],'NOT_MEASURED')

    def test_same_named_generators_on_different_lines_are_distinct_functions(self):
        rows=profile_snapshot(dict(events=[self.event(source_line=12),self.event('next',source_line=28)]))
        self.assertEqual(len(rows['rows']),2)
        self.assertEqual({row['source_line'] for row in rows['rows']},{12,28})
        self.assertTrue(all(row['calls']==1 for row in rows['rows']))


if __name__=='__main__':unittest.main()
