# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Re-evaluate a saved manual stop recording, without transport or qualification.

Only writes a new optional output directory; never modifies the input report.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'packages/twinpulse_robot_safety'))
from stop_policy import assess_stop, POLICY, MM_PER_TICK
from teleop_contract import settling_details


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('report',type=Path)
    p.add_argument('--output',type=Path)
    a=p.parse_args()
    raw=a.report.read_bytes();report=json.loads(raw)
    rows=report['telemetry_tail'];timeout=report['timeout_seen_s']
    result={'source_sha256':hashlib.sha256(raw).hexdigest(),'original_status':report['status'],
            'data':'SAVED_RECORDING_REVIEW_NOT_A_NEW_PHYSICAL_TEST','physical_verified':False,
            'qualification_written':False,'robot_access':False,
            'legacy':settling_details(rows,timeout),
            'assessment':assess_stop(rows,timeout,report['last_send_s']), 'policy':POLICY}
    # Explicit partial-view metric, not a stand-in for complete policy coverage.
    part=[r for r in rows if timeout<r['t']<=timeout+.5]
    if len(part)>1:
        result['partial_first_to_last_wheel_net_mm']=[(part[-1]['encoders'][i]-part[0]['encoders'][i])*MM_PER_TICK for i in range(2)]
    if a.report.read_bytes()!=raw:raise ValueError('Input changed during review')
    text=json.dumps(result,indent=2,allow_nan=False)
    if a.output:
        a.output.mkdir(parents=True,exist_ok=False)
        (a.output/'review.json').write_text(text,encoding='utf-8')
    print(text)


if __name__=='__main__':main()
