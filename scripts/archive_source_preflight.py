# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only source inventory for the explicitly requested private Git backup.

Does not upload, stage, read ignored runtime/credential files, or print matches.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
DENIED = {'.exe', '.dll', '.pyd', '.zip', '.mp4', '.jpg', '.jpeg', '.bin', '.pem', '.key', '.p12', '.pyc'}
PATTERNS = {
    'PRIVATE_KEY_MATERIAL': re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'PROVIDER_KEY_SHAPE': re.compile(rb'\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{24,}'),
    'GITHUB_TOKEN_SHAPE': re.compile(rb'\bgh[pousr]_[A-Za-z0-9]{20,}'),
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    names = subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=ROOT).split(b'\0')
    rows, excluded, findings = [], [], []
    for name in sorted({n.decode('utf-8') for n in names if n}):
        path = ROOT / name
        if not path.exists():
            continue
        if path.is_symlink() or path.is_junction() or not path.resolve().is_relative_to(ROOT):
            raise ValueError('SOURCE_LINK_OR_OUTSIDE_SCOPE')
        if path.suffix.lower() in DENIED or (path.suffix.lower() == '.png' and not name.startswith('assets/')):
            excluded.append(dict(path=name, reason='MEDIA_OR_BINARY_NOT_SOURCE_BACKUP'))
            continue
        data = path.read_bytes()
        if len(data) > 10 * 1024 * 1024:
            findings.append(dict(path=name, reason='UNEXPECTED_LARGE_SOURCE'))
        for reason, pattern in PATTERNS.items():
            for match in pattern.finditer(data):
                findings.append(dict(path=name, reason=reason, line=data[:match.start()].count(b'\n') + 1))
        rows.append(dict(path=name, bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))
    result = dict(schema='private-source-backup-preflight-1.0', files=rows, excluded=excluded,
                  findings=findings, bytes=sum(r['bytes'] for r in rows), status='REVIEW_REQUIRED' if findings else 'PASS')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    args.output.with_suffix('.paths').write_bytes(b'\0'.join(r['path'].encode('utf-8') for r in rows)+b'\0')
    print(json.dumps({k: result[k] for k in ('status', 'bytes', 'findings', 'excluded')} | {'files':len(rows)}))
    return bool(findings)


if __name__ == '__main__':
    raise SystemExit(main())
