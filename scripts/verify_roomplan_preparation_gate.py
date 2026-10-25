# SPDX-License-Identifier: Apache-2.0
"""Read-only RoomPlan addition to the current-release robot evidence gate.

Manifest parent is the evidence root. Each refs entry is {path,sha256}; original
records are never edited or reconstructed. No App, provider or device is run.
"""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path, PureWindowsPath
import re

READY = 'READY_FOR_SUPERVISED_POWERED_TEST'
ROLES = ('base_gate', 'import', 'ai_edit', 'sim', 'cold', 'model_request',
         'model_result', 'model_diagnostic', 'model_job', 'model_ledger')
CHAIR = 'Env_7869f91460f65066f8c9'
SOFA = 'Env_cc8fbcdf2f69d0ebdbd8'
EDIT_COMMITTED_CAPTION = 'Edit COMMITTED · Engine ACK confirmed · Saved yes · Current frame confirmed'
REQUIRED = {
    'import': ['Isaac ready', 'Actual New chat', 'Attach original USD and choose space purpose',
               'Explicit uncalibrated meters and local inspection', 'Adopt original space into empty project',
               'Show Twin with engine receipt'],
    'ai_edit': ['Select Chair0 and preview a bounded 0.1m edit',
                'Apply, engine ACK, durable revision and current frame',
                'Undo through the same engine/durable transaction'],
    'sim': ['Control view keeps the imported space visible', 'Explicit SIM registration at predeclared start',
            'Connect and Prepare the explicitly selected SIM', 'LiDAR streaming from the imported mesh',
            *['Manual ' + direction + ' and release stop' for direction in ('forward', 'backward', 'left', 'right')],
            'Shared imported mask and 60-second uninterrupted visible hold',
            'Original Sofa0 destination, not a substituted goal',
            'Main chat finite robot command uses the same selected SIM',
            'One full scan turn is an explicit bounded SIM command', 'LiDAR off and operation export'],
    'cold': ['Cold installed Isaac start', 'Reopen the exact imported project',
             'Explicitly show saved original geometry after cold reopen'],
}


def digest(value):
    return isinstance(value, str) and re.fullmatch('[a-f0-9]{64}', value) is not None


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def text(value):
    return isinstance(value, str) and bool(value.strip())


def read_refs(manifest, root):
    records, receipts, issues = {}, [], []
    refs = manifest.get('refs')
    if not isinstance(refs, dict):
        return records, receipts, ['MISSING_REFS']
    for role in ROLES:
        ref = refs.get(role)
        if not isinstance(ref, dict) or set(ref) != {'path', 'sha256'}:
            issues.append('MISSING_OR_INVALID_REFERENCE:' + role)
            continue
        relative = ref['path']
        try:
            if (not isinstance(relative, str) or not relative or '\\' in relative or ':' in relative
                    or PureWindowsPath(relative).is_absolute() or Path(relative).is_absolute()
                    or '..' in Path(relative).parts or not digest(ref['sha256'])):
                raise ValueError('reference')
            candidate = root / relative
            if not candidate.resolve().is_relative_to(root.resolve()):
                raise ValueError('outside root')
            if any(path.is_symlink() or path.is_junction() for path in (candidate, *candidate.parents)
                   if path.is_relative_to(root)):
                raise ValueError('linked reference')
            raw = candidate.read_bytes()
            if sha256(raw).hexdigest() != ref['sha256']:
                issues.append('EVIDENCE_HASH_MISMATCH:' + role)
                continue
            row = json.loads(raw.decode('utf-8-sig'))
            if not isinstance(row, dict):
                raise ValueError('record shape')
            records[role] = row
            receipts.append(dict(role=role, path=relative, sha256=ref['sha256']))
        except (OSError, ValueError, TypeError, UnicodeError):
            issues.append('UNREADABLE_OR_UNSAFE_REFERENCE:' + role)
    return records, receipts, issues


def responses(row):
    # A completed observation may legitimately have JSON null. Keep its HTTP
    # identity/status (especially an explicit Apply) while exposing empty
    # metadata to validators. Never normalize or rewrite the original record.
    values = row.get('responses')
    if not isinstance(values, list):
        return []
    return [{**value, 'body': value['body'] if isinstance(value.get('body'), dict) else {}}
            for value in values if isinstance(value, dict)]


