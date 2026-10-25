# SPDX-License-Identifier: Apache-2.0
"""Immutable, bounded local evidence for a late engine ACK, never authority."""
import hashlib
import json
import os
from pathlib import Path


def preserve_late_receipt(root, command, original, late):
    directory = Path(root) / 'late-engine-receipts'
    for path in (directory, *directory.parents):
        if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
            raise ValueError('LATE_RECEIPT_LINKED_LOCATION')
    value = dict(schema_version='late-engine-receipt-1.0',
                 expected_applied_revision=command.expected_applied_revision,
                 original_receipt=original.to_dict(), late_receipt=late.to_dict())
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                     allow_nan=False).encode('utf-8')
    if len(raw) > 16384:
        raise ValueError('LATE_RECEIPT_TOO_LARGE')
    directory.mkdir(exist_ok=True, parents=True)
    target = directory / (hashlib.sha256(command.command_id.encode()).hexdigest() + '.json')
    if target.exists():
        if target.is_symlink() or target.stat().st_nlink != 1 or target.stat().st_size > 16384:
            raise ValueError('LATE_RECEIPT_INVALID_STORAGE')
        with target.open('r+b') as stream:
            if os.fstat(stream.fileno()).st_nlink != 1 or stream.read(16385) != raw:
                raise ValueError('LATE_RECEIPT_CONTENT_CONFLICT')
            # A prior attempt may have written all bytes but failed its fsync.
            # A delivery retry must not bypass that failed durable step.
            stream.flush()
            os.fsync(stream.fileno())
    else:
        # One immutable record per retained operation, no deletion/rotation.
        from itertools import islice
        if len(list(islice(directory.iterdir(), 257))) >= 256:
            raise OSError('LATE_RECEIPT_STORE_FULL')
        with target.open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    return hashlib.sha256(json.dumps(late.to_dict(), sort_keys=True,
        separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
