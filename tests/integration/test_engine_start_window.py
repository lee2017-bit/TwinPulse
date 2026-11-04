# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Isaac start window, engine environment, proxy rule, python.bat command line and stale lock.

Supplementary unit tests only: no Windows, Isaac, Kit or provider is used.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
import os
from pathlib import Path
import runpy
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import tomllib
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import uuid


ROOT = Path(__file__).resolve().parents[2]
for source in (
    ROOT / "packages" / "twinpulse_core" / "src",
    ROOT / "packages" / "twinpulse_provider" / "src",
    ROOT / "packages" / "twinpulse_app" / "src",
):
    sys.path.insert(0, str(source))

from twinpulse_app import ProcessManagerError, TwinPulseProcessManager  # noqa: E402
import twinpulse_app.process_manager as pm  # noqa: E402
from twinpulse_app.desktop_settings import configured_isaac_root, read_settings, save_settings  # noqa: E402

EXTENSION_TOML = ROOT / "extensions" / "twinpulse.extension" / "config" / "extension.toml"
# Read from the real manifest, so a later dependency change keeps these tests valid.
DECLARED = sorted(tomllib.loads(EXTENSION_TOML.read_text(encoding="utf-8"))["dependencies"])


class FakeProcess:
    def __init__(self, pid: int, code: int | None = None) -> None:
        self.pid, self.code = pid, code

    def poll(self) -> int | None:
        return self.code

    def wait(self, timeout: float | None = None) -> int:
        if self.code is None:
            raise subprocess.TimeoutExpired("fake", timeout)
        return self.code

    def terminate(self) -> None:
        self.code = 0

    def kill(self) -> None:
        self.code = -9


class Clock:
    def __init__(self) -> None:
        self.value = 1_000.0

    def __call__(self) -> float:
        return self.value


class FakeProxy:
    """Records every connection; a loopback request must never arrive here."""

    def __init__(self) -> None:
        self.socket = socket.create_server(("127.0.0.1", 0))
        self.socket.settimeout(0.1)
        self.url = f"http://127.0.0.1:{self.socket.getsockname()[1]}"
        self.seen: list[bytes] = []
        self.closed = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self) -> None:
        while not self.closed.is_set():
            try:
                connection, _ = self.socket.accept()
            except OSError:
                continue
            with connection:
                connection.settimeout(2.0)
                try:
                    self.seen.append(connection.recv(4096).split(b"\r\n", 1)[0])
                    connection.sendall(b"HTTP/1.1 503 Blocked\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                except OSError:
                    pass

    def close(self) -> None:
        self.closed.set()
        self.thread.join(2.0)
        self.socket.close()


class LoopbackServer:
    """Tiny real HTTP server on 127.0.0.1 answering fixed JSON per path."""

    def __init__(self, routes: dict[str, object]) -> None:
        received = self.paths = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                self.rfile.read(int(self.headers.get("Content-Length", "0")))
                received.append(self.path)
                body = json.dumps(routes[self.path]).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args: object) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def bridge_module():
    """Load the extension bridge without Kit, as test_bridge_lease_rotation does."""
    package = ModuleType("_tp_engine_start_bridge")
    package.__path__ = []
    adapter = ModuleType("_tp_engine_start_bridge.isaac_adapter")
    adapter.IsaacSimulationAdapter = object
    path = ROOT / "extensions/twinpulse.extension/twinpulse/extension/bridge_client.py"
    spec = importlib.util.spec_from_file_location("_tp_engine_start_bridge.bridge_client", path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {package.__name__: package, adapter.__name__: adapter}):
        spec.loader.exec_module(module)
    return module


def engine_host():
    with patch.object(sys, "argv", ["host", "--stop-file", "unused-stop", "--result-file", "unused-result",
                                    "--viewport-capture", "unused-capture"]):
        return runpy.run_path(str(ROOT / "scripts" / "twinpulse_engine_host.py"), run_name="engine_start_window_test")


INTERNET_SETTINGS = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"


def fake_winreg(values: dict[str, object]) -> ModuleType:
    """winreg with one Internet Options key holding values; anything else is not found."""
    module = ModuleType("winreg")
    module.HKEY_CURRENT_USER = object()

    class Key:
        def Close(self) -> None:  # noqa: N802
            pass

    def open_key(root: object, path: str) -> Key:
        if root is not module.HKEY_CURRENT_USER or path != INTERNET_SETTINGS:
            raise FileNotFoundError(path)
        return Key()

    def query_value(_key: Key, name: str) -> tuple[object, int]:
        if name not in values:
            raise FileNotFoundError(name)
        return values[name], 1

    module.OpenKey, module.QueryValueEx = open_key, query_value
    return module


def windows_urllib() -> ModuleType:
    """The installed urllib.request compiled with its Windows proxy branch selected.

    Only its two platform tests change, so getproxies() is the Windows rule:
    the proxy variables when any is set, otherwise the Internet Options registry.
    """
    source = Path(urllib.request.__file__).read_text(encoding="utf-8")
    for marker, selected in (("if sys.platform == 'darwin':", "if False:"), ("elif os.name == 'nt':", "elif True:")):
        if source.count(marker) != 1:
            raise AssertionError("urllib.request no longer has exactly one " + marker)
        source = source.replace(marker, selected)
    module = ModuleType("_tp_windows_urllib_request")
    exec(compile(source, urllib.request.__file__, "exec"), module.__dict__)  # noqa: S102
    return module


def without_launcher_variables(environment: dict[str, str]) -> dict[str, str]:
    return {key: value for key, value in environment.items() if not key.startswith(("TWINPULSE_", "PYTHON"))}


class EngineStartWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        configured = os.environ.get("TWINPULSE_TEST_TMP")
        if configured:
            self.root = Path(configured) / f"engine-start-{uuid.uuid4().hex}"
            self.root.mkdir(parents=True)
            self.addCleanup(shutil.rmtree, self.root, True)
        else:
            temporary = tempfile.TemporaryDirectory()
            self.addCleanup(temporary.cleanup)
            self.root = Path(temporary.name)
        for relative in (
            "python.exe", "isaac/python.bat", "scripts/twinpulse_backend.py",
            "scripts/twinpulse_engine_host.py", "apps/twinpulse-web/dist/index.html",
            "extensions/twinpulse.extension/config/extension.toml",
        ):
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("fixture", encoding="utf-8")
        self.state = self.root / "state"

    def manager(self, **overrides: object) -> TwinPulseProcessManager:
        values = {
            "repo_root": self.root, "state_dir": self.state,
            "python_executable": self.root / "python.exe", "isaac_python": self.root / "isaac/python.bat",
        }
        values.update(overrides)
        return TwinPulseProcessManager(**values)  # type: ignore[arg-type]

    def child_environments(self, outer: dict[str, str]) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
        """os.environ without proxy variables plus outer, and the backend and engine environments start() builds."""
        manager = self.manager()
        spawned: dict[str, dict[str, str]] = {}

        def spawn(command, **kwargs):
            role = "engine" if any("twinpulse_engine_host.py" in str(part) for part in command) else "backend"
            spawned[role] = dict(kwargs["env"])
            if role == "backend":
                manager.ready_file.write_text(json.dumps({"base_url": "http://127.0.0.1:43123"}), encoding="utf-8")
                return FakeProcess(201)
            raise OSError("engine environment captured")

        manager._popen = spawn  # type: ignore[assignment]
        with patch.dict(os.environ):
            for key in [key for key in os.environ if key.lower().endswith("_proxy")]:
                os.environ.pop(key)
            os.environ.update(outer)
            given = dict(os.environ)
            with self.assertRaises(ProcessManagerError) as raised:
                manager.start(open_browser=False)
        self.assertEqual(raised.exception.code, "engine_spawn_failed")
        return given, spawned

    # a) start window and bootstrap lifetime
    def test_default_window_is_600_s_with_800_s_one_use_bootstrap_lifetime(self) -> None:
        manager = self.manager()
        self.assertEqual(manager.ready_timeout_s, 600.0)
        command = manager._backend_command()
        self.assertEqual(command[command.index("--bootstrap-ttl-s") + 1], "800")
        self.assertEqual(pm.MAX_BOOTSTRAP_TTL_S, 800)
        with self.assertRaisesRegex(ProcessManagerError, "0..600"):
            self.manager(ready_timeout_s=601)

    def test_engine_credential_outlives_the_longest_ui_open_and_a_599_s_engine_start(self) -> None:
        from twinpulse_app import CommandBroker, LocalApiServer
        from twinpulse_app.desktop_ui_host import HANDSHAKE_TIMEOUT_S
        clock, bridge = Clock(), bridge_module()
        at: dict[str, float] = {}
        servers: list[LocalApiServer] = []
        owned: dict[str, FakeProcess] = {}
        engine_secret: list[str] = []
        bootstraps: list[object] = []

        def engine_bootstrap() -> None:
            # The real extension client, as the engine runs it once Kit is up.
            client = bridge.BridgeClient(SimpleNamespace(engine_session_id="engine-1", stage_epoch="stage-1"),
                                         base_url=servers[0].base_url, bootstrap_secret=engine_secret[0])
            try:
                client._bootstrap()
            except bridge.BridgeProtocolError as error:
                bootstraps.append(str(error))
                owned["engine"].code = 1  # an engine without a session exits
                return
            bootstraps.append("accepted")
            pm._write_json_atomic(manager.engine_status_file, {
                "engine_connected": True, "stage_epoch": "stage-1",
                "snapshot": {"stage_epoch": "stage-1", "capabilities": sorted(pm.REQUIRED_ENGINE_CAPABILITIES),
                             "permitted_commands": ["get_state"], "runtime_state": "idle"}})

        def sleep(seconds: float) -> None:
            clock.value += seconds
            if "backend_spawn" in at and "ready" not in at and clock.value - at["backend_spawn"] >= 89.9:
                # Readiness arrives at the end of the backend budget.
                at["ready"] = clock.value
                pm._write_json_atomic(manager.ready_file, {"base_url": servers[0].base_url})
            if "engine_spawn" in at and "bootstrap" not in at and clock.value - at["engine_spawn"] >= 599.0 - 1e-6:
                at["bootstrap"] = clock.value
                engine_bootstrap()

        def spawn(command, **kwargs):
            environment = kwargs["env"]
            if any("twinpulse_backend.py" in str(part) for part in command):
                # The backend's API server starts the credential's clock; the
                # earliest it can is at once.
                at["backend_spawn"] = clock.value
                server = LocalApiServer(CommandBroker(clock=clock), clock=clock,
                                        product_bootstrap_secret=environment["TWINPULSE_PRODUCT_BOOTSTRAP"],
                                        engine_bootstrap_secret=environment["TWINPULSE_ENGINE_BOOTSTRAP"],
                                        bootstrap_ttl_s=float(command[command.index("--bootstrap-ttl-s") + 1]))
                server.start()
                servers.append(server)
                owned["backend"] = FakeProcess(301)
                return owned["backend"]
            at["engine_spawn"] = clock.value
            engine_secret.append(environment["TWINPULSE_ENGINE_BOOTSTRAP"])
            owned["engine"] = FakeProcess(302)
            return owned["engine"]

        class SlowestWindow:
            """Confirms at the end of the handshake window; its ticket takes the whole request timeout."""

            def open(self, owner: TwinPulseProcessManager, ui_url: str) -> None:
                at["ui_open"] = clock.value
                clock.value += HANDSHAKE_TIMEOUT_S
                owner._issue_product_bootstrap(ui_url.rstrip("/"))
                clock.value += pm.BOOTSTRAP_TICKET_TIMEOUT_S
                at["ui_opened"] = clock.value

        manager = self.manager(clock=clock, sleep=sleep, popen_factory=spawn)
        manager.ui_host = SlowestWindow()
        try:
            result = manager.start(open_browser=True)
            # Still one-use after the longer lifetime.
            again = bridge.BridgeClient(SimpleNamespace(engine_session_id="engine-1", stage_epoch="stage-1"),
                                        base_url=servers[0].base_url, bootstrap_secret=engine_secret[0])
            with self.assertRaisesRegex(bridge.BridgeProtocolError, "bootstrap_rejected"):
                again._bootstrap()
        finally:
            manager.stop()
            for server in servers:
                server.stop()
        self.assertEqual(bootstraps, ["accepted"])
        self.assertEqual((result.backend_pid, result.engine_pid, result.stage_epoch), (301, 302, "stage-1"))
        self.assertAlmostEqual(at["ready"] - at["backend_spawn"], 89.9, delta=0.06)
        self.assertAlmostEqual(at["ui_open"], at["ready"], delta=1e-6)
        self.assertAlmostEqual(at["engine_spawn"] - at["ui_open"], HANDSHAKE_TIMEOUT_S + pm.BOOTSTRAP_TICKET_TIMEOUT_S,
                               delta=1e-6)
        self.assertAlmostEqual(at["bootstrap"] - at["engine_spawn"], 599.0, delta=0.06)

    def test_backend_accepts_the_launcher_lifetime_and_refuses_an_unbounded_one(self) -> None:
        from twinpulse_app import CommandBroker, LocalApiServer
        ready = self.root / "unused-ready.json"
        environment = {key: value for key, value in os.environ.items()
                       if key not in {"TWINPULSE_PRODUCT_BOOTSTRAP", "TWINPULSE_ENGINE_BOOTSTRAP"}}

        def run(value: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run([sys.executable, "-B", str(ROOT / "scripts" / "twinpulse_backend.py"),
                                   "--ready-file", str(ready), "--bootstrap-ttl-s", value],
                                  cwd=ROOT, env=environment, capture_output=True, text=True, timeout=60, check=False)

        longest = str(pm.MAX_BOOTSTRAP_TTL_S)
        values = (longest, "nan", "inf", "0", str(pm.MAX_BOOTSTRAP_TTL_S + 1))
        with ThreadPoolExecutor(len(values)) as pool:
            results = dict(zip(values, pool.map(run, values)))
        accepted = results.pop(longest)
        # Past argument parsing: only the missing bootstrap environment stops it.
        self.assertEqual((accepted.returncode, accepted.stderr.strip().splitlines()[-1]),
                         (1, "Bootstrap environment is missing"), accepted.stderr)
        for value, refused in results.items():
            with self.subTest(value=value):
                self.assertEqual(refused.returncode, 2, refused.stderr)
                self.assertIn("argument --bootstrap-ttl-s: must be finite and within 0..800 seconds", refused.stderr)
        self.assertFalse(ready.exists())
        for unbounded in (float("nan"), float("inf")):
            with self.subTest(unbounded=unbounded), self.assertRaisesRegex(ValueError, "lifetimes must be positive"):
                LocalApiServer(CommandBroker(), product_bootstrap_secret="p" * 43, engine_bootstrap_secret="e" * 43,
                               bootstrap_ttl_s=unbounded)

    # b) backend readiness budget
    def test_backend_readiness_budget_is_90_s_and_never_longer_than_the_window(self) -> None:
        for timeout, budget in ((600.0, 90.0), (30.0, 30.0)):
            with self.subTest(timeout=timeout):
                clock = Clock()
                manager = self.manager(ready_timeout_s=timeout, clock=clock,
                                       sleep=lambda seconds: setattr(clock, "value", clock.value + seconds))
                started = clock.value
                with self.assertRaises(ProcessManagerError) as raised:
                    manager._wait_backend_ready(FakeProcess(11))
                self.assertEqual(raised.exception.code, "backend_ready_timeout")
                self.assertAlmostEqual(clock.value - started, budget, delta=0.06)

    # c), d), e), g) child environments and the engine command
    def test_engine_and_backend_environments_and_progress_argument(self) -> None:
        manager = self.manager()
        spawned: dict[str, tuple[list[str], dict[str, str]]] = {}

        def spawn(command, **kwargs):
            role = "engine" if any("twinpulse_engine_host.py" in str(part) for part in command) else "backend"
            spawned[role] = (list(command), dict(kwargs["env"]))
            if role == "backend":
                manager.ready_file.write_text(json.dumps({"base_url": "http://127.0.0.1:43123"}), encoding="utf-8")
                return FakeProcess(201)
            raise OSError("engine command captured")

        manager._popen = spawn  # type: ignore[assignment]
        with patch.dict(os.environ, {"NO_PROXY": "corp.example", "HTTP_PROXY": "http://proxy.invalid:3128",
                                     "TWINPULSE_ISAAC_ROOT": str(self.root / "elsewhere")}):
            for key in [k for k in os.environ if k in {"no_proxy", "PYTHONUNBUFFERED", "PYTHONNOUSERSITE"}
                        or "EULA" in k.upper()]:
                os.environ.pop(key)
            with self.assertRaises(ProcessManagerError) as raised:
                manager.start(open_browser=False)
        self.assertEqual(raised.exception.code, "engine_spawn_failed")
        command, engine = spawned["engine"]
        _, backend = spawned["backend"]
        self.assertEqual(engine["PYTHONUNBUFFERED"], "1")
        self.assertEqual(engine["PYTHONNOUSERSITE"], "1")
        self.assertNotIn("PYTHONNOUSERSITE", backend)
        for environment in (engine, backend):
            self.assertEqual(environment["NO_PROXY"], "corp.example,127.0.0.1,localhost")
            self.assertEqual(environment["no_proxy"], "corp.example,127.0.0.1,localhost")
            self.assertEqual(environment["HTTP_PROXY"], "http://proxy.invalid:3128")
            self.assertEqual([key for key in environment if "EULA" in key.upper()], [])
        self.assertEqual(backend["TWINPULSE_ISAAC_ROOT"], str((self.root / "isaac").resolve()))
        self.assertEqual(command[command.index("--progress-file") + 1], str(manager.engine_progress_file))
        self.assertEqual(manager.engine_progress_file.parent, manager.launch_dir)

    def test_no_proxy_appends_loopback_and_never_drops_existing_entries(self) -> None:
        cases = (
            ({"NO_PROXY": "corp.example"}, "corp.example,127.0.0.1,localhost", "corp.example,127.0.0.1,localhost"),
            ({"NO_PROXY": "a", "no_proxy": "b"}, "a,127.0.0.1,localhost", "b,127.0.0.1,localhost"),
            ({"no_proxy": "corp, "}, "corp,127.0.0.1,localhost", "corp,127.0.0.1,localhost"),
            ({"NO_PROXY": "LocalHost, 127.0.0.1"}, "LocalHost, 127.0.0.1", "LocalHost, 127.0.0.1"),
            ({"NO_PROXY": "localhost"}, "localhost,127.0.0.1", "localhost,127.0.0.1"),
            ({"NO_PROXY": "*"}, "*", "*"),
        )
        for given, upper, lower in cases:
            with self.subTest(given=given):
                result = pm._no_proxy_loopback({**given, "OTHER": "kept"})
                self.assertEqual((result["NO_PROXY"], result["no_proxy"], result["OTHER"]), (upper, lower, "kept"))

    def test_child_environments_without_a_proxy_variable_are_passed_unchanged(self) -> None:
        environment = {"PATH": r"C:\Windows", "USERPROFILE": r"C:\Users\kim"}
        self.assertIs(pm._no_proxy_loopback(environment), environment)
        self.assertEqual(environment, {"PATH": r"C:\Windows", "USERPROFILE": r"C:\Users\kim"})
        given, spawned = self.child_environments({})
        self.assertEqual(sorted(spawned), ["backend", "engine"])
        for role, child in spawned.items():
            with self.subTest(role=role):
                self.assertEqual(without_launcher_variables(child), without_launcher_variables(given))
                with patch.dict(os.environ, child, clear=True):
                    self.assertEqual(urllib.request.getproxies_environment(), {})

    def test_proxy_variables_are_counted_as_urllib_counts_them(self) -> None:
        rows = ({}, {"PATH": "x"}, {"HTTPS_PROXY": "http://p:1"}, {"https_proxy": "http://p:1"}, {"http_proxy": ""},
                {"NO_PROXY": "corp.example"}, {"ALL_PROXY": "socks5://p:1"}, {"_PROXY": "x"},
                {"PROXY": "x", "MYPROXY": "x"}, {"REQUEST_METHOD": "GET", "HTTP_PROXY": "http://p:1"},
                {"REQUEST_METHOD": "GET", "http_proxy": "http://p:1"}, {"HTTPS_PROXY": "http://p:1", "https_proxy": ""})
        for row in rows:
            # The launcher passes os.environ.copy(); on Windows its names are upper case.
            row = {name.upper(): value for name, value in row.items()} if os.name == "nt" else row
            with self.subTest(row=row):
                with patch.dict(os.environ, row, clear=True):
                    expected = urllib.request.getproxies_environment()
                self.assertEqual(pm._environment_proxies(row), expected)
                # Loopback is added exactly when urllib would use the variables.
                self.assertEqual(pm._no_proxy_loopback(dict(row)) == row, expected == {})

    def test_with_a_proxy_variable_only_loopback_bypasses_it(self) -> None:
        environment = {"HTTPS_PROXY": "http://proxy.corp.example:8080", "NO_PROXY": "corp.example"}
        with patch.dict(os.environ, environment, clear=True):
            self.assertFalse(urllib.request.proxy_bypass_environment("127.0.0.1"))  # without the change
        with patch.dict(os.environ, pm._no_proxy_loopback(dict(environment)), clear=True):
            self.assertEqual(urllib.request.getproxies_environment()["https"], "http://proxy.corp.example:8080")
            for host, bypassed in (("127.0.0.1", True), ("localhost", True), ("corp.example", True),
                                   ("api.openai.com", False), ("api.tokenfactory.nebius.com", False)):
                with self.subTest(host=host):
                    self.assertEqual(urllib.request.proxy_bypass_environment(host), bypassed)

    def test_without_proxy_variables_windows_provider_calls_keep_the_internet_options_proxy(self) -> None:
        # A company PC whose only proxy is the Internet Options (registry) one.
        _given, spawned = self.child_environments({})
        windows = windows_urllib()
        registry = fake_winreg({"ProxyEnable": 1, "ProxyServer": "proxy.corp.example:8080", "ProxyOverride": "<local>"})

        def first_hop(environment: dict[str, str]) -> list[tuple[str, int]]:
            hops: list[tuple[str, int]] = []

            def connect(address, *_args, **_kwargs):
                hops.append(address)
                raise ConnectionRefusedError("first hop recorded; nothing is sent")

            with patch.dict(os.environ, environment, clear=True), patch.dict(sys.modules, {"winreg": registry}), \
                    patch.object(urllib.request, "getproxies", windows.getproxies), \
                    patch.object(urllib.request, "proxy_bypass", windows.proxy_bypass), \
                    patch.object(socket, "create_connection", connect):
                # Built as the provider clients build theirs, with the default proxy handler.
                with self.assertRaises(urllib.error.URLError):
                    urllib.request.build_opener().open("https://api.tokenfactory.nebius.com/v1/models", timeout=1)
            return hops

        for role, environment in spawned.items():
            with self.subTest(role=role):
                self.assertEqual(first_hop(environment), [("proxy.corp.example", 8080)])
        # Control: loopback in NO_PROXY anyway, as before, makes urllib skip the
        # registry, and the call goes past the company proxy.
        injected = {**spawned["backend"], "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"}
        self.assertEqual(first_hop(injected), [("api.tokenfactory.nebius.com", 443)])

    def test_loopback_requests_ignore_http_proxy(self) -> None:
        proxy = FakeProxy()
        self.addCleanup(proxy.close)
        server = LoopbackServer({"/v1/bootstrap/product/issue": {"bootstrap_secret": "t" * 43},
                                 "/v1/bootstrap": {"session_token": "engine-session"}})
        self.addCleanup(server.close)
        bridge = bridge_module()
        # urlopen caches its proxy table on first use; start from no cached
        # opener so a return to urlopen is caught whatever ran before.
        with patch.object(urllib.request, "_opener", None), \
                patch.dict(os.environ, {"HTTP_PROXY": proxy.url, "http_proxy": proxy.url}):
            for key in ("NO_PROXY", "no_proxy"):
                os.environ.pop(key, None)
            # Control: a default opener built now really sends loopback to this proxy.
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.build_opener().open(server.base_url + "/v1/bootstrap", data=b"{}", timeout=3)
            self.assertEqual(len(proxy.seen), 1)
            manager = self.manager()
            manager._product_secret = "p" * 43
            self.assertEqual(manager._issue_product_bootstrap(server.base_url), "t" * 43)
            client = bridge.BridgeClient(SimpleNamespace(engine_session_id="engine", stage_epoch="stage"),
                                         base_url=server.base_url, bootstrap_secret="e" * 43)
            client._bootstrap()
            self.assertEqual(client._engine_token, "engine-session")
        self.assertEqual(len(proxy.seen), 1)
        self.assertEqual(server.paths, ["/v1/bootstrap/product/issue", "/v1/bootstrap"])

    def test_bridge_keeps_the_code_of_coded_render_errors(self) -> None:
        bridge = bridge_module()

        class Adapter:
            stage_epoch, engine_session_id, mission_visual_status = "stage", "engine", "NOT_STARTED"
            runtime = SimpleNamespace(state="idle")

            def __init__(self, error: Exception) -> None:
                self.error = error

            def refresh_stage_epoch(self) -> bool:
                return False

            def update_control_lease(self, *_args: object) -> None:
                pass

            def update_mission_geometry(self, _value: object) -> None:
                raise self.error

            update_mission_visual = update_mission_geometry

            def snapshot(self) -> None:
                return None

        # Asset checks raise 'CODE: detail'; the code survives, free text never does.
        for message, geometry_code, visual_code in (
                ("SIM_BURGER_ASSET_DIGEST_MISMATCH: payloads/geometries.usd (matches neither pin set)",
                 "SIM_BURGER_ASSET_DIGEST_MISMATCH", "SIM_BURGER_ASSET_DIGEST_MISMATCH"),
                ("ACTIVE_VISUAL_OUT_OF_ORDER", "ACTIVE_VISUAL_OUT_OF_ORDER", "ACTIVE_VISUAL_OUT_OF_ORDER"),
                (r"layer missing: C:\Users\x", "ACTIVE_GEOMETRY_PROCESSING_FAILED", "ACTIVE_VISUAL_PROCESSING_FAILED")):
            with self.subTest(message=message):
                client = bridge.BridgeClient(Adapter(ValueError(message)), base_url="http://127.0.0.1:1",
                                             bootstrap_secret="x" * 32, clock=lambda: 10.0)
                client._lease_valid, client._lease_id, client._mission_received = True, "lease", 10.0
                client._mission_geometry = {"job_id": "job", "sequence": 1}
                client.update()
                self.assertEqual(client._mission_result["error_code"], geometry_code)
                client._mission_frame, client._mission_available = {"job_id": "job", "sequence": 2}, True
                client.update()
                self.assertEqual(client.mission_visual_error["error_code"], visual_code)

    # e) progress relay and timeout message
    def test_progress_relay_updates_status_on_phase_change_and_names_last_phase_on_timeout(self) -> None:
        clock = Clock()
        manager = self.manager(clock=clock)
        manager.launch_dir.mkdir(parents=True)
        started = clock.value
        writes: list[tuple[str, str, str]] = []
        original_status = manager._write_status

        def record(status, phase, message, **kwargs):
            writes.append((status, phase, message))
            original_status(status, phase, message, **kwargs)

        def progress(**value):
            pm._write_json_atomic(manager.engine_progress_file, {"schema_version": "1.0", **value})

        schedule = [(2.0, dict(phase="simulation_app_init", elapsed_s=2.1)),
                    (2.6, dict(phase="simulation_app_init", elapsed_s=2.1)),
                    (3.2, dict(phase="engine_secret", elapsed_s=3.0, message="free text"))]

        def sleep(seconds):
            clock.value += seconds
            while schedule and clock.value - started >= schedule[0][0]:
                progress(**schedule.pop(0)[1])

        manager._write_status = record  # type: ignore[method-assign]
        manager._sleep = sleep  # type: ignore[assignment]
        progress(phase="isaac_import", elapsed_s=0.4)
        original_read = pm._read_json
        with patch.object(pm, "_read_json", side_effect=original_read) as read:
            with self.assertRaises(ProcessManagerError) as raised:
                manager._wait_engine_ready(FakeProcess(21), FakeProcess(22))
        self.assertEqual(raised.exception.code, "engine_ready_timeout")
        self.assertEqual(str(raised.exception),
                         "Isaac did not finish starting within 600 s (last phase: simulation_app_init, last reported at 2 s)")
        self.assertEqual(writes, [("starting", "engine_start", "Starting Isaac 3D engine: isaac_import (phase started at 0 s)"),
                                  ("starting", "engine_start",
                                   "Starting Isaac 3D engine: simulation_app_init (phase started at 2 s)")])
        status = json.loads(manager.supervisor_status_file.read_text(encoding="utf-8"))
        self.assertEqual(status["ready_timeout_s"], 600.0)
        from twinpulse_app.api import _sanitize_supervisor_status
        self.assertEqual(_sanitize_supervisor_status(status)["message"],
                         "Starting Isaac 3D engine: simulation_app_init (phase started at 2 s)")
        reads = sum(1 for call in read.call_args_list if call.args[0] == manager.engine_progress_file)
        # About once per second (ten 0.1 s polls may sum to just under 1 s),
        # never on each of the 6000 polls.
        self.assertTrue(500 <= reads <= 610, reads)

    def test_timeout_message_includes_http_status_or_says_no_phase_was_reported(self) -> None:
        for progress, expected in (
                (None, "Isaac did not finish starting within 0.5 s (no startup phase was reported)"),
                ({"schema_version": "1.0", "phase": "bridge_wait", "elapsed_s": 512.4, "http_status": 503},
                 "Isaac did not finish starting within 0.5 s (last phase: bridge_wait, last reported at 512 s, HTTP 503)")):
            with self.subTest(progress=progress):
                clock = Clock()
                manager = self.manager(ready_timeout_s=0.5, clock=clock,
                                       sleep=lambda seconds: setattr(clock, "value", clock.value + seconds))
                manager.launch_dir.mkdir(parents=True)
                if progress is not None:
                    pm._write_json_atomic(manager.engine_progress_file, progress)
                with self.assertRaises(ProcessManagerError) as raised:
                    manager._wait_engine_ready(FakeProcess(31), FakeProcess(32))
                self.assertEqual((raised.exception.code, str(raised.exception)), ("engine_ready_timeout", expected))

    def test_failed_progress_status_write_never_aborts_the_engine_wait(self) -> None:
        clock = Clock()
        manager = self.manager(ready_timeout_s=3.0, clock=clock,
                               sleep=lambda seconds: setattr(clock, "value", clock.value + seconds))
        manager.launch_dir.mkdir(parents=True)
        pm._write_json_atomic(manager.engine_progress_file,
                              {"schema_version": "1.0", "phase": "stage_ready", "elapsed_s": 40.0})
        attempts = []

        def busy(*_args, **_kwargs):
            attempts.append(True)
            raise PermissionError("status file held by a scanner")

        manager._write_status = busy  # type: ignore[method-assign]
        with self.assertRaises(ProcessManagerError) as raised:
            manager._wait_engine_ready(FakeProcess(41), FakeProcess(42))
        self.assertEqual(str(raised.exception),
                         "Isaac did not finish starting within 3 s (last phase: stage_ready, last reported at 40 s)")
        self.assertGreaterEqual(len(attempts), 2)  # retried on later reads, not given up

    def test_progress_record_is_allowlisted(self) -> None:
        valid = {"schema_version": "1.0", "phase": "bridge_wait", "elapsed_s": 5, "http_status": 401, "note": "x"}
        self.assertEqual(pm._engine_progress(valid), {"phase": "bridge_wait", "elapsed_s": 5.0, "http_status": 401})
        for change in ({"phase": "Authorization: Bearer x"}, {"phase": ["bridge_wait"]}, {"phase": None},
                       {"schema_version": "2.0"}, {"elapsed_s": True},
                       {"elapsed_s": float("nan")}, {"elapsed_s": -1}, {"elapsed_s": "5"}):
            with self.subTest(change=change):
                self.assertIsNone(pm._engine_progress({**valid, **change}))
        for status in (99, 600, "503", True):
            self.assertIsNone(pm._engine_progress({**valid, "http_status": status})["http_status"])
        self.assertIsNone(pm._engine_progress(None))

    # e), f) engine host side
    def test_engine_host_writes_phases_and_names_kit_dependencies_when_extension_does_not_start(self) -> None:
        fake = self.root / "fake_kit"
        (fake / "omni" / "kit").mkdir(parents=True)
        (fake / "isaacsim.py").write_text(
            "class SimulationApp:\n    def __init__(self, config):\n        self.config = config\n"
            "    def update(self):\n        pass\n    def close(self):\n        pass\n", encoding="utf-8")
        (fake / "omni" / "__init__.py").write_text("", encoding="utf-8")
        (fake / "omni" / "kit" / "__init__.py").write_text("", encoding="utf-8")
        (fake / "omni" / "usd.py").write_text(
            "class _Context:\n    def new_stage(self):\n        pass\n"
            "def get_context():\n    return _Context()\n", encoding="utf-8")
        self.assertGreaterEqual(len(DECLARED), 2, "the manifest declares Kit dependencies")
        missing, unverified = DECLARED[0], DECLARED[-1]
        (fake / "omni" / "kit" / "app.py").write_text(
            f"ENABLED = {sorted(set(DECLARED) - {missing, unverified})!r}\n"
            "class _Manager:\n"
            "    def add_path(self, path):\n        pass\n"
            "    def set_extension_enabled_immediate(self, name, enabled):\n        return False\n"
            "    def is_extension_enabled(self, name):\n"
            f"        if name == {unverified!r}:\n"
            "            raise RuntimeError('unverified API shape')\n"
            "        return name in ENABLED\n"
            "class _App:\n    def get_extension_manager(self):\n        return _Manager()\n"
            "def get_app():\n    return _App()\n", encoding="utf-8")
        base = [sys.executable, "-B", str(ROOT / "scripts" / "twinpulse_engine_host.py"),
                "--stop-file", str(self.root / "stop"), "--viewport-capture", str(self.root / "capture.png"), "--headless"]
        environment = {**os.environ, "PYTHONPATH": str(fake)}
        progress_file = self.root / "launch" / "engine-progress.json"
        outcome = subprocess.run(base + ["--result-file", str(self.root / "result.json"), "--progress-file", str(progress_file)],
                                 cwd=self.root, env=environment, capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual(outcome.returncode, 1, outcome.stderr)
        progress = json.loads(progress_file.read_text(encoding="utf-8"))
        self.assertEqual(progress["schema_version"], "1.0")
        self.assertEqual(progress["phase"], "extension_enable")
        self.assertIsInstance(progress["elapsed_s"], float)
        phases = [line.split()[1] for line in outcome.stdout.splitlines() if line.startswith("TWINPULSE_ENGINE_PHASE ")]
        self.assertEqual(phases, ["phase=isaac_import", "phase=simulation_app_init", "phase=simulation_app_ready",
                                  "phase=stage_ready", "phase=extension_enable"])
        result = json.loads((self.root / "result.json").read_text(encoding="utf-8"))
        self.assertEqual(result["extension_diagnostic"], {"extension": "not_enabled", "dependencies": {
            name: "not_enabled" if name == missing else "unknown" if name == unverified else "enabled"
            for name in DECLARED}})
        self.assertEqual(result["error"], "RuntimeError: Managed TwinPulse Extension did not start (extension "
                         f"not_enabled; dependencies not_enabled: {missing}; dependencies unknown: {unverified})")
        self.assertIn("ModuleNotFoundError", result["traceback"])  # original import failure kept as the cause
        # Without --progress-file the host behaves exactly as before.
        quiet = subprocess.run(base + ["--result-file", str(self.root / "quiet.json")], cwd=self.root, env=environment,
                               capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual(quiet.returncode, 1, quiet.stderr)
        self.assertNotIn("TWINPULSE_ENGINE_PHASE", quiet.stdout)
        self.assertEqual(sorted(p.name for p in progress_file.parent.iterdir()), ["engine-progress.json"])

    def test_dependency_report_helper_with_fake_extension_manager(self) -> None:
        host = engine_host()
        manifest = self.root / "fixture.toml"
        manifest.write_text('\ufeff[package]\ntitle = "x"\n\n[dependencies]\n"omni.usd" = {}\n'
                            'omni_plain = { version = "1.0" }\n"isaacsim.core.api" = {}\n\n'
                            '[[python.module]]\nname = "twinpulse.extension"\n', encoding="utf-8")
        for source, expected in ((EXTENSION_TOML, DECLARED), (manifest, ["isaacsim.core.api", "omni.usd", "omni_plain"])):
            with self.subTest(source=source.name):
                self.assertEqual(host["_declared_dependencies"](source), expected)
                with patch.dict(sys.modules, {"tomllib": None}):  # older Kit Python: regex fallback
                    self.assertEqual(host["_declared_dependencies"](source), expected)
        self.assertEqual(host["_declared_dependencies"](), DECLARED)
        self.assertEqual(host["_declared_dependencies"](self.root / "missing.toml"), [])
        names = ["omni.kit.window.filepicker", "omni.timeline", "omni.usd", "omni.ui", "omni.kit.uiapp",
                 "isaacsim.core.api", "omni.physx"]

        class Manager:
            def is_extension_enabled(self, name):
                if name == "omni.timeline":
                    raise RuntimeError("unverified API shape")
                return name != "omni.kit.window.filepicker"

        class OlderManager:
            def get_enabled_extension_id(self, name):
                return "" if name == "omni.usd" else name + "-1.0.0"

        diagnostic = host["_extension_diagnostic"](Manager(), names)
        self.assertEqual(diagnostic["extension"], "enabled")
        self.assertEqual(diagnostic["dependencies"]["omni.kit.window.filepicker"], "not_enabled")
        self.assertEqual(diagnostic["dependencies"]["omni.timeline"], "unknown")
        self.assertEqual(diagnostic["dependencies"]["omni.usd"], "enabled")
        self.assertEqual(host["_diagnostic_summary"](diagnostic),
                         "extension enabled; dependencies not_enabled: omni.kit.window.filepicker; "
                         "dependencies unknown: omni.timeline")
        older = host["_extension_diagnostic"](OlderManager(), names)
        self.assertEqual([n for n, s in older["dependencies"].items() if s != "enabled"], ["omni.usd"])
        unknown = host["_extension_diagnostic"](object(), names)
        self.assertEqual(set(unknown["dependencies"].values()) | {unknown["extension"]}, {"unknown"})
        everything = host["_extension_diagnostic"](SimpleNamespace(is_extension_enabled=lambda _name: True), names)
        self.assertEqual(host["_diagnostic_summary"](everything), "extension enabled; 7 declared dependencies enabled")
        self.assertEqual(host["_http_status"]("HTTPError: HTTP Error 503: Service Unavailable"), 503)
        self.assertIsNone(host["_http_status"](None))

    def test_engine_host_progress_writer_is_best_effort(self) -> None:
        host = engine_host()
        report = host["_report_progress"]
        printed = io.StringIO()
        with redirect_stdout(printed):
            report("isaac_import")  # no --progress-file: no-op
            self.assertEqual(printed.getvalue(), "")
            host["ARGS"].progress_file = self.root / "progress.json"
            report("bridge_wait", http_status=None)
            report("bridge_wait", http_status=401)  # a refresh is not a new phase line
        self.assertEqual(printed.getvalue().count("TWINPULSE_ENGINE_PHASE phase=bridge_wait "), 1)
        value = json.loads((self.root / "progress.json").read_text(encoding="utf-8"))
        self.assertEqual(set(value), {"schema_version", "phase", "elapsed_s", "http_status"})
        self.assertEqual((value["schema_version"], value["phase"], value["http_status"]), ("1.0", "bridge_wait", 401))
        calls = []

        def busy_then_ok(path, data):
            calls.append(data["phase"])
            if len(calls) < 3:
                raise PermissionError("reader holds the file")
            Path(path).write_text(json.dumps(data), encoding="utf-8")

        with redirect_stdout(io.StringIO()):
            with patch.dict(report.__globals__, {"_write_json_atomic": busy_then_ok}):
                report("bridge_connected")
            self.assertEqual(calls, ["bridge_connected"] * 3)
            self.assertEqual(json.loads((self.root / "progress.json").read_text())["phase"], "bridge_connected")
            with patch.dict(report.__globals__, {"_write_json_atomic": lambda *_: (_ for _ in ()).throw(OSError("disk"))}):
                report("stage_ready")  # never raises into startup
        closed = io.StringIO()
        closed.close()
        with redirect_stdout(closed):
            report("extension_enable")  # a closed stdout never raises either
        self.assertEqual(json.loads((self.root / "progress.json").read_text())["phase"], "extension_enable")

    # g) one Isaac root for every worker
    def test_configured_isaac_root_precedence_and_bom_tolerant_settings(self) -> None:
        launcher_root = self.root / "D-isaac"
        (launcher_root / "python.bat").parent.mkdir(parents=True)
        (launcher_root / "python.bat").write_text("fixture", encoding="utf-8")
        runtime = self.root / "runtime"
        self.assertEqual(configured_isaac_root(runtime, {}), Path(r"C:\isaacsim"))
        save_settings(runtime, isaac_root=str(self.root / "saved-isaac"))
        self.assertEqual(configured_isaac_root(runtime, {}), self.root / "saved-isaac")
        self.assertEqual(configured_isaac_root(runtime, {"TWINPULSE_ISAAC_ROOT": str(launcher_root)}), launcher_root)
        for ignored in ("relative/isaac", str(self.root / "no-python-bat"), ""):
            with self.subTest(ignored=ignored):
                self.assertEqual(configured_isaac_root(runtime, {"TWINPULSE_ISAAC_ROOT": ignored}), self.root / "saved-isaac")
        with patch.dict(os.environ, {"TWINPULSE_ISAAC_ROOT": str(launcher_root)}):
            self.assertEqual(configured_isaac_root(runtime), launcher_root)
        settings = runtime / "desktop-settings.json"
        settings.write_bytes(b"\xef\xbb\xbf" + json.dumps({"schema_version": "1.0", "preferred_port": 8765,
                                                           "isaac_root": "D:/isaacsim"}).encode("utf-8"))
        self.assertEqual(read_settings(runtime)["isaac_root"], "D:/isaacsim")
        save_settings(runtime, preferred_port=8766)
        self.assertFalse(settings.read_bytes().startswith(b"\xef\xbb\xbf"))
        self.assertEqual(read_settings(runtime), {"schema_version": "1.0", "preferred_port": 8766, "isaac_root": "D:/isaacsim"})

    def test_environment_and_library_workers_use_the_launcher_isaac_root(self) -> None:
        from threading import RLock
        from twinpulse_app.environment_workspace import EnvironmentWorkspace
        from twinpulse_app.library_workspace import LibraryWorkspace
        launcher_root = self.root / "D-isaac"
        (launcher_root / "python.bat").parent.mkdir(parents=True)
        (launcher_root / "python.bat").write_text("fixture", encoding="utf-8")
        folder = self.root / "inspection"
        folder.mkdir()
        captured = []

        def run_finite(command, *_args, **_kwargs):
            captured.append(command)
            raise ValueError("WORKER_COMMAND_CAPTURED")

        job: dict[str, object] = {}
        with patch.dict(os.environ, {"TWINPULSE_ISAAC_ROOT": str(launcher_root), "LOCALAPPDATA": str(self.root / "appdata")}), \
                patch("twinpulse_app.environment_workspace.run_finite", side_effect=run_finite):
            self.assertEqual(LibraryWorkspace._isaac_python(None), launcher_root / "python.bat")
            EnvironmentWorkspace._inspect(SimpleNamespace(lock=RLock()), folder, folder / "room.usda", None, job,
                                          None, SimpleNamespace(finish=lambda *_args, **_kwargs: None))
        self.assertEqual(captured[0][0], str(launcher_root / "python.bat"))
        self.assertEqual(job["error"], "WORKER_COMMAND_CAPTURED")

    # h) stale lock after PID reuse
    def lock(self, identity: object) -> bytes:
        self.state.mkdir(parents=True, exist_ok=True)
        content = json.dumps({"schema_version": "1.0", "launch_id": "a" * 32, "owner_pid": os.getpid(),
                              "pid": os.getpid(), "process_identity": identity}).encode("utf-8")
        (self.state / "launcher.lock").write_bytes(content)
        return content

    def test_lock_with_reused_pid_is_archived_and_the_launch_proceeds(self) -> None:
        original = self.lock({"executable": r"C:\TwinPulse\TwinPulse.exe", "creation_filetime": 1})
        manager = self.manager(popen_factory=lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("stop at spawn")))
        printed = io.StringIO()
        with patch.object(pm, "_process_identity", return_value={"executable": r"C:\Other\other.exe", "creation_filetime": 2}):
            with self.assertRaises(ProcessManagerError) as raised, redirect_stdout(printed):
                manager.start(open_browser=False)
        self.assertEqual(raised.exception.code, "backend_spawn_failed")  # past the lock, at the first spawn
        archived = list((self.state / "stale-launch-records").glob("*.json"))
        self.assertEqual(len(archived), 1)
        self.assertRegex(archived[0].name, r"^[0-9a-f]{32}\.json$")
        self.assertIn("TWINPULSE_STALE_LAUNCHER_LOCK_ARCHIVED record=" + archived[0].name, printed.getvalue())
        self.assertEqual(archived[0].read_bytes(), original)
        self.assertFalse(manager.lock_file.exists())  # this launch released its own lock on failure

    def test_lock_of_an_exited_owner_is_archived_not_deleted(self) -> None:
        original = self.lock({"executable": r"C:\TwinPulse\TwinPulse.exe", "creation_filetime": 1})
        manager = self.manager()
        printed = io.StringIO()
        with patch.object(pm, "_pid_alive", return_value=False), redirect_stdout(printed):
            manager._acquire_lock()
        self.assertTrue(manager._lock_owned)
        archived = list((self.state / "stale-launch-records").glob("*.json"))
        self.assertEqual([item.read_bytes() for item in archived], [original])
        self.assertIn("TWINPULSE_STALE_LAUNCHER_LOCK_ARCHIVED record=" + archived[0].name, printed.getvalue())
        self.assertEqual(json.loads((self.state / "launcher.lock").read_text(encoding="utf-8"))["launch_id"],
                         manager._launch_id)

    # i) a second Start asks the running App to reopen
    def reopen_fixture(self, clock: Clock, answer_at: float | None) -> tuple[TwinPulseProcessManager, dict]:
        launch_id, owner = "b" * 32, os.getpid()
        existing = {"schema_version": "1.0", "launch_id": launch_id, "owner_pid": owner, "pid": owner,
                    "repo_root": str(self.root), "reopen_protocol": "1.0"}
        self.state.mkdir(parents=True, exist_ok=True)
        (self.state / "launcher.lock").write_text(json.dumps(existing), encoding="utf-8")
        launch = self.state / "launches" / launch_id
        launch.mkdir(parents=True)
        (launch / "supervisor-status.json").write_text(json.dumps(
            {"status": "starting", "launch": {"instance_id": launch_id, "owner_pid": owner}}), encoding="utf-8")
        start = clock.value

        def sleep(seconds: float) -> None:
            clock.value += seconds
            # The owner answers late, as after re-creating a closed desktop window.
            if answer_at is not None and clock.value - start >= answer_at:
                for request in (launch / "open-requests").glob("*.request.json"):
                    request_id = request.name.removesuffix(".request.json")
                    pm._write_json_atomic(request.with_name(request_id + ".reply.json"), {
                        "request_id": request_id, "launch_id": launch_id, "owner_pid": owner, "status": "opened",
                        "base_url": "http://127.0.0.1:8765", "backend_pid": 10, "engine_pid": 11, "phase": "engine_start"})
        return self.manager(clock=clock, sleep=sleep), existing

    def test_reopen_waits_longer_than_a_desktop_window_handshake(self) -> None:
        from twinpulse_app.desktop_ui_host import HANDSHAKE_TIMEOUT_S
        self.assertGreater(pm.REOPEN_ACK_TIMEOUT_S, HANDSHAKE_TIMEOUT_S)
        clock = Clock()
        manager, existing = self.reopen_fixture(clock, answer_at=HANDSHAKE_TIMEOUT_S + 2)
        result = manager._reopen_existing(existing, open_browser=True)
        self.assertEqual((result.reused, result.ui_url, result.phase), (True, "http://127.0.0.1:8765/", "engine_start"))
        self.assertEqual(list((self.state / "launches" / existing["launch_id"] / "open-requests").iterdir()), [])

    def test_reopen_without_an_answer_stops_after_the_window_and_starts_nothing(self) -> None:
        clock = Clock()
        manager, existing = self.reopen_fixture(clock, answer_at=None)
        start = clock.value
        with self.assertRaises(ProcessManagerError) as raised:
            manager._reopen_existing(existing, open_browser=True)
        self.assertEqual(raised.exception.code, "launcher_reopen_timeout")
        self.assertIn("within 60 seconds", str(raised.exception))
        self.assertTrue(60.0 <= clock.value - start < 61.0, clock.value - start)
        self.assertEqual(json.loads((self.state / "launcher.lock").read_text(encoding="utf-8")), existing)

    def test_live_owner_with_matching_identity_still_refuses(self) -> None:
        identity = {"executable": r"C:\TwinPulse\TwinPulse.exe", "creation_filetime": 1}
        original = self.lock(identity)
        manager = self.manager()
        with patch.object(pm, "_process_identity", return_value=identity):
            with self.assertRaises(ProcessManagerError) as raised:
                manager._acquire_lock()
        self.assertEqual(raised.exception.code, "launcher_already_running")
        self.assertEqual((self.state / "launcher.lock").read_bytes(), original)
        self.assertFalse((self.state / "stale-launch-records").exists())
        self.assertFalse(manager._lock_owned)

    def test_unverifiable_owner_identity_keeps_the_record(self) -> None:
        recorded = {"executable": r"C:\TwinPulse\TwinPulse.exe", "creation_filetime": 1}
        # Unknown now, the same start time under another path spelling, or a
        # malformed record: never proof of PID reuse, so the record is kept.
        for current, stored in ((None, recorded), ({"executable": r"\\?\C:\TwinPulse\TwinPulse.exe", "creation_filetime": 1}, recorded),
                                ({"executable": "x", "creation_filetime": 2}, "malformed")):
            with self.subTest(current=current, stored=stored):
                original = self.lock(stored)
                with patch.object(pm, "_process_identity", return_value=current):
                    with self.assertRaises(ProcessManagerError) as raised:
                        self.manager()._acquire_lock()
                self.assertEqual(raised.exception.code, "launcher_owner_identity_changed")
                self.assertEqual((self.state / "launcher.lock").read_bytes(), original)
                self.assertFalse((self.state / "stale-launch-records").exists())

    # j) python.bat runs through cmd.exe on Windows
    def test_batch_command_line_quotes_every_argument_when_a_path_holds_cmd_metacharacters(self) -> None:
        command = [r"C:\isaac\python.bat", "-B", r"C:\Users\kim&lee\AppData\Local\TwinPulse\scripts\host.py",
                   "--stop-file", r"C:\Users\kim^lee\launch\engine.stop", "--viewport-capture", "C:\\Users\\kim(1)|x\\"]
        self.assertEqual(pm._batch_command_line(command),
                         '"C:\\isaac\\python.bat" "-B" "C:\\Users\\kim&lee\\AppData\\Local\\TwinPulse\\scripts\\host.py" '
                         '"--stop-file" "C:\\Users\\kim^lee\\launch\\engine.stop" '
                         '"--viewport-capture" "C:\\Users\\kim(1)|x\\\\"')
        # Where subprocess quotes too (a space), both give the same MSVC argument.
        spaced = [r"C:\Program Files\isaac\python.bat", r"C:\Users\Kim & Lee\host.py", "C:\\Users\\Kim & Lee\\state\\"]
        self.assertEqual(pm._batch_command_line(spaced), subprocess.list2cmdline(spaced))
        for program in (r"C:\isaac\PYTHON.BAT", r"C:\isaac\run.Cmd"):
            with self.subTest(program=program):
                self.assertEqual(pm._batch_command_line([program, "a^b"]), f'"{program}" "a^b"')

    def test_batch_command_line_refuses_percent_quote_and_line_break_and_names_the_folder(self) -> None:
        for command, folder in (
                ([r"C:\isaac\python.bat", "-B", r"C:\Users\50%off\AppData\host.py"], r"C:\Users\50%off"),
                ([r"C:\isaac\python.bat", r"C:\Users\kim&lee\x", 'C:\\Users\\a"b\\host.py'], 'C:\\Users\\a"b'),
                ([r"C:\isaac\python.bat", "C:\\Users\\a\nb\\host.py"], r"C:\Users\a\nb"),
                ([r"C:\isaac%\python.bat", "-B"], r"C:\isaac%")):
            with self.subTest(command=command):
                with self.assertRaises(ProcessManagerError) as raised:
                    pm._batch_command_line(command)
                self.assertEqual((raised.exception.code, str(raised.exception)), (
                    "engine_path_unsupported", f"Isaac cannot start from {folder}: python.bat cannot pass a path with "
                    '" % or a line break. Use a Windows account or profile path without these characters.'))

    def test_batch_command_line_keeps_plain_and_non_batch_commands_as_lists(self) -> None:
        for command in ([r"C:\isaac\python.bat", "-B", r"C:\Users\kim\host.py", "C:\\Users\\kim\\"],
                        [r"C:\isaac\python.exe", r"C:\Users\kim&lee\host.py", "50%", 'a"b']):
            with self.subTest(command=command):
                result = pm._batch_command_line(command)
                self.assertIsInstance(result, list)
                self.assertEqual(result, command)

    def test_engine_spawn_command_is_one_quoted_line_on_windows_only(self) -> None:
        manager = self.manager(state_dir=self.root / "kim&lee" / "state")
        command = manager._engine_command()
        self.assertEqual(manager._engine_spawn_command(windows=False), command)
        self.assertEqual(manager._engine_spawn_command(windows=True), " ".join(f'"{part}"' for part in command))
        refused = self.manager(state_dir=self.root / "50%off" / "state")
        self.assertEqual(refused._engine_spawn_command(windows=False), refused._engine_command())
        with self.assertRaises(ProcessManagerError) as raised:
            refused._engine_spawn_command(windows=True)
        self.assertEqual(raised.exception.code, "engine_path_unsupported")
        self.assertIn(f"Isaac cannot start from {str(refused.engine_stop_file).split('50%off')[0]}50%off: ",
                      str(raised.exception))

    def test_start_gives_subprocess_the_quoted_engine_line_or_stops_before_the_engine(self) -> None:
        original = TwinPulseProcessManager._engine_spawn_command
        for folder, code in (("kim&lee", "engine_spawn_failed"), ("50%off", "engine_path_unsupported")):
            with self.subTest(folder=folder):
                manager = self.manager(state_dir=self.root / folder / "state")
                spawned: list[object] = []

                def spawn(command, **_kwargs):
                    spawned.append(command)
                    if len(spawned) == 1:
                        manager.ready_file.write_text(json.dumps({"base_url": "http://127.0.0.1:43123"}),
                                                      encoding="utf-8")
                        return FakeProcess(201)
                    raise OSError("engine command captured")

                manager._popen = spawn  # type: ignore[assignment]
                with patch.object(TwinPulseProcessManager, "_engine_spawn_command",
                                  lambda self: original(self, windows=True)):
                    with self.assertRaises(ProcessManagerError) as raised:
                        manager.start(open_browser=False)
                self.assertEqual(raised.exception.code, code)
                self.assertEqual(spawned[0], manager._backend_command())  # the backend list is unchanged
                if code == "engine_spawn_failed":
                    self.assertEqual(spawned[1:], [" ".join(f'"{part}"' for part in manager._engine_command())])
                else:
                    self.assertEqual(len(spawned), 1)  # no engine process was started


if __name__ == "__main__":
    unittest.main()
