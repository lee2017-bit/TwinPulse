# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Revision-bound preview snapshots for candidate rollback; never live authority."""
from copy import deepcopy
from twinpulse_core import canonical_sha256
from .semantic_scene import revision


def snapshot_preview(draft, plan, capture, progress):
    if not draft or not plan or not progress:
        return None
    identity = revision(draft)
    if progress.get('candidate_revision') != identity:
        return None
    metadata = capture.get('metadata') if capture else None
    if metadata and (metadata.get('candidate_revision') != identity or
                     metadata.get('plan_sha256') != canonical_sha256(plan)):
        return None
    return dict(candidate_revision=identity, plan=deepcopy(plan), progress=deepcopy(progress),
                capture_metadata=deepcopy(metadata),
                render_key=canonical_sha256(metadata) if metadata else None)


def checked_preview_snapshot(draft, snapshot):
    if not snapshot or snapshot.get('candidate_revision') != revision(draft):
        return None
    progress = snapshot.get('progress')
    plan = snapshot.get('plan')
    metadata = snapshot.get('capture_metadata')
    if not plan or not progress or progress.get('candidate_revision') != revision(draft):
        return None
    if metadata and (metadata.get('candidate_revision') != revision(draft) or
                     metadata.get('plan_sha256') != canonical_sha256(plan) or
                     snapshot.get('render_key') != canonical_sha256(metadata)):
        return None
    result = deepcopy(snapshot)
    # A successful historic Build is not the current engine revision after a
    # newer candidate, cancellation, restart, or context switch.
    result['progress'].update(state='blocked', error_code='PREVIEW_REBUILD_REQUIRED')
    return result
