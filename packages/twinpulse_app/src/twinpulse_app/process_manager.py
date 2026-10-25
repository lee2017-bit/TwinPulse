# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Finite, owner-aware local process supervisor for the TwinPulse product App."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import secrets
import subprocess
import time
from typing import Callable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4

from .credentials import DEFAULT_CREDENTIAL_TARGET


REQUIRED_ENGINE_CAPABILITIES = frozenset({"simulation", "build", "telemetry", "watchdog"})
ALLOWED_BROWSER_NAMES = frozenset({"chrome.exe", "msedge.exe", "chrome", "msedge"})


class _JobBasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class _JobExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JobBasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _JobBasicAccountingInformation(ctypes.Structure):
    _fields_ = [
        ("TotalUserTime", ctypes.c_longlong),
        ("TotalKernelTime", ctypes.c_longlong),
        ("ThisPeriodTotalUserTime", ctypes.c_longlong),
        ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
        ("TotalPageFaultCount", wintypes.DWORD),
        ("TotalProcesses", wintypes.DWORD),
        ("ActiveProcesses", wintypes.DWORD),
        ("TotalTerminatedProcesses", wintypes.DWORD),
    ]


class _WindowsJob:
    """Own one process tree and kill remaining descendants when closed."""

    _EXTENDED_LIMIT_INFORMATION = 9
    _BASIC_ACCOUNTING_INFORMATION = 1
    _KILL_ON_JOB_CLOSE = 0x00002000

    def __init__(self, name: str) -> None:
        if os.name != "nt":
            raise RuntimeError("Windows Job Objects are unavailable on this platform")
        self._api = ctypes.WinDLL("Kernel32.dll", use_last_error=True)
        self._api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self._api.CreateJobObjectW.restype = wintypes.HANDLE
        self._api.SetInformationJobObject.argtypes = [
            wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
        ]
        self._api.SetInformationJobObject.restype = wintypes.BOOL
        self._api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self._api.AssignProcessToJobObject.restype = wintypes.BOOL
        self._api.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self._api.TerminateJobObject.restype = wintypes.BOOL
        self._api.QueryInformationJobObject.argtypes = [
            wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self._api.QueryInformationJobObject.restype = wintypes.BOOL
        self._api.CloseHandle.argtypes = [wintypes.HANDLE]
        self._api.CloseHandle.restype = wintypes.BOOL
        self._handle = self._api.CreateJobObjectW(None, f"TwinPulse-{name}-{uuid4().hex}")
        if not self._handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = _JobExtendedLimitInformation()
        limits.BasicLimitInformation.LimitFlags = self._KILL_ON_JOB_CLOSE
        if not self._api.SetInformationJobObject(
            self._handle,
            self._EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
        ):
            error = ctypes.WinError(ctypes.get_last_error())
            try:self.close()
            except Exception as cleanup_error:
                error.add_note('Job handle cleanup also failed: '+type(cleanup_error).__name__)
            raise error

    def assign(self, process: subprocess.Popen[bytes]) -> None:
        process_handle = getattr(process, "_handle", None)
        if process_handle is None:
            raise RuntimeError("spawned process does not expose a Windows process handle")
        if not self._api.AssignProcessToJobObject(
            self._handle, wintypes.HANDLE(int(process_handle)),
        ):
            raise ctypes.WinError(ctypes.get_last_error())

    def terminate(self) -> None:
        if self._handle and not self._api.TerminateJobObject(self._handle, 1):
            raise ctypes.WinError(ctypes.get_last_error())

    def active_process_count(self) -> int:
        information = _JobBasicAccountingInformation()
        returned = wintypes.DWORD()
        if not self._api.QueryInformationJobObject(
            self._handle,
            self._BASIC_ACCOUNTING_INFORMATION,
            ctypes.byref(information),
            ctypes.sizeof(information),
            ctypes.byref(returned),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        return int(information.ActiveProcesses)

    def close(self) -> None:
        if self._handle:
            if not self._api.CloseHandle(self._handle):raise ctypes.WinError(ctypes.get_last_error())
            self._handle = None


class ProcessManagerError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


RESTART_REQUESTED = 75
PROJECT_SWITCH_REQUESTED = 76


@dataclass(frozen=True, slots=True)
class LaunchResult:
    launch_id: str
    base_url: str
    ui_url: str
    backend_pid: int
    engine_pid: int
    stage_epoch: str
    capabilities: tuple[str, ...]
    reused: bool = False
    phase: str = "ready"


class TwinPulseProcessManager:
    """Start only fixed repository/Isaac commands and stop only owned children."""

    def __init__(
        self,
        *,
        repo_root: Path,
        state_dir: Path,
        python_executable: Path,
        isaac_python: Path,
        browser_executable: Path | None = None,
        port: int | None = None,
        headless: bool = False,
        ready_timeout_s: float = 120.0,
        popen_factory: Callable[..., subprocess.Popen[bytes]] = subprocess.Popen,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        credential_target: str = DEFAULT_CREDENTIAL_TARGET,
        fixture_mode: bool = False,
        offline_mode: bool = False,
        project_id: str = "default",
        retry_remaining: int = 3,
        replay_report: Path | None = None,
        replay_fixture_id: str | None = None,
        session_history_root: Path | None = None,
        job_factory: Callable[[str], _WindowsJob] | None = None,
        defer_engine_validation: bool = False,
    ) -> None:
        self.repo_root = repo_root.resolve()
        self.state_dir = state_dir.resolve()
        # Host configuration only, never a path supplied by chat or a command.
        # Keep existing raw archives in their original repository location.
        self.session_history_root = (session_history_root or self.repo_root).resolve()
        self.python_executable = python_executable.resolve()
        self.isaac_python = isaac_python.resolve()
        self.browser_executable = browser_executable.resolve() if browser_executable else None
        self._preferred_port = port is None
        self.defer_engine_validation = bool(defer_engine_validation)
        from .desktop_settings import read_settings
        self.port = read_settings(self.state_dir)['preferred_port'] if port is None else int(port)
        self.headless = bool(headless)
        self.ready_timeout_s = float(ready_timeout_s)
        if not math.isfinite(self.ready_timeout_s) or not 0 < self.ready_timeout_s <= 600:
            raise ProcessManagerError('ready_timeout_invalid','Owned startup timeout must be finite and within 0..600 seconds')
        self.credential_target = str(credential_target).strip()
        self.fixture_mode = bool(fixture_mode)
        self.offline_mode = bool(offline_mode)
        from .project_store import checked_project_id
        self.project_id = checked_project_id(project_id)
        if type(retry_remaining) is not int or not 0 <= retry_remaining <= 3:
            raise ValueError("retry_remaining must be between zero and three")
        self.retry_remaining = retry_remaining
        self.replay_report = replay_report.resolve() if replay_report is not None else None
        self.replay_fixture_id = replay_fixture_id
        if (self.replay_report is None) != (self.replay_fixture_id is None):
            raise ValueError("replay_report and replay_fixture_id must be supplied together")
        if self.fixture_mode and self.replay_report is not None:
            raise ValueError("fixture_mode and replay mode are mutually exclusive")
        if self.offline_mode and (self.fixture_mode or self.replay_report is not None):
            raise ValueError("offline mode cannot be combined with fixture or replay")
        if not self.credential_target:
            raise ValueError("credential_target must not be empty")
        self._popen = popen_factory
        self._clock = clock
        self._sleep = sleep
        self._owned: dict[str, subprocess.Popen[bytes]] = {}
        self._exit_observations={};self._exit_evidence_complete=True
        self._jobs: dict[str, _WindowsJob] = {}
        self._job_factory = job_factory
        if self._job_factory is None and os.name == "nt" and popen_factory is subprocess.Popen:
            self._job_factory = _WindowsJob
        self._logs: dict[str, object] = {}
        self._lock_owned = False
        self._product_secret: str | None = None
        self._terminal_error: tuple[str, str] | None = None
        self._diagnostics_active = False
        self._repair_checks: list[dict[str, object]] = []
        self._started_at = _utc_now()
        self._launch_id = uuid4().hex
        self._owner_pid = os.getpid()

        self.launch_dir = self.state_dir / "launches" / self._launch_id
        self.provider_settings_file = self.state_dir / "provider_settings.json"
        self.engine_state_dir = self.launch_dir / "engine-state"
        self.ready_file = self.launch_dir / "backend-ready.json"
        self.engine_status_file = self.launch_dir / "engine-status.json"
        self.supervisor_status_file = self.launch_dir / "supervisor-status.json"
        self.engine_stop_file = self.launch_dir / "engine-stop.request"
        self.launcher_retry_file = self.launch_dir / "launcher-retry.request"
        self.launcher_project_switch_file = self.launch_dir / "launcher-project-switch.request"
        self.launcher_cancel_file = self.launch_dir / "launcher-startup-cancel.request"
        self.launcher_shutdown_file = self.launch_dir / 'launcher-shutdown.request'
        self.backend_stop_file = self.launch_dir / 'backend-stop.request'
        self.launcher_open_dir = self.launch_dir / "open-requests"
        self.requested_project_id: str | None = None
        self.engine_result_file = self.launch_dir / "engine-result.json"
        self.viewport_capture_file = self.launch_dir / "isaac-viewport.png"
        self.backend_log_file = self.launch_dir / "backend.log"
        self.engine_log_file = self.launch_dir / "engine.log"
        self.lock_file = self.state_dir / "launcher.lock"
        self._launch_trace = None

    def validate(self) -> None:
        if not 0 <= self.port <= 65535:
            raise ProcessManagerError("port_invalid", "Port must be in the range 0..65535")
        required = self.required_paths()
        missing = [f"{name}={path}" for name, path in required.items() if not path.is_file()
                   and not (self.defer_engine_validation and name == 'isaac_python')]
        if missing:
            raise ProcessManagerError("launch_file_missing", "Required launch file is missing: " + "; ".join(missing))
        if self.browser_executable is not None:
            if not self.browser_executable.is_file():
                raise ProcessManagerError("browser_missing", "Configured browser executable does not exist")
            if self.browser_executable.name.lower() not in ALLOWED_BROWSER_NAMES:
                raise ProcessManagerError("browser_not_allowed", "Only Chrome or Edge may be launched")
        if self.replay_report is not None:
            if not self.replay_report.is_file():
                raise ProcessManagerError("replay_report_missing", "Stored replay report does not exist")
            if not self.replay_fixture_id or len(self.replay_fixture_id) > 128:
                raise ProcessManagerError("replay_fixture_invalid", "Stored replay fixture id is invalid")

    def required_paths(self):
        return {
            "python": self.python_executable,
            "isaac_python": self.isaac_python,
            "backend": self.repo_root / "scripts" / "twinpulse_backend.py",
            "engine_host": self.repo_root / "scripts" / "twinpulse_engine_host.py",
            "web_build": self.repo_root / "apps" / "twinpulse-web" / "dist" / "index.html",
            "extension": self.repo_root / "extensions" / "twinpulse.extension" / "config" / "extension.toml",
        }

    def start(self, *, open_browser: bool = True) -> LaunchResult:
        from twinpulse_core.execution_diagnostics import ExecutionStore
        from .project_store import ProjectStore
        try:
            self.validate()
        except Exception as error:
            # Keep invalid launch configuration from creating runtime state.
            # The only write is a separate, owned repository diagnostic artifact.
            store=ExecutionStore(self.state_dir.parent/'launcher-diagnostics',self.project_id)
            trace=store.begin('launcher_start',component='launcher',launch_id=self._launch_id)
            trace.child('launcher_validation').finish('failed',error=error)
            trace.finish('failed',error=error);store.flush(timeout=.25)
            error.execution_id=trace.execution_id
            error.diagnostics_path=store.root/trace.execution_id
            raise
        store=ExecutionStore(ProjectStore.for_project(self.state_dir,self.project_id).path.parent/'diagnostics',self.project_id)
        trace=store.begin('launcher_start',component='launcher',launch_id=self._launch_id)
        self._launch_trace=trace
        try:
            try:
                result=self._start(open_browser=open_browser)
            except ProcessManagerError as error:
                if error.code != 'launcher_already_running':
                    raise
                result = self._reopen_existing(getattr(error, 'existing_launch', {}), open_browser=open_browser)
                trace.child('existing_app_reopen', existing_launch_id=result.launch_id,
                            phase=result.phase).finish('succeeded')
            trace.finish('succeeded')
            # A secondary launcher exits immediately after reopening. Drain
            # its diagnostic queue so this successful entry-point result survives.
            store.flush(timeout=.25)
            return result
        except Exception as error:
            trace.finish('cancelled' if getattr(error,'code',None)=='startup_cancelled' else 'failed',error=error)
            error.execution_id=trace.execution_id
            error.diagnostics_path=store.root/trace.execution_id
            store.flush(timeout=.25)
            raise

    def _start(self, *, open_browser: bool = True) -> LaunchResult:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._acquire_lock()
        from .startup_checks import prepare_owned_directories
        self._repair_checks = prepare_owned_directories(self.launch_dir)
        if any(row['state']=='failed' for row in self._repair_checks):
            self._release_lock()
            raise ProcessManagerError('owned_directory_prepare_failed',
                                      'Fresh owned runtime directory preparation failed; no process was started or original file removed')
        self._clear_runtime_files()
        self._write_status("starting", "backend_start", "Starting authenticated local backend")
        self._product_secret = secrets.token_urlsafe(32)
        engine_secret = secrets.token_urlsafe(32)
        try:
            backend_env = os.environ.copy()
            backend_env["TWINPULSE_PRODUCT_BOOTSTRAP"] = self._product_secret
            backend_env["TWINPULSE_ENGINE_BOOTSTRAP"] = engine_secret
            backend_env["TWINPULSE_LAUNCH_ID"] = self._launch_id
            backend_env['TWINPULSE_LAUNCH_EXECUTION_ID']=self._launch_trace.execution_id
            backend = self._spawn("backend", self._backend_command(), backend_env, hidden=True)
            with self._launch_trace.span('backend_ready_wait'):
                ready = self._wait_backend_ready(backend)
            base_url = _validated_loopback_url(ready.get("base_url"))
            if self._preferred_port:
                from .desktop_settings import save_settings
                save_settings(self.state_dir, preferred_port=urlsplit(base_url).port)

            # The local UI can show engine startup and its failure only while
            # its authenticated backend is still available.
            self._write_status("starting", "backend_ready", "Backend ready; starting Isaac 3D engine")
            if open_browser:
                self.open_browser(base_url + "/")

            self._write_status("starting", "engine_start", "Starting owned Isaac 3D engine")
            if not self.isaac_python.is_file():
                raise ProcessManagerError('isaac_missing', 'Isaac Sim is not installed at the configured folder. '
                    'Your conversations and settings remain available. Exit and configure the installed Isaac folder.')
            engine_env = os.environ.copy()
            engine_env["TWINPULSE_BRIDGE_URL"] = base_url
            engine_env["TWINPULSE_ENGINE_BOOTSTRAP"] = engine_secret
            engine_env["TWINPULSE_STATE_DIR"] = str(self.engine_state_dir)
            engine_env["TWINPULSE_PROJECT_STATE_ROOT"] = str(self.state_dir)
            engine_env["TWINPULSE_SESSION_HISTORY_ROOT"] = str(self.session_history_root)
            engine_env["TWINPULSE_LAUNCH_ID"] = self._launch_id
            engine_env["TWINPULSE_PROJECT_ID"] = self.project_id
            engine = self._spawn("engine", self._engine_command(), engine_env, hidden=self.headless)
            with self._launch_trace.span('engine_ready_wait'):
                engine_status = self._wait_engine_ready(backend, engine)
            snapshot = engine_status["snapshot"]
            capabilities = tuple(str(item) for item in snapshot["capabilities"])
            result = LaunchResult(
                launch_id=self._launch_id,
                base_url=base_url,
                ui_url=base_url + "/",
                backend_pid=int(backend.pid),
                engine_pid=int(engine.pid),
                stage_epoch=str(engine_status["stage_epoch"]),
                capabilities=capabilities,
            )
            self._write_status("ready", "ready", "Authenticated Isaac stage is ready")
            return result
        except Exception as error:
            code = error.code if isinstance(error, ProcessManagerError) else type(error).__name__
            if code == "startup_cancelled":
                self._terminal_error = None
                self.stop()
                raise
            self._terminal_error = (str(code), str(error))
            backend = self._owned.get("backend")
            status = _read_json(self.supervisor_status_file) or {}
            browser = status.get("browser")
            if (backend is not None and backend.poll() is None
                    and isinstance(browser, Mapping) and browser.get("launched") is True):
                self._write_status("error", str(code), str(error))
                self._stop_owned("engine", graceful_s=20.0)
                self._write_status("error", str(code), str(error))
                self._diagnostics_active = True
                raise
            self.stop(final_status="error")
            raise

    def open_browser(self, ui_url: str) -> None:
        if getattr(self, 'ui_host', None) is not None:
            self.ui_host.open(self, ui_url)
            return
        if self.browser_executable is None:
            raise ProcessManagerError("browser_missing", "Chrome or Edge was not found")
        base = _validated_loopback_url(ui_url)
        bootstrap_secret = self._issue_product_bootstrap(base)
        bootstrap_url = f"{base}/#bootstrap={bootstrap_secret}"
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        # Chrome/Edge may delegate to an existing browser process.  The
        # returned PID is therefore never added to the owned shutdown set.
        self._popen(
            [str(self.browser_executable), "--new-window", bootstrap_url],
            cwd=str(self.repo_root), stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            shell=False, creationflags=flags,
        )
        current = _read_json(self.supervisor_status_file) or {}
        self._write_status(
            str(current.get("status", "starting")), str(current.get("phase", "backend_ready")),
            str(current.get("message", "Backend ready; starting Isaac 3D engine")),
            browser_launched=True,
        )

    @property
    def diagnostics_active(self) -> bool:
        return self._diagnostics_active

    def monitor_diagnostics(self, *, poll_s: float = 0.25) -> int:
        """Keep the owned read-only failure UI available until normal exit."""
        return self._trace_monitor(lambda: self._monitor_diagnostics(poll_s=poll_s))

    def _monitor_diagnostics(self, *, poll_s: float = 0.25) -> int:
        while self._diagnostics_active:
            backend = self._owned.get("backend")
            if backend is None or backend.poll() is not None:
                return 1
            self._handle_open_requests()
            if _read_json(self.launcher_shutdown_file) == {'schema_version': '1.0', 'action': 'shutdown'}:
                return 0
            engine = self._owned.get("engine")
            if ((engine is None or engine.poll() is not None)
                    and _read_json(self.launcher_retry_file) == {"schema_version": "1.0", "action": "retry"}):
                return RESTART_REQUESTED
            self._sleep(poll_s)
        return 1

    def monitor(self, *, poll_s: float = 0.25) -> int:
        return self._trace_monitor(lambda: self._monitor(poll_s=poll_s))

    def _lifecycle_trace(self, stage: str):
        start = getattr(self, '_launch_trace', None)
        if start is None:
            return None
        try:
            return start.store.begin(stage, durable=False, component='launcher',
                launch_id=self._launch_id, launch_execution_id=start.execution_id)
        except (OSError, ValueError):
            start.store.note_storage_error()
            return None

    def _trace_monitor(self, function) -> int:
        trace = self._lifecycle_trace('launcher_monitor')
        self._monitor_trace = trace
        try:
            outcome = function()
        except BaseException as error:
            if trace:
                trace.finish('cancelled' if isinstance(error, KeyboardInterrupt) else 'failed',
                    error=error, error_code='monitor_interrupted' if isinstance(error, KeyboardInterrupt) else 'monitor_failed')
            raise
        if trace:
            if outcome == 0 and self._terminal_error is None:
                trace.finish('succeeded')
            elif outcome in {RESTART_REQUESTED, PROJECT_SWITCH_REQUESTED}:
                trace.finish('cancelled', error_code='explicit_restart' if outcome == RESTART_REQUESTED else 'explicit_project_switch')
            else:
                trace.finish('failed', error_code=self._terminal_error[0] if self._terminal_error else 'monitor_incomplete')
        return outcome

    def _monitor(self, *, poll_s: float = 0.25) -> int:
        from .engine_loss_probe import EngineLossProbe
        loss_probe=EngineLossProbe(self._clock)
        suspect=False
        while True:
            if _read_json(self.launcher_shutdown_file) == {'schema_version': '1.0', 'action': 'shutdown'}:
                return 0
            backend = self._owned.get("backend")
            engine = self._owned.get("engine")
            if backend is None or engine is None:
                return 1
            backend_code = backend.poll()
            engine_code = engine.poll()
            if backend_code is not None:
                message = self._exit_message("backend", backend_code)
                self._terminal_error = ("backend_exited", message)
                self._write_status("error", "backend_exited", message)
                return 1
            self._handle_open_requests()
            requested = _read_json(self.launcher_project_switch_file)
            if requested is not None and requested.get("schema_version") == "1.0" \
                    and requested.get("action") == "switch_project":
                from .project_store import checked_project_id
                try:
                    target = checked_project_id(requested.get("project_id"))
                except (TypeError, ValueError):
                    target = None
                if target is not None and target != self.project_id:
                    self.requested_project_id = target
                    return PROJECT_SWITCH_REQUESTED
            if engine_code is not None:
                if engine_code == 0:
                    self._write_status("stopped", "engine_closed", "Isaac was closed normally; stopping owned App processes")
                    return 0
                message = self._exit_message("engine", engine_code)
                self._terminal_error = ("engine_exited", message)
                self._write_status("error", "engine_exited", message)
                return 1
            engine_status,read_info = _read_engine_status(self.engine_status_file)
            if read_info:
                self._note_engine_liveness('status_read_diagnostic',engine_status,read_info=read_info)
            decision=loss_probe.observe(engine_status)
            if decision=='pending':
                if not suspect:
                    self._note_engine_liveness('suspect',engine_status)
                    self._write_status('error','engine_liveness_suspect',
                        'Engine observation is stale. Idle/SIM process loss awaits a distinct status sample; no motion permission was restored.')
                    print('TWINPULSE_ENGINE_LIVENESS_SUSPECT launch_id='+self._launch_id,flush=True)
                suspect=True
            elif decision=='healthy' and suspect:
                self._note_engine_liveness('recovered_without_command_resume',engine_status)
                self._write_status('ready','engine_recovered',
                    'Authenticated engine observation recovered; expired or unknown commands were not resumed.')
                print('TWINPULSE_ENGINE_LIVENESS_RECOVERED launch_id='+self._launch_id,flush=True)
                suspect=False
            elif decision=='failed':
                self._note_engine_liveness('confirmed_or_physical_not_idle',engine_status)
                message = ("engine status file could not be read or validated; heartbeat freshness was not established"
                           if engine_status is None else "engine heartbeat is stale while its PID is still running")
                message += "; see local engine log"
                self._terminal_error = ("engine_unresponsive", message)
                self._write_status("error", "engine_unresponsive", message)
                return 1
            self._sleep(poll_s)

    def _note_engine_liveness(self,phase,value,*,read_info=None):
        """Bounded, secret-free evidence bound to the actual monitor ID."""
        rows=getattr(self,'_engine_liveness_events',[])
        row=dict(phase=phase,at_utc=_utc_now(),manager_monotonic_s=self._clock(),
            value_kind=type(value).__name__,read_info=read_info,
            status_sample_id=(value or {}).get('status_sample_id'),
            engine_session_id=(value or {}).get('engine_session_id'),
            engine_connected=(value or {}).get('engine_connected'),
            physical_runtime_active=(value or {}).get('physical_runtime_active'))
        rows=(rows+[row])[-32:];self._engine_liveness_events=rows
        trace=getattr(self,'_monitor_trace',None)
        try:_write_json_atomic(self.launch_dir/'engine-liveness-observations.json',dict(schema='engine-liveness-confirmation-1.0',
            launch_id=self._launch_id,execution_id=getattr(trace,'execution_id',None),events=rows))
        except OSError:
            if trace:trace.store.note_storage_error()

    def stop(self, *, final_status: str = "stopped") -> None:
        if not self._lock_owned and not self._owned and not self._logs and not self._jobs:
            return
        trace = self._lifecycle_trace('launcher_shutdown')
        self._shutdown_trace = trace
        self._cleanup_failed = False
        try:
            self._stop(final_status=final_status, trace=trace)
        except BaseException as error:
            if trace:
                trace.finish('failed', role='cleanup', error=error, error_code='launcher_cleanup_failed')
            raise
        else:
            if not self._cleanup_failed and not self._owned and not self._jobs and not self._lock_owned:
                # Cleanup success is distinct from startup success. Preserve an
                # original terminal error while letting a diagnostic UI close.
                _write_json_atomic(self.launch_dir / 'cleanup-receipt.json', {
                    'schema_version': 'launcher-cleanup-1.0', 'launch_id': self._launch_id,
                    'owner_pid': self._owner_pid, 'owned_processes_stopped': True,
                    'completed_at_utc': _utc_now(),
                    'process_exit_observations': self._exit_observations,
                    'exit_evidence_complete': self._exit_evidence_complete,
                })
            if trace:
                trace.finish('failed' if self._cleanup_failed else 'succeeded', role='cleanup',
                    error_code='launcher_cleanup_failed' if self._cleanup_failed else None)
        finally:
            if trace:
                trace.store.flush(timeout=.25)

    def _stop(self, *, final_status: str, trace) -> None:
        if self._lock_owned and self._terminal_error is None:
            self._write_status("stopping", "shutdown", "Stopping owned TwinPulse processes")
        engine = self._owned.get("engine")
        if self._lock_owned and engine is not None and engine.poll() is None:
            signal = trace.child('engine_stop_signal') if trace else None
            try:
                _write_json_atomic(self.engine_stop_file, {
                    "schema_version": "1.0",
                    "launch_id": self._launch_id,
                    "owner_pid": self._owner_pid,
                    "requested_at_utc": _utc_now(),
                })
            except OSError as error:
                self._cleanup_failed = True
                if signal:
                    signal.finish('failed', role='cleanup', error=error, error_code='engine_stop_signal_failed')
            else:
                if signal:
                    signal.finish(role='cleanup')
        # Backend owns persistent robot sessions. Its explicit close requests
        # Stop on every owner before bounded ROS/native/journal cleanup; the old
        # ten-second process limit could kill that cleanup before its receipt.
        # This is an upper bound, not a sleep or a claim of physical stop.
        for name, grace in (('engine', 20.0), ('backend', 60.0)):
            if name == 'backend' and self._lock_owned:
                _write_json_atomic(self.backend_stop_file, {'schema_version': '1.0', 'action': 'stop_backend'})
            child = trace.child(name + '_owned_shutdown') if trace else None
            try:
                self._stop_owned(name, graceful_s=grace)
            except BaseException as error:
                if child:
                    child.finish('failed', role='cleanup', error=error, error_code=name + '_shutdown_failed')
                raise
            else:
                if child:
                    child.finish(role='cleanup')
        self._diagnostics_active = False
        for stream in self._logs.values():
            try:
                stream.close()
            except Exception as error:
                self._cleanup_failed = True
                if trace:
                    trace.child('owned_log_close').finish('failed', role='cleanup', error=error,
                        error_code='owned_log_close_failed')
        self._logs.clear()
        if self._lock_owned:
            if self._terminal_error is not None:
                phase, message = self._terminal_error
                self._write_status("error", phase, message)
            else:
                self._write_status(final_status, "stopped", "Owned TwinPulse processes stopped")
            self._release_lock()

    def product_bootstrap(self) -> tuple[str, str]:
        """Mint and return an ephemeral bootstrap pair for an owned client.

        Callers must pass it in memory only and must never log or persist the
        one-time ticket. The long-lived owner secret never enters the URL.
        """
        ready = _read_json(self.ready_file)
        if self._product_secret is None or ready is None:
            raise ProcessManagerError("bootstrap_unavailable", "Product bootstrap is not available")
        base_url = _validated_loopback_url(ready.get("base_url"))
        return base_url, self._issue_product_bootstrap(base_url)

    def _issue_product_bootstrap(self, base_url: str) -> str:
        owner_secret = self._product_secret
        if owner_secret is None:
            raise ProcessManagerError("bootstrap_unavailable", "Product bootstrap is not available")
        payload = json.dumps(
            {"owner_secret": owner_secret}, separators=(",", ":"),
        ).encode("utf-8")
        request = Request(
            base_url + "/v1/bootstrap/product/issue",
            data=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=5.0) as response:
                value = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ProcessManagerError(
                "bootstrap_issue_failed", "Could not mint a product bootstrap ticket",
            ) from error
        ticket = value.get("bootstrap_secret") if isinstance(value, Mapping) else None
        if not isinstance(ticket, str) or len(ticket) < 32:
            raise ProcessManagerError(
                "bootstrap_issue_invalid", "Backend returned an invalid product bootstrap ticket",
            )
        return ticket

    def _backend_command(self) -> list[str]:
        from .runtime_paths import script_command
        command = script_command(self.repo_root, 'backend', python=self.python_executable) + [
            "--port", str(self.port), "--ready-file", str(self.ready_file),
            "--static-root", str(self.repo_root / "apps" / "twinpulse-web" / "dist"),
            "--engine-status-file", str(self.engine_status_file),
            "--supervisor-status-file", str(self.supervisor_status_file),
            "--launcher-retry-file", str(self.launcher_retry_file),
            "--launcher-project-switch-file", str(self.launcher_project_switch_file),
            "--launcher-cancel-file", str(self.launcher_cancel_file),
            "--engine-result-file", str(self.engine_result_file),
            "--settings-path", str(self.provider_settings_file),
            "--credential-target", self.credential_target,
            "--project-id", self.project_id,
            "--session-history-root", str(self.session_history_root),
            "--retry-remaining", str(self.retry_remaining),
            # The one-use engine credential is issued before Kit initializes.
            # Keep it valid for the bounded owned startup window, not forever.
            # Default120s startup still uses the existing180s bootstrap lifetime.
            "--bootstrap-ttl-s", str(math.ceil(max(180.,self.ready_timeout_s+60.))),
            '--launcher-shutdown-file', str(self.launcher_shutdown_file),
            '--backend-stop-file', str(self.backend_stop_file),
            '--port-candidates', '10' if self._preferred_port else '1',
        ]
        if self.fixture_mode:
            command.append("--fixture-mode")
        if self.offline_mode:
            command.append("--offline")
        if self.replay_report is not None:
            command.extend([
                "--replay-report", str(self.replay_report),
                "--replay-fixture-id", str(self.replay_fixture_id),
            ])
        return command

    def _engine_command(self) -> list[str]:
        command = [
            str(self.isaac_python), "-B", str(self.repo_root / "scripts" / "twinpulse_engine_host.py"),
            "--stop-file", str(self.engine_stop_file),
            "--result-file", str(self.engine_result_file),
            "--viewport-capture", str(self.viewport_capture_file),
        ]
        if self.headless:
            command.append("--headless")
        return command

    def _spawn(
        self, name: str, command: Sequence[str], environment: Mapping[str, str], *, hidden: bool,
    ) -> subprocess.Popen[bytes]:
        self.launch_dir.mkdir(parents=True, exist_ok=True)
        log_path = self.launch_dir / f"{name}.log"
        stream = log_path.open("wb")
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        if hidden:
            flags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            from .runtime_paths import child_environment, external_dll_search
            from contextlib import nullcontext
            with external_dll_search() if name == 'engine' else nullcontext():
                process = self._popen(
                    list(command), cwd=str(self.repo_root), env=child_environment(environment, external=name == 'engine'),
                    stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT,
                    shell=False, creationflags=flags,
                )
        except Exception as error:
            stream.close()
            raise ProcessManagerError(
                f"{name}_spawn_failed",
                f"Failed to start {name}: {type(error).__name__}: {error}",
            ) from error
        job: _WindowsJob | None = None
        if self._job_factory is not None and (
            self._job_factory is not _WindowsJob or isinstance(process, subprocess.Popen)
        ):
            try:
                job = self._job_factory(name)
                job.assign(process)
            except Exception as error:
                try:
                    process.terminate()
                    process.wait(timeout=5.0)
                except Exception:
                    try:
                        process.kill()
                    except Exception:
                        pass
                if job is not None:
                    try:job.close()
                    except Exception as cleanup_error:error.add_note('Job handle cleanup also failed: '+type(cleanup_error).__name__)
                try:stream.close()
                except Exception as cleanup_error:error.add_note('Process log cleanup also failed: '+type(cleanup_error).__name__)
                raise ProcessManagerError(
                    f"{name}_job_failed",
                    f"Failed to establish owned {name} process tree: {type(error).__name__}: {error}",
                ) from error
        self._owned[name] = process
        if job is not None:
            self._jobs[name] = job
        self._logs[name] = stream
        return process

    def _wait_backend_ready(self, process: subprocess.Popen[bytes]) -> dict[str, object]:
        deadline = self._clock() + min(self.ready_timeout_s, 30.0)
        while self._clock() < deadline:
            code = process.poll()
            if code is not None:
                raise ProcessManagerError("backend_start_failed", self._exit_message("backend", code))
            value = _read_json(self.ready_file)
            if value is not None:
                return value
            self._sleep(0.05)
        raise ProcessManagerError("backend_ready_timeout", "Backend did not publish readiness before timeout")

    def _wait_engine_ready(
        self, backend: subprocess.Popen[bytes], engine: subprocess.Popen[bytes],
    ) -> dict[str, object]:
        deadline = self._clock() + self.ready_timeout_s
        while self._clock() < deadline:
            if _read_json(self.launcher_cancel_file) == {"schema_version": "1.0", "action": "cancel_startup"}:
                raise ProcessManagerError("startup_cancelled", "Startup cancelled by the authenticated local user")
            if _read_json(self.launcher_shutdown_file) == {'schema_version': '1.0', 'action': 'shutdown'}:
                raise ProcessManagerError('startup_cancelled', 'Exit requested by the authenticated local user')
            backend_code = backend.poll()
            engine_code = engine.poll()
            if backend_code is not None:
                raise ProcessManagerError("backend_exited", self._exit_message("backend", backend_code))
            if engine_code is not None:
                raise ProcessManagerError("engine_start_failed", self._exit_message("engine", engine_code))
            self._handle_open_requests()
            value = _read_json(self.engine_status_file)
            if value is not None and self._engine_ready(value):
                return value
            self._sleep(0.1)
        raise ProcessManagerError(
            "engine_ready_timeout",
            "Isaac did not complete authenticated handshake, capabilities, and stage readiness before timeout",
        )

    @staticmethod
    def _engine_ready(value: Mapping[str, object]) -> bool:
        snapshot = value.get("snapshot")
        if not value.get("engine_connected") or not isinstance(snapshot, Mapping):
            return False
        capabilities = snapshot.get("capabilities")
        permitted = snapshot.get("permitted_commands")
        return bool(
            value.get("stage_epoch")
            and snapshot.get("stage_epoch") == value.get("stage_epoch")
            and isinstance(capabilities, list)
            and REQUIRED_ENGINE_CAPABILITIES.issubset(str(item) for item in capabilities)
            and isinstance(permitted, list)
            and "get_state" in permitted
            and snapshot.get("runtime_state") in {"idle", "built", "paused", "completed"}
        )

    def _stop_owned(self, name: str, *, graceful_s: float) -> None:
        # Do not lose ownership on a failed wait/job-close. A later stop must
        # recheck the same process rather than certify an empty handle table.
        process = self._owned.get(name)
        job = self._jobs.get(name)
        if process is None:
            if job is not None:
                job.close()
                self._jobs.pop(name, None)
            return
        began=time.monotonic()
        observation=dict(role=name,pid=process.pid,ownership='HELD_POPEN_PROCESS_HANDLE',
            began_monotonic_s=began,root_disposition='UNKNOWN',return_code=None,
            job_close_requested=False,job_active_before_close=None,job_observation='NOT_USED' if job is None else 'UNKNOWN',
            evidence_complete=True,errors=[])
        primary_error=None
        try:
            if process.poll() is None:
                observation['root_disposition']='GRACEFUL_WAIT'
                try:
                    process.wait(timeout=graceful_s)
                except subprocess.TimeoutExpired:
                    observation['root_disposition']='TERMINATE_AFTER_TIMEOUT'
                    process.terminate()
                    try:
                        process.wait(timeout=5.0)
                    except subprocess.TimeoutExpired:
                        if job is not None:
                            observation['root_disposition']='JOB_TERMINATE_AFTER_TIMEOUT'
                            job.terminate()
                        else:
                            observation['root_disposition']='KILL_AFTER_TIMEOUT'
                            process.kill()
                        process.wait(timeout=5.0)
                else:observation['root_disposition']='EXITED_DURING_GRACE'
            else:observation['root_disposition']='ALREADY_EXITED'
        except BaseException as error:
            primary_error=error
            observation['errors'].append(dict(stage='root_wait',error=type(error).__name__))
            observation['evidence_complete']=False
            raise
        finally:
            # KILL_ON_JOB_CLOSE reaps descendants left behind by a wrapper
            # even when the root process already exited after terminate().
            try:
                try:observation['return_code']=process.poll()
                except Exception as error:
                    observation['evidence_complete']=False;observation['errors'].append(dict(stage='root_poll',error=type(error).__name__))
                if job is not None:
                    try:
                        observation['job_active_before_close']=job.active_process_count()
                        observation['job_observation']='OBSERVED'
                    except Exception as error:
                        observation['evidence_complete']=False;observation['errors'].append(dict(stage='job_query',error=type(error).__name__))
                    observation['job_close_requested']=True
                    try:job.close()
                    except BaseException as error:
                        observation['evidence_complete']=False;observation['errors'].append(dict(stage='job_close',error=type(error).__name__))
                        if primary_error is None:raise
                        primary_error.add_note('Job handle cleanup also failed: '+type(error).__name__)
            finally:
                observation.update(ended_at_utc=_utc_now(),elapsed_s=max(0.,time.monotonic()-began))
                self._record_owned_exit(name,observation)
        self._owned.pop(name, None)
        self._jobs.pop(name, None)

    def _record_owned_exit(self,name,observation):
        """Evidence must not throw over the original wait/cleanup exception."""
        self._exit_observations[name]=observation
        self._exit_evidence_complete=self._exit_evidence_complete and observation['evidence_complete']
        try:
            _write_json_atomic(self.launch_dir/'owned-exit-observations.json',dict(schema='owned-exit-observations-1.0',
                launch_id=self._launch_id,owner_pid=self._owner_pid,
                execution_id=getattr(getattr(self,'_shutdown_trace',None),'execution_id',None),
                evidence_complete=self._exit_evidence_complete,roles=self._exit_observations))
        except Exception as error:
            self._exit_evidence_complete=False
            observation['evidence_complete']=False;observation['errors'].append(dict(stage='evidence_store',error=type(error).__name__))

    def _acquire_lock(self) -> None:
        from .release_contract import MaintenanceLock, initialize_data_epoch
        try:
            with MaintenanceLock(self.state_dir):
                initialize_data_epoch(self.state_dir)
                self._acquire_launcher_lock()
        except ValueError as error:
            raise ProcessManagerError(str(error), str(error)) from error

    def _acquire_launcher_lock(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({
            "schema_version": "1.0",
            "launch_id": self._launch_id,
            "owner_pid": self._owner_pid,
            "pid": self._owner_pid,
            "started_at_utc": self._started_at,
            "repo_root": str(self.repo_root),
            "reopen_protocol": "1.0",
            "desktop_automation": bool(os.environ.get('TWINPULSE_UI_TEST_CDP_PORT')),
            "automation_port": int(os.environ['TWINPULSE_UI_TEST_CDP_PORT']) if os.environ.get('TWINPULSE_UI_TEST_CDP_PORT') else None,
            'process_identity': _process_identity(self._owner_pid),
        })
        for _attempt in range(2):
            try:
                descriptor = os.open(self.lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                try:
                    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                        stream.write(payload)
                except Exception as error:
                    self.lock_file.unlink(missing_ok=True)
                    raise ProcessManagerError(
                        "launcher_lock_write_failed", f"Could not write launcher lock: {error}",
                    ) from error
                self._lock_owned = True
                return
            except FileExistsError:
                existing = self._read_lock_with_retry()
                if existing is None:
                    continue
                pid = existing.get("owner_pid", existing.get("pid"))
                if isinstance(pid, int) and _pid_alive(pid):
                    if existing.get('process_identity') is not None and existing['process_identity'] != _process_identity(pid):
                        raise ProcessManagerError('launcher_owner_identity_changed', 'The recorded launcher process identity changed; its record was preserved')
                    error = ProcessManagerError(
                        "launcher_already_running",
                        f"TwinPulse launcher is already running (PID {pid}); no process was terminated",
                    )
                    error.existing_launch = existing
                    raise error
                if not isinstance(pid, int) or pid <= 0:
                    raise ProcessManagerError(
                        "launcher_lock_invalid",
                        "Existing launcher lock has no valid owner PID; it was preserved",
                    )
                try:
                    self.lock_file.unlink()
                except FileNotFoundError:
                    continue
                except PermissionError as error:
                    raise ProcessManagerError(
                        "launcher_lock_access_denied",
                        "Existing stale launcher lock could not be removed",
                    ) from error
            except PermissionError as error:
                raise ProcessManagerError(
                    "launcher_lock_access_denied", "Launcher lock could not be created or opened",
                ) from error
        raise ProcessManagerError("launcher_lock_failed", "Could not acquire the TwinPulse launcher lock")

    def _reopen_existing(self, existing: Mapping[str, object], *, open_browser: bool) -> LaunchResult:
        """Ask the live owner to open its App; never copy a credential or adopt its children."""
        launch_id, owner = existing.get('launch_id'), existing.get('owner_pid')
        if type(existing.get('desktop_automation')) is bool and existing['desktop_automation']!=bool(os.environ.get('TWINPULSE_UI_TEST_CDP_PORT')):
            raise ProcessManagerError('launcher_mode_mismatch','Exit the current TwinPulse normally before switching normal/test mode; no process was stopped')
        if existing.get('process_identity') is not None and existing['process_identity'] != _process_identity(owner):
            raise ProcessManagerError('launcher_owner_identity_changed', 'The existing launch owner could not be verified')
        if (not isinstance(launch_id, str) or not re.fullmatch('[a-f0-9]{32}', launch_id)
                or type(owner) is not int or owner <= 0
                or existing.get('repo_root') != str(self.repo_root)
                or existing.get('reopen_protocol') != '1.0'):
            raise ProcessManagerError('launcher_reopen_unavailable',
                'An older or different TwinPulse launch is running. Close that App normally, then start again; no process was terminated')
        launch = self.state_dir / 'launches' / launch_id
        requests = launch / 'open-requests'
        if (launch.is_symlink() or launch.resolve() != launch or requests.is_symlink()
                or requests.resolve() != requests):
            raise ProcessManagerError('launcher_reopen_invalid', 'Existing launch path is invalid; it was preserved')
        # O_EXCL ownership precedes directory preparation and the first status
        # write. A quick double-click must wait for that same owner's record,
        # not misclassify the small publication gap as a broken running App.
        published = self._clock() + 5.0
        status = {}
        while self._clock() < published:
            if _read_json(self.lock_file) != dict(existing) or not _pid_alive(owner):
                break
            status = _read_json(launch / 'supervisor-status.json') or {}
            if status:
                break
            self._sleep(.05)
        identity = status.get('launch') or {}
        if (not isinstance(identity, Mapping) or identity.get('instance_id') != launch_id
                or identity.get('owner_pid') != owner or status.get('status') not in {'starting', 'ready', 'error'}
                or _read_json(self.lock_file) != dict(existing) or not _pid_alive(owner)):
            raise ProcessManagerError('launcher_reopen_unavailable',
                'Existing TwinPulse is not available for reopening; no process was terminated')
        requests.mkdir(exist_ok=True)
        if len(list(requests.glob('*.request.json'))) >= 24:
            raise ProcessManagerError('launcher_reopen_busy', 'Existing TwinPulse has too many pending open requests')
        request_id = uuid4().hex
        request = requests / (request_id + '.request.json')
        reply = requests / (request_id + '.reply.json')
        _write_json_atomic(request, dict(schema_version='1.0', action='open', request_id=request_id,
            launch_id=launch_id, owner_pid=owner, requested_at_utc=_utc_now(), open_browser=bool(open_browser)))
        try:
            deadline = self._clock() + 30.0
            while self._clock() < deadline:
                if _read_json(self.lock_file) != dict(existing) or not _pid_alive(owner):
                    raise ProcessManagerError('launcher_reopen_changed',
                        'The existing TwinPulse launch changed during reopening. Start again; no process was terminated')
                result = _read_json(reply)
                if result is not None:
                    if (result.get('request_id') != request_id or result.get('launch_id') != launch_id
                            or result.get('owner_pid') != owner):
                        raise ProcessManagerError('launcher_reopen_invalid', 'Existing launch returned an invalid open acknowledgement')
                    if result.get('status') != 'opened':
                        raise ProcessManagerError('launcher_reopen_failed', 'Existing TwinPulse could not open its App; no process was terminated')
                    base = _validated_loopback_url(result.get('base_url'))
                    return LaunchResult(launch_id, base, base + '/', int(result.get('backend_pid', 0)),
                        int(result.get('engine_pid', 0)), '', (), reused=True, phase=str(result.get('phase', 'starting')))
                self._sleep(.05)
            raise ProcessManagerError('launcher_reopen_timeout',
                'Existing TwinPulse did not acknowledge reopening within 30 seconds; no duplicate App was started')
        finally:
            request.unlink(missing_ok=True)
            reply.unlink(missing_ok=True)

    def _handle_open_requests(self) -> None:
        if not self._lock_owned or not self.launcher_open_dir.is_dir() or self.launcher_open_dir.is_symlink():
            return
        backend = self._owned.get('backend')
        ready = _read_json(self.ready_file)
        if backend is None or backend.poll() is not None or ready is None:
            return
        for request in sorted(self.launcher_open_dir.glob('*.request.json'))[:24]:
            request_id = request.name.removesuffix('.request.json')
            if not re.fullmatch('[a-f0-9]{32}', request_id) or request.is_symlink():
                continue
            reply = self.launcher_open_dir / (request_id + '.reply.json')
            if reply.is_symlink():
                continue
            try:
                value = _read_json(request) if request.stat().st_size <= 4096 else None
            except OSError:
                # The requesting launcher may time out and remove only its own request.
                continue
            if not value:
                continue
            try:
                at = datetime.fromisoformat(value.get('requested_at_utc', ''))
                age = (datetime.now(timezone.utc) - at).total_seconds()
            except (TypeError, ValueError):
                continue
            if (value.get('schema_version') != '1.0' or value.get('action') != 'open'
                    or value.get('request_id') != request_id or value.get('launch_id') != self._launch_id
                    or value.get('owner_pid') != self._owner_pid or type(value.get('open_browser')) is not bool
                    or not -2 <= age <= 30):
                continue
            trace = self._lifecycle_trace('launcher_reopen')
            payload = dict(request_id=request_id, launch_id=self._launch_id, owner_pid=self._owner_pid,
                           status='failed')
            try:
                base = _validated_loopback_url(ready.get('base_url'))
                if value['open_browser']:
                    self.open_browser(base + '/')
                status = _read_json(self.supervisor_status_file) or {}
                engine = self._owned.get('engine')
                payload.update(status='opened', base_url=base, backend_pid=int(backend.pid),
                    engine_pid=int(engine.pid) if engine is not None else 0, phase=status.get('phase', 'starting'))
            except Exception as error:
                if trace:
                    trace.finish('failed', error=error, error_code='launcher_reopen_failed')
            else:
                if trace:
                    trace.finish('succeeded', request_id=request_id)
            try:
                _write_json_atomic(reply, payload)
                request.unlink(missing_ok=True)
            except OSError:
                # An optional window-open failure must never stop the running App/Isaac.
                continue

    def _read_lock_with_retry(self) -> dict[str, object] | None:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                content = self.lock_file.read_text(encoding="utf-8")
                value = json.loads(content)
                if isinstance(value, Mapping):
                    return dict(value)
                last_error = ValueError("launcher lock root is not an object")
            except FileNotFoundError:
                return None
            except PermissionError as error:
                last_error = error
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
                last_error = error
            if attempt < 2:
                self._sleep(0.02)
        code = "launcher_lock_access_denied" if isinstance(last_error, PermissionError) else "launcher_lock_unreadable"
        raise ProcessManagerError(
            code, "Existing launcher lock could not be read safely and was preserved",
        ) from last_error

    def _release_lock(self) -> None:
        try:
            existing = _read_json(self.lock_file)
            if (
                existing is not None
                and existing.get("launch_id") == self._launch_id
                and existing.get("owner_pid", existing.get("pid")) == self._owner_pid
            ):
                self.lock_file.unlink(missing_ok=True)
        finally:
            self._lock_owned = False

    def _clear_runtime_files(self) -> None:
        for path in (
            self.ready_file, self.engine_status_file, self.engine_stop_file,
            self.engine_result_file, self.viewport_capture_file, self.launcher_retry_file,
            self.launcher_project_switch_file,
            self.launcher_cancel_file,
        ):
            path.unlink(missing_ok=True)

    def _write_status(
        self, status: str, phase: str, message: str, *, browser_launched: bool | None = None,
    ) -> None:
        previous = _read_json(self.supervisor_status_file) or {}
        browser = previous.get("browser") if isinstance(previous.get("browser"), Mapping) else {}
        payload = {
            "schema_version": "1.0", "status": status, "phase": phase,
            "retry_remaining": self.retry_remaining,
            "message": str(message)[:240], "started_at_utc": self._started_at,
            "updated_at_utc": _utc_now(),
            "launch": {
                "instance_id": self._launch_id,
                "owner_pid": self._owner_pid,
                "started_at_utc": self._started_at,
            },
            "backend": self._component("backend"),
            "engine": self._component("engine"),
            "browser": {
                "launched": bool(browser.get("launched", False))
                if browser_launched is None else browser_launched,
            },
        }
        # Only opaque identifiers leave the launcher; no log text or paths.
        origin = getattr(self, '_monitor_trace', None) if status == 'error' else None
        origin = origin or getattr(self, '_launch_trace', None)
        if origin:
            payload['diagnostic_execution_id'] = origin.execution_id
        from .startup_checks import file_checklist, package_checklist
        payload['startup_checks'] = (
            file_checklist(self.required_paths(), state_dir=self.state_dir, isaac_python=self.isaac_python)
            + package_checklist(self.repo_root, python_executable=self.python_executable) + self._repair_checks
        )
        _write_json_atomic(self.supervisor_status_file, payload)

    def _component(self, name: str) -> dict[str, object]:
        process = self._owned.get(name)
        if process is None:
            return {"owned": False, "state": "not_started"}
        code = process.poll()
        return {
            "owned": True, "pid": int(process.pid),
            "state": "running" if code is None else "exited",
            **({"exit_code": int(code)} if code is not None else {}),
        }

    def _exit_message(self, name: str, code: int) -> str:
        if name == "engine":
            result = _read_json(self.engine_result_file)
            if result is not None and result.get("status") == "FAIL":
                phase = result.get("startup_phase")
                error_type = result.get("error_type")
                if phase in {"isaac_import", "simulation_app_init"} and isinstance(error_type, str) \
                        and error_type.isidentifier() and len(error_type) <= 64:
                    return f"engine exited with code {code} during {phase} ({error_type}); see local engine result"
        # Status is exposed through the authenticated product API. Logs can
        # contain user paths, prompts, or provider diagnostics, so never copy
        # their arbitrary tail into that status payload.
        return f"{name} exited with code {code}; see local {name} log"


def _validated_loopback_url(value: object) -> str:
    if not isinstance(value, str):
        raise ProcessManagerError("backend_url_invalid", "Backend did not publish a URL")
    parsed = urlsplit(value)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.port is None:
        raise ProcessManagerError("backend_url_invalid", "Backend URL is not an explicit loopback endpoint")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise ProcessManagerError("backend_url_invalid", "Backend URL contains unsupported components")
    return f"http://127.0.0.1:{parsed.port}"


def _engine_status_win_api():
    """Exact local-file API; no process or desktop automation."""
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                               ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    kernel.ReadFile.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    return kernel


def _status_file_win_error(phase):
    error = ctypes.WinError(ctypes.get_last_error())
    error.status_read_phase = phase
    return error


def _read_engine_status_bytes(path: Path, limit: int):
    """One bounded immutable publication read, with replace-compatible sharing.

    CRT readers can deny DELETE sharing while the writer atomically replaces
    the filename. A pinned Win32 handle permits READ/WRITE/DELETE sharing and
    reads only that original file's bytes. No cache, restamp, extra health grace
    or fallback to a previously observed physical-idle value is introduced.
    """
    if os.name != 'nt':
        with path.open('rb') as stream:
            return stream.read(limit)
    kernel = _engine_status_win_api()
    handle = kernel.CreateFileW(str(path), 0x80000000, 1 | 2 | 4, None, 3, 128, None)
    if handle == ctypes.c_void_p(-1).value:
        raise _status_file_win_error('open_shared_delete')
    primary = None
    try:
        buffer = ctypes.create_string_buffer(limit)
        count = wintypes.DWORD()
        if not kernel.ReadFile(handle, buffer, limit, ctypes.byref(count), None):
            raise _status_file_win_error('read_file')
        return buffer.raw[:count.value]
    except BaseException as error:
        primary = error
        raise
    finally:
        if not kernel.CloseHandle(handle):
            close_error = _status_file_win_error('close_handle')
            if primary is None:
                raise close_error
            primary.status_close_winerror = close_error.winerror


def _read_engine_status(path: Path):
    """Retry only transient local read/parse errors, never a health decision.

    Three attempts, no sleeps/cache/restamping. This is NOT a wall-time bound
    on OS I/O. A successfully read stale/invalid sample is returned unchanged.
    """
    failures=[]
    for attempt in range(1,4):
        began=time.monotonic()
        try:
            raw=_read_engine_status_bytes(path,1024*1024+1)
            if len(raw)>1024*1024:
                return None,dict(attempt=attempt,reason='oversized_status',failures=failures)
            value=json.loads(raw.decode('utf-8'))
            if not isinstance(value,dict):
                return None,dict(attempt=attempt,reason='non_object_status',value_kind=type(value).__name__,failures=failures)
            missing=[key for key in ('engine_connected','engine_session_id','status_sample_id','physical_runtime_active') if key not in value]
            info=dict(attempt=attempt,reason='missing_health_fields' if missing else 'read_recovered',missing_fields=missing,failures=failures) if missing or failures else None
            return value,info
        except (OSError,UnicodeError,json.JSONDecodeError) as error:
            failures.append(dict(attempt=attempt,type=type(error).__name__,errno=getattr(error,'errno',None),
                                 winerror=getattr(error,'winerror',None),phase=getattr(error,'status_read_phase','read_or_decode'),
                                 elapsed_s=max(0.,time.monotonic()-began),close_winerror=getattr(error,'status_close_winerror',None)))
    return None,dict(attempt=3,reason='status_read_failed',failures=failures)


def _read_json(path: Path) -> dict[str, object] | None:
    try:
        if not path.is_file() or path.stat().st_size > 1024 * 1024:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        return dict(value) if isinstance(value, Mapping) else None
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None


def _write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{time.monotonic_ns()}.tmp")
    temporary.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    try:
        for attempt in range(50):
            try:
                os.replace(temporary, path)
                return
            except PermissionError:
                if attempt == 49:
                    raise
                time.sleep(0.01)
    finally:
        temporary.unlink(missing_ok=True)


def _process_identity(pid):
    if os.name != 'nt' or type(pid) is not int or pid <= 0:
        return None
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4)]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return None
    try:
        buffer = ctypes.create_unicode_buffer(32768); size = wintypes.DWORD(len(buffer))
        times = [wintypes.FILETIME() for _ in range(4)]
        if (not kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size))
                or not kernel.GetProcessTimes(handle, *(ctypes.byref(item) for item in times))):
            return None
        return {'executable': buffer.value, 'creation_filetime': (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime}
    finally:
        kernel.CloseHandle(handle)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        # Windows does not implement ``os.kill(pid, 0)`` as the harmless
        # Unix existence probe. Query a limited process handle instead so
        # duplicate-launch detection can never terminate the inspected PID.
        kernel32 = ctypes.WinDLL("Kernel32.dll", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        try:
            exit_code = wintypes.DWORD()
            return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))) and exit_code.value == 259
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _safe_log_tail(path: Path) -> str:
    try:
        with path.open("rb") as stream:
            stream.seek(0, os.SEEK_END)
            stream.seek(max(0, stream.tell() - 2048))
            content = stream.read(2048).decode("utf-8", errors="replace")
    except OSError:
        return ""
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    tail = " | ".join(lines[-3:])
    lowered = tail.lower()
    for marker in ("sk-", "bearer ", "bootstrap=", "password", "api_key", "apikey", "secret", "authorization"):
        if marker in lowered:
            return "process log contained redacted credential material"
    return tail[:240]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
