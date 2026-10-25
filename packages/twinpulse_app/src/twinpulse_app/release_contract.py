# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Shared update/start lock and explicit data compatibility for SIM releases.

Epoch 1 retains the existing storage formats. A future format migration must
stage data separately and publish its compatible executable/data pair; this
module deliberately does not claim a generic downgrade of arbitrary schemas.
"""
from contextlib import AbstractContextManager
import json
import os
from pathlib import Path
from uuid import uuid4

DATA_EPOCH = 1
DATA_CONTRACT = dict(schema='twinpulse-data-contract-1.0', read_epochs=[1], write_epoch=1,
    project=['1.0', '2.0'], conversation=['conversation-1.0'], site_draft=['2.0','2.1','2.2','2.3','2.4'],
    settings=['1.0','2.0','3.0'], read_capabilities=['environment-static-1.1','environment-survey-binding-1.0'],
    update_policy='same_epoch_and_required_capabilities_no_data_conversion')


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name('.' + path.name + '-' + uuid4().hex + '.tmp')
    with temporary.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, sort_keys=True)
        stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)


class MaintenanceLock(AbstractContextManager):
    """Kernel-held file lock: a crash releases it; file existence grants no lock."""
    def __init__(self, state):
        self.path = Path(state).parent / 'maintenance.lock'
        self.stream = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.is_symlink():
            raise ValueError('UPDATE_LOCK_PATH_INVALID')
        self.stream = self.path.open('a+b')
        try:
            self.stream.seek(0, os.SEEK_END)
            if not self.stream.tell():
                self.stream.write(b'0'); self.stream.flush()
            self.stream.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.stream.close(); self.stream = None
            raise ValueError('TWINPULSE_UPDATE_IN_PROGRESS') from error
        return self

    def __exit__(self, *args):
        if self.stream:
            self.stream.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
            self.stream.close(); self.stream = None


def check_data_epoch(state, contract=DATA_CONTRACT):
    path = Path(state) / 'data-compatibility.json'
    if path.is_symlink():
        raise ValueError('DATA_COMPATIBILITY_RECORD_INVALID')
    if not path.exists():
        return DATA_EPOCH  # Original formats are epoch 1; no conversion occurs.
    if path.stat().st_size > 4096:
        raise ValueError('DATA_COMPATIBILITY_RECORD_INVALID')
    value = json.loads(path.read_text(encoding='utf-8'))
    epoch = value.get('data_epoch')
    if value.get('schema') not in {'twinpulse-runtime-data-1.0','twinpulse-runtime-data-1.1'} or type(epoch) is not int:
        raise ValueError('DATA_COMPATIBILITY_RECORD_INVALID')
    if value['schema']=='twinpulse-runtime-data-1.1':
        required=value.get('required_capabilities')
        if (not isinstance(required,list) or not required or len(required)>32 or
                any(not isinstance(c,str) or not 1<=len(c)<=100 for c in required) or len(set(required))!=len(required)):
            raise ValueError('DATA_COMPATIBILITY_RECORD_INVALID')
        if not set(required)<=set(contract.get('read_capabilities',[])):
            raise ValueError('DATA_CAPABILITY_REQUIRES_COMPATIBLE_RELEASE')
    if epoch not in contract.get('read_epochs', []) or epoch != contract.get('write_epoch'):
        raise ValueError('DATA_VERSION_REQUIRES_COMPATIBLE_RELEASE')
    return epoch


def initialize_data_epoch(state):
    epoch = check_data_epoch(state)
    path = Path(state) / 'data-compatibility.json'
    if not path.exists():
        atomic_json(path, dict(schema='twinpulse-runtime-data-1.0', data_epoch=epoch))
    return epoch


def require_data_capability(state,capability):
    """Sticky barrier BEFORE journals contain a new nested format, even STAGED.

    Older launchers reject the 1.1 marker schema instead of ignoring added keys.
    Undo cannot remove this barrier: historical operations still need readers.
    No project conversion or data-epoch change is performed.
    """
    # Same App writes are serialized by its scene writer. The kernel maintenance
    # lock also excludes an installer while this marker is published.
    if capability not in DATA_CONTRACT['read_capabilities']:raise ValueError('DATA_CAPABILITY_UNSUPPORTED')
    with MaintenanceLock(state):
        epoch=check_data_epoch(state)
        path=Path(state)/'data-compatibility.json'
        old=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        required=set(old.get('required_capabilities',[]))|{capability}
        atomic_json(path,dict(schema='twinpulse-runtime-data-1.1',data_epoch=epoch,required_capabilities=sorted(required)))


def project_runtime_root(path):
    path=Path(path)
    return path.parent.parent.parent if path.name=='project.json' and path.parent.parent.name=='projects' else path.parent
