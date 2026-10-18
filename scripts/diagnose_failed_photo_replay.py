# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Exact failed live photo replay for diagnosis only; no network/credentials.

Use immutable audited responses and the original archived input. A rejected
candidate is never promoted or edited; even an exhausted repair stays rejected.
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for name in ('twinpulse_core', 'twinpulse_app', 'twinpulse_provider'):
    sys.path.insert(0, str(ROOT/'packages'/name/'src'))


async def diagnose(args):
    from scripts.replay_audited_inference import ExactAuditedResponses
    from twinpulse_app import JsonProviderSettingsStore
    from twinpulse_app.project_store import ProjectStore
    from twinpulse_core import InputArtifactStore
    from twinpulse_provider import (CancellationToken, GenerationRequest, ImageInput,
        NebiusChatCompletionsPipelineProvider, ProviderCapabilities, ProviderConfig)
    root, output = args.run.resolve(), args.output.resolve()
    if not root.is_relative_to(ROOT/'artifacts') or not output.is_relative_to(ROOT/'artifacts') or output.exists():
        raise ValueError('Original run and fresh output must be inside artifacts; no overwrite')
    result = json.loads((root/'result.json').read_text(encoding='utf-8'))
    if (result.get('status') != 'FAIL' or result.get('provider') != 'live_configured_provider'
            or result.get('experimental_compact_photo') is not True
            or result.get('supervisor', {}).get('phase') != 'stopped'):
        raise ValueError('Completed failed compact live photo run required')
    evidence_root = root/'runtime/provider-evidence'
    rows = sorted((json.loads(p.read_text(encoding='utf-8')) for p in evidence_root.glob('*.json')),
                  key=lambda row: row['started_at'])
    if len(rows) != 2:
        raise ValueError('Exactly one completed observer and planner required')
    originals = [args.campaign.resolve(), *root.rglob('*.json'), *root.rglob('*.bin')]
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    before = {str(p): digest(p) for p in originals}
    transport = ExactAuditedResponses(args.campaign, evidence_root, [row['attempt_id'] for row in rows])
    store = ProjectStore(root/'runtime/active_project.json')
    record = store.load()
    if record.site_draft is not None or record.latest_input is None:
        raise ValueError('Failed input without committed scene required')
    revision, images = InputArtifactStore(store.input_root()).load(record.latest_input)
    if revision.generation_settings.get('measurement_constraints'):
        raise ValueError('This diagnostic supports the original unmeasured photo only')
    request = GenerationRequest('exact-failed-photo-diagnosis', revision.prompt,
        tuple(ImageInput(*image) for image in images), image_detail=revision.generation_settings.get('image_detail', 'auto'))
    settings = JsonProviderSettingsStore(root/'runtime/provider_settings.json').load().validated()
    config = ProviderConfig(settings.base_url, settings.endpoint_path, settings.model_id,
        'UNUSED_EXACT_REPLAY', ProviderCapabilities(settings.supports_images, settings.supports_structured_output,
            settings.max_images, settings.accepted_mime_types), timeout_s=90.)
    provider = NebiusChatCompletionsPipelineProvider(transport,
        observer_model_id=settings.observer_model_id, planner_model_id=settings.model_id,
        site_plan_version='2.2', max_repairs=1, compact_photo_layout=True,
        planner_template_no_thinking=True, output_token_cap=10000)
    failure = None
    try:
        await provider.generate(request, CancellationToken(), config)
    except Exception as error:
        failure = type(error).__name__ + ': ' + str(error)[:500]
    diagnostic = provider.diagnostic_for(request.request_id)
    rejected = [row for row in diagnostic.get('attempts', []) if row.get('validation') == 'failed']
    report = dict(status='DIAGNOSIS_ONLY', new_calls=0, robot_connections=0, isaac='NOT_RUN',
        original_live_status='FAIL', candidate_accepted=False, exact_request_checks=transport.used,
        first_validation_errors=[row['validation_error'] for row in rejected],
        diagnostic=diagnostic, replay_terminal=failure, original_hashes=before,
        source_hashes={str(p.relative_to(ROOT)): digest(p) for p in [Path(__file__),
            ROOT/'scripts/replay_audited_inference.py',
            ROOT/'packages/twinpulse_provider/src/twinpulse_provider/nebius_pipeline.py',
            ROOT/'packages/twinpulse_provider/src/twinpulse_provider/photo_layout.py']},
        originals_unchanged=all(digest(Path(p)) == sha for p, sha in before.items()))
    if transport.used != 2 or not rejected or not report['originals_unchanged']:
        raise AssertionError('Exact replay did not reproduce the original validation rejection')
    output.mkdir(parents=True, exist_ok=False)
    (output/'diagnosis.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('status', 'new_calls', 'exact_request_checks', 'first_validation_errors', 'originals_unchanged')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--campaign', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    asyncio.run(diagnose(parser.parse_args()))
