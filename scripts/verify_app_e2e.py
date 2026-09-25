"""Finite R6 launcher -> browser -> actual Isaac acceptance runner.

This runner reuses the deterministic R5 browser journey. It never performs a
new paid provider request and it stops only backend/engine children that were
started by its own process manager.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time
import traceback
import zlib


ROOT = Path(__file__).resolve().parents[1]
for source in (
    ROOT / "packages" / "twinpulse_core" / "src",
    ROOT / "packages" / "twinpulse_provider" / "src",
    ROOT / "packages" / "twinpulse_app" / "src",
):
    sys.path.insert(0, str(source))

from twinpulse_app import TwinPulseProcessManager  # noqa: E402


def _browser(configured: Path | None) -> Path:
    candidates = [
        configured,
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return candidate.resolve()
    raise RuntimeError("Chrome or Edge executable was not found")


def _input_png(path: Path, width: int = 96, height: int = 64) -> None:
    def chunk(kind: bytes, data: bytes) -> bytes:
        checksum = zlib.crc32(kind + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)

    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            aisle = 220 if width // 3 < x < width * 2 // 3 else 70
            rows.extend((aisle, min(255, 80 + y * 2), min(255, 110 + x)))
    payload = b"\x89PNG\r\n\x1a\n"
    payload += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    payload += chunk(b"IDAT", zlib.compress(bytes(rows), level=9))
    payload += chunk(b"IEND", b"")
    path.write_bytes(payload)


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{time.monotonic_ns()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8",
    )
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--isaac-root", type=Path, default=Path(r"C:\isaacsim"))
    parser.add_argument("--artifact-dir", type=Path)
    parser.add_argument("--browser", type=Path)
    parser.add_argument("--visible-isaac", action="store_true")
    parser.add_argument("--timeout-s", type=float, default=180.0)
    args = parser.parse_args()

    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    artifact_dir = (args.artifact_dir or ROOT / "artifacts" / "runs" / run_id / "r6-app").resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    state_dir = artifact_dir / "runtime"
    screenshot_dir = artifact_dir / "browser"
    browser_result_file = artifact_dir / "browser-result.json"
    input_image = artifact_dir / "input.png"
    result_file = artifact_dir / "result.json"
    _input_png(input_image)

    result: dict[str, object] = {
        "schema_version": "1.0", "status": "FAIL", "run_id": run_id,
        "artifact_dir": str(artifact_dir), "live_provider_request": "NOT_RUN",
    }
    manager = TwinPulseProcessManager(
        repo_root=ROOT,
        state_dir=state_dir,
        python_executable=Path(sys.executable),
        isaac_python=(args.isaac_root / "python.bat"),
        browser_executable=_browser(args.browser),
        headless=not args.visible_isaac,
        fixture_mode=True,
        ready_timeout_s=min(args.timeout_s, 180.0),
    )
    browser_process: subprocess.Popen[str] | None = None
    try:
        launch = manager.start(open_browser=False)
        base_url, product_secret = manager.product_bootstrap()
        node = shutil.which("node")
        if node is None:
            raise RuntimeError("Node.js executable was not found")
        environment = os.environ.copy()
        environment.update({
            "TWINPULSE_R5_URL": base_url,
            "TWINPULSE_PRODUCT_BOOTSTRAP": product_secret,
            "TWINPULSE_CHROME": str(manager.browser_executable),
            "TWINPULSE_R5_IMAGE": str(input_image),
            "TWINPULSE_R5_BROWSER_RESULT": str(browser_result_file),
            "TWINPULSE_R5_SCREENSHOT_DIR": str(screenshot_dir),
        })
        browser_process = subprocess.Popen(
            [node, str(ROOT / "apps" / "twinpulse-web" / "e2e" / "r5-browser.mjs")],
            cwd=str(ROOT / "apps" / "twinpulse-web"), env=environment,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), shell=False,
        )
        try:
            browser_output, _ = browser_process.communicate(timeout=args.timeout_s)
        except subprocess.TimeoutExpired:
            browser_process.kill()
            browser_output, _ = browser_process.communicate(timeout=10.0)
            raise TimeoutError("Browser acceptance exceeded its finite timeout")
        result["browser_output_tail"] = browser_output[-1500:]
        if browser_process.returncode != 0 or not browser_result_file.is_file():
            raise RuntimeError(f"Browser acceptance failed with code {browser_process.returncode}")
        browser_result = _read_json(browser_result_file)
        result["browser"] = browser_result
        if browser_result.get("status") != "PASS":
            raise AssertionError(f"Browser result is not PASS: {browser_result}")

        result["launch"] = {
            "launch_id": launch.launch_id,
            "backend_pid": launch.backend_pid, "engine_pid": launch.engine_pid,
            "stage_epoch": launch.stage_epoch, "capabilities": list(launch.capabilities),
        }
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {error}"
        result["traceback"] = traceback.format_exc()
    finally:
        if browser_process is not None and browser_process.poll() is None:
            browser_process.kill()
            browser_process.wait(timeout=10.0)
        manager.stop()

    try:
        engine_result = _read_json(manager.engine_result_file)
        result["engine"] = engine_result
        browser_pass = isinstance(result.get("browser"), dict) and result["browser"].get("status") == "PASS"  # type: ignore[union-attr]
        capture = engine_result.get("capture")
        capture_request = capture.get("request") if isinstance(capture, dict) else None
        capture_timestamps = capture.get("timestamps") if isinstance(capture, dict) else None
        capture_attempts = capture.get("attempts") if isinstance(capture, dict) else None
        capture_path = capture.get("path") if isinstance(capture, dict) else None
        capture_pass = bool(
            isinstance(capture, dict)
            and capture.get("status") == "PASS"
            and isinstance(capture_request, dict)
            and capture_request.get("stage_epoch") == engine_result.get("stage_epoch")
            and capture_request.get("applied_revision") == engine_result.get("applied_revision")
            and isinstance(capture_timestamps, dict)
            and all(capture_timestamps.get(name) for name in (
                "requested_at", "task_returned_at", "first_file_seen_at",
                "size_stable_at", "decoded_at", "completed_at",
            ))
            and isinstance(capture_attempts, list)
            and 1 <= len(capture_attempts) <= 2
            and isinstance(capture_path, str)
            and Path(capture_path).resolve() == manager.viewport_capture_file.resolve()
            and manager.viewport_capture_file.is_file()
        )
        engine_pass = (
            engine_result.get("status") == "PASS"
            and capture_pass
            and isinstance(engine_result.get("applied_revision"), str)
            and int(engine_result.get("prim_count", 0)) > 0
            and float(engine_result.get("max_movement_m", 0.0)) > 0.02
            and {"running", "paused"}.issubset(set(engine_result.get("observed_states", [])))
        )
        if browser_pass and engine_pass and "error" not in result:
            result["status"] = "PASS"
        elif "error" not in result:
            result["error"] = "Acceptance evidence was incomplete"
    except Exception as error:
        if "error" not in result:
            result["error"] = f"{type(error).__name__}: {error}"
            result["traceback"] = traceback.format_exc()

    _write_json_atomic(result_file, result)
    print(f"TWINPULSE_R6_RESULT={result['status']} artifact_dir={artifact_dir}", flush=True)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
