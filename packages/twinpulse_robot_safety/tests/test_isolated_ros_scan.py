# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Device-free reviewed driver selection, validation and launch orchestration."""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import coin_driver_identity as pins
import isolated_ros_scan as scan


class DriverIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.binary=self.root/'single_coin_d4_node'; self.library=self.root/'libcoin_d4_driver_lib.so'
        data=bytearray(64); data[:6]=b'\x7fELF\x02\x01'; data[18:20]=(183).to_bytes(2,'little')
        self.data=bytes(data)
        self.binary.write_bytes(self.data); self.library.write_bytes(self.data)
        self.stack=ExitStack(); self.addCleanup(self.stack.close)
        for key,value in (('BINARY',self.binary),('DRIVER_LIB',self.library),
                ('BINARY_SHA256',hashlib.sha256(self.data).hexdigest()),
                ('DRIVER_LIB_SHA256',hashlib.sha256(self.data).hexdigest())):
            self.stack.enter_context(patch.object(scan,key,value))
        self.runner=self.stack.enter_context(patch.object(scan.subprocess,'run',return_value=
            subprocess.CompletedProcess([],0,('libcoin_d4_driver_lib.so => '+str(self.library)).encode(),b'')))

    def test_artifact_check_never_opens_sensor_or_launches(self):
        with patch.object(scan.subprocess,'Popen') as child, patch.object(scan.os.path,'realpath') as device:
            self.assertEqual(scan.driver_artifact_identity()['artifact_checks'],'PASS_NO_SENSOR_ACCESS')
            device.assert_not_called(); child.assert_not_called()
        self.assertEqual(self.runner.call_args.args[0],['ldd',str(self.binary)])

    def test_binary_and_library_change_fail_before_loader(self):
        for path,reason in ((self.binary,'BINARY_SHA'),(self.library,'LIBRARY_SHA')):
            with self.subTest(path=path):
                path.write_bytes(b'changed')
                with self.assertRaisesRegex(RuntimeError,reason):scan.driver_artifact_identity()
                self.runner.assert_not_called(); path.write_bytes(self.data)

    def test_missing_binary_is_precise(self):
        with patch.object(scan,'BINARY',self.root/'absent'):
            with self.assertRaisesRegex(RuntimeError,'BINARY_MISSING'):scan.driver_artifact_identity()
        self.runner.assert_not_called()

    def test_wrong_architecture_is_rejected(self):
        data=self.data[:18]+(62).to_bytes(2,'little')+self.data[20:]
        self.binary.write_bytes(data)
        with patch.object(scan,'BINARY_SHA256',hashlib.sha256(data).hexdigest()):
            with self.assertRaisesRegex(RuntimeError,'NOT_ARM64_ELF'):scan.driver_artifact_identity()
        self.runner.assert_not_called()

    def test_loader_missing_dependency_is_precise(self):
        self.runner.return_value=subprocess.CompletedProcess([],0,b'libexample.so => not found',b'')
        with self.assertRaisesRegex(RuntimeError,'UNRESOLVED:libexample.so'):scan.driver_artifact_identity()

    def test_loader_different_candidate_is_rejected(self):
        self.runner.return_value=subprocess.CompletedProcess([],0,b'libcoin_d4_driver_lib.so => /old/lib.so',b'')
        with self.assertRaisesRegex(RuntimeError,'DIFFERENT_PATH'):scan.driver_artifact_identity()

    def test_busy_sensor_does_not_launch(self):
        self.runner.side_effect=[subprocess.CompletedProcess([],0,str(self.library).encode(),b''),
                                 subprocess.CompletedProcess([],0,b'12345',b'')]
        with patch.object(scan.os.path,'realpath',return_value='/dev/ttyUSB0'), patch.object(scan.subprocess,'Popen') as child:
            with self.assertRaisesRegex(RuntimeError,'SENSOR_PORT_BUSY'):scan.binary_identity()
            child.assert_not_called()

    def test_start_uses_reviewed_binary_and_environment(self):
        with patch.object(scan,'binary_identity',return_value={}), patch.object(scan.subprocess,'Popen') as child:
            driver=scan.IsolatedRosScan(self.root/'driver.log')
            driver.start()
            self.assertEqual(child.call_args.args[0][0],str(self.binary))
            self.assertIn(str(self.library.parent),child.call_args.kwargs['env']['LD_LIBRARY_PATH'])
            driver.stream.close()

    def test_environment_does_not_inject_preloads(self):
        with patch.dict(scan.os.environ,{'LD_PRELOAD':'bad.so','LD_AUDIT':'audit.so'}):
            environment=scan.driver_environment()
            self.assertNotIn('LD_PRELOAD',environment); self.assertNotIn('LD_AUDIT',environment)

    def test_pins_match_actual_saved_build_and_keep_unverified_timing(self):
        root=Path(__file__).resolve().parents[3]
        report=root/'artifacts/coin-target-build/coin-time-build-20261006T125707Z-30d7bdc2/target/report.json'
        if not report.is_file():self.skipTest('PC-only exported target evidence')
        saved=json.loads(report.read_bytes())
        self.assertEqual(pins.BINARY.as_posix(),saved['artifacts']['single_coin_d4_node']['path'])
        self.assertEqual(pins.BINARY_SHA256,saved['artifacts']['single_coin_d4_node']['sha256'])
        self.assertEqual(pins.DRIVER_LIB_SHA256,saved['artifacts']['libcoin_d4_driver_lib.so']['sha256'])
        self.assertFalse(pins.description()['physical_verified'])
        self.assertEqual(pins.TIMING_BASIS,'HOST_SYNC_APPROXIMATE_NOT_HARDWARE_FIRST_RAY')


if __name__=='__main__':unittest.main()
