"""S1b finite viewport-capture lifecycle tests without Isaac or Kit imports."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import uuid


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
