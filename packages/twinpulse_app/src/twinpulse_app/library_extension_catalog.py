# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Bundled reviewed manifests. UI/forms/jobs do not know specialist tools.

This is not installation of arbitrary Python or a plugin security sandbox.
Adapters are trusted packaged code. Personal extension installation is a
separate reviewed workflow, not an LLM-controlled import path.
"""
import importlib
import json
from pathlib import Path
import re
from .runtime_paths import resource_root


def definitions(folder=None):
    folder=Path(folder or resource_root()/'packages/twinpulse_app/src/twinpulse_app/tool_manifests')
    result=[];seen=set()
    for path in sorted(folder.glob('*.json')):
        if path.is_symlink() or path.stat().st_size>32000:raise ValueError('EXTENSION_MANIFEST_INVALID')
        value=json.loads(path.read_text(encoding='utf-8'))
        if set(value)!={'extension_id','title','transport','default_enabled','version','tools'}:
            raise ValueError('EXTENSION_MANIFEST_SHAPE_INVALID')
        if value['transport'] not in {'builtin','mcp','cli'} or type(value['default_enabled']) is not bool:
            raise ValueError('EXTENSION_MANIFEST_TRANSPORT_INVALID')
        for tool in value['tools']:
            if set(tool)!={'tool_id','title','adapter','output_kind','input_schema'} or tool['tool_id'] in seen:
                raise ValueError('EXTENSION_TOOL_INVALID_OR_DUPLICATE')
            if not re.fullmatch(r'twinpulse_app\.[a-z_]+:[a-z_]+',tool['adapter']):raise ValueError('EXTENSION_ADAPTER_INVALID')
            if not isinstance(tool['input_schema'],dict) or tool['input_schema'].get('type')!='object':
                raise ValueError('EXTENSION_INPUT_SCHEMA_INVALID')
            seen.add(tool['tool_id'])
        result.append(value)
    return result


def execute(tool,raw,inputs,folder,token):
    from twinpulse_provider.semantic_scene import _shape_issues
    if _shape_issues(inputs,tool['input_schema']):raise ValueError('EXTENSION_INPUT_VALIDATION_FAILED')
    module,name=tool['adapter'].split(':')
    adapter=getattr(importlib.import_module(module),name)
    output=adapter(raw,inputs,folder,token)
    if not isinstance(output,dict) or len(json.dumps(output,allow_nan=False).encode())>512000:
        raise ValueError('EXTENSION_RESULT_INVALID_OR_LARGE')
    return output
