# SPDX-License-Identifier: Apache-2.0
"""Transcribe completed independent reviews, not an invented App verdict."""
from hashlib import sha256
import argparse
import json
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--revision',choices=('','b','c'),default='');args=parser.parse_args()
OUT=ROOT/'outputs/robot-continuous-repair-20261021'
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
active=read(Path(os.environ['LOCALAPPDATA'])/'TwinPulse/installed/active-release.json')
parent=read(OUT/'source-review52.json')
unchanged={name:digest for name,digest in parent['final_reviewed_files'].items()
           if sha256((ROOT/name).read_bytes()).hexdigest()==digest}
names=[*unchanged,'scripts/twinpulse_live_viewport.py','scripts/verify_robot_focus_gate.py',
       'scripts/verify_robot_fleet_ui.mjs','scripts/verify_continuous_gate_negatives_20261021.py',
       'scripts/finalize_continuous_review_20261021.py','scripts/report_continuous_repair_20261021.py',
       'scripts/run_saved_sim_preparation_20261022.ps1','scripts/prepare_saved_sim_clearance_20261022.mjs',
       'tests/integration/test_live_viewport.py','tests/integration/test_robot_focus_gate.py',
       'tests/integration/test_continuous_report_binding.py','packages/twinpulse_app/src/twinpulse_app/project_catalog.py',
       'packages/twinpulse_app/src/twinpulse_app/request_latency.py','packages/twinpulse_app/src/twinpulse_app/api.py']
exact={'project_catalog.py':'0b1450a260cb506998d65b76d35a5f74af5f1b6b591530cb5a69234b58cb7474',
       'request_latency.py':'3a7d4cf3f56ce60b5ad8a478ea96def52cfc54a168ad2770c611551a9d13d517',
       'api.py':'e65a5b8eb534b885b7b6913f3aa57d107148b880aff7d65cb55b3a51b99adea1'}
for name,digest in exact.items():
    assert sha256((ROOT/'packages/twinpulse_app/src/twinpulse_app'/name).read_bytes()).hexdigest()==digest
result=dict(schema='read-only-independent-source-review-1.0',
    status='NO_ADDITIONAL_CONFIRMED_CRITICAL_SOURCE_DEFECT_NOT_PHYSICAL_QUALIFICATION',
    agent='/root/sol_catalog_final_review22',model='gpt-6.1-sol',effort='high',read_only=True,
    recorded_by='Main transcription of actual independent collaboration reviews; no reviewer file/App/robot mutations.',
    release_id=active['release_id'],source_manifest_sha256=active['source_manifest_sha256'],unresolved=[],
    final_reviewed_files={name:sha256((ROOT/name).read_bytes()).hexdigest() for name in dict.fromkeys(names)},
    source_review_parent=dict(path='source-review52.json',sha256=sha256((OUT/'source-review52.json').read_bytes()).hexdigest()),
    scopes=[dict(agent='/root/astra_continuous_path_review21',model='gpt-6-astra',effort='xhigh',
        scope='Private diagnostic wake/unchanged bounded joins; seven-launch shutdown and selected reproduction SHA; explicit source-bound SIM prep helper. Source-only before use-limit.'),
        dict(agent='/root/sol_catalog_final_review22',model='gpt-6.1-sol',effort='high',
        scope='Three final catalog/diagnostic product files; retained selected-path safety/ranking/output; optional begin/finish/header errors neutral; 87 targeted tests. Then F01-F12 tool review: full selected reproduction phase/project/scene/steps/errors/angles/scan/display and shared exact Stop ACK, seven-launch cleanup, required explicit source review and report selection; 46 gate/report tests.')],
    findings_fixed=['Diagnostic Queue.get/join race: nonblocking sentinel wake, blocked writer still fails',
        'Separate reproduction excluded from inner shutdown gate: exact seventh launch and selected path/SHA now required',
        'Unselected catalog metadata repeatedly resolved: DirEntry ranking, fresh selected/open checks retained',
        'Optional diagnostic begin/finish/header clock could abort or mask a product result: narrow isolation and original-error tests'],
    limits=['Actual installed whole57/58 and final machine gate are separately required',
        'Original53 ordinary projects6000ms abort remains FAIL; stack enumeration overlaps memory pressure, sole cause UNKNOWN',
        'Offline equal response hashes/timing comparison is not loaded HTTP acceptance or full causal attribution',
        'Historical failures and original unknown LiDAR bytes remain unchanged',
        'Physical acquisition/Pi load/storage/braking/continuous driving/world alignment NOT_RUN_ROBOT_OFF',
        'Legacy private-bedroom asset and old strict listing unit failures recur on exact installed32; not relabelled PASS'])
with (OUT/f'source-review57{args.revision}.json').open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
print(json.dumps(dict(status=result['status'],release_id=result['release_id'],files=len(result['final_reviewed_files']))))
