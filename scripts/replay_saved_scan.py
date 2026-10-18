# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Validate a local stationary scan recording and write an offline review preview.

Only local file I/O and pure geometry; no transport, device, engine or scene edits.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages/twinpulse_core/src"))
from twinpulse_core.scan_recording import MAX_BYTES, ScanRecording


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", type=Path)
    parser.add_argument("--site", required=True)
    parser.add_argument("--scene-revision", required=True)
    parser.add_argument("--profile-digest", required=True)
    parser.add_argument("--output", required=True, type=Path, help="New JSON file; existing files are never overwritten")
    args = parser.parse_args(argv)
    try:
        with args.recording.open("rb") as source:
            recording = ScanRecording.from_json(source.read(MAX_BYTES + 1))
        preview = recording.replay(site_id=args.site, scene_revision=args.scene_revision,
                                   robot_profile_digest=args.profile_digest)
        payload = json.dumps(preview, indent=2, allow_nan=False) + "\n"
        with args.output.open("x", encoding="utf-8") as target:
            target.write(payload)
    except (OSError, ValueError) as exc:
        print(f"Offline scan review failed: {exc}", file=sys.stderr)
        return 2
    print(f"Offline preview saved: {args.output}; provenance={recording.provenance}; physical_validation=NOT_RUN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
