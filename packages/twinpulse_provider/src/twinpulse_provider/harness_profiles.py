# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Data-only, model-bound prompt profiles. Host schemas and limits stay outside.

A profile changes prompt composition; it cannot grant provider capabilities
or execution rights.
"""
from copy import deepcopy
import hashlib
import json
import re

REVISION = 'harness-profile-1.0'
MAX_TEXT = 6000
STAGES = {
    'observer': ('observation', 'structure', 'render_review'),
    'planner': ('planning', 'resolution', 'recipe', 'batch', 'repair', 'feedback'),
}
SCHEMAS = {
    'twinpulse_image_observation': ('observer', 'observation'),
    'twinpulse_asset_observation': ('observer', 'observation'),
    'twinpulse_room_observation': ('observer', 'structure'),
    'twinpulse_render_review': ('observer', 'render_review'),
    'twinpulse_site_tool_plan_v2': ('planner', 'planning'),
    'twinpulse_compact_photo_layout': ('planner', 'planning'),
    'twinpulse_semantic_room': ('planner', 'planning'),
    'twinpulse_semantic_structure': ('planner', 'planning'),
    'twinpulse_model_resolution': ('planner', 'resolution'),
    'twinpulse_model_recipe': ('planner', 'recipe'),
    'twinpulse_library_recipe': ('planner', 'recipe'),
    'twinpulse_semantic_batch': ('planner', 'batch'),
    'twinpulse_semantic_patch': ('planner', 'repair'),
    'twinpulse_scene_feedback': ('planner', 'feedback'),
}
SUPER = 'nvidia/nemotron-3-super-120b-a12b'
FLASH = 'deepseek-ai/DeepSeek-V4.1-Flash'
BASE_INSTRUCTIONS = {
    'observer': {
        'observation': 'Record observed objects and relationships separately from estimates. Preserve uncertain counts and occlusions. Do not invent metric certainty from one image.',
        'structure': 'Return a compact estimated room shell first. Include the scale uncertainty. Detailed observation may revise the shell later.',
        'render_review': 'Compare the supplied current render against source evidence. Name affected object IDs and the concrete mismatch. Distinguish plan intent from rendered orientation and support. Return a concise final JSON answer.',
    },
    'planner': {
        'planning': 'Use stable inventory IDs. Keep observations, estimated dimensions and unresolved requirements distinct. Preserve all requested objects, including pending dependencies.',
        'resolution': 'Search the provided model library before defining a new model. An unsupported shape remains pending; do not replace it with an unrelated model just to finish.',
        'recipe': 'Author only the typed data recipe requested by the host. Use supplied dimensions and support surfaces. Do not generate executable source code.',
        'batch': 'Place parents and important floor furniture before their dependent objects. Follow world-axis and compiled-footprint evidence. Return only the requested batch.',
        'repair': 'Address the supplied concrete failure and the named affected objects. Reposition existing parents and their dependants when required. Describe the actual permitted edits; do not claim unchanged output as progress.',
        'feedback': 'Translate the user feedback into the typed atomic edit proposal. Preserve unrelated objects and pending work. Name ambiguities rather than inventing a requested direction.',
    },
}


def digest(value):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def checked_profile(value, *, provider, model, role):
    fields = {'schema_version', 'id', 'revision', 'provider', 'model_id', 'role',
              'baseline_sha256', 'instructions', 'compatibility'}
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError('HARNESS_PROFILE_SHAPE')
    if (value['schema_version'] != REVISION or value['provider'] != provider
            or value['model_id'] != model or value['role'] != role or role not in STAGES):
        raise ValueError('HARNESS_PROFILE_MODEL_BINDING')
    if (not isinstance(value['id'], str) or not re.fullmatch(r'[a-z0-9][a-z0-9_.-]{0,79}', value['id'])
            or type(value['revision']) is not int or value['revision'] < 1
            or value['compatibility'] not in ('baseline', 'unverified')
            or not isinstance(value['baseline_sha256'], str)
            or not re.fullmatch('[a-f0-9]{64}', value['baseline_sha256'])):
        raise ValueError('HARNESS_PROFILE_IDENTITY')
    instructions = value['instructions']
    if (not isinstance(instructions, dict) or set(instructions) != set(STAGES[role])
            or any(not isinstance(v, str) or not v.strip() or len(v) > MAX_TEXT or '\x00' in v
                   or '\nResponse JSON Schema:\n' in v
                   for v in instructions.values())):
        raise ValueError('HARNESS_PROFILE_INSTRUCTIONS')
    if value['compatibility'] == 'baseline':
        model_baseline = provider == 'nebius' and model == (SUPER if role == 'planner' else FLASH)
        baseline = {'revision': REVISION, 'role': role, 'instructions': BASE_INSTRUCTIONS[role]}
        expected_id = ('nemotron-super' if role == 'planner' else 'flash-observer') + '-' + role
        if (not model_baseline or value['revision'] != 1 or value['id'] != expected_id
                or instructions != BASE_INSTRUCTIONS[role] or value['baseline_sha256'] != digest(baseline)):
            raise ValueError('HARNESS_BASELINE_MISMATCH')
    return deepcopy(value)


def default_profile(provider, model, role):
    if role not in STAGES or provider not in ('nebius', 'openai') or not isinstance(model, str) or not model:
        raise ValueError('HARNESS_PROFILE_ROUTE')
    instructions = deepcopy(BASE_INSTRUCTIONS[role])
    model_baseline = (provider == 'nebius' and model == (SUPER if role == 'planner' else FLASH))
    baseline = {'revision': REVISION, 'role': role, 'instructions': instructions}
    return checked_profile(dict(schema_version=REVISION,
        id=('nemotron-super' if role == 'planner' else 'flash-observer') + '-' + role,
        revision=1, provider=provider, model_id=model, role=role,
        baseline_sha256=digest(baseline), instructions=instructions,
        compatibility='baseline' if model_baseline else 'unverified'),
        provider=provider, model=model, role=role)


def edited_profile(profile, instructions, *, name=None):
    """Create a new value; an already captured run retains the original bytes."""
    result = deepcopy(profile)
    result.update(revision=result['revision'] + 1, instructions=deepcopy(instructions), compatibility='unverified')
    if name is not None:
        result['id'] = name
    return checked_profile(result, provider=result['provider'], model=result['model_id'], role=result['role'])


def binding(profile):
    if not isinstance(profile, dict) or not {'provider', 'model_id', 'role'} <= set(profile):
        raise ValueError('HARNESS_PROFILE_SHAPE')
    checked = checked_profile(profile, provider=profile['provider'], model=profile['model_id'], role=profile['role'])
    return {'schema_version': REVISION, 'id': checked['id'], 'revision': checked['revision'],
            'sha256': digest(checked), 'profile': checked}


def checked_binding(value, *, provider, model, role):
    if not isinstance(value, dict) or set(value) != {'schema_version', 'id', 'revision', 'sha256', 'profile'}:
        raise ValueError('HARNESS_BINDING_SHAPE')
    expected = binding(checked_profile(value['profile'], provider=provider, model=model, role=role))
    if expected != value:
        raise ValueError('HARNESS_BINDING_DIGEST')
    return expected


def apply_profile(original, frozen, *, stage_hint=None, repairing=False):
    """Append guidance once, BEFORE explicit_json_contract normalizes the body.

    Existing normalized prompts are rebuilt before the host schema is attached
    again. Editable instructions cannot contain the reserved schema delimiter.
    """
    body = deepcopy(original)
    schema = body.get('response_format', {}).get('json_schema', {}).get('name')
    if schema not in SCHEMAS:
        raise ValueError('HARNESS_UNKNOWN_SCHEMA')
    role, stage = SCHEMAS[schema]
    if stage_hint is not None:
        if stage_hint not in STAGES[role]:
            raise ValueError('HARNESS_HOST_STAGE_INVALID')
        stage = stage_hint
    if not isinstance(frozen, dict) or not isinstance(frozen.get('profile'), dict):
        raise ValueError('HARNESS_BINDING_SHAPE')
    profile = frozen['profile']
    checked_binding(frozen, provider=profile['provider'], model=body.get('model'), role=role)
    systems = [r for r in body.get('messages', []) if r.get('role') == 'system']
    if len(systems) != 1 or not isinstance(systems[0].get('content'), str):
        raise ValueError('HARNESS_SYSTEM_REQUIRED')
    # Existing callers can already have attached the host schema. Rebuild that
    # final section after composition so guidance is not discarded by routing.
    systems[0]['content'] = systems[0]['content'].split('\nResponse JSON Schema:\n', 1)[0]
    systems[0]['content'] += '\nModel-specific guidance (' + frozen['sha256'] + '):\n' + profile['instructions'][stage]
    if repairing and role == 'planner' and stage != 'repair':
        systems[0]['content'] += '\nRepair guidance:\n' + profile['instructions']['repair']
    return body


def assert_continuation_profiles(parent_bindings, current_bindings):
    """Old checkpoints stay readable; migrating their prompt identity is explicit."""
    if parent_bindings != current_bindings:
        raise ValueError('CONTINUATION_HARNESS_CHANGED')
