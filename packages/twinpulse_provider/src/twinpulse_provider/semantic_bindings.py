# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Request-local immutable source references; models never rewrite provenance."""
from copy import deepcopy
from .scene_contract import role_of, SceneContractError, report, issue

BINDING_REVISION = 'semantic-binding-1.0'
STRUCTURE_REPAIR_REVISION = 'semantic-structure-repair-1.1'


def evidence_catalog(request, observation):
    rows = []
    for entity in observation.entities:
        if role_of(entity) not in ('object', 'unknown'):
            continue
        rows.append({'ref': 'seen:'+entity['id'], 'role': role_of(entity),
            'category': entity.get('category', 'unknown'), 'source': {
                'basis': 'inferred' if role_of(entity) == 'unknown' or entity['kind'] == 'unknown' else 'visual',
                'observation_ids': [entity['id']], 'user_quote': None}})
    # Exact original text slices are created by the host, not copied/invented
    # by the planner. Presence of a quote is not a claim of full text NLU.
    for index, start in enumerate(range(0, len(request.prompt), 256)):
        quote = request.prompt[start:start+256].strip()
        if quote:
            rows.append({'ref': 'text:'+str(index), 'role': 'user_text', 'category': None,
                         'source': {'basis': 'user', 'observation_ids': [], 'user_quote': quote}})
    rows.append({'ref': 'hypothesis', 'role': 'unobserved_estimate', 'category': None,
                 'source': {'basis': 'inferred', 'observation_ids': [], 'user_quote': None}})
    return rows


def binding_fields(request, observation):
    from .photo_layout import KINDS
    return {'id': {'type': 'string', 'pattern': r'^[A-Za-z][A-Za-z0-9_-]{0,31}$'},
            'kind': {'type': 'string', 'enum': list(KINDS)},
            'evidence_ref': {'type': 'string', 'enum': [row['ref'] for row in evidence_catalog(request, observation)]}}


def bind_inventory(rows, request, observation):
    by_ref = {row['ref']: row for row in evidence_catalog(request, observation)}
    result, issues, used = [], [], set()
    for index, row in enumerate(rows):
        path = f'$.inventory[{index}]'
        if not isinstance(row, dict) or set(row) != {'id', 'kind', 'evidence_ref'}:
            issues.append(issue('BINDING_ITEM_SHAPE_INVALID', path))
            continue
        evidence = by_ref.get(row['evidence_ref']) if isinstance(row['evidence_ref'], str) else None
        if evidence is None:
            issues.append(issue('BINDING_REFERENCE_INVALID', path+'.evidence_ref'))
            continue
        ref = row['evidence_ref']
        if ref.startswith('seen:'):
            if ref in used:
                issues.append(issue('BINDING_OBSERVATION_DUPLICATED', path+'.evidence_ref', observed_id=ref[5:]))
            used.add(ref)
        result.append({'id': row['id'], 'kind': row['kind'], 'source': deepcopy(evidence['source'])})
    if issues:
        raise SceneContractError(report(issues))
    return result


