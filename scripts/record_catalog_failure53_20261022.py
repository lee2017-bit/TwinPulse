# SPDX-License-Identifier: Apache-2.0
"""Original-request and same-window resource analysis; no product calls."""
from hashlib import sha256
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/robot-continuous-repair-20261021'
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
ui=read(OUT/'ui-53/result.json')
row=next(r for r in ui['network_failures'] if r['path']=='/v1/product/projects')
begin=row['cdp_wall_time']*1000
end=begin+(row['failure_cdp_timestamp']-row['cdp_timestamp'])*1000
samples=[json.loads(line) for line in (OUT/'memory-final53/samples.jsonl').read_text(encoding='utf-8').splitlines()]
window=[dict(at_ms=r['at_ms'],physical_available_bytes=r['system']['PhysicalAvailable_bytes'],
             system_commit_bytes=r['system']['CommitTotal_bytes']) for r in samples if begin<=r['at_ms']<=end]
refs=[]
for name in ('ui-53/result.json','failed-ui53-original-logs/receipt.json','memory-final53/receipt.json',
             'catalog53-before/result.json','catalog53-after/result.json','catalog-baseline32-failures57b.log'):
    p=OUT/name;refs.append(dict(path=name,sha256=sha256(p.read_bytes()).hexdigest()))
value=dict(classification='ORIGINAL_FAILED53_READ_ONLY_ANALYSIS_NOT_APP_ACCEPTANCE',status='FAIL_PRESERVED',
    launch_id=ui['desktop']['engine']['launch_id'],project=ui['project'],original_status=ui['status'],
    original_step_pass=sum(s['status']=='PASS' for s in ui['steps']),request=row,native_duration_ms=end-begin,
    memory_original_window=window,
    direct_observation='Frozen backend all-thread stack includes project_catalog.snapshot/nlargest/candidates/Path.is_dir/stat during the request window.',
    unknown='No exact projects request CPU/subphase telemetry existed. Memory pressure and Kit/backend work overlapped; metadata enumeration is not proven sole cause of the full6.027s.',
    change='DirEntry caches only candidate ranking metadata; selected64/active/open fresh checks unchanged. Original projects6s deadline and ordinary abort FAIL retained.',
    baseline='Original installed32 catalog repeats same2legacyFAIL/6errors in7tests: private-bedroom asset hashes and old strict-listing expectation. No failure relabelled PASS.',
    references=refs)
with (OUT/'catalog-failure53-review.json').open('x',encoding='utf-8') as stream:json.dump(value,stream,indent=2)
print(json.dumps(dict(status=value['status'],step_pass=value['original_step_pass'],native_duration_ms=value['native_duration_ms'],memory_samples=len(window))))
