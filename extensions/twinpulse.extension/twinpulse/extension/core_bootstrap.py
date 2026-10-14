# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Make repository-owned pure Python packages available to the Extension."""

from __future__ import annotations

from pathlib import Path
import sys


def add_core_to_path() -> Path:
    repo_root = Path(__file__).resolve().parents[4]
    core_src = repo_root / "packages" / "twinpulse_core" / "src"
    if not core_src.is_dir():
        raise RuntimeError(f"TwinPulse core source not found: {core_src}")
    core_path = str(core_src)
    if core_path not in sys.path:
        sys.path.insert(0, core_path)
    provider_src = repo_root / "packages" / "twinpulse_provider" / "src"
    if provider_src.is_dir():
        provider_path = str(provider_src)
        if provider_path not in sys.path:
            sys.path.insert(0, provider_path)
    app_src = repo_root / "packages" / "twinpulse_app" / "src"
    if app_src.is_dir():
        app_path = str(app_src)
        if app_path not in sys.path:
            sys.path.insert(0, app_path)
    return core_src