def _legacy_structure_repair_schema(candidate, diagnosis, request, observation):
    """Return a bounded correction contract only for a parsed binding inventory."""
    from .semantic_scene import ID
    from twinpulse_core import canonical_sha256
    import re
    if (not isinstance(candidate, dict) or set(candidate) != {'summary', 'room', 'inventory'}
            or not isinstance(candidate['inventory'], list)
            or any(not isinstance(row, dict) or set(row) != {'id', 'kind', 'evidence_ref'}
                   or not isinstance(row['id'], str) or not ID.fullmatch(row['id']) for row in candidate['inventory'])
            or len({row['id'] for row in candidate['inventory']}) != len(candidate['inventory'])):
        return None
    affected, missing, room, summary = set(), set(), False, False
    for error in diagnosis.get('issues', []):
        path = error.get('path', '')
        match = re.match(r'^\$\.inventory\[(\d+)\]', path)
        if match:
            index = int(match[1])
            if index < len(candidate['inventory']): affected.add(candidate['inventory'][index]['id'])
        if error['code'] == 'PHOTO_LAYOUT_OBSERVED_ITEMS_MISSING':
            missing.update(error.get('missing_ids', []))
        room |= path == '$.room' or path.startswith('$.room.')
        summary |= path == '$.summary'
    alternatives = []
    fields = binding_fields(request, observation)
    if affected:
        alternatives += [dict(type='object', additionalProperties=False, required=['op', 'id', 'value'], properties={
            'op': {'const': 'set'}, 'id': {'type': 'string', 'enum': sorted(affected)},
            'value': {'type': 'object', 'additionalProperties': False, 'required': ['kind', 'evidence_ref'],
                      'properties': {key: fields[key] for key in ('kind', 'evidence_ref')}}}),
            dict(type='object', additionalProperties=False, required=['op', 'id'], properties={
                'op': {'const': 'remove'}, 'id': {'type': 'string', 'enum': sorted(affected)}})]
    allowed_refs = ['seen:'+identity for identity in sorted(missing)]
    if allowed_refs:
        alternatives.append(dict(type='object', additionalProperties=False, required=['op', 'value'], properties={
            'op': {'const': 'add'}, 'value': {'type': 'object', 'additionalProperties': False,
                'required': list(fields), 'properties': {**fields,
                    'evidence_ref': {'type': 'string', 'enum': allowed_refs}}}}))
    if room:
        from .photo_layout import layout_schema
        alternatives.append(dict(type='object', additionalProperties=False, required=['op', 'value'],
            properties={'op': {'const': 'room'}, 'value': layout_schema(request.prompt)['properties']['room']}))
    if summary:
        alternatives.append(dict(type='object', additionalProperties=False, required=['op', 'value'],
            properties={'op': {'const': 'summary'}, 'value': {'type': 'string', 'minLength': 1, 'maxLength': 240}}))
    if not alternatives:
        return None
    return dict(type='object', additionalProperties=False, required=['base_revision', 'operations'], properties={
        'base_revision': {'const': canonical_sha256(candidate)}, 'operations': {'type': 'array', 'minItems': 1,
            'maxItems': 33, 'items': {'anyOf': alternatives}}})


def replay_legacy_structure_patch(candidate, patch, diagnosis, request, observation):
    """Explicit historical audit only; never selected by the production loop."""
    from .semantic_scene import _shape_issues
    schema = _legacy_structure_repair_schema(candidate, diagnosis, request, observation)
    problems = _shape_issues(patch, schema) if schema else [issue('BINDING_REPAIR_UNAVAILABLE', '$')]
    if problems:
        error = SceneContractError(report(problems))
        error.candidate_value = deepcopy(candidate)
        raise error
    result = deepcopy(candidate)
    used = set()
    for operation in patch['operations']:
        identity = (operation['id'] if 'id' in operation else operation['value']['id']
                    if operation['op'] == 'add' else '$'+operation['op'])
        if identity in used:
            error = SceneContractError(report([issue('BINDING_REPAIR_DUPLICATE_TARGET', '$.operations')]))
            error.candidate_value = deepcopy(candidate)
            raise error
        used.add(identity)
        if operation['op'] == 'set':
            row = next(row for row in result['inventory'] if row['id'] == identity)
            row.update(deepcopy(operation['value']))
        elif operation['op'] == 'remove':
            result['inventory'] = [row for row in result['inventory'] if row['id'] != identity]
        elif operation['op'] == 'add':
            if any(row['id'] == identity for row in result['inventory']):
                error = SceneContractError(report([issue('BINDING_REPAIR_ID_EXISTS', '$.operations')]))
                error.candidate_value = deepcopy(candidate)
                raise error
            result['inventory'].append(deepcopy(operation['value']))
        else:
            result[operation['op']] = deepcopy(operation['value'])
    return result


