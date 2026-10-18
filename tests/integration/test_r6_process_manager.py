# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""R6 launcher ownership, allowlist, readiness, and finite failure tests."""

from __future__ import annotations

import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch


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
    def test_explicit_diagnostic_exit_is_success_without_second_alert(self):
        main = runpy.run_path(str(ROOT / 'scripts/twinpulse_launcher.py'))['main']
        events = []
        class FailedManager:
            diagnostics_active = True
            def start(self, **kwargs):
                raise ProcessManagerError('isaac_missing', 'fixture')
            def monitor_diagnostics(self):
                events.append('explicit_exit')
                return 0
            def stop(self):
                events.append('stopped')
        with patch.dict(main.__globals__, {'TwinPulseProcessManager': lambda **kwargs: FailedManager(),
                                           '_browser': lambda value: None}), \
                patch.object(sys, 'argv', ['twinpulse_launcher.py', '--no-browser']):
            self.assertEqual(main(), 0)
        self.assertEqual(events, ['explicit_exit', 'stopped'])

    def test_launcher_switch_stops_old_manager_before_new_project(self) -> None:
        module = runpy.run_path(str(ROOT / "scripts" / "twinpulse_launcher.py"))
        main = module["main"]
        events: list[str] = []

        class SwitchingManager:
            requested_project_id = "room_two"
            def monitor(self):
                events.append("switch_requested")
                from twinpulse_app.process_manager import PROJECT_SWITCH_REQUESTED
                return PROJECT_SWITCH_REQUESTED
            def start(self, *, open_browser: bool):
                events.append("old_start")
                from types import SimpleNamespace
                return SimpleNamespace(launch_id="old", ui_url="http://127.0.0.1:1/",
                    backend_pid=10, engine_pid=11, stage_epoch="stage")
            def stop(self):
                events.append("old_stopped")

        class NewManager:
            requested_project_id = None
            def start(self, *, open_browser: bool):
                events.append("new_start")
                from types import SimpleNamespace
                return SimpleNamespace(launch_id="new", ui_url="http://127.0.0.1:2/",
                    backend_pid=12, engine_pid=13, stage_epoch="stage2")
            def monitor(self):
                events.append("new_monitor")
                return 0
            def stop(self):
                events.append("new_stopped")

        managers = iter((SwitchingManager(), NewManager()))
        def factory(**kwargs):
            events.append("project=" + kwargs["project_id"])
            return next(managers)
        with patch.dict(main.__globals__, {"TwinPulseProcessManager": factory,
                                           "_browser": lambda _configured: None}), \
                patch.object(sys, "argv", ["twinpulse_launcher.py", "--no-browser"]):
            self.assertEqual(main(), 0)
        self.assertEqual(events, ["project=default", "old_start", "switch_requested", "old_stopped",
                                  "project=room_two", "new_start", "new_monitor", "new_stopped"])

    def test_launcher_retry_stops_old_manager_before_fresh_session(self) -> None:
        module = runpy.run_path(str(ROOT / "scripts" / "twinpulse_launcher.py"))
        main = module["main"]
        events: list[str] = []

        class FailedManager:
            diagnostics_active = True

            def start(self, *, open_browser: bool):
                events.append("failed_start")
                raise ProcessManagerError("engine_start_failed", "fixture")

            def monitor_diagnostics(self):
                events.append("retry_requested")
                from twinpulse_app.process_manager import RESTART_REQUESTED
                return RESTART_REQUESTED

            def stop(self):
                events.append("failed_stopped")

        class ReadyManager:
            diagnostics_active = False

            def start(self, *, open_browser: bool):
                events.append("fresh_start")
                self.assert_open_browser = open_browser
                from types import SimpleNamespace
                return SimpleNamespace(launch_id="fresh", ui_url="http://127.0.0.1:1/",
                    backend_pid=10, engine_pid=11, stage_epoch="stage")

            def monitor(self):
                events.append("fresh_monitor")
                return 0

            def stop(self):
                events.append("fresh_stopped")

        managers = iter((FailedManager(), ReadyManager()))
        with patch.dict(main.__globals__, {"TwinPulseProcessManager": lambda **_kwargs: next(managers),
                                           "_browser": lambda _configured: None}), \
                patch.object(sys, "argv", ["twinpulse_launcher.py", "--no-browser"]):
            self.assertEqual(main(), 0)
        self.assertEqual(events, ["failed_start", "retry_requested", "failed_stopped",
                                  "fresh_start", "fresh_monitor", "fresh_stopped"])

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

    def test_owned_bootstrap_lifetime_covers_bounded_startup(self) -> None:
        for timeout,expected in ((120,180),(300,360),(600,660),(.5,180)):
            manager=self.manager(ready_timeout_s=timeout)
            command=manager._backend_command()
            self.assertEqual(command[command.index('--bootstrap-ttl-s')+1],str(expected))
            self.assertEqual(manager.ready_timeout_s,timeout)
        for invalid in (0,-1,float('nan'),float('inf'),601):
            with self.assertRaisesRegex(ProcessManagerError,'finite'):
                self.manager(ready_timeout_s=invalid)

    def test_named_project_is_passed_to_backend_without_changing_default(self) -> None:
        named = self.manager(project_id="room_two")
        command = named._backend_command()
        self.assertEqual(command[command.index("--project-id") + 1], "room_two")
        self.assertEqual(self.manager().project_id, "default")
        with self.assertRaises(ValueError):
            self.manager(project_id="../outside")

    def test_validation_rejects_unapproved_browser_and_bad_port(self) -> None:
        browser = self.root / "powershell.exe"
        browser.write_text("fixture", encoding="utf-8")
        with self.assertRaisesRegex(ProcessManagerError, "Only Chrome or Edge"):
            self.manager(browser_executable=browser).validate()
        with self.assertRaisesRegex(ProcessManagerError, "0..65535"):
            self.manager(port=70_000).validate()

    def test_derived_directory_failure_releases_lock_without_spawn_or_deletion(self) -> None:
        manager=self.manager(popen_factory=lambda *a,**k:self.fail('must not spawn'))
        with patch('twinpulse_app.startup_checks.prepare_owned_directories',return_value=[
            {'id':'owned_launch_directory','state':'failed','attempts':1}]):
            with self.assertRaisesRegex(ProcessManagerError,'Fresh owned runtime directory'):
                manager.start(open_browser=False)
        self.assertFalse(manager.lock_file.exists())
        self.assertFalse(manager._owned)

    def test_product_launcher_defaults_to_live_and_fixture_is_explicit(self) -> None:
        self.assertNotIn("--fixture-mode", self.manager()._backend_command())
        self.assertIn("--fixture-mode", self.manager(fixture_mode=True)._backend_command())
        self.assertNotIn("--offline", self.manager()._backend_command())
        self.assertIn("--offline", self.manager(offline_mode=True)._backend_command())
        with self.assertRaises(ValueError):
            self.manager(offline_mode=True, fixture_mode=True)

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

    def test_duplicate_start_reopens_through_owner_without_new_children_or_cleanup(self) -> None:
        owner = self.manager(); owner._acquire_lock()
        owner._owned = {'backend': FakeProcess(901), 'engine': FakeProcess(902)}
        owner._write_status('ready', 'ready', 'fixture')
        owner.ready_file.write_text(json.dumps({'base_url': 'http://127.0.0.1:43123'}))
        opened = []
        owner.open_browser = opened.append
        child = self.manager()
        child._sleep = lambda _seconds: owner._handle_open_requests()
        result = child.start(open_browser=True)
        self.assertTrue(result.reused); self.assertEqual(result.launch_id, owner._launch_id)
        self.assertEqual(opened, ['http://127.0.0.1:43123/'])
        child.stop()
        self.assertFalse(child._owned); self.assertFalse(child._lock_owned)
        self.assertEqual(json.loads(owner.lock_file.read_text())['launch_id'], owner._launch_id)
        self.assertFalse(owner._owned['engine'].terminated)
        self.assertFalse(list(owner.launcher_open_dir.glob('*.json')))
        owner._release_lock()

    def test_reopen_starting_owner_preserves_starting_phase_and_uses_no_cookie_file(self) -> None:
        owner = self.manager(); owner._acquire_lock()
        owner._owned = {'backend': FakeProcess(901)}
        owner._write_status('starting', 'backend_ready', 'fixture')
        owner.ready_file.write_text(json.dumps({'base_url': 'http://127.0.0.1:43123'}))
        owner.open_browser = lambda _url: None
        child = self.manager(); child._sleep = lambda _seconds: owner._handle_open_requests()
        result = child.start(open_browser=True)
        self.assertTrue(result.reused); self.assertEqual(result.phase, 'backend_ready')
        self.assertEqual(result.engine_pid, 0)
        self.assertEqual(json.loads(owner.supervisor_status_file.read_text())['status'], 'starting')
        child.stop(); owner._release_lock()

    def test_older_owner_cannot_be_adopted_or_terminated(self) -> None:
        self.state.mkdir()
        old = dict(schema_version='1.0', launch_id='a'*32, owner_pid=os.getpid())
        (self.state/'launcher.lock').write_text(json.dumps(old))
        child = self.manager()
        with self.assertRaises(ProcessManagerError) as error: child.start(open_browser=True)
        self.assertEqual(error.exception.code, 'launcher_reopen_unavailable')
        child.stop(); self.assertEqual(json.loads(child.lock_file.read_text()), old)

    def test_double_click_waits_for_first_owner_status_publication(self) -> None:
        owner = self.manager(); owner._acquire_lock()
        owner._owned = {'backend': FakeProcess(901), 'engine': FakeProcess(902)}
        owner.ready_file.parent.mkdir(parents=True)
        owner.ready_file.write_text(json.dumps({'base_url':'http://127.0.0.1:43123'}))
        owner.open_browser = lambda _url: None
        child = self.manager()
        def publish(_seconds):
            if not owner.supervisor_status_file.exists(): owner._write_status('starting','engine_start','fixture')
            owner._handle_open_requests()
        child._sleep=publish
        result=child.start(open_browser=True)
        self.assertTrue(result.reused); self.assertEqual(result.phase,'engine_start')
        child.stop(); owner._release_lock()

    def test_normal_engine_close_is_success_not_failed_launch(self) -> None:
        from twinpulse_core.execution_diagnostics import ExecutionStore
        owner = self.manager(); owner.launch_dir.mkdir(parents=True)
        store=ExecutionStore(self.state/'diagnostics','default')
        start=store.begin('launcher_start'); start.finish(); store.flush(); owner._launch_trace=start
        owner._owned={'backend': FakeProcess(901), 'engine': FakeProcess(902,code=0)}
        self.assertEqual(owner.monitor(poll_s=0), 0); store.flush()
        records={row['stage']:store.detail(row['execution_id']) for row in store.list()['executions']}
        self.assertEqual(records['launcher_monitor']['status'], 'succeeded')
        self.assertIsNone(owner._terminal_error)

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

    def test_engine_failure_keeps_only_the_owned_diagnostic_backend_available(self) -> None:
        backend = FakeProcess(301)
        engine = FakeProcess(302, code=7)
        manager = self.manager()
        browser_urls: list[str] = []

        def spawn(*_args: object, **_kwargs: object) -> FakeProcess:
            if not manager.ready_file.exists():
                manager.ready_file.write_text(
                    json.dumps({"base_url": "http://127.0.0.1:43123"}), encoding="utf-8",
                )
                return backend
            self.assertEqual(browser_urls, ["http://127.0.0.1:43123/"])
            return engine

        def open_browser(url: str) -> None:
            browser_urls.append(url)
            manager._write_status("starting", "backend_ready", "fixture", browser_launched=True)

        manager._popen = spawn  # type: ignore[assignment]
        manager.open_browser = open_browser  # type: ignore[method-assign]
        with self.assertRaises(ProcessManagerError) as raised:
            manager.start(open_browser=True)
        self.assertEqual(raised.exception.code, "engine_start_failed")
        self.assertTrue(manager.diagnostics_active)
        self.assertFalse(backend.terminated)
        self.assertTrue(manager.lock_file.exists())
        status = json.loads(manager.supervisor_status_file.read_text(encoding="utf-8"))
        self.assertEqual(status["status"], "error")
        self.assertTrue(status["browser"]["launched"])
        manager.launcher_retry_file.write_text('{"schema_version":"1.0","action":"retry"}', encoding="utf-8")
        from twinpulse_app.process_manager import RESTART_REQUESTED
        self.assertEqual(manager.monitor_diagnostics(poll_s=0), RESTART_REQUESTED)
        self.assertFalse(backend.terminated)
        manager.stop()
        self.assertTrue(backend.terminated)
        self.assertFalse(manager.lock_file.exists())

    def test_ready_monitor_accepts_only_valid_project_switch_request(self) -> None:
        from twinpulse_app.process_manager import PROJECT_SWITCH_REQUESTED
        manager = self.manager()
        manager.launch_dir.mkdir(parents=True)
        manager._owned = {"backend": FakeProcess(401), "engine": FakeProcess(402)}
        manager.launcher_project_switch_file.write_text(
            json.dumps({"schema_version": "1.0", "action": "switch_project", "project_id": "room_two"}),
            encoding="utf-8",
        )
        self.assertEqual(manager.monitor(poll_s=0), PROJECT_SWITCH_REQUESTED)
        self.assertEqual(manager.requested_project_id, "room_two")
        self.assertFalse(manager._owned["backend"].terminated)
        self.assertFalse(manager._owned["engine"].terminated)

    def test_engine_wait_observes_explicit_startup_cancel_before_timeout(self) -> None:
        manager = self.manager()
        manager.launch_dir.mkdir(parents=True)
        manager.launcher_cancel_file.write_text(
            json.dumps({"schema_version": "1.0", "action": "cancel_startup"}), encoding="utf-8")
        with self.assertRaises(ProcessManagerError) as raised:
            manager._wait_engine_ready(FakeProcess(501), FakeProcess(502))
        self.assertEqual(raised.exception.code, "startup_cancelled")

    def test_validation_failure_and_finally_stop_do_not_create_runtime_state(self) -> None:
        manager = self.manager(port=70_000)
        with self.assertRaises(ProcessManagerError) as raised:
            manager.start(open_browser=False)
        self.assertEqual(raised.exception.code, "port_invalid")
        manager.stop()
        manager.stop()
        self.assertFalse(self.state.exists())
        self.assertTrue(raised.exception.execution_id)
        from twinpulse_core.execution_diagnostics import ExecutionStore
        saved=ExecutionStore(self.state.parent/'launcher-diagnostics','default').detail(raised.exception.execution_id)
        self.assertEqual(saved['status'],'failed')
        self.assertEqual(saved['first_error']['error_code'],'port_invalid')

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

    def test_monitor_and_shutdown_have_separate_traces_without_rewriting_successful_launch(self) -> None:
        from twinpulse_core.execution_diagnostics import ExecutionStore
        manager=self.manager();manager.launch_dir.mkdir(parents=True)
        store=ExecutionStore(self.state/'diagnostics','default')
        start=store.begin('launcher_start',component='launcher');start.finish();store.flush()
        manager._launch_trace=start
        manager._owned={'backend':FakeProcess(801),'engine':FakeProcess(802,code=7)}
        self.assertEqual(manager.monitor(poll_s=0),1)
        manager.stop();store.flush()
        records={value['stage']:store.detail(value['execution_id']) for value in store.list()['executions']}
        self.assertEqual(records['launcher_start']['status'],'succeeded')
        self.assertEqual(records['launcher_monitor']['status'],'failed')
        self.assertEqual(records['launcher_monitor']['first_error']['error_code'],'engine_exited')
        self.assertEqual(records['launcher_shutdown']['status'],'succeeded')
        for stage in ('launcher_monitor','launcher_shutdown'):
            self.assertEqual(records[stage]['manifest']['metadata']['launch_execution_id'],start.execution_id)
        count=len(records);manager.stop();store.flush();self.assertEqual(len(store.list()['executions']),count)
        self.assertEqual(manager._terminal_error[0],'engine_exited')
        status=json.loads(manager.supervisor_status_file.read_text())
        from twinpulse_app.api import _sanitize_supervisor_status
        safe=_sanitize_supervisor_status(status)
        self.assertEqual(safe['diagnostic_execution_id'],records['launcher_monitor']['manifest']['execution_id'])

    def test_runtime_diagnostic_identifier_is_allowlisted_without_paths_or_secrets(self) -> None:
        from twinpulse_app.api import _sanitize_supervisor_status
        for invalid in ('../private/key','https://private/token','a'*31,'b'*33,None,123):
            self.assertIsNone(_sanitize_supervisor_status({'diagnostic_execution_id':invalid})['diagnostic_execution_id'])
        safe=_sanitize_supervisor_status({'diagnostic_execution_id':'a'*32,'owner_secret':'PRIVATE','diagnostics_path':'PRIVATE'})
        self.assertEqual(safe['diagnostic_execution_id'],'a'*32);self.assertNotIn('PRIVATE',json.dumps(safe))

    def test_optional_lifecycle_sink_failure_does_not_change_monitor_or_owned_shutdown(self) -> None:
        from twinpulse_core.execution_diagnostics import ExecutionStore
        manager=self.manager();manager.launch_dir.mkdir(parents=True)
        store=ExecutionStore(self.state/'diagnostics','default');start=store.begin('launcher_start');start.finish();store.flush()
        manager._launch_trace=start;manager._lock_owned=True
        manager._owned={'backend':FakeProcess(901),'engine':FakeProcess(902,code=7)}
        with patch.object(store,'begin',side_effect=OSError('PRIVATE DIAGNOSTIC PATH')):
            self.assertEqual(manager.monitor(poll_s=0),1);manager.stop()
        self.assertFalse(manager._owned);self.assertFalse(manager._lock_owned)
        self.assertEqual(manager._terminal_error[0],'engine_exited');self.assertTrue(store.health['diagnostics_degraded'])
        self.assertEqual(store.detail(start.execution_id)['status'],'succeeded')

    def test_explicit_project_switch_monitor_is_cancelled_and_never_rewrites_launch_success(self) -> None:
        from twinpulse_core.execution_diagnostics import ExecutionStore
        from twinpulse_app.process_manager import PROJECT_SWITCH_REQUESTED
        manager=self.manager();manager.launch_dir.mkdir(parents=True)
        store=ExecutionStore(self.state/'diagnostics','default');start=store.begin('launcher_start');start.finish();store.flush()
        manager._launch_trace=start;manager._owned={'backend':FakeProcess(901),'engine':FakeProcess(902)}
        manager.launcher_project_switch_file.write_text(json.dumps({'schema_version':'1.0','action':'switch_project','project_id':'room_b'}))
        self.assertEqual(manager.monitor(poll_s=0),PROJECT_SWITCH_REQUESTED);store.flush()
        value=next(row for row in store.list()['executions'] if row['stage']=='launcher_monitor')
        self.assertEqual(value['status'],'cancelled');self.assertIsNone(value['first_error'])
        self.assertEqual(manager.requested_project_id,'room_b');self.assertEqual(store.detail(start.execution_id)['status'],'succeeded')

    def test_cooperative_stop_signal_error_is_logged_as_cleanup_without_hiding_original_monitor_error(self) -> None:
        from twinpulse_core.execution_diagnostics import ExecutionStore
        import twinpulse_app.process_manager as module
        manager=self.manager();manager.launch_dir.mkdir(parents=True)
        store=ExecutionStore(self.state/'diagnostics','default');start=store.begin('launcher_start');start.finish();store.flush()
        manager._launch_trace=start;manager._lock_owned=True
        manager._owned={'backend':FakeProcess(901),'engine':FakeProcess(902)}
        manager._terminal_error=('engine_unresponsive','original heartbeat failure')
        original=module._write_json_atomic
        def write(path,value):
            if path==manager.engine_stop_file:raise OSError('PRIVATE STOP FILE PATH')
            return original(path,value)
        with patch.object(module,'_write_json_atomic',side_effect=write):manager.stop()
        store.flush();value=next(value for value in store.list()['executions'] if value['stage']=='launcher_shutdown')
        detail=store.detail(value['execution_id'])
        self.assertEqual(detail['status'],'failed')
        self.assertIsNone(detail['first_error'])  # Cleanup role is separate from primary monitor failure.
        failed=[span for span in detail['spans'] if span['status']=='failed']
        self.assertTrue(any(span['stage']=='engine_stop_signal' and span['metadata']['role']=='cleanup' for span in failed))
        self.assertNotIn('PRIVATE',json.dumps(detail));self.assertFalse(manager._owned)
        self.assertEqual(manager._terminal_error[0],'engine_unresponsive')

    def test_engine_import_and_initialization_failures_are_recorded_before_main(self) -> None:
        fake = self.root / "fake_isaac"
        fake.mkdir()
        module = fake / "isaacsim.py"
        for phase, source in (
            ("isaac_import", "raise ImportError('DLL load failed while importing _pocketfft_umath')"),
            ("simulation_app_init", "class SimulationApp:\n    def __init__(self, config):\n        raise OSError('private diagnostic detail')"),
        ):
            with self.subTest(phase=phase):
                module.write_text(source, encoding="utf-8")
                result_file = self.root / f"{phase}.json"
                outcome = subprocess.run(
                    [sys.executable, "-B", str(ROOT / "scripts" / "twinpulse_engine_host.py"),
                     "--stop-file", str(self.root / "stop"), "--result-file", str(result_file),
                     "--viewport-capture", str(self.root / "capture.png"), "--headless"],
                    cwd=self.root, env={**os.environ, "PYTHONPATH": str(fake)},
                    capture_output=True, text=True, timeout=20, check=False,
                )
                self.assertEqual(outcome.returncode, 1)
                report = json.loads(result_file.read_text(encoding="utf-8"))
                self.assertEqual(report["status"], "FAIL")
                self.assertEqual(report["startup_phase"], phase)
                self.assertEqual(report["capture"]["status"], "NOT_RUN")
                profile = report["startup_profile"]
                self.assertEqual(profile["schema_version"], "engine-startup-profile-1.0")
                self.assertEqual(set(profile["packages"]), {"numpy", "scipy"})
                self.assertNotIn(str(self.root), json.dumps(profile))
                manager = self.manager()
                manager.launch_dir.mkdir(parents=True, exist_ok=True)
                manager.engine_result_file.write_text(json.dumps(report), encoding="utf-8")
                message = manager._exit_message("engine", 1)
                self.assertIn(phase, message)
                self.assertNotIn("private diagnostic detail", message)

    def test_log_tail_is_bounded_and_redacts_secret_markers(self) -> None:
        from twinpulse_app.process_manager import _safe_log_tail

        log = self.root / "large.log"
        with log.open("wb") as stream:
            stream.write(b"unrelated\n" * 200_000)
            stream.write(b"last phase: waiting for bridge\n")
        self.assertIn("waiting for bridge", _safe_log_tail(log))
        with log.open("ab") as stream:
            stream.write(b"Authorization: Bearer private-value\n")
        self.assertEqual(_safe_log_tail(log), "process log contained redacted credential material")


if __name__ == "__main__":
    unittest.main()
