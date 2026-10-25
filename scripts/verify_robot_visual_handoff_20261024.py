# SPDX-License-Identifier: Apache-2.0
"""Read-only AND of the full journey and this change's visual-impact gate.

This binds existing gate bytes. It does not run a missing check, modify an
original result, grant hardware authority, or claim physical qualification.
"""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path


def checks(records, release, source):
    issues = []
    for role, status in (
        ('full', 'READY_FOR_SUPERVISED_POWERED_TEST'),
        ('scoped', 'PASS_SCOPED_SOFTWARE_PREPARATION'),
    ):
        row = records.get(role, {})
        if row.get('status') != status:
            issues.append('GATE_NOT_PASS:' + role)
        if row.get('issues') != []:
            issues.append('GATE_ISSUES_OR_MISSING:' + role)
        if row.get('release_id') != release or row.get('source_sha256') != source:
            issues.append('GATE_NOT_CURRENT:' + role)
    return issues


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', required=True, type=Path)
    p.add_argument('--full', required=True, type=Path)
    p.add_argument('--scoped', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    root = a.root.resolve()
    active = json.loads((Path(os.environ['LOCALAPPDATA']) /
                         'TwinPulse/installed/active-release.json').read_text(encoding='utf-8-sig'))
    release, source = active['release_id'], active['source_manifest_sha256']
    records, refs, originals = {}, {}, {}
    for role, path in (('full', a.full), ('scoped', a.scoped)):
        if path.is_symlink() or path.is_junction():
            raise ValueError('UNSAFE_GATE_REFERENCE:' + role)
        path = path.resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError('MISSING_OR_OUTSIDE_GATE:' + role)
        raw = path.read_bytes()
        originals[path] = raw
        records[role] = json.loads(raw.decode('utf-8-sig'))
        refs[role] = dict(path=path.relative_to(root).as_posix(), sha256=sha256(raw).hexdigest())
    issues = checks(records, release, source)
    negatives = []
    for role in ('full', 'scoped'):
        for name in ('missing', 'status', 'issues', 'release', 'source'):
            candidate = deepcopy(records)
            if name == 'missing':
                candidate.pop(role)
            else:
                key = {'status': 'status', 'issues': 'issues', 'release': 'release_id', 'source': 'source_sha256'}[name]
                candidate[role][key] = ['ORIGINAL_FAILURE'] if name == 'issues' else 'WRONG'
            rejected = bool(checks(candidate, release, source))
            negatives.append(dict(role=role, mutation=name, rejected=rejected))
            if not rejected:
                issues.append('NEGATIVE_ACCEPTED:' + role + ':' + name)
    unchanged = all(path.read_bytes() == raw for path, raw in originals.items())
    if not unchanged:
        issues.append('ORIGINAL_GATE_CHANGED_DURING_CHECK')
    value = dict(schema='robot-visual-whole-handoff-1.0',
                 status='READY_FOR_SUPERVISED_POWERED_TEST' if not issues else 'NOT_READY',
                 release_id=release, source_sha256=source, issues=issues,
                 evidence=refs, negatives=negatives, originals_unchanged=unchanged,
                 physical_outcomes='NOT_RUN_ROBOT_OFF',
                 limitation='Full current-release journey AND current visual-impact acceptance only. '
                            'Historical failures are retained; no physical acquisition, braking, driving or world alignment qualification.')
    with a.output.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
    print(json.dumps(dict(status=value['status'], issues=issues, negative_count=len(negatives))))
    return int(bool(issues))


if __name__ == '__main__':
    raise SystemExit(main())