def ui_issues(role, row, release, *, expected_phase=None):
    issues = []
    if row.get('phase') != (expected_phase or ('ai-edit' if role == 'ai_edit' else role)):
        issues.append('WRONG_PHASE:' + role)
    if row.get('status') not in ('PASS', 'PASS_WITH_EXPECTED_STOP_REJECTION'):
        issues.append('UI_NOT_WHOLE_PASS:' + role)
    if row.get('versions', {}).get('engine', {}).get('release_id') != release:
        issues.append('WRONG_RELEASE:' + role)
    if (row.get('errors') != [] or row.get('failed_requests') or row.get('page_errors') or row.get('video_error')
            or row.get('error') or row.get('response_gate', {}).get('status') != 'PASS'
            or row.get('response_gate', {}).get('issues')):
        issues.append('UI_ERRORS_OR_UNPROVEN_RESPONSES:' + role)
    if row.get('hardware_actions') != 0 or 'Electron/' not in row.get('user_agent', ''):
        issues.append('WRONG_ACCEPTANCE_SURFACE:' + role)
    ordered = [step for step in row.get('steps', []) if isinstance(step, dict)]
    positions = []
    for name in REQUIRED[role]:
        matches = [(index, step) for index, step in enumerate(ordered) if step.get('name') == name]
        if len(matches) != 1 or matches[0][1].get('status') != 'PASS':
            issues.append('MISSING_OR_FAILED_STEP:' + role + ':' + name)
        else:
            positions.append(matches[0][0])
    if positions != sorted(positions) or any(s.get('status') not in (None, 'PASS') for s in ordered):
        issues.append('FAILED_OR_REORDERED_STEPS:' + role)
    return issues


def hold_and_map_issues(row, source):
    issues = []
    summary = row.get('shared_map', {})
    hold = row.get('continuous', {})
    samples = row.get('continuous_display', [])
    if (summary.get('status') != 'AVAILABLE' or summary.get('kind') != 'imported'
            or summary.get('source_sha256') != source or summary.get('units_basis') != 'selected_for_sim'
            or summary.get('physical_accuracy') != 'UNQUALIFIED' or not digest(summary.get('geometry_revision'))
            or not digest(summary.get('scene_revision')) or not finite(summary.get('meters_per_unit'))
            or summary.get('meters_per_unit', 0) <= 0):
        issues.append('IMPORTED_SHARED_MAP_UNQUALIFIED_OR_MISSING')
    if not any(r.get('status') == 200 and r.get('body', {}).get('navigation_scene') == summary for r in responses(row)):
        issues.append('MAP_NOT_BOUND_TO_ORIGINAL_FLEET_RESPONSE')
    try:
        if (not isinstance(samples, list) or len(samples) < 61 or hold.get('samples') != len(samples)
                or not finite(hold.get('duration_ms')) or hold['duration_ms'] < 60000):
            raise ValueError('short hold')
        first, last = samples[0]['view'], samples[-1]['view']
        epoch = samples[0]['motion_epoch']
        if (not text(epoch) or first != hold.get('first') or last != hold.get('last')
                or last['at'] - first['at'] < 60000 or last['frame_id'] <= first['frame_id']
                or first['scene_revision'] != summary.get('scene_revision') or not text(first['stage_epoch'])):
            raise ValueError('unbound hold')
        previous = None
        for sample in samples:
            view = sample['view']
            if (sample.get('control_state') != 'DRIVING' or sample.get('motion_epoch') != epoch
                    or view.get('live') is not True or view.get('canvas_visible') is not True
                    or view.get('stop_visible') is not True or view.get('pad_visible') is not True
                    or view.get('robot_badge_visible') is not True or view.get('intersection_px2') != 0
                    or any(not finite(view.get(k)) for k in ('at', 'frame_id', 'captured_at_ms', 'frame_age_ms'))
                    or not 0 <= view['frame_age_ms'] < 1000 or abs(view['at'] - view['captured_at_ms'] - view['frame_age_ms']) > 2
                    or view.get('scene_revision') != first['scene_revision'] or view.get('stage_epoch') != first['stage_epoch']
                    or previous and (not 0 < view['at'] - previous['at'] <= 1000 or view['frame_id'] < previous['frame_id'])):
                raise ValueError('stale, clipped or interrupted hold')
            previous = view
        registered = row['registered']
        if registered['source_twin_context']['scene_revision'] != first['scene_revision']:
            raise ValueError('wrong Twin')
    except (KeyError, TypeError, ValueError, IndexError):
        issues.append('CONTINUOUS_60S_DISPLAY_UNPROVEN')
    return issues


