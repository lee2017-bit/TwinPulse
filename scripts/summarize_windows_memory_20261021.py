# SPDX-License-Identifier: Apache-2.0
"""Offline phase/role summary and optional matched-reboot comparison."""
import argparse
from collections import defaultdict
from hashlib import sha256
from html import escape
import json
from pathlib import Path
from statistics import median

FIELDS=('PhysicalAvailable_bytes','physical_in_use_bytes','CommitTotal_bytes','SystemCache_bytes','KernelPaged_bytes','KernelNonpaged_bytes')

def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def stats(values):
    return dict(min=min(values),median=median(values),max=max(values)) if values else None

def summarize(folder):
    meta=read(folder/'metadata.json');receipt=read(folder/'receipt.json');path=folder/'samples.jsonl'
    if sha256(path.read_bytes()).hexdigest()!=receipt['samples_sha256']:raise ValueError('MEMORY_TRACE_SHA_MISMATCH')
    phases=defaultdict(lambda:dict(samples=0,system=defaultdict(list),roles=defaultdict(lambda:defaultdict(list)),start_ms=None,end_ms=None))
    top={};overhead=[];launches={};last=None;first=None;all_rows=0
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            row=json.loads(line);all_rows+=1;first=first or row;last=row;overhead.append(row['sampler_wall_ms'])
            binding=row['binding'];step=(row.get('ui_step') or {}).get('name')
            phase=(step or 'STARTUP:'+str(binding.get('phase'))) if binding.get('launch_id') else 'POST_APP_CLOSED' if step else 'APP_CLOSED'
            if binding.get('launch_id'):launches[binding['launch_id']]=binding
            group=phases[phase];group['samples']+=1;group['start_ms']=group['start_ms'] or row['at_ms'];group['end_ms']=row['at_ms']
            for field in FIELDS:group['system'][field].append(row['system'][field])
            group['system']['actual_pagefile_used_bytes'].append(sum(p['TotalInUse_bytes'] for p in row['system'].get('pagefiles') or []))
            protected=row.get('protected_process_projection') or {};protected_rows={p['pid']:p for p in protected.get('rows',[]) if 0<=row['at_ms']-protected.get('at_ms',0)<=3000}
            if 'processes' in row:
                totals=defaultdict(lambda:defaultdict(int))
                for p in row['processes']:
                    extra=protected_rows.get(p['pid'],{});p=dict(p)
                    for k in ('working_set_bytes','private_committed_bytes'):
                        if p.get(k) is None and k in extra:p[k]=extra[k]
                    role=p.get('role','other');role='isaac_engine' if role.startswith('engine') or role.startswith('owner') and p['name'].lower()=='kit.exe' else 'twinpulse_backend' if role.startswith('backend') else 'twinpulse_host_electron' if role.startswith('owner') else 'windows_compression' if p['name'].lower()=='memory compression' else role
                    totals[role]['observed_processes']+=1
                    for field in ('working_set_bytes','private_working_set_bytes','private_committed_bytes'):
                        if p.get(field) is not None:totals[role][field]+=p[field]
                        else:totals[role][field+'_unavailable_processes']+=1
                    identity=str(p['pid'])+':'+str(p.get('created_unix_ms'))
                    prior=top.get(identity,dict(pid=p['pid'],name=p['name'],created_unix_ms=p.get('created_unix_ms'),role=role,first_seen_ms=row['at_ms'],peak_working_set_bytes=None,peak_private_committed_bytes=None))
                    for field in ('working_set_bytes','private_committed_bytes'):
                        if p.get(field) is not None:prior['peak_'+field]=max(prior.get('peak_'+field) or 0,p[field])
                    prior.update(role=role,last_seen_ms=row['at_ms'],last_working_set_bytes=p.get('working_set_bytes'),last_private_committed_bytes=p.get('private_committed_bytes'));top[identity]=prior
                for role,values in totals.items():
                    for field,value in values.items():group['roles'][role][field].append(value)
    data={name:dict(samples=g['samples'],start_ms=g['start_ms'],end_ms=g['end_ms'],system={k:stats(v) for k,v in g['system'].items()},
        roles={role:{k:stats(v) for k,v in values.items()} for role,values in g['roles'].items()}) for name,g in phases.items()}
    return dict(schema='windows-memory-summary-1.0',classification='OBSERVED_COUNTER_ATTRIBUTION_NOT_PROOF_OF_SINGLE_CAUSE',folder=str(folder),metadata=meta,receipt=receipt,
        rows=all_rows,first_at_ms=first['at_ms'] if first else None,last_at_ms=last['at_ms'] if last else None,first_system=first['system'] if first else None,last_system=last['system'] if last else None,phases=data,launches=launches,
        sampler_wall_ms=stats(overhead),top_processes_by_peak_commit=sorted(top.values(),key=lambda p:p.get('peak_private_committed_bytes') or 0,reverse=True)[:35],
        role_projection_note='Startup may precede component PID publication. Proven owner-descendant kit.exe is derived as Isaac, not Electron; original rows remain unchanged. Protected DWM values come from the same-PID timestamped .NET projection; no control ownership is inferred.',
        limits=['Per-process all-system samples every5s; system/DWM projection every1s. Peaks between samples may be missed; original Kit phase diagnostics give separate failure-bound resources.',
            'Working-set sums share pages, cache overlaps availability, private commit is not physical RAM. Missing counters are recorded, not zero-filled evidence.',
            'Boot reset and lower memory identify allocation categories, not necessarily a leaking driver/function. Basename aggregates are not process identity across reboots.'])

