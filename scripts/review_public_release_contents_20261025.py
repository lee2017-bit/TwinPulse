# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Audit existing release ZIP contents without changing GitHub or original bytes."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from inspect_publication_scope_20261025 import NoRedirect, PATTERNS, REPO, ROOT
import re

OUT = ROOT / 'outputs/public-publication-20261025-01'


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def main():
    receipt = OUT / 'release-content01.json'
    if receipt.exists():
        raise ValueError('NEW_RECEIPT_REQUIRED')
    scope = json.loads((OUT / 'scope01.json').read_bytes())
    files = subprocess.check_output(['rg', '--files', '--no-ignore', 'outputs',
        '-g', 'TwinPulse-Windows*zip'], cwd=ROOT, text=True).splitlines()
    local = {Path(name).name: ROOT / name for name in files}
    credential = subprocess.run(['git', '-c', 'credential.interactive=false', 'credential', 'fill'],
        cwd=ROOT, input='protocol=https\nhost=github.com\npath=' + REPO + '.git\n\n',
        text=True, capture_output=True, timeout=30,
        env={**os.environ, 'GCM_INTERACTIVE': 'Never', 'GIT_TERMINAL_PROMPT': '0'})
    fields = dict(line.split('=', 1) for line in credential.stdout.splitlines() if '=' in line)
    token = fields.get('password')
    if credential.returncode or not token:
        raise ValueError('EXISTING_GIT_CREDENTIAL_UNAVAILABLE')
    opener = urllib.request.build_opener(NoRedirect())
    results = []
    for release in scope['releases']:
        for asset in release['assets']:
            if not asset['name'].endswith('.zip'):
                continue
            path = local.get(asset['name'])
            downloaded = False
            if path is None:
                path = OUT / asset['name']
                if path.exists():
                    raise ValueError('UNREVIEWED_DOWNLOAD_ALREADY_EXISTS')
                request = urllib.request.Request(
                    'https://api.github.com/repos/' + REPO + '/releases/assets/' + str(asset['id']),
                    headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/octet-stream',
                             'User-Agent': 'TwinPulse-publication-content-review'})
                try:
                    response = opener.open(request, timeout=60)
                except urllib.error.HTTPError as error:
                    if error.code not in (301, 302, 303, 307, 308):
                        raise ValueError('ASSET_HTTP_' + str(error.code)) from None
                    location = error.headers.get('Location', '')
                    parsed = urllib.parse.urlsplit(location)
                    if parsed.scheme != 'https' or parsed.hostname not in {
                            'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}:
                        raise ValueError('ASSET_REDIRECT_REJECTED')
                    response = urllib.request.urlopen(location, timeout=60)  # No credential forwarded.
                with response, path.open('xb') as target:
                    for block in iter(lambda: response.read(1024 * 1024), b''):
                        target.write(block)
                downloaded = True
            actual = digest(path)
            if path.stat().st_size != asset['bytes'] or 'sha256:' + actual != asset['digest']:
                raise ValueError('ASSET_DIGEST_MISMATCH')
            findings = []
            members = 0
            manifests = []
            with zipfile.ZipFile(path) as archive:
                for info in archive.infolist():
                    if info.is_dir():
                        continue
                    name = PurePosixPath(info.filename)
                    members += 1
                    if name.is_absolute() or '..' in name.parts:
                        findings.append(dict(path=str(name), category='UNSAFE_ZIP_PATH'))
                    if set(name.parts) & {'captures', 'saved-projects', '.aws', '.codex', 'datasets', 'physical-live'} or name.name.startswith('.env'):
                        findings.append(dict(path=str(name), category='PRIVATE_DATA_PATH'))
                    raw = archive.read(info)
                    for category, pattern in PATTERNS.items():
                        if re.search(pattern, raw, re.I):
                            findings.append(dict(path=str(name), category=category))
                    if name.name == 'windows-release-manifest.json':
                        data = json.loads(raw)
                        manifests.append(dict(path=str(name), build_id=data.get('build_id'),
                            source_manifest_sha256=data.get('source_manifest_sha256'),
                            file_count=len(data.get('files', []))))
            row = dict(tag=release['tag'], asset=asset['name'], bytes=asset['bytes'], sha256=actual,
                exact_remote_digest=True, downloaded_for_local_audit=downloaded, members=members,
                findings=findings, manifests=manifests)
            results.append(row)
            print(json.dumps(dict(asset=asset['name'], members=members, findings=findings)), flush=True)
    result = dict(schema='public-existing-release-content-review-1.0', results=results,
        mutation=False, original_bytes_changed=False, deleted=0,
        media_scope='Existing four MP4s/posters have original synthetic-SIM-only review receipts; no new media upload.',
        limitations='Bounded credential/path inspection, original content provenance and notices; not exhaustive legal or malware certification.')
    with receipt.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
    if any(row['findings'] for row in results):
        raise ValueError('RELEASE_CONTENT_REQUIRES_REVIEW')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps(dict(status='FAILED', reason=str(error) if isinstance(error, ValueError) else type(error).__name__)))
        raise SystemExit(1)
