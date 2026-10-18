# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Developer-only synthetic fixture and state snapshots for offline browser tests.

Uses the regression fixture, no transport/engine/device. Never a physical recording.
"""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
for source in ["packages/twinpulse_core/src", "packages/twinpulse_app/src", "packages/twinpulse_provider/src", "packages/twinpulse_core/tests"]:
    sys.path.insert(0, str(ROOT / source))
from test_scan_correction import fixture
from twinpulse_app.scan_review import ScanReview


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path, help="New directory only")
    args = parser.parse_args()
    plan, recording, matches = fixture()
    bundle = {"schema_version": "offline-scan-bundle-1.0", "site_plan": plan.to_dict(), "recording": recording.to_dict()}
    pairs = json.loads(json.dumps([asdict(p) for p in matches]))
    service = ScanReview()
    empty = service.snapshot()
    imported = service.import_bundle(json.dumps(bundle))
    proposed = service.propose(imported["workspace_revision"], "observed_box", pairs)
    applied = service.apply(proposed["workspace_revision"], proposed["proposal"]["revision"])
    exported = service.export_review()
    undone = service.undo(applied["workspace_revision"], applied["edit_revision"])
    assert undone["scene"]["objects"] == imported["scene"]["objects"]
    assert not applied["map_present"] and not applied["mission_present"]
    args.output_dir.mkdir(parents=True, exist_ok=False)
    artifacts = {"bundle.json": bundle, "pairs.json": pairs,
                 "states.json": dict(empty=empty, imported=imported, proposed=proposed, applied=applied, undone=undone, exported=exported)}
    for name, value in artifacts.items():
        with (args.output_dir / name).open("x", encoding="utf-8") as output:
            json.dump(value, output, indent=2, allow_nan=False)
    print(f"Synthetic offline rehearsal prepared: {args.output_dir}; actual robot/Isaac NOT_RUN")


if __name__ == "__main__":
    main()
