# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Isolated saved-project switch rehearsal with the installed local Isaac engine.

Uses the real backend/engine lifecycle and authenticated product API. No browser,
provider call, robot connection, sensor, motor, or physical authority is used.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
for source in (
    ROOT / "packages" / "twinpulse_core" / "src",
    ROOT / "packages" / "twinpulse_provider" / "src",
    ROOT / "packages" / "twinpulse_app" / "src",
):
    sys.path.insert(0, str(source))

from twinpulse_app import TwinPulseProcessManager  # noqa: E402
from twinpulse_app.process_manager import PROJECT_SWITCH_REQUESTED  # noqa: E402


def _request(base: str, path: str, *, body: dict | None = None,
             cookie: str | None = None, csrf: str | None = None) -> tuple[int, dict, str | None]:
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if cookie is not None:
        headers["Cookie"] = cookie
    if csrf is not None:
        headers["X-TwinPulse-CSRF"] = csrf
    request = Request(base + path, data=json.dumps(body).encode("utf-8") if body is not None else None,
                      headers=headers)
    with urlopen(request, timeout=10) as response:
        value = json.loads(response.read().decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("product response was not an object")
        return response.status, value, response.headers.get("Set-Cookie")


def _session(manager: TwinPulseProcessManager) -> tuple[str, str, str]:
    base, ticket = manager.product_bootstrap()
    status, value, set_cookie = _request(base, "/v1/bootstrap", body={"role": "product", "secret": ticket})
    if status != 200 or not set_cookie or not isinstance(value.get("csrf_token"), str):
        raise RuntimeError("product authentication failed")
    return base, set_cookie.split(";", 1)[0], value["csrf_token"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--isaac-root", type=Path, default=Path(r"C:\isaacsim"))
    parser.add_argument("--browser", action="store_true",
                        help="Exercise the actual project create/open/reopen UI with installed Chrome")
    parser.add_argument("--inject-create-failure", action="store_true",
                        help="In an isolated browser run, fail first create via a temporary local project lock")
    args = parser.parse_args()
    if args.inject_create_failure and not args.browser:
        parser.error("--inject-create-failure requires --browser")
    artifact = args.artifact_dir.resolve()
    artifact.mkdir(parents=True, exist_ok=False)
    state = artifact / "runtime"
    outcome: dict[str, object] = {"status": "FAIL", "kind": "actual_local_isaac_project_switch",
                                  "provider": "NOT_RUN", "robot": "NOT_RUN", "browser": "NOT_RUN"}
    active: TwinPulseProcessManager | None = None
    original_project_bytes: bytes | None = None
    node = shutil.which("node") if args.browser else None
    chrome = Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Google/Chrome/Application/chrome.exe"
    try:
        if args.browser and (node is None or not chrome.is_file()):
            raise RuntimeError("Existing Node and Chrome are required for browser rehearsal")
        for project_id in ("default", "room_two"):
            active = TwinPulseProcessManager(
                repo_root=ROOT, state_dir=state, python_executable=Path(sys.executable),
                isaac_python=args.isaac_root / "python.bat", browser_executable=None,
                headless=True, fixture_mode=True, ready_timeout_s=180.0, project_id=project_id,
            )
            launch = active.start(open_browser=False)
            base, cookie, csrf = _session(active)
            status, product_state, _ = _request(base, "/v1/product/state", cookie=cookie)
            if status != 200 or product_state.get("project_id") != project_id:
                raise RuntimeError("backend project identity mismatch")
            status, projects, _ = _request(base, "/v1/product/projects", cookie=cookie)
            if status != 200 or projects.get("active_project_id") != project_id:
                raise RuntimeError("catalog project identity mismatch")
            if args.browser:
                lock_file = None
                if args.inject_create_failure and project_id == "default":
                    locks = state / "project-transactions" / "locks"
                    locks.mkdir(parents=True, exist_ok=True)
                    lock_file = locks / "room_two.lock"
                    lock_file.write_text("isolated browser retry fixture", encoding="utf-8")
                browser_base, browser_ticket = active.product_bootstrap()
                if browser_base != base:
                    raise RuntimeError("browser bootstrap target changed")
                environment = dict(os.environ, TWINPULSE_REHEARSAL_URL=base,
                                   TWINPULSE_REHEARSAL_BOOTSTRAP=browser_ticket,
                                   TWINPULSE_REHEARSAL_OUTPUT=str(artifact),
                                   TWINPULSE_REHEARSAL_CHROME=str(chrome),
                                   TWINPULSE_SWITCH_PHASE="create_switch" if project_id == "default" else "reopen",
                                   TWINPULSE_SWITCH_INJECT_CREATE_FAILURE="1" if lock_file else "0")
                phase = environment["TWINPULSE_SWITCH_PHASE"]
                command = [node, str(ROOT / "apps/twinpulse-web/e2e/project-switch-isaac-real.mjs")]
                if lock_file is None:
                    return_code = subprocess.run(
                        command, cwd=ROOT / "apps/twinpulse-web", env=environment,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=65,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                    ).returncode
                else:
                    child = subprocess.Popen(
                        command, cwd=ROOT / "apps/twinpulse-web", env=environment,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                    )
                    released = False
                    try:
                        deadline = time.monotonic() + 65
                        while child.poll() is None and time.monotonic() < deadline:
                            if not released and (artifact / "release-create-lock-request").exists():
                                lock_file.unlink()
                                (artifact / "create-lock-released").write_text("1", encoding="utf-8")
                                released = True
                            time.sleep(0.05)
                        if child.poll() is None:
                            raise TimeoutError("owned browser project retry exceeded deadline")
                        return_code = child.returncode
                        if not released:
                            browser_path = artifact / "browser-create_switch.json"
                            browser_error = (json.loads(browser_path.read_text(encoding="utf-8")).get("error")
                                             if browser_path.exists() else "browser result unavailable")
                            raise RuntimeError(f"browser did not reach injected first-create failure: {browser_error}")
                    finally:
                        if child.poll() is None:
                            child.terminate()
                            child.wait(timeout=10)
                        if lock_file.exists():
                            lock_file.unlink()
                browser_result = json.loads((artifact / f"browser-{phase}.json").read_text(encoding="utf-8"))
                if return_code != 0 or browser_result.get("status") != "PASS":
                    raise RuntimeError(f"browser {phase} failed: {browser_result.get('error', 'unknown')}")
                outcome.setdefault("browser_checks", []).append(browser_result)
                if lock_file is not None:
                    outcome["create_failure_fixture"] = "transient_isolated_project_lock"
            if project_id == "default":
                old_path = state / "active_project.json"
                original_project_bytes = old_path.read_bytes() if old_path.is_file() else None
                if not args.browser:
                    status, created, _ = _request(base, "/v1/product/projects/create",
                                                  body={"project_id": "room_two"}, cookie=cookie, csrf=csrf)
                    if status != 201 or created.get("created_project_id") != "room_two":
                        raise RuntimeError("saved project creation failed")
                    status, switched, _ = _request(base, "/v1/product/projects/switch",
                                                   body={"project_id": "room_two"}, cookie=cookie, csrf=csrf)
                    if status != 202 or switched.get("status") != "requested":
                        raise RuntimeError("project switch request failed")
                if active.monitor(poll_s=0.1) != PROJECT_SWITCH_REQUESTED:
                    raise RuntimeError("owned launcher did not accept the project switch")
                if active.requested_project_id != "room_two":
                    raise RuntimeError("launcher selected a different project")
                outcome["first_launch_id"] = launch.launch_id
                active.stop()
                active = None
            else:
                if launch.launch_id == outcome.get("first_launch_id"):
                    raise RuntimeError("project switch reused the old launch")
                old_path = state / "active_project.json"
                if ((old_path.read_bytes() if old_path.is_file() else None) != original_project_bytes):
                    raise RuntimeError("old project state changed during switching")
                status, workflow, _ = _request(base, "/v1/product/workflow", cookie=cookie)
                if status != 200 or workflow.get("build_allowed") is not False:
                    raise RuntimeError("new project restored an old Build approval")
                if args.browser and workflow.get("phase") != "draft_ready":
                    raise RuntimeError("browser did not explicitly continue the saved room review")
                outcome.update(status="PASS", old_project="default", new_project="room_two",
                               launch_identity_changed=True, new_engine_ready=True,
                               saved_project_reopened=True, old_project_preserved=True,
                               build_approval_restored=False, physical_validation="NOT_RUN",
                               browser="PASS" if args.browser else "NOT_RUN")
    except Exception as error:
        outcome["failure_type"] = type(error).__name__
        outcome["failure"] = str(error)[:240]
    finally:
        if active is not None:
            active.stop()
        (artifact / "result.json").write_text(json.dumps(outcome, indent=2, sort_keys=True), encoding="utf-8")
    print(f"PROJECT_SWITCH_ISAAC={outcome['status']} artifact={artifact}", flush=True)
    return 0 if outcome["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
