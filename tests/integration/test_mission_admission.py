# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import copy
import unittest
from twinpulse_app.mission_admission import QualifiedMissionAdmission
from twinpulse_core.mission_contract import document_hash


class AdmissionTests(unittest.TestCase):
    def fixture(self):
        scope={'frame_id':'odom','waypoints':[[.08,0.]],'duration_s':5.}
        expected={'project_id':'default','boot_id':'fake','release_id':'a'*64,'calibration_revision':'b'*64,
            'stop_policy_revision':'c'*64,'scope_revision':document_hash(scope)}
        evidence={**expected,'sample_s':20.,'voltage':12.,'origin':'live_ros','timing_basis':'VERIFIED_ACQUISITION',
            'transform_basis':'measured_sensor_extrinsic',**{k:True for k in ('release_reviewed','calibration_reviewed',
            'current_stop_qualified','scope_approved','sensor_owned','output_watchdog_verified','board_idle')}}
        return scope,expected,evidence
    def test_current_server_evidence_is_copied_scope_bound_and_not_saved_unlock(self):
        scope,expected,evidence=self.fixture();admit=QualifiedMissionAdmission(expected,lambda:evidence,lambda:20.01)
        result=admit(scope);result['release_id']='e'*64;self.assertEqual(evidence['release_id'],'a'*64)
        with self.assertRaises(ValueError):admit({**scope,'duration_s':6.})
    def test_missing_or_changed_qualification_each_reject(self):
        scope,expected,base=self.fixture()
        for key in expected:
            evidence={**base,key:'changed'}
            with self.subTest(key=key),self.assertRaises(ValueError):QualifiedMissionAdmission(expected,lambda:evidence,lambda:20.01)(scope)
        for key,value in (('sample_s',19.8),('origin','recorded_ros'),('timing_basis','UNVERIFIED'),
                ('transform_basis','nominal'),('voltage',11.1),('voltage',True),
                *((k,False) for k in ('release_reviewed','calibration_reviewed','current_stop_qualified',
                    'scope_approved','sensor_owned','output_watchdog_verified','board_idle'))):
            evidence={**base,key:value}
            with self.subTest(key=key),self.assertRaises(ValueError):QualifiedMissionAdmission(expected,lambda:evidence,lambda:20.01)(scope)
