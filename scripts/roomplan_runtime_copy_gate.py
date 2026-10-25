# SPDX-License-Identifier: Apache-2.0
"""Strict, read-only validation of this campaign's original runtime copies."""
from collections import Counter
import hashlib
from pathlib import PureWindowsPath
import re

REQUIRED={'backend.log','desktop-host.log','engine.log','engine-result.json','engine-status.json',
    'supervisor-status.json','cleanup-receipt.json','owned-exit-observations.json'}
OPTIONAL='engine-liveness-observations.json'

def check_runtime_copy(folder,launch,value):
    issues=[]
    if not isinstance(value,dict) or value.get('launch_id')!=launch:return ['wrong launch identity']
    kit=value.get('kit_log')
    if not isinstance(kit,str):return ['original Kit log identity missing']
    path=PureWindowsPath(kit)
    if (str(path.parent).lower()!=r'C:\isaacsim\kit\logs\Kit\Isaac-Sim Python\6.0'.lower()
            or not re.fullmatch(r'kit_[0-9]{8}_[0-9]{6}\.log',path.name)):
        return ['original Kit log path unavailable or outside reviewed scope']
    expected=REQUIRED|{OPTIONAL,path.name};rows=value.get('files')
    if not isinstance(rows,list) or any(not isinstance(row,dict) or not isinstance(row.get('name'),str) for row in rows):
        return ['invalid copy file list']
    counts=Counter(row['name'] for row in rows)
    if set(counts)!=expected or any(n!=1 for n in counts.values()):issues.append('missing, extra or duplicate file rows')
    for item in rows:
        name=item['name']
        if name not in expected:continue  # Never resolve an untrusted path from a receipt.
        copied=folder/name
        if name==OPTIONAL and item.get('status')=='ORIGINAL_UNAVAILABLE':
            if copied.exists() or copied.is_symlink() or set(item)!={'name','status'}:issues.append('optional absence conflicts with actual file/metadata')
            continue  # This absence does not certify health.
        if (set(item)!={'name','status','bytes','sha256'} or item.get('status')!='EXACT_COPY'
                or type(item.get('bytes')) is not int or item['bytes']<0
                or not isinstance(item.get('sha256'),str) or not re.fullmatch('[a-f0-9]{64}',item['sha256'])
                or copied.is_symlink() or not copied.is_file()):
            issues.append('original file missing or invalid: '+name);continue
        raw=copied.read_bytes()
        if len(raw)!=item['bytes'] or hashlib.sha256(raw).hexdigest()!=item['sha256']:
            issues.append('original file size/hash mismatch: '+name)
    return issues
