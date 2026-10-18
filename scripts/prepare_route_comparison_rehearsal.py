# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Generate explicitly synthetic D6 rehearsal files; no device or engine access."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.integration.test_scan_review import route_bundle
from twinpulse_app.scan_review import ScanReview


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path, help="New directory only")
    args = parser.parse_args()
    text, baseline, candidate, pairs = route_bundle()
    service = ScanReview()
    empty = service.snapshot()
    imported = service.import_bundle(text)
    compared = service.compare(imported["workspace_revision"], imported["route_conditions"]["revision"], baseline, candidate)
    exported = service.export_review()
    blocked = service.compare(compared["workspace_revision"], compared["route_conditions"]["revision"], baseline,
                              dict(candidate, points_xy_m=[[-2., 0.], [2., 0.]]))
    assert compared["route_comparison"]["comparable"]
    assert not blocked["route_comparison"]["comparable"]
    assert not compared["motion_authorized"] and not compared["active_project_changed"]
    args.output_dir.mkdir(parents=True, exist_ok=False)
    artifacts = {"bundle.json": json.loads(text), "baseline-points.json": baseline["points_xy_m"],
                 "candidate-points.json": candidate["points_xy_m"], "pairs.json": pairs,
                 "comparison.json": compared["route_comparison"], "exported.json": exported,
                 "states.json": dict(empty=empty, imported=imported, compared=compared, blocked=blocked)}
    for name, value in artifacts.items():
        with (args.output_dir / name).open("x", encoding="utf-8") as output:
            json.dump(value, output, indent=2, allow_nan=False)
    print(f"SYNTHETIC geometry rehearsal: {args.output_dir}. Robot/Isaac NOT_RUN; not a Burger profile.")


if __name__ == "__main__":
    main()
