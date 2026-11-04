# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Launcher UI-host choice and error lines. Supplementary: no Windows, Electron, browser or Isaac runs here."""

from __future__ import annotations

import contextlib
import io
import os
from pathlib import Path
import runpy
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
for name in ("twinpulse_core", "twinpulse_provider", "twinpulse_app"):
    sys.path.insert(0, str(ROOT / "packages" / name / "src"))

from twinpulse_app.desktop_ui_host import DesktopUiHost  # noqa: E402

REAL = object()


class FakeManager:
    diagnostics_active = False
    requested_project_id = None

    def __init__(self, events: list, error: BaseException | None) -> None:
        self.events, self.error = events, error

    def start(self, *, open_browser: bool):
        self.events.append(("start", open_browser, getattr(self, "ui_host", None)))
        if self.error is not None:
            raise self.error
        return SimpleNamespace(launch_id="launch", ui_url="http://127.0.0.1:8765/",
                               backend_pid=10, engine_pid=11, stage_epoch="stage")

    def monitor(self) -> int:
        return 0

    def stop(self) -> None:
        self.events.append(("stop",))


class LauncherUiFallbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.main = staticmethod(runpy.run_path(str(ROOT / "scripts" / "twinpulse_launcher.py"))["main"])

    def setUp(self) -> None:
        self.temp = TemporaryDirectory(dir=ROOT / "artifacts" / "test-tmp")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.events: list = []
        self.created: list[dict] = []
        self.managers: list[FakeManager] = []

    def launch(self, *arguments: str, browser: object = None, desktop: bool = False,
               error: BaseException | None = None, manager: object = None, isaac: bool = True,
               overrides: dict | None = None) -> tuple[int, str, str]:
        def factory(**kwargs):
            self.created.append(kwargs)
            self.managers.append(FakeManager(self.events, error))
            return self.managers[-1]
        values = {"TwinPulseProcessManager": factory if manager is None else manager, **(overrides or {})}
        if browser is not REAL:
            values["_browser"] = lambda configured: browser
        argv = ["twinpulse_launcher.py", "--state-dir", str(self.base / "state")]
        if isaac:
            argv += ["--isaac-root", str(self.base / "isaac")]
        out, err = io.StringIO(), io.StringIO()
        with patch.dict(self.main.__globals__, values), \
                patch.object(DesktopUiHost, "available", return_value=desktop), \
                patch.object(DesktopUiHost, "close_after_stop", lambda host, owner: self.events.append(("close_after_stop",))), \
                patch.object(sys, "argv", argv + list(arguments)), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = self.main()
        return code, out.getvalue(), err.getvalue()

    def test_missing_desktop_host_falls_back_to_found_browser(self) -> None:
        browser = self.base / "msedge.exe"
        code, out, err = self.launch(browser=browser, desktop=False)
        self.assertEqual(code, 0)
        self.assertEqual([line for line in out.splitlines() if line.startswith("TWINPULSE_UI_HOST=")],
                         ["TWINPULSE_UI_HOST=browser reason=desktop_host_not_built"])
        self.assertNotIn("#bootstrap=", out + err)
        self.assertEqual(self.created[0]["browser_executable"], browser)
        self.assertFalse(hasattr(self.managers[0], "ui_host"))
        self.assertEqual(self.events, [("start", True, None), ("stop",)])

    def test_no_desktop_host_and_no_browser_fails_before_any_start(self) -> None:
        code, out, err = self.launch(browser=None, desktop=False)
        self.assertEqual(code, 1)
        self.assertRegex(err, r"\ATWINPULSE_LAUNCH_ERROR code=ui_host_unavailable message=\S")
        self.assertEqual(err.count("\n"), 1)
        self.assertNotIn("TWINPULSE_UI_HOST=", out)
        self.assertEqual((self.created, self.events), ([], []))

    def test_built_desktop_host_is_attached_without_notice(self) -> None:
        code, out, _err = self.launch(browser=None, desktop=True)
        self.assertEqual(code, 0)
        self.assertNotIn("TWINPULSE_UI_HOST=", out)
        self.assertEqual(self.events[0][:2], ("start", True))
        self.assertIsInstance(self.events[0][2], DesktopUiHost)
        self.assertEqual(self.events[1:], [("stop",), ("close_after_stop",)])

    def test_explicit_browser_choices_keep_their_previous_path(self) -> None:
        chrome = self.base / "chrome.exe"
        chrome.write_bytes(b"fixture")
        for arguments, browser, expected in ((("--ui-host", "browser"), None, None),
                                             (("--browser", str(chrome)), REAL, chrome)):
            with self.subTest(arguments=arguments):
                self.events.clear(); self.created.clear()
                code, out, _err = self.launch(*arguments, browser=browser, desktop=True)
                self.assertEqual(code, 0)
                self.assertNotIn("TWINPULSE_UI_HOST=", out)
                self.assertEqual(self.created[0]["browser_executable"], expected)
                self.assertEqual(self.events, [("start", True, None), ("stop",)])

    def test_missing_configured_browser_fails_loudly(self) -> None:
        code, _out, err = self.launch("--browser", str(self.base / "missing" / "chrome.exe"), browser=REAL, desktop=True)
        self.assertEqual(code, 1)
        self.assertRegex(err, r"\ATWINPULSE_LAUNCH_ERROR code=browser_missing message=\S")
        self.assertEqual((self.created, self.events), ([], []))

    def test_default_browser_search_covers_another_drive_and_per_user_edge(self) -> None:
        find = self.main.__globals__["_browser"]
        machine, user = self.base / "D" / "Program Files", self.base / "LocalAppData"
        edge = user / "Microsoft" / "Edge" / "Application" / "msedge.exe"
        chrome = machine / "Google" / "Chrome" / "Application" / "chrome.exe"
        real = Path.is_file
        # Only files in the temp folder count, so browsers installed on this machine cannot interfere.
        with patch.dict(os.environ, {"ProgramFiles": str(machine), "ProgramFiles(x86)": str(machine), "LOCALAPPDATA": str(user)}), \
                patch.object(Path, "is_file", lambda path: self.base in path.parents and real(path)):
            self.assertIsNone(find(None))
            edge.parent.mkdir(parents=True); edge.write_bytes(b"fixture")
            self.assertEqual(find(None), edge)
            chrome.parent.mkdir(parents=True); chrome.write_bytes(b"fixture")
            self.assertEqual(find(None), chrome)

    def test_default_ready_timeout_matches_the_600_second_cap(self) -> None:
        self.launch("--no-browser")
        self.launch("--no-browser", "--ready-timeout-s", "120")
        self.assertEqual([row["ready_timeout_s"] for row in self.created], [600.0, 120.0])

    def test_unexpected_start_error_is_one_line_plus_traceback_and_cleanup_runs(self) -> None:
        code, _out, err = self.launch(desktop=True, error=RuntimeError("boom\n" + "x" * 400))
        self.assertEqual(code, 1)
        first = err.splitlines()[0]
        self.assertTrue(first.startswith("TWINPULSE_LAUNCH_ERROR code=RuntimeError message=boom xxx"))
        self.assertEqual(len(first.split("message=", 1)[1]), 300)
        self.assertIn("Traceback (most recent call last)", err)
        self.assertEqual(self.events[1:], [("stop",), ("close_after_stop",)])

    def test_unexpected_error_text_never_carries_a_bootstrap_ticket(self) -> None:
        code, _out, err = self.launch("--no-browser", error=OSError("open http://127.0.0.1:8765/#bootstrap=Secret_Ticket-1 failed"))
        self.assertEqual(code, 1)
        self.assertNotIn("Secret_Ticket-1", err)
        self.assertIn("#bootstrap=[REDACTED]", err)

    def test_errors_outside_a_launch_attempt_are_reported(self) -> None:
        def broken(**_kwargs):
            raise OSError("settings disk unavailable")
        code, _out, err = self.launch("--no-browser", manager=broken)
        self.assertEqual(code, 1)
        self.assertTrue(err.startswith("TWINPULSE_LAUNCH_ERROR code=OSError message=settings disk unavailable\n"))
        self.assertIn("Traceback (most recent call last)", err)
        from twinpulse_app import TwinPulseProcessManager
        code, _out, err = self.launch("--no-browser", "--ready-timeout-s", "601", manager=TwinPulseProcessManager)
        self.assertEqual(code, 1)
        self.assertRegex(err, r"\ATWINPULSE_LAUNCH_ERROR code=ready_timeout_invalid message=\S")
        self.assertNotIn("Traceback", err)

    def test_bom_isaac_root_file_resolves_to_the_saved_folder(self) -> None:
        repo = self.base / "repo"
        saved = r"D:\isaacsim\isaac-sim-standalone-6.0.1-windows-x86_64"
        (repo / ".runtime").mkdir(parents=True)
        (repo / ".runtime" / "isaac-root.txt").write_bytes(b"\xef\xbb\xbf" + saved.encode("utf-8") + b"\r\n")
        code, _out, _err = self.launch("--no-browser", isaac=False, overrides={"ROOT": repo})
        self.assertEqual(code, 0)
        self.assertEqual(self.created[0]["isaac_python"], Path(saved) / "python.bat")


if __name__ == "__main__":
    unittest.main()
