# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""PC-only audit of the declared demo operation inventory."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'packages/twinpulse_core/src'))
from twinpulse_core.demo_contract import audit


def main():
    report = audit(ROOT)
    print(json.dumps(report, indent=2))
    return 0 if report['offline_inventory_complete'] and report['manifest_mapped'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