def stop_and_target_issues(row):
    issues = []
    registered, arrival = row.get('registered', {}), row.get('arrival', {})
    if (arrival.get('command', {}).get('state') != 'ARRIVED' or arrival.get('command', {}).get('target_id') != SOFA
            or any(not text(registered.get(k)) or arrival.get(k) != registered.get(k)
                   for k in ('robot_id', 'operation_id', 'connection_epoch'))):
        issues.append('ORIGINAL_SOFA0_ARRIVAL_UNPROVEN')
    receipts = row.get('stop_receipts', [])
    seen = set()
    if len(receipts) < 8:
        issues.append('MISSING_EXACT_STOP_RECEIPTS')
    for item in receipts:
        try:
            request, receipt, ack = item['request'], item['receipt'], item['engine_ack']
            identity = request['request_id']
            if (request['action'] != 'stop' or not text(identity) or identity in seen
                    or not text(receipt.get('motion_epoch')) or receipt['motion_epoch'] == request.get('motion_epoch')
                    or any(request.get(k) != registered.get(k) for k in ('robot_id', 'connection_epoch'))
                    or any(receipt.get(k) != registered.get(k) or ack.get(k) != registered.get(k)
                           for k in ('robot_id', 'operation_id', 'connection_epoch'))
                    or receipt.get('control_state') != 'PAUSED' or ack.get('control_state') != 'PAUSED'
                    or ack.get('motion_epoch') != receipt['motion_epoch'] or ack.get('applied_motion_epoch') != receipt['motion_epoch']):
                raise ValueError('Stop identity')
            seen.add(identity)
            rows = responses(row)
            original = [r for r in rows if r.get('method') == 'POST' and r.get('status') == 200
                        and r.get('path') == '/v1/product/robot-fleet' and r.get('request') == request
                        and receipt in r.get('body', {}).get('robots', [])]
            if len(original) != 1 or not any(ack in r.get('body', {}).get('robots', []) for r in rows):
                raise ValueError('Stop original missing')
        except (KeyError, TypeError, ValueError):
            issues.append('UNBOUND_STOP_RECEIPT')
    for gesture in row.get('gestures', []):
        if not any(item.get('request', {}).get('motion_epoch') == gesture.get('before', {}).get('motion_epoch') for item in receipts):
            issues.append('GESTURE_WITHOUT_EXACT_STOP')
    return issues


