# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Fingerprint protected local project/sensor data before/after binary pruning."""
import argparse
import hashlib
import json
import os
from pathlib import Path


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            h.update(block)
    return h.hexdigest()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--compare',type=Path)
    args=parser.parse_args()
    runtime=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime'
    selected=('projects','devices','provider-evidence','harness-profiles','model-library','library-workspace','inputs','source-blobs')
    files={}
    for name in selected:
        root=runtime/name
        if not root.exists():continue
        for path in sorted(root.rglob('*')):
            if path.is_symlink() or path.is_junction():raise ValueError('PROTECTED_DATA_LINK')
            if path.is_file():
                files[str(path)]=dict(bytes=path.stat().st_size,sha256=digest(path))
    photo=Path('C:/Projects/TwinPulse/ITM0018.jpg')
    if photo.is_file():files[str(photo)]=dict(bytes=photo.stat().st_size,sha256=digest(photo))
    result=dict(schema='retention-protected-data-1.0',files=files,count=len(files),bytes=sum(v['bytes'] for v in files.values()))
    if args.compare:
        original=json.loads(args.compare.read_text(encoding='utf-8'))['files']
        changed=[p for p in original if files.get(p)!=original[p]]
        added=[p for p in files if p not in original]
        result.update(status='UNCHANGED' if not changed and not added else 'CHANGED',changed=changed,added=added)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='files'}))


if __name__=='__main__':main()
