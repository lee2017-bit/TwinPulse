# SPDX-License-Identifier: Apache-2.0
"""Pure serializer equivalence; not App/device acceptance."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

SOURCE=Path(__file__).resolve().parents[2]/'packages/twinpulse_app/src/twinpulse_app/fleet_recorder.py'
spec=importlib.util.spec_from_file_location('fleet_encoding_test',SOURCE)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class SnapshotEncodingTests(unittest.TestCase):
    def test_wire_and_hash_identical_for_empty_nested_unicode_and_numeric_events(self):
        for events in ([],[{}],[dict(z='한국어 🦊',a=[None,True,False,-0.,1e-12,1e20],nested={'2':2,'1':'escaped\\\"\n'})]*65):
            for separators in (None,(',',':')):
                with self.subTest(count=len(events),separators=separators):
                    row=dict(operation_id='id',events=deepcopy(events),manifest=dict(complete=False),tail='z')
                    digest=hashlib.sha256(json.dumps(events,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
                    module.materialize_operation(row)
                    self.assertEqual(row['manifest']['events_sha256'],digest)
                    self.assertEqual(module.operation_json_bytes(row,separators=separators),json.dumps(row,ensure_ascii=False,allow_nan=False,separators=separators).encode())

    def test_each_new_snapshot_reencodes_mutated_values_without_identity_cache(self):
        event=dict(value=1);row=dict(events=[event],manifest={})
        first=module.materialize_operation(row)['manifest']['events_sha256'];wire=module.operation_json_bytes(row)
        event['value']=2
        self.assertNotEqual(module.materialize_operation(row)['manifest']['events_sha256'],first)
        self.assertNotEqual(module.operation_json_bytes(row),wire)

    def test_nan_and_nonserializable_values_still_raise(self):
        for value in (float('nan'),float('inf'),object()):
            for call in (module.materialize_operation,module.operation_json_bytes):
                with self.assertRaises((ValueError,TypeError)):call(dict(events=[dict(value=value)],manifest={}))

    def test_batch_yields_without_changing_sleep_or_gc_global_policy(self):
        with patch.object(module.time,'sleep') as sleep:
            list(module._event_json_parts([{}]*65,json.JSONEncoder()))
        self.assertEqual(sleep.call_args_list,[((0,),),((0,),)])

    def test_nonoperation_fallback_and_top_level_order(self):
        for row in ([1,{'a':2}],{1:'number key'},dict(events=[],manifest={}),dict(manifest={},events=[]),dict(first=1,events=[],last=2),dict(manifest={},events=[{'b':2,'a':1}],first=3)):
            self.assertEqual(module.operation_json_bytes(row),json.dumps(row,ensure_ascii=False,allow_nan=False).encode())

    def test_c_encoder_never_receives_entire_history_or_outer_record(self):
        events=[dict(index=i) for i in range(65)];row=dict(events=events,manifest={});seen=[]
        original=json.JSONEncoder.encode
        def observe(encoder,value):
            self.assertIsNot(value,events);self.assertIsNot(value,row)
            if any(value is event for event in events):seen.append(value)
            return original(encoder,value)
        with patch.object(json.JSONEncoder,'encode',observe):
            module.materialize_operation(row);module.operation_json_bytes(row)
        self.assertEqual(len(seen),130)

    def test_large_single_event_remains_exact_not_a_claim_of_latency_bound(self):
        row=dict(events=[dict(text='한글'*200000,values=list(range(10000)))],manifest={})
        module.materialize_operation(row)
        self.assertEqual(module.operation_json_bytes(row),json.dumps(row,ensure_ascii=False,allow_nan=False).encode())

    def test_circular_value_sticky_failure_does_not_replace_existing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'operation.json';path.write_bytes(b'protected original')
            event={};event['cycle']=event
            writer=module.FleetSnapshotWriter()
            writer.submit(path,dict(events=[event],manifest={}),estimated_bytes=1024)
            until=time.monotonic()+1
            while not writer.error and time.monotonic()<until:time.sleep(.001)
            receipt=writer.close()
            self.assertFalse(receipt['complete']);self.assertEqual(receipt['error'],'SNAPSHOT_WRITE_FAILED')
            self.assertEqual(path.read_bytes(),b'protected original')

if __name__=='__main__':unittest.main()
