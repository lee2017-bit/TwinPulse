# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""S1b finite viewport-capture lifecycle tests without Isaac or Kit imports."""

from __future__ import annotations

import os
import asyncio
import runpy
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import uuid
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from twinpulse_capture_contract import CaptureAttempt  # noqa: E402


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds

    def timestamp(self) -> str:
        return f"T+{self.value:.3f}"


def decode_fixture(path: Path) -> dict[str, object]:
    content = path.read_bytes()
    if content == b"complete":
        return {"status": "PASS", "bytes": len(content), "width": 960, "height": 640}
    if content == b"black":
        return {"status": "FAIL", "reason": "black_or_constant_frame"}
    raise ValueError("decoder saw a partial file")


class CaptureReadinessTests(unittest.IsolatedAsyncioTestCase):
    """Known local readiness stubs, not actual Isaac acceptance."""
    def host(self):
        with patch.object(sys,'argv',['host','--stop-file','unused-stop','--result-file','unused-result',
                                      '--viewport-capture','unused-image']):
            return runpy.run_path(str(ROOT/'scripts/twinpulse_engine_host.py'),run_name='capture_readiness_test')

    def modules(self, getter, update, capture):
        modules={name:ModuleType(name) for name in ('omni','omni.kit','omni.kit.app','omni.kit.viewport','omni.kit.viewport.utility')}
        modules['omni'].kit=modules['omni.kit']
        modules['omni.kit'].app=modules['omni.kit.app']
        modules['omni.kit'].viewport=modules['omni.kit.viewport']
        modules['omni.kit.viewport'].utility=modules['omni.kit.viewport.utility']
        modules['omni.kit.app'].get_app=lambda:SimpleNamespace(next_update_async=update)
        modules['omni.kit.viewport.utility'].get_active_viewport=getter
        modules['omni.kit.viewport.utility'].capture_viewport_to_file=capture
        return patch.dict(sys.modules,modules)

    async def test_capture_waits_for_late_viewport_without_resubmitting_capture(self):
        host=self.host();viewport=SimpleNamespace(resolution=None)
        getter=Mock(side_effect=[None,None,viewport]);update=AsyncMock()
        completion=AsyncMock();capture=Mock(return_value=SimpleNamespace(wait_for_result=completion))
        path=Mock();path.__str__=Mock(return_value='known-test-path');path.is_file.return_value=True
        path.stat.return_value=SimpleNamespace(st_size=64)
        with self.modules(getter,update,capture):
            self.assertTrue(await host['_capture'](path))
        self.assertEqual(getter.call_count,3);self.assertEqual(capture.call_count,1)
        self.assertEqual(update.await_count,3);completion.assert_awaited_once()

    async def test_missing_viewport_has_finite_wait_and_no_capture(self):
        host=self.host();getter=Mock(return_value=None);update=AsyncMock();capture=Mock()
        with self.modules(getter,update,capture):
            self.assertFalse(await host['_capture'](Path('unused'),ready_timeout_s=0.001))
        capture.assert_not_called()

    async def test_render_completion_does_not_require_writer_file_to_exist_yet(self):
        # Actual Kit wait_for_result can return before the async file writer.
        # CaptureAttempt owns the bounded file/stability/decode acceptance.
        host=self.host();viewport=SimpleNamespace(resolution=None)
        completion=AsyncMock();capture=Mock(return_value=SimpleNamespace(wait_for_result=completion))
        path=Mock();path.__str__=Mock(return_value='known-late-writer-path')
        path.is_file.return_value=False
        with self.modules(Mock(return_value=viewport),AsyncMock(),capture):
            self.assertTrue(await host['_capture'](path))
        capture.assert_called_once();completion.assert_awaited_once()
        path.is_file.assert_not_called()

    async def test_cancelled_readiness_never_creates_a_capture(self):
        host=self.host();entered=asyncio.Event()
        async def update():
            entered.set();await asyncio.Event().wait()
        capture=Mock()
        with self.modules(Mock(return_value=None),update,capture):
            task=asyncio.create_task(host['_capture'](Path('unused')))
            try:
                await asyncio.wait_for(entered.wait(),.1)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):await task
            finally:
                task.cancel()
        capture.assert_not_called()


