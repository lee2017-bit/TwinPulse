# SPDX-License-Identifier: Apache-2.0
"""Main transcription of actual read-only Astra review; no App/model/device."""
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
    old=read(OUT/'build26/dist/TwinPulse/_internal/resources/source-manifest.json')
    new=read(OUT/'build27/dist/TwinPulse/_internal/resources/source-manifest.json')
    manifest=read(OUT/'build27/dist/TwinPulse/windows-release-manifest.json')
    changed=sorted(k for k in old.keys()|new.keys() if old.get(k)!=new.get(k))
    assert changed==['packages/twinpulse_app/src/twinpulse_app/fleet_recorder.py'],changed
    assert sha256((ROOT/changed[0]).read_bytes()).hexdigest()==new[changed[0]]
    tests=['tests/integration/test_fleet_snapshot_encoding.py']
    review=dict(schema='read-only-independent-source-review-1.0',status='NO_ADDITIONAL_CONFIRMED_CRITICAL_SOURCE_DEFECT_NOT_PHYSICAL_QUALIFICATION',
        agent='/root/astra_continuous_path_review21',model='gpt-6-astra',effort='xhigh',read_only=True,
        recorded_by='Main transcription of actual source and eight-test read-only Astra review; reviewer executed no App, tests, system or robot actions.',
        release_id=manifest['build_id'],source_manifest_sha256=manifest['source_manifest_sha256'],
        final_reviewed_files={name:sha256((ROOT/name).read_bytes()).hexdigest() for name in changed+tests},
        exact_product_delta_from_frozen26=changed,unresolved=[],
        findings=['Per-event encode retains canonical hash, wire separators and original top-level order; no mutable identity cache.',
            'NaN/circular/encoding exceptions remain sticky; atomic replace, capacity and original close deadline unchanged.',
            'No additional confirmed source blocker in this delta; current full installed acceptance remains required.'],
        references=[ref(OUT/name) for name in ('snapshot-baseline39.json','snapshot-eventwise39.json','snapshot-regression41.log','raycast-source-review37.json')],
        limits=['Original39 overall FAIL remains immutable.', 'Snapshot CPU/time reduction is not proof of sole old root cause or better peer maximum gap.',
            'Large individual event encoding has no guaranteed latency ceiling; sleep(0)/batch32 are not control or sensor timeouts.',
            'No timeout/authority/geometry/GC-policy change. Physical/Pi/storage/braking/world alignment NOT_RUN.'])
    write(OUT/'snapshot-source-review41.json',review)
    ui=read(OUT/'ui-39/result.json');assert ui['status']=='FAIL'
    value=dict(status='ORIGINAL_FAIL_PRESERVED_SNAPSHOT_CONCURRENT_LOAD_NOT_SOLE_CAUSE_PROOF',
        launch_id=ui['desktop']['engine']['launch_id'],release_id=ui['desktop']['engine']['release_id'],project=ui['project'],
        failure_at_ms=1792596981641,displayed_frame=1608,displayed_age_ms=707.195556640625,
        chronology=[dict(at_ms=1792596981491,event='Atomic204/stale/no current; last1605 captured1792596980443.2905 is about1048ms old.'),
            dict(at_ms=1792596981590,event='Metadata200 now has1608; contract imports only last_frame, not JPEG/current authority.'),
            dict(at_ms=1792596981641,event='1608 static decode previewOnly/livefalse/anchors absent, so whole current-display criterion fails.'),
            dict(at_ms=1792596981731,event='Subsequent atomic200/1608 arrives90ms after failed check; not substituted for it.')],
        command_outcome='Original event1233 NAVIGATION_ARRIVED at1792596980309; not ISAAC_UPDATE_STALLED or navigation-target failure.',
        concurrent_snapshot=dict(operation_id='ebe1a33b79d44a69841d63c88dd9dcf3',events=1234,bytes=3805301,start_at_ms=1792596980313.2905,
            elapsed_ms=1437.7125,materialize_ms=554.6142,encode_ms=853.4801,file_ms=29.6182),
        limitations=['Current source already used iterencode; not a single whole-history C-encoder hold.',
            'Exact1605/1608 raw-wait/JPEG/upload stage breakdown was not retained; contribution of GIL/locks/CPU remains UNKNOWN.',
            'No metadata promotion, stale-live exception, guard relaxation or retroactive PASS.'],
        references=[ref(OUT/name) for name in ('ui-39/result.json','failed-ui39-original-logs/receipt.json',
            'failed-ui39-original-logs/00-backend.log','failed-ui39-original-logs/10-ebe1a33b79d44a69841d63c88dd9dcf3.json',
            'runtime-final39/receipt.json','memory-final39/receipt.json','budget-final39.json')])
    write(OUT/'snapshot-failure39-review.json',value)
    print(json.dumps(dict(status='SOURCE_REVIEW_RECORDED_NOT_UI_ACCEPTANCE',release_id=manifest['build_id'],changed=changed)))
if __name__=='__main__':main()
