# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Append a monetary-evidence supplement; never modify original UNKNOWN/hold."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.progressive_functional_scope import host_finance_supplement,exclusive


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('scope',type=Path)
    args=parser.parse_args();scope=args.scope.resolve()
    supplement=host_finance_supplement(scope,ROOT)
    exclusive(scope.parent/'host-finance-supplement.json',supplement)
    print(json.dumps(dict(status=supplement['classification'],case_id=supplement['case_id'],
        protected_exposure_usd=supplement['protected_exposure_usd'],
        estimated_wire_usd=supplement['estimated_wire_usd'],
        original_unknown_preserved=True,original_hold_released=False,new_http_requests=0)))


if __name__=='__main__':main()
