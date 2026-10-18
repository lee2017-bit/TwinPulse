# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Bind one explicit native-evidence run and one explicit regression run.

Produces a static, robot-free handoff page. Does not search for another PASS,
execute checks, open a network connection or confer physical readiness.
"""
import argparse
from datetime import datetime, timezone
import hashlib
from html import escape
import json
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/twinpulse_core/src"))
from twinpulse_core.native_scan import NativeScanBundle
from twinpulse_core.native_scan_quality import analyze_native_scan
from summarize_offline_rehearsal import collect as collect_regression
from rehearse_offline_app import native_source_hashes

STAGES = ["real_bootstrap_session", "actual_74_frame_bundle_imported_native_angles_preserved",
          "wrong_photo_rejected_both_original_hashes_and_jpeg_decode_passed",
          "server_computed_74_frame_quality_descriptive_only_unknown_clearance",
          "first_middle_last_frames_and_reflection_display_only",
          "export_roundtrip_all_original_beams_and_photo_bindings_equal",
          "unsupported_authority_field_rejected_old_evidence_unchanged",
          "mobile_no_horizontal_overflow_no_external_requests_no_engine_commands"]
SOURCE_FILES = ["packages/twinpulse_core/src/twinpulse_core/native_scan.py",
                "packages/twinpulse_core/src/twinpulse_core/native_scan_quality.py",
                "packages/twinpulse_app/src/twinpulse_app/native_scan_review.py",
                "packages/twinpulse_app/src/twinpulse_app/api.py",
                "apps/twinpulse-web/src/NativeScanReview.tsx", "apps/twinpulse-web/src/api.ts",
                "scripts/export_native_scan_bundle.py", "scripts/analyze_native_scan.py",
                "scripts/rehearse_offline_app.py", "apps/twinpulse-web/e2e/native-scan-real.mjs",
                "scripts/summarize_native_scan_hour.py", "apps/twinpulse-web/e2e/native-handoff-page.mjs"]


def read_bounded(root, path, maximum=8 * 1024 * 1024):
    target = path.resolve(strict=True)
    if not target.is_relative_to(root.resolve()):
        raise ValueError("evidence must stay within the repository")
    with target.open("rb") as handle:
        data = handle.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError("evidence exceeds budget")
    return data


def collect(repo, saved, native_run, regression_run):
    repo = repo.resolve(strict=True)
    for directory in (saved, native_run, regression_run):
        if not directory.resolve(strict=True).is_relative_to(repo):
            raise ValueError("explicit in-repository evidence directories required")
    evidence = []
    def read(path, maximum=8 * 1024 * 1024):
        data = read_bounded(repo, path, maximum)
        evidence.append({"path": path.resolve().relative_to(repo).as_posix(), "bytes": len(data),
                         "sha256": hashlib.sha256(data).hexdigest()})
        return data
    bundle = NativeScanBundle.from_text(read(saved / "native-scan-bundle.json").decode("utf-8"))
    quality = analyze_native_scan(bundle)
    recorded_quality = json.loads(read(saved / "native-quality.json", 200000))
    browser = json.loads(read(native_run / "browser-result.json", 64000))
    app = json.loads(read(native_run / "result.json", 64000))
    imported = NativeScanBundle.from_text(read(native_run / "native-scan-bundle.json").decode("utf-8"))
    exported = NativeScanBundle.from_text(read(native_run / "exported-native-scan-bundle.json").decode("utf-8"))
    regression = collect_regression(regression_run)
    read(regression_run / "regression/manifest.json", 200000)
    log_bytes = read(regression_run / "regression.log", 5 * 1024 * 1024)
    # Windows PowerShell 5 Tee-Object emits a UTF-16 BOM; pwsh emits UTF-8.
    log = log_bytes.decode("utf-16" if log_bytes.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig")
    python_counts = [int(n) for n in re.findall(r"(?m)^Ran (\d+) tests? in ", log)]
    web_counts = re.findall(r"Tests\s+(\d+) passed \(\d+\)", log)
    photos_ok = {p["role"] for p in bundle.to_dict()["photos"]} == {"room", "top_view"}
    for photo in bundle.to_dict()["photos"]:
        name = {"room": "room.jpg", "top_view": "top-view-window-up.jpg"}[photo["role"]]
        photos_ok &= hashlib.sha256(read(saved / name, 10 * 1024 * 1024)).hexdigest() == photo["sha256"]
    original_scan = repo / "artifacts/lidar-capture-20260927-1214"
    raw = read(original_scan / "lidar-20260927T031354Z-323c99a6/raw.bin", 512 * 1024)
    nodes = read(original_scan / "nodes.ndjson", 8 * 1024 * 1024)
    source = bundle.to_dict()["source"]
    screenshot_paths = []
    for name in ("native-photo-review-desktop.png", "native-photo-review-mobile.png"):
        data = read(native_run / name, 10 * 1024 * 1024)
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("browser screenshot is not a PNG")
        screenshot_paths.append((native_run / name).resolve().relative_to(repo).as_posix())
    checks = {
        "actual_saved_provenance": bundle.to_dict()["source"]["kind"] == "saved_sensor_recording",
        "native_import_export_identity": bundle.digest == imported.digest == exported.digest == browser.get("bundle_digest"),
        "quality_recomputed_exactly": quality == recorded_quality,
        "original_recording_hashes": hashlib.sha256(raw).hexdigest() == source["raw_sha256"]
            and hashlib.sha256(nodes).hexdigest() == source["nodes_sha256"],
        "original_photo_hashes": bool(photos_ok),
        "native_browser_eight_stages": browser.get("status") == "PASS" and browser.get("stages") == STAGES
            and app.get("browser_stages") == STAGES,
        "native_run_isolation": app.get("status") == "PASS" and app.get("active_project_changed") is False
            and app.get("data") == browser.get("data") == "saved_sensor_recording"
            and app.get("http") == browser.get("http") == "actual_local_backend"
            and all(app.get(key) == "NOT_RUN" for key in ("robot", "isaac", "provider_calls"))
            and browser.get("physical_validation") == "NOT_RUN"
            and all(type(browser.get(key)) is int and browser[key] == 0 for key in ("external_requests", "engine_commands", "page_errors")),
        "existing_synthetic_regression": regression["status"] == "PASS",
        "native_tested_source_and_build_unchanged": app.get("source_and_build_sha256") == native_source_hashes(),
        "regression_counts_present": len(python_counts) == 8 and len(web_counts) == 1
            and "TWINPULSE_VERIFY_RESULT=PASS" in log and not re.search(r"(?m)^FAILED \(", log),
    }
    for source in SOURCE_FILES:
        read(repo / source, 500000)
    return {"schema_version": "native-hour-handoff-1.0", "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": "OFFLINE_EVIDENCE_PASS" if all(checks.values()) else "EVIDENCE_CHECK_FAILED",
            "checks": checks, "bundle_digest": bundle.digest,
            "python_tests": sum(python_counts), "web_tests": int(web_counts[0]) if len(web_counts) == 1 else None,
            "quality": {key: quality[key] for key in ("frame_count", "sample_count", "excluded_count", "excluded_percent",
                "min_usable_per_frame", "max_usable_per_frame", "worst_return_gap_deg", "clearance")},
            "screenshots": screenshot_paths, "evidence": evidence,
            "robot_power": "OFF_USER_REPORTED_NOT_TELEMETRY", "physical_demo_ready": False,
            "motion_authorized": False, "physical_validation": "NOT_RUN",
            "unresolved": ["native/base/world alignment and handedness", "physical stopping qualification FAIL",
                           "active Twin / physical mission integration", "integrated physical demo"],
            "notice": "Native rehearsal records source/build hashes before and after execution; this summary rechecks those bytes. Hashes are not signatures or hardware verification. This is saved evidence, not fresh robot readiness."}


def render(summary):
    rows = "".join(f"<tr><td>{escape(name)}</td><td>{'PASS' if ok else 'FAIL'}</td></tr>" for name, ok in summary["checks"].items())
    quality = summary["quality"]
    return f'''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>TwinPulse · 저장 사진/스캔 작업 인수인계</title><style>
body{{font:16px/1.65 system-ui,sans-serif;background:#101b2d;color:#e2e8f0;margin:0}}main{{max-width:1040px;margin:auto;padding:28px}}
h1{{font-size:28px;line-height:1.35}}h2{{font-size:21px;margin-top:32px}}.notice{{padding:16px;border-left:4px solid #fb923c;background:#253047}}
.metrics{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}.metrics div{{background:#1c2b41;padding:16px;border-radius:10px}}strong{{color:#5eead4}}
table{{width:100%;border-collapse:collapse}}td{{padding:8px;border-bottom:1px solid #475569;overflow-wrap:anywhere}}td:last-child{{white-space:nowrap;width:60px}}
a{{color:#7dd3fc}}.screens{{display:grid;grid-template-columns:2fr 1fr;gap:16px}}figure{{margin:0}}img{{width:100%;max-height:620px;object-fit:contain;object-position:top;background:#07101b}}small{{overflow-wrap:anywhere}}
@media(max-width:650px){{main{{padding:16px}}.metrics,.screens{{grid-template-columns:1fr}}h1{{font-size:23px}}}}
</style><main><p>TWINPULSE / OFFLINE HANDOFF / 2026-09-27</p><h1>실제 사진과 스캔,<br>App 연결·검증 결과입니다.</h1>
<p class="notice">상태: <strong>{escape(summary['status'])}</strong><br>저장자료 검토와 소프트웨어 검사 결과입니다.
실물 주행·최종 데모 완료 판정은 아닙니다. 이번 작업에서 로봇 접속·센서·모터·유료 API를 사용하지 않았습니다.</p>
<div class="metrics"><div><strong>{quality['frame_count']}개 스캔</strong><br>{quality['sample_count']:,}개 원샘플 보존</div>
<div><strong>Python {summary['python_tests']} / Web {summary['web_tests']}</strong><br>회귀검사 + 제품 빌드</div>
<div><strong>검사 대상: App 8단계</strong><br>기존 합성 리허설은 별도9단계</div></div>
<h2>완료한 것</h2><ul><li>비균등 각도를 그대로 읽는 데이터 형식과 별도 App 검토 패널.</li>
<li>74개 스캔 선택, 원본 사진2장 해시 확인, 방향 후보 비교, 원형 내보내기.</li>
<li>프레임별 유효점·방향별 편차 통계. 제외 {quality['excluded_count']:,}개({quality['excluded_percent']:.2f}%).</li>
<li>다른 사진/잘못된 입력 거부, 활성 프로젝트 무변경, 모바일 화면 검증.</li></ul>
<h2>아직 해결되지 않은 것</h2><p>센서↔로봇↔세계 좌표와 좌우 방향, 실제 정지시험 FAIL,
active Twin/실물 임무 통합입니다. 사진위=창문은 확인했지만 로봇전방이라고 가정하지 않았습니다.
반사표시 후보는 실제 TF가 아니며, 라이다가 보지 못한 곳은 UNKNOWN입니다.</p>
<h2>복귀 후 다음 순서</h2><ol><li>이 페이지는 로봇을 켜지 않고 바로 볼 수 있습니다.</li>
<li>다음 실물 점검을 승인하면 기존 단일 진입점으로 현재 연결·배터리·토크·배포 상태를 한 번에 읽습니다.</li>
<li>그 결과에 따라 필요한 좌표/정지 확인만 진행합니다. 실제 이동 직전에만 별도 승인과 현장 확인을 받습니다.</li></ol>
<p><a href="../../docs/planning/TWINPULSE_NEXT_PHYSICAL_SESSION_2026-09-27.md">다음 실물 세션 상세</a> ·
<a href="../../docs/verification/native-scan-app-20260927.md">구현·검증 기록</a> · <a href="summary.json">파일 해시와 원본 증거</a></p>
<h2>실제 App 화면</h2><div class="screens"><figure><figcaption>데스크톱 · 클릭하면 원본 크기</figcaption>
<a href="desktop.png"><img src="desktop.png" alt="실제 저장 스캔과 원본 사진의 TwinPulse App 검토 화면"></a></figure>
<figure><figcaption>모바일 · 잘못된 입력 거부 검사 포함</figcaption><a href="mobile.png"><img src="mobile.png" alt="동일 App의 모바일 화면"></a></figure></div>
<h2>인수인계 증거 확인</h2><table>{rows}</table>
<p>모든 PASS는 위 오프라인 범위만 의미합니다. 첫 실패 기록도 보존했으며 다른 실행의 PASS로 덮어쓰지 않았습니다.</p>
<small>생성: {escape(summary['created_at_utc'])}<br>{escape(summary['notice'])}</small></main></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--saved", type=Path, required=True)
    parser.add_argument("--native-run", type=Path, required=True)
    parser.add_argument("--regression-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New directory directly under repository artifacts")
    args = parser.parse_args()
    if args.output.resolve().parent != ROOT / "artifacts":
        parser.error("output must be a new direct child of repository artifacts")
    summary = collect(ROOT, args.saved, args.native_run, args.regression_run)
    args.output.mkdir(parents=False, exist_ok=False)
    for source, name in zip(summary["screenshots"], ("desktop.png", "mobile.png")):
        shutil.copy2(ROOT / source, args.output / name)
    with (args.output / "summary.json").open("x", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, ensure_ascii=False, allow_nan=False)
    with (args.output / "index.html").open("x", encoding="utf-8") as handle:
        handle.write(render(summary))
    print(json.dumps({"status": summary["status"], "python_tests": summary["python_tests"], "web_tests": summary["web_tests"],
                      "physical_demo_ready": False, "output": str(args.output)}, ensure_ascii=False))
    return 0 if summary["status"] == "OFFLINE_EVIDENCE_PASS" else 1


if __name__ == "__main__": raise SystemExit(main())
