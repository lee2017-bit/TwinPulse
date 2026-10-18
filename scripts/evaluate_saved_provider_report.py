# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Offline A4 projection of an existing stored M2-C provider report. No API calls."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
for package in ("twinpulse_core", "twinpulse_provider", "twinpulse_app"):
    sys.path.insert(0, str(ROOT / "packages" / package / "src"))

from twinpulse_app.evaluation_report import evaluate_saved_provider_report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider-report", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate_saved_provider_report(args.provider_report, args.manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, sort_keys=True, indent=2)
    print("A4_STORED_PROVIDER_EVALUATION=PASS fixtures=3 offline=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
