# SPDX-License-Identifier: Apache-2.0
"""Local settings integration only; no transport/motors or application UI claim."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from threading import Thread
from unittest.mock import patch
from tests.integration import test_r5_product_api
from twinpulse_app.robot_registry import RobotRegistry,RobotEndpoint
from twinpulse_app.robot_adapters import instance_binding
from twinpulse_core.robot_timing_profile import DEFAULTS,TimingAccumulator,digest


class RobotTimingSettingsTests(unittest.TestCase):
    def test_first_measurement_baseline_then_operator_override_and_cold_restore(self):
        with TemporaryDirectory() as directory:
            reg=RobotRegistry(Path(directory))
            row=reg.register(label='one',adapter_id='turtlebot3_burger_v1',adapter_version='burger-reviewed-1.0',endpoint=RobotEndpoint('one.local','twinpulse'),expected_revision=0)
            rid=row['id'];binding=instance_binding(row)['sha256'];p=TimingAccumulator()
            for i in range(500):p.observe('sensor_source_ms',30+i%20,i*.1,'lidar')
            reg.record_timing_measurement(rid,binding,'a'*32,p.snapshot())
            s=reg.snapshot();settings=s['robots'][0]['timing_settings']
            self.assertEqual(settings['profile']['mode'],'measured_default')
            self.assertIsNone(settings['recommendation'])
            values=dict(settings['profile']['values'],input_ttl_ms=400,output_timeout_ms=500,operator_presence_ms=600)
            reg.timing_action(rid,expected_revision=s['revision'],expected_sha256=settings['profile_sha256'],values=values,mode='custom')
            reg.record_timing_measurement(rid,binding,'b'*32,p.snapshot())
            cold=RobotRegistry(Path(directory)).snapshot()['robots'][0]['timing_settings']
            self.assertEqual(cold['profile']['values'],values);self.assertEqual(cold['profile']['mode'],'custom')
            self.assertIsNone(cold['recommendation'])
            self.assertEqual(cold['apply_policy'],'NEXT_EXPLICIT_CONNECTION_ONLY')
            with self.assertRaisesRegex(ValueError,'ROBOT_REGISTRY_CHANGED'):
                reg.timing_action(rid,expected_revision=s['revision'],expected_sha256=settings['profile_sha256'],values=values,mode='custom')
            # Metadata stays outside strict old-reader registry and immutable binding.
            self.assertEqual(instance_binding(reg._read()['robots'][0])['sha256'],binding)
            self.assertNotIn('timing_settings',reg._read()['robots'][0])
            errors=[]
            def cleanup_writer():
                try:reg.record_timing_measurement(rid,binding,'d'*32,p.snapshot())
                except Exception as exc:errors.append(str(exc))
            # A UI reader/selection owning the registry mutex must not prevent
            # an already-stopped session cleanup from finishing its writer.
            with reg.lock:
                worker=Thread(target=cleanup_writer);worker.start();worker.join(2.)
                self.assertFalse(worker.is_alive(),'cleanup/registry lock inversion')
            self.assertEqual(errors,[])

    def test_measurement_recalculate_and_apply_are_three_separate_transitions(self):
        with TemporaryDirectory() as directory:
            reg=RobotRegistry(Path(directory))
            row=reg.register(label='one',adapter_id='turtlebot3_burger_v1',adapter_version='burger-reviewed-1.0',endpoint=RobotEndpoint('one.local','u'),expected_revision=0)
            rid=row['id'];binding=instance_binding(row)['sha256']
            p=TimingAccumulator();p.observe('odom_interval_ms',100,1,'base')
            reg.record_timing_measurement(rid,binding,'a'*32,p.snapshot())
            def current():
                s=reg.snapshot();return s['revision'],s['robots'][0]['timing_settings']
            _,initial=current();self.assertIsNone(initial['recommendation'])
            p.observe('odom_interval_ms',350,2,'base')
            # Later records validate/store observations without running the calculator.
            with patch('twinpulse_app.robot_timing_store.recommendation',side_effect=AssertionError('automatic recalculation')):
                reg.record_timing_measurement(rid,binding,'b'*32,p.snapshot())
            rev,s=current();self.assertEqual(s['profile'],initial['profile']);self.assertIsNone(s['recommendation'])
            reg.timing_action(rid,expected_revision=rev,expected_sha256=s['profile_sha256'],recalculate=True)
            rev,s=current();rec=deepcopy(s['recommendation']);rec_sha=s['recommendation_sha256']
            self.assertEqual(s['profile'],initial['profile']);self.assertEqual(rec['profile']['values']['odom_interval_ms'],450)
            self.assertEqual(rec['profile']['evidence']['operation_id'],'b'*32)
            # Even a new source record does not refresh an existing recommendation.
            p.observe('odom_interval_ms',450,3,'base')
            with patch('twinpulse_app.robot_timing_store.recommendation',side_effect=AssertionError('automatic recalculation')):
                reg.record_timing_measurement(rid,binding,'c'*32,p.snapshot())
            rev,s=current();self.assertEqual(s['recommendation'],rec);self.assertEqual(s['profile'],initial['profile'])
            cold=RobotRegistry(Path(directory)).snapshot()['robots'][0]['timing_settings']
            self.assertEqual(cold['recommendation_sha256'],rec_sha);self.assertEqual(cold['measurement_operation_id'],'c'*32)
            with self.assertRaisesRegex(ValueError,'ROBOT_REGISTRY_CHANGED'):
                reg.timing_action(rid,expected_revision=rev,expected_sha256=s['profile_sha256'],mode='measured_default',expected_recommendation_sha256='f'*64)
            reg.timing_action(rid,expected_revision=rev,expected_sha256=s['profile_sha256'],mode='measured_default',expected_recommendation_sha256=rec_sha)
            _,applied=current();self.assertEqual(applied['profile'],rec['profile'])
            self.assertEqual(applied['measurement_operation_id'],'c'*32)
            # Explicit apply registers exactly the displayed recommendation, not
            # newer measurements that arrived after its calculation.
            self.assertEqual(applied['profile']['evidence']['operation_id'],'b'*32)

    def test_recalculation_requires_measurement_and_legacy_migration_never_recalculates(self):
        import json
        from twinpulse_app.robot_timing_store import RobotTimingStore
        from twinpulse_core.robot_timing_profile import recommendation
        with TemporaryDirectory() as directory:
            store=RobotTimingStore(Path(directory));rid='a'*32;binding='b'*64
            with self.assertRaisesRegex(ValueError,'TIMING_MEASUREMENT_REQUIRED'):store.recalculate(rid,binding)
            p=TimingAccumulator();p.observe('sensor_source_ms',50,1,'base');measurement=p.snapshot()
            initial=store.record(rid,binding,'c'*32,measurement,origin='test')
            legacy=dict(initial,recommendation=recommendation(measurement,rid,binding,'c'*32))
            for key in ('measurement_operation_id','measurement_sha256','recommendation_origin','recommendation_sha256'):legacy.pop(key,None)
            store._path(rid).write_text(json.dumps(legacy),encoding='utf-8')
            with patch('twinpulse_app.robot_timing_store.recommendation',side_effect=AssertionError('automatic recalculation')):
                saved=store.read(rid,binding)
            self.assertEqual(saved['profile'],initial['profile']);self.assertEqual(saved['recommendation_origin'],'LEGACY_AUTOMATIC')
            self.assertEqual(saved['measurement_operation_id'],'c'*32)
            self.assertEqual(saved['recommendation'],legacy['recommendation'])

    def test_robot_and_endpoint_isolation_and_corrupt_saved_data_rejection(self):
        with TemporaryDirectory() as directory:
            reg=RobotRegistry(Path(directory));a=reg.register(label='a',adapter_id='unreviewed',adapter_version='unreviewed-1.0',endpoint=RobotEndpoint('a.local','u'),expected_revision=0)
            b=reg.register(label='b',adapter_id='unreviewed',adapter_version='unreviewed-1.0',endpoint=RobotEndpoint('b.local','u'),expected_revision=1)
            rows=reg.snapshot()['robots'];v=dict(DEFAULTS,input_ttl_ms=300)
            reg.timing_action(a['id'],expected_revision=2,expected_sha256=rows[0]['timing_settings']['profile_sha256'],values=v,mode='custom')
            current=reg.snapshot()['robots'];self.assertEqual(current[0]['timing_settings']['profile']['values']['input_ttl_ms'],300)
            self.assertEqual(current[1]['timing_settings']['profile']['values']['input_ttl_ms'],350)
            with self.assertRaisesRegex(ValueError,'TIMING_BINDING_CHANGED'):
                reg.record_timing_measurement(a['id'],'f'*64,'c'*32,TimingAccumulator().snapshot())

if __name__=='__main__':unittest.main()
