# SPDX-License-Identifier: Apache-2.0
"""Copy finished RoomPlan launch diagnostics; never changes product state."""
import argparse,hashlib,json,os,re
from pathlib import Path

default_root=Path(__file__).resolve().parents[1]/'outputs/roomplan-import-20261023'
runtime=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime'
parser=argparse.ArgumentParser();parser.add_argument('launch',nargs='+')
parser.add_argument('--output-root',type=Path,default=default_root)
parser.add_argument('--copy-set',default='18');args=parser.parse_args()
if not re.fullmatch('[a-zA-Z0-9_-]{1,40}',args.copy_set):raise ValueError('COPY_SET_INVALID')
root=args.output_root.resolve()
if (runtime/'launcher.lock').exists():raise ValueError('FINISH_APP_FIRST')
for launch in args.launch:
    if not re.fullmatch('[a-f0-9]{32}',launch):raise ValueError('LAUNCH_ID_REQUIRED')
    folder=runtime/'launches'/launch
    receipt=json.loads((folder/'cleanup-receipt.json').read_text(encoding='utf-8'))
    if receipt.get('launch_id')!=launch:raise ValueError('LAUNCH_ID_MISMATCH')
    target=root/('runtime-copies'+args.copy_set)/launch;target.mkdir(parents=True,exist_ok=False)
    files=[folder/name for name in ('backend.log','desktop-host.log','engine.log','engine-result.json','engine-status.json',
        'engine-liveness-observations.json','supervisor-status.json','cleanup-receipt.json','owned-exit-observations.json')]
    log=(folder/'engine.log').read_text(encoding='utf-8',errors='replace')
    match=re.search(r'Logging to file: ([^\r\n]+)',log)
    kit='ORIGINAL_PATH_UNAVAILABLE_IN_LAUNCH_LOG'
    if match:
        path=Path(match.group(1)).resolve();parent=Path('C:/isaacsim/kit/logs/Kit/Isaac-Sim Python/6.0').resolve()
        if path.parent==parent and re.fullmatch(r'kit_[0-9]{8}_[0-9]{6}\.log',path.name):files.append(path);kit=str(path)
    rows=[]
    for path in files:
        if not path.is_file():rows.append(dict(name=path.name,status='ORIGINAL_UNAVAILABLE'));continue
        raw=path.read_bytes();(target/path.name).write_bytes(raw)
        rows.append(dict(name=path.name,status='EXACT_COPY',bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
    (target/'copy-receipt.json').write_text(json.dumps(dict(launch_id=launch,kit_log=kit,files=rows),indent=2),encoding='utf-8')
    print(json.dumps(dict(launch=launch,files=len(rows),kit=kit)))
