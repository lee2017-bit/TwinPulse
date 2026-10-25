# SPDX-License-Identifier: Apache-2.0
"""Hash-bind actual current-install evidence. Missing journeys stay missing."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/robot-continuous-repair-20261021'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def ref(p):return dict(path=p.relative_to(OUT).as_posix(),sha256=sha256(p.read_bytes()).hexdigest())
def write(p,v):
    with p.open('x',encoding='utf-8') as f:json.dump(v,f,ensure_ascii=False,indent=2)

def main():
    global OUT
    parser=argparse.ArgumentParser();parser.add_argument('--attempt',required=True)
    parser.add_argument('--review',type=Path,required=True);parser.add_argument('--budget',type=Path,required=True)
    parser.add_argument('--output-root',type=Path,default=OUT)
    parser.add_argument('--supplementary',type=Path)
    parser.add_argument('--normal-tag',help='Explicit already-recorded normal/restart tag on the same installed release')
    args=parser.parse_args();a=args.attempt
    OUT=args.output_root.resolve()
    if len(a)!=2 or not a.isascii() or not a.isdecimal():raise ValueError('TWO_DIGIT_ATTEMPT_REQUIRED')
    normal_tag=args.normal_tag or a
    if len(normal_tag)!=2 or not normal_tag.isascii() or not normal_tag.isdecimal():raise ValueError('TWO_DIGIT_NORMAL_TAG_REQUIRED')
    active=read(Path(os.environ['LOCALAPPDATA'])/'TwinPulse/installed/active-release.json')
    release,source=active['release_id'],active['source_manifest_sha256']
    roles=dict(fresh=OUT/f'ui-{a}/result.json',cold=OUT/f'ui-cold-{a}/result.json',
        lineage=OUT/f'lineage-{a}/result.json',lineage_cold=OUT/f'lineage-cold-{a}/result.json',
        normal=OUT/f'normal{normal_tag}/result.json',installation=OUT/f'installed-files{a}.json',
        supplementary=OUT/f'supplementary{a}/result.json',budget=args.budget.resolve())
    if args.supplementary:roles['supplementary']=args.supplementary.resolve()
    restart=OUT/f'normal{normal_tag}-restart/result.json';shutdown=OUT/f'normal{normal_tag}/shutdown.json';again=OUT/f'normal{normal_tag}-restart/shutdown.json'
    if all(p.is_file() for p in (roles['normal'],restart,shutdown,again)):
        n,r,s,t=[read(p) for p in (roles['normal'],restart,shutdown,again)]
        consistent=all(v.get('release_id')==release and v.get('source_sha256')==source for v in (n,r,s,t))
        lifecycle=dict(status='PASS' if consistent and s['shutdown_clean'] and t['shutdown_clean'] and r['status']=='PASS_NORMAL_START_REUSE_DEBUG_OFF' else 'FAIL',
            release_id=release,source_sha256=source,normal_start_launch_id=n['launch_id'],restart_launch_id=r['launch_id'],
            shutdown_clean=s['shutdown_clean'],restart_shutdown_clean=t['shutdown_clean'],
            restart_ready=r['status']=='PASS_NORMAL_START_REUSE_DEBUG_OFF',
            restart_authenticated_ready=r['status']=='PASS_NORMAL_START_REUSE_DEBUG_OFF',
            authenticated_ready_basis='Actual supervisor authenticated Isaac stage; not a claim of full native pointer or Explorer acceptance',
            restart_ready_wait_ms=r['ready_wait_ms'],restart_debug_listener_count=r['debug_listener_count'],restart_app_listener_count=r['app_listener_count'],
            references=[ref(p) for p in (roles['normal'],restart,shutdown,again)])
        roles['lifecycle']=OUT/f'normal-lifecycle{a}.json';write(roles['lifecycle'],lifecycle)
    review=read(args.review.resolve())
    # Do not let a per-UI PASS hide a failed wrapper shutdown observation.
    for branch in ('fresh','cold','lineage','history'):
        p=OUT/f'cleanup-{branch}-{a}.json'
        if not p.is_file() or read(p).get('status')!='PASS':
            review['unresolved'].append('FINAL_'+branch.upper()+'_SHUTDOWN_NOT_CONFIRMED')
    if review['unresolved']:review['status']='KNOWN_BLOCKER'
    manifest=dict(release_id=release,source_sha256=source,physical_readiness_review=review,
        evidence=[dict(role=role,**ref(p)) for role,p in roles.items() if p.is_file()],
        acceptance_tools=[dict(path=str(p.relative_to(ROOT)),sha256=sha256(p.read_bytes()).hexdigest()) for p in (
            ROOT/'scripts/verify_robot_focused_journey.ps1',ROOT/'scripts/verify_robot_fleet_ui.mjs',ROOT/'scripts/verify_robot_lineage_ui.mjs',
            ROOT/'scripts/verify_robot_lineage_offline.py',ROOT/'scripts/verify_robot_focus_gate.py')])
    target=OUT/f'evidence-manifest{a}.json';write(target,manifest)
    gate=subprocess.run([sys.executable,str(ROOT/'scripts/verify_robot_focus_gate.py'),'--manifest',str(target),'--output',str(OUT/f'gate-result{a}.json')],cwd=ROOT,capture_output=True,text=True)
    (OUT/f'gate-run{a}.log').write_text(gate.stdout+gate.stderr,encoding='utf-8')
    value=read(OUT/f'gate-result{a}.json')
    original=OUT/'ui-03/result.json'
    if original.is_file():
        negative=deepcopy(manifest)
        negative['classification']='NEGATIVE_ORIGINAL_FAILED_UI03_NOT_NEW_ACCEPTANCE'
        for entry in negative['evidence']:
            if entry['role']=='fresh':entry.update(ref(original))
        target_negative=OUT/f'gate-negative-original03-manifest{a}.json';write(target_negative,negative)
        run=subprocess.run([sys.executable,str(ROOT/'scripts/verify_robot_focus_gate.py'),'--manifest',str(target_negative),
            '--output',str(OUT/f'gate-negative-original03-result{a}.json')],cwd=ROOT,capture_output=True,text=True)
        (OUT/f'gate-negative-original03-run{a}.log').write_text(run.stdout+run.stderr,encoding='utf-8')
        rejected=read(OUT/f'gate-negative-original03-result{a}.json')
        if run.returncode!=1 or 'RUN_NOT_PASS:fresh' not in rejected['issues']:raise ValueError('ORIGINAL_FAILURE_NOT_REJECTED')
    print(json.dumps(dict(status=value['status'],issues=value['issues'],manifest=str(target))))
    return gate.returncode
if __name__=='__main__':raise SystemExit(main())
