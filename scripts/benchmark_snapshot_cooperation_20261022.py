# SPDX-License-Identifier: Apache-2.0
"""Saved-record CPU/scheduling probe only; not App, network or robot evidence."""
import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import threading
import time

def main():
    p=argparse.ArgumentParser();p.add_argument('--module',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();root=Path(__file__).resolve().parents[1]
    original=root/'outputs/robot-continuous-repair-20261021/failed-ui39-original-logs/10-ebe1a33b79d44a69841d63c88dd9dcf3.json'
    raw=original.read_bytes();record=json.loads(raw)
    spec=importlib.util.spec_from_file_location('snapshot_probe_module',args.module);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    rows=[]
    for i in range(5):
        value=deepcopy(record);ticks=[];stop=threading.Event()
        def heartbeat():
            while not stop.is_set():ticks.append(time.perf_counter());stop.wait(.005)
        peer=threading.Thread(target=heartbeat);peer.start();time.sleep(.02)
        start=time.perf_counter();cpu=time.process_time()
        try:
            materialized=module.materialize_operation(value);middle=time.perf_counter();output=module.operation_json_bytes(materialized)
            end=time.perf_counter();process=time.process_time()-cpu
        finally:stop.set();peer.join()
        ticks.append(end)
        reference=hashlib.sha256(json.dumps(record['events'],sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
        expected=deepcopy(record);expected['manifest'].update(event_count=len(expected['events']),events_sha256=reference)
        assert output==json.dumps(expected,ensure_ascii=False,allow_nan=False).encode()
        assert materialized['manifest']['events_sha256']==reference
        rows.append(dict(index=i,total_ms=(end-start)*1000,materialize_ms=(middle-start)*1000,encode_ms=(end-middle)*1000,
            process_cpu_s=process,maximum_peer_gap_ms=max(b-a for a,b in zip(ticks,ticks[1:]))*1000,
            bytes=len(output),output_sha256=hashlib.sha256(output).hexdigest(),events_sha256=reference))
    result=dict(scope='OFFLINE_SAVED_RECORD_CPU_AND_SCHEDULING_ONLY_NOT_ROOT_CAUSE_OR_UI_ACCEPTANCE',
        original_sha256=hashlib.sha256(raw).hexdigest(),module_sha256=hashlib.sha256(args.module.read_bytes()).hexdigest(),rows=rows)
    with args.output.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
    print(json.dumps(result))
if __name__=='__main__':main()