def _structure_repair_scope(candidate, diagnosis, request, observation):
    """Coalesce field and coverage errors by identity in THIS candidate only."""
    from .semantic_scene import ID
    import re
    if (not isinstance(candidate, dict) or set(candidate) != {'summary', 'room', 'inventory'}
            or not isinstance(candidate['inventory'], list)
            or any(not isinstance(row, dict) or set(row) != {'id', 'kind', 'evidence_ref'}
                   or not isinstance(row['id'], str) or not ID.fullmatch(row['id'])
                   for row in candidate['inventory'])
            or len({row['id'] for row in candidate['inventory']}) != len(candidate['inventory'])):
        return None
    catalog = {row['ref']: row for row in evidence_catalog(request, observation)}
    claims = {}
    for row in candidate['inventory']:
        ref = row['evidence_ref']
        if isinstance(ref, str) and ref in catalog:
            claims.setdefault(ref, []).append(row['id'])
    targets, missing, coverage, room, summary = {}, set(), [], [], []
    for error in diagnosis.get('issues', []):
        path = error.get('path', '')
        match = re.match(r'^\$\.inventory\[(\d+)\]', path)
        if match and int(match[1]) < len(candidate['inventory']):
            row = candidate['inventory'][int(match[1])]
            targets.setdefault(row['id'], {'id': row['id'], 'current': deepcopy(row), 'issues': []})['issues'].append(deepcopy(error))
        if error['code'] == 'PHOTO_LAYOUT_OBSERVED_ITEMS_MISSING':
            missing.update(identity for identity in error.get('missing_ids', []) if 'seen:'+identity in catalog)
            coverage.append(error)
        if path == '$.room' or path.startswith('$.room.'): room.append(deepcopy(error))
        if path == '$.summary': summary.append(deepcopy(error))
    for target in targets.values():
        ref = target['current']['evidence_ref']
        # A known, unique observation is still the object's identity when its
        # kind is wrong. Coverage then reports the SAME error, not a new object.
        preserved = (ref if isinstance(ref, str) and ref in catalog
                     and (not ref.startswith('seen:') or len(claims[ref]) == 1) else None)
        target['preserved_evidence_ref'] = preserved
        target['observed_category'] = catalog[preserved]['category'] if preserved else None
        if preserved and preserved.startswith('seen:') and preserved[5:] in missing:
            identity = preserved[5:]
            missing.remove(identity)
            target['issues'].extend({**deepcopy(error), 'missing_ids': [identity],
                                    'related_to_existing_target': True}
                                   for error in coverage if identity in error.get('missing_ids', []))
    return {'targets': targets, 'missing': sorted(missing), 'room': room, 'summary': summary,
            'catalog': catalog}


def structure_repair_context(candidate, diagnosis, request, observation):
    scope = _structure_repair_scope(candidate, diagnosis, request, observation)
    if scope is None:
        return None
    return {'revision': STRUCTURE_REPAIR_REVISION,
        'targets': [scope['targets'][identity] for identity in sorted(scope['targets'])],
        'missing_observations': [deepcopy(scope['catalog']['seen:'+identity]) for identity in scope['missing']],
        'room_issues': scope['room'], 'summary_issues': scope['summary'],
        'semantics': 'One coherent final change per target in this revision. Null means unchanged. '
                     'This is not a lifetime lock: validation may request the same target again in the next revision.'}


def structure_repair_schema(candidate, diagnosis, request, observation):
    """One nullable named slot per target, not an ambiguous sequence of writes."""
    from twinpulse_core import canonical_sha256
    scope = _structure_repair_scope(candidate, diagnosis, request, observation)
    if scope is None or not any(scope[key] for key in ('targets', 'missing', 'room', 'summary')):
        return None
    fields = binding_fields(request, observation)
    changes = {}
    for identity, target in sorted(scope['targets'].items()):
        value_fields = {key: deepcopy(fields[key]) for key in ('kind', 'evidence_ref')}
        ref = target['preserved_evidence_ref']
        if ref:
            value_fields['evidence_ref'] = {'type': 'string', 'const': ref}
            category = target['observed_category']
            if ref.startswith('seen:') and category in fields['kind']['enum'] and category != 'unknown':
                value_fields['kind'] = {'type': 'string', 'const': category}
        actions = [dict(type='object', additionalProperties=False, required=['op', 'value'], properties={
            'op': {'const': 'set'}, 'value': {'type': 'object', 'additionalProperties': False,
                'required': ['kind', 'evidence_ref'], 'properties': value_fields}})]
        # An invalid/duplicated binding or optional hypothesis can be removed;
        # unique observed and request-backed items cannot be erased as a shortcut.
        if ref is None or ref == 'hypothesis':
            actions.append(dict(type='object', additionalProperties=False, required=['op'],
                                properties={'op': {'const': 'remove'}}))
        changes[identity] = {'anyOf': [{'type': 'null'}]+actions}
    additions = {}
    for identity in scope['missing']:
        additions[identity] = {'anyOf': [{'type': 'null'}, dict(type='object', additionalProperties=False,
            required=list(fields), properties={**deepcopy(fields),
                'evidence_ref': {'type': 'string', 'const': 'seen:'+identity}})]}
    from .photo_layout import layout_schema
    nullable = lambda allowed: {'anyOf': [{'type': 'null'}, allowed]}
    properties = {
        'repair_version': {'const': STRUCTURE_REPAIR_REVISION},
        'base_revision': {'const': canonical_sha256(candidate)},
        'changes': dict(type='object', additionalProperties=False, required=list(changes), properties=changes),
        'additions': dict(type='object', additionalProperties=False, required=list(additions), properties=additions),
        'room': nullable(layout_schema(request.prompt)['properties']['room']) if scope['room'] else {'type': 'null'},
        'summary': nullable({'type': 'string', 'minLength': 1, 'maxLength': 240}) if scope['summary'] else {'type': 'null'}}
    return dict(type='object', additionalProperties=False, required=list(properties), properties=properties)


