# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Bounded failed-candidate context; never a relaxation or placement authority."""
from copy import deepcopy


def remember_failure(history, candidate, diagnosis, problems, context, revision, *, kind):
    """Preserve rejected target combinations across repairs and explicit resume.

    Only semantic parameters of actual repair targets are retained. Raw renders,
    prompts and duplicate compiler reports are not copied into the model input.
    Truncation describes context only; it never removes inventory or blockers.
    """
    identities = sorted({row['id'] for row in context.get('targets', [])})
    objects = candidate.get('objects', {})
    row = dict(candidate_revision=revision, repair_kind=kind,
        reason_codes=list(dict.fromkeys(str(p).split(':', 1)[0] for p in problems)),
        targets={identity:deepcopy(objects[identity]) for identity in identities[:32] if identity in objects},
        target_context_truncated=len(identities)>32,
        failed_checks=[r['check_id'] for r in diagnosis.get('checks', []) if r.get('status')=='failed'])
    result = deepcopy(history)
    if not result or result[-1] != row:
        result.append(row)
    return result[-8:]
