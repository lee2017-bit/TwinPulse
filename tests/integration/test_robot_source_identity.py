# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Local-only release identity parity with the exact deployable archive."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from prepare_robot import bundle
from robot_source_identity import source_id,bundle_files


class SourceIdentityTests(unittest.TestCase):
    def test_reviewed_archive_complete_safe_and_inert_outside_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);configured=os.environ.get('TWINPULSE_REVIEWED_ARCHIVE')
            archive_path=Path(configured).resolve() if configured else root/'source.tar'
            if not configured:bundle(archive_path)
            expected=bundle_files(ROOT);actual={}
            with tarfile.open(archive_path) as archive:
                for member in archive.getmembers():
                    self.assertTrue(member.isfile());self.assertNotIn(member.name,actual)
                    self.assertIn(member.name,expected);self.assertLessEqual(member.size,512*1024)
                    data=archive.extractfile(member).read();self.assertEqual(data,expected[member.name])
                    actual[member.name]=data
            self.assertEqual(set(actual),set(expected))
            self.assertIn('twinpulse_core/mission_correction_contract.py',actual)
            self.assertIn('twinpulse_core/mission_evidence_contract.py',actual)
            package=root/'isolated';package.mkdir()
            for name,data in actual.items():
                if name.endswith('.py'):
                    compile(data,name,'exec');path=package/name
                    self.assertTrue(path.resolve().is_relative_to(package.resolve()))
                    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
            code=('import sys;sys.path.insert(0,sys.argv[1]);import mission_runtime,teleop_ros,observed_runtime;'
                  'from twinpulse_core.mission_correction_contract import checked_reply;'
                  'from twinpulse_core.navigation_binding import PlanarBinding;'
                  'assert mission_runtime.PlanarBinding is PlanarBinding;'
                  'assert "rclpy" not in sys.modules and "twinpulse_app" not in sys.modules;'
                  'print("SOURCE_ONLY_INERT_IMPORT_PASS")')
            result=subprocess.run([sys.executable,'-I','-B','-c',code,str(package)],cwd=package,capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr);self.assertIn('SOURCE_ONLY_INERT_IMPORT_PASS',result.stdout)
            identity=hashlib.sha256(json.dumps({n:hashlib.sha256(v).hexdigest() for n,v in actual.items()},sort_keys=True).encode()).hexdigest()
            self.assertEqual(identity,source_id(ROOT))
            evidence=os.environ.get('TWINPULSE_ARCHIVE_EVIDENCE')
            if evidence:
                self.assertRegex(evidence,'^[a-z0-9-]{1,100}$')
                output=ROOT/'artifacts'/evidence;output.mkdir(parents=True,exist_ok=False)
                sources=('scripts/prepare_robot.py','scripts/robot_source_identity.py','tests/integration/test_robot_source_identity.py',
                    'packages/twinpulse_core/src/twinpulse_core/mission_correction_contract.py')
                (output/'verification.json').write_text(json.dumps({'status':'SOURCE_ONLY_OFFLINE_ACCEPTED',
                    'member_count':len(actual),'source_id':identity,'archive_sha256':hashlib.sha256(archive_path.read_bytes()).hexdigest(),
                    'archive_path':str(archive_path),'isolated_import':'PASS','robot_connections':0,'physical_validation':'NOT_RUN',
                    'target_binary':'NOT_BUILT','profile_qualification':'NOT_REGISTERED','deployment':'NOT_RUN',
                    'offline_implementation_ready':False,'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources}},indent=2))

    def test_local_release_matches_runtime_source_file_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / 'source.tar'
            bundle(archive_path)
            with tarfile.open(archive_path) as archive:
                files = {member.name: hashlib.sha256(archive.extractfile(member).read()).hexdigest()
                         for member in archive.getmembers() if member.isfile()}
        expected = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
        self.assertEqual(source_id(ROOT), expected)


if __name__ == '__main__':
    unittest.main()
