# SPDX-License-Identifier: Apache-2.0
"""Actual shipped stdin bootstrap in isolated Python/HOME; no SSH or device.

The deliberately invalid session context stops the real worker before its first
runtime/device action. This tests receiver validation/extraction, not just the
sender's archive membership or imports from a hand-extracted directory.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from twinpulse_app.physical_live_session import BOOTSTRAP, reviewed_bundle

ROOT = Path(__file__).resolve().parents[2]


def packet_for(files):
    digests = {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}
    identity = hashlib.sha256(json.dumps(digests, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    packet = dict(schema='physical-live-bundle-1.0', sha256=identity,
                  files={name: dict(base64=base64.b64encode(raw).decode(), sha256=digests[name])
                         for name, raw in files.items()})
    return (json.dumps(packet) + '\n').encode(), identity


def probe(code, encoded, home):
    # -I avoids repo/PYTHONPATH leakage. Empty context is rejected before
    # verify_release(), idle board reads, ROS, threads or port ownership.
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home))
    return subprocess.run([sys.executable, '-I', '-B', '-c', code],
                          input=encoded + b'{}\n', cwd=home, env=env,
                          capture_output=True, timeout=25)


class BootstrapRoundtripTests(unittest.TestCase):
    def test_complete_sender_receiver_roundtrip_cache_and_inert_worker(self):
        identity, encoded, expected = reviewed_bundle(ROOT)
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            for _ in range(2):
                result = probe(BOOTSTRAP, encoded, home)
                self.assertEqual(result.returncode, 2, result.stderr.decode())
                self.assertEqual(result.stderr.strip(), b'FLEET_WORKER_REJECTED:START_SHAPE')
                self.assertFalse(result.stdout)
            release = home / '.local/share/twinpulse/fleet/releases' / identity
            actual = {p.relative_to(release).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in release.rglob('*') if p.is_file()}
            self.assertEqual(actual, expected)
            self.assertFalse((home / '.local/share/twinpulse/robot').exists())
            self.assertFalse((home / '.local/share/twinpulse/fleet/sessions').exists())
            (release / 'guard_base/src/turtlebot3.cpp').write_bytes(b'changed')
            changed = probe(BOOTSTRAP, encoded, home)
            self.assertNotEqual(changed.returncode, 0)
            self.assertIn(b'BOOTSTRAP_CACHE_CHANGED', changed.stderr)

    def test_path_expansion_does_not_admit_traversal_or_unreviewed_scripts(self):
        names = ('../escape.py', '/escape.py', 'guard_base/src/../escape.cpp',
                 'guard_base/src/a/../../escape.cpp', 'guard_base/src\\escape.cpp',
                 'guard_base/src/inject.py', 'tests/inject.py', 'C:/escape.py',
                 'twinpulse_core/../escape.py', 'guard_base//src/escape.cpp')
        for name in names:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                home = Path(directory)
                encoded, _ = packet_for({name: b'not executed'})
                result = probe(BOOTSTRAP, encoded, home)
                self.assertIn(b'BOOTSTRAP_PATH', result.stderr)
                self.assertFalse((home / '.local').exists())

    def test_file_and_bundle_hashes_remain_mandatory_before_writes(self):
        _, encoded, _ = reviewed_bundle(ROOT)
        for kind in ('file', 'bundle'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                packet = json.loads(encoded)
                if kind == 'file':
                    packet['files']['guard_base/LICENSE']['sha256'] = '0' * 64
                else:
                    packet['sha256'] = '0' * 64
                result = probe(BOOTSTRAP, (json.dumps(packet) + '\n').encode(), Path(directory))
                self.assertIn(('BOOTSTRAP_FILE_SHA' if kind == 'file' else 'BOOTSTRAP_BUNDLE_SHA').encode(), result.stderr)
                self.assertFalse((Path(directory) / '.local').exists())


if __name__ == '__main__':
    unittest.main()
