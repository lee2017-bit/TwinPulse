# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Immutable original bytes and inspected snapshots, separate from scenes."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
from threading import RLock
from uuid import uuid4
from twinpulse_core.library_assets import MeshAsset


def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):raise ValueError('LIBRARY_LOCATION_INVALID')
    temporary=path.with_name('.'+path.name+'.'+uuid4().hex+'.tmp')
    try:
        with temporary.open('x',encoding='utf-8') as stream:
            json.dump(value,stream,ensure_ascii=False,sort_keys=True,allow_nan=False)
            stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:temporary.unlink(missing_ok=True)


class LibraryAssetStore:
    def __init__(self,state_root):
        self.root=Path(state_root)/'model-library'/'assets';self.lock=RLock()

    def register(self,snapshot):
        asset=MeshAsset.from_dict(snapshot);path=self.root/(asset.version+'.json')
        with self.lock:
            if path.exists():
                if path.is_symlink() or self.load(asset.logical_asset_id,asset.version)!=asset.to_dict():
                    raise ValueError('LIBRARY_IMMUTABLE_VERSION_CONFLICT')
            else:atomic_json(path,asset.to_dict())
        return asset

    def load(self,identity,version):
        if not re.fullmatch('[a-f0-9]{64}',str(version)):raise ValueError('LIBRARY_VERSION_INVALID')
        path=self.root/(version+'.json')
        if path.is_symlink() or not path.is_file() or path.stat().st_size>1500000:raise ValueError('LIBRARY_ASSET_UNAVAILABLE')
        asset=MeshAsset.from_dict(json.loads(path.read_text(encoding='utf-8')))
        if asset.logical_asset_id!=identity or asset.version!=version:raise ValueError('LIBRARY_ASSET_IDENTITY_MISMATCH')
        return asset.to_dict()

    def catalog(self):
        if not self.root.exists():return []
        rows=[]
        for path in sorted(self.root.glob('*.json')):
            if not re.fullmatch('[a-f0-9]{64}.json',path.name):continue
            asset=MeshAsset.from_dict(json.loads(path.read_text(encoding='utf-8')))
            self.load(asset.logical_asset_id,path.stem)
            rows.append(dict(asset_id=asset.logical_asset_id,version=asset.version,title=asset.title,kind='usd',
                source_name=asset.source_name,source_sha256=asset.source_sha256,dimensions_m=list(asset.dimensions_m),
                units='m',up_axis='Z',origin=asset.origin,license=asset.license,visual_status='inspected_static_triangles',
                physics_status='conservative_static_box_not_physics_validated',reusable=True))
        return deepcopy(rows)


def store_source(root,raw):
    digest=hashlib.sha256(raw).hexdigest();path=Path(root)/'source-blobs'/(digest+'.bin')
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):raise ValueError('LIBRARY_LOCATION_INVALID')
    if path.exists():
        if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('LIBRARY_SOURCE_HASH_MISMATCH')
    else:
        try:
            with path.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        except FileExistsError:
            if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('LIBRARY_SOURCE_HASH_MISMATCH')
    return path,digest
