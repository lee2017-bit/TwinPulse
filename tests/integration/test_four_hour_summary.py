# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""All generated evidence here is synthetic, including claimed capture records."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
sys.path.insert(0, str(ROOT/'packages/twinpulse_core/tests'))
from test_native_scan import fixture
from summarize_four_hour_prep import collect, render, COMBINED_STAGES, NATIVE_STAGES, APP_CHECKS, FAULT_CHECKS
from twinpulse_core.native_scan import NativeScanBundle
from twinpulse_core.native_scan_3d import export_native_frame_3d


class FourHourSummaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.c, self.n, self.i, self.r = [self.root/name for name in ('combined', 'native', 'isaac', 'regression')]
        for path in (self.c, self.n, self.i, self.r): path.mkdir()
        image = b'\x89PNG\r\n\x1a\nSYNTHETIC'
        raw, nodes, photo = b'fixture raw', b'fixture nodes', b'fixture photo'
        value = fixture()
        value['source'].update(kind='saved_sensor_recording', raw_sha256=hashlib.sha256(raw).hexdigest(), nodes_sha256=hashlib.sha256(nodes).hexdigest())
        first = value['frames'][0]
        value['frames'] = []
        for index in range(3):
            frame = copy.deepcopy(first); frame['index'] = index
            for beam in frame['beams']:
                beam['node_index'] += index*10; beam['source_byte_cursor'] += index*10
            value['frames'].append(frame)
        value['photos'][0]['sha256'] = hashlib.sha256(photo).hexdigest()
        value['photos'].append(dict(value['photos'][0], role='top_view'))
        bundle = NativeScanBundle.from_dict(value)
        for name in ('native-scan-bundle.json', 'exported-native-scan-bundle.json'): self.write(self.n/name, value)
        for name in ('room.jpg', 'top-view-window-up.jpg'): (self.n/name).write_bytes(photo)
        capture = self.root/'artifacts/lidar-capture-20260927-1214'
        (capture/'lidar-20260927T031354Z-323c99a6').mkdir(parents=True)
        (capture/'lidar-20260927T031354Z-323c99a6/raw.bin').write_bytes(raw)
        (capture/'nodes.ndjson').write_bytes(nodes)
        frames = []
        for index in range(3):
            final = export_native_frame_3d(bundle, index)
            (self.i/f'native-frame-{index:03d}.usda').write_bytes(final['usda'].encode())
            (self.i/f'frame-{index:03d}.png').write_bytes(image)
            frames.append(dict(index=index, point_count=final['point_count'], export_sha256=final['sha256'], capture_sha256=hashlib.sha256(image).hexdigest()))
        (self.n/'exported-native-frame-002.usda').write_bytes(final['usda'].encode())
        for folder,name in ((self.n,'native-photo-review-desktop.png'),(self.c,'combined-desktop.png')): (folder/name).write_bytes(image)
        (self.c/'synthetic-derived-stage.usda').write_text('synthetic fixture')
        self.write(self.i/'result.json', dict(status='PASS', kind='actual_isaac_saved_evidence_import', source_kind='saved_sensor_recording',
            bundle_digest=bundle.digest, frames=frames, world_alignment='UNVERIFIED', motion_authorized=False,
            physics_run='NOT_RUN', physical_validation='NOT_RUN', robot_connections=0, provider_calls=0, app_download_sha256=final['sha256']))
        self.write(self.c/'result.json', dict(status='PASS', data='synthetic_test_fixture', checks=COMBINED_STAGES,
            boundary='browser_API_broker_production_bridge_actual_Isaac', original_project_changed=False,
            external_prim_preserved=True, extension_UI_started=False, robot_connections=0, provider_calls=0,
            physics_run='NOT_RUN', physical_validation='NOT_RUN', failure_checks=FAULT_CHECKS, source_and_build_sha256={'synthetic': 'current'}))
        self.write(self.c/'browser-result.json', dict(status='PASS', data='synthetic', stages=COMBINED_STAGES,
            commands=['build_site_scene']*2, failure_checks=FAULT_CHECKS, external_requests=0, page_errors=0))
        self.write(self.n/'result.json', dict(status='PASS', browser_stages=NATIVE_STAGES, data='saved_sensor_recording',
            http='actual_local_backend', active_project_changed=False, robot='NOT_RUN', isaac='NOT_RUN', provider_calls='NOT_RUN', source_and_build_sha256={'synthetic':'current'}))
        self.write(self.n/'browser-result.json', dict(status='PASS', data='saved_sensor_recording', http='actual_local_backend',
            stages=NATIVE_STAGES, physical_validation='NOT_RUN', external_requests=0, engine_commands=0, page_errors=0,
            bundle_digest=bundle.digest, native_3d_export={'sha256':final['sha256'],'frame_index':2}))
        self.write(self.r/'manifest.json', dict(status='PASS', app=APP_CHECKS, isaac='NOT_RUN', artifact_dir=str(self.r)))
        self.r.with_suffix('.log').write_text('Ran 2 tests in 0.1s\n'*8+'Tests 3 passed (3)\nTWINPULSE_VERIFY_RESULT=PASS\n')

    @staticmethod
    def write(path, value): path.write_text(json.dumps(value), encoding='utf-8')

    def change(self, path, **values):
        obj = json.loads(path.read_text()); obj.update(values); self.write(path,obj)

    def collect(self):
        with patch('summarize_four_hour_prep.native_source_hashes', return_value={'synthetic':'current'}), patch('summarize_four_hour_prep.combined_source_hashes', return_value={'synthetic':'current'}):
            return collect(self.root,self.c,self.n,self.i,self.r)

    def test_matching_evidence_static_only_not_physical_ready(self):
        s = self.collect()
        self.assertEqual(s['status'],'OFFLINE_EVIDENCE_PASS')
        self.assertEqual((s['python_tests'],s['web_tests']),(16,3))
        self.assertFalse(s['physical_demo_ready']); self.assertFalse(s['motion_authorized'])
        self.assertEqual(s['physical_stop'],'FAIL_UNCHANGED')
        self.assertNotIn('<script',render(s)); self.assertNotIn('https://',render(s))

    def test_changed_current_source_binding_is_failure(self):
        self.change(self.c/'result.json',source_and_build_sha256={'synthetic':'old'})
        s = self.collect()
        self.assertFalse(s['checks']['combined_current_code_build_binding'])
        self.assertIn('EVIDENCE_CHECK_FAILED',render(s)); self.assertNotIn('통과',render(s))

    def test_wrong_data_boundary_or_extra_run_is_failure(self):
        self.change(self.c/'browser-result.json',data='saved_sensor_recording',commands=['build_site_scene','run'],failure_checks=[])
        s = self.collect()
        self.assertFalse(s['checks']['combined_real_UI_bridge_Isaac_six_stages'])
        self.assertFalse(s['checks']['combined_browser_fault_and_actual_lease_expiry'])

    def test_historical_USD_or_capture_change_is_failure(self):
        (self.i/'native-frame-001.usda').write_text('changed')
        (self.i/'frame-002.png').write_bytes(b'\x89PNG\r\n\x1a\nchanged')
        self.assertFalse(self.collect()['checks']['historical_actual_native_Isaac_three_frames_unchanged'])

    def test_missing_run_is_not_replaced(self):
        (self.c/'result.json').unlink()
        with self.assertRaises(FileNotFoundError): self.collect()

    def test_duplicate_json_and_nonfinite_rejected(self):
        for text in ('{"status":"PASS","status":"PASS"}', '{"value":NaN}'):
            (self.c/'result.json').write_text(text)
            with self.assertRaises(ValueError): self.collect()

    def test_regression_wrong_directory_or_incomplete_counts_fail(self):
        self.change(self.r/'manifest.json',artifact_dir=str(self.n))
        self.assertFalse(self.collect()['checks']['explicit_full_regression_and_counts'])

    def test_utf16_counts_and_missing_stage(self):
        path=self.r.with_suffix('.log'); path.write_bytes(path.read_text().encode('utf-16'))
        self.assertEqual(self.collect()['status'],'OFFLINE_EVIDENCE_PASS')
        self.change(self.n/'browser-result.json',stages=NATIVE_STAGES[:-1])
        self.assertFalse(self.collect()['checks']['saved_native_actual_App_nine_stages'])


if __name__ == '__main__': unittest.main()
