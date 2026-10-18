# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Frozen Nebius catalog contracts, never credentials or spending authority.

Visibility/modalities select an adapter, not proven JSON support, account
access or quality. The live runner rechecks metadata before inference.
"""
from copy import deepcopy
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re


def catalog_sha(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _time(value):
    try:
        result = datetime.fromisoformat(value)
        if result.tzinfo is None or result.utcoffset().total_seconds() != 0: raise ValueError()
        return result
    except (TypeError, ValueError):
        raise ValueError('MODEL_CATALOG_TIME_INVALID') from None


def checked_catalog(value, *, now=None):
    fields = {'schema_version', 'verified_at', 'valid_until', 'source_sha256', 'models'}
    if type(value) is not dict or set(value) != fields or value['schema_version'] != 'stage-model-catalog-1.0':
        raise ValueError('MODEL_CATALOG_SHAPE_INVALID')
    if not isinstance(value['source_sha256'], str) or not re.fullmatch('[a-f0-9]{64}', value['source_sha256']):
        raise ValueError('MODEL_CATALOG_SOURCE_INVALID')
    verified, expiry = _time(value['verified_at']), _time(value['valid_until'])
    if not verified < expiry <= verified + timedelta(days=7): raise ValueError('MODEL_CATALOG_VALIDITY_INVALID')
    if now is not None and not verified <= now < expiry: raise ValueError('MODEL_CATALOG_EXPIRED_OR_FUTURE')
    if type(value['models']) is not list or not 1 <= len(value['models']) <= 256: raise ValueError('MODEL_CATALOG_COUNT_INVALID')
    seen = set()
    for row in value['models']:
        if type(row) is not dict or set(row) != {'model_id', 'visible', 'modalities', 'context_tokens',
                                               'input_per_million', 'output_per_million'}:
            raise ValueError('MODEL_CATALOG_ROW_INVALID')
        model = row['model_id']
        if not isinstance(model, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]{0,159}', model) or model in seen:
            raise ValueError('MODEL_CATALOG_ID_INVALID')
        seen.add(model)
        if (type(row['visible']) is not bool or type(row['modalities']) is not list
                or any(type(m) is not str or m not in ('text', 'image') for m in row['modalities'])
                or len(set(row['modalities'])) != len(row['modalities'])
                or type(row['context_tokens']) is not int or not 1 <= row['context_tokens'] <= 4_000_000):
            raise ValueError('MODEL_CATALOG_CAPABILITY_INVALID')
        for key in ('input_per_million', 'output_per_million'):
            try:
                rate = Decimal(row[key]) if isinstance(row[key], str) else None
                if rate is None or not rate.is_finite() or not 0 <= rate <= 1000: raise ValueError()
            except (InvalidOperation, TypeError, ValueError):
                raise ValueError('MODEL_CATALOG_PRICE_INVALID') from None
    return deepcopy(value)


def load_catalog(path, expected_sha, *, now=None):
    path = Path(path)
    if (not isinstance(expected_sha, str) or not re.fullmatch('[a-f0-9]{64}', expected_sha)
            or any(p.is_symlink() for p in (path, *path.parents)) or path.stat().st_size > 262144):
        raise ValueError('MODEL_CATALOG_FILE_INVALID')
    def pairs(rows):
        result = {}
        for key, value in rows:
            if key in result: raise ValueError('MODEL_CATALOG_DUPLICATE_FIELD')
            result[key] = value
        return result
    value = checked_catalog(json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=pairs), now=now)
    if catalog_sha(value) != expected_sha: raise ValueError('MODEL_CATALOG_SHA_CHANGED')
    return value


def model_supported(catalog, stage, model):
    required = 'image' if stage == 'observer' else 'text' if stage == 'planner' else None
    return bool(required and any(r['model_id'] == model and r['visible']
        and required in r['modalities'] and 'text' in r['modalities'] for r in catalog['models']))


def catalog_prices(catalog):
    return {r['model_id']: {**{k: r[k] for k in ('input_per_million', 'output_per_million', 'context_tokens')},
        'source': 'https://api.tokenfactory.nebius.com/private/v1/models_info',
        'source_sha256': catalog['source_sha256'], 'verified_at': catalog['verified_at']}
        for r in catalog['models'] if r['visible'] and 'text' in r['modalities']}


def catalog_from_inventory(inventory, *, valid_until):
    """Normalize saved metadata only. No lookup, inference or new approval."""
    models = []
    for row in inventory['models']:
        if row['provider'] != 'nebius': continue
        modalities = sorted(set(row['use_cases']) & {'text', 'image'})
        models.append({**{k: row[k] for k in ('model_id', 'visible', 'context_tokens')},
            'modalities': modalities, **{k: str(row[k]) for k in ('input_per_million', 'output_per_million')}})
    return checked_catalog(dict(schema_version='stage-model-catalog-1.0',
        verified_at=inventory['created_at'], valid_until=valid_until,
        source_sha256=inventory['catalog_sha256'], models=models))
