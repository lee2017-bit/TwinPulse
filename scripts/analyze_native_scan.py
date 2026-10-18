# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Save a descriptive audit of a local native scan bundle; no robot operations."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/twinpulse_core/src"))
from twinpulse_core.native_scan import NativeScanBundle
from twinpulse_core.native_scan_quality import analyze_native_scan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("output", type=Path, help="New JSON file only")
    args = parser.parse_args()
    result = analyze_native_scan(NativeScanBundle.from_text(args.bundle.read_text(encoding="utf-8")))
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
    print(json.dumps({key: result[key] for key in ("assessment", "frame_count", "sample_count", "excluded_count",
                     "excluded_percent", "min_usable_per_frame", "max_usable_per_frame", "worst_return_gap_deg",
                     "never_observed_angle_bins", "clearance", "motion_authorized")}, indent=2))


if __name__ == "__main__": main()
