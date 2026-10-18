# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Evaluation-only exact real-response replay. No credentials or network fallback."""
import hashlib
import json
from pathlib import Path
from dataclasses import replace


class ExactAuditedResponses:
    def __init__(self, campaign, evidence_root, attempt_ids):
        from twinpulse_provider.nebius_pipeline import parse_chat_completion
        import re
        if not 1 <= len(attempt_ids) <= 3 or len(set(attempt_ids)) != len(attempt_ids):
            raise ValueError('Replay requires 1..3 distinct completed attempts')
        ledger = json.loads(Path(campaign).read_text(encoding='utf-8'))
        self.entries = []
        self.used = 0
        for identity in attempt_ids:
            if not re.fullmatch('[a-f0-9]{32}', identity):
                raise ValueError('Invalid replay attempt identity')
            rows = [row for row in ledger['requests'] if row['attempt_id'] == identity]
            evidence = json.loads((Path(evidence_root)/(identity+'.json')).read_text(encoding='utf-8'))
            if (len(rows) != 1 or not rows[0].get('finished_at') or rows[0]['status'] != 'received'
                    or evidence.get('attempt_id') != identity or evidence.get('status') != 'received'
                    or evidence.get('http_status') != 200 or evidence.get('response_truncated')
                    or evidence.get('model_id') != rows[0]['model_id']):
                raise ValueError('Replay requires completed successful real dispatch evidence')
            raw = evidence.get('response_redacted', '').encode('utf-8')
            if (hashlib.sha256(raw).hexdigest() != evidence.get('response_sha256')
                    or len(raw) != evidence.get('response_byte_count')):
                raise ValueError('Replay response exact hash mismatch')
            completion = parse_chat_completion(json.loads(raw))
            if completion.model_id != evidence['model_id'] or completion.finish_reason != 'stop':
                raise ValueError('Replay completion model/finish mismatch')
            self.entries.append((evidence, replace(completion, attempt_id=identity)))

    async def complete(self, body, token, config):
        if token.is_cancelled or self.used >= len(self.entries):
            raise ValueError('Replay cancelled/exhausted; no network fallback')
        evidence, completion = self.entries[self.used]
        request_sha = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        schema_sha = hashlib.sha256(json.dumps(body['response_format'], sort_keys=True).encode()).hexdigest()
        if (request_sha != evidence['request_sha256'] or schema_sha != evidence['schema_sha256']
                or body['model'] != completion.model_id):
            raise ValueError('Replay requires the exact original photo/prompt/model/schema request')
        self.used += 1
        return completion


def live_run_inputs(run_root):
    """Read completed owned live provenance, never an arbitrary fixture manifest."""
    from twinpulse_app.project_store import ProjectStore
    root = Path(run_root)
    result = json.loads((root/'result.json').read_text(encoding='utf-8'))
    if (result.get('provider') != 'live_configured_provider' or result.get('photo_inference') != 'LIVE'
            or result.get('experimental_compact_photo') is not True
            or result.get('supervisor', {}).get('phase') != 'stopped'):
        raise ValueError('Replay requires a completed owned compact live photo run')
    draft = ProjectStore(root/'runtime/active_project.json').load().site_draft
    if draft is None or draft.input_revision.generation_settings.get('request_schema') != 'photo-layout-1.1':
        raise ValueError('Replay source photo-layout contract unavailable')
    evidence_root = root/'runtime/provider-evidence'
    files = list(evidence_root.glob('*.json'))
    evidence = [json.loads(p.read_text(encoding='utf-8')) for p in files]
    evidence.sort(key=lambda item: item['started_at'])
    ids = [item['attempt_id'] for item in evidence]
    if len(ids) not in (2,3):
        raise ValueError('Replay requires one observer, one planner and at most one recorded repair')
    if len(ids)==3:
        # A runtime/browser failure may follow a successfully committed model
        # result. Preserve that FAIL, and admit only its exact accepted repair
        # history for a separately labelled zero-network regression.
        from twinpulse_core.photo_quality import inspect_photo_geometry
        from scripts.summarize_live_photo_product import checked_generation_progress
        progress=checked_generation_progress(draft,result,
            inspect_photo_geometry(draft.plan.to_dict(),draft.input_revision.images[0]['sha256']))
        attempts=progress['attempts']
        if (progress['repair_count']!=1 or [a.get('attempt_id') for a in attempts]!=ids
                or [a.get('stage') for a in attempts]!=['observer','planner','planner']
                or [a.get('validation') for a in attempts]!=['passed','failed','passed']):
            raise ValueError('Replay repair must bind the original accepted plan and all three attempts')
    return draft, evidence_root, ids


