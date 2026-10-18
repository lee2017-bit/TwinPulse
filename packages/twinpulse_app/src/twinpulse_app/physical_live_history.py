# SPDX-License-Identifier: Apache-2.0
"""Bounded read-only recovery of original stream summaries; never control state."""
from collections import deque
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re
import base64
from twinpulse_core.field_persistence import restored_field_trials

MAX_LINE=256*1024


def _json(raw):
    def unique(pairs):
        value={}
        for key,item in pairs:
            if key in value:raise ValueError('HISTORY_DUPLICATE_KEY')
            value[key]=item
        return value
    return json.loads(raw,object_pairs_hook=unique,
        parse_constant=lambda _:(_ for _ in ()).throw(ValueError('HISTORY_NONFINITE')))


def checked_worker_sources(files,worker_sha256):
    if not isinstance(files,dict) or not 1<=len(files)<=160:raise ValueError('WORKER_SOURCES_SHAPE')
    for name,sha in files.items():
        if (not isinstance(name,str) or not re.fullmatch(r'(?:twinpulse_core/)?[A-Za-z0-9_.-]+\.(?:py|sh|json|txt)',name)
                or not isinstance(sha,str) or not re.fullmatch('[a-f0-9]{64}',sha)):raise ValueError('WORKER_SOURCES_MEMBER')
    digest=hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if digest!=worker_sha256:raise ValueError('WORKER_SOURCES_SHA_MISMATCH')
    return deepcopy(files)


