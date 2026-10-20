# SPDX-License-Identifier: Apache-2.0
"""Private archival backup, not a full-product or physical-readiness release."""
import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import runpy
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from preserve_github_release import NoRedirect, ROOT, REPO, sha

BUILD = '20261020T034213Z-ee4c39105987'
TAG = 'sim-alpha-2026-10-20-scoped-checkpoint'
OUT = ROOT / 'outputs/github-preservation-20261020'
PACKAGE = Path(os.environ['LOCALAPPDATA']) / 'TwinPulse/installed/releases' / BUILD
NOTES = ('Private recovery checkpoint for the scoped SIM/PC-tested build '+BUILD+'.\n\n'
    'Verified in the installed explicit Test BrowserWindow: saved-scene two-SIM connection,62-second held control,'
    'four directions,90-degree command,one360-degree scan,exact Stop/Stop-all ACK and applied epochs,'
    'sensor OFF/disconnect,operation export and cold restoration/PC preparation. '
    'Original failed attempts are preserved locally.\n\n'
    'NOT a fresh-generation/full9-role reacceptance,normal-mode/native/Explorer acceptance,or physical qualification. '
    'Pi ARM64/ROS build/readback,sensing,braking,driving and world alignment remain NOT_RUN with robot OFF. '
    'Unsigned Windows checkpoint; no Isaac/ROS installer or personal photos/projects/sensor data are included. '
    'The ZIP preserves the original package manifest,including its pre-commit dirty build provenance; '
    'the source commit records the reviewed source and maintenance additions,not a retroactive clean rebuild. '
    'Existing third-party licenses/notices remain separate. No repository visibility change.\n')


def prepare():
    OUT.mkdir(parents=True, exist_ok=True)
    verify = runpy.run_path(str(ROOT / 'packages/twinpulse_app/src/twinpulse_app/windows_package.py'))['verify_package']
    verified = verify(PACKAGE)
    active = json.loads((PACKAGE.parent.parent / 'active-release.json').read_bytes())
    if active['release_id'] != BUILD or verified['build_id'] != BUILD:
        raise ValueError('FROZEN_INSTALLATION_CHANGED')
    gate = ROOT / 'outputs/robot-protocol-prep-20261020/ack-gate.json'
    if json.loads(gate.read_bytes())['status'] != 'PASS_SCOPED_ACK_AND_EXPORT':
        raise ValueError('SCOPED_GATE_REQUIRED')
    manifest = json.loads((PACKAGE / 'windows-release-manifest.json').read_bytes())
    archive = OUT / ('TwinPulse-Windows-scoped-SIM-PC-' + BUILD + '.zip')
    if not archive.exists():
        with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as target:
            for name in [r['path'] for r in manifest['files']] + ['windows-release-manifest.json']:
                file = PACKAGE / name
                target.write(file, 'TwinPulse/' + name)
    with zipfile.ZipFile(archive) as source:
        expected = {'TwinPulse/' + r['path']: r for r in manifest['files']}
        if set(source.namelist()) != set(expected) | {'TwinPulse/windows-release-manifest.json'}:
            raise ValueError('ARCHIVE_EXTRA_OR_MISSING_FILES')
        for name, row in expected.items():
            raw = source.read(name)
            if len(raw) != row['bytes'] or hashlib.sha256(raw).hexdigest() != row['sha256']:
                raise ValueError('ARCHIVE_PACKAGE_HASH_MISMATCH')
        if source.read('TwinPulse/windows-release-manifest.json') != (PACKAGE / 'windows-release-manifest.json').read_bytes():
            raise ValueError('ARCHIVE_MANIFEST_CHANGED')
    review = dict(schema='scoped-private-checkpoint-1.0', repository=REPO, private=True,
        scope='SCOPED_SIM_PC_NOT_FULL_PRODUCT_OR_PHYSICAL', release_id=BUILD,
        source_sha256=verified['source_manifest_sha256'], tag=TAG, notes=NOTES,
        package_files=verified['files'], gate_sha256=sha(gate), assets=[])
    sums = OUT / 'SHA256SUMS.txt'
    sums.write_text(sha(archive) + '  ' + archive.name + '\n', encoding='utf-8')
    for file in (archive, sums):
        review['assets'].append(dict(path=file.relative_to(ROOT).as_posix(), bytes=file.stat().st_size, sha256=sha(file)))
    (OUT / 'archive-review.json').write_text(json.dumps(review, indent=2), encoding='utf-8')
    print(json.dumps(dict(status='EXACT_PRIVATE_ARCHIVE_PREPARED', files=verified['files'], assets=review['assets'])), flush=True)
    return review


