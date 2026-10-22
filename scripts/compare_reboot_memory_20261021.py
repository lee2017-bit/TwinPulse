# SPDX-License-Identifier: Apache-2.0
"""Offline matched-reboot projection. No App/provider/hardware operations."""
from hashlib import sha256
import json
from pathlib import Path
from statistics import median

from report_continuous_repair_20261021 import memory_components

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/robot-continuous-repair-20261021'
TARGET='Actual main-chat nearest chair destination reaches scene-derived approach with visible receipt'


def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def ref(path):return dict(path=path.relative_to(OUT).as_posix(),sha256=sha256(path.read_bytes()).hexdigest())
def stats(values):return dict(min=min(values),median=median(values),max=max(values)) if values else None


def exact_window(attempt,folder):
    ui=read(OUT/f'ui-reproduction-{attempt}/result.json')
    step=next((s for s in ui['steps'] if s['name']==TARGET),None)
    starts=[]
    for line in (OUT/f'reproduction{attempt}.log').read_text(encoding='utf-8-sig',errors='replace').splitlines():
        try:value=json.loads(line)
        except ValueError:continue
        if isinstance(value,dict) and value.get('ui_step')==TARGET:starts.append(value['at'])
    if not step or len(starts)!=1:return dict(status='NOT_RUN_OR_WINDOW_UNAVAILABLE',whole_status=ui['status'])
    begin=starts[0];end=begin+step['elapsed_ms'];systems=[];before=None;after=None;first=None;last=None
    for line in (folder/'samples.jsonl').open(encoding='utf-8'):
        row=json.loads(line)
        if begin<=row['at_ms']<=end:systems.append(row)
        if 'processes' in row:
            if row['at_ms']<=begin:before=row
            if row['at_ms']>=end and after is None:after=row
        if begin<=row['at_ms']<=end and 'processes' in row:first=first or row;last=row
    return dict(status=step['status'],whole_status=ui['status'],start_ms=begin,end_ms=end,elapsed_ms=step['elapsed_ms'],
        system_samples=len(systems),system={key:stats([r['system'][key] for r in systems]) for key in (
            'PhysicalAvailable_bytes','CommitTotal_bytes','KernelPaged_bytes','KernelNonpaged_bytes')},
        process_first_inside=memory_components(first) if first else None,process_last_inside=memory_components(last) if last else None,
        process_before=memory_components(before) if before and begin-before['at_ms']<=6000 else None,
        process_after=memory_components(after) if after and after['at_ms']-end<=6000 else None,
        limits='Exact UI start+elapsed window only; excluded post-failure idle. Bracketing5s process snapshots are separately labelled, not the exact failed516ms CPU interval.')


def main():
    comparison=read(OUT/'memory-reboot-traces29-30.json')
    issues=comparison['reboot_comparison']['issues']
    before=read(OUT/'memory-after-failure29-stage.json');after=read(OUT/'memory-after-reboot30-before-stage.json')
    if before['last_boot']==after['last_boot']:issues.append('STAGE_BOOT_TIME_DID_NOT_CHANGE')
    files=read(OUT/'installed-files30.json')
    if files['status']!='PASS' or files['source_manifest_sha256']!='77b57c4346316db99bebc616bb82ca9b42ec47b72b5304f28fb1ee1af74372d6':issues.append('FROZEN23_INSTALLATION_MISMATCH')
    def stage(v):
        dwm=next((p for p in v['processes'] if p['name']=='dwm'),None)
        return dict(at_utc=v['at_utc'],last_boot=v['last_boot'],memory=v['memory'],dwm=dwm,
            top_processes_by_commit=sorted(v['processes'],key=lambda p:p.get('private_committed_bytes') or 0,reverse=True)[:20],
            gpu_adapters=v['gpu_adapters'],sampler_wall_ms=v['sampler_wall_ms'],errors=v['errors'])
    value=dict(schema='matched-reboot-memory-1.0',status='COMPARISON_REVIEW_REQUIRED' if issues else 'MATCHED_SAME_SOURCE_REBOOT_OBSERVED_NOT_SOLE_CAUSE_PROOF',issues=issues,
        before_reboot_app_closed=stage(before),after_reboot_app_not_started=stage(after),
        closed_to_closed_counter_delta={k:after['memory'][k]-before['memory'][k] for k in (
            'AvailableMBytes','CommittedBytes','PoolPagedBytes','PoolNonpagedBytes')},
        original29_chair=exact_window('29',OUT/'memory-before-reboot29'),
        after30_chair=exact_window('30',OUT/'memory-after-reboot30'),
        references=[ref(OUT/p) for p in ('memory-reboot-traces29-30.json','memory-after-failure29-stage.json',
            'memory-after-reboot30-before-stage.json','memory-after-reboot30-after-stage.json','installed-files30.json',
            'ui-reproduction-29/result.json','ui-reproduction-30/result.json','runtime-final30/receipt.json')],
        limitations=[
            'Before and after closed-App stages have different background apps/process lifetimes and uptime; process basenames across boots are not the same PID identity.',
            'DWM private commit is not physical RAM. Shared process working sets/cache/GPU allocations cannot be summed as disjoint RAM.',
            'Lower DWM commit and kernel pools identify changed categories, not the particular allocator, driver or leaking function.',
            'A post-reboot PASS would support resource pressure as a candidate, not prove sole causality or permanent repair. A FAIL despite lower memory rules out reboot alone as a sufficient fix for this trial.',
            'The same frozen23 diagnostic allowlist bug remains intentionally unfixed during A/B; unknown exact failure CPU data cannot be reconstructed.',
            'Saved original25 geometry UI repetition, not fresh generation or exact initial robot-pose/time replay. Physical robot and final normal/restart acceptance remain separate.'])
    with (OUT/'memory-reboot-comparison30.json').open('x',encoding='utf-8') as stream:json.dump(value,stream,ensure_ascii=False,indent=2)
    print(json.dumps(dict(status=value['status'],issues=issues,before_chair=value['original29_chair']['status'],after_chair=value['after30_chair']['status'],delta=value['closed_to_closed_counter_delta'])))


if __name__=='__main__':main()
