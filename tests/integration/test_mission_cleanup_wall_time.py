# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Observe the existing cleanup regression beyond its old wall-time join."""
import hashlib
import json
import os
from pathlib import Path
import unittest
from tests.integration import test_automatic_mission_service as fixture


class CleanupWallTimeTests(unittest.TestCase):
    def test_exact_cleanup_failure_after_same_short_goal_preserves_cause(self):
        helper=fixture.AutomaticMissionTests();self.addCleanup(helper.doCleanups);helper.setUp()
        helper.configure([0.,-.6,0.]);original=helper.service.adapter_factory
        def factory(*args):
            adapter=original(*args)
            def close():
                adapter.halt();raise ValueError('OWNED_SENSOR_STOP_UNCONFIRMED')
            adapter.close=close;return adapter
        helper.service.adapter_factory=factory
        helper.service.start('owner',helper.map_id,helper.goal([.05,-.6]))
        helper.service.worker.join(30)
        at30=helper.service.snapshot('owner')['job'];alive_at30=helper.service.worker.is_alive()
        helper.service.worker.join(150)  # Diagnostic wall time only;45 source seconds remain fixed.
        job=helper.service.snapshot('owner')['job'];adapter=helper.adapters[-1]
        name=os.environ.get('TWINPULSE_CLEANUP_EVIDENCE')
        if name:
            self.assertRegex(name,'^[a-z0-9-]{1,100}$')
            folder=Path(__file__).resolve().parents[2]/'artifacts'/name
            folder.mkdir(parents=True,exist_ok=False)
            record={'alive_at30':alive_at30,'snapshot_at30':at30,'job':job,
                'raw':adapter.raw,'published':adapter.sent,'source_clock_s':adapter.t,
                'final_velocity':adapter.velocity,'physical_validation':'NOT_RUN','robot_connections':0}
            (folder/'diagnosis.json').write_text(json.dumps(record,allow_nan=False),encoding='utf-8')
            sources=('tests/integration/test_mission_cleanup_wall_time.py',
                'tests/integration/test_automatic_mission_service.py',
                'packages/twinpulse_core/src/twinpulse_core/current_mission_evidence.py',
                'packages/twinpulse_core/src/twinpulse_core/sensor_map_localization.py',
                'packages/twinpulse_core/src/twinpulse_core/automatic_mapping.py',
                'packages/twinpulse_core/src/twinpulse_core/room_localization.py',
                'packages/twinpulse_app/src/twinpulse_app/automatic_mission_service.py')
            (folder/'source-hashes.json').write_text(json.dumps({p:hashlib.sha256(
                (Path(__file__).resolve().parents[2]/p).read_bytes()).hexdigest() for p in sources}),encoding='utf-8')
        self.assertFalse(helper.service.worker.is_alive())
        self.assertEqual(job['state'],'FAILED')
        self.assertEqual(job['error'],'OWNED_SENSOR_STOP_UNCONFIRMED')
        self.assertEqual(job['cleanup_error'],job['error'])
        self.assertEqual(adapter.velocity,(0.,0.));self.assertLess(adapter.t,65.)
        self.assertIsNone(job['visual']['pose_room']);self.assertFalse(job['visual']['scan_room'])


if __name__=='__main__':unittest.main()
