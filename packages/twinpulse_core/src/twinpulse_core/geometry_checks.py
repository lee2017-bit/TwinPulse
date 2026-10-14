# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Evidence from executed compiler phases, bound to one immutable candidate.

No PASS is inferred from the absence of an exception in a later phase. The
compiler explicitly enters/completes each registered phase; skipped phases are
blocked and executor failures remain errors rather than model mistakes.
"""
from copy import deepcopy

CHECK_REVISION = 'geometry-check-ledger-1.0'
PHASES = ('input_contract', 'model_relations', 'floor_packing', 'support_packing',
          'attachment_placement', 'tool_executor', 'placement_validation', 'evidence_binding')


class GeometryChecks:
    def __init__(self, candidate_revision, compiler_revision, library_revision, targets):
        self.current = None
        self.rows = []
        for index, phase in enumerate(PHASES):
            self.rows.append(dict(check_id=phase, target_ids=sorted(targets),
                dependency_fields=['$.room', '$.inventory', '$.objects'],
                candidate_revision=candidate_revision, checker_revision=CHECK_REVISION,
                compiler_revision=compiler_revision, library_revision=library_revision,
                status='not_run', blocked_by=[], issue_refs=[],
                depends_on=list(PHASES[:index])))

    def mark(self, phase, status):
        row = next(r for r in self.rows if r['check_id'] == phase)
        if status == 'running':
            self.current = phase
        elif status in {'passed','partial'}:
            row['status'] = status
            self.current = None
        else:
            raise ValueError('GEOMETRY_CHECK_TRANSITION_INVALID')

    def failure(self, diagnosis):
        current = self.current or 'input_contract'
        issues = diagnosis.get('issues', [])
        internal = not issues or any(r.get('repairable') is False or
            r.get('code') == 'UNMAPPED_COMPILER_ERROR' for r in issues)
        for row in self.rows:
            if row['check_id'] == current:
                row['status'] = 'error' if internal else 'failed'
                row['issue_refs'] = [r.get('issue_id', r.get('code')) for r in issues]
            elif row['status'] != 'passed':
                row.update(status='blocked', blocked_by=[current])
        return self.report()

    def report(self):
        rows = deepcopy(self.rows)
        return dict(check_ledger_version=CHECK_REVISION, candidate_revision=rows[0]['candidate_revision'], checks=rows,
            mandatory_checks=list(PHASES), checks_complete=all(r['status']=='passed' for r in rows),
            checks_truncated=False,
            **({'materialized_subset_checked':all(r['status'] in {'passed','partial'} for r in rows),
                'inventory_complete':False} if any(r['status']=='partial' for r in rows) else {}))
