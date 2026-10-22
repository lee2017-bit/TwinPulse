# SPDX-License-Identifier: Apache-2.0
"""Freeze exact failed launch logs before any new Start can rotate Kit logs."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import argparse
import re
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--attempt',required=True)
parser.add_argument('--phase',choices=('fresh','cold','lineage','history','reproduction'),default='fresh')
args=parser.parse_args()
if not re.fullmatch(r'[0-9]{2}',args.attempt):raise ValueError('TWO_DIGIT_ATTEMPT_REQUIRED')
base=ROOT/'outputs/robot-continuous-repair-20261021'
launch=json.loads((base/f'start-{args.phase}-{args.attempt}.json').read_text(encoding='utf-8-sig'))
label={'fresh':'ui','cold':'ui-cold','lineage':'lineage','history':'lineage-cold','reproduction':'ui-reproduction'}[args.phase]
ui=json.loads((base/f'{label}-{args.attempt}/result.json').read_text(encoding='utf-8'))
cleanup=base/f'cleanup-{args.phase}-{args.attempt}.json'
if ui.get('status')!='FAIL' and (not cleanup.is_file() or json.loads(cleanup.read_text(encoding='utf-8-sig')).get('status')!='FAIL'):
    raise ValueError('ORIGINAL_FAILED_UI_OR_CLEANUP_REQUIRED')
OUT=base/f'failed-{label}{args.attempt}-original-logs'
OUT.mkdir(exist_ok=False)
run=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime/launches'/launch['launch_id']
paths=[run/name for name in ('backend.log','desktop-host.log','engine.log','engine-status.json','engine-result.json',
    'engine-liveness-observations.json','supervisor-status.json','cleanup-receipt.json')]
engine_log=(run/'engine.log').read_text(encoding='utf-8',errors='replace')
kit=re.search(r'Logging to file: ([^\r\n]+)',engine_log)
if kit:paths.append(Path(kit.group(1)))
if ui.get('project'):paths+=list((run.parent.parent/'projects'/ui['project']/'robot-operations').glob('*.json'))
rows=[]
for index,path in enumerate(paths):
    if not path.is_file():rows.append(dict(source=str(path),status='ORIGINAL_UNAVAILABLE'));continue
    raw=path.read_bytes();target=OUT/('%02d-'%index+path.name);target.write_bytes(raw)
    rows.append(dict(source=str(path),path=target.name,status='COPIED_EXACT',bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
(OUT/'receipt.json').write_text(json.dumps(dict(launch_id=run.name,classification='ORIGINAL_FAILED_UI_NOT_RETIMED',files=rows),indent=2),encoding='utf-8')
engine_path=run/'engine-result.json';cleanup_path=run/'cleanup-receipt.json'
engine=json.loads(engine_path.read_text(encoding='utf-8')) if engine_path.is_file() else {}
cleanup=json.loads(cleanup_path.read_text()) if cleanup_path.is_file() else 'ORIGINAL_UNAVAILABLE_UNTIL_SHUTDOWN'
print(json.dumps(dict(files=len(rows),live_viewport=engine.get('live_viewport'),
    engine_final_status='AVAILABLE' if engine_path.is_file() else 'ORIGINAL_UNAVAILABLE_UNTIL_SHUTDOWN',
    cleanup=cleanup,output=str(OUT))))
