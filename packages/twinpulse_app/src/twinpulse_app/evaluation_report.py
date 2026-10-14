# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""A4 read-only, axis-separated evaluation of saved results.

This adapter consumes a validated comparison; it never turns estimated geometry,
synthetic duration, or unobserved collisions into physical success claims.
"""

from hashlib import sha256
import json
from pathlib import Path

from twinpulse_core.revisions import canonical_sha256

from .bedroom_rehearsal import compare_rehearsals
from .replay import MAX_REPLAY_REPORT_BYTES, load_replay_fixture


def evaluate_bedroom_comparison(comparison: dict) -> dict:
    if type(comparison) is not dict or comparison.get("schema") != "bedroom-route-comparison-1.0":
        raise ValueError("validated bedroom comparison required")
    try:
        candidates = comparison["candidates"]
        if type(candidates) is not list or len(candidates) != 2:
            raise ValueError("two comparison candidates required")
        checked = compare_rehearsals(candidates[0]["record"], candidates[1]["record"])
        if canonical_sha256(comparison) != canonical_sha256(checked):
            raise ValueError("comparison record differs from recomputed result")
    except (KeyError, TypeError, IndexError, OverflowError) as error:
        raise ValueError("invalid bedroom comparison record") from error

    results = []
    for candidate in checked["candidates"]:
        metrics = candidate["metrics"]
        results.append({
            "label": candidate["label"],
            "record_revision": candidate["record"]["revision"],
            "axes": {
                "scene_fidelity": {"status": "NOT_MEASURED", "basis": "photo_approximation_no_survey"},
                "simulation_quality": {"status": "NOT_RUN", "basis": "kinematic_rehearsal_not_isaac_physics"},
                "task_success": {"status": "PASS" if metrics["arrived"] else "FAIL",
                                 "basis": "synthetic_kinematic_only", "terminal_state": metrics["status"]},
                "latency": {"status": "NOT_MEASURED", "basis": "provider_or_wall_clock_latency_absent"},
                "cost": {"status": "UNKNOWN", "basis": "no_pricing_or_usage_receipt"},
                "tool_validity": {"status": "NOT_EVALUATED", "basis": "no_model_tool_plan_in_rehearsal"},
                "collision": {"status": "NOT_MEASURED", "source": "none", "count": None},
            },
            "synthetic_duration_s": metrics["duration_s"],
            "synthetic_distance_m": metrics["distance_m"],
        })
    body = {
        "schema_version": "adaptive-evaluation-1.0", "mode": "stored_synthetic_bedroom_comparison",
        "source_comparison_revision": checked["revision"],
        "conditions_revision": checked["conditions_revision"],
        "candidates": results,
        "eligible_for_efficiency_comparison": checked["eligible_for_efficiency_comparison"],
        "synthetic_b_minus_a": checked["b_minus_a"] if checked["eligible_for_efficiency_comparison"] else None,
        "overall_score": None, "source_verified": False, "physical_validation": "NOT_RUN",
        "motion_authorized": False,
    }
    return {**body, "revision": canonical_sha256(body)}


def evaluate_saved_provider_report(report_path: Path, manifest_path: Path) -> dict:
    """Recompile three historical photo plans; never infer image truth or paid usage."""
    report_path, manifest_path = Path(report_path), Path(manifest_path)
    if not 0 < report_path.stat().st_size <= MAX_REPLAY_REPORT_BYTES:
        raise ValueError("stored provider report size is invalid")
    if not 0 < manifest_path.stat().st_size <= 64 * 1024:
        raise ValueError("fixture manifest size is invalid")
    raw_report, raw_manifest = report_path.read_bytes(), manifest_path.read_bytes()
    report, manifest = json.loads(raw_report), json.loads(raw_manifest)
    if (type(report) is not dict or report.get("schema_version") != "1.0"
            or report.get("status") != "PASS" or type(report.get("fixtures")) is not list
            or type(manifest) is not dict or manifest.get("schema_version") != "1.0"
            or type(manifest.get("fixtures")) is not list
            or len(report["fixtures"]) != 3 or len(manifest["fixtures"]) != 3):
        raise ValueError("three-fixture saved provider report and manifest required")
    expected = manifest["fixtures"]
    if (any(type(item) is not dict for item in expected + report["fixtures"])
            or len({item.get("id") for item in expected}) != 3):
        raise ValueError("fixture manifest identities are invalid")
    results = []
    report_hash = sha256(raw_report).hexdigest()
    for fixture, saved in zip(expected, report["fixtures"], strict=True):
        if (saved.get("fixture_id") != fixture.get("id")
                or saved.get("image_filename") != fixture.get("local_filename")
                or saved.get("image_sha256") != fixture.get("sha256")
                or saved.get("prompt") != fixture.get("prompt")):
            raise ValueError("stored provider fixture differs from pinned manifest")
        checked = load_replay_fixture(report_path, fixture["id"])
        if checked.report_sha256 != report_hash:
            raise ValueError("stored provider report changed during validation")
        results.append({
            "fixture_id": checked.fixture_id,
            "image_sha256": checked.image_sha256,
            "plan_sha256": checked.plan_sha256,
            "bundle_sha256": checked.bundle_sha256,
            "tool_count": checked.tool_count,
            "object_count": checked.object_count,
            "axes": {
                "scene_fidelity": {"status": "NOT_MEASURED", "basis": "photo_has_no_surveyed_geometry_ground_truth"},
                "simulation_quality": {"status": "NOT_RUN", "basis": "stored_plan_validation_not_isaac_episode"},
                "task_success": {"status": "NOT_RUN", "basis": "stored_plan_validation_not_mission"},
                "latency": {"status": "NOT_MEASURED", "basis": "no_per_fixture_wall_clock_receipt"},
                "cost": {"status": "UNKNOWN", "basis": "no_pricing_or_usage_receipt"},
                "tool_validity": {"status": "PASS", "basis": "stored_plan_reparsed_and_bundle_recompiled_locally"},
                "collision": {"status": "NOT_MEASURED", "source": "none", "count": None},
            },
        })
    body = {
        "schema_version": "adaptive-evaluation-1.0", "mode": "stored_m2c_photo_plan_offline",
        "source_report_sha256": report_hash, "fixture_manifest_sha256": sha256(raw_manifest).hexdigest(),
        "data_partition": "historical_regression_not_held_out", "fixtures": results,
        "overall_score": None, "source_verified": False, "physical_validation": "NOT_RUN",
        "motion_authorized": False,
    }
    return {**body, "revision": canonical_sha256(body)}
