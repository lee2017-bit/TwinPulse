# SPDX-License-Identifier: Apache-2.0
"""Recheck the original19 SHA-bound segments; no robot/provider calls."""
import json
from pathlib import Path
from analyze_robot_timing_20261020 import analyze,ROOT
out=ROOT/'outputs/robot-protocol-prep-20261020'
current=analyze(ROOT/'outputs/robot-powered-20261020-current07')
original=json.loads((ROOT/'outputs/robot-timing-settings-20261020/original-analysis.json').read_text())
same=current['sources']==original['sources'] and current['original_failures']==original['original_failures']
result=dict(status='PASS_ORIGINAL_BYTES_UNCHANGED' if same else 'FAIL',scope='RECORDED_INPUT_RECALCULATION_NOT_NEW_HARDWARE',
    original_operation=current['import_report']['operation_id'],segments=current['sources'],original_failures=current['original_failures'],
    values=current['recommendation']['profile']['values'],raw_integrity=current['raw_integrity'])
(out/'original19-recheck.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='segments'}))
raise SystemExit(0 if same else 1)
