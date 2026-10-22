# SPDX-License-Identifier: Apache-2.0
"""Main transcription of actual read-only Astra review, bound to built bytes."""
from hashlib import sha256
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/robot-continuous-repair-20261021'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def digest(p):return sha256(p.read_bytes()).hexdigest()
def main():
    old=read(OUT/'build24/dist/TwinPulse/_internal/resources/source-manifest.json')
    new=read(OUT/'build25/dist/TwinPulse/_internal/resources/source-manifest.json')
    manifest=read(OUT/'build25/dist/TwinPulse/windows-release-manifest.json')
    changed=sorted(k for k in old.keys()|new.keys() if old.get(k)!=new.get(k))
    assert changed==['scripts/twinpulse_engine_host.py','scripts/twinpulse_update_probe.py']
    files=changed+['tests/integration/test_update_probe.py']
    assert all(digest(ROOT/name)==new[name] for name in changed)
    value=dict(schema='read-only-independent-source-review-1.0',
        status='NO_ADDITIONAL_CONFIRMED_CRITICAL_SOURCE_DEFECT_NOT_PHYSICAL_QUALIFICATION',
        agent='/root/astra_continuous_path_review21',model='gpt-6-astra',effort='xhigh',read_only=True,
        recorded_by='Main transcription of actual collaboration messages/final review. Reviewer performed source reads, not App execution or physical tests.',
        release_id=manifest['build_id'],source_manifest_sha256=manifest['source_manifest_sha256'],
        final_reviewed_files={name:digest(ROOT/name) for name in files},
        exact_product_delta_from_frozen24=changed,unresolved=[],
        findings_fixed_before_install=[
            'Detailed stack ledger is host-only opt-in; viewport retains legacy lightweight totals only.',
            'Separate bounded slow-cycle ring preserves a later motion GC after a larger startup GC and more than32 normal cycles.',
            'Collector generation/thread pairing is verified; mismatches remain UNKNOWN, not attributed CPU.',
            'Only bounded scalar basename/function/line stack data; no frame/locals/source/arguments, locks or I/O in callback.',
            'Callback metadata failure cannot skip legacy duration totals; CPU/stack errors remain diagnostic.',
            'begin/finish and nested scopes restore prior phase tuple even on diagnostic/body exceptions without a new clock call.',
            'Review caught a transient host indentation error before build/install; final two-file AST check passed.',
            'Fault test now actually injects copy failure inside __exit__ and asserts original exception and phase restoration.'],
        supplementary='60 focused tests PASS; broader installed-source supplementary is a separately recorded job, not a hardware result.',
        limits=['Diagnosis enhancement only: not a GC scheduling/performance fix.',
            'Original33 collector generation/trigger/allocation/CPU cannot be recovered retroactively.',
            'No GC enable/disable/threshold/collection scheduling, deadline, authority, geometry or safety policy change.',
            'Current installed full UI and physical outcomes require their own evidence.'],
        evidence=[dict(path=p.name,sha256=digest(p)) for p in (OUT/'gc-ledger-red35.log',OUT/'gc-ledger-green35-reviewed-final.log',OUT/'gc-failure-review33.json')])
    with (OUT/'gc-source-review35.json').open('x',encoding='utf-8') as f:json.dump(value,f,indent=2)
    print(json.dumps(dict(status=value['status'],release_id=value['release_id'],changed=changed)))
if __name__=='__main__':main()