def comparison(before,after):
    issues=[]
    for k in ('source_sha256','collector_sources','windows_version','test_contract_sha256'):
        if before['metadata'].get(k)!=after['metadata'].get(k):issues.append('RECORDER_OR_WORKLOAD_CHANGED:'+k)
    if before['metadata']['start_binding']!=after['metadata']['start_binding']:issues.append('START_BINDING_CHANGED_CHECK_RELEASE_AND_NO_ACTIVE_SESSION')
    if (not before['first_system'] or not after['first_system'] or after['first_system']['uptime_ms']>=before['last_system']['uptime_ms']
            or after['first_at_ms']<=before['last_at_ms']):issues.append('LATER_REBOOT_NOT_OBSERVED')
    pairs={}
    for name,a in before['phases'].items():
        b=after['phases'].get(name)
        if not b:continue
        pairs[name]=dict(before_samples=a['samples'],after_samples=b['samples'],system_median_after_minus_before={k:b['system'][k]['median']-a['system'][k]['median'] for k in a['system'] if a['system'][k] and b['system'].get(k)})
    return dict(status='COMPARISON_REVIEW_REQUIRED' if issues else 'MATCHED_COUNTER_COMPARISON_NOT_CAUSAL_PROOF',issues=issues,matched_phases=pairs,
        limits='Use the identical frozen release, test scenario and recording mode. Boot/driver/background-process changes and fresh model variability still confound causal attribution. Do not call same-boot repetition a reboot comparison.')

def main():
    p=argparse.ArgumentParser();p.add_argument('--before',type=Path,required=True);p.add_argument('--after',type=Path);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    if args.output.exists():raise ValueError('NEW_SUMMARY_REQUIRED')
    value=dict(before=summarize(args.before.resolve()),after=summarize(args.after.resolve()) if args.after else None,
        reboot_comparison='NOT_RUN_NO_AFTER_REBOOT_TRACE')
    if value['after']:value['reboot_comparison']=comparison(value['before'],value['after'])
    args.output.write_text(json.dumps(value,indent=2),encoding='utf-8')
    html='<!doctype html><meta charset="utf-8"><title>TwinPulse memory comparison</title><style>body{font:16px system-ui;max-width:1200px;margin:24px auto;padding:20px}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><h1>재부팅 전후 메모리 비교</h1><p>재부팅 후 자료가 없으면 비교 미실행입니다. 수치 감소만으로 단독 누수 원인을 확정하지 않습니다.</p><pre>'+escape(json.dumps(value,ensure_ascii=False,indent=2))+'</pre>'
    args.output.with_suffix('.html').write_text(html,encoding='utf-8')
    print(json.dumps(dict(status='SUMMARY_ONLY' if not args.after else value['reboot_comparison']['status'],rows=value['before']['rows'],phases=len(value['before']['phases']),summary=str(args.output))))

if __name__=='__main__':main()
