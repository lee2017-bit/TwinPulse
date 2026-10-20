# SPDX-License-Identifier: Apache-2.0
"""Read-only derivation from original UI08 receipts; never repairs original evidence."""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/robot-protocol-prep-20261020'
UI = sys.argv[1] if len(sys.argv) > 1 else 'actual-ui08'
if UI not in {'actual-ui08', 'actual-ui11'}:
    raise ValueError('Explicit reviewed UI run required')


def check(receipts, result):
    issues, rows = [], []
    stops = [r for r in receipts['requests'] if r['action'] in {'stop', 'stop_all'}]
    if len([r for r in stops if r['action'] == 'stop']) < 5:
        issues.append('MISSING_REQUIRED_INDIVIDUAL_STOPS')
    if not any(r['action'] == 'stop_all' for r in stops):
        issues.append('MISSING_STOP_ALL_RESPONSE')
    for request in stops:
        identity = request.get('request_id')
        if not identity or request.get('status') != 200 or not request.get('response_order'):
            issues.append('MISSING_EXACT_HTTP_ACK:' + str(identity))
            continue
        targets = [r for r in request.get('result_robots', []) if r.get('operation_id')
                   and (request['action'] == 'stop_all' or r['robot_id'] == request['robot_id'])]
        if len(targets) != (2 if request['action'] == 'stop_all' else 1):
            issues.append('MISSING_ACK_TARGET:' + identity)
        for robot in targets:
            rid = robot['robot_id']
            before = [r for s in receipts['samples'] if s['order'] < request['order']
                      for r in s['robots'] if r['robot_id'] == rid and r.get('operation_id')]
            prior = before[-1] if before else {}
            old_epoch = request.get('motion_epoch') if request['action'] == 'stop' else prior.get('motion_epoch')
            if (not old_epoch or old_epoch == robot.get('motion_epoch')
                    or not robot.get('connection_epoch') or not robot.get('operation_id')
                    or (request['action'] == 'stop' and request.get('connection_epoch') != robot['connection_epoch'])
                    or prior.get('operation_id') != robot['operation_id']
                    or prior.get('connection_epoch') != robot['connection_epoch']):
                issues.append('ACK_IDENTITY_OR_NEW_EPOCH_MISMATCH:' + identity + ':' + rid)
            applied = [s for s in receipts['samples'] if s['order'] >= request['response_order']
                       and any(all(r.get(k) == robot.get(k) for k in
                                   ('robot_id', 'operation_id', 'connection_epoch', 'motion_epoch'))
                               and r.get('applied_motion_epoch') == robot['motion_epoch']
                               and r.get('control_state') == 'PAUSED' for r in s['robots'])]
            if not applied:
                issues.append('MISSING_NEW_APPLIED_EPOCH:' + identity + ':' + rid)
            rows.append(dict(request_id=identity, action=request['action'], robot_id=rid,
                             operation_id=robot['operation_id'], connection_epoch=robot['connection_epoch'],
                             old_motion_epoch=old_epoch, new_motion_epoch=robot['motion_epoch'],
                             response_order=request['response_order'],
                             applied_observation_order=applied[0]['order'] if applied else None))
    if result.get('status') != 'PASS_SCOPED_FINAL_SAVED_SIM_AND_EXPORT' or len(result.get('steps', [])) != 8:
        issues.append('WHOLE_SCOPED_UI_JOURNEY_NOT_PASS')
    for export in result.get('exports', []):
        file = OUT / UI / 'downloads' / export['file']
        raw = file.read_bytes()
        record = json.loads(raw)
        if (sha256(raw).hexdigest() != export['sha256'] or len(raw) != export['bytes']
                or record['operation_id'] != export['operation_id'] or not record['manifest']['complete']
                or record['manifest']['source_twin_context'] != export['source_twin_context']):
            issues.append('EXPORT_INTEGRITY_OR_IDENTITY_MISMATCH:' + export['operation_id'])
    if len(result.get('exports', [])) != 2:
        issues.append('MISSING_TWO_OPERATION_EXPORTS')
    return dict(status='FAIL' if issues else 'PASS_SCOPED_ACK_AND_EXPORT', issues=issues, stops=rows)


if __name__ == '__main__':
    receipt_path = OUT / UI / 'fleet-http-receipts.json'
    result_path = OUT / UI / 'result.json'
    receipts = json.loads(receipt_path.read_bytes())
    result = json.loads(result_path.read_bytes())
    positive = check(receipts, result)
    negatives = []
    missing = deepcopy(receipts)
    missing['requests'] = [r for r in missing['requests'] if r['action'] != 'stop_all']
    negatives.append(dict(case='missing_stop_all_ack', rejected=bool(check(missing, result)['issues'])))
    wrong = deepcopy(receipts)
    target = next(r for r in wrong['requests'] if r['action'] == 'stop_all')['result_robots'][0]
    target['motion_epoch'] = 'CORRUPTED_NOT_AN_OBSERVED_EPOCH'
    negatives.append(dict(case='wrong_applied_epoch', rejected=bool(check(wrong, result)['issues'])))
    corrupted = deepcopy(result)
    corrupted['exports'][0]['sha256'] = '0' * 64
    negatives.append(dict(case='corrupted_export_hash', rejected=bool(check(receipts, corrupted)['issues'])))
    missing_journey = deepcopy(result)
    missing_journey['steps'].pop()
    negatives.append(dict(case='missing_required_ui_step', rejected=bool(check(receipts, missing_journey)['issues'])))
    report = dict(schema='robot-protocol-ack-gate-1.0', checked_at_utc=datetime.now(timezone.utc).isoformat(),
                  scope='DERIVED_FROM_ORIGINAL_RECORDED_HTTP_ACKS_AND_LATER_APPLIED_SAMPLES_NOT_HARDWARE',
                  original_sha256={str(p.relative_to(OUT)): sha256(p.read_bytes()).hexdigest()
                                   for p in (receipt_path, result_path)}, **positive, negatives=negatives,
                  note='Original result/response files are not rewritten. Later telemetry confirms a preserved exact HTTP ACK; it does not backfill a missing ACK.')
    if not all(n['rejected'] for n in negatives):
        report['status'] = 'FAIL'
        report['issues'].append('NEGATIVE_GATE_DID_NOT_REJECT')
    (OUT / 'ack-gate.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(dict(status=report['status'], issues=report['issues'], targets=len(report['stops']), negatives=negatives)))
    raise SystemExit(0 if report['status'].startswith('PASS') else 1)