def publish(commit):
    if not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError('EXACT_COMMIT_REQUIRED')
    review = json.loads((OUT / 'archive-review.json').read_bytes())
    remote = subprocess.check_output(['git', 'ls-remote', 'origin', 'refs/heads/main'], cwd=ROOT, text=True).split()[0]
    if remote != commit or review['scope'] != 'SCOPED_SIM_PC_NOT_FULL_PRODUCT_OR_PHYSICAL':
        raise ValueError('REMOTE_SOURCE_OR_REVIEW_CHANGED')
    credential = subprocess.run(['git', '-c', 'credential.interactive=false', 'credential', 'fill'], cwd=ROOT,
        input='protocol=https\nhost=github.com\npath='+REPO+'.git\n\n', text=True, capture_output=True,
        env={**os.environ, 'GCM_INTERACTIVE':'Never', 'GIT_TERMINAL_PROMPT':'0'})
    fields = dict(line.split('=', 1) for line in credential.stdout.splitlines() if '=' in line)
    token = fields.get('password')
    if credential.returncode or not token:
        raise ValueError('EXISTING_GIT_CREDENTIAL_UNAVAILABLE')
    headers = {'Authorization':'Bearer '+token, 'Accept':'application/vnd.github+json',
        'X-GitHub-Api-Version':'2022-11-28', 'User-Agent':'TwinPulse-approved-private-checkpoint'}
    opener = urllib.request.build_opener(NoRedirect())

    def api(route, data=None):
        body = json.dumps(data).encode() if data is not None else None
        request = urllib.request.Request('https://api.github.com/repos/'+REPO+route, body,
            headers | ({'Content-Type':'application/json'} if body is not None else {}))
        try:
            with opener.open(request, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code == 404 and data is None:
                return None
            raise ValueError('GITHUB_HTTP_'+str(error.code)) from None

    repo = api('')
    if not repo or repo.get('full_name') != REPO or repo.get('private') is not True:
        raise ValueError('EXISTING_PRIVATE_REPOSITORY_REQUIRED')
    release = api('/releases/tags/'+TAG)
    if release is None:
        release = api('/releases', dict(tag_name=TAG, target_commitish=commit,
            name='Scoped SIM PC recovery checkpoint 2026-10-20',
            body=review['notes']+'\nVerified source commit: `'+commit+'`\n',
            draft=False, prerelease=True, make_latest='false'))
    if release['tag_name'] != TAG or release.get('prerelease') is not True:
        raise ValueError('ARCHIVE_RELEASE_IDENTITY_CHANGED')
    result = dict(schema='github-scoped-private-preservation-1.0', repository=REPO, private=True,
        source_commit=commit, release_id=BUILD, source_sha256=review['source_sha256'],
        scope=review['scope'], release_url=release['html_url'], assets=[])
    for row in review['assets']:
        file = ROOT / row['path']
        if not file.resolve().is_relative_to(OUT) or sha(file) != row['sha256'] or file.stat().st_size != row['bytes']:
            raise ValueError('REVIEWED_ARCHIVE_CHANGED')
        existing = next((a for a in release.get('assets', []) if a['name'] == file.name), None)
        if existing is None:
            connection = http.client.HTTPSConnection('uploads.github.com', timeout=120)
            connection.putrequest('POST', '/repos/'+REPO+'/releases/'+str(release['id'])+'/assets?'+urllib.parse.urlencode({'name':file.name}))
            for key, value in (headers | {'Content-Type':'application/octet-stream', 'Content-Length':str(row['bytes'])}).items():
                connection.putheader(key, value)
            connection.endheaders()
            with file.open('rb') as stream:
                for block in iter(lambda:stream.read(1024*1024), b''):
                    connection.send(block)
            response = connection.getresponse()
            if response.status != 201:
                raise ValueError('GITHUB_UPLOAD_HTTP_'+str(response.status))
            existing = json.load(response)
            connection.close()
        request = urllib.request.Request('https://api.github.com/repos/'+REPO+'/releases/assets/'+str(existing['id']),
            headers=headers | {'Accept':'application/octet-stream'})
        try:
            download = opener.open(request, timeout=120)
        except urllib.error.HTTPError as error:
            if error.code not in (301,302,303,307,308):
                raise ValueError('GITHUB_DOWNLOAD_HTTP_'+str(error.code)) from None
            location = error.headers.get('Location', '')
            parsed = urllib.parse.urlsplit(location)
            if parsed.scheme != 'https' or parsed.hostname not in {'release-assets.githubusercontent.com','objects.githubusercontent.com'}:
                raise ValueError('UNEXPECTED_DOWNLOAD_REDIRECT')
            download = urllib.request.urlopen(location, timeout=120)  # Authorization is not forwarded.
        h = hashlib.sha256()
        size = 0
        with download:
            for block in iter(lambda:download.read(1024*1024), b''):
                size += len(block)
                h.update(block)
        if size != row['bytes'] or h.hexdigest() != row['sha256']:
            raise ValueError('REMOTE_ARCHIVE_HASH_MISMATCH')
        result['assets'].append(dict(name=file.name, bytes=size, sha256=row['sha256'],
            id=existing['id'], download_verified=True, url=existing['browser_download_url']))
        print(json.dumps(dict(asset=file.name, verified_bytes=size)), flush=True)
    result['status'] = 'REMOTE_SOURCE_AND_ARCHIVE_VERIFIED'
    (OUT / 'remote-verification.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--publish-commit')
    args = parser.parse_args()
    try:
        publish(args.publish_commit) if args.publish_commit else prepare()
    except Exception as error:
        print(json.dumps(dict(status='FAILED', reason=str(error) if isinstance(error, ValueError) else type(error).__name__)), flush=True)
        raise SystemExit(1)
