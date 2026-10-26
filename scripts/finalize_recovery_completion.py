# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only verification plus generated local evidence; never controls a robot/App."""
import argparse
from datetime import datetime,timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from verify_robot_lineage_offline import source_receipt

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();root=a.output.resolve()
    def read(name):return json.loads((root/name).read_text(encoding='utf-8-sig'))
    def save(name,value):
        with (root/name).open('x',encoding='utf-8') as stream:json.dump(value,stream,ensure_ascii=False,indent=2)
    identity=source_receipt();normal=read('normal-02/result.json');restart=read('normal-restart-02/result.json')
    closed=read('normal-02/shutdown.json');closed2=read('normal-restart-02/shutdown.json');auth=read('normal-authentication.json')
    lifecycle=dict(status='PASS' if all([closed['shutdown_clean'],closed2['shutdown_clean'],auth['restart_authenticated_ready']]) else 'FAIL',**identity,
        normal_start_launch_id=normal['launch_id'],shutdown_clean=closed['shutdown_clean'],restart_ready=restart['status']=='PASS_NORMAL_START_REUSE_DEBUG_OFF',
        restart_launch_id=restart['launch_id'],restart_debug_listener_count=restart['debug_listener_count'],restart_app_listener_count=restart['app_listener_count'],
        restart_authenticated_ready=auth['restart_authenticated_ready'],restart_ready_wait_ms=restart['ready_wait_ms'],restart_shutdown_clean=closed2['shutdown_clean'],
        input_receipt='native-input-receipts.json',normal=normal,restart=restart,shutdown=closed,restart_shutdown=closed2)
    save('normal-lifecycle.json',lifecycle)
    roles=dict(fresh='ui-fresh-02/result.json',cold='ui-cold-02/result.json',lineage='lineage-02/result.json',lineage_cold='lineage-cold-02b/result.json',
        normal='normal-02/result.json',lifecycle='normal-lifecycle.json',installation='installation-final.json',supplementary='offline-final02/result.json',budget='budget-final.json')
    def entry(role,name):return dict(role=role,path=name,sha256=sha256((root/name).read_bytes()).hexdigest())
    evidence=[entry(role,name) for role,name in roles.items()]
    review=dict(schema='physical-readiness-review-1.0',status='NOT_READY',
        unresolved=['ORIGINAL_201_UNKNOWN_CONTROL_SPANS_AND_202_INCOMPLETE_RINGS','ACTUAL_PI_ROS_SOURCE_AGE_AND_TRACKER_LOAD_NOT_RETESTED','PHYSICAL_MOTION_STOPPING_LOCALIZATION_NOT_RUN_ROBOT_OFF'],
        evidence=[dict(path=name,sha256=sha256((root/name).read_bytes()).hexdigest()) for name in ('astra-review.json','ablation-current.json')],
        basis='Current preserved-data/source review. Known physical blockers veto readiness; scoped SIM/PC is separate.')
    manifest=dict(release_id=identity['release_id'],source_sha256=identity['source_sha256'],physical_readiness_review=review,evidence=evidence)
    save('evidence-manifest.json',manifest)
    gate_script=Path(__file__).with_name('verify_robot_focus_gate.py')
    run=subprocess.run([sys.executable,str(gate_script),'--manifest',str(root/'evidence-manifest.json'),'--output',str(root/'gate-result.json')],capture_output=True,text=True)
    result=read('gate-result.json')
    if result['software_status']!='PASS_SCOPED_SIM_AND_PC' or any(not i.startswith('KNOWN_PHYSICAL_BLOCKER:') for i in result['issues']):
        raise RuntimeError('Final software evidence is not qualified: '+str(result['issues']))
    negative=dict(manifest,evidence=[entry(role,'ui-cold-01/result.json' if role=='cold' else name) for role,name in roles.items()])
    save('gate-negative-manifest.json',negative)
    subprocess.run([sys.executable,str(gate_script),'--manifest',str(root/'gate-negative-manifest.json'),'--output',str(root/'gate-negative-result.json')],capture_output=True,text=True)
    if read('gate-negative-result.json')['software_status']!='FAIL':raise RuntimeError('Original failed cold run incorrectly passed')
    save('completion-verification.json',dict(checked_at_utc=datetime.now(timezone.utc).isoformat(),source_unchanged=True,**identity,
        software_status=result['software_status'],physical_status=result['status'],physical_actions=0,failed_cold_negative_rejected=True))
    print(json.dumps(dict(software=result['software_status'],status=result['status'],issues=result['issues']),ensure_ascii=False))

if __name__=='__main__':main()
