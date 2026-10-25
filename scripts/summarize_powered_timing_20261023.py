# SPDX-License-Identifier: Apache-2.0
"""Offline actual-timing summary; no device connection or control authority."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import statistics


def stats(values):
    values=sorted(values)
    if not values:return dict(n=0)
    return dict(n=len(values),mean_ms=statistics.mean(values),
                sample_std_ms=statistics.stdev(values) if len(values)>1 else None,
                p99_observed_ms=values[math.ceil(len(values)*.99)-1],max_ms=values[-1],min_ms=values[0])


parser=argparse.ArgumentParser()
parser.add_argument('session',type=Path)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
receipt=json.loads((args.session/'live-final/receipt.json').read_text(encoding='utf-8'))
issues=[];pauses=[];rejects=[];motions={};ages=[];kinds=Counter()
for segment in receipt['segments']:
    file=args.session/'live-final'/segment['path'];raw=file.read_bytes()
    if len(raw)!=segment['bytes'] or hashlib.sha256(raw).hexdigest()!=segment['sha256']:
        issues.append(file.name+':bytes_or_sha')
    lines=raw.splitlines()
    if len(lines)!=segment['events']:issues.append(file.name+':rows')
    for index,line in enumerate(lines,1):
        row=json.loads(line);kind=row.get('kind') or row.get('schema');data=row.get('data') or row
        kinds[kind]+=1
        ref=dict(file=file.name,line=index,robot_s=row.get('robot_monotonic_s'))
        if kind=='control_pause':
            pauses.append(dict(ref,reason=data.get('reason'),input_diagnostic=data.get('input_diagnostic')))
        observation=data.get('motion_observation')
        if isinstance(observation,dict) and observation.get('state')=='ENDED':
            motions[observation['request_id']]=dict(observation,original=ref)
        if kind=='command' and data.get('action')=='drive' and data.get('status')=='REJECTED':
            rejects.append(dict(ref,request_id=data.get('request_id'),reason=data.get('reason')))
        if kind=='motion_observation' and data.get('state')=='ENDED':
            motions[data['request_id']]=dict(data,original=ref)
        if kind=='physical-live-pc-input-age-1.0':
            ages.append(dict(ref,**{k:data[k] for k in ('request_id','ui_age_ms','source_age_ms',
                'deducted_overlap_ms','checked_wall_s') if k in data}))
native=json.loads((args.session/'native-network-receipts.json').read_text(encoding='utf-8'))
groups=defaultdict(list)
for row in native['requests']:
    if row.get('method')!='POST':continue
    end=row.get('native_finished_s') or row.get('native_response_s')
    if end is not None:groups[row.get('action') or 'unknown'].append((end-row['native_request_s'])*1000)
summary=dict(schema='powered-timing-offline-summary-1.0',
    scope='Actual source-clock/native-network observations; not a physical-motion or safety certificate',
    archive=dict(complete=receipt.get('complete'),accepted=receipt.get('accepted'),saved=receipt.get('saved'),
        bytes=receipt.get('bytes'),segments=len(receipt['segments']),issues=issues),
    motions=list(motions.values()),pauses=pauses,drive_rejections=rejects,
    native_request_response_ms={k:stats(v) for k,v in groups.items()},
    pc_input_ui_age_ms=stats([v['ui_age_ms'] for v in ages]),
    pc_wire_source_age_ms=stats([v['source_age_ms'] for v in ages]),
    exact_input_age_rows=ages,original_kind_counts=dict(kinds),
    limits='Correlated observations; empirical p99 is not a future bound. HTTP200 is not execution confirmation. Original failures remain failures.')
with args.output.open('x',encoding='utf-8') as handle:json.dump(summary,handle,indent=2,allow_nan=False)
print(json.dumps(dict(archive=summary['archive'],motions=len(motions),
    drive_rejections=len(rejects),non_operator_pauses=Counter(v['reason'] for v in pauses if v['reason']!='OPERATOR_STOP'),
    request_response=summary['native_request_response_ms'],pc_input_age=summary['pc_input_ui_age_ms'])))
