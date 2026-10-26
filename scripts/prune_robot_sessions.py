# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Prune robot-side fleet session directories whose PC copy is complete (operator-confirmed, read-only until DELETE).

The robot keeps every live session under ~/.local/share/twinpulse/fleet/sessions/<operation_id> and never prunes it;
on 2026-10-26 that filled the SD card (15 GB, 0 free) and the worker's journal write failed mid-session (PHYS09).
This tool lists robot session directories that (a) have a PC receipt with complete=true under
%LOCALAPPDATA%/TwinPulse/runtime/devices/local/physical-live/<operation_id>/receipt.json, (b) are older than
--days (default 1), (c) are not the newest robot session, and deletes ONLY those after the operator types DELETE.
Incomplete or missing PC receipts are never deleted. Nothing else on the robot is touched; no app, no motion.

usage: python scripts/prune_robot_sessions.py [--days 1] [--yes] [--robot-label "Imported existing settings"]
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

SESSIONS = '~/.local/share/twinpulse/fleet/sessions'


def ssh_base(registry_path, label_prefix):
    registry = json.load(open(registry_path, encoding='utf-8'))
    robot = next((r for r in registry['robots'] if r['label'].startswith(label_prefix)), None)
    if robot is None:
        raise SystemExit('ROBOT_NOT_REGISTERED: no robot label starts with %r' % label_prefix)
    ep = robot['endpoint']
    key = Path.home() / '.ssh/twinpulse-burger/id_ed25519_automation'
    known = Path.home() / '.ssh/known_hosts'
    ssh = shutil.which('ssh.exe') or shutil.which('ssh')
    if not (ssh and key.is_file() and known.is_file() and ep.get('host') and ep.get('user')):
        raise SystemExit('PC_SSH_PREREQUISITE_MISSING')
    base = [ssh, '-T', '-i', str(key), '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
            '-o', 'UserKnownHostsFile=' + str(known), '-o', 'ConnectTimeout=8', '-o', 'ForwardAgent=no', '-o', 'ClearAllForwardings=yes',
            '-p', str(int(ep.get('port', 22))), '%s@%s' % (ep['user'], ep['host'])]
    return base, ep['host']


def run(base, host, command, timeout=900):
    result = subprocess.run(base + [command], capture_output=True, text=True, timeout=timeout)
    return (result.stdout + result.stderr).replace(host, '<robot>'), result.returncode


def pc_receipts(root):
    receipts = {}
    for directory in root.glob('*'):
        receipt = directory / 'receipt.json'
        if not directory.is_dir() or not receipt.is_file():
            continue
        try:
            value = json.load(open(receipt, encoding='utf-8'))
        except (OSError, ValueError):
            continue
        receipts[directory.name] = dict(complete=value.get('complete') is True, error=value.get('error'),
                                        bytes=sum(f.stat().st_size for f in directory.glob('*') if f.is_file()))
    return receipts


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--days', type=float, default=1.0, help='only sessions whose robot directory is older than this many days')
    parser.add_argument('--yes', action='store_true', help='skip the DELETE prompt (for a reviewed, scripted run)')
    parser.add_argument('--robot-label', default='Imported existing settings', help='registry label prefix of the physical robot')
    args = parser.parse_args()
    local = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData/Local'))) / 'TwinPulse/runtime/devices/local'
    base, host = ssh_base(local / 'robot-registry.json', args.robot_label)
    receipts = pc_receipts(local / 'physical-live')
    listing, code = run(base, host, 'cd %s 2>/dev/null || exit 9; for d in *; do [ -d "$d" ] && printf "%%s %%s %%s\\n" "$d" "$(du -sm "$d" | cut -f1)" "$(stat -c %%Y "$d")"; done' % SESSIONS)
    if code == 9:
        raise SystemExit('ROBOT_SESSIONS_DIR_MISSING')
    rows = []
    for line in listing.splitlines():
        parts = line.split()
        if len(parts) == 3 and len(parts[0]) == 32 and parts[0].isalnum():
            rows.append((parts[0], int(parts[1]), int(parts[2])))
    if not rows:
        print('no robot sessions found; raw listing head:', ' | '.join(listing[:400].splitlines())); return 0
    newest = max(rows, key=lambda r: r[2])[0]
    cutoff = time.time() - args.days * 86400
    before, _ = run(base, host, 'df -h / | tail -1; du -sh %s' % SESSIONS)
    print('BEFORE\n' + before.strip())
    candidates, kept = [], []
    for sid, mb, mtime in sorted(rows, key=lambda r: r[2]):
        receipt = receipts.get(sid)
        why = ('newest session' if sid == newest else 'younger than %.1f day(s)' % args.days if mtime > cutoff else
               'no PC receipt' if receipt is None else None if receipt['complete'] else 'PC receipt incomplete (%s)' % (receipt['error'] or 'no error text'))
        (kept if why else candidates).append((sid, mb, why))
    print('\nDELETE CANDIDATES (robot dir age > %.1f d, PC receipt complete):' % args.days)
    for sid, mb, _ in candidates:
        print('  %s %5d MB' % (sid, mb))
    print('  total %d sessions, %d MB' % (len(candidates), sum(mb for _, mb, _ in candidates)))
    print('\nKEPT:')
    for sid, mb, why in kept:
        print('  %s %5d MB  %s' % (sid[:8], mb, why))
    if not candidates:
        print('\nnothing to delete'); return 0
    if not args.yes:
        try:
            answer = input('\nType DELETE to remove the %d candidate directories on the robot: ' % len(candidates))
        except EOFError:
            answer = ''
        if answer.strip() != 'DELETE':
            print('aborted, nothing removed'); return 1
    ids = ' '.join(sid for sid, _, _ in candidates)
    script = ('cd %s || exit 9; for d in %s; do if [ -d "$d" ]; then rm -r -- "$d" && echo "removed ${d:0:8}" || echo "FAILED ${d:0:8}"; '
              'else echo "MISSING ${d:0:8}"; fi; done' % (SESSIONS, ids))
    out, _ = run(base, host, script)
    print('\n' + out.strip())
    after, _ = run(base, host, 'df -h / | tail -1; du -sh %s; ls %s | wc -l' % (SESSIONS, SESSIONS))
    print('\nAFTER\n' + after.strip())
    return 0


if __name__ == '__main__':
    sys.exit(main())
