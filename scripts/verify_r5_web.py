"""Finite R5 browser -> authenticated backend -> actual Isaac acceptance."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import secrets
import shutil
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import traceback
import zlib


ROOT = Path(__file__).resolve().parents[1]
TEMP_PARENT = os.environ.get("TWINPULSE_TEST_TMP")
STATE = TemporaryDirectory(prefix="tmp-r5-web-", dir=TEMP_PARENT)
os.environ["TWINPULSE_STATE_DIR"] = str(Path(STATE.name) / "extension-state")

from isaacsim import SimulationApp  # noqa: E402


APP = SimulationApp({
    "headless": True,
    "renderer": "MinimalRendering",
    "disable_viewport_updates": True,
    "width": 640,
    "height": 480,
})

RESULT: dict[str, object] = {"status": "FAIL", "browser": {}, "actual_isaac": {}}


def _png(path: Path, width: int = 96, height: int = 64) -> None:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            aisle = 220 if width // 3 < x < width * 2 // 3 else 80
            rows.extend((aisle, min(255, 90 + y * 2), min(255, 120 + x)))
    payload = b"\x89PNG\r\n\x1a\n"
    payload += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    payload += chunk(b"IDAT", zlib.compress(bytes(rows), level=9))
    payload += chunk(b"IEND", b"")
    path.write_bytes(payload)


def _chrome() -> Path:
    configured = os.environ.get("TWINPULSE_CHROME")
    candidates = [
        Path(configured) if configured else None,
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return candidate
    raise RuntimeError("System Chrome executable was not found")


def _start_backend(directory: Path) -> tuple[subprocess.Popen[str], dict[str, object], str, str]:
    product_secret = secrets.token_urlsafe(32)
    engine_secret = secrets.token_urlsafe(32)
    ready_file = directory / "backend-ready.json"
    environment = os.environ.copy()
    environment["TWINPULSE_PRODUCT_BOOTSTRAP"] = product_secret
    environment["TWINPULSE_ENGINE_BOOTSTRAP"] = engine_secret
    process = subprocess.Popen(
        [
            sys.executable, str(ROOT / "scripts" / "twinpulse_backend.py"),
            "--ready-file", str(ready_file),
            "--static-root", str(ROOT / "apps" / "twinpulse-web" / "dist"),
            "--settings-path", str(directory / "provider-settings.json"),
            "--fixture-mode",
        ],
        cwd=str(ROOT), env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = process.stdout.read() if process.stdout else ""
            raise RuntimeError(f"Backend exited before ready: {output[-1000:]}")
        if ready_file.is_file():
            return process, json.loads(ready_file.read_text(encoding="utf-8")), product_secret, engine_secret
        time.sleep(0.05)
    process.terminate()
    raise RuntimeError("Backend did not publish its ready file")


def _stop(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5.0)


def _distance(first: tuple[float, float, float], second: tuple[float, float, float]) -> float:
    return math.hypot(second[0] - first[0], second[1] - first[1])


backend: subprocess.Popen[str] | None = None
browser: subprocess.Popen[str] | None = None
try:
    import omni.kit.app
    import omni.usd

    artifact_root = Path(os.environ.get("TWINPULSE_ARTIFACT_DIR", STATE.name)).resolve()
    screenshot_dir = artifact_root / "r5-browser"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    image = artifact_root / "r5-input-drawing.png"
    result_file = artifact_root / "r5-browser-result.json"
    _png(image)

    context = omni.usd.get_context()
    context.new_stage()
    for _ in range(5):
        APP.update()

    backend, ready, product_secret, engine_secret = _start_backend(Path(STATE.name))
    os.environ["TWINPULSE_BRIDGE_URL"] = str(ready["base_url"])
    os.environ["TWINPULSE_ENGINE_BOOTSTRAP"] = engine_secret
    manager = omni.kit.app.get_app().get_extension_manager()
    manager.add_path(str(ROOT / "extensions"))
    manager.set_extension_enabled_immediate("twinpulse.extension", True)
    for _ in range(8):
        APP.update()
        time.sleep(0.01)

    import twinpulse.extension as extension_module

    extension = extension_module.get_extension()
    if extension is None or extension._bridge_client is None or not extension._managed_mode:
        raise AssertionError("Managed Extension did not start")
    bridge = extension._bridge_client
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline and not bridge.connected:
        APP.update()
        time.sleep(0.02)
    if not bridge.connected:
        raise TimeoutError("Isaac bridge did not connect")

    node = shutil.which("node")
    if not node:
        raise RuntimeError("Node.js executable was not found")
    environment = os.environ.copy()
    environment.update({
        "TWINPULSE_R5_URL": str(ready["base_url"]),
        "TWINPULSE_PRODUCT_BOOTSTRAP": product_secret,
        "TWINPULSE_CHROME": str(_chrome()),
        "TWINPULSE_R5_IMAGE": str(image),
        "TWINPULSE_R5_BROWSER_RESULT": str(result_file),
        "TWINPULSE_R5_SCREENSHOT_DIR": str(screenshot_dir),
    })
    browser = subprocess.Popen(
        [node, str(ROOT / "apps" / "twinpulse-web" / "e2e" / "r5-browser.mjs")],
        cwd=str(ROOT / "apps" / "twinpulse-web"), env=environment,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        encoding="utf-8", errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )

    start: tuple[float, float, float] | None = None
    max_movement = 0.0
    observed_states: set[str] = set()
    deadline = time.monotonic() + 90.0
    while browser.poll() is None and time.monotonic() < deadline:
        APP.update()
        state = extension.runtime.state
        observed_states.add(state)
        if state == "running":
            position = extension.runtime.robot_position()
            if start is None:
                start = position
            max_movement = max(max_movement, _distance(start, position))
        time.sleep(0.01)
    if browser.poll() is None:
        browser.kill()
        browser.wait(timeout=5.0)
        raise TimeoutError("R5 browser acceptance exceeded 90 seconds")
    browser_output = browser.stdout.read() if browser.stdout else ""
    if not result_file.is_file():
        raise RuntimeError(f"Browser did not write a result: {browser_output[-1500:]}")
    browser_result = json.loads(result_file.read_text(encoding="utf-8"))
    RESULT["browser"] = browser_result
    if browser.returncode != 0 or browser_result.get("status") != "PASS":
        raise AssertionError(f"Browser acceptance failed: {browser_result}; output={browser_output[-1200:]}")

    for _ in range(10):
        APP.update()
        time.sleep(0.01)
    snapshot = bridge.adapter.snapshot()
    actual = {
        "applied_revision_matches": snapshot.applied_revision == ready["revision"],
        "prim_count": extension.runtime.compiler.owned_prim_count(),
        "max_movement_m": max_movement,
        "observed_states": sorted(observed_states),
        "final_runtime_state": snapshot.runtime_state,
        "passed": bool(
            snapshot.applied_revision == ready["revision"]
            and extension.runtime.compiler.owned_prim_count() > 0
            and max_movement > 0.02
            and "running" in observed_states
            and "paused" in observed_states
        ),
    }
    RESULT["actual_isaac"] = actual
    if not actual["passed"]:
        raise AssertionError(f"Actual Isaac acceptance failed: {actual}")
    RESULT["status"] = "PASS"
except Exception as error:
    RESULT["error"] = f"{type(error).__name__}: {error}"
    RESULT["traceback"] = traceback.format_exc()
finally:
    if browser is not None and browser.poll() is None:
        browser.kill()
        browser.wait(timeout=5.0)
    try:
        if "manager" in locals():
            extension = None
            manager.set_extension_enabled_immediate("twinpulse.extension", False)
            for _ in range(8):
                APP.update()
    except Exception:
        pass
    _stop(backend)
    os.environ.pop("TWINPULSE_BRIDGE_URL", None)
    os.environ.pop("TWINPULSE_ENGINE_BOOTSTRAP", None)
    print("TWINPULSE_R5_RESULT=" + json.dumps(RESULT, ensure_ascii=False, sort_keys=True), flush=True)
    APP.close()
    STATE.cleanup()

raise SystemExit(0 if RESULT["status"] == "PASS" else 1)