def edit_revision_chain(row, initial_revision, *, first_preview_action='model_review'):
    """Independently bind both recorder claims to original HTTP and UI evidence."""
    if first_preview_action not in {'model_review', 'move_preview'}:
        return None
    rows = responses(row)
    applies = [(index, r) for index, r in enumerate(rows) if r.get('method') == 'POST'
               and r.get('path') == '/v1/product/scene-edit/apply']
    proofs, origin = row.get('edit_transactions'), row.get('edit_origin')
    if (not isinstance(proofs, list) or len(proofs) != 2 or not isinstance(origin, dict)
            or origin.get('scene_revision') != initial_revision or not text(origin.get('project_id'))
            or not digest(origin.get('source_sha256')) or len(applies) != 2
            or any(r.get('status') not in (200, 202) for _, r in applies)):
        return None
    ids = [r.get('body', {}).get('operation_id') for _, r in applies]
    if any(not text(identity) for identity in ids) or len(set(ids)) != 2 or not digest(initial_revision):
        return None

    def original_index(claim):
        if not isinstance(claim, dict) or not finite(claim.get('at')) or not isinstance(claim.get('body'), dict):
            return None
        # Native timing fields can finish asynchronously after the recorder's
        # snapshot. Compare the immutable received identity/request/body fields.
        keys = ('at', 'method', 'path', 'status', 'request', 'body')
        matches = [i for i, original in enumerate(rows)
                   if all(original.get(key) == claim.get(key) for key in keys)]
        return matches[0] if len(matches) == 1 else None

    parent = initial_revision
    revisions = [initial_revision]
    for position, (start, accepted) in enumerate(applies):
        identity = ids[position]
        end = applies[position + 1][0] if position + 1 < len(applies) else len(rows)
        proof = proofs[position]
        if not isinstance(proof, dict):
            return None
        expected, ui = proof.get('expected'), proof.get('ui')
        if not isinstance(expected, dict) or not isinstance(ui, dict):
            return None
        result = expected.get('result_revision')
        mode = 'change' if position == 0 else 'undo'
        if (expected.get('operation_id') != identity or expected.get('mode') != mode
                or expected.get('parent_revision') != parent or not digest(result) or result in revisions
                or not digest(expected.get('preview_digest'))
                or expected.get('project_id') != origin['project_id'] or expected.get('source_sha256') != origin['source_sha256']):
            return None
        apply, committed, environment = (proof.get(key) for key in ('apply', 'committed', 'environment'))
        apply_index, commit_index, environment_index = (original_index(value) for value in (apply, committed, environment))
        if (apply_index != start or commit_index is None or environment_index is None
                or not start < commit_index < environment_index < end):
            return None
        request, admission, commit, imported = apply.get('request'), apply['body'], committed['body'], environment['body']
        if (not isinstance(request, dict) or request != dict(schema_version='scene-edit-apply-2.0',
                environment_preview_id=identity, preview_digest=expected['preview_digest'])
                or admission.get('operation_id') != identity or admission.get('parent_revision') != parent
                or admission.get('result_revision') != result or admission.get('preview_digest') != expected['preview_digest']
                or admission.get('error') or admission.get('state') not in
                   {'STAGED', 'PREPARED', 'BUILDING', 'ENGINE_ACKNOWLEDGED', 'COMMITTED'}
                or committed.get('method') != 'GET' or committed.get('path') != '/v1/product/scene-edit/transaction'
                or committed.get('status') != 200 or commit.get('operation_id') != identity or commit.get('state') != 'COMMITTED'
                or commit.get('parent_revision') != parent or commit.get('result_revision') != result or commit.get('error')
                or any(commit.get(key) is not True for key in ('durable_committed', 'engine_acknowledged', 'current_frame'))
                or environment.get('method') != 'GET' or environment.get('path') != '/v1/product/environment'
                or environment.get('status') != 200 or imported.get('status') != 'imported'
                or imported.get('project_id') != origin['project_id'] or imported.get('source_sha256') != origin['source_sha256']
                or imported.get('scene_revision') != result):
            return None
        frame = ui.get('frame')
        if (ui.get('caption') != EDIT_COMMITTED_CAPTION or ui.get('undo_enabled') is not True
                or ui.get('preview_visible') is not False or not isinstance(frame, dict)
                or frame.get('live') is not True or frame.get('scene_revision') != result or not text(frame.get('stage_epoch'))
                or not finite(frame.get('frame_id')) or frame['frame_id'] <= 0
                or not finite(frame.get('frame_age_ms')) or not 0 <= frame['frame_age_ms'] < 1000):
            return None
        action = first_preview_action if position == 0 else 'undo_preview'
        previews = [r.get('body', {}).get('preview', {}) for r in rows[:start]
                    if r.get('path') == '/v1/product/environment/action' and r.get('method') == 'POST'
                    and r.get('request', {}).get('action') == action and r.get('status') == 200
                    and (position != 0 or first_preview_action != 'move_preview'
                         or (r['request'].get('object_id') == CHAIR and r['request'].get('translation_m') == [.1, 0, 0]))
                    and r['request'].get('expected_scene_revision') == parent
                    and r['body'].get('project_id') == origin['project_id']
                    and r['body'].get('source_sha256') == origin['source_sha256'] and r['body'].get('scene_revision') == parent]
        if not any(preview.get('operation', {}).get('operation_id') == identity
                   and preview['operation'].get('mode') == mode
                   and preview['operation'].get('parent_revision') == parent
                   and preview['operation'].get('result_revision') == result
                   and preview.get('preview_digest') == expected['preview_digest']
                   and preview.get('parent_revision') == parent and preview.get('result_revision') == result
                   for preview in previews):
            return None
        revisions.append(result)
        parent = result
    return dict(initial_revision=revisions[0], moved_revision=revisions[1], undone_revision=revisions[2],
                operation_ids=ids)


