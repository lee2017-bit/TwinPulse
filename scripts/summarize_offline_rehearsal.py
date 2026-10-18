# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Summarize one isolated offline run, not the newest results from other runs.

This validates evidence structure and records byte hashes; it is not a signature,
a new test run, a robot health check, or permission to execute a mission.
"""
import argparse
from datetime import datetime, timezone
import hashlib
from html import escape
import json
from pathlib import Path

STAGES = (
    "real_bootstrap_session",
    "synthetic_health_import_historical_only",
    "actual_http_same_condition_comparison",
    "shorter_but_blocked_no_winner",
    "reviewed_scratch_apply_invalidates_map_mission_comparison",
    "explicit_map_mission_review_and_fresh_comparison",
    "real_download_inspection_record",
    "undo_geometry_not_old_approvals",
    "reload_session_recovery_mobile_no_active_project_operations",
)
APP_CHECKS = "PASS_R3_R4_R5_S2A_S2B_S2C_S2D_S3B_S3C_WIRING_CONTRACTS_REACT_BUILD_R6_PROCESS_MANAGER"
SOURCES = ("regression/manifest.json", "browser/result.json", "browser/browser-result.json")
IMAGES = (
    ("desktop-comparison.png", "Same-condition manual route comparison"),
    ("map-proposal-desktop.png", "Separate map and mission review"),
    ("map-proposal-mobile.png", "Map review on mobile"),
    ("map-overlay-review.png", "Conservative overlay applied in scratch only"),
    ("mobile-review.png", "Undo and reload on mobile"),
)
MAX_JSON_BYTES = 2_000_000


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _constant(_value):
    raise ValueError("non-finite JSON")


def _bytes(root, relative, limit):
    path = root / relative
    if not path.resolve().is_relative_to(root) or not path.is_file():
        raise ValueError("missing or outside-run evidence")
    with path.open("rb") as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise ValueError("oversized evidence")
    return data


def collect(run_dir):
    root = Path(run_dir).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("existing run directory required")
    documents, evidence, problems = {}, [], []
    for relative in SOURCES:
        try:
            data = _bytes(root, relative, MAX_JSON_BYTES)
            value = json.loads(data.decode("utf-8-sig"), object_pairs_hook=_pairs, parse_constant=_constant)
            if not isinstance(value, dict):
                raise ValueError("object required")
            documents[relative] = value
            evidence.append({"path": relative, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
        except (OSError, ValueError, UnicodeError, RecursionError):
            problems.append("missing_or_invalid:" + relative)

    regression = documents.get(SOURCES[0], {})
    app = documents.get(SOURCES[1], {})
    browser = documents.get(SOURCES[2], {})
    checks = {
        "regression_build": regression.get("status") == "PASS" and regression.get("app") == APP_CHECKS
            and regression.get("isaac") == "NOT_RUN",
        "local_app": app.get("schema_version") == "offline-app-rehearsal-1.0"
            and app.get("status") == "PASS" and app.get("data") == "synthetic"
            and app.get("http") == "actual_local_backend"
            and all(app.get(key) == "NOT_RUN" for key in ("robot", "isaac", "provider_calls"))
            and app.get("active_project_changed") is False,
        "browser": browser.get("status") == "PASS" and browser.get("data") == "synthetic"
            and browser.get("http") == "actual_local_backend" and browser.get("physical_validation") == "NOT_RUN"
            and all(type(browser.get(key)) is int and browser[key] == 0
                    for key in ("external_requests", "page_errors", "engine_commands")),
        "nine_stage_agreement": app.get("browser_stages") == list(STAGES) and browser.get("stages") == list(STAGES),
    }
    # The wrapper creates this exact new directory and passes it to the verifier.
    # Never glob for a latest PASS or accept a manifest from an unrelated run.
    try:
        checks["regression_directory_binding"] = Path(regression["artifact_dir"]).resolve() == root / "regression"
    except (KeyError, TypeError, ValueError, OSError):
        checks["regression_directory_binding"] = False

    screenshots = []
    for name, label in IMAGES:
        relative = "browser/" + name
        try:
            data = _bytes(root, relative, 10_000_000)
            if not data.startswith(b"\x89PNG\r\n\x1a\n"):
                raise ValueError("PNG required")
            screenshots.append({"path": relative, "label": label, "sha256": hashlib.sha256(data).hexdigest()})
        except (OSError, ValueError):
            problems.append("missing_or_invalid:" + relative)
    try:
        data = _bytes(root, "browser/browser-export.json", MAX_JSON_BYTES)
        exported = json.loads(data.decode("utf-8-sig"), object_pairs_hook=_pairs, parse_constant=_constant)
        checks["inspection_export"] = (isinstance(exported, dict)
            and exported.get("execution_authority") is False and exported.get("restore_supported") is False)
        evidence.append({"path": "browser/browser-export.json", "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
    except (OSError, ValueError, UnicodeError, RecursionError):
        checks["inspection_export"] = False
    problems.extend("check_failed:" + name for name, passed in checks.items() if not passed)
    return {
        "schema_version": "offline-rehearsal-summary-1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "FAIL" if problems else "PASS", "scope": "synthetic_offline_rehearsal_only",
        "checks": checks, "problems": problems, "evidence": evidence, "screenshots": screenshots,
        "physical_demo_ready": False, "motion_authorized": False, "current_robot_state": "UNKNOWN",
        "physical_validation": "NOT_RUN", "isaac_validation": "NOT_RUN",
        "provider_calls": "NOT_RUN", "expected_browser_stages": list(STAGES),
        "notice": "Recorded evidence checks only. Hashes identify these bytes, not signed provenance or current source freshness. No robot readiness is inferred.",
    }


def render_html(summary):
    rows = "".join(f"<tr><td>{escape(name)}</td><td>{'PASS' if passed else 'FAIL'}</td></tr>"
                   for name, passed in summary["checks"].items())
    problems = "".join(f"<li>{escape(value)}</li>" for value in summary["problems"])
    evidence = "".join(f'<li><a href="{escape(item["path"], quote=True)}">{escape(item["path"])}</a>'
                       f'<br><code>{item["sha256"]}</code></li>' for item in summary["evidence"])
    images = "".join(f'<figure><figcaption>{escape(item["label"])} — SYNTHETIC</figcaption>'
                     f'<a href="{item["path"]}"><img loading="lazy" src="{item["path"]}" alt="{escape(item["label"])}"></a></figure>'
                     for item in summary["screenshots"])
    return f'''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>TwinPulse offline evidence — {summary['status']}</title>
<style>body{{font:16px/1.6 system-ui,sans-serif;margin:24px auto;padding:0 20px;max-width:960px;color:#17283b;background:#f6f8fb}}h1{{line-height:1.2}}.notice{{padding:16px;background:#fff0cf;border:2px solid #aa7621;border-radius:8px}}table{{width:100%;border-collapse:collapse}}td{{border-bottom:1px solid #bcc8d5;padding:8px;overflow-wrap:anywhere}}code{{overflow-wrap:anywhere}}figure{{margin:24px 0;padding:12px;background:white;border:1px solid #ccd4df}}img{{max-width:100%;height:auto}}a{{color:#174d90}}small{{overflow-wrap:anywhere}}</style>
<h1>TwinPulse · Offline rehearsal {summary['status']}</h1>
<p>실물 데모 완료 판정이 아닌, 합성 자료를 사용한 로컬 앱 검증 결과입니다.</p>
<div class="notice"><strong>SYNTHETIC INPUTS · NO PHYSICAL APPROVAL</strong><br>
Robot state: UNKNOWN · Robot / Isaac / provider: NOT_RUN · Motion authorized: false.<br>
Battery values in screenshots are fixtures, not the current battery.
No live scan, SLAM, automatic optimization or active Twin promotion is proved here.</div>
<p><small>Summary generated: {escape(summary['created_at'])}</small></p>
<h2>Evidence checks</h2><table>{rows}</table><ul>{problems}</ul>
<p>PASS only covers this offline run. Missing, failed or inconsistent records do not count as PASS.
This page has no control buttons, scripts, remote resources or automatic refresh.</p>
<h2>What remains before a physical demo</h2>
<p>Confirm present power/charge status and authorize stationary checks; verify deployment and the physical trial adapter;
qualify stopping, real scan/TF and the Burger profile; validate active Twin and mission integration.
Obtain fresh operator presence and explicit approval immediately before any movement.
Existing physical FAIL results remain unresolved by this rehearsal.</p>
<h2>Recorded screens</h2>{images}<h2>Source records and byte hashes</h2><ul>{evidence}</ul>
<p>{escape(summary['notice'])}</p><p><a href="summary.json">Machine-readable summary</a> · <a href="regression.log">Regression log</a></p></html>'''


def write_summary(run_dir):
    root = Path(run_dir).resolve(strict=True)
    targets = [root / "summary.json", root / "summary.html"]
    if any(path.exists() for path in targets):
        raise FileExistsError("Existing summary preserved; use a new rehearsal run")
    summary = collect(root)
    contents = [json.dumps(summary, indent=2, allow_nan=False), render_html(summary)]
    for path, content in zip(targets, contents):
        with path.open("x", encoding="utf-8") as handle:
            handle.write(content)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    try:
        summary = write_summary(args.run_dir)
    except (OSError, ValueError):
        print("OFFLINE_SUMMARY=FAIL; existing evidence was not replaced")
        return 1
    print(f"OFFLINE_SUMMARY={summary['status']} page={args.run_dir / 'summary.html'}")
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
