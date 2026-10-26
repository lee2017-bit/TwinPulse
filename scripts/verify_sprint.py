# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Sprint test gate: every suite the sprint touches, one receipt the build checks.

PASS means (1) every REQUIRED step is fully green: byte-compile, the robot-safety suites, the
robot-path integration modules (physical session, fleet, robot health/diagnostics, link,
sprint gate, licence policy) and the web tests; and (2) every other step (core, provider, the
full integration discovery) has no failing test outside the recorded baseline.

The baseline is the failing-test set of a run the operator accepted with --set-baseline
(outputs/verify-sprint/baseline.json, machine-local, untracked). It exists because the full
suites carry environment-dependent and long-standing failures (untracked artifacts, expired
pricing metadata, Windows-only loaders); grandfathering them is reported on every receipt as
baseline_failures, never hidden, and a test that was green and turns red is a NEW failure that
fails the gate. Nothing here installs packages or touches the robot, Isaac or the network.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
RECEIPT_SCHEMA = 'twinpulse-sprint-gate-1.1'
BASELINE_SCHEMA = 'twinpulse-sprint-gate-baseline-1.0'
# Integration modules that must be fully green: the physical robot path and the gate itself.
REQUIRED_INTEGRATION_PREFIXES = (
    'test_physical_', 'test_robot_', 'test_fleet_', 'test_live_', 'test_sim_fleet_', 'test_sim_robot_',
    'test_mission_live_', 'test_bridge_robot_', 'test_manual_controller', 'test_scene_edit_physical_',
    'test_adaptive_robot_', 'test_chat_robot_', 'test_build_sprint_gate', 'test_license_policy',
)
FAILURE_LINE = re.compile(r'^(?:ERROR|FAIL): \S+ \(([^)\n]*)\)', re.M)


def required_integration_modules(root=ROOT):
    folder = root / 'tests' / 'integration'
    return sorted('tests.integration.' + p.stem for p in folder.glob('test_*.py')
                  if p.stem.startswith(REQUIRED_INTEGRATION_PREFIXES))


def steps(root=ROOT, python=sys.executable, skip_web=False):
    unittest = [python, '-B', '-m', 'unittest']
    rows = [
        dict(name='compileall', required=True, argv=[python, '-B', '-m', 'compileall', '-q', 'packages', 'scripts', 'tests']),
        dict(name='robot_safety_test_prefix', required=True,
             argv=unittest + ['discover', '-s', os.path.join('packages', 'twinpulse_robot_safety', 'tests'), '-p', 'test_*.py']),
        dict(name='robot_safety_test_suffix', required=True,
             argv=unittest + ['discover', '-s', os.path.join('packages', 'twinpulse_robot_safety', 'tests'), '-p', '*_test.py']),
        dict(name='integration_robot_path', required=True, argv=unittest + required_integration_modules(root)),
    ]
    if not skip_web:
        pnpm = shutil.which('pnpm') or 'pnpm'
        rows.append(dict(name='web', required=True, argv=[pnpm, '--dir', os.path.join('apps', 'twinpulse-web'), 'test']))
    rows += [
        dict(name='core', required=False,
             argv=unittest + ['discover', '-s', os.path.join('packages', 'twinpulse_core', 'tests'), '-p', 'test_*.py']),
        dict(name='provider', required=False,
             argv=unittest + ['discover', '-s', os.path.join('packages', 'twinpulse_provider', 'tests'), '-p', 'test_*.py']),
        dict(name='integration', required=False,
             argv=unittest + ['discover', '-s', os.path.join('tests', 'integration'), '-p', 'test_*.py']),
    ]
    return rows


def parse_failures(text):
    """Failing/erroring test ids from unittest's text report (loader failures included)."""
    return sorted(set(FAILURE_LINE.findall(text)))


def evaluate(results, baseline):
    """Gate verdict for one run.

    results: [{name, required, exit_code, failures:[ids]}]; baseline: {step: [ids]} or None.
    A required step passes only with exit code 0. A baseline-compared step passes when it has
    no failing id outside its baseline; with no baseline at all every failure is new.
    """
    baseline = baseline or {}
    new, grandfathered, fixed, verdicts = {}, {}, {}, {}
    for row in results:
        known = set(baseline.get(row['name'], []))
        failing = set(row['failures'])
        if row['required']:
            ok = row['exit_code'] == 0
            if not ok:
                new[row['name']] = sorted(failing) or ['<exit %s>' % row['exit_code']]
        else:
            unexpected = failing - known
            # A non-zero exit with no parsable failure (crash, loader abort) is a failure too.
            if row['exit_code'] != 0 and not failing:
                unexpected = {'<exit %s>' % row['exit_code']}
            ok = not unexpected
            if unexpected:
                new[row['name']] = sorted(unexpected)
            if failing & known:
                grandfathered[row['name']] = sorted(failing & known)
            if known - failing:
                fixed[row['name']] = sorted(known - failing)
        verdicts[row['name']] = 'PASS' if ok else 'FAIL'
    return dict(status='PASS' if all(v == 'PASS' for v in verdicts.values()) else 'FAIL',
                verdicts=verdicts, new_failures=new, baseline_failures=grandfathered, fixed_since_baseline=fixed)


