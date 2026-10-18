# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Read-only review of one saved PC evidence bundle; never contacts a robot."""

import importlib.util
import json
from pathlib import Path
import re

from .command_broker import BrokerError


def _safe_reason(value):
    if isinstance(value, str) and len(value) <= 160 and not any(char in value for char in '/\\\r\n'):
        return value
    return 'DETAIL_REDACTED'


def review_saved_evidence(root, job_id):
    if not isinstance(job_id, str) or re.fullmatch('[a-f0-9]{32}', job_id) is None:
        raise BrokerError('evidence_job_invalid', 'Exact saved job ID required', status=400)
    root = Path(root).resolve()
    base = root/'artifacts/manual-control'
    job = base/job_id
    evidence = job/'robot-evidence'
    receipt = evidence/'export.json'
    if (any(path.is_symlink() for path in (root/'artifacts', base, job, evidence, receipt))
            or not evidence.resolve().is_relative_to(root)):
        raise BrokerError('evidence_path_unsafe', 'Saved evidence path is unsafe', status=409)
    if not evidence.is_dir() or not receipt.is_file():
        return {'schema_version':'robot-evidence-offline-review-1', 'job_id':job_id,
                'status':'INCOMPLETE', 'reason':'EVIDENCE_NOT_EXPORTED',
                'physical_validation':'NOT_RUN_BY_THIS_TOOL', 'transfer_only':True}
    from .runtime_paths import resource_root
    source = resource_root()/'scripts/inspect_robot_evidence.py'
    if not source.is_file() or source.is_symlink():
        return {'schema_version':'robot-evidence-offline-review-1', 'job_id':job_id,
                'status':'INCOMPLETE', 'reason':'EVIDENCE_INSPECTOR_UNAVAILABLE',
                'physical_validation':'NOT_RUN_BY_THIS_TOOL', 'transfer_only':True}
    try:
        spec = importlib.util.spec_from_file_location('twinpulse_saved_evidence_inspector', source)
        if spec is None or spec.loader is None:
            raise ValueError('INSPECTOR_LOAD_FAILED')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        result = module.inspect(evidence)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError, ImportError) as exc:
        return {'schema_version':'robot-evidence-offline-review-1', 'job_id':job_id,
                'status':'INCOMPLETE', 'reason':'EVIDENCE_INSPECTION_ERROR',
                'error_type':type(exc).__name__, 'physical_validation':'NOT_RUN_BY_THIS_TOOL',
                'transfer_only':True}
    result['job_id'] = job_id
    result['transfer_only'] = True
    result['contract_errors'] = [_safe_reason(value) for value in result['contract_errors']]
    if isinstance(result.get('raw_ros'), dict) and 'reason' in result['raw_ros']:
        result['raw_ros']['reason'] = _safe_reason(result['raw_ros']['reason'])
    return result
