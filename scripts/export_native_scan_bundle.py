# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Export the pinned actual saved capture for native-angle App review. Offline only."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/twinpulse_core/src"))
from twinpulse_core.native_scan import NativeScanBundle
from review_lidar_recording import summarize
from prepare_photo_scan_review import require_confirmed_pair


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_bundle(scan_dir, photo_dir):
    capture = scan_dir / "lidar-20260927T031354Z-323c99a6"
    report = json.loads((capture / "report.json").read_text(encoding="utf-8"))
    nodes_file = scan_dir / "nodes.ndjson"
    nodes = [json.loads(line) for line in nodes_file.read_text(encoding="utf-8").splitlines()]
    review = json.loads((photo_dir / "review.json").read_text(encoding="utf-8"))
    direction = json.loads((photo_dir / "top-view-evidence.json").read_text(encoding="utf-8"))
    raw_digest = sha(capture / "raw.bin")
    require_confirmed_pair(sha(photo_dir / "room.jpg"), raw_digest)
    if (review["raw_sha256"] != raw_digest or review["nodes_sha256"] != sha(nodes_file)
            or direction["related_raw_sha256"] != raw_digest
            or direction["photo_sha256"] != sha(photo_dir / "top-view-window-up.jpg")
            or direction["window_direction_in_displayed_photo"] != "up"):
        raise ValueError("source photo/scan evidence binding mismatch")
    summary, _ = summarize((capture / "raw.bin").read_bytes(), nodes, report)
    starts = [i for i, node in enumerate(nodes) if node["ring_start"]]
    frames = []
    for start, end in zip(starts, starts[1:]):
        if end - start <= 1:
            raise ValueError("incomplete ring in source capture")
        frames.append({"index": len(frames), "beams": [
            {key: node[key] for key in ("angle_deg", "distance_m", "quality", "source_byte_cursor")} | {"node_index": index}
            for index, node in enumerate(nodes[start:end], start)]})
    if len(frames) != summary["complete_scans"]:
        raise ValueError("frame inventory differs from verified source review")
    return NativeScanBundle.from_dict({"schema_version": "native-scan-bundle-1.0",
        "source": {"kind": "saved_sensor_recording", "raw_sha256": raw_digest, "nodes_sha256": sha(nodes_file),
                   "observation_start_utc": report["before"]["observed_at_utc"],
                   "observation_end_utc": report["finished_at_utc"],
                   "timestamp_basis": "host_observation_window_not_beam_time"},
        "frames": frames,
        "photos": [
            {"role": "room", "sha256": sha(photo_dir / "room.jpg"), "media_type": "image/jpeg",
             "same_position_user_declared": True, "window_direction": "unspecified"},
            {"role": "top_view", "sha256": direction["photo_sha256"], "media_type": "image/jpeg",
             "same_position_user_declared": False, "window_direction": "up"}],
        "display_hypotheses": [{key: candidate[key] for key in ("id", "rotation_deg", "mirror_native_y")}
                               for candidate in review["orientation_candidates"]]})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan-dir", type=Path, default=ROOT / "artifacts/lidar-capture-20260927-1214")
    parser.add_argument("--photo-dir", type=Path, default=ROOT / "artifacts/photo-scan-review-20260927")
    parser.add_argument("--output", type=Path, required=True, help="New file; existing evidence is never overwritten")
    args = parser.parse_args()
    bundle = build_bundle(args.scan_dir, args.photo_dir)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(bundle.to_dict(), handle, separators=(",", ":"), allow_nan=False)
    print(json.dumps({"status": "SAVED_NATIVE_BUNDLE_EXPORTED", "digest": bundle.digest,
                      "frames": len(bundle.to_dict()["frames"]), "motion_authorized": False}))


if __name__ == "__main__":
    main()
