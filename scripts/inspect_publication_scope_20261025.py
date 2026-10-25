# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only Git/history and GitHub release inventory for an approved public switch.

Reports path/category/line only, never matched credentials or authorization.
Does not change Git, visibility, releases, local projects or robot state.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/public-publication-20261025-01'
REPO = 'lee2017-bit/TwinPulse'
PATTERNS = {
    'github_token': rb'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b',
    'provider_token': rb'\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{25,}\b',
    'private_key': rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    'literal_auth_header': rb'Authorization\s*:\s*(?:Bearer|Basic)\s+[A-Za-z0-9/+_.=-]{20,}',
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def main():
    OUT.mkdir(exist_ok=True)
    target = OUT / 'scope01.json'
    if target.exists():
        raise ValueError('NEW_RECEIPT_REQUIRED')
    objects = subprocess.check_output(['git', 'rev-list', '--objects', '--all'], cwd=ROOT).splitlines()
    paths = {}
    for row in objects:
        oid, _, name = row.partition(b' ')
        if name:
            paths[oid.decode()] = name.decode('utf-8', errors='replace')
    proc = subprocess.Popen(['git', 'cat-file', '--batch'], cwd=ROOT,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    findings = []
    count = size = 0
    for oid, name in paths.items():
        proc.stdin.write(oid.encode() + b'\n')
        proc.stdin.flush()
        header = proc.stdout.readline().split()
        length = int(header[2])
        raw = proc.stdout.read(length)
        if len(raw) != length or proc.stdout.read(1) != b'\n':
            raise ValueError('GIT_OBJECT_READ_INCOMPLETE')
        if header[1] != b'blob':
            continue
        count += 1
        size += length
        for category, pattern in PATTERNS.items():
            for match in re.finditer(pattern, raw, re.I):
                findings.append(dict(object=oid, path=name, category=category,
                                     line=raw.count(b'\n', 0, match.start()) + 1))
    proc.stdin.close()
    if proc.wait(timeout=15):
        raise ValueError('GIT_OBJECT_PROCESS_FAILED')
    credential = subprocess.run(['git', '-c', 'credential.interactive=false', 'credential', 'fill'],
        cwd=ROOT, input='protocol=https\nhost=github.com\npath=' + REPO + '.git\n\n',
        text=True, capture_output=True, timeout=30,
        env={**os.environ, 'GCM_INTERACTIVE': 'Never', 'GIT_TERMINAL_PROMPT': '0'})
    fields = dict(line.split('=', 1) for line in credential.stdout.splitlines() if '=' in line)
    token = fields.get('password')
    if credential.returncode or not token:
        raise ValueError('EXISTING_GIT_CREDENTIAL_UNAVAILABLE')
    opener = urllib.request.build_opener(NoRedirect())

    def get(route):
        req = urllib.request.Request('https://api.github.com/repos/' + REPO + route,
            headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
                     'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'TwinPulse-publication-review'},
            method='GET')
        try:
            with opener.open(req, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            raise ValueError('GITHUB_HTTP_' + str(error.code)) from None

    repository = get('')
    releases = []
    page = 1
    while True:
        batch = get('/releases?per_page=100&page=' + str(page))
        for release in batch:
            body = release.get('body') or ''
            releases.append(dict(id=release['id'], tag=release['tag_name'], url=release['html_url'],
                draft=release['draft'], prerelease=release['prerelease'],
                body_sha256=hashlib.sha256(body.encode()).hexdigest(),
                assets=[dict(id=a['id'], name=a['name'], bytes=a['size'],
                             digest=a.get('digest'), url=a['browser_download_url']) for a in release['assets']]))
        if len(batch) < 100:
            break
        page += 1
    result = dict(schema='public-publication-scope-1.0', repository=repository['full_name'],
        private=repository['private'], visibility=repository.get('visibility'),
        admin_permission=repository.get('permissions', {}).get('admin'),
        default_branch=repository['default_branch'],
        history_blob_count=count, history_blob_bytes=size, secret_pattern_findings=findings,
        releases=releases, release_count=len(releases),
        asset_count=sum(len(r['assets']) for r in releases),
        mutation=False, credentials_persisted=False,
        limitation='Bounded pattern scan and asset metadata inventory; binary/release content needs separate review.')
    with target.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps(result))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps(dict(status='FAILED', reason=str(error) if isinstance(error, ValueError) else type(error).__name__)))
        raise SystemExit(1)
