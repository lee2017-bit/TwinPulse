# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
r"""List (and, only after the operator types DELETE, remove) old installed TwinPulse releases.

Every `TwinPulse.exe --install` adds an immutable release (~290 MB on disk, ~460 MB apparent) under
%LOCALAPPDATA%\TwinPulse\installed\releases; 32 of them held 9.3 GB on 2026-10-27. This tool never
touches user data, the active release, the protected evidence builds or the newest releases:

  kept   the active release (active-release.json), the PROTECTED ids below (PHYS08/PHYS09 evidence,
         builds 33 and 50-54 of 2026-10-26), the newest KEEP_NEWEST releases, and anything not shaped
         like a release id or sitting behind a reparse point
  shown  everything else, with its apparent size (identical desktop files are hard-linked between
         releases, so the freed space is at most the printed total)

Dry run is the default and prints the plan only. `--delete` asks for the word DELETE on the console;
there is no --yes. Refuses while TwinPulse.exe is running. Old active-release.previous.*.json
pointers and update journals are tiny and are left alone (they are the install history).

usage: python scripts/prune_old_builds.py [--delete] [--keep-newest 3]
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

RELEASE_ID = re.compile(r'^\d{8}T\d{6}Z-[0-9a-f]{12}$')
PROTECTED = (
    '20261025T162952Z-62f7a3f1e698',  # PHYS08 evidence build
    '20261025T120155Z-cb02064b5674',  # PHYS07 evidence build
    '20261026T034429Z-7321cb659b9d',  # 2026-10-26 build 33
    '20261026T120941Z-dda717ce494f',  # build 50
    '20261026T123129Z-9f16781d6049',  # build 51
    '20261026T125513Z-8ff43ad1f4dc',  # build 52 (PHYS09)
    '20261026T231114Z-339c8cce22c8',  # build 53 (session gate UI)
)
KEEP_NEWEST = 3


def install_root():
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData/Local'))) / 'TwinPulse/installed'


def active_release(root):
    pointer = root / 'active-release.json'
    if not pointer.is_file():
        raise SystemExit('ACTIVE_RELEASE_POINTER_MISSING: %s' % pointer)
    return json.loads(pointer.read_text(encoding='utf-8-sig')).get('release_id') or ''


def apparent_size(directory):
    total = 0
    for base, dirs, files in os.walk(directory):
        for name in files:
            try:
                total += (Path(base) / name).stat().st_size
            except OSError:
                pass
    return total


def plan(root, *, active, protected=PROTECTED, keep_newest=KEEP_NEWEST):
    """Return (candidates, kept): lists of (release_id, reason) where reason is None for a candidate."""
    releases = root / 'releases'
    if not releases.is_dir():
        raise SystemExit('RELEASE_STORE_MISSING: %s' % releases)
    names = sorted(p.name for p in releases.iterdir() if p.is_dir() and RELEASE_ID.match(p.name))
    newest = set(names[-keep_newest:]) if keep_newest > 0 else set()
    candidates, kept = [], []
    for name in names:
        path = releases / name
        why = ('active release' if name == active else 'protected evidence build' if name in protected else
               'newest %d' % keep_newest if name in newest else
               'reparse point (not touched)' if path.is_symlink() or (path.stat().st_file_attributes & 0x400) else None)
        (kept if why else candidates).append((name, why))
    return candidates, kept


def twinpulse_running():
    try:
        out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq TwinPulse.exe'], stdout=subprocess.PIPE, text=True, check=False).stdout
    except OSError:
        return False
    return 'TwinPulse.exe' in out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--delete', action='store_true', help='after the listing, ask for DELETE and remove the candidates (default: dry run)')
    parser.add_argument('--keep-newest', type=int, default=KEEP_NEWEST, help='always keep this many newest releases (default %d)' % KEEP_NEWEST)
    parser.add_argument('--root', type=Path, default=None, help=argparse.SUPPRESS)  # tests only
    args = parser.parse_args(argv)
    root = args.root or install_root()
    active = active_release(root)
    candidates, kept = plan(root, active=active, keep_newest=args.keep_newest)
    sizes = {name: apparent_size(root / 'releases' / name) for name, _ in candidates}
    print('install store: %s' % root)
    print('active release: %s' % (active or '(none)'))
    print('\nDELETE CANDIDATES (%s):' % ('dry run, nothing removed' if not args.delete else 'after DELETE'))
    for name, _ in candidates:
        print('  %s %6.0f MB' % (name, sizes[name] / 1e6))
    print('  total %d releases, %.1f GB apparent (hard-linked desktop files are counted per release)' % (len(candidates), sum(sizes.values()) / 1e9))
    print('\nKEPT:')
    for name, why in kept:
        print('  %s  %s' % (name, why))
    if not candidates:
        print('\nnothing to delete'); return 0
    if not args.delete:
        print('\ndry run; rerun with --delete to remove the candidates above (asks for DELETE)'); return 0
    if twinpulse_running():
        print('\nTwinPulse.exe is running; exit the App first. nothing removed'); return 2
    try:
        answer = input('\nType DELETE to remove the %d candidate releases: ' % len(candidates))
    except EOFError:
        answer = ''
    if answer.strip() != 'DELETE':
        print('aborted, nothing removed'); return 1
    failed = 0
    for name, _ in candidates:
        path = root / 'releases' / name
        if path.is_symlink():
            print('  skipped %s (reparse point)' % name); continue
        try:
            shutil.rmtree(path)
            print('  removed %s' % name)
        except OSError as error:
            failed += 1
            print('  FAILED %s: %s' % (name, error))
    remaining = sorted(p.name for p in (root / 'releases').iterdir() if p.is_dir())
    print('\n%d releases remain; %d failed' % (len(remaining), failed))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