def model_issues(records, source):
    issues = []
    request, result, diagnostic, job, ledger, ui = [records.get(k, {}) for k in
        ('model_request', 'model_result', 'model_diagnostic', 'model_job', 'model_ledger', 'ai_edit')]
    prompt, proposal = request.get('prompt', {}), ui.get('model_proposal', {})
    edit_origin = ui.get('edit_origin', {})
    model, request_id, revision = job.get('model_id'), job.get('request_id'), job.get('source_revision')
    project = request.get('project_id')
    if (job.get('status') != 'ready' or job.get('error') is not None or job.get('diagnostic_storage_errors')
            or '_owner' in job or not text(job.get('job_id')) or not text(request_id) or not digest(revision)
            or job.get('_project') != project or job.get('_source_sha256') != source
            or job.get('_object_id') != CHAIR or job.get('_text') != prompt.get('text')
            or request.get('source_sha256') != source or request.get('scene_revision') != revision
            or request.get('request_id') != request_id or request.get('model_id') != model
            or edit_origin.get('project_id') != project or edit_origin.get('source_sha256') != source
            or edit_origin.get('scene_revision') != revision
            or request.get('images_sent') != 0 or request.get('mesh_sent') is not False
            or set(prompt) != {'object_id', 'text'} or prompt.get('object_id') != CHAIR or not text(prompt.get('text'))
            or not text(model) or not model.startswith('nvidia/') or 'nemotron' not in model.lower()
            or any(proposal.get(k) != job.get(k) for k in ('job_id', 'request_id', 'status', 'source_revision', 'model_id', 'suggestion'))):
        issues.append('MODEL_JOB_REQUEST_OR_UI_IDENTITY_UNPROVEN')
    expected = [0.1, 0, 0]
    if (set(result) != {'schema_version', 'mode', 'object_id', 'translation_m', 'explanation'}
            or result.get('schema_version') != 'environment-move-1.0' or result.get('mode') != 'move'
            or result.get('object_id') != CHAIR or result.get('translation_m') != expected
            or not text(result.get('explanation'))
            or job.get('suggestion') != dict(translation_m=expected, explanation=result.get('explanation'))):
        issues.append('MODEL_RESULT_NOT_SELECTED_01M_X_MOVE')
    try:
        attempts, rows = diagnostic['attempts'], ledger['requests']
        if len(attempts) != 1 or len(rows) != 1:
            raise ValueError('not one HTTP')
        attempt, row = attempts[0], rows[0]
        usage = row['usage']
        budget = diagnostic['budget']
        if (ledger.get('schema_version') != 'product-usage-1.0' or not text(ledger.get('approval'))
                or diagnostic.get('request_id') != request_id or diagnostic.get('model_id') != model
                or diagnostic.get('status') != 'proposal_ready' or diagnostic.get('input_kind') != 'selected_object_move_text_only'
                or attempt.get('model_id') != model or row.get('model_id') != model
                or not text(row.get('attempt_id')) or attempt.get('attempt_id') != row['attempt_id']
                or attempt.get('status') != 'received' or row.get('status') != 'received'
                or attempt.get('finish_reason') != 'stop' or diagnostic.get('finish_reason') != 'stop'
                or not text(row.get('started_at')) or not text(row.get('finished_at'))
                or not isinstance(usage, dict) or any(type(usage.get(k)) is not int or usage[k] <= 0
                                                       for k in ('prompt_tokens', 'completion_tokens'))
                or attempt.get('usage') != usage or diagnostic.get('usage') != usage
                or budget.get('requests') != 1 or budget.get('cumulative_requests') != 1
                or budget.get('automatic_retry') is not False or budget.get('in_flight') is not None
                or budget.get('stop_reason') != 'ENVIRONMENT_MOVE_PROPOSAL_READY'):
            raise ValueError('ledger not bound')
    except (KeyError, TypeError, ValueError, IndexError):
        issues.append('ACTUAL_ONE_HTTP_MODEL_LEDGER_UNPROVEN')
    action_rows = [r for r in responses(ui) if r.get('method') == 'POST'
                   and r.get('path') == '/v1/product/environment/action']
    requested = [r for r in action_rows if r.get('request', {}).get('action') == 'model_move_preview']
    reviewed = [r for r in action_rows if r.get('request', {}).get('action') == 'model_review']
    if (len(requested) != 1 or requested[0].get('status') != 200
            or requested[0].get('request') != dict(action='model_move_preview', request_id=request_id,
                object_id=CHAIR, text=prompt.get('text'), expected_scene_revision=revision)
            or len(reviewed) != 1 or reviewed[0].get('status') != 200
            or reviewed[0].get('request', {}).get('job_id') != job.get('job_id')
            or reviewed[0].get('request', {}).get('expected_scene_revision') != revision):
        issues.append('MODEL_ACTION_NOT_EXPLICIT_OR_REPEATED')
    if edit_revision_chain(ui, revision) is None:
        issues.append('MODEL_APPLY_UNDO_PARENT_CHAIN_UNPROVEN')
    return issues


