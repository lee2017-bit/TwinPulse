# SPDX-License-Identifier: Apache-2.0
"""Freeze and inspect actual App-exported original evidence; never contact hardware."""
from pathlib import Path
import base64
import hashlib
import html
import json
import os
import shutil
import sys
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/robot-powered-20261020-guard01'


def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
def identity(path):return dict(path=str(path),bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def main():
    global OUT
    if len(sys.argv)>1:
        if sys.argv[1] not in ('01','02','02c','03','04','04c','05'):raise ValueError('Reviewed attempt required')
        OUT=ROOT/('outputs/robot-powered-20261020-guard'+sys.argv[1])
    operation=read(OUT/'prepare-final-operation.json');receipt=read(OUT/'receipt.json')
    start=None;chunks={};source_manifest=None;commands=[];cleanup=[];count=0
    for member in receipt['segments']:
        path=OUT/member['path'];info=identity(path)
        assert info['sha256']==member['sha256'] and info['bytes']==member['bytes']
        original=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime/devices/local/physical-live'/operation['operation_id']/path.name
        assert identity(original)['sha256']==info['sha256']
        for line in path.read_bytes().splitlines():
            event=json.loads(line);count+=1;data=event.get('data',{})
            if start is None:start=event
            if event.get('kind')=='raw_source':
                if data.get('kind')=='chunk':
                    block=base64.b64decode(data['base64'],validate=True)
                    assert len(block)==data['length'] and hashlib.sha256(block).hexdigest()==data['sha256']
                    chunks.setdefault(data['member'],[]).append((data['offset'],block))
                elif data.get('kind')=='manifest':source_manifest=data
            if event.get('kind')=='command' and data.get('action') not in {'watch','input_window'}:
                commands.append(dict(sequence=event['sequence'],robot_s=event['robot_monotonic_s'],data=data))
            if event.get('kind')=='cleanup':cleanup.append(event)
    assert count==receipt['event_count']==receipt['accepted']==receipt['saved']
    source_export_origin='hash_verified_recording_segments'
    if source_manifest is None:
        # A capacity-failed recording can still return its bounded final tail
        # in the actual UI operation export. Preserve that distinct source;
        # never relabel these bytes as part of the incomplete recording.
        source_export_origin='actual_UI_operation_export_final_tail_not_recording_segments'
        for event in operation['events']:
            data=event.get('data',{})
            if event.get('kind')!='raw_source':continue
            if data.get('kind')=='manifest':source_manifest=data
            elif data.get('kind')=='chunk':
                block=base64.b64decode(data['base64'],validate=True)
                assert len(block)==data['length'] and hashlib.sha256(block).hexdigest()==data['sha256']
                existing=dict(chunks.get(data['member'],[]))
                if data['offset'] in existing:assert existing[data['offset']]==block
                else:chunks.setdefault(data['member'],[]).append((data['offset'],block))
    if source_manifest is None:
        source_export_origin='robot_final_summary_only_source_bytes_unavailable_after_PC_capacity_failure'
        for event in operation['events']:
            if event.get('kind')=='cleanup' and event.get('data',{}).get('subsystem')=='session':
                source_manifest=event['data'].get('source_export')
        if source_manifest is None:raise ValueError('ORIGINAL_SOURCE_MANIFEST_UNAVAILABLE')
    sources=OUT/'exported-sources';sources.mkdir(exist_ok=True)
    missing_bodies=[]
    for row in source_manifest['members']:
        if row['status']=='NOT_CREATED':continue
        parts=sorted(chunks.get(row['member'],[]));cursor=row['exported_offset'];blocks=[]
        if not parts and row['exported_bytes']:
            missing_bodies.append(row['member']);continue
        for offset,block in parts:
            assert offset==cursor;cursor+=len(block);blocks.append(block)
        raw=b''.join(blocks);assert len(raw)==row['exported_bytes']
        assert hashlib.sha256(raw).hexdigest()==row['export_sha256']
        path=sources/row['member']
        if path.exists():assert path.read_bytes()==raw
        else:path.write_bytes(raw)
    write(OUT/'source-export-manifest.json',source_manifest)
    write(OUT/'source-body-status.json',dict(origin=source_export_origin,complete=not missing_bodies,missing=missing_bodies))
    session=read(OUT/'session.json');launch_id=session['identity']['engine']['launch_id']
    launch=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime/launches'/launch_id
    frozen=OUT/'original-launch-logs';frozen.mkdir(exist_ok=True);logs=[]
    for name in ('backend.log','desktop-host.log','engine.log','engine-result.json','engine-status.json','supervisor-status.json','cleanup-receipt.json'):
        source=launch/name;destination=frozen/name
        if source.is_file():
            if not destination.exists():shutil.copy2(source,destination)
            assert source.read_bytes()==destination.read_bytes();logs.append(identity(destination))
    # Preserve the matching native Kit log before subsequent starts rotate it.
    kit_candidates=[]
    for folder in (Path(os.environ['USERPROFILE'])/'.nvidia-omniverse/logs/Kit',Path('C:/isaacsim/kit/logs/Kit')):
        if folder.exists():kit_candidates.extend(folder.rglob('kit_*.log'))
    began=datetime.fromisoformat(session['began'].replace('Z','+00:00')).timestamp()
    matching=[p for p in kit_candidates if began-180<=p.stat().st_mtime<=datetime.now(timezone.utc).timestamp()+5]
    for source in matching:
        destination=frozen/('Kit-'+source.name)
        if not destination.exists():shutil.copy2(source,destination)
        assert destination.read_bytes()==source.read_bytes();logs.append(identity(destination))
    build=[json.loads(line) for line in (sources/'output-guard-build.jsonl').read_text(encoding='utf-8').splitlines()] if (sources/'output-guard-build.jsonl').exists() else []
    base=(sources/'base.log').read_text(encoding='utf-8') if (sources/'base.log').exists() else 'SOURCE BYTES UNAVAILABLE; original recording failure preserved.'
    qos_failure='intraprocess communication allowed only with volatile durability' in base
    off=(sources/'final-off.log').read_text(encoding='utf-8') if (sources/'final-off.log').exists() else ''
    independent_idle='TORQUE_OFF_READBACK_PASS encoder_changed=0' in off and 'RESTORE verified=1' in off
    trials={c['data']['trial']['trial_id']:c['data']['trial'] for c in commands if isinstance(c['data'].get('trial'),dict)}
    motions={c['data'].get('request_id') for c in commands if c['data'].get('action') in {'drive','task'} and c['data'].get('request_id')}
    motions.update(t['request_id'] for t in trials.values() if t['case'] not in {'stationary','soak'})
    result=dict(verdict='ACTUAL_PI_BUILD_LOADER_PASS_BASE_START_FAILED_NO_MOTION' if qos_failure else 'ACTUAL_POWERED_RESULTS_REQUIRE_JOURNEY_REVIEW',
        release=session['identity'],launch_id=launch_id,operation_id=operation['operation_id'],
        project_id=operation['project_id'],source_twin_context=operation['manifest']['source_twin_context'],
        worker_sources=start['worker_sources'],raw_count=count,receipt=receipt,commands=commands,
        motion_requests=len(motions),field_trials=list(trials.values()),cleanup=cleanup,source_manifest=source_manifest,build_records=build,
        diagnosis='Base intra-process=true conflicts with the transient-local timing publisher; actual std::invalid_argument and exit -6.' if qos_failure else 'Review original commands, runtime faults and base log separately; no success inferred from object count or connection.',
        secondary='Missing first sensor dereference precedes both ROS Stop/OFF calls. Independent final board OFF/zero/unchanged encoders passed; original cleanup remains false.' if qos_failure else 'No changes to original cleanup or trial verdicts.',
        independent_final_idle=independent_idle,source_export_origin=source_export_origin,source_body_missing=missing_bodies,
        original_launch_logs=logs,matching_kit_logs=len(matching),
        video=identity(OUT/'app-screen.mp4'),
        budget=dict(new_provider_http=0,new_usd='0',additional_50_used='3.5109468',additional_50_remaining='46.4890532',previous_20_separate='14.9450973',previous_unknown_included='0.4770432'),
        not_run=(['LiDAR collection'] if not trials else [])+(['Bootstrap stop'] if not any(t['case']=='bootstrap_stop' for t in trials.values()) else [])+
            ['manual/chat driving','360-degree scan','world alignment','physical stopping distance'],
        user_path='Actual installed Electron explicit Test BrowserWindow; same Start via execution tool, not Explorer/native full-input acceptance.')
    write(OUT/'powered-analysis.json',result)
    esc=lambda v:html.escape(str(v))
    pictures=''.join('<figure><img style="width:100%" src="'+esc(p.name)+'"><figcaption>'+esc(p.name)+'</figcaption></figure>' for p in sorted(OUT.glob('0*.png')))
    report='<meta charset="utf-8"><title>TwinPulse powered Prepare</title><style>body{font:16px system-ui;max-width:1200px;margin:2rem auto}pre{white-space:pre-wrap;overflow-wrap:anywhere}video{width:100%}</style><h1>실제 전원 시험: 원문·화면·실행 결과</h1>'
    report+='<p>Operation '+esc(operation['operation_id'])+' / launch '+esc(launch_id)+'. '+esc(result['verdict'])+'</p><p>'+esc(result['diagnosis'])+'</p><p>'+esc(result['secondary'])+'</p>'
    report+='<p><a href="powered-analysis.json">실행 ID·SHA·원문/단계·정확 예산</a> · <a href="source-export-manifest.json">원문 반출 검사</a> · <a href="prepare-final-operation.json">앱 최종 실행 JSON</a></p><video controls src="app-screen.mp4"></video>'+pictures+'<h2>실제 base.log 원문</h2><pre>'+esc(base)+'</pre><h2>검증 범위/잔여</h2><pre>'+esc(json.dumps({k:result[k] for k in ('raw_count','motion_requests','budget','not_run','user_path')},ensure_ascii=False,indent=2))+'</pre>'
    (OUT/'report.html').write_text(report,encoding='utf-8')
    print(json.dumps(dict(operation_id=operation['operation_id'],raw_count=count,source_export=source_manifest['complete'],motion_requests=len(motions),logs=len(logs),video=result['video']),ensure_ascii=False))


if __name__=='__main__':main()
