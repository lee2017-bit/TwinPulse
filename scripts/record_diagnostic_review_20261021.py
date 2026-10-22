# SPDX-License-Identifier: Apache-2.0
"""Main's hash-bound transcription of the actual Astra read-only delta review."""
from hashlib import sha256
import json
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/robot-continuous-repair-20261021'


def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    active=read(Path(os.environ['LOCALAPPDATA'])/'TwinPulse/installed/active-release.json')
    package=OUT/'build24/dist/TwinPulse'
    manifest=read(package/'windows-release-manifest.json')
    if active['release_id']!=manifest['build_id'] or active['source_manifest_sha256']!=manifest['source_manifest_sha256']:raise ValueError('REVIEW_NOT_ACTIVE_BUILD24')
    before=read(OUT/'build23/dist/TwinPulse/_internal/resources/source-manifest.json')
    after=read(package/'_internal/resources/source-manifest.json')
    delta={name:dict(before=before.get(name),after=after.get(name)) for name in before.keys()|after.keys() if before.get(name)!=after.get(name)}
    if set(delta)!={'packages/twinpulse_core/src/twinpulse_core/fleet_diagnostics.py'}:raise ValueError('UNREVIEWED_PRODUCT_DELTA:'+str(sorted(delta)))
    files={name:sha256((ROOT/name).read_bytes()).hexdigest() for name in (
        'packages/twinpulse_core/src/twinpulse_core/fleet_diagnostics.py','tests/integration/test_fleet_diagnostics.py')}
    if after['packages/twinpulse_core/src/twinpulse_core/fleet_diagnostics.py']!=files['packages/twinpulse_core/src/twinpulse_core/fleet_diagnostics.py']:raise ValueError('REVIEWED_CORE_CHANGED')
    value=dict(schema='read-only-independent-source-review-1.0',status='NO_ADDITIONAL_CONFIRMED_CRITICAL_SOURCE_DEFECT_NOT_PHYSICAL_QUALIFICATION',
        agent='/root/astra_continuous_path_review21',model='gpt-6-astra',effort='xhigh',read_only=True,
        recorded_by='Main transcription of actual collaboration final review; reviewer performed no file/App/device/external writes.',
        release_id=active['release_id'],source_manifest_sha256=active['source_manifest_sha256'],final_reviewed_files=files,
        exact_product_delta_from_frozen23=delta,
        findings=['Actual fast/slow UpdateProbe.finish fields are accepted; before_resources permits only its three reviewed optional numeric keys.',
            'Type/range/finite checks retain rejection of bool, huge integer, NaN, negatives and unregistered keys; deep copy and original fault byte bound remain.',
            'Actual producer to fault and operation export roundtrip separates original failed-check timing from a later heartbeat.',
            'Change affects diagnostic acceptance only; pause, epoch, authority and control deadline decisions are unchanged. No further confirmed defect in this delta.'],
        unresolved=[],limits=['Exact lost CPU data from original29 cannot be recovered and this patch is not a sole-cause or performance fix.',
            'This delta source review is not current installed UI/normal-start/physical acceptance. Final current receipts and evidence gate are independently required.'],
        evidence=[dict(path=name,sha256=sha256((OUT/name).read_bytes()).hexdigest()) for name in ('diagnostic-contract-red31.log','diagnostic-contract-green31.log')])
    with (OUT/'diagnostic-source-review31.json').open('x',encoding='utf-8') as stream:json.dump(value,stream,indent=2)
    print(json.dumps(dict(status=value['status'],product_delta=list(delta),release_id=value['release_id'])))


if __name__=='__main__':main()