def repair_structure(candidate, patch, diagnosis, request, observation):
    from .semantic_scene import _shape_issues
    from twinpulse_core import canonical_sha256
    schema = structure_repair_schema(candidate, diagnosis, request, observation)
    problems = _shape_issues(patch, schema) if schema else [issue('BINDING_REPAIR_UNAVAILABLE', '$')]
    result = deepcopy(candidate)
    used = set()
    if not problems:
        for identity, action in patch['changes'].items():
            if action is None: continue
            used.add(identity)
            if action['op'] == 'set':
                next(row for row in result['inventory'] if row['id'] == identity).update(deepcopy(action['value']))
            else:
                result['inventory'] = [row for row in result['inventory'] if row['id'] != identity]
        for observed_id, row in patch['additions'].items():
            if row is None: continue
            identity = row['id']
            if identity in used or any(item['id'] == identity for item in candidate['inventory']):
                problems.append(issue('BINDING_REPAIR_DUPLICATE_TARGET', '$.additions.'+observed_id,
                                      target_id=identity, conflicting_fields=['id']))
                break
            used.add(identity)
            result['inventory'].append(deepcopy(row))
        for key in ('room', 'summary'):
            if patch[key] is not None: result[key] = deepcopy(patch[key])
        if not problems and canonical_sha256(result) == canonical_sha256(candidate):
            problems.append(issue('BINDING_REPAIR_NO_CHANGE', '$'))
    if problems:
        error = SceneContractError(report(problems))
        error.candidate_value = deepcopy(candidate)
        raise error
    return result


def batch_repair_schema(candidate, draft, targets):
    """Keep valid parameter slots; only malformed/missing slots may be set."""
    from .semantic_scene import _shape_issues, batch_schema
    from twinpulse_core import canonical_sha256
    if not isinstance(candidate, dict):
        return None
    fields = batch_schema(draft['inventory'], targets)['properties']
    affected = [identity for identity in targets
                if identity not in candidate or _shape_issues(candidate[identity], fields[identity])]
    extras = sorted(set(candidate)-set(targets))
    alternatives = [dict(type='object', additionalProperties=False, required=['op', 'id', 'value'],
        properties={'op': {'const': 'set'}, 'id': {'const': identity}, 'value': fields[identity]})
        for identity in affected]
    if extras:
        alternatives.append(dict(type='object', additionalProperties=False, required=['op', 'id'],
            properties={'op': {'const': 'discard'}, 'id': {'type': 'string', 'enum': extras}}))
    if not alternatives:
        return None
    return dict(type='object', additionalProperties=False, required=['base_revision', 'operations'],
        properties={'base_revision': {'const': canonical_sha256(candidate)}, 'operations': {
            'type': 'array', 'minItems': 1, 'maxItems': len(affected)+len(extras),
            'items': {'anyOf': alternatives}}})


def repair_batch(candidate, patch, draft, targets):
    from .semantic_scene import _shape_issues
    schema = batch_repair_schema(candidate, draft, targets)
    problems = _shape_issues(patch, schema) if schema else [issue('BATCH_REPAIR_UNAVAILABLE', '$')]
    result, used = deepcopy(candidate), set()
    if not problems:
        for operation in patch['operations']:
            identity = operation['id']
            if identity in used:
                problems.append(issue('BATCH_REPAIR_DUPLICATE_TARGET', '$.operations'))
                break
            used.add(identity)
            if operation['op'] == 'set':
                result[identity] = deepcopy(operation['value'])
            else:
                result.pop(identity, None)
    if problems:
        error = SceneContractError(report(problems))
        error.candidate_value = deepcopy(candidate)
        raise error
    return result
