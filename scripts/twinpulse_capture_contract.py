"""Pure, finite capture-attempt state machine shared by R6 tests and Isaac host."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Callable, Mapping


TERMINAL_STATUSES = frozenset({"PASS", "FAIL", "TIMEOUT", "DECODER_ERROR"})
RETRYABLE_REASONS = frozenset({
    "black_or_constant_frame",
    "capture_task_exception",
    "decoder_error",
    "empty_file_timeout",
    "file_missing_timeout",
    "file_unstable_timeout",
    "task_pending_timeout",
    "viewport_missing",
})


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CaptureAttempt:
    """Track one non-blocking viewport capture through stable decode or failure."""

    def __init__(
        self,
        *,
        output_path: Path,
        attempt: int,
        requested_frame: int,
        stage_epoch: str,
        applied_revision: str,
        camera: str,
        timeout_s: float = 15.0,
        settle_s: float = 0.25,
        clock: Callable[[], float] = time.monotonic,
        timestamp: Callable[[], str] = _utc_now,
    ) -> None:
        if attempt < 1 or timeout_s <= 0 or settle_s < 0:
            raise ValueError("capture attempt limits are invalid")
        if not stage_epoch or not applied_revision or not camera:
            raise ValueError("capture request identity is incomplete")
        self.output_path = output_path.resolve()
        self.attempt = int(attempt)
        self.requested_frame = int(requested_frame)
        self.stage_epoch = stage_epoch
        self.applied_revision = applied_revision
        self.camera = camera
        self.timeout_s = float(timeout_s)
        self.settle_s = float(settle_s)
        self._clock = clock
        self._timestamp = timestamp
        self._started = clock()
        self._status = "PENDING"
        self._phase = "task_pending"
        self._reason: str | None = None
        self._task_returned = False
        self._task_succeeded = False
        self._task_error: str | None = None
        self._file_seen = False
        self._last_signature: tuple[int, int] | None = None
        self._signature_since: float | None = None
        self._last_decoded_signature: tuple[int, int] | None = None
        self._last_decoder_error: str | None = None
        self._decode_attempts = 0
        self._decoded: dict[str, object] | None = None
        self._timestamps: dict[str, str | None] = {
            "requested_at": timestamp(),
            "task_returned_at": None,
            "first_file_seen_at": None,
            "size_stable_at": None,
            "decoded_at": None,
            "completed_at": None,
        }

    @property
    def terminal(self) -> bool:
        return self._status in TERMINAL_STATUSES

    def mark_task_returned(self, success: bool, *, reason: str | None = None) -> dict[str, object]:
        if self.terminal or self._task_returned:
            return self.public()
        self._task_returned = True
        self._task_succeeded = bool(success)
        self._timestamps["task_returned_at"] = self._timestamp()
        if success:
            self._phase = "file_pending"
        else:
            self._finish("FAIL", "capture_unavailable", reason or "viewport_missing")
        return self.public()

    def mark_task_exception(self, error: BaseException) -> dict[str, object]:
        if self.terminal:
            return self.public()
        self._task_returned = True
        self._task_succeeded = False
        self._task_error = f"{type(error).__name__}: {error}"[:500]
        self._timestamps["task_returned_at"] = self._timestamp()
        self._finish("FAIL", "capture_exception", "capture_task_exception")
        return self.public()

    def poll(
        self,
        current_stage_epoch: str | None,
        current_applied_revision: str | None,
        decoder: Callable[[Path], Mapping[str, object]],
    ) -> dict[str, object]:
        if self.terminal:
            return self.public()
        if (
            current_stage_epoch != self.stage_epoch
            or current_applied_revision != self.applied_revision
        ):
            self._finish("FAIL", "identity_changed", "scene_revision_changed")
            return self.public()

        now = self._clock()
        size = 0
        try:
            stat = self.output_path.stat()
            self._file_seen = True
            size = int(stat.st_size)
            if self._timestamps["first_file_seen_at"] is None:
                self._timestamps["first_file_seen_at"] = self._timestamp()
            signature = (size, int(stat.st_mtime_ns))
            if signature != self._last_signature:
                self._last_signature = signature
                self._signature_since = now
                self._timestamps["size_stable_at"] = None
                self._phase = "file_settling" if size > 0 else "empty_file"
            elif size > 0 and self._signature_since is not None and now - self._signature_since >= self.settle_s:
                if self._timestamps["size_stable_at"] is None:
                    self._timestamps["size_stable_at"] = self._timestamp()
                self._phase = "decode_pending"
                if self._task_returned and self._task_succeeded and signature != self._last_decoded_signature:
                    self._last_decoded_signature = signature
                    self._decode_attempts += 1
                    try:
                        decoded = dict(decoder(self.output_path))
                    except Exception as error:
                        self._last_decoder_error = f"{type(error).__name__}: {error}"[:500]
                        self._phase = "decoder_retry_pending"
                    else:
                        if decoded.get("status") == "PASS":
                            self._decoded = decoded
                            self._timestamps["decoded_at"] = self._timestamp()
                            self._finish("PASS", "decoded", None)
                            return self.public()
                        reason = str(decoded.get("reason") or "decoded_frame_invalid")[:240]
                        if reason == "black_or_constant_frame":
                            self._decoded = decoded
                            self._timestamps["decoded_at"] = self._timestamp()
                            self._finish("FAIL", "invalid_frame", reason)
                            return self.public()
                        self._last_decoder_error = reason
                        self._phase = "decoder_retry_pending"
        except FileNotFoundError:
            self._phase = "file_pending" if self._task_returned else "task_pending"
        except OSError as error:
            self._last_decoder_error = f"{type(error).__name__}: {error}"[:500]
            self._phase = "file_read_retry_pending"

        if now - self._started >= self.timeout_s:
            if self._last_decoder_error is not None:
                self._finish("DECODER_ERROR", "decoder_error", "decoder_error")
            elif self._file_seen and size == 0:
                self._finish("TIMEOUT", "timeout", "empty_file_timeout")
            elif not self._task_returned:
                self._finish("TIMEOUT", "timeout", "task_pending_timeout")
            elif not self._file_seen:
                self._finish("TIMEOUT", "timeout", "file_missing_timeout")
            else:
                self._finish("TIMEOUT", "timeout", "file_unstable_timeout")
        return self.public()

    def retry_allowed(self, *, max_attempts: int = 2) -> bool:
        return bool(
            self.terminal
            and self._status != "PASS"
            and self.attempt < max_attempts
            and self._reason in RETRYABLE_REASONS
        )

    def force_timeout(self, reason: str = "shutdown_capture_timeout") -> dict[str, object]:
        if not self.terminal:
            self._finish("TIMEOUT", "timeout", reason)
        return self.public()

    def public(self) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "status": self._status,
            "phase": self._phase,
            "reason": self._reason,
            "attempt": self.attempt,
            "output_path": str(self.output_path),
            "request": {
                "frame": self.requested_frame,
                "stage_epoch": self.stage_epoch,
                "applied_revision": self.applied_revision,
                "camera": self.camera,
                "timeout_s": self.timeout_s,
                "settle_s": self.settle_s,
            },
            "timestamps": dict(self._timestamps),
            "task_returned": self._task_returned,
            "task_succeeded": self._task_succeeded,
            "task_error": self._task_error,
            "file_seen": self._file_seen,
            "last_observed_bytes": self._last_signature[0] if self._last_signature else None,
            "decode_attempts": self._decode_attempts,
            "last_decoder_error": self._last_decoder_error,
            "decoded": dict(self._decoded) if self._decoded is not None else None,
        }

    def _finish(self, status: str, phase: str, reason: str | None) -> None:
        if self.terminal:
            return
        self._status = status
        self._phase = phase
        self._reason = reason
        self._timestamps["completed_at"] = self._timestamp()
