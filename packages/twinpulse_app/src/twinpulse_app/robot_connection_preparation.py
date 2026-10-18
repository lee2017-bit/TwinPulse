# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Local connection prerequisites only. Never opens a robot or a private key."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import shutil
import subprocess
import sys
import time

from .robot_adapters import ADAPTER_ID, checked_binding

CHECKER_FILES = ('check_robot_connection.py', 'robot_health.py', 'turtlebot_probe.py')


def local_file_exists(path):
    try:return path.is_file()
    except OSError:return False


class RobotConnectionPreparation:
    def __init__(self, source_root, *, identity=None, known_hosts=None,
                 which=shutil.which, runner=subprocess.run, clock=time.monotonic):
        self.root = Path(source_root) if source_root is not None else None
        self.identity = Path(identity) if identity is not None else Path.home()/'.ssh/twinpulse-burger/id_ed25519_automation'
        self.known_hosts = Path(known_hosts) if known_hosts is not None else Path.home()/'.ssh/known_hosts'
        self.which, self.runner, self.clock = which, runner, clock
        self.value = None
        self.fingerprint = None
        self.checked_at = 0

    def _files(self):
        sources = [self.root/'scripts'/name for name in CHECKER_FILES] if self.root is not None else []
        return [self.identity, self.known_hosts, *sources]

    def _stamp(self):
        # Private key contents and known-host entries never enter state/logs.
        def stamp(path):
            try:
                value = path.stat()
                return (path.is_file(), value.st_size, value.st_mtime_ns)
            except OSError:
                return None
        return (tuple(stamp(path) for path in self._files()),
                self.which('ssh.exe' if sys.platform == 'win32' else 'ssh'),
                self.which('ssh-keygen.exe' if sys.platform == 'win32' else 'ssh-keygen'))

    def snapshot(self, binding, revision=None):
        if self.value is None or self.value['binding_sha256'] != (binding or {}).get('sha256'):
            return {'schema_version': 'robot-local-preparation-1.0', 'state': 'not_checked',
                    'pc_ready': False, 'connection_verified': False, 'motion_authorized': False, 'checks': []}
        value = deepcopy(self.value)
        if (self.clock()-self.checked_at > 120 or self._stamp() != self.fingerprint
                or revision is not None and self.value['registry_revision'] != revision):
            value.update(state='stale', pc_ready=False)
        return value

    def check(self, binding, revision):
        binding = checked_binding(binding)
        before = self._stamp()
        checks = []
        def add(identifier, ok, detail, next_step):
            checks.append({'id': identifier, 'state': 'ready' if ok else 'needs_attention',
                           'detail': detail, 'next_step': '' if ok else next_step})
        supported = binding['adapter_id'] == ADAPTER_ID
        add('reviewed_adapter', supported,
            'Reviewed TurtleBot3 Burger adapter.' if supported else 'This hardware has no reviewed connection adapter.',
            'Keep the registration and review a device adapter before connecting.')
        ssh = self.which('ssh.exe' if sys.platform == 'win32' else 'ssh')
        keygen = self.which('ssh-keygen.exe' if sys.platform == 'win32' else 'ssh-keygen')
        add('ssh_client', bool(ssh), 'OpenSSH client found.' if ssh else 'OpenSSH client is missing.',
            'Install the Windows OpenSSH client using the system setup guide, then check again.')
        sources = [self.root/'scripts'/name for name in CHECKER_FILES] if self.root is not None else []
        source_ready = len(sources) == len(CHECKER_FILES) and all(local_file_exists(path) for path in sources)
        add('checker_sources', source_ready, 'Read-only checker files found.' if source_ready else 'Read-only checker files are missing from this installation.',
            'Update or repair the TwinPulse installation. Do not copy robot data into the application folder.')
        key_exists = supported and local_file_exists(self.identity)
        add('identity_file', key_exists,
            'Automation key file exists; authentication has not been tested.' if key_exists else 'The reviewed adapter automation key is not available.',
            'Set up the adapter automation key locally. Never paste a private key into chat or robot registration.')
        known_exists = local_file_exists(self.known_hosts)
        add('known_hosts_file', known_exists, 'Local known-hosts file exists.' if known_exists else 'Local known-hosts file is missing.',
            'Verify the robot SSH fingerprint using its trusted setup instructions before recording its host identity.')
        matched = False
        lookup_state = 'not_checked'
        if known_exists and keygen:
            endpoint = binding['endpoint']
            host = endpoint['host'] if endpoint['port'] == 22 else f"[{endpoint['host']}]:{endpoint['port']}"
            try:
                result = self.runner([keygen, '-F', host, '-f', str(self.known_hosts)],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=3, check=False,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                matched = result.returncode == 0
                lookup_state = 'matched' if matched else 'not_registered' if result.returncode == 1 else 'unavailable'
            except (OSError, subprocess.TimeoutExpired):
                lookup_state = 'unavailable'
        add('selected_host_identity', matched,
            'Selected address has a local host-key entry; live identity is not yet verified.' if matched
            else 'Selected address has no confirmed local host-key entry.' if lookup_state == 'not_registered'
            else 'Selected address host-key lookup could not be confirmed.',
            'Check this exact address and SSH port against the robot fingerprint. TwinPulse will not accept or replace host keys automatically.')
        ready = all(row['state'] == 'ready' for row in checks)
        self.value = {'schema_version': 'robot-local-preparation-1.0', 'state': 'ready' if ready else 'needs_attention',
                      'pc_ready': ready, 'checked_at_utc': datetime.now(timezone.utc).isoformat(),
                      'registry_revision': revision, 'instance_id': binding['instance_id'],
                      'binding_sha256': binding['sha256'], 'host_key_lookup': lookup_state,
                      'checks': checks, 'connection_verified': False, 'motion_authorized': False}
        self.fingerprint, self.checked_at = self._stamp(), self.clock()
        if before != self.fingerprint:
            self.value.update(state='stale',pc_ready=False)
        return deepcopy(self.value)
