# SPDX-License-Identifier: Apache-2.0
"""Read original SHA-bound powered data; export local timing import/report only."""
import base64
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'packages/twinpulse_core/src'))
from twinpulse_core.robot_timing_profile import TimingAccumulator,recommendation,digest
OUT=ROOT/'outputs/robot-timing-settings-20261020'


def analyze(directory):
    operation=json.loads((directory/'operation.json').read_text(encoding='utf-8'))
    receipt=json.loads((directory/'raw/receipt.json').read_text(encoding='utf-8'))
    probe=TimingAccumulator();seen=set();prior_raw={};prior_window={};prior_publication={};load='base';sources=[];faults={}
    for segment in receipt['segments']:
        path=directory/'raw'/segment['path'];raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=segment['sha256']:raise ValueError('SOURCE_SHA_CHANGED')
        sources.append(dict(path=str(path),bytes=len(raw),sha256=segment['sha256']))
        for line in raw.splitlines():
            e=json.loads(line);d=e.get('data',{});at=e.get('robot_monotonic_s');kind=e.get('kind')
            if type(at) not in (int,float):continue
            if kind=='heartbeat':
                field=d.get('field') or {};tracking=field.get('tracking') or {}
                load=('tracking_recording' if d.get('lidar_state')=='STREAMING' and tracking.get('status')=='ESTIMATED'
                      else 'lidar' if d.get('lidar_state')=='STREAMING' else 'base')
                diag=d.get('telemetry_diagnostic') or {};checked=diag.get('checked_monotonic_s')
                if checked is not None and ('diag',checked) not in seen:
                    seen.add(('diag',checked))
                    for name,key in [('sensor_source_ms','source_age_s'),('sensor_receipt_ms','sensor_receipt_age_s'),('guard_receipt_ms','guard_receipt_age_s')]:
                        if type(diag.get(key)) in (int,float):probe.observe(name,diag[key]*1000,checked,load)
                n=field.get('native_observation') or {};seq=(n.get('stream_id'),n.get('frame_sequence'))
                if n and ('native',seq) not in seen:
                    seen.add(('native',seq))
                    if type(n.get('receipt_age_s')) in (int,float):probe.observe('native_receipt_ms',n['receipt_age_s']*1000,at,load)
            if kind=='raw' and d.get('source')=='serialized_ros_message':
                topic=d.get('topic');stream=d.get('stream_id');callback=d.get('callback_timing') or {}
                # Verify every raw CDR chunk used for source-clock statistics.
                payload=base64.b64decode(d['base64'],validate=True)
                if hashlib.sha256(payload).hexdigest()!=d['sha256']:raise ValueError('CDR_SHA_CHANGED')
                stamp=callback.get('source_stamp_ns');received=d.get('receipt_start_s')
                key=(stream,topic);previous=prior_raw.get(key)
                if previous is not None:
                    if topic=='sensor_state':probe.observe('wheel_interval_ms',(received-previous[0])*1000,at,load)
                    if topic=='odom' and type(stamp) is int and type(previous[1]) is int:
                        probe.observe('odom_interval_ms',(stamp-previous[1])/1e6,at,load)
                prior_raw[key]=(received,stamp)
            if kind=='command' and d.get('action')=='input_window':
                generation=d.get('motion_generation');issued=d.get('issued_s')
                if type(issued) in (int,float):
                    if generation in prior_window:probe.observe('input_window_interval_ms',(issued-prior_window[generation])*1000,at,load)
                    prior_window[generation]=issued
            if kind=='command' and d.get('status')=='PUBLISHED' and type(d.get('source_created_s')) in (int,float):
                source=d['source_created_s'];key=(d.get('request_id'),d.get('applied_motion_epoch'))
                probe.observe('input_age_ms',(at-source)*1000,at,load)
                if key in prior_publication:probe.observe('output_pressure_ms',(at-prior_publication[key])*1000,at,load)
                prior_publication[key]=source
            if kind=='control_pause':faults[d.get('reason','UNKNOWN')]=faults.get(d.get('reason','UNKNOWN'),0)+1
    m=probe.snapshot();rid=operation['robot_id'];binding=operation['manifest']['binding_sha256'];op=operation['operation_id']
    rec=recommendation(m,rid,binding,op)
    exported=dict(schema_version='robot-timing-import-1.0',robot_id=rid,binding_sha256=binding,operation_id=op,
        measurement=m,measurement_sha256=digest(m),origin='IMPORTED_RECORDED_TIMING_NOT_LIVE_AUTHENTICATION')
    return dict(import_report=exported,recommendation=rec,sources=sources,original_failures=faults,
        raw_integrity=receipt.get('complete'),historical_outcomes_unchanged=True)


if __name__=='__main__':
    OUT.mkdir(exist_ok=True)
    result=analyze(ROOT/'outputs/robot-powered-20261020-current07')
    (OUT/'original-analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'recorded-measurement-import.json').write_text(json.dumps(result['import_report'],ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(values=result['recommendation']['profile']['values'],coverage=result['recommendation']['coverage'],
        metrics=result['import_report']['measurement']['metrics'],sources=len(result['sources'])),ensure_ascii=False))
