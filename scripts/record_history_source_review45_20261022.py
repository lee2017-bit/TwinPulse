# SPDX-License-Identifier: Apache-2.0
"""Main transcription of the actual read-only Astra review, never UI PASS."""
from hashlib import sha256
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/robot-continuous-repair-20261021'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def ref(p):return dict(path=p.relative_to(OUT).as_posix(),sha256=sha256(p.read_bytes()).hexdigest())
def write(p,v):
    with p.open('x',encoding='utf-8') as f:json.dump(v,f,ensure_ascii=False,indent=2)

def main():
    old=read(OUT/'build28/dist/TwinPulse/_internal/resources/source-manifest.json')
    new=read(OUT/'build30/dist/TwinPulse/_internal/resources/source-manifest.json')
    manifest=read(OUT/'build30/dist/TwinPulse/windows-release-manifest.json')
    changed=sorted(k for k in old.keys()|new.keys() if old.get(k)!=new.get(k))
    assert changed==['packages/twinpulse_app/src/twinpulse_app/api.py',
        'packages/twinpulse_app/src/twinpulse_app/physical_live_history.py',
        'packages/twinpulse_app/src/twinpulse_app/request_latency.py'],changed
    assert all(sha256((ROOT/name).read_bytes()).hexdigest()==new[name] for name in changed)
    before=read(OUT/'history-before45.json');after=read(OUT/'history-after45.json')
    assert before['receipt_sha256']==after['receipt_sha256']
    assert {row['output_sha256'] for row in before['rows']+after['rows']}=={'2b19e25b40144c04696d66d56f82192f1513c1dcb615c9b4fdb6ee22a0aad6c2'}
    files=changed+['tests/integration/test_physical_live_history.py','tests/integration/test_request_latency.py']
    write(OUT/'history-source-review45.json',dict(schema='read-only-independent-source-review-1.0',
        status='NO_ADDITIONAL_CONFIRMED_CRITICAL_SOURCE_DEFECT_NOT_PHYSICAL_QUALIFICATION',
        agent='/root/astra_continuous_path_review21',model='gpt-6-astra',effort='xhigh',read_only=True,
        recorded_by='Main transcription of actual final source/negative-test review. Reviewer only read files/artifacts; did not execute tests/App/system/device actions.',
        release_id=manifest['build_id'],source_manifest_sha256=manifest['source_manifest_sha256'],
        exact_product_delta_from_frozen28=changed,unresolved=[],
        final_reviewed_files={name:sha256((ROOT/name).read_bytes()).hexdigest() for name in files},
        fixed=['Deep-copy/redact only retained100 parsed history events after unchanged full archive validation.',
            'Keep original cleanup/export projections and the independent first SHA pass/incomplete verdicts.',
            'Exact32hex history GET maps to one capped diagnostic bucket, without arbitrary path/query data.',
            'Optional read/encode timing isolates begin/end clock and phase-storage failure from original result/exception.'],
        references=[ref(OUT/name) for name in ('history-before45.json','history-after45.json','history-tail-red45.log',
            'history-final45.log','viewport-source-review43.json','snapshot-source-review41.json','raycast-source-review37.json')],
        limits=['Original43 remains FAIL; original GET server-phase/native-header evidence was not retained.',
            'Isolated CPU/time reduction and identical bytes are not proof of historical20s cause or current UI readiness.',
            'Build29 was not installed and is excluded; it preceded the optional-diagnostic isolation correction.',
            'Fresh45/cold/lineage/history, original geometry46 and final evidence gate remain required.',
            'Physical/Pi/storage/braking/world alignment NOT_RUN.']))
    original=read(OUT/'lineage-43/result.json');assert original['status']=='FAIL'
    write(OUT/'history-failure43-review.json',dict(status='ORIGINAL_FAIL_PRESERVED_COLD_READ_TIMEOUT_CAUSE_UNRESOLVED',
        launch_id=original['desktop']['engine']['launch_id'],project=original['project'],operation_id=original['operation_id'],
        failed_step=original['steps'][-1],failed_requests=original['request_failed'],
        physical_operation='65fe078b1975404886704c2df728a33f',
        fresh43_status=read(OUT/'ui-43/result.json')['status'],cold43_status=read(OUT/'ui-cold-43/result.json')['status'],
        missing=['HISTORY43_NOT_RUN','REPRODUCTION44_NOT_RUN','ORIGINAL_GET_SERVER_PHASE_AND_NATIVE_HEADERS_UNAVAILABLE'],
        interpretation=['UI explicitly showed local operation record read exceeded20 seconds; not a missing-locator-only failure.',
            'All source rows/SHA verified; intermediate tail copies were wasted CPU. Exact contribution to original20s remains UNKNOWN.',
            'No timeout/authority/geometry/incomplete-verdict relaxation; source review is not actual acceptance.'],
        references=[ref(OUT/name) for name in ('lineage-43/result.json','lineage-43/failure-8.png',
            'failed-lineage43-original-logs/receipt.json','runtime-final43/receipt.json','memory-final43/receipt.json','budget-final43.json')]))
    print(json.dumps(dict(status='ACTUAL_REVIEW_RECORDED_NOT_UI_ACCEPTANCE',release_id=manifest['build_id'],source_sha256=manifest['source_manifest_sha256'])))

if __name__=='__main__':main()
