"""R6 launcher ownership, allowlist, readiness, and finite failure tests."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import uuid


ROOT = Path(__file__).resolve().parents[2]
for source in (
    ROOT / "packages" / "twinpulse_core" / "src",
    ROOT / "packages" / "twinpulse_provider" / "src",
    ROOT / "packages" / "twinpulse_app" / "src",
):
    sys.path.insert(0, str(source))

from twinpulse_app import ProcessManagerError, TwinPulseProcessManager  # noqa: E402


class FakeProcess:
    def __init__(self, pid: int, code: int | None = None) -> None:
        self.pid = pid
        self.code = code
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        return self.code

    def wait(self, timeout: float | None = None) -> int:
        if self.code is None:
            raise __import__("subprocess").TimeoutExpired("fake", timeout)
        return self.code

    def terminate(self) -> None:
        self.terminated = True
        self.code = 0

    def kill(self) -> None:
        self.killed = True
        self.code = -9


class R6ProcessManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        configured = os.environ.get("TWINPULSE_TEST_TMP")
        if configured:
            root = Path(configured) / f"r6-{uuid.uuid4().hex}"
            root.mkdir(parents=True)
            self.temporary = None
        else:
            self.temporary = tempfile.TemporaryDirectory()
            root = Path(self.temporary.name)
        for relative in (
            "python.exe", "isaac/python.bat", "scripts/twinpulse_backend.py",
            "scripts/twinpulse_engine_host.py", "apps/twinpulse-web/dist/index.html",
            "extensions/twinpulse.extension/config/extension.toml",
        ):
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("fixture", encoding="utf-8")
        self.root = root
        self.state = root / "state"

    def tearDown(self) -> None:
        if self.temporary is not None:
            self.temporary.cleanup()
        else:
            shutil.rmtree(self.root, ignore_errors=True)

    def manager(self, **overrides: object) -> TwinPulseProcessManager:
        values = {
            "repo_root": self.root,
            "state_dir": self.state,
            "python_executable": self.root / "python.exe",
            "isaac_python": self.root / "isaac/python.bat",
        }
        values.update(overrides)
        return TwinPulseProcessManager(**values)  # type: ignore[arg-type]

    def test_validation_rejects_unapproved_browser_and_bad_port(self) -> None:
        browser = self.root / "powershell.exe"
        browser.write_text("fixture", encoding="utf-8")
        with self.assertRaisesRegex(ProcessManagerError, "Only Chrome or Edge"):
            self.manager(browser_executable=browser).validate()
        with self.assertRaisesRegex(ProcessManagerError, "0..65535"):
            self.manager(port=70_000).validate()

    def test_product_launcher_defaults_to_live_and_fixture_is_explicit(self) -> None:
        self.assertNotIn("--fixture-mode", self.manager()._backend_command())
        self.assertIn("--fixture-mode", self.manager(fixture_mode=True)._backend_command())

    def test_ready_requires_authenticated_capabilities_stage_and_permission(self) -> None:
        pid_only = {"engine_connected": True, "pid": 7}
        self.assertFalse(TwinPulseProcessManager._engine_ready(pid_only))
        ready = {
            "engine_connected": True, "stage_epoch": "stage-1",
            "snapshot": {
                "stage_epoch": "stage-1", "runtime_state": "idle",
                "capabilities": ["simulation", "build", "telemetry", "watchdog"],
                "permitted_commands": ["get_state", "focus_scene"],
            },
        }
        self.assertTrue(TwinPulseProcessManager._engine_ready(ready))
        ready["snapshot"]["capabilities"].remove("watchdog")
        self.assertFalse(TwinPulseProcessManager._engine_ready(ready))

    def test_duplicate_launcher_lock_never_terminates_existing_process(self) -> None:
        self.state.mkdir()
        owner_lock = json.dumps({
            "schema_version": "1.0", "launch_id": "existing-owner",
            "owner_pid": os.getpid(), "pid": os.getpid(),
            "started_at_utc": "2026-09-22T00:00:00+00:00",
        }).encode("utf-8")
        preserved = {
            "launcher.lock": owner_lock,
            "backend-ready.json": b'{"owner":"ready"}',
            "engine-status.json": b'{"owner":"engine"}',
            "supervisor-status.json": b'{"owner":"supervisor"}',
        }
        for name, content in preserved.items():
            (self.state / name).write_bytes(content)

        rejected = self.manager()
        with self.assertRaisesRegex(ProcessManagerError, "no process was terminated"):
            rejected._acquire_lock()
        rejected.stop()
        rejected.stop()

        for name, content in preserved.items():
            self.assertEqual((self.state / name).read_bytes(), content)
        self.assertFalse(rejected.engine_stop_file.exists())

    def test_unreadable_or_partial_live_lock_is_never_deleted_as_stale(self) -> None:
        self.state.mkdir()
        lock = self.state / "launcher.lock"
        lock.write_bytes(b'{"owner_pid":')
        manager = self.manager()
        with self.assertRaises(ProcessManagerError) as raised:
            manager._acquire_lock()
        self.assertEqual(raised.exception.code, "launcher_lock_unreadable")
        self.assertEqual(lock.read_bytes(), b'{"owner_pid":')

    def test_owned_runtime_status_and_stop_request_are_instance_bound(self) -> None:
        manager = self.manager()
        manager._acquire_lock()
        manager._write_status("starting", "test", "fixture")
        status = json.loads(manager.supervisor_status_file.read_text(encoding="utf-8"))
        lock = json.loads(manager.lock_file.read_text(encoding="utf-8"))

        self.assertEqual(status["launch"]["instance_id"], manager._launch_id)
        self.assertEqual(status["launch"]["owner_pid"], os.getpid())
        self.assertEqual(lock["launch_id"], manager._launch_id)
        self.assertEqual(lock["owner_pid"], os.getpid())
        self.assertIn(manager._launch_id, str(manager.engine_stop_file))

        engine = FakeProcess(101)
        manager._owned = {"engine": engine}  # type: ignore[assignment]
        manager.stop()
        stop_request = json.loads(manager.engine_stop_file.read_text(encoding="utf-8"))
        self.assertEqual(stop_request["launch_id"], manager._launch_id)
        self.assertEqual(stop_request["owner_pid"], os.getpid())

        manager.engine_stop_file.unlink()
        stopped_status = manager.supervisor_status_file.read_bytes()
        manager.stop()
        self.assertFalse(manager.engine_stop_file.exists())
        self.assertEqual(manager.supervisor_status_file.read_bytes(), stopped_status)

    def test_stop_touches_only_processes_registered_as_owned(self) -> None:
        manager = self.manager()
        manager._acquire_lock()
        engine = FakeProcess(101)
        backend = FakeProcess(102)
        unrelated = FakeProcess(999)
        manager._owned = {"engine": engine, "backend": backend}  # type: ignore[assignment]
        manager.stop()
        self.assertTrue(engine.terminated)
        self.assertTrue(backend.terminated)
        self.assertFalse(unrelated.terminated)
        self.assertFalse(unrelated.killed)

    def test_backend_spawn_failure_is_classified_and_cleans_only_owned_state(self) -> None:
        def fail_spawn(*_args: object, **_kwargs: object) -> FakeProcess:
            raise OSError("fixture spawn denied")

        manager = self.manager(popen_factory=fail_spawn)
        with self.assertRaises(ProcessManagerError) as raised:
            manager.start(open_browser=False)
        self.assertEqual(raised.exception.code, "backend_spawn_failed")
        self.assertFalse(manager.lock_file.exists())
        self.assertFalse(manager.engine_stop_file.exists())
        status = json.loads(manager.supervisor_status_file.read_text(encoding="utf-8"))
        self.assertEqual(status["phase"], "backend_spawn_failed")

    def test_engine_spawn_failure_cleans_the_owned_backend_without_stop_signal(self) -> None:
        backend = FakeProcess(201)
        manager = self.manager()
        calls = 0

        def spawn(*_args: object, **_kwargs: object) -> FakeProcess:
            nonlocal calls
            calls += 1
            if calls == 1:
                manager.ready_file.write_text(
                    json.dumps({"base_url": "http://127.0.0.1:43123"}), encoding="utf-8",
                )
                return backend
            raise OSError("fixture engine spawn denied")

        manager._popen = spawn  # type: ignore[assignment]
        with self.assertRaises(ProcessManagerError) as raised:
            manager.start(open_browser=False)

        self.assertEqual(raised.exception.code, "engine_spawn_failed")
        self.assertTrue(backend.terminated)
        self.assertFalse(manager.lock_file.exists())
        self.assertFalse(manager.engine_stop_file.exists())
        status = json.loads(manager.supervisor_status_file.read_text(encoding="utf-8"))
        self.assertEqual(status["phase"], "engine_spawn_failed")

    def test_validation_failure_and_finally_stop_do_not_create_runtime_state(self) -> None:
        manager = self.manager(port=70_000)
        with self.assertRaises(ProcessManagerError) as raised:
            manager.start(open_browser=False)
        self.assertEqual(raised.exception.code, "port_invalid")
        manager.stop()
        manager.stop()
        self.assertFalse(self.state.exists())

    def test_terminal_failure_survives_owned_cleanup(self) -> None:
        manager = self.manager()
        self.state.mkdir()
        manager._lock_owned = True
        manager._terminal_error = ("engine_exited", "engine exited with code 7")
        manager.stop(final_status="error")
        status = json.loads(manager.supervisor_status_file.read_text(encoding="utf-8"))
        self.assertEqual(status["status"], "error")
        self.assertEqual(status["phase"], "engine_exited")
        self.assertIn("code 7", status["message"])


if __name__ == "__main__":
    unittest.main()
