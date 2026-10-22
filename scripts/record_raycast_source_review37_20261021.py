# SPDX-License-Identifier: Apache-2.0
"""Main record of actual independent review and exact candidate product delta."""
from hashlib import sha256
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/robot-continuous-repair-20261021'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def digest(p):return sha256(p.read_bytes()).hexdigest()
def main():
    old=read(OUT/'build25/dist/TwinPulse/_internal/resources/source-manifest.json')
    new=read(OUT/'build26/dist/TwinPulse/_internal/resources/source-manifest.json')
    manifest=read(OUT/'build26/dist/TwinPulse/windows-release-manifest.json')
    changed=sorted(k for k in old.keys()|new.keys() if old.get(k)!=new.get(k))
    assert changed==['packages/twinpulse_core/src/twinpulse_core/lidar_geometry.py']
    assert digest(ROOT/changed[0])==new[changed[0]]
    files=changed+['tests/integration/test_lidar_geometry.py']
    value=dict(schema='read-only-independent-source-review-1.0',
        status='NO_ADDITIONAL_CONFIRMED_CRITICAL_SOURCE_DEFECT_NOT_PHYSICAL_QUALIFICATION',
        agent='/root/astra_continuous_path_review21',model='gpt-6-astra',effort='xhigh',read_only=True,
        recorded_by='Main transcription from actual source/artifact review; reviewer did not execute tests or App/robot actions.',
        release_id=manifest['build_id'],source_manifest_sha256=manifest['source_manifest_sha256'],
        final_reviewed_files={name:digest(ROOT/name) for name in files},exact_product_delta_from_frozen25=changed,unresolved=[],
        confirmed_defect='Nested recursive visit retained one function/closure-cell cycle per ray; nested build one per index. Original35 generation2 collector trigger was this raycast path.',
        fix='Module-level stable builder; explicit DFS with right pushed first and left visited first. No recursive closure per ray/index.',
        preserved=['100000 segment bound','stable sort/axis/8-item leaves','cancel before None and each node','AABB pruning and1e-12/1e-9/1e-7','strict t<best/maximum/no fake endpoint','scan rounding','all deadlines/GC policy/authority'],
        supplementary='23 geometry/scan-worker tests PASS; isolated python-I GC-disabled weakref and closure RED2 then GREEN, independent fixed-seed300-ray intersections, first-hit and cancel order. GC policy changes only inside disposable no-device test subprocesses.',
        preserved_test_attempt='First combined GREEN had an App import-path fixture error; original log retained, explicit correct package paths then passed. No product change used to hide it.',
        limits=['Collected1856 objects are not all attributed to these closures; full735ms cost is not solely proven from them.',
            'Confirmed unnecessary allocation-cycle removal, not all-GC elimination or a whole-cycle/physical result.',
            'SitePlan revision allocation optimization is separate and unchanged.'],
        evidence=[dict(path=p.name,sha256=digest(p)) for p in (OUT/'gc-failure-review35.json',OUT/'raycast-cycle-red37-isolated.log',
            OUT/'raycast-cycle-green37.log',OUT/'raycast-cycle-green37-path-corrected.log',OUT/'raycast-cycle-green37-final.log')])
    with (OUT/'raycast-source-review37.json').open('x',encoding='utf-8') as f:json.dump(value,f,indent=2)
    print(json.dumps(dict(status=value['status'],release_id=value['release_id'],changed=changed)))
if __name__=='__main__':main()
