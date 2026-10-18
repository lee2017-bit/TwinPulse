# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Download the fixed, attributed M2-C warehouse images and verify their hashes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import requests


REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=REPO_ROOT / "fixtures" / "m2c" / "warehouse_images.json",
    )
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": "TwinPulse-M2C-Research-Fixture/1.0"}

    for fixture in manifest["fixtures"]:
        destination = args.output_dir / fixture["local_filename"]
        response = requests.get(fixture["download_url"], headers=headers, timeout=60)
        response.raise_for_status()
        content = response.content
        digest = hashlib.sha256(content).hexdigest()
        if digest != fixture["sha256"]:
            raise RuntimeError(f"{fixture['id']}: SHA-256 mismatch")
        if not content.startswith(b"\xff\xd8\xff"):
            raise RuntimeError(f"{fixture['id']}: downloaded content is not JPEG")
        destination.write_bytes(content)
        print(f"fixture={fixture['id']} bytes={len(content)} sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
