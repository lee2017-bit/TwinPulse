# SPDX-License-Identifier: Apache-2.0
"""Hash-bind actual RoomPlan records and explicitly derived negative gate tests."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--attempt', required=True)
    parser.add_argument('--base-attempt', required=True)
    args = parser.parse_args()
    out, a, b = args.output_root.resolve(), args.attempt, args.base_attempt
    if any(len(v) != 2 or not v.isascii() or not v.isdecimal() for v in (a, b)):
        raise ValueError('Two-digit attempts required')

    def ref(path):
        return dict(path=path.relative_to(out).as_posix(), sha256=sha256(path.read_bytes()).hexdigest())

    active = read(Path(os.environ['LOCALAPPDATA']) / 'TwinPulse/installed/active-release.json')
    cycle_path = out / f'roomplan-saved-cycle{a}.json'
    cycle = read(cycle_path)
    if (cycle.get('status') != 'PASS' or cycle.get('issues') != [] or cycle.get('release_id') != active['release_id']
            or cycle.get('source_sha256') != active['source_manifest_sha256']):
        raise ValueError('Actual current saved-source/final-export/shutdown cycle required')
    copied = read(out / f'model-evidence{a}/copy-receipt.json')
    refs = {role: ref(out / name) for role, name in dict(base_gate=f'gate-result{b}.json',
            **{role: f'roomplan-{phase}-{a}/result.json' for role, phase in
               (('import', 'import'), ('ai_edit', 'ai-edit'), ('sim', 'sim'), ('cold', 'cold'))}).items()}
    for role in ('model_request', 'model_result', 'model_diagnostic', 'model_job', 'model_ledger'):
        refs[role] = copied['refs'][role]
        if ref(out / refs[role]['path']) != refs[role]:
            raise ValueError('Exact frozen model original changed')
    tools = ['verify_roomplan_preparation_gate.py', 'verify_roomplan_ui_20261023.mjs',
             'roomplan_edit_observation.mjs', 'roomplan_response_gate.mjs',
             'verify_roomplan_saved_cycle_20261023.py', 'run_roomplan_ready_ui_20261023.ps1']
    manifest = dict(release_id=active['release_id'], source_sha256=active['source_manifest_sha256'],
                    source_usd_sha256=cycle['source_usd_sha256'], refs=refs, saved_cycle=ref(cycle_path),
                    acceptance_tools={name: sha256((ROOT / 'scripts' / name).read_bytes()).hexdigest() for name in tools})
    source = out / f'roomplan-evidence-manifest{a}.json'
    target = out / f'roomplan-gate-result{a}.json'
    write(source, manifest)
    run = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/verify_roomplan_preparation_gate.py'),
                          '--manifest', str(source), '--output', str(target)], cwd=ROOT, capture_output=True, text=True)
    (out / f'roomplan-gate-run{a}.log').write_text(run.stdout + run.stderr, encoding='utf-8')
    gate = read(target)
    if run.returncode or gate['status'] != 'READY_FOR_SUPERVISED_POWERED_TEST':
        print(json.dumps(dict(status=gate['status'], issues=gate['issues'])))
        return 1
    original_hashes = {role: ref(out / row['path']) for role, row in refs.items()}
    negatives = []
    for kind in ('original-ai03-failure', 'missing-60s', 'missing-own-edit-proof', 'missing-model-ledger'):
        derived = deepcopy(manifest)
        derived['classification'] = 'EXPLICIT_GATE_NEGATIVE_NOT_APP_OUTPUT:' + kind
        if kind == 'original-ai03-failure':
            derived['refs']['ai_edit'] = ref(out / 'roomplan-ai-edit-03/result.json')
            expected = 'UI_NOT_WHOLE_PASS:ai_edit'
        elif kind == 'missing-model-ledger':
            derived['refs'].pop('model_ledger')
            expected = 'MISSING_OR_INVALID_REFERENCE:model_ledger'
        else:
            role = 'sim' if kind == 'missing-60s' else 'ai_edit'
            row = deepcopy(read(out / refs[role]['path']))
            row['classification'] = derived['classification']
            if kind == 'missing-60s':
                name = 'Shared imported mask and 60-second uninterrupted visible hold'
                row['steps'] = [s for s in row['steps'] if s['name'] != name]
                expected = 'MISSING_OR_FAILED_STEP:sim:' + name
            else:
                row.pop('edit_transactions', None)
                expected = 'MODEL_APPLY_UNDO_PARENT_CHAIN_UNPROVEN'
            p = out / f'roomplan-negative-{kind}-derived{a}.json'
            write(p, row)
            derived['refs'][role] = ref(p)
        p = out / f'roomplan-negative-{kind}-manifest{a}.json'
        target = out / f'roomplan-negative-{kind}-result{a}.json'
        write(p, derived)
        run = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/verify_roomplan_preparation_gate.py'),
                              '--manifest', str(p), '--output', str(target)], cwd=ROOT, capture_output=True, text=True)
        (out / f'roomplan-negative-{kind}-run{a}.log').write_text(run.stdout + run.stderr, encoding='utf-8')
        checked = read(target)
        rejected = run.returncode == 1 and checked['status'] == 'NOT_READY' and expected in checked['issues']
        negatives.append(dict(kind=kind, status='PASS_NEGATIVE_REJECTED' if rejected else 'FAIL',
                              expected=expected, issues=checked['issues'], manifest=ref(p), result=ref(target)))
    unchanged = all(ref(out / refs[role]['path']) == original_hashes[role] for role in refs)
    value = dict(status='PASS' if unchanged and all(n['status'] == 'PASS_NEGATIVE_REJECTED' for n in negatives) else 'FAIL',
                 classification='EVIDENCE_GATE_NEGATIVES_NOT_NEW_APP_OR_PHYSICAL_TEST',
                 original_records_unchanged=unchanged, tests=negatives)
    write(out / f'roomplan-gate-negatives{a}.json', value)
    print(json.dumps(dict(status=gate['status'], negative_status=value['status'], issues=gate['issues'])))
    return 0 if value['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
