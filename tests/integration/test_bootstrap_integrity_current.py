# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Supplementary bootstrap byte/path checks; no installed App execution."""
import hashlib
import json
from pathlib import Path
import runpy
import tempfile
import unittest

verify=runpy.run_path(str(Path(__file__).resolve().parents[2]/'scripts/twinpulse_bootstrap_integrity.py'))['verify_before_import']


class BootstrapIntegrityTests(unittest.TestCase):
    def test_every_file_still_hashed_and_next_call_revalidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);directory=root/'shared/ancestor';directory.mkdir(parents=True)
            files=[]
            for i in range(5):
                name=f'shared/ancestor/{i}.bin';data=bytes([i])*20;(root/name).write_bytes(data)
                files.append(dict(path=name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
            manifest=dict(schema='twinpulse-windows-exe-1.0',files=files)
            (root/'windows-release-manifest.json').write_text(json.dumps(manifest))
            self.assertEqual(len(verify(root)['files']),5)
            (root/files[-1]['path']).write_bytes(b'x'*20)
            with self.assertRaisesRegex(ValueError,'MISMATCH'):verify(root)

    def test_unlisted_file_and_traversal_still_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'data.bin';path.write_bytes(b'data')
            files=[dict(path='data.bin',bytes=4,sha256=hashlib.sha256(b'data').hexdigest())]
            manifest=root/'windows-release-manifest.json'
            manifest.write_text(json.dumps(dict(schema='twinpulse-windows-exe-1.0',files=files)))
            extra=root/'unlisted.bin';extra.write_bytes(b'extra')
            with self.assertRaisesRegex(ValueError,'UNMANIFESTED'):verify(root)
            files[0]['path']='../data.bin';manifest.write_text(json.dumps(dict(schema='twinpulse-windows-exe-1.0',files=files)))
            with self.assertRaisesRegex(ValueError,'PATH_INVALID'):verify(root)
