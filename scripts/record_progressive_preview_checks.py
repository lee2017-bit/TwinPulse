# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Record scoped local regressions without printing giant diagnostic payloads."""
import argparse
from io import StringIO
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT)]+[str(ROOT/'packages'/name/'src') for name in ('twinpulse_core','twinpulse_provider','twinpulse_app')]+[str(ROOT/'packages/twinpulse_provider/tests')]


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('suite',choices=['provider','api','core']);parser.add_argument('output',type=Path)
    args=parser.parse_args();output=args.output.resolve()
    if not output.is_relative_to(ROOT/'outputs'):raise SystemExit('OUTPUT_OUTSIDE_WORKSPACE')
    output.mkdir(parents=True,exist_ok=False)
    loader=unittest.TestLoader()
    suite=(loader.discover(str(ROOT/'packages/twinpulse_provider/tests')) if args.suite=='provider' else
        loader.discover(str(ROOT/'packages/twinpulse_core/tests')) if args.suite=='core' else loader.loadTestsFromNames([
        'tests.integration.test_generation_approval','tests.integration.test_generation_render_port',
        'tests.integration.test_generation_visual','tests.integration.test_room_visuals',
        'tests.integration.test_live_viewport',
        'tests.integration.test_room_items','tests.integration.test_model_library','tests.integration.test_photo_placement',
        'tests.integration.test_scene_feedback_chat','tests.integration.test_scene_edit_transaction']))
    captured=StringIO();result=unittest.TextTestRunner(stream=captured,verbosity=1).run(suite)
    (output/'unittest.log').write_text(captured.getvalue(),encoding='utf-8')
    summary=dict(status='PASS' if result.wasSuccessful() else 'PARTIAL',tests=result.testsRun,
        failures=[dict(test=str(test),exception=trace.splitlines()[-1][:300]) for test,trace in result.failures],
        errors=[dict(test=str(test),exception=trace.splitlines()[-1][:300]) for test,trace in result.errors],
        skipped=len(result.skipped),external_requests=0)
    (output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(json.dumps(summary))
    return 0 if result.wasSuccessful() else 1


if __name__=='__main__':raise SystemExit(main())