def recover_live_history(directory,receipt,*,operation_id,project_id,robot_id,connection_epoch,binding_sha256,source_twin_context):
    if (not isinstance(receipt,dict) or type(receipt.get('event_count')) is not int
            or type(receipt.get('bytes')) is not int or not isinstance(receipt.get('segments'),list)
            or not 1<=len(receipt['segments'])<=128):raise ValueError('HISTORY_RECEIPT_SHAPE')
    directory=Path(directory);tail=deque(maxlen=100);first=None;sequence=0;count=0;size=0;cleanup=None;sources=None;export=None
    field_sources={name:bytearray() for name in ('field-trials.json','field-commits.jsonl','field-stop.json')};field_source_error=False
    expected=dict(operation_id=operation_id,project_id=project_id,robot_id=robot_id,connection_epoch=connection_epoch)
    for segment in receipt['segments']:
        name=segment['path']
        if not isinstance(name,str) or not re.fullmatch(r'events-\d{5}\.jsonl',name):raise ValueError('HISTORY_MEMBER_PATH')
        path=directory/name
        if path.is_symlink() or path.resolve().parent!=directory.resolve():raise ValueError('HISTORY_MEMBER_PATH')
        digest=hashlib.sha256();member_size=0
        with path.open('rb') as stream:
            while True:
                line=stream.readline(MAX_LINE+1)
                if not line:break
                if len(line)>MAX_LINE or not line.endswith(b'\n'):raise ValueError('HISTORY_LINE_BOUND')
                size+=len(line);member_size+=len(line);count+=1;digest.update(line)
                if size>256*1024*1024 or count>2_000_000:raise ValueError('HISTORY_READ_BOUND')
                event=_json(line)
                if not isinstance(event,dict):raise ValueError('HISTORY_EVENT_SHAPE')
                if first is None:
                    first=event
                    if (event.get('schema') not in {'physical-live-pc-start-1.0','physical-live-pc-start-2.0'}
                            or any(event.get(k)!=v for k,v in expected.items()) or event.get('binding_sha256')!=binding_sha256
                            or event.get('source_twin_context')!=source_twin_context
                            or not isinstance(event.get('worker_sha256'),str) or not re.fullmatch('[a-f0-9]{64}',event['worker_sha256'])):
                        raise ValueError('HISTORY_START_BINDING')
                    if 'worker_sources' in event:sources=checked_worker_sources(event['worker_sources'],event['worker_sha256'])
                    continue
                if any(event.get(k)!=v for k,v in expected.items() if k in event):raise ValueError('HISTORY_EVENT_IDENTITY')
                if event.get('schema') in {'physical-live-pc-start-1.0','physical-live-pc-start-2.0'}:raise ValueError('HISTORY_DUPLICATE_START')
                if event.get('schema') not in {'physical-live-event-1.0','physical-live-event-2.0'}:continue
                if any(event.get(k)!=v for k,v in expected.items()):raise ValueError('HISTORY_EVENT_IDENTITY')
                if (type(event.get('sequence')) is not int or event['sequence']!=sequence+1
                        or type(event.get('robot_monotonic_s')) not in (int,float) or not math.isfinite(event['robot_monotonic_s'])
                        or not isinstance(event.get('data'),dict)):raise ValueError('HISTORY_EVENT_SEQUENCE')
                if source_twin_context is not None and event.get('source_twin_context_id')!=source_twin_context['context_id']:
                    raise ValueError('HISTORY_TWIN_CONTEXT')
                sequence=event['sequence'];data=event['data'];kind=event.get('kind')
                if kind=='heartbeat' and data.get('worker_sha256')!=first['worker_sha256']:raise ValueError('HISTORY_WORKER_CHANGED')
                if kind=='cleanup' and data.get('subsystem')=='session':cleanup=data
                if kind=='raw_source' and data.get('kind')=='manifest':export=data
                if kind=='raw_source' and data.get('kind')=='chunk' and data.get('member') in field_sources:
                    try:
                        original=base64.b64decode(data['base64'],validate=True);target=field_sources[data['member']]
                        if (len(original)!=data['length'] or hashlib.sha256(original).hexdigest()!=data['sha256']
                                or data['offset']!=len(target) or len(target)+len(original)>256*1024):
                            raise ValueError('FIELD_SOURCE_CHUNK')
                        target.extend(original)
                    except (ValueError,KeyError,TypeError):field_source_error=True
                if kind not in {'raw','raw_source'}:
                    safe=deepcopy(event);safe['data'].pop('challenge',None);safe['data'].pop('watch_challenge',None);tail.append(safe)
        if member_size!=segment['bytes'] or digest.hexdigest()!=segment['sha256']:raise ValueError('HISTORY_SEGMENT_SHA')
    if first is None or count!=receipt['event_count'] or size!=receipt['bytes']:raise ValueError('HISTORY_RECEIPT_COUNT')
    source_provenance='RECORDED_START_MANIFEST' if sources else 'NOT_RECORDED'
    adjunct=directory/'worker-sources.json'
    if sources is None and adjunct.exists():
        if adjunct.is_symlink() or adjunct.stat().st_size>32768:raise ValueError('WORKER_SOURCES_FILE')
        value=_json(adjunct.read_text(encoding='utf-8'))
        if (not isinstance(value,dict) or value.get('schema')!='physical-live-worker-sources-1.0' or any(value.get(k)!=v for k,v in expected.items())
                or value.get('worker_sha256')!=first['worker_sha256']):raise ValueError('WORKER_SOURCES_BINDING')
        sources=checked_worker_sources(value.get('files'),first['worker_sha256']);source_provenance='VERIFIED_MATCHING_PRESERVED_PACKAGE'
    field_resolution=dict(status='ACK_LEDGER_NOT_RECORDED',trials=[],authority_restored=False)
    if field_sources['field-commits.jsonl']:
        try:
            if field_source_error:raise ValueError('FIELD_SOURCE_CHUNK')
            for name,raw in field_sources.items():
                if not raw and name=='field-stop.json':continue
                member=next((m for m in (export or {}).get('members',[]) if m.get('member')==name),{})
                if not member.get('source_complete') or member.get('source_sha256')!=hashlib.sha256(raw).hexdigest():
                    raise ValueError('FIELD_SOURCE_MANIFEST')
            field_context=_json(field_sources['field-trials.json'])['context']
            if any(field_context.get(k)!=v for k,v in expected.items()):raise ValueError('FIELD_SOURCE_CONTEXT')
            writer_receipt=(cleanup or {}).get('control',{}).get('field_evidence',{})
            complete=writer_receipt.get('complete') is True
            trials=restored_field_trials(field_sources['field-trials.json'],field_sources['field-commits.jsonl'],
                writer_complete=complete,context=field_context,writer_receipt=writer_receipt,
                stop_raw=bytes(field_sources['field-stop.json']) if field_sources['field-stop.json'] else None)
            field_resolution=dict(status='VERIFIED_READ_ONLY' if complete else 'WRITER_INCOMPLETE',trials=trials,authority_restored=False)
        except (ValueError,KeyError,TypeError,StopIteration):
            field_resolution=dict(status='FIELD_PERSISTENCE_UNVERIFIED',trials=[],authority_restored=False)
    return dict(events=list(tail),cleanup_confirmed=cleanup.get('confirmed') if cleanup is not None else None,
        field_trial_resolution=field_resolution,
        cleanup=cleanup,source_export=export,worker_sources=sources,worker_sources_provenance=source_provenance,
        runtime_event_count=count,runtime_worker_sequence=sequence,worker_sha256=first['worker_sha256'])


def preserve_matching_sources(source_root,directory):
    """Explicit offline repair of missing metadata, not rewritten raw evidence."""
    from .physical_live_session import reviewed_bundle
    directory=Path(directory);first_path=directory/'events-00000.jsonl'
    if first_path.is_symlink():raise ValueError('HISTORY_MEMBER_PATH')
    with first_path.open('rb') as stream:first=json.loads(stream.readline(MAX_LINE+1))
    sha,_,files=reviewed_bundle(source_root)
    if first.get('worker_sha256')!=sha:raise ValueError('PRESERVED_PACKAGE_DOES_NOT_MATCH_RECORDED_WORKER')
    value=dict(schema='physical-live-worker-sources-1.0',**{k:first[k] for k in
        ('operation_id','robot_id','project_id','connection_epoch','worker_sha256')},files=checked_worker_sources(files,sha))
    path=directory/'worker-sources.json'
    if path.exists():
        if path.is_symlink() or json.loads(path.read_text(encoding='utf-8'))!=value:raise ValueError('WORKER_SOURCES_CONFLICT')
    else:
        import os
        with path.open('x',encoding='utf-8') as stream:json.dump(value,stream,sort_keys=True);stream.flush();os.fsync(stream.fileno())
    return dict(operation_id=first['operation_id'],worker_sha256=sha,files=len(files),original_events_rewritten=False)