def load_baseline(path):
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    if value.get('schema') != BASELINE_SCHEMA:
        raise ValueError('SPRINT_BASELINE_SCHEMA')
    return value


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=1, sort_keys=True), encoding='utf-8')


def git(root, *args):
    try:
        return subprocess.run(['git', '-C', str(root), *args], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ''


def run_step(row, root, log_path):
    started = time.monotonic()
    with log_path.open('w', encoding='utf-8', errors='replace') as log:
        try:
            child = subprocess.Popen(row['argv'], cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, encoding='utf-8', errors='replace')
        except OSError as exc:
            message = 'STEP_LAUNCH_FAILED: %s' % exc
            log.write(message + '\n'); print(message)
            return dict(name=row['name'], required=row['required'], exit_code=127, failures=[],
                        seconds=round(time.monotonic() - started, 1), log=str(log_path), text='')
        text = []
        for line in child.stdout:
            log.write(line); sys.stdout.write(line); text.append(line)
        code = child.wait()
    text = ''.join(text)
    return dict(name=row['name'], required=row['required'], exit_code=code, failures=parse_failures(text),
                seconds=round(time.monotonic() - started, 1), log=str(log_path))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--skip-web', action='store_true', help='skip the web (vitest) step; the receipt then cannot PASS for a build')
    parser.add_argument('--steps', default='', help='comma-separated step names to run (default all); partial runs never write latest.json')
    parser.add_argument('--set-baseline', action='store_true',
                        help='record this full run\'s failing tests of the baseline-compared steps as the new baseline (operator decision; reported on every later receipt)')
    args = parser.parse_args(argv)
    root = ROOT
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out_dir = root / 'outputs' / 'verify-sprint' / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    baseline_path = root / 'outputs' / 'verify-sprint' / 'baseline.json'
    head = git(root, 'rev-parse', 'HEAD')
    dirty = bool(git(root, 'status', '--porcelain', '--untracked-files=no'))
    rows = steps(root, sys.executable, skip_web=args.skip_web)
    wanted = {s.strip() for s in args.steps.split(',') if s.strip()}
    partial = bool(wanted) or args.skip_web
    if wanted:
        unknown = wanted - {r['name'] for r in rows}
        if unknown:
            raise SystemExit('unknown steps: %s (known: %s)' % (sorted(unknown), [r['name'] for r in rows]))
        rows = [r for r in rows if r['name'] in wanted]
    results = []
    for row in rows:
        print('== %s: %s' % (row['name'], ' '.join(map(str, row['argv']))), flush=True)
        result = run_step(row, root, out_dir / (row['name'] + '.log'))
        results.append(result)
        print('== %s exit %s in %ss, %d failing ids' % (row['name'], result['exit_code'], result['seconds'], len(result['failures'])), flush=True)
    baseline = load_baseline(baseline_path)
    if args.set_baseline:
        if partial:
            raise SystemExit('--set-baseline needs a full run (no --steps, no --skip-web)')
        baseline = dict(schema=BASELINE_SCHEMA, run_id=run_id, head=head,
                        recorded_utc=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                        failures={r['name']: r['failures'] for r in results if not r['required']})
        write_json(baseline_path, baseline)
    verdict = evaluate(results, (baseline or {}).get('failures'))
    receipt = dict(schema=RECEIPT_SCHEMA, run_id=run_id, head=head, dirty=dirty,
                   finished_utc=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                   status=verdict['status'] if not partial else 'PARTIAL',
                   partial=partial, python=sys.executable,
                   baseline_run_id=(baseline or {}).get('run_id'), baseline_head=(baseline or {}).get('head'),
                   verdicts=verdict['verdicts'], new_failures=verdict['new_failures'],
                   baseline_failures=verdict['baseline_failures'], fixed_since_baseline=verdict['fixed_since_baseline'],
                   steps=[{k: v for k, v in r.items() if k != 'text'} for r in results])
    write_json(out_dir / 'receipt.json', receipt)
    if not partial:
        write_json(root / 'outputs' / 'verify-sprint' / 'latest.json', receipt)
    print('Sprint gate %s at %s%s -> %s' % (receipt['status'], head[:12], ' (dirty tree)' if dirty else '', out_dir))
    for name, ids in verdict['new_failures'].items():
        print('!! NEW failures in %s (%d):' % (name, len(ids)))
        for value in ids:
            print('   ' + value)
    for name, ids in verdict['baseline_failures'].items():
        print('-- %s: %d baseline failures still failing (grandfathered)' % (name, len(ids)))
    for name, ids in verdict['fixed_since_baseline'].items():
        print('++ %s: %d baseline failures now pass' % (name, len(ids)))
    if baseline is None and any(not r['required'] for r in results):
        print('No baseline recorded: every failure in core/provider/integration counts as new. '
              'Review them, then rerun with --set-baseline to grandfather the environment-dependent ones.')
    return 0 if receipt['status'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
