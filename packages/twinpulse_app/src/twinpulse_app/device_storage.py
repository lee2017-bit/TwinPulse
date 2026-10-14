# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""User-local device files and non-destructive, repeatable legacy migration."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import time
from uuid import uuid4


def migrate_device_records(source_root, data_root):
    source_root, data_root = Path(source_root).resolve(), Path(data_root).resolve()
    groups = ('robot-readiness-app', 'manual-control', 'project-session-index', 'robot-console')
    destination = data_root / 'artifacts'
    destination.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink() or destination.resolve() != destination:
        raise ValueError('DEVICE_STORAGE_PATH_INVALID')
    marker = data_root / 'legacy-migration.json'
    if marker.exists():
        return
    copied = []
    for group in groups:
        source, target = source_root / 'artifacts' / group, destination / group
        if not source.exists() or target.exists():
            continue
        entries = [source, *source.rglob('*')]
        if any(p.is_symlink() or not p.resolve().is_relative_to(source_root) for p in entries):
            raise ValueError('LEGACY_DEVICE_ARCHIVE_PATH_INVALID')
        staging = destination / ('.migration-' + uuid4().hex)
        shutil.copytree(source, staging)
        for path in entries:
            if path.is_file():
                relative = path.relative_to(source)
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                if hashlib.sha256((staging / relative).read_bytes()).hexdigest() != digest:
                    raise ValueError('LEGACY_DEVICE_ARCHIVE_COPY_MISMATCH')
        os.replace(staging, target)
        copied.append(group)
    temporary = data_root / ('.migration-' + uuid4().hex + '.json')
    with temporary.open('x', encoding='utf-8') as stream:
        json.dump(dict(schema='device-migration-1.0', copied=copied, original_deleted=False), stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, marker)


class DeviceOwnerLease:
    """OS lock is released on process death; stale file contents are not a lock."""
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.is_symlink():
            raise ValueError('DEVICE_OWNER_PATH_INVALID')
        self.stream = self.path.open('a+b')
        try:
            self.stream.seek(0, os.SEEK_END)
            if self.stream.tell() == 0:
                self.stream.write(b'\0')
                self.stream.flush()
            self.stream.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            self.stream.close()
            raise

    def close(self):
        if self.stream.closed:
            return
        self.stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
        self.stream.close()


def diagnostic_retention(data_root, *, days=30, max_bytes=512*1024*1024, archive=False, active_job=None):
    """Archive finished connection diagnostics only; never project/sensor/current state."""
    if type(days) is not int or not 1 <= days <= 365:
        raise ValueError('Invalid retention period')
    root = Path(data_root).resolve()
    folder = root/'artifacts/robot-console'
    rows = []
    if folder.is_symlink():
        raise ValueError('Invalid diagnostic archive')
    if folder.exists():
        for directory in folder.iterdir():
            import re
            if (directory.name == active_job or not re.fullmatch('[a-f0-9]{24}|[a-f0-9]{32}', directory.name)
                    or not directory.is_dir()):
                continue
            entries = [directory, *directory.rglob('*')]
            if any(p.is_symlink() or not p.resolve().is_relative_to(folder) for p in entries):
                continue
            if not (directory/'report.json').is_file():
                continue
            rows.append((directory, directory.stat().st_mtime,
                         sum(p.stat().st_size for p in entries if p.is_file())))
    total = sum(row[2] for row in rows)
    remaining = total
    candidates = []
    threshold = time.time() - days*86400
    for directory, timestamp, size in sorted(rows, key=lambda row: row[1]):
        if timestamp < threshold or remaining > max_bytes:
            candidates.append((directory, size))
            remaining -= size
    moved = 0
    if archive and candidates:
        retired = root/'retired-diagnostics'/uuid4().hex
        if retired.parent.is_symlink() or retired.parent.resolve() != retired.parent:
            raise ValueError('Invalid retired diagnostic path')
        retired.mkdir(parents=True)
        for directory, _size in candidates:
            os.replace(directory, retired/directory.name)
            moved += 1
    return dict(days=days, max_bytes=max_bytes, eligible_count=len(candidates),
                eligible_bytes=sum(row[1] for row in candidates), active_bytes=remaining,
                archived_count=moved, recoverable=True,
                scope='finished_connection_diagnostics_only')
