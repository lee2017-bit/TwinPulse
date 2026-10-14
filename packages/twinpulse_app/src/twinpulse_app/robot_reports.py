# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Recorded diagnostics, never live telemetry or a physical command authority."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import re
from threading import RLock
from uuid import uuid4


def _timestamp(value):
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError("Robot report requires an explicit UTC observation time")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("Invalid robot observation time") from None
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError("Robot observation time must use UTC")
    return parsed


def _number(value, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError("Robot report contains an invalid measurement")
    return value


def _boolean(value):
    if type(value) is not bool:
        raise ValueError("Robot report contains an invalid boolean")
    return value


class RobotReports:
    """Session-local, bounded, sanitized saved-report review shared by CLI/API.

    Uploaded JSON is unverified evidence. Even a new timestamp or all-green
    checks cannot establish a live connection, current boot, or motion readiness.
    Raw command output, filesystem paths, and unknown fields are not retained.
    """

    def __init__(self, *, clock=lambda: datetime.now(timezone.utc)):
        self._clock = clock
        self._lock = RLock()
        self._record = None
        self._session_id = str(uuid4())

    def import_report(self, report):
        if not isinstance(report, dict):
            raise ValueError("Robot report must be a JSON object")
        try:
            encoded = json.dumps(report, allow_nan=False, sort_keys=True).encode()
        except (TypeError, ValueError):
            raise ValueError("Robot report must contain finite JSON values") from None
        if len(encoded) > 256 * 1024:
            raise ValueError("Robot report exceeds 256 KiB")
        if report.get("schema_version") == "robot-connection-1.0":
            if report.get("mode") != "read_only" or report.get("motion_authorized") is not False:
                raise ValueError("Only read-only diagnostic reports are supported")
            report = report.get("health")
        if not isinstance(report, dict) or report.get("schema_version") != "robot-health-1.0":
            raise ValueError("Expected a robot-health-1.0 report or connection report with health")
        if report.get("motion_authorized") is not False:
            raise ValueError("A diagnostic report cannot grant motion permission")
        observed = _timestamp(report.get("observed_at_utc"))
        now = self._clock()
        if observed > now:
            raise ValueError("Robot observation time is in the future; check device clocks")
        boot = report.get("boot_id")
        if not isinstance(boot, str) or not re.fullmatch(r"[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}", boot):
            raise ValueError("Robot report requires a boot ID")
        board = report.get("board")
        if not isinstance(board, dict) or board.get("status") not in {"OBSERVED", "UNKNOWN", "BUSY", "NOT_REQUESTED"}:
            raise ValueError("Invalid board report status")
        result = {"boot_id": boot, "observed_at_utc": observed.isoformat(),
                  "board_status": board["status"], "battery": None, "idle_at_observation": None,
                  "board_observation": None, "idle_failure_reasons": [],
                  "guard_artifact_verified_at_observation": _boolean(report.get("guard_artifact_verified")),
                  "release_id": None}
        if board["status"] == "OBSERVED":
            board_time = _timestamp(board.get("observed_at_utc"))
            # The health collector timestamps its start before doing the board read.
            if board_time > now or abs((board_time - observed).total_seconds()) > 120:
                raise ValueError("Board and health observation times do not match")
            volts = _number(board.get("voltage_v"), 3.5, 13.0)
            velocity = board.get("wheel_velocity_raw")
            if not isinstance(velocity, list) or len(velocity) != 2 or any(type(v) is not int for v in velocity):
                raise ValueError("Invalid wheel velocity observation")
            torque = _boolean(board.get("torque_enabled"))
            zero = _boolean(board.get("command_bytes_zero"))
            restored = _boolean(board.get("port_restored"))
            result["idle_at_observation"] = not torque and velocity == [0, 0] and zero and restored
            result["board_observation"] = {
                "observed_at_utc": board_time.isoformat(), "torque_enabled": torque,
                "wheel_velocity_raw": list(velocity), "command_bytes_zero": zero,
                "port_restored": restored,
            }
            result["idle_failure_reasons"] = [code for failed, code in (
                (torque, "TORQUE_ENABLED"), (velocity != [0, 0], "WHEEL_VELOCITY_NONZERO"),
                (not zero, "COMMAND_NONZERO"), (not restored, "PORT_RESTORE_UNCONFIRMED")) if failed]
            result["battery"] = {"voltage_v": volts,
                "estimated_percent": round(max(0, min(100, (volts - 10.5) / 1.8 * 100)), 1),
                "observed_at_utc": board_time.isoformat(), "capacity_measured": False,
                "charge_requested_at_observation": volts <= 10.86,
                "near_protection_at_observation": volts <= 11.1}
        deployment = report.get("deployment", {})
        if not isinstance(deployment, dict):
            raise ValueError("Invalid deployment observation")
        release = deployment.get("release_id")
        if release is not None:
            if not isinstance(release, str) or not re.fullmatch("[a-f0-9]{64}", release):
                raise ValueError("Invalid release identity")
            result["release_id"] = release
        result["report_sha256"] = hashlib.sha256(encoded).hexdigest()
        result["imported_at_utc"] = now.isoformat()
        with self._lock:
            self._record = result
            return self.snapshot()

    def snapshot(self):
        with self._lock:
            record = deepcopy(self._record)
        if record:
            record["age_seconds"] = max(0, round((self._clock() - _timestamp(record["observed_at_utc"])).total_seconds()))
        return {"schema_version": "robot-report-review-1.0", "session_id": self._session_id,
                "mode": "recorded_report", "source_verified": False,
                "connection": "NOT_CONNECTED", "current_robot_state": "UNKNOWN",
                "motion_authorized": False, "demo_ready": False, "record": record,
                "blockers": ["live_robot_session_not_connected", "physical_stop_qualification_incomplete",
                             "lidar_scan_and_stop_unverified", "scan_twin_navigation_integration_pending"],
                "notice": "Saved report only. No robot connection or movement. Measurements are historical, not current state."}
