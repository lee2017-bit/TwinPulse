# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Archive the approved frozen SIM ZIP to the existing PRIVATE repository.

Uses the existing Git credential helper in memory. Never prints/stores secrets.
No public switch, force push, product execution, robot or provider call.
"""
import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REPO = 'lee2017-bit/TwinPulse'
TAG = 'sim-alpha-2026-10-18-archive'
BUILD = '20261018T044930Z-d0d4e62d6701'
ZIP_SHA = 'b40e498fc19eda8b045152c92cddc91def3b90f824e047146a47f01bc1f1dd8f'
ZIP = ROOT / 'artifacts/robot-focused-test-20261018/build06' / ('TwinPulse-Windows-x64-0.1.0-alpha.1-' + BUILD + '.zip')


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--commit', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9a-f]{40}', args.commit):
        raise ValueError('COMMIT_SHA_REQUIRED')
    remote = subprocess.check_output(['git','ls-remote','origin','refs/heads/main'], cwd=ROOT, text=True).split()[0]
    if remote != args.commit or sha(ZIP) != ZIP_SHA:
        raise ValueError('REMOTE_SOURCE_OR_LOCAL_ARCHIVE_MISMATCH')
    credential = subprocess.run(['git','-c','credential.interactive=false','credential','fill'],
        cwd=ROOT, input='protocol=https\nhost=github.com\npath='+REPO+'.git\n\n',
        text=True, capture_output=True, env={**os.environ,'GCM_INTERACTIVE':'Never','GIT_TERMINAL_PROMPT':'0'})
    fields = dict(line.split('=',1) for line in credential.stdout.splitlines() if '=' in line)
    token = fields.get('password')
    if credential.returncode or not token:
        raise ValueError('EXISTING_GIT_CREDENTIAL_UNAVAILABLE')
    headers = {'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json',
        'X-GitHub-Api-Version':'2022-11-28','User-Agent':'TwinPulse-approved-private-preservation'}
    opener = urllib.request.build_opener(NoRedirect())

    def api(route, data=None):
        url='https://api.github.com/repos/'+REPO+route
        body=json.dumps(data).encode() if data is not None else None
        request=urllib.request.Request(url, body, headers | ({'Content-Type':'application/json'} if body is not None else {}))
        try:
            with opener.open(request, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code == 404 and data is None:
                return None
            raise ValueError('GITHUB_HTTP_'+str(error.code)) from None

    repository=api('')
    if not repository or repository.get('full_name') != REPO or repository.get('private') is not True:
        raise ValueError('PRIVATE_REPOSITORY_REQUIRED')
    release=api('/releases/tags/'+TAG)
    if release is None:
        release=api('/releases',dict(tag_name=TAG,target_commitish=args.commit,
            name='Frozen SIM acceptance archive — 2026-10-18 (not hardware-ready)',
            body=(ROOT/'docs/releases/SIM_ALPHA_ARCHIVE_2026-10-18.md').read_text(encoding='utf-8'),
            draft=False,prerelease=True,make_latest='false'))
    if release.get('tag_name') != TAG or not release.get('prerelease'):
        raise ValueError('ARCHIVE_RELEASE_IDENTITY_MISMATCH')
    result=dict(schema='github-private-preservation-1.0',repository=REPO,private=True,
        source_commit=args.commit,release_url=release['html_url'],release_id=release['id'],tag=TAG,assets=[])
    sources=[ZIP, ZIP.parent/'SHA256SUMS.txt']
    for source in sources:
        digest=sha(source)
        existing=next((a for a in release.get('assets',[]) if a['name']==source.name),None)
        if existing is None:
            connection=http.client.HTTPSConnection('uploads.github.com',timeout=120)
            route='/repos/'+REPO+'/releases/'+str(release['id'])+'/assets?'+urllib.parse.urlencode({'name':source.name})
            connection.putrequest('POST',route)
            for key,value in (headers | {'Content-Type':'application/octet-stream','Content-Length':str(source.stat().st_size)}).items():
                connection.putheader(key,value)
            connection.endheaders()
            with source.open('rb') as stream:
                for block in iter(lambda:stream.read(1024*1024),b''):
                    connection.send(block)
            response=connection.getresponse()
            if response.status != 201:
                raise ValueError('GITHUB_ASSET_UPLOAD_HTTP_'+str(response.status))
            existing=json.load(response);connection.close()
        asset_url='https://api.github.com/repos/'+REPO+'/releases/assets/'+str(existing['id'])
        request=urllib.request.Request(asset_url,headers=headers | {'Accept':'application/octet-stream'})
        try:
            download=opener.open(request,timeout=120)
        except urllib.error.HTTPError as error:
            if error.code not in (301,302,303,307,308):
                raise ValueError('GITHUB_ASSET_DOWNLOAD_HTTP_'+str(error.code)) from None
            location=error.headers.get('Location','')
            parsed=urllib.parse.urlsplit(location)
            if parsed.scheme!='https' or parsed.hostname not in {'release-assets.githubusercontent.com','objects.githubusercontent.com'}:
                raise ValueError('UNEXPECTED_ASSET_REDIRECT')
            # Never forward Authorization to the signed asset-storage URL.
            download=urllib.request.urlopen(location,timeout=120)
        check=hashlib.sha256();size=0
        with download:
            for block in iter(lambda:download.read(1024*1024),b''):
                size+=len(block);check.update(block)
        if check.hexdigest()!=digest or size!=source.stat().st_size:
            raise ValueError('REMOTE_ASSET_SHA_MISMATCH')
        result['assets'].append(dict(name=source.name,id=existing['id'],bytes=size,sha256=digest,download_verified=True))
    result['status']='REMOTE_SOURCE_AND_ARCHIVE_VERIFIED'
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))


if __name__=='__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps(dict(status='FAILED',reason=str(error) if isinstance(error,ValueError) else type(error).__name__)))
        raise SystemExit(1)
