# SPDX-License-Identifier: Apache-2.0
"""Offline logging regressions, not Isaac or physical execution evidence."""
from copy import deepcopy
import unittest
from tests.integration.test_robot_fleet import FleetTests
from twinpulse_core.fleet_diagnostics import checked_work,checked_fault
import json
import hashlib
from unittest.mock import patch
from unittest.mock import Mock


def probe_host(elapsed):
    """Use the actual engine producer, including its optional slow resources."""
    from scripts.twinpulse_update_probe import UpdateProbe
    probe=UpdateProbe()
    try:
        probe._memory=Mock(side_effect=[dict(page_fault_count=10,available_ram_mib=650.,
            process_private_mib=7221.,process_working_set_mib=1646.),
            dict(page_fault_count=30,available_ram_mib=601.,process_private_mib=7222.,process_working_set_mib=1210.),{}])
        probe.begin()
        return dict(app_update_s=elapsed,previous_tail_s=.01,previous_viewport_s=.02,**probe.finish(elapsed))
    finally:probe.close()


class DiagnosticsTests(unittest.TestCase):
    def test_actual_fast_and_slow_probe_host_roundtrip(self):
        for elapsed in (.02,.516):
            with self.subTest(elapsed=elapsed):
                work=dict(bounds_s=.001,model_authoring_s=0.,bounds_rebuilds=1,host=probe_host(elapsed))
                actual=checked_work(json.loads(json.dumps(work,allow_nan=False)))
                self.assertEqual(actual,work)
                self.assertIn('thread_cpu_s',actual['host']);self.assertIn('process_cpu_s',actual['host'])
                if elapsed>=.25:
                    self.assertEqual(actual['host']['before_resources']['available_ram_mib'],650.)
                    self.assertEqual(actual['host']['available_ram_mib'],601.)
                    self.assertEqual(actual['host']['page_fault_delta'],20)
                    work['host']['before_resources']['available_ram_mib']=999.
                    self.assertEqual(actual['host']['before_resources']['available_ram_mib'],650.)
                else:self.assertNotIn('before_resources',actual['host'])

    def test_probe_resources_reject_unknown_malformed_and_nonfinite_without_throwing(self):
        work=dict(bounds_s=0.,model_authoring_s=0.,bounds_rebuilds=0,host=probe_host(.516))
        self.assertIsNotNone(checked_work(work))
        for invalid in (None,[],1,{'unreviewed':1},{'available_ram_mib':float('nan')},
                {'process_private_mib':float('inf')},{'process_working_set_mib':-1},
                {'available_ram_mib':True},{'available_ram_mib':10**1000}):
            with self.subTest(invalid_type=type(invalid).__name__):
                self.assertIsNone(checked_work({**work,'host':{**work['host'],'before_resources':invalid}}))
        for key in ('thread_cpu_s','process_cpu_s','process_working_set_mib'):
            for invalid in (True,-1,float('nan'),float('inf'),10**1000,[],None):
                self.assertIsNone(checked_work({**work,'host':{**work['host'],key:invalid}}))
        fault=dict(schema='fleet-first-fault-1.0',reason='ISAAC_UPDATE_STALLED',observed_monotonic_s=10.,
            observed_at_ms=10000.,elapsed_s=.516,current_work=work,previous_work=deepcopy(work),motion_epoch='epoch',task_id='original')
        self.assertEqual(checked_fault(fault),fault)
        fault['previous_work']['host']['before_resources']['unknown']=0
        self.assertIsNone(checked_fault(fault))
    def test_chunked_operation_encoding_keeps_original_digest_and_bytes(self):
        from twinpulse_app.fleet_recorder import materialize_operation,operation_json_bytes
        record=dict(schema_version='robot-operation-1.0',events=[{'unicode':'한글','points':[[.1,.2]]}]*2000,manifest={})
        expected=hashlib.sha256(json.dumps(record['events'],sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
        with patch('twinpulse_app.fleet_recorder.json.dumps',side_effect=AssertionError('monolithic history encoding')):
            self.assertEqual(materialize_operation(record)['manifest']['events_sha256'],expected)
            actual=operation_json_bytes(record,separators=(',',':'))
        self.assertEqual(actual,json.dumps(record,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode())
    def test_legacy_and_current_work_are_retained_but_unknown_fields_rejected(self):
        work=dict(bounds_s=.001,model_authoring_s=0.,bounds_rebuilds=2)
        self.assertEqual(checked_work(work),work)
        work.update(scan_s=.012,scan_error=None,update_s=.015,navigation_s=.001,
                    host=dict(app_update_s=.02,previous_tail_s=.005,previous_viewport_s=.016))
        self.assertEqual(checked_work(work),work)
        for bad in ({**work,'scan_s':float('nan')},{**work,'scan_error':'x'*161},
                    {**work,'host':{'unknown':.1}},{**work,'unbounded':[]}):
            self.assertIsNone(checked_work(bad))

    def test_first_fault_is_bounded_and_copy_does_not_change(self):
        work=dict(bounds_s=0.,model_authoring_s=0.,bounds_rebuilds=1)
        fault=dict(schema='fleet-first-fault-1.0',reason='ISAAC_UPDATE_STALLED',
            observed_monotonic_s=10.,observed_at_ms=10000.,elapsed_s=.72,
            current_work=work,previous_work=None,motion_epoch='epoch',task_id='request')
        copy=checked_fault(fault);work['bounds_s']=8.
        self.assertEqual(copy['current_work']['bounds_s'],0.)
        self.assertIsNone(checked_fault({**fault,'elapsed_s':float('inf')}))


class FleetFaultRecordingTests(unittest.TestCase):
    setUp=FleetTests.setUp
    tearDown=FleetTests.tearDown
    send=FleetTests.send
    register=FleetTests.register
    report=FleetTests.report
    connected=FleetTests.connected

    def test_operation_read_never_schedules_another_disk_snapshot(self):
        robot=self.connected();identity=self.fleet.robots[robot]['operation_id']
        with patch.object(self.fleet.snapshot_writer,'submit',side_effect=AssertionError('GET scheduled a snapshot')):
            result=self.fleet.operation(identity)
        self.assertEqual(result['operation_id'],identity)
        self.assertEqual(result['manifest']['event_count'],len(result['events']))

    def test_motion_result_retains_scan_work_and_original_gap_not_latest_dt(self):
        identity=self.connected();row=self.fleet.robots[identity]
        work=dict(bounds_s=.001,model_authoring_s=0.,bounds_rebuilds=2,scan_s=.025,scan_error=None,host=probe_host(.516))
        fault=dict(schema='fleet-first-fault-1.0',reason='ISAAC_UPDATE_STALLED',
            observed_monotonic_s=10.,observed_at_ms=10000.,elapsed_s=.72,
            current_work=deepcopy(work),previous_work=None,motion_epoch=row['motion_epoch'],task_id=None)
        self.report(identity,reason='ISAAC_UPDATE_STALLED',runtime_timing=dict(elapsed_s=.032,integrated_s=0.,substeps=0),
                    runtime_work=work,runtime_fault=fault)
        event=next(e for e in self.fleet.operations[row['operation_id']]['events'] if e['kind']=='motion_result')
        self.assertEqual(event['runtime_fault']['elapsed_s'],.72)
        self.assertEqual(event['runtime_timing']['elapsed_s'],.032)
        self.assertEqual(event['runtime_work'],work)
        exported=json.loads(json.dumps(self.fleet.operation(row['operation_id'])))
        saved=next(e for e in exported['events'] if e['kind']=='motion_result')
        self.assertEqual(saved['runtime_fault']['current_work'],work)
        self.assertEqual(saved['runtime_work']['host']['before_resources']['available_ram_mib'],650.)
        self.assertEqual(saved['runtime_work']['host']['available_ram_mib'],601.)


if __name__=='__main__':unittest.main()
