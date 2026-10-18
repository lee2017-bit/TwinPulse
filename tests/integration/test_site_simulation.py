# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""SIM binding stays distinct from a v2 scene and physical authority."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
for name in ('twinpulse_core', 'twinpulse_provider', 'twinpulse_app'):
    sys.path.insert(0, str(ROOT/'packages'/name/'src'))
from twinpulse_app.bedroom_review import load_bedroom_source
from twinpulse_app.simulation_assets import burger_inventory
from twinpulse_app.command_broker import BrokerError, CommandBroker
from twinpulse_core import SimulationSnapshot
from twinpulse_core.site_simulation import make_plan, checked_plan, waypoint_command


class SiteSimulationTests(unittest.TestCase):
    def setUp(self):
        self.scene = load_bedroom_source()[0].site.scene
        self.inventory = burger_inventory()
        self.plan = make_plan(self.scene, [-.3, -1.2], [-.3, -.25], self.inventory)

    def test_plan_does_not_modify_v2_or_authorize_real(self):
        before = self.scene.to_dict()
        self.assertEqual(checked_plan(self.scene, self.plan), self.plan)
        self.assertEqual(self.scene.to_dict(), before)
        self.assertFalse(self.plan['physical_authority'])
        self.assertEqual(self.plan['mode'], 'SIM')
        self.assertEqual(len(self.inventory), 9)

    def test_tampered_route_hash_speed_and_authority_are_rejected(self):
        for field, value in [('route', [[99., 99.]]), ('plan_id', '0'*64), ('max_linear_mps', 1.),
                             ('physical_authority', True), ('scene_revision', '0'*64)]:
            with self.subTest(field=field):
                changed = deepcopy(self.plan); changed[field] = value
                with self.assertRaises(ValueError): checked_plan(self.scene, changed)

    def test_blocked_and_outside_goal_rejected(self):
        for point in ([.88, -.05], [20., 20.], [-.3, -1.2]):
            with self.assertRaises(ValueError): make_plan(self.scene, [-.3, -1.2], point, self.inventory)

    def test_invalid_coordinates_and_yaw(self):
        for point in ([True, 0], [float('nan'), 0], [0], '0, 1'):
            with self.assertRaises(ValueError): make_plan(self.scene, point, [0, 0], self.inventory)
        with self.assertRaises(ValueError): make_plan(self.scene, [-.3, -1.2], [0, 0], self.inventory, yaw_rad=True)

    def test_rotation_translation_and_arrival(self):
        linear, angular, done = waypoint_command([0, 0], 0, [0, 1])
        self.assertEqual(linear, 0); self.assertGreater(angular, 0); self.assertFalse(done)
        self.assertGreater(waypoint_command([0, 0], 1.570796, [0, 1])[0], 0)
        self.assertTrue(waypoint_command([0, .99], 1.57, [0, 1])[2])
        self.assertLess(waypoint_command([0, 0], 0, [0, -1])[1], 0)

    def broker(self, capability=True, revision=None, safety=None, preview=True):
        broker = CommandBroker()
        broker.register_site_scene('room', self.scene)
        broker.register_engine('engine', 'stage')
        broker.acquire_lease('product')
        broker.record_snapshot(SimulationSnapshot(engine_session_id='engine', stage_epoch='stage', project_id='default',
            applied_revision=revision or self.scene.revision, run_id=None, sequence=1, runtime_state='built',
            safety_state=safety, safety_reason=None, permitted_commands=('build_site_scene', 'get_state'),
            capabilities=('simulation', 'site_scene_build_v2')+ (('site_simulation_v1',) if capability else ())
                + (('site_simulation_preview_v1',) if preview else ())))
        return broker

    def test_build_preview_binds_registered_plan_without_run(self):
        broker = self.broker(); broker.register_simulation_plan(self.scene, self.plan)
        body = dict(client_request_id='preview-1', command_type='build_site_scene',
                    artifact_id='room', expected_applied_revision=self.scene.revision,
                    simulation_id=self.plan['plan_id'])
        op = broker.submit('product', body)
        self.assertEqual(broker.submit('product', body), op)
        command = broker.claim('engine', 'stage')
        self.assertEqual(command.command_type, 'build_site_scene')
        self.assertEqual(command.payload['simulation_preview'], self.plan)
        self.assertNotIn('site_simulation', command.payload)
        self.assertFalse(command.payload['simulation_preview']['physical_authority'])

    def test_preview_rejects_unknown_plan_or_old_engine(self):
        body = dict(client_request_id='preview-1', command_type='build_site_scene',
                    artifact_id='room', expected_applied_revision=self.scene.revision,
                    simulation_id=self.plan['plan_id'])
        for broker, code in ((self.broker(), 'simulation_plan_unknown'),
                             (self.broker(preview=False), 'simulation_preview_capability_missing')):
            if code != 'simulation_plan_unknown': broker.register_simulation_plan(self.scene, self.plan)
            with self.assertRaises(BrokerError) as caught: broker.submit('product', body)
            self.assertEqual(caught.exception.code, code)

    def body(self):
        return dict(client_request_id='run-1', command_type='run', expected_applied_revision=self.scene.revision,
                    simulation_id=self.plan['plan_id'])

    def test_ordinary_scene_run_still_forbidden(self):
        broker = self.broker(); body = self.body(); body.pop('simulation_id')
        with self.assertRaises(BrokerError) as caught: broker.submit('product', body)
        self.assertEqual(caught.exception.code, 'site_scene_run_forbidden')

    def test_capability_revision_safety_and_registry_required(self):
        for broker in (self.broker(False), self.broker(revision='0'*64), self.broker(safety='blocked')):
            broker.register_simulation_plan(self.scene, self.plan)
            with self.assertRaises(BrokerError): broker.submit('product', self.body())
        with self.assertRaises(BrokerError): self.broker().submit('product', self.body())

    def test_duplicate_and_lost_response_recovery_owned_only(self):
        broker = self.broker(); broker.register_simulation_plan(self.scene, self.plan)
        op = broker.submit('product', self.body())
        self.assertEqual(broker.submit('product', self.body()), op)
        self.assertEqual(broker.request_outcome('product', 'run-1'), op)
        with self.assertRaises(BrokerError): broker.request_outcome('other', 'run-1')
        command = broker.claim('engine', 'stage')
        self.assertEqual(command.payload, {'site_simulation': self.plan})

    def test_plan_registration_detaches_caller(self):
        broker = self.broker(); broker.register_simulation_plan(self.scene, self.plan)
        self.plan['physical_authority'] = True
        broker.submit('product', self.body())
        self.assertFalse(broker.claim('engine', 'stage').payload['site_simulation']['physical_authority'])


if __name__ == '__main__': unittest.main()
