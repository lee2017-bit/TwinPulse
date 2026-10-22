# SPDX-License-Identifier: Apache-2.0
"""Inventory the authorized private source checkpoint without staging or pushing.

Protect raw data by a code/docs-only allowlist and never print matched secrets.
Pattern checks are bounded safeguards, not a proof that all private information
is absent. Existing personal-path references are counted, not published anew as
raw datasets. Original photos/USD/runtime/output and unrelated PNGs are excluded.
"""
import argparse
import ast
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
import runpy
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PREFIXES = ('apps/', 'packages/', 'scripts/', 'tests/', 'extensions/', 'docs/')
SOURCE_SUFFIXES = {'.py', '.mjs', '.cjs', '.js', '.ts', '.tsx', '.css', '.ps1', '.cpp', '.hpp',
                   '.h', '.txt', '.md', '.json', '.toml', '.xml', '.sh', '.patch', '.yaml', '.yml'}
SECRET_PATTERNS = {
    'github_token': re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b'),
    'provider_token': re.compile(r'\bsk-[A-Za-z0-9_-]{25,}\b'),
    'private_key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'literal_auth_header': re.compile(r'Authorization\s*:\s*(?:Bearer|Basic)\s+[A-Za-z0-9/+_.=-]{20,}', re.I),
}


def git(*args):
    return subprocess.check_output(['git', '-c', 'core.safecrlf=false', *args], cwd=ROOT)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('NEW_AUDIT_DIRECTORY_REQUIRED')
    tracked = {p.decode('utf-8') for p in git('diff', 'HEAD', '--name-only', '-z').split(b'\0') if p}
    untracked = {p.decode('utf-8') for p in git('ls-files', '--others', '--exclude-standard', '-z').split(b'\0') if p}
    candidates, excluded, issues = [], [], []
    python_files = 0
    private_paths = 0
    for name in sorted(tracked | untracked):
        path = ROOT / name
        allowed = (name in {'.gitattributes', 'AGENTS.md', 'README.md'} or name.startswith(PREFIXES)) and (
            path.suffix in SOURCE_SUFFIXES or path.name in {'.gitattributes', 'CMakeLists.txt', 'LICENSE', 'NOTICE'})
        if not allowed:
            excluded.append(dict(path=name, reason='OUTSIDE_SOURCE_DOCS_ALLOWLIST'))
            continue
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            issues.append(dict(path=name, category='NONREGULAR_OR_OUT_OF_SCOPE'))
            continue
        raw = path.read_bytes()
        if len(raw) > 8 * 1024 * 1024:
            issues.append(dict(path=name, category='SOURCE_FILE_TOO_LARGE'))
            continue
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            issues.append(dict(path=name, category='NONTEXT_SOURCE'))
            continue
        for category, pattern in SECRET_PATTERNS.items():
            for match in pattern.finditer(text):
                issues.append(dict(path=name, category=category,
                                   line=text.count('\n', 0, match.start()) + 1))
        private_paths += len(re.findall(r'(?:[A-Za-z]:[\\/]+Users[\\/]+|/home/)', text))
        if path.suffix == '.py':
            ast.parse(text, filename=name)
            python_files += 1
        candidates.append(dict(path=name, bytes=len(raw), sha256=sha256(raw).hexdigest(),
                               origin='tracked_change' if name in tracked else 'new_source'))
    # This verifier checks every repository member of the installed source
    # manifest, not just three recently edited files. It runs no App or robot.
    identity = runpy.run_path(str(ROOT / 'scripts/verify_robot_lineage_offline.py'))['source_receipt']()
    result = dict(schema='private-source-checkpoint-audit-1.0',
                  status='PASS_PRIVATE_SOURCE_SCOPE' if not issues else 'FAIL',
                  head=git('rev-parse', 'HEAD').decode().strip(), **identity,
                  candidate_count=len(candidates), candidate_bytes=sum(c['bytes'] for c in candidates),
                  python_ast_checked=python_files, candidate_by_root=dict(Counter(c['path'].split('/')[0] for c in candidates)),
                  secret_pattern_findings=issues, excluded=excluded,
                  existing_personal_path_reference_count=private_paths,
                  private_target_required=True, public_clearance=False,
                  staging_or_git_mutation=False, candidates=candidates,
                  limits='Bounded pattern/source checks; not public-media/rights clearance or new UI/hardware acceptance.')
    args.output.mkdir(parents=True)
    (args.output / 'audit.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    (args.output / 'pathspecs.bin').write_bytes(b'\0'.join(c['path'].encode('utf-8') for c in candidates) + b'\0')
    print(json.dumps({k: v for k, v in result.items() if k != 'candidates'}))
    if issues:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