def failed_packing_run_inputs(run_root):
    """Explicit rejection regression only, not an accepted historical draft.

    No credential or transport fallback. ExactAuditedResponses independently
    binds both raw responses to the finished ledger and original request hashes.
    """
    from types import SimpleNamespace
    from twinpulse_app.project_store import ProjectStore
    root=Path(run_root)
    result=json.loads((root/'result.json').read_text(encoding='utf-8'))
    record=ProjectStore(root/'runtime/active_project.json').load()
    progress=result.get('browser',{}).get('workflow',{}).get('generation_progress',{})
    evidence_root=root/'runtime/provider-evidence'
    evidence=[json.loads(p.read_text(encoding='utf-8')) for p in evidence_root.glob('*.json')]
    evidence.sort(key=lambda e:e['started_at'])
    ids=[e['attempt_id'] for e in evidence]
    attempts=progress.get('attempts',[])
    dispatched=[a for a in attempts if a.get('attempt_id')]
    blocked=[a for a in attempts if not a.get('attempt_id')]
    if (result.get('status')!='FAIL' or result.get('provider')!='live_configured_provider'
            or result.get('photo_inference')!='LIVE' or result.get('experimental_compact_photo') is not True
            or result.get('supervisor',{}).get('phase')!='stopped'
            or result.get('browser',{}).get('browser_closed') is not True
            or record.site_draft is not None or record.latest_input is None
            or record.latest_input.generation_settings.get('request_schema')!='photo-layout-1.1'
            or record.latest_input.measurement_constraints
            or len(record.latest_input.images)!=1 or len(ids)!=2
            or [a.get('attempt_id') for a in dispatched]!=ids
            or [a.get('stage') for a in dispatched]!=['observer','planner']
            or [a.get('validation') for a in dispatched]!=['passed','failed']
            or dispatched[-1].get('validation_code')!='PHOTO_LAYOUT_REGION_FULL'
            or progress.get('validation_code')!='PHOTO_LAYOUT_REGION_FULL'
            or len(blocked)>1 or any(a.get('stage')!='planner' or a.get('status')!='failed'
                or a.get('error_type')!='ProviderConfigurationError' for a in blocked)):
        raise ValueError('Failed replay requires exact stopped two-response packing rejection, not an accepted plan')
    # Deliberately no invented Site or plan/hash. The caller records the original
    # failure and labels newly accepted output as zero-network regression only.
    return SimpleNamespace(input_revision=record.latest_input,plan_sha256=None,site=None),evidence_root,ids


def expected_failed_packing_plan(source,evidence_root,ids,photo):
    """Independent current compile of unmodified rejected raw intent, zero I/O writes."""
    from twinpulse_provider.contracts import GenerationRequest,ImageInput
    from twinpulse_provider.nebius_pipeline import parse_chat_completion,ObservationArtifact
    from twinpulse_provider.photo_layout import compile_layout
    from tests.fixtures.historical_room_photo_inventory import photo_reference
    from twinpulse_core.photo_quality import inspect_photo_geometry
    from tests.fixtures.historical_photo_quality import reviewed_photo_constraints
    raw=[]
    for identity in ids:
        facts=json.loads((Path(evidence_root)/(identity+'.json')).read_text(encoding='utf-8'))
        response=facts['response_redacted'].encode()
        if hashlib.sha256(response).hexdigest()!=facts['response_sha256']:
            raise ValueError('Rejection expected-plan raw response changed')
        raw.append(json.loads(parse_chat_completion(json.loads(response)).content))
    content=Path(photo).read_bytes();digest=hashlib.sha256(content).hexdigest()
    image=source.input_revision.images[0]
    if image['sha256']!=digest:raise ValueError('Rejection photo differs from original input')
    constraints=reviewed_photo_constraints(digest,semantic_review=True)
    if constraints is None:raise ValueError('Rejection has no explicit reviewed photo constraints')
    request=GenerationRequest('rejection-regression',source.input_revision.prompt,
        (ImageInput(image['name'],image['mime_type'],content),))
    plan,provenance=compile_layout(raw[1],ObservationArtifact.from_mapping(raw[0]),request,
        photo_reference(digest),quality_constraints=constraints)
    quality=inspect_photo_geometry(plan,digest,constraints)
    if quality['issues']:raise ValueError('Recompiled rejected intent still fails reviewed geometry')
    return plan,provenance,quality
