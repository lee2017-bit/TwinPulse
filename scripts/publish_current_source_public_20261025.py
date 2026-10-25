# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Perform the explicitly approved repository public switch after exact main push.

No release creation/deletion, force push, credential persistence, or robot access.
This date-specific workflow is not a general automatic publication service.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.error
import urllib.request

from inspect_publication_scope_20261025 import NoRedirect, OUT, REPO, ROOT


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--commit', required=True)
    parser.add_argument('--apply-approved-public-switch', action='store_true', required=True)
    args = parser.parse_args()
    if not re.fullmatch('[0-9a-f]{40}', args.commit):
        raise ValueError('EXACT_COMMIT_REQUIRED')
    receipt = OUT / 'publication01.json'
    if receipt.exists():
        raise ValueError('NEW_RECEIPT_REQUIRED')
    original = json.loads((OUT / 'scope01.json').read_bytes())
    reviewed = json.loads((OUT / 'release-content01.json').read_bytes())
    if original['repository'] != REPO or original['secret_pattern_findings']:
        raise ValueError('HISTORY_REVIEW_REQUIRED')
    if len(reviewed['results']) != 3 or any(row['findings'] or not row['exact_remote_digest'] for row in reviewed['results']):
        raise ValueError('ORIGINAL_RELEASE_REVIEW_REQUIRED')
    if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() != args.commit:
        raise ValueError('CURRENT_HEAD_MISMATCH')
    credential = subprocess.run(['git', '-c', 'credential.interactive=false', 'credential', 'fill'],
        cwd=ROOT, input='protocol=https\nhost=github.com\npath=' + REPO + '.git\n\n',
        text=True, capture_output=True, timeout=30,
        env={**os.environ, 'GCM_INTERACTIVE': 'Never', 'GIT_TERMINAL_PROMPT': '0'})
    fields = dict(line.split('=', 1) for line in credential.stdout.splitlines() if '=' in line)
    token = fields.get('password')
    if credential.returncode or not token:
        raise ValueError('EXISTING_GIT_CREDENTIAL_UNAVAILABLE')
    opener = urllib.request.build_opener(NoRedirect())

    def api(route='', *, authenticated=True, payload=None):
        headers = {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28',
                   'User-Agent': 'TwinPulse-user-approved-public-switch'}
        if authenticated:
            headers['Authorization'] = 'Bearer ' + token
        body = None
        if payload is not None:
            body = json.dumps(payload).encode()
            headers['Content-Type'] = 'application/json'
        request = urllib.request.Request('https://api.github.com/repos/' + REPO + route, body,
            headers=headers, method='PATCH' if payload is not None else 'GET')
        try:
            with opener.open(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            raise ValueError('GITHUB_HTTP_' + str(error.code)) from None

    repository = api()
    if repository['full_name'] != REPO or not repository.get('permissions', {}).get('admin'):
        raise ValueError('EXPECTED_ADMIN_TARGET_REQUIRED')
    before = api('/branches/main')
    if before['commit']['sha'] != args.commit:
        raise ValueError('EXACT_REMOTE_MAIN_REQUIRED')
    local_tree = subprocess.check_output(['git', 'rev-parse', 'HEAD^{tree}'], cwd=ROOT, text=True).strip()
    if before['commit']['commit']['tree']['sha'] != local_tree:
        raise ValueError('EXACT_REMOTE_TREE_REQUIRED')
    releases = api('/releases?per_page=100')
    def release_identity(rows):
        return sorted((r['id'], r.get('tag', r.get('tag_name')),
                       sorted((a['id'], a['name'], a.get('bytes', a.get('size')), a.get('digest')) for a in r['assets'])) for r in rows)
    if release_identity(releases) != release_identity(original['releases']):
        raise ValueError('RELEASE_INVENTORY_CHANGED_REVIEW_AGAIN')
    switched = False
    if repository['private']:
        updated = api(payload={'private': False})
        if updated.get('private') is not False or updated['full_name'] != REPO:
            raise ValueError('PUBLIC_SWITCH_NOT_CONFIRMED')
        switched = True
    public = api(authenticated=False)
    public_branch = api('/branches/main', authenticated=False)
    public_status = api('/contents/docs/STATUS_2026-10-25.md?ref=main', authenticated=False)
    if public.get('private') is not False or public.get('visibility') != 'public' or public_branch['commit']['sha'] != args.commit:
        raise ValueError('ANONYMOUS_PUBLIC_MAIN_VERIFICATION_FAILED')
    expected_blob = subprocess.check_output(['git', 'rev-parse', 'HEAD:docs/STATUS_2026-10-25.md'], cwd=ROOT, text=True).strip()
    if public_status.get('sha') != expected_blob:
        raise ValueError('ANONYMOUS_PUBLIC_DOCUMENT_MISMATCH')
    result = dict(schema='public-source-publication-1.0', status='PUBLIC_REMOTE_MAIN_TREE_AND_DOCUMENT_VERIFIED',
        verified_at_utc=datetime.now(timezone.utc).isoformat(), repository=REPO, url=public['html_url'],
        private=False, visibility=public['visibility'], visibility_changed=switched, branch='main',
        commit=args.commit, tree=local_tree, anonymous_access_verified=True,
        public_summary_url=public_status['html_url'], public_summary_git_blob=expected_blob,
        unchanged_release_count=len(releases), release_assets_created_or_deleted=0,
        credentials_persisted=False, raw_photos_usd_runtime_uploads=0,
        source_review_scope='Source/docs/tests only; original raw evidence excluded; product outcomes remain partial/failed.',
        content_review_sha256=hashlib.sha256((OUT / 'release-content01.json').read_bytes()).hexdigest())
    with receipt.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps(result))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps(dict(status='FAILED', reason=str(error) if isinstance(error, ValueError) else type(error).__name__)))
        raise SystemExit(1)
