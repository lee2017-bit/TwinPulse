# SPDX-License-Identifier: Apache-2.0
"""Explicit pending gate: never promotes fake tests/cold failure to live PASS."""
import hashlib,json,os,subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[1];out=root/'outputs/environment-photo-20261024-01'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
fresh=read(out/'ui01/result.json');cold=read(out/'cold01/result.json');audit=read(out/'job-audit01/audit.json')
checks={
    'original_ui_failure_preserved':fresh['status']=='FAIL' and fresh['proposal']['status']=='failed',
    'pre_dispatch_failure_http_zero':audit['total_requests']==0 and fresh['proposal']['response_sha256'] is None,
    'original_thirty_meshes':len(fresh['environment']['objects'])==30,
    'same_job_cold_failed_not_ready':cold['proposal']['job_id']==fresh['proposal']['job_id'] and cold['proposal']['status']=='failed',
    'cold_no_photo_post':not any(r.get('action')=='photo_analyze' for r in cold['responses']),
    'cold_explicit_build_passed':cold['status']=='PASS_SCOPED',
    'focused_contracts_only_passed':read(out/'focused04/result.json')['status']=='PASS',
    'current_candidate_verified':read(out/'installation02.json')['verification']['files']==1690,
    'launcher_lock_absent':not (Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime/launcher.lock').exists(),
}
for label,folder in [('first','runtime-copies01/dcae8c8dafc94d838b9906ab0646e162'),('fixed','runtime-copies02/95df1e785ebe4dfc930410a216d7925e')]:
    r=read(out/folder/'owned-exit-observations.json')
    checks[label+'_roots_natural_zero']=all(r['roles'][role]['return_code']==0 and r['roles'][role]['root_disposition']=='EXITED_DURING_GRACE' for role in ('backend','engine'))
    receipt=read(out/folder/'copy-receipt.json')
    checks[label+'_original_log_copies_exact']=all(hashlib.sha256((out/folder/item['name']).read_bytes()).hexdigest()==item['sha256'] for item in receipt['files'] if item['status']=='EXACT_COPY')
decode=subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-i',str(out/'ui01/recording/app-screen.mp4'),'-f','null','NUL'],capture_output=True)
checks['full_encoded_recording_decode']=decode.returncode==0
result=dict(status='LOCAL_IMPLEMENTATION_ONLY_LIVE_ACCEPTANCE_PENDING',checks=checks,model_http_requests=0,hardware_actions=0,
    live_detection_pass=False,live_candidate_apply_pass=False,metric_photo_alignment_pass=False,lidar_world_registration_pass=False,
    pending='Fresh explicit one-photo/one-call approval requested after preserved pre-dispatch failure. No automatic retry.',
    decode=dict(exit_code=decode.returncode,error=decode.stderr.decode('utf-8',errors='replace')))
with (out/'acceptance01.json').open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
print(json.dumps(result));raise SystemExit(0 if all(checks.values()) else 1)
