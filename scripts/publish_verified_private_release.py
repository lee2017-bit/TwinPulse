# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Publish explicitly reviewed assets to the existing private repository only.

Uses the existing Git helper in memory, with no credential/log/header output.
Never overwrites assets, changes visibility or invokes an App/model/robot.
"""
import argparse
import http.client
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request

from preserve_github_release import NoRedirect, sha, ROOT, REPO
from verify_robot_lineage_offline import source_receipt


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--commit',required=True)
    parser.add_argument('--review',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--refresh-notes',action='store_true',help='Update only our generated notes, without touching assets')
    args=parser.parse_args()
    if not re.fullmatch('[0-9a-f]{40}',args.commit):raise ValueError('EXACT_COMMIT_REQUIRED')
    review=json.loads(args.review.read_text(encoding='utf-8-sig'))
    if review.get('schema')!='reviewed-private-release-1.0' or review.get('repository')!=REPO or review.get('private') is not True:
        raise ValueError('REVIEWED_EXISTING_PRIVATE_TARGET_REQUIRED')
    identity=source_receipt()
    if any(review.get(k)!=v for k,v in identity.items()):raise ValueError('REVIEWED_INSTALLATION_CHANGED')
    gate_path=(ROOT/review['gate_path']).resolve()
    gate=json.loads(gate_path.read_text(encoding='utf-8'))
    if not gate_path.is_relative_to(ROOT) or sha(gate_path)!=review['gate_sha256'] or gate.get('status')!='READY_FOR_SUPERVISED_POWERED_TEST':
        raise ValueError('CURRENT_GATE_REQUIRED')
    if any(gate.get(k)!=v for k,v in identity.items()):raise ValueError('GATE_IDENTITY_CHANGED')
    remote=subprocess.check_output(['git','ls-remote','origin','refs/heads/main'],cwd=ROOT,text=True).split()[0]
    if remote!=args.commit:raise ValueError('EXACT_REMOTE_SOURCE_REQUIRED')
    assets=[]
    for row in review['assets']:
        path=(ROOT/row['path']).resolve()
        if not path.is_relative_to(ROOT) or path.is_symlink() or path.is_junction() or sha(path)!=row['sha256'] or path.stat().st_size!=row['bytes']:
            raise ValueError('REVIEWED_ASSET_CHANGED')
        assets.append((path,row))
    credential=subprocess.run(['git','-c','credential.interactive=false','credential','fill'],cwd=ROOT,
        input='protocol=https\nhost=github.com\npath='+REPO+'.git\n\n',text=True,capture_output=True,
        env={**os.environ,'GCM_INTERACTIVE':'Never','GIT_TERMINAL_PROMPT':'0'})
    fields=dict(line.split('=',1) for line in credential.stdout.splitlines() if '=' in line)
    token=fields.get('password')
    if credential.returncode or not token:raise ValueError('EXISTING_GIT_CREDENTIAL_UNAVAILABLE')
    headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json',
             'X-GitHub-Api-Version':'2022-11-28','User-Agent':'TwinPulse-approved-private-release'}
    opener=urllib.request.build_opener(NoRedirect())

    def api(route,data=None,method=None):
        payload=json.dumps(data).encode() if data is not None else None
        request=urllib.request.Request('https://api.github.com/repos/'+REPO+route,payload,
            headers|({'Content-Type':'application/json'} if payload is not None else {}),method=method)
        try:
            with opener.open(request,timeout=60) as response:return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code==404 and data is None:return None
            raise ValueError('GITHUB_HTTP_'+str(error.code)) from None

    repo=api('')
    if not repo or repo.get('private') is not True or repo.get('full_name')!=REPO:raise ValueError('PRIVATE_TARGET_CHANGED')
    tag=review['tag']
    if not re.fullmatch('sim-alpha-[a-z0-9-]+',tag):raise ValueError('SCOPED_SIM_TAG_REQUIRED')
    release=api('/releases/tags/'+tag)
    if release is None:
        notes=(ROOT/review['notes_path']).read_text(encoding='utf-8')
        release=api('/releases',dict(tag_name=tag,target_commitish=args.commit,name=review['title'],
            body=notes+'\n\nVerified source commit: `'+args.commit+'`\n',draft=False,prerelease=True,make_latest='false'))
    if release.get('tag_name')!=tag or release.get('prerelease') is not True:raise ValueError('RELEASE_IDENTITY_MISMATCH')
    if args.refresh_notes:
        notes=(ROOT/review['notes_path']).read_text(encoding='utf-8')+'\n\nVerified source commit: `'+args.commit+'`\n'
        updated=api('/releases/'+str(release['id']),dict(body=notes),method='PATCH')
        if updated.get('body')!=notes or updated.get('tag_name')!=tag:raise ValueError('RELEASE_NOTES_NOT_VERIFIED')
        from hashlib import sha256
        with args.output.open('x',encoding='utf-8') as stream:
            json.dump(dict(status='PRIVATE_RELEASE_NOTES_VERIFIED',url=updated['html_url'],body_sha256=sha256(notes.encode()).hexdigest(),assets_unchanged=True),stream,indent=2)
        print(json.dumps(dict(status='PRIVATE_RELEASE_NOTES_VERIFIED',url=updated['html_url'])))
        return
    result=dict(schema='verified-private-release-upload-1.0',repository=REPO,private=True,commit=args.commit,
                **identity,release_url=release['html_url'],tag=tag,assets=[])
    for path,row in assets:
        existing=next((a for a in release.get('assets',[]) if a['name']==path.name),None)
        if existing is None:
            connection=http.client.HTTPSConnection('uploads.github.com',timeout=120)
            route='/repos/'+REPO+'/releases/'+str(release['id'])+'/assets?'+urllib.parse.urlencode({'name':path.name})
            connection.putrequest('POST',route)
            for key,value in (headers|{'Content-Type':'application/octet-stream','Content-Length':str(row['bytes'])}).items():
                connection.putheader(key,value)
            connection.endheaders()
            with path.open('rb') as stream:
                for block in iter(lambda:stream.read(1024*1024),b''):connection.send(block)
            response=connection.getresponse()
            if response.status!=201:raise ValueError('GITHUB_UPLOAD_HTTP_'+str(response.status))
            existing=json.load(response);connection.close()
        request=urllib.request.Request('https://api.github.com/repos/'+REPO+'/releases/assets/'+str(existing['id']),
                                      headers=headers|{'Accept':'application/octet-stream'})
        try:download=opener.open(request,timeout=120)
        except urllib.error.HTTPError as error:
            if error.code not in (301,302,303,307,308):raise ValueError('GITHUB_DOWNLOAD_HTTP_'+str(error.code)) from None
            location=error.headers.get('Location','');parsed=urllib.parse.urlsplit(location)
            if parsed.scheme!='https' or parsed.hostname not in {'release-assets.githubusercontent.com','objects.githubusercontent.com'}:
                raise ValueError('UNEXPECTED_ASSET_REDIRECT')
            download=urllib.request.urlopen(location,timeout=120)  # No forwarded Authorization.
        from hashlib import sha256
        check=sha256();size=0
        with download:
            for block in iter(lambda:download.read(1024*1024),b''):check.update(block);size+=len(block)
        if check.hexdigest()!=row['sha256'] or size!=row['bytes']:raise ValueError('REMOTE_ASSET_HASH_MISMATCH')
        result['assets'].append(dict(name=path.name,bytes=size,sha256=row['sha256'],
                                    url=existing['browser_download_url'],download_verified=True))
        print(json.dumps(dict(asset=path.name,verified_bytes=size)),flush=True)
    result['status']='REMOTE_SOURCE_AND_ASSETS_VERIFIED'
    with args.output.open('x',encoding='utf-8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps(dict(status='FAILED',reason=str(error) if isinstance(error,ValueError) else type(error).__name__)))
        raise SystemExit(1)
