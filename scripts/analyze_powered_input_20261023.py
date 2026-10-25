# SPDX-License-Identifier: Apache-2.0
"""Offline derivation of exact recorded command timing; never contacts a robot."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

parser=argparse.ArgumentParser()
parser.add_argument('directory',type=Path)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
root=args.directory.resolve()
receipt=json.loads((root/'receipt.json').read_text(encoding='utf-8'))
issues=[];kinds=Counter();rows=[];faults=[];audits=[];commands=[];pc=[];motion=[];windows=[]
safe_fields=('action','request_id','status','reason','motion_generation','sequence','source_created_s',
    'source_age_s','source_age_ms','issued_s','accepted_s','deadline_s','remaining_s','direction',
    'published_s','queue_received_s','queue_wait_s','received_s','elapsed_s','scope','execution_confirmed',
    'disposition','ui_age_ms','window_elapsed_ms','window_received_pc_monotonic_s',
    'checked_pc_monotonic_s','checked_pc_wall_ms','checked_wall_s','window_age_ms','deducted_overlap_ms',
    'original_expires_at_ms','expiry_ms','expires_at_ms','pc_queue_age_s','pc_sent_monotonic_s')
for segment in receipt['segments']:
    path=root/segment['path'];raw=path.read_bytes()
    if len(raw)!=segment['bytes'] or hashlib.sha256(raw).hexdigest()!=segment['sha256']:issues.append(path.name)
    lines=raw.splitlines()
    if len(lines)!=segment['events']:issues.append(path.name+':count')
    for n,line in enumerate(lines,1):
        row=json.loads(line);kind=row.get('kind') or row.get('schema');kinds[kind]+=1
        data=row.get('data') or row
        location=dict(file=path.name,line=n,sequence=row.get('sequence'),robot_s=row.get('robot_monotonic_s'),kind=kind)
        mini={k:data[k] for k in safe_fields if k in data}
        if data.get('action')=='drive':
            command=dict(location,**mini)
            if isinstance(data.get('payload'),dict):command['payload']={k:data['payload'][k] for k in safe_fields if k in data['payload']}
            for key in ('input_diagnostic','input_gate','admission','delivery','event_delivery'):
                if key in data:command[key]=data[key]
            commands.append(command)
        if row.get('schema')=='physical-live-pc-input-age-1.0' or data.get('schema')=='physical-live-pc-input-age-1.0':
            audits.append(dict(location,**mini,available_fields=list(data)))
        if kind=='physical-live-pc-input-disposition-1.0':pc.append(dict(location,**mini,available_fields=list(data)))
        if kind=='command' and data.get('action')=='input_window' and 390<row.get('robot_monotonic_s',0)<393:
            windows.append(dict(location,**mini))
        if kind=='control_pause' and data.get('reason')=='INPUT_DEADLINE_EXPIRED':
            faults.append(dict(location,input_diagnostic=data.get('input_diagnostic'),motion=data.get('motion_observation')))
        if kind=='motion_observation':motion.append(dict(location,**mini))
out=dict(schema='powered-input-offline-analysis-1.0',root=str(root),receipt_complete=receipt.get('complete'),
    accepted=receipt.get('accepted'),saved=receipt.get('saved'),bytes=receipt.get('bytes'),segments=len(receipt['segments']),
    original_byte_hash_count_issues=issues,kinds=dict(kinds),commands=commands,pc=pc,audits=audits,faults=faults,motion=motion,windows=windows)
with args.output.open('x',encoding='utf-8') as stream:json.dump(out,stream,indent=2,allow_nan=False)
print(json.dumps(dict(issues=issues,commands=commands,pc=pc,windows=windows),allow_nan=False))
