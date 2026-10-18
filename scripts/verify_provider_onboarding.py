# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Actual fresh metadata and gateway setup with existing secure key; no inference."""
from pathlib import Path
import os,sys,json,hashlib
ROOT=Path(__file__).resolve().parents[1]
for p in ('twinpulse_core','twinpulse_provider','twinpulse_app'):sys.path.insert(0,str(ROOT/'packages'/p/'src'))
from twinpulse_app.credentials import WindowsCredentialStore
from twinpulse_app.settings import JsonProviderSettingsStore
from twinpulse_app.key_registry import KeyRegistry
from twinpulse_app.stage_routing import StageRoutingSettings,build_configured_stage_service
from twinpulse_app.provider_onboarding import configure_first_nebius_key

def main():
    original=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime'
    files=[original/n for n in ('provider_settings.json','provider_keys.json','provider_stage_routing.json','stage_model_catalog.json')]
    hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.exists()}
    registry=KeyRegistry(JsonProviderSettingsStore(original/'provider_settings.json'),WindowsCredentialStore())
    selected=StageRoutingSettings(registry).load()['observer']['key_id']
    output=ROOT/'outputs/product-flow-20261013/onboarding-live';output.mkdir(exist_ok=False)
    # A new local settings scope shares only existing OS credential references.
    for name in ('provider_settings.json','provider_keys.json'):
        (output/name).write_bytes((original/name).read_bytes())
    isolated=KeyRegistry(JsonProviderSettingsStore(output/'provider_settings.json'),WindowsCredentialStore())
    def changed():
        service=build_configured_stage_service(isolated,evidence_root=output/'provider-evidence')
        if service is None:raise ValueError('Gateway was not configured')
    result=configure_first_nebius_key(isolated,selected,changed)
    result.update(scope='actual metadata and production gateway construction; first-key UI registration remains fixture-tested',
        inference_requests=0,physical_commands=0,original_settings_unchanged=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==sha for p,sha in hashes.items()))
    (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
