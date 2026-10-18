# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read an exact retained generation capture; never Build or restore authority."""
import base64
import binascii
import hashlib
from io import BytesIO
from itertools import islice
import json
import math
from pathlib import Path
import re
from twinpulse_core import canonical_sha256
from PIL import Image

READ_ERRORS=(OSError,ValueError,TypeError,KeyError,binascii.Error,RecursionError,Image.DecompressionBombError)

def _bounded_record(root,kind,key,remaining):
    if kind not in ('checkpoint','render') or not re.fullmatch('[a-f0-9]{64}',key):raise ValueError('key')
    folder=root/kind;path=folder/(key+'.json')
    if root.resolve()!=root or root.is_symlink() or folder.is_symlink() or path.is_symlink() or path.resolve().parent!=root/kind:raise ValueError('location')
    limit=min(2*1024*1024,remaining)
    if limit<0:raise ValueError('total_size')
    with path.open('rb') as stream:data=stream.read(limit+1)
    if len(data)>limit:raise ValueError('size')
    envelope=json.loads(data)
    if (not isinstance(envelope,dict) or set(envelope)!={'schema_version','payload_sha256','payload'}
            or envelope['schema_version']!='generation-store-1.0' or not isinstance(envelope.get('payload'),dict)
            or canonical_sha256(envelope['payload'])!=envelope['payload_sha256']):raise ValueError('digest')
    return envelope['payload'],len(data)

def preview_binding(generation):
    progress=(generation or {}).get('progress') or {};preview=progress.get('generation_preview') or {}
    keys=((generation or {}).get('request_id'),progress.get('request_id'),progress.get('checkpoint_id'),
        preview.get('candidate_revision'),preview.get('scene_revision'))
    return keys if all(isinstance(v,str) and v for v in keys) else None

def load_generation_preview(root,project_id,generation):
    binding=preview_binding(generation)
    if not binding:return None
    root=Path(root)
    try:
        _outer_request,request_id,key,candidate,scene=binding
        cp,used=_bounded_record(root,'checkpoint',key,32*1024*1024)
        progress=generation['progress']['generation_preview']
        if (cp.get('request_id')!=request_id or cp.get('generation_preview')!=progress or not cp.get('preview_plan')):return None
        plan_sha=canonical_sha256(cp['preview_plan'])
        explicit=cp.get('preview_render_key')
        if explicit and (not isinstance(explicit,str) or not re.fullmatch('[a-f0-9]{64}',explicit)):return None
        paths=[root/'render'/(explicit+'.json')] if explicit else list(islice((root/'render').glob('*.json'),257))
        if len(paths)>256:return None
        captures=[]
        for path in paths:
            try:
                render,length=_bounded_record(root,'render',path.stem,32*1024*1024-used);used+=length
            except READ_ERRORS:
                used+=2*1024*1024
                if explicit or used>=32*1024*1024:return None
                continue
            meta=render.get('metadata') or {}
            if not isinstance(meta,dict):continue
            if (canonical_sha256(meta)!=path.stem or meta.get('project_id')!=project_id
                    or meta.get('candidate_revision')!=candidate or meta.get('scene_revision')!=scene
                    or meta.get('applied_revision')!=scene or meta.get('plan_sha256')!=plan_sha):continue
            if (not isinstance(render.get('jpeg_base64'),str) or len(render['jpeg_base64'])>240000
                    or type(meta.get('captured_at_ms')) not in (int,float) or not math.isfinite(meta['captured_at_ms'])
                    or type(meta.get('frame_id')) is not int or not 0<=meta['frame_id']<=2**53-1
                    or type(meta.get('width')) is not int or not 64<=meta['width']<=1280
                    or type(meta.get('height')) is not int or not 64<=meta['height']<=960
                    or type(meta.get('camera_sequence')) is not int or meta['camera_sequence']<0
                    or any(not isinstance(meta.get(k),str) or not 1<=len(meta[k])<=100 for k in ('engine_session_id','stage_epoch'))):continue
            try:
                data=base64.b64decode(render['jpeg_base64'],validate=True)
                if hashlib.sha256(data).hexdigest()!=meta.get('sha256'):continue
                with Image.open(BytesIO(data)) as image:
                    if image.format!='JPEG' or image.size!=(meta['width'],meta['height']):continue
                    image.verify()
            except READ_ERRORS:continue
            frame={k:meta[k] for k in ('frame_id','applied_revision','captured_at_ms','width','height',
                'camera_sequence','sha256','engine_session_id','stage_epoch')}
            frame['data']=data;captures.append(frame)
        return max(captures,key=lambda row:row['captured_at_ms']) if captures else None
    except READ_ERRORS:return None
