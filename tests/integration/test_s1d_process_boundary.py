# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""S1d process-tree ownership, state isolation, and stale-heartbeat tests."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
import uuid
import shutil
from contextlib import contextmanager
from collections.abc import Iterator


ROOT = Path(__file__).resolve().parents[2]
for source in (
    ROOT / "packages" / "twinpulse_core" / "src",
    ROOT / "packages" / "twinpulse_provider" / "src",
    ROOT / "packages" / "twinpulse_app" / "src",
):
    sys.path.insert(0, str(source))

from twinpulse_app import TwinPulseProcessManager  # noqa: E402


TEST_TEMP_ROOT = ROOT / "artifacts" / "test-tmp"
TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)


@contextmanager
def _isolated_directory() -> Iterator[Path]:
    path = TEST_TEMP_ROOT / f"s1d-{uuid.uuid4().hex}"
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


class _AliveProcess:
    pid = 9876

    def poll(self) -> None:
        return None


def _process_alive(pid: int) -> bool:
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("Kernel32.dll", use_last_error=True)
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    try:
        exit_code = wintypes.DWORD()
        return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))) and exit_code.value == 259
    finally:
        kernel32.CloseHandle(handle)


@unittest.skipUnless(os.name == "nt", "Windows Job Object acceptance")
class S1dWindowsProcessBoundaryTests(unittest.TestCase):
    def test_owned_wrapper_shutdown_reaps_descendant(self) -> None:
        with _isolated_directory() as root:
            child_pid_file = root / "child.pid"
            release_file = root / "release"
            wrapper = root / "wrapper.py"
            wrapper.write_text(
                """from pathlib import Path
import subprocess, sys, time
pid_file, release_file = map(Path, sys.argv[1:])
while not release_file.exists():
    time.sleep(0.01)
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])
pid_file.write_text(str(child.pid), encoding='utf-8')
while True:
    time.sleep(1)
""",
                encoding="utf-8",
            )
            manager = TwinPulseProcessManager(
                repo_root=ROOT,
                state_dir=root / "state",
                python_executable=Path(sys.executable),
                isaac_python=Path(sys.executable),
            )
            manager.launch_dir.mkdir(parents=True)
            child_pid: int | None = None
            try:
                manager._spawn(
                    "wrapper",
                    [sys.executable, str(wrapper), str(child_pid_file), str(release_file)],
                    os.environ,
                    hidden=True,
                )
                release_file.touch()
                deadline = time.monotonic() + 10.0
                while time.monotonic() < deadline and not child_pid_file.is_file():
                    time.sleep(0.02)
                self.assertTrue(child_pid_file.is_file(), "wrapper did not publish child PID")
                child_pid = int(child_pid_file.read_text(encoding="utf-8"))
                self.assertTrue(_process_alive(child_pid))
                self.assertGreaterEqual(manager._jobs["wrapper"].active_process_count(), 2)

                manager._stop_owned("wrapper", graceful_s=0.05)
                deadline = time.monotonic() + 5.0
                while time.monotonic() < deadline and _process_alive(child_pid):
                    time.sleep(0.05)
                self.assertFalse(_process_alive(child_pid), "owned descendant survived wrapper shutdown")
            finally:
                manager._stop_owned("wrapper", graceful_s=0.0)
                manager.stop()
                if child_pid is not None and _process_alive(child_pid):
                    subprocess.run(
                        ["taskkill", "/PID", str(child_pid), "/T", "/F"],
                        check=False,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )


class S1dStateAndHealthTests(unittest.TestCase):
    def manager(self, state: Path, **overrides: object) -> TwinPulseProcessManager:
        values: dict[str, object] = {
            "repo_root": ROOT,
            "state_dir": state,
            "python_executable": Path(sys.executable),
            "isaac_python": Path(sys.executable),
            "credential_target": f"TwinPulse/Test/{uuid.uuid4().hex}",
        }
        values.update(overrides)
        return TwinPulseProcessManager(**values)  # type: ignore[arg-type]

    def test_each_launch_has_isolated_runtime_but_persistent_explicit_settings(self) -> None:
        with _isolated_directory() as temporary:
            state = temporary / "state"
            first = self.manager(state, credential_target="TwinPulse/Test/isolated")
            second = self.manager(state, credential_target="TwinPulse/Test/isolated")

            self.assertNotEqual(first.launch_dir, second.launch_dir)
            self.assertEqual(first.provider_settings_file, state.resolve() / "provider_settings.json")
            self.assertEqual(first.provider_settings_file, second.provider_settings_file)
            self.assertEqual(first.credential_target, "TwinPulse/Test/isolated")
            self.assertTrue(str(first.ready_file).startswith(str(first.launch_dir)))
            self.assertTrue(str(first.engine_state_dir).startswith(str(first.launch_dir)))
            command = first._backend_command()
            self.assertEqual(command[command.index("--settings-path") + 1], str(first.provider_settings_file))
            self.assertEqual(command[command.index("--credential-target") + 1], first.credential_target)

    def test_alive_pid_with_stale_engine_heartbeat_is_unresponsive_and_reports_safe_tail(self) -> None:
        with _isolated_directory() as temporary:
            manager = self.manager(temporary / "state")
            manager.launch_dir.mkdir(parents=True)
            manager.engine_status_file.write_text(
                json.dumps({
                    "schema_version": "1.0",
                    "sampled_at_utc": "2026-09-23T00:00:00+00:00",
                    "engine_connected": False,
                    "engine_session_id": "engine-test",
                    "stage_epoch": "stage-test",
                    "snapshot": {"permitted_commands": []},
                }),
                encoding="utf-8",
            )
            manager.engine_log_file.write_text(
                "Traceback: engine heartbeat stopped\nAuthorization: Bearer never-print-this\n",
                encoding="utf-8",
            )
            manager._owned = {"backend": _AliveProcess(), "engine": _AliveProcess()}  # type: ignore[assignment]

            self.assertEqual(manager.monitor(poll_s=0.0), 1)
            status = json.loads(manager.supervisor_status_file.read_text(encoding="utf-8"))
            self.assertEqual(status["status"], "error")
            self.assertEqual(status["phase"], "engine_unresponsive")
            self.assertIn("redacted", status["message"])
            self.assertNotIn("never-print-this", status["message"])


if __name__ == "__main__":
    unittest.main()
