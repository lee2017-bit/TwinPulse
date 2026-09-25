"""Finite, owner-aware local process supervisor for the TwinPulse product App."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
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
            self.close()
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
            self._api.CloseHandle(self._handle)
            self._handle = None


class ProcessManagerError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class LaunchResult:
    launch_id: str
    base_url: str
    ui_url: str
    backend_pid: int
    engine_pid: int
    stage_epoch: str
    capabilities: tuple[str, ...]


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
        port: int = 0,
        headless: bool = False,
        ready_timeout_s: float = 120.0,
        popen_factory: Callable[..., subprocess.Popen[bytes]] = subprocess.Popen,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        credential_target: str = DEFAULT_CREDENTIAL_TARGET,
        fixture_mode: bool = False,
        replay_report: Path | None = None,
        replay_fixture_id: str | None = None,
        job_factory: Callable[[str], _WindowsJob] | None = None,
    ) -> None:
        self.repo_root = repo_root.resolve()
        self.state_dir = state_dir.resolve()
        self.python_executable = python_executable.resolve()
        self.isaac_python = isaac_python.resolve()
        self.browser_executable = browser_executable.resolve() if browser_executable else None
        self.port = int(port)
        self.headless = bool(headless)
        self.ready_timeout_s = float(ready_timeout_s)
        self.credential_target = str(credential_target).strip()
        self.fixture_mode = bool(fixture_mode)
        self.replay_report = replay_report.resolve() if replay_report is not None else None
        self.replay_fixture_id = replay_fixture_id
        if (self.replay_report is None) != (self.replay_fixture_id is None):
            raise ValueError("replay_report and replay_fixture_id must be supplied together")
        if self.fixture_mode and self.replay_report is not None:
            raise ValueError("fixture_mode and replay mode are mutually exclusive")
        if not self.credential_target:
            raise ValueError("credential_target must not be empty")
        self._popen = popen_factory
        self._clock = clock
        self._sleep = sleep
        self._owned: dict[str, subprocess.Popen[bytes]] = {}
        self._jobs: dict[str, _WindowsJob] = {}
        self._job_factory = job_factory
        if self._job_factory is None and os.name == "nt" and popen_factory is subprocess.Popen:
            self._job_factory = _WindowsJob
        self._logs: dict[str, object] = {}
        self._lock_owned = False
        self._product_secret: str | None = None
        self._terminal_error: tuple[str, str] | None = None
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
        self.engine_result_file = self.launch_dir / "engine-result.json"
        self.viewport_capture_file = self.launch_dir / "isaac-viewport.png"
        self.backend_log_file = self.launch_dir / "backend.log"
        self.engine_log_file = self.launch_dir / "engine.log"
        self.lock_file = self.state_dir / "launcher.lock"

    def validate(self) -> None:
        if not 0 <= self.port <= 65535:
            raise ProcessManagerError("port_invalid", "Port must be in the range 0..65535")
        required = {
            "python": self.python_executable,
            "isaac_python": self.isaac_python,
            "backend": self.repo_root / "scripts" / "twinpulse_backend.py",
            "engine_host": self.repo_root / "scripts" / "twinpulse_engine_host.py",
            "web_build": self.repo_root / "apps" / "twinpulse-web" / "dist" / "index.html",
            "extension": self.repo_root / "extensions" / "twinpulse.extension" / "config" / "extension.toml",
        }
        missing = [f"{name}={path}" for name, path in required.items() if not path.is_file()]
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

    def start(self, *, open_browser: bool = True) -> LaunchResult:
        self.validate()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._acquire_lock()
        self._clear_runtime_files()
        self._write_status("starting", "backend_start", "Starting authenticated local backend")
        self._product_secret = secrets.token_urlsafe(32)
        engine_secret = secrets.token_urlsafe(32)
        try:
            backend_env = os.environ.copy()
            backend_env["TWINPULSE_PRODUCT_BOOTSTRAP"] = self._product_secret
            backend_env["TWINPULSE_ENGINE_BOOTSTRAP"] = engine_secret
            backend_env["TWINPULSE_LAUNCH_ID"] = self._launch_id
            backend = self._spawn("backend", self._backend_command(), backend_env, hidden=True)
            ready = self._wait_backend_ready(backend)
            base_url = _validated_loopback_url(ready.get("base_url"))

            self._write_status("starting", "engine_start", "Starting owned Isaac 3D engine")
            engine_env = os.environ.copy()
            engine_env["TWINPULSE_BRIDGE_URL"] = base_url
            engine_env["TWINPULSE_ENGINE_BOOTSTRAP"] = engine_secret
            engine_env["TWINPULSE_STATE_DIR"] = str(self.engine_state_dir)
            engine_env["TWINPULSE_LAUNCH_ID"] = self._launch_id
            engine = self._spawn("engine", self._engine_command(), engine_env, hidden=self.headless)
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
            if open_browser:
                self.open_browser(result.ui_url)
            return result
        except Exception as error:
            code = error.code if isinstance(error, ProcessManagerError) else type(error).__name__
            self._terminal_error = (str(code), str(error))
            self.stop(final_status="error")
            raise

    def open_browser(self, ui_url: str) -> None:
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
        self._write_status("ready", "ready", "Authenticated Isaac stage is ready", browser_launched=True)

    def monitor(self, *, poll_s: float = 0.25) -> int:
        while True:
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
            if engine_code is not None:
                message = self._exit_message("engine", engine_code)
                self._terminal_error = ("engine_exited", message)
                self._write_status("error", "engine_exited", message)
                return 1
            engine_status = _read_json(self.engine_status_file)
            if (
                engine_status is not None
                and engine_status.get("engine_session_id")
                and not engine_status.get("engine_connected")
            ):
                tail = _safe_log_tail(self.engine_log_file)
                message = "engine heartbeat is stale while its PID is still running"
                if tail:
                    message += f": {tail}"
                self._terminal_error = ("engine_unresponsive", message)
                self._write_status("error", "engine_unresponsive", message)
                return 1
            self._sleep(poll_s)

    def stop(self, *, final_status: str = "stopped") -> None:
        if not self._lock_owned and not self._owned and not self._logs and not self._jobs:
            return
        if self._lock_owned and self._terminal_error is None:
            self._write_status("stopping", "shutdown", "Stopping owned TwinPulse processes")
        engine = self._owned.get("engine")
        if self._lock_owned and engine is not None and engine.poll() is None:
            try:
                _write_json_atomic(self.engine_stop_file, {
                    "schema_version": "1.0",
                    "launch_id": self._launch_id,
                    "owner_pid": self._owner_pid,
                    "requested_at_utc": _utc_now(),
                })
            except OSError:
                pass
        self._stop_owned("engine", graceful_s=20.0)
        self._stop_owned("backend", graceful_s=5.0)
        for stream in self._logs.values():
            try:
                stream.close()
            except Exception:
                pass
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
        command = [
            str(self.python_executable), str(self.repo_root / "scripts" / "twinpulse_backend.py"),
            "--port", str(self.port), "--ready-file", str(self.ready_file),
            "--static-root", str(self.repo_root / "apps" / "twinpulse-web" / "dist"),
            "--engine-status-file", str(self.engine_status_file),
            "--supervisor-status-file", str(self.supervisor_status_file),
            "--settings-path", str(self.provider_settings_file),
            "--credential-target", self.credential_target,
            "--bootstrap-ttl-s", "180",
        ]
        if self.fixture_mode:
            command.append("--fixture-mode")
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
            process = self._popen(
                list(command), cwd=str(self.repo_root), env=dict(environment),
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
                    job.close()
                stream.close()
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
            backend_code = backend.poll()
            engine_code = engine.poll()
            if backend_code is not None:
                raise ProcessManagerError("backend_exited", self._exit_message("backend", backend_code))
            if engine_code is not None:
                raise ProcessManagerError("engine_start_failed", self._exit_message("engine", engine_code))
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
        process = self._owned.pop(name, None)
        job = self._jobs.pop(name, None)
        if process is None:
            if job is not None:
                job.close()
            return
        try:
            if process.poll() is None:
                try:
                    process.wait(timeout=graceful_s)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    try:
                        process.wait(timeout=5.0)
                    except subprocess.TimeoutExpired:
                        if job is not None:
                            job.terminate()
                        else:
                            process.kill()
                        process.wait(timeout=5.0)
        finally:
            # KILL_ON_JOB_CLOSE reaps descendants left behind by a wrapper
            # even when the root process already exited after terminate().
            if job is not None:
                job.close()

    def _acquire_lock(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({
            "schema_version": "1.0",
            "launch_id": self._launch_id,
            "owner_pid": self._owner_pid,
            "pid": self._owner_pid,
            "started_at_utc": self._started_at,
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
                    raise ProcessManagerError(
                        "launcher_already_running",
                        f"TwinPulse launcher is already running (PID {pid}); no process was terminated",
                    )
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
            self.engine_result_file, self.viewport_capture_file,
        ):
            path.unlink(missing_ok=True)

    def _write_status(
        self, status: str, phase: str, message: str, *, browser_launched: bool | None = None,
    ) -> None:
        previous = _read_json(self.supervisor_status_file) or {}
        browser = previous.get("browser") if isinstance(previous.get("browser"), Mapping) else {}
        payload = {
            "schema_version": "1.0", "status": status, "phase": phase,
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
        tail = _safe_log_tail(self.launch_dir / f"{name}.log")
        return f"{name} exited with code {code}" + (f": {tail}" if tail else "")


def _validated_loopback_url(value: object) -> str:
    if not isinstance(value, str):
        raise ProcessManagerError("backend_url_invalid", "Backend did not publish a URL")
    parsed = urlsplit(value)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.port is None:
        raise ProcessManagerError("backend_url_invalid", "Backend URL is not an explicit loopback endpoint")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise ProcessManagerError("backend_url_invalid", "Backend URL contains unsupported components")
    return f"http://127.0.0.1:{parsed.port}"


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
        content = path.read_bytes()[-2048:].decode("utf-8", errors="replace")
    except OSError:
        return ""
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    tail = " | ".join(lines[-3:])
    for marker in ("sk-", "Bearer ", "bootstrap="):
        if marker in tail:
            return "process log contained redacted credential material"
    return tail[:240]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
