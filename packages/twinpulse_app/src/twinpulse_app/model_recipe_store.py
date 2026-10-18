# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Local immutable reusable recipes, separate from source and user scenes."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from threading import RLock
from uuid import uuid4

from twinpulse_core.model_library import LIBRARY_VERSION, library_models
from twinpulse_core.model_recipe import checked_recipe, recipe_digest, recipe_manifest
from twinpulse_core.model_recipe import compiled_parts


class ModelRecipeStore:
    def __init__(self, state_root):
        self.root=Path(state_root)/'model-library'
        self.lock=RLock()

    def _checked_root(self, create=False):
        if self.root.is_symlink() or self.root.parent.is_symlink():
            raise ValueError('MODEL_LIBRARY_LOCATION_INVALID')
        if create:self.root.mkdir(parents=True,exist_ok=True)
        if self.root.exists() and not self.root.is_dir():raise ValueError('MODEL_LIBRARY_LOCATION_INVALID')

    def records(self):
        with self.lock:
            self._checked_root()
            records=[]
            if not self.root.exists():return records
            for path in sorted(self.root.glob('*.json')):
                if not re.fullmatch('[0-9a-f]{64}.json',path.name):continue
                if path.is_symlink() or path.stat().st_size>80000:raise ValueError('MODEL_LIBRARY_RECORD_INVALID')
                value=json.loads(path.read_text(encoding='utf-8'))
                recipe=checked_recipe(value['recipe'],sample=False)
                if recipe_digest(recipe)!=path.stem:raise ValueError('MODEL_LIBRARY_DIGEST_MISMATCH')
                records.append(value)
            return records

    def snapshots(self):
        return {m['model_id']:deepcopy(r['recipe']) for r in self.records()
            if (m:=recipe_manifest(r['recipe']))['reusable']}

    def register(self, recipe, *, request_id, model_id):
        recipe=checked_recipe(recipe)
        digest=recipe_digest(recipe)
        record=dict(schema_version='local-model-record-1.0',recipe=recipe,
            created_at_utc=datetime.now(timezone.utc).isoformat(),origin='model_generated',
            generation_request_id=str(request_id)[:100],generator_model=str(model_id)[:120],
            physical_validation='not_run',photo_validation='not_run')
        with self.lock:
            self._checked_root(create=True)
            path=self.root/(digest+'.json')
            if path.exists():
                if path.is_symlink():raise ValueError('MODEL_LIBRARY_RECORD_INVALID')
                old=json.loads(path.read_text(encoding='utf-8'))
                if old['recipe']!=recipe:raise ValueError('MODEL_LIBRARY_DIGEST_MISMATCH')
                return recipe_manifest(recipe)
            temp=self.root/(digest+'.'+uuid4().hex+'.tmp')
            with temp.open('x',encoding='utf-8') as stream:
                json.dump(record,stream,ensure_ascii=False,allow_nan=False,sort_keys=True)
                stream.flush();os.fsync(stream.fileno())
            os.replace(temp,path)
        return recipe_manifest(recipe)

    def public(self):
        generated=[]
        for row in self.records():
            generated.append(recipe_manifest(row['recipe'])|dict(origin=row['origin'],
                created_at_utc=row['created_at_utc'],generation_request_id=row['generation_request_id'],
                generator_model=row['generator_model'],preview_parts=compiled_parts(row['recipe'],
                    {p['name']:p['default'] for p in row['recipe']['parameters']})))
        builtins=[dict(row,origin='builtin',title=row['kind'].replace('_',' '),status='builtin') for row in library_models()]
        return dict(library_version=LIBRARY_VERSION,models=builtins+generated,physical_authority=False)