class S1bCaptureContractTests(unittest.TestCase):
    def setUp(self) -> None:
        configured = os.environ.get("TWINPULSE_TEST_TMP")
        if configured:
            self.root = Path(configured) / f"s1b-{uuid.uuid4().hex}"
            self.root.mkdir(parents=True)
            self.temporary = None
        else:
            self.temporary = tempfile.TemporaryDirectory()
            self.root = Path(self.temporary.name)
        self.clock = FakeClock()

    def tearDown(self) -> None:
        if self.temporary is not None:
            self.temporary.cleanup()
        else:
            shutil.rmtree(self.root, ignore_errors=True)

    def attempt(self, number: int = 1, *, timeout_s: float = 2.0) -> CaptureAttempt:
        return CaptureAttempt(
            output_path=self.root / f"attempt-{number}.png",
            attempt=number,
            requested_frame=120,
            stage_epoch="stage-a",
            applied_revision="revision-a",
            camera="/OmniverseKit_Persp",
            timeout_s=timeout_s,
            settle_s=0.1,
            clock=self.clock,
            timestamp=self.clock.timestamp,
        )

    def settle(self, attempt: CaptureAttempt) -> dict[str, object]:
        attempt.poll("stage-a", "revision-a", decode_fixture)
        self.clock.advance(0.11)
        return attempt.poll("stage-a", "revision-a", decode_fixture)

    def test_task_may_return_before_late_file_becomes_stable_and_decodable(self) -> None:
        attempt = self.attempt()
        attempt.mark_task_returned(True)
        self.assertEqual(attempt.poll("stage-a", "revision-a", decode_fixture)["status"], "PENDING")
        self.clock.advance(0.4)
        attempt.output_path.write_bytes(b"complete")
        result = self.settle(attempt)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["phase"], "decoded")
        self.assertIsNotNone(result["timestamps"]["task_returned_at"])
        self.assertIsNotNone(result["timestamps"]["first_file_seen_at"])
        self.assertIsNotNone(result["timestamps"]["size_stable_at"])
        self.assertIsNotNone(result["timestamps"]["decoded_at"])

    def test_partial_file_decode_error_stays_pending_until_complete_bytes_arrive(self) -> None:
        attempt = self.attempt()
        attempt.mark_task_returned(True)
        attempt.output_path.write_bytes(b"part")
        pending = self.settle(attempt)
        self.assertEqual(pending["status"], "PENDING")
        self.assertEqual(pending["last_decoder_error"], "ValueError: decoder saw a partial file")
        attempt.output_path.write_bytes(b"complete")
        result = self.settle(attempt)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["decode_attempts"], 2)

    def test_empty_file_reaches_a_finite_timeout(self) -> None:
        attempt = self.attempt(timeout_s=0.5)
        attempt.mark_task_returned(True)
        attempt.output_path.touch()
        attempt.poll("stage-a", "revision-a", decode_fixture)
        self.clock.advance(0.51)
        result = attempt.poll("stage-a", "revision-a", decode_fixture)
        self.assertEqual(result["status"], "TIMEOUT")
        self.assertEqual(result["reason"], "empty_file_timeout")

    def test_black_frame_is_a_terminal_invalid_frame(self) -> None:
        attempt = self.attempt()
        attempt.mark_task_returned(True)
        attempt.output_path.write_bytes(b"black")
        result = self.settle(attempt)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["reason"], "black_or_constant_frame")

    def test_missing_viewport_is_reported_without_waiting_for_timeout(self) -> None:
        attempt = self.attempt()
        result = attempt.mark_task_returned(False, reason="viewport_missing")
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["phase"], "capture_unavailable")

    def test_capture_task_exception_is_preserved(self) -> None:
        attempt = self.attempt()
        result = attempt.mark_task_exception(RuntimeError("capture fixture exploded"))
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["reason"], "capture_task_exception")
        self.assertEqual(result["task_error"], "RuntimeError: capture fixture exploded")

    def test_never_completing_task_times_out_and_allows_only_one_retry(self) -> None:
        first = self.attempt(1, timeout_s=0.5)
        self.clock.advance(0.51)
        result = first.poll("stage-a", "revision-a", decode_fixture)
        self.assertEqual(result["status"], "TIMEOUT")
        self.assertEqual(result["reason"], "task_pending_timeout")
        self.assertTrue(first.retry_allowed(max_attempts=2))

        second = self.attempt(2, timeout_s=0.5)
        self.clock.advance(0.51)
        second.poll("stage-a", "revision-a", decode_fixture)
        self.assertFalse(second.retry_allowed(max_attempts=2))

    def test_stage_or_revision_change_aborts_without_retry(self) -> None:
        attempt = self.attempt()
        result = attempt.poll("stage-b", "revision-b", decode_fixture)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["reason"], "scene_revision_changed")
        self.assertFalse(attempt.retry_allowed(max_attempts=2))


if __name__ == "__main__":
    unittest.main()
