# SPDX-License-Identifier: Apache-2.0
"""GET-only private GitHub target check using the existing in-memory Git helper.

No token/header/helper output is printed or persisted. No repository mutation,
release creation or visibility change. A separately authorized git push owns
the actual source update.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = 'lee2017-bit/TwinPulse'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('NEW_RECEIPT_REQUIRED')
    credential = subprocess.run(
        ['git', '-c', 'credential.interactive=false', 'credential', 'fill'],
        cwd=ROOT, input='protocol=https\nhost=github.com\npath=' + REPOSITORY + '.git\n\n',
        text=True, capture_output=True, timeout=30,
        env={**os.environ, 'GCM_INTERACTIVE': 'Never', 'GIT_TERMINAL_PROMPT': '0'})
    fields = dict(line.split('=', 1) for line in credential.stdout.splitlines() if '=' in line)
    token = fields.get('password')
    if credential.returncode or not token:
        raise ValueError('EXISTING_GIT_CREDENTIAL_UNAVAILABLE')
    headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
               'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'TwinPulse-authorized-target-inspection'}
    opener = urllib.request.build_opener(NoRedirect())

    def get(route):
        request = urllib.request.Request('https://api.github.com/repos/' + REPOSITORY + route,
                                         headers=headers, method='GET')
        try:
            with opener.open(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            raise ValueError('GITHUB_HTTP_' + str(error.code)) from None

    repository = get('')
    if repository.get('full_name') != REPOSITORY or repository.get('private') is not True:
        raise ValueError('EXISTING_PRIVATE_REPOSITORY_REQUIRED_NO_VISIBILITY_CHANGE')
    branch = get('/branches/main')
    result = dict(schema='private-github-target-inspection-1.0', checked_at_utc=datetime.now(timezone.utc).isoformat(),
                  repository=repository['full_name'], private=repository['private'],
                  default_branch=repository['default_branch'], url=repository['html_url'],
                  push_permission=repository.get('permissions', {}).get('push'),
                  main_commit=branch['commit']['sha'], main_tree=branch['commit']['commit']['tree']['sha'],
                  branch_protected=branch['protected'],
                  mutation=False, credentials_persisted=False)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps(result))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps(dict(status='FAILED', reason=str(error) if isinstance(error, ValueError) else type(error).__name__)))
        raise SystemExit(1)
