# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Finite S1d acceptance for graceful and forced owned-Isaac shutdown."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
for source in (
    ROOT / "packages" / "twinpulse_core" / "src",
    ROOT / "packages" / "twinpulse_provider" / "src",
    ROOT / "packages" / "twinpulse_app" / "src",
):
    sys.path.insert(0, str(source))

from twinpulse_app import TwinPulseProcessManager  # noqa: E402


def _run_case(name: str, *, isaac_python: Path, root: Path, timeout_s: float) -> dict[str, object]:
    state_dir = root / name
    manager = TwinPulseProcessManager(
        repo_root=ROOT,
        state_dir=state_dir,
        python_executable=Path(sys.executable),
        isaac_python=isaac_python,
        headless=True,
        ready_timeout_s=timeout_s,
    )
    started = time.monotonic()
    stopped = False
    try:
        launch = manager.start(open_browser=False)
        engine_process = manager._owned["engine"]
        backend_process = manager._owned["backend"]
        engine_job = manager._jobs.get("engine")
        if engine_job is None:
            raise RuntimeError("actual engine was not assigned to an owned Windows Job Object")
        active_members = engine_job.active_process_count()
        if active_members < 1:
            raise RuntimeError("owned engine Job Object has no active process")

        shutdown_started = time.monotonic()
        if name == "forced":
            manager._stop_owned("engine", graceful_s=0.0)
            manager.stop()
        else:
            manager.stop()
        stopped = True
        shutdown_s = time.monotonic() - shutdown_started
        if engine_process.poll() is None or backend_process.poll() is None:
            raise RuntimeError("owned root process survived shutdown")
        return {
            "case": name,
            "launch_id": launch.launch_id,
            "engine_pid": launch.engine_pid,
            "backend_pid": launch.backend_pid,
            "engine_job_active_members_before_stop": active_members,
            "engine_exit_code": engine_process.returncode,
            "backend_exit_code": backend_process.returncode,
            "shutdown_s": round(shutdown_s, 3),
            "elapsed_s": round(time.monotonic() - started, 3),
            "result": "PASS",
        }
    finally:
        if not stopped:
            manager.stop(final_status="error")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--isaac-python", type=Path, default=Path(r"C:\isaacsim\python.bat"))
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--ready-timeout-s", type=float, default=180.0)
    parser.add_argument("--case", choices=("graceful", "forced", "both"), default="both")
    args = parser.parse_args()

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-s1d-boundary"
    output_root = (args.output_root or ROOT / "artifacts" / "runs" / run_id).resolve()
    output_root.mkdir(parents=True, exist_ok=False)
    cases = ("graceful", "forced") if args.case == "both" else (args.case,)
    result: dict[str, object] = {
        "schema_version": "1.0",
        "run_id": run_id,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "paid_provider_requests": 0,
        "cases": [],
    }
    result_path = output_root / "result.json"
    try:
        result["cases"] = [
            _run_case(
                case,
                isaac_python=args.isaac_python.resolve(),
                root=output_root,
                timeout_s=args.ready_timeout_s,
            )
            for case in cases
        ]
        result["result"] = "PASS"
        return_code = 0
    except Exception as error:
        result["result"] = "FAIL"
        result["error"] = f"{type(error).__name__}: {error}"
        return_code = 1
    result["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"result": result["result"], "run_id": run_id, "result_path": str(result_path)}))
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
