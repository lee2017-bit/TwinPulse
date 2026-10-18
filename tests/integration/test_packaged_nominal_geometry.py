# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Portable pinned nominal model, never a measured robot or scan fallback."""
import hashlib
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from twinpulse_app.robot_geometry_evidence import ROOT,MODEL,load_geometry_evidence

FILES=('artifacts/robot-models/burger-prepared/source.json',MODEL+'/urdf/turtlebot3_burger.urdf',
       MODEL+'/meshes/bases/burger_base.stl',MODEL+'/meshes/wheels/left_tire.stl',
       MODEL+'/meshes/wheels/right_tire.stl',MODEL+'/meshes/sensors/lds.stl')

class PortableNominalTests(unittest.TestCase):
    def fixture(self,folder):
        hashes={}
        for name in FILES:
            target=folder/name;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/name,target);hashes[name]=hashlib.sha256(target.read_bytes()).hexdigest()
        return hashes
    def test_no_private_capture_required_and_no_physical_authority(self):
        with TemporaryDirectory() as directory:
            folder=Path(directory);hashes=self.fixture(folder);e=load_geometry_evidence(folder)
            self.assertEqual(e['basis'],'PINNED_NOMINAL_MODEL_ONLY')
            self.assertEqual(e['source_sha256'],hashes)
            self.assertEqual(e['base_link_to_scan_xyz_m'],[-.032,0.,.172]);self.assertEqual(e['retained_guard_radius_m'],.18)
            self.assertEqual(e['saved_scan']['frames'],0);self.assertEqual(e['saved_scan']['status'],'NOT_PROVIDED')
            self.assertFalse(e['motion_authorized']);self.assertFalse(e['alignment_verified'])
            self.assertEqual(e['physical_robot_match'],'UNVERIFIED')
            self.assertIn('SAVED_RAW_SCAN_NOT_PROVIDED',e['missing'])
    def test_partial_capture_is_error_not_silently_ignored(self):
        with TemporaryDirectory() as directory:
            folder=Path(directory);self.fixture(folder)
            p=folder/'artifacts/photo-scan-review-20260927/native-scan-bundle.json'
            p.parent.mkdir(parents=True);p.write_text('{}')
            with self.assertRaisesRegex(ValueError,'SAVED_SCAN_EVIDENCE_INCOMPLETE'):load_geometry_evidence(folder)
    def test_changed_nominal_model_still_rejected_without_capture(self):
        with TemporaryDirectory() as directory:
            folder=Path(directory);self.fixture(folder);(folder/(MODEL+'/urdf/turtlebot3_burger.urdf')).write_text('tampered')
            with self.assertRaisesRegex(ValueError,'PINNED_MODEL_CHANGED'):load_geometry_evidence(folder)

if __name__=='__main__':unittest.main()
