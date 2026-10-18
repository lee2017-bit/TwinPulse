# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Local unittest record only. No inference transport, credential or robot I/O."""
import argparse
import json
from pathlib import Path
import sys
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for name in ('twinpulse_core','twinpulse_provider','twinpulse_app'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    parser.add_argument('--discover')
    parser.add_argument('modules',nargs='*')
    args=parser.parse_args()
    suite=(unittest.defaultTestLoader.discover(args.discover) if args.discover
        else unittest.defaultTestLoader.loadTestsFromNames(args.modules))
    result=unittest.TestResult();start=time.perf_counter();suite.run(result)
    report=dict(status='PASS' if result.wasSuccessful() else 'FAIL',tests=result.testsRun,
        elapsed_s=round(time.perf_counter()-start,3),skipped=len(result.skipped),
        failures=[dict(test=t.id(),detail=message.splitlines()[-1][:240]) for t,message in result.failures],
        errors=[dict(test=t.id(),detail=message.splitlines()[-1][:240]) for t,message in result.errors],
        new_model_calls=0,robot_connections=0,scope='Local regression, not LLM quality or physical acceptance')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as out:json.dump(report,out,indent=2)
    print(json.dumps(report,ensure_ascii=True))
    return 0 if result.wasSuccessful() else 1

if __name__=='__main__':raise SystemExit(main())
