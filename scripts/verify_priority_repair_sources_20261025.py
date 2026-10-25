# SPDX-License-Identifier: Apache-2.0
"""Bind this repair to its predecessor; no runtime or robot actions."""
import hashlib,json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/robot-data-priority-20261025-01'
base=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/installed/releases'
old=base/'20261024T205438Z-be150e10b23f'
new=base/'20261025T034741Z-1387861a7bfd'
read=lambda p:json.loads(p.read_bytes())
a=read(old/'_internal/resources/source-manifest.json');b=read(new/'_internal/resources/source-manifest.json')
changed=[dict(path=p,before=a.get(p),after=b.get(p)) for p in sorted(a.keys()|b.keys()) if a.get(p)!=b.get(p)]
expected={'packages/twinpulse_app/src/twinpulse_app/robot_task_service.py',
    'packages/twinpulse_app/src/twinpulse_app/physical_task_map.py',
    'packages/twinpulse_app/src/twinpulse_app/environment_survey_review.py'}
checks=dict(same_file_set=a.keys()==b.keys(),only_expected_product_sources_changed={r['path'] for r in changed}==expected,
    current_sources_exact=all(hashlib.sha256((ROOT/r['path']).read_bytes()).hexdigest()==r['after'] for r in changed))
value=dict(status='PASS' if all(checks.values()) else 'FAIL',scope='SOURCE_DIFFERENCE_NOT_PHYSICAL_SUCCESS',checks=checks,
    predecessor=old.name,current=new.name,manifest_members=len(b),changed=changed)
(OUT/'source-comparison01.json').write_text(json.dumps(value,indent=2),encoding='utf-8')
print(json.dumps(value))
