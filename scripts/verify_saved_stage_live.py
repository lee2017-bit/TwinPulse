# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Explicit bounded host test of the saved ordinary stage service, not a product mode."""
import hashlib
import json
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for name in ('twinpulse_app', 'twinpulse_provider', 'twinpulse_core'):
    sys.path.insert(0, str(ROOT/'packages'/name/'src'))


def approved_service(scope, observer, observer_key, planner, planner_key, ledger, evidence_root, **kwargs):
    from twinpulse_app.stage_routing import StageRoutingSettings, build_configured_stage_service, DEFAULT_GENERATION_TIMEOUT_S
    from twinpulse_app.key_registry import KeyRegistry
    from twinpulse_app.settings import JsonProviderSettingsStore
    from twinpulse_app.credentials import WindowsCredentialStore
    from twinpulse_provider import ProviderConfigurationError
    registry = KeyRegistry(JsonProviderSettingsStore(), WindowsCredentialStore())
    route = StageRoutingSettings(registry).load()
    expected = dict(observer=dict(key_id=scope['observer_entry_id'], model_id='gpt-5.4-mini'),
        planner=dict(key_id=scope['planner_entry_id'], model_id=scope['planner_model']))
    if scope.get('schema_version') == 'configured-stage-evaluation-1.0':
        expected=scope['saved_stage_route']
    timeout = scope.get('generation_timeout_s', DEFAULT_GENERATION_TIMEOUT_S)
    if (route != expected or kwargs.get('timeout_s') != timeout or kwargs.get('compact_photo_layout')
            or route.get('generation_timeout_s', DEFAULT_GENERATION_TIMEOUT_S) != timeout):
        raise ProviderConfigurationError('Saved route/default policy does not match this approval')
    service = build_configured_stage_service(registry, evidence_root=evidence_root)
    provider = service._provider
    transport = provider._transport
    if scope.get('schema_version') == 'configured-stage-evaluation-1.0' and provider.stage_output_token_caps != scope['stage_output_tokens']:
        raise ProviderConfigurationError('Approved output limits changed; no dispatch')
    for stage in ('observer', 'planner'):
        transport.transports[stage].ledger = ledger
    original = provider.generate
    async def guarded(request, token, config):
        if (request.prompt != scope['prompt'] or len(request.images) != 1
                or hashlib.sha256(request.images[0].content).hexdigest() != scope['photo_sha256']):
            raise ProviderConfigurationError('Input outside this approved photo/prompt')
        return await original(request, token, config)
    provider.generate = guarded
    return service


if __name__ == '__main__':
    if '--backend-child' in sys.argv:
        sys.argv.remove('--backend-child')
        from twinpulse_app import split_evaluation
        split_evaluation.build_scoped_split_service = approved_service
        from scripts import twinpulse_backend
        twinpulse_backend.main()
    else:
        from twinpulse_app.process_manager import TwinPulseProcessManager
        original = TwinPulseProcessManager._backend_command
        def command(self):
            args = original(self)
            for i, value in enumerate(args):
                if str(value).endswith('twinpulse_backend.py'):
                    args[i] = str(Path(__file__).resolve())
                    args.insert(i+1, '--backend-child')
                    break
            else:
                raise RuntimeError('Known backend entrypoint not found')
            return args
        TwinPulseProcessManager._backend_command = command
        runpy.run_path(str(ROOT/'scripts/verify_chat_sim_journey.py'), run_name='__main__')
