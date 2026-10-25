# SPDX-License-Identifier: Apache-2.0
"""Actual packaged read-only role; no robot, network or control access."""
import hashlib,json,os,subprocess,sys
from pathlib import Path
out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=False);release=Path(sys.argv[2]).resolve()
state=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime/devices/local';operation='db929f4ad15e418e88ddd71a85ea55f6';project='chat_mvki3gm9_e212190a'
source=state/'physical-live'/operation;receipt=source/'receipt.json'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
before=sha(receipt);command=[str(release/'TwinPulse.exe'),'--internal-role','alignment-archive','--state-root',str(state),'--operation',operation,'--project',project,'--output',str(out/'extracted.json'),'--start-sequence','715']
run=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=75);(out/'worker.log').write_bytes(run.stdout)
data=json.loads((out/'extracted.json').read_bytes()) if (out/'extracted.json').exists() else None
result=dict(scope='PACKAGED_READ_ONLY_EXTRACTION_NOT_ALIGNMENT_OR_HARDWARE_ACCEPTANCE',command=command,exit_code=run.returncode,receipt_before_sha256=before,receipt_after_sha256=sha(receipt),extraction_sha256=sha(out/'extracted.json') if data else None,
    frame_ids=[f['identity'] for f in data['frames']] if data else [],physical_actions=0,model_calls=0)
result['status']='PASS' if run.returncode==0 and data and data['receipt_complete'] is True and data['receipt_sha256']==before==result['receipt_after_sha256'] and len(data['frames'])==3 and data['frames'][0]['identity'][1]==715 and data['physical_authority'] is False else 'FAIL'
(out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(dict(status=result['status'],exit_code=run.returncode,frames=len(result['frame_ids']))));raise SystemExit(0 if result['status']=='PASS' else 1)
