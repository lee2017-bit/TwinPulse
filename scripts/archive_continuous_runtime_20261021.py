# SPDX-License-Identifier: Apache-2.0
"""Preserve finished launch evidence before later starts rotate shared Kit logs."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'outputs/robot-continuous-repair-20261021'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--attempt',required=True);parser.add_argument('--extra-attempt',action='append',default=[])
    parser.add_argument('--archive-label',choices=('runtime-final','runtime-ui','runtime-normal','runtime-restart','runtime-overlap'),default='runtime-final')
    parser.add_argument('--diagnostic-start',type=Path,action='append',default=[]);args=parser.parse_args();a=args.attempt
    if not re.fullmatch('[0-9]{2}',a):raise ValueError('TWO_DIGIT_ATTEMPT_REQUIRED')
    if (Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime/launcher.lock').exists():raise ValueError('FINISH_APP_NORMALLY_FIRST')
    out=BASE/f'{args.archive_label}{a}';out.mkdir(exist_ok=False)
    records=sorted(BASE.glob(f'start-*-{a}.json'))+[BASE/f'normal{a}/result.json',BASE/f'normal{a}-restart/result.json']
    for extra in args.extra_attempt:
        if not re.fullmatch('[0-9]{2}',extra):raise ValueError('TWO_DIGIT_EXTRA_REQUIRED')
        records+=sorted(BASE.glob(f'start-*-{extra}.json'))
    for p in args.diagnostic_start:
        p=p.resolve()
        if p.parent!=BASE.resolve() or not re.fullmatch('start-diagnostic[0-9]{2}[a-z]?\\.json',p.name):raise ValueError('EXACT_LOCAL_DIAGNOSTIC_START_REQUIRED')
        records.append(p)
    launches={read(p)['launch_id'] for p in records if p.is_file()};rows=[]
    for launch in sorted(launches):
        if not re.fullmatch('[a-f0-9]{32}',launch):raise ValueError('LAUNCH_ID_SHAPE')
        source=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime/launches'/launch
        target=out/launch;target.mkdir()
        paths=[source/name for name in ('backend.log','desktop-host.log','engine.log','engine-result.json','engine-status.json',
            'engine-liveness-observations.json','supervisor-status.json','cleanup-receipt.json','owned-exit-observations.json')]
        if (source/'engine.log').is_file():
            match=re.search(r'Logging to file: ([^\r\n]+)',(source/'engine.log').read_text(encoding='utf-8',errors='replace'))
            if match:
                kit=Path(match.group(1)).resolve();parent=Path('C:/isaacsim/kit/logs/Kit/Isaac-Sim Python/6.0').resolve()
                if kit.parent==parent and re.fullmatch('kit_[0-9]{8}_[0-9]{6}\\.log',kit.name):paths.append(kit)
        entry=dict(launch_id=launch,files=[])
        for path in paths:
            if not path.is_file():entry['files'].append(dict(source=str(path),status='ORIGINAL_UNAVAILABLE'));continue
            raw=path.read_bytes();dest=target/path.name;dest.write_bytes(raw)
            entry['files'].append(dict(source=str(path),path=dest.relative_to(BASE).as_posix(),bytes=len(raw),sha256=sha256(raw).hexdigest(),status='COPIED_EXACT'))
        if (source/'engine-result.json').is_file():
            v=read(source/'engine-result.json');host=v.get('host_phase_diagnostics',{});view=v.get('viewport_phase_diagnostics',{})
            entry['engine_summary']=dict(capture_only_status=v.get('status'),not_whole_journey_verdict=True,
                engine_session_id=v.get('engine_session_id'),stage_epoch=v.get('stage_epoch'),applied_revision=v.get('applied_revision'),
                live_viewport=v.get('live_viewport'),host_first_stall=host.get('first_stall'),host_worst_phase=host.get('worst_phase'),
                viewport_worst_phase=view.get('worst_phase'),viewport_worst_io=view.get('worst_io'),
                viewport_join_status=view.get('join_status'),viewport_active_io=view.get('active_io'))
        rows.append(entry)
    value=dict(classification='EXACT_FINISHED_RUNTIME_DIAGNOSTICS_NOT_HARDWARE_ACCEPTANCE',attempt=a,launches=rows)
    (out/'receipt.json').write_text(json.dumps(value,indent=2),encoding='utf-8')
    print(json.dumps(dict(launches=len(rows),receipt=str(out/'receipt.json'))))
if __name__=='__main__':main()