def verify(manifest, root):
    records, receipts, issues = read_refs(manifest, Path(root).resolve())
    release, source, usd = (manifest.get(k) for k in ('release_id', 'source_sha256', 'source_usd_sha256'))
    if not text(release) or not digest(source) or not digest(usd):
        issues.append('INVALID_MANIFEST_IDENTITIES')
    base = records.get('base_gate', {})
    if (base.get('schema') != 'robot-focused-evidence-gate-1.0' or base.get('status') != READY
            or base.get('issues') != [] or base.get('release_id') != release or base.get('source_sha256') != source):
        issues.append('CURRENT_RELEASE_BASE_GATE_NOT_READY')
    for role in REQUIRED:
        try:
            issues += ui_issues(role, records.get(role, {}), release)
        except (TypeError, AttributeError, KeyError):
            issues.append('MALFORMED_UI_RECORD:' + role)
    for checker, args in ((hold_and_map_issues, (records.get('sim', {}), usd)),
                          (stop_and_target_issues, (records.get('sim', {}),)), (model_issues, (records, usd))):
        try:
            issues += checker(*args)
        except (TypeError, AttributeError, KeyError, ValueError):
            issues.append('MALFORMED_EVIDENCE:' + checker.__name__)
    try:
        project = records.get('model_request', {}).get('project_id')
        original_revision = records.get('model_job', {}).get('source_revision')
        chain = edit_revision_chain(records.get('ai_edit', {}), original_revision)
        current_revision = chain['undone_revision'] if chain else None
        if (not text(project) or records.get('cold', {}).get('selected_project') != project
                or records.get('sim', {}).get('registered', {}).get('source_twin_context', {}).get('project_id') != project
                or not current_revision
                or records.get('sim', {}).get('shared_map', {}).get('scene_revision') != current_revision
                or records.get('sim', {}).get('registered', {}).get('source_twin_context', {}).get('scene_revision') != current_revision):
            issues.append('ROOMPLAN_PROJECT_LINEAGE_MISMATCH')
        for role in ('import', 'ai_edit', 'cold'):
            expected_revision = current_revision if role == 'cold' else original_revision
            if not any(r.get('body', {}).get('project_id') == project and r['body'].get('source_sha256') == usd
                       and r['body'].get('scene_revision') == expected_revision
                       and r['body'].get('status') == 'imported' for r in responses(records.get(role, {}))):
                issues.append('ORIGINAL_IMPORTED_SOURCE_NOT_BOUND:' + role)
    except (TypeError, AttributeError, KeyError):
        issues.append('MALFORMED_PROJECT_LINEAGE')
    return dict(schema='roomplan-preparation-gate-1.0', checked_at_utc=datetime.now(timezone.utc).isoformat(),
        status='NOT_READY' if issues else READY, release_id=release, source_sha256=source,
        source_usd_sha256=usd, issues=issues, evidence=receipts, physical_outcomes='NOT_RUN_ROBOT_OFF',
        limitation='Additional RoomPlan evidence only; relies on the SHA-bound current-release base gate. '
                   'SIM and model evidence do not certify physical driving, scale or world alignment. '
                   'Map summary binding is not an independent replay of every path cell.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text(encoding='utf-8-sig'))
        if not isinstance(manifest, dict):
            raise ValueError('manifest')
        result = verify(manifest, args.manifest.resolve().parent)
    except (OSError, ValueError, TypeError, UnicodeError):
        result = dict(schema='roomplan-preparation-gate-1.0', status='NOT_READY', issues=['MANIFEST_UNREADABLE'])
    # Exclusive creation preserves every earlier rejection/result.
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps(dict(status=result['status'], issues=result['issues']), ensure_ascii=False))
    return 0 if result['status'] == READY else 1


if __name__ == '__main__':
    raise SystemExit(main())
