# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Explicit evidence-bound offline handoff. No execution, network or live status.

Rechecks named runs only; never searches for a passing replacement. The native
Isaac result is historical, bound by recomputed USD bytes, not a new Isaac run.
"""
import argparse
from datetime import datetime, timezone
import hashlib
from html import escape
import json
from pathlib import Path
import re

from summarize_native_scan_hour import ROOT, read_bounded, STAGES as NATIVE_BASE
from summarize_offline_rehearsal import APP_CHECKS, _pairs, _constant
from rehearse_offline_app import native_source_hashes
from rehearse_derived_isaac import source_hashes as combined_source_hashes
from twinpulse_core.native_scan import NativeScanBundle
from twinpulse_core.native_scan_3d import export_native_frame_3d
from twinpulse_core.native_scan_quality import analyze_native_scan

COMBINED_STAGES = [
    'explicit_control_acquisition_does_not_build_or_acknowledge',
    'source_real_UI_ack_build_bridge_receipt_snapshot_confirmed',
    'derived_explicit_adoption_new_ack_real_build_UI_confirmation',
    'scene_only_real_engine_Run_disabled_no_motion_command',
    'explicit_restore_revokes_ack_without_engine_mutation',
    'mobile_no_overflow_exactly_two_builds_no_external_requests',
]
NATIVE_STAGES = NATIVE_BASE[:6] + ['selected_native_3d_download_hash_bound_no_display_reflection_or_world_tf'] + NATIVE_BASE[6:]
FAULT_CHECKS = ['failed_browser_state_read_discards_cached_engine_authority',
                'state_read_recovery_no_automatic_build',
                'real_lease_expiry_disables_build_no_automatic_acquisition',
                'never_settling_browser_read_times_out_no_extra_command',
                'post_timeout_recovery_no_automatic_build']


def collect(repo, combined, native, isaac, regression):
    repo = repo.resolve(strict=True)
    for folder in (combined, native, isaac, regression):
        if not folder.resolve(strict=True).is_relative_to(repo):
            raise ValueError('Evidence must remain in the repository')
    evidence = []
    def read(path, limit=10_000_000):
        data = read_bounded(repo, path, limit)
        evidence.append(dict(path=path.resolve().relative_to(repo).as_posix(), bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))
        return data
    def document(path):
        value = json.loads(read(path, 8_000_000).decode('utf-8-sig'), object_pairs_hook=_pairs, parse_constant=_constant)
        if not isinstance(value, dict): raise ValueError('Evidence object required')
        return value
    c, cb = document(combined/'result.json'), document(combined/'browser-result.json')
    n, nb = document(native/'result.json'), document(native/'browser-result.json')
    i, reg = document(isaac/'result.json'), document(regression/'manifest.json')
    log_bytes = read(regression.with_suffix('.log'))
    log = log_bytes.decode('utf-16' if log_bytes.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig')
    counts = [int(x) for x in re.findall(r'(?m)^Ran (\d+) tests? in ', log)]
    web = re.findall(r'Tests\s+(\d+) passed \((\d+)\)', log)
    bundle = NativeScanBundle.from_text(read(native/'native-scan-bundle.json').decode('utf-8'))
    exported = NativeScanBundle.from_text(read(native/'exported-native-scan-bundle.json').decode('utf-8'))
    quality = analyze_native_scan(bundle)
    data = bundle.to_dict()
    photos_ok = {p['role'] for p in data['photos']} == {'room', 'top_view'}
    for photo in data['photos']:
        name = {'room': 'room.jpg', 'top_view': 'top-view-window-up.jpg'}[photo['role']]
        photos_ok &= hashlib.sha256(read(native/name)).hexdigest() == photo['sha256']
    capture = repo/'artifacts/lidar-capture-20260927-1214'
    raw = read(capture/'lidar-20260927T031354Z-323c99a6/raw.bin')
    nodes = read(capture/'nodes.ndjson')
    frames = i.get('frames', [])
    frame_checks = []
    indices = sorted({0, len(data['frames'])//2, len(data['frames'])-1})
    for frame, index in zip(frames, indices):
        fresh = export_native_frame_3d(bundle, index)
        usd = read(isaac/f'native-frame-{index:03d}.usda')
        picture = read(isaac/f'frame-{index:03d}.png')
        frame_checks.append(frame.get('index') == index and frame.get('point_count') == fresh['point_count']
            and usd == fresh['usda'].encode('utf-8') and frame.get('export_sha256') == fresh['sha256']
            and picture.startswith(b'\x89PNG\r\n\x1a\n') and hashlib.sha256(picture).hexdigest() == frame.get('capture_sha256'))
    final = export_native_frame_3d(bundle, indices[-1])
    downloaded = read(native/f'exported-native-frame-{indices[-1]:03d}.usda')
    # Read and bind the observed final synthetic stage, never execute/import it.
    read(combined/'synthetic-derived-stage.usda')
    checks = {
        'combined_real_UI_bridge_Isaac_six_stages': c.get('status') == cb.get('status') == 'PASS'
            and c.get('checks') == cb.get('stages') == COMBINED_STAGES
            and c.get('boundary') == 'browser_API_broker_production_bridge_actual_Isaac'
            and c.get('data') == 'synthetic_test_fixture' and cb.get('data') == 'synthetic'
            and cb.get('commands') == ['build_site_scene', 'build_site_scene'],
        'combined_isolation_and_no_physical_claim': c.get('original_project_changed') is False
            and c.get('external_prim_preserved') is True and c.get('extension_UI_started') is False
            and all(type(c.get(k)) is int and c[k] == 0 for k in ('robot_connections', 'provider_calls'))
            and all(c.get(k) == 'NOT_RUN' for k in ('physics_run', 'physical_validation'))
            and all(type(cb.get(k)) is int and cb[k] == 0 for k in ('external_requests', 'page_errors')),
        'combined_current_code_build_binding': c.get('source_and_build_sha256') == combined_source_hashes(),
        'combined_browser_fault_and_actual_lease_expiry': c.get('failure_checks') == cb.get('failure_checks') == FAULT_CHECKS,
        'saved_native_actual_App_nine_stages': n.get('status') == nb.get('status') == 'PASS'
            and n.get('browser_stages') == nb.get('stages') == NATIVE_STAGES
            and n.get('data') == nb.get('data') == data['source']['kind'] == 'saved_sensor_recording'
            and n.get('http') == nb.get('http') == 'actual_local_backend'
            and n.get('active_project_changed') is False
            and all(n.get(k) == 'NOT_RUN' for k in ('robot', 'isaac', 'provider_calls'))
            and nb.get('physical_validation') == 'NOT_RUN'
            and all(type(nb.get(k)) is int and nb[k] == 0 for k in ('external_requests', 'engine_commands', 'page_errors')),
        'saved_native_current_code_build_binding': n.get('source_and_build_sha256') == native_source_hashes(),
        'source_photos_raw_nodes_and_bundle': bool(photos_ok) and bundle.digest == exported.digest == nb.get('bundle_digest')
            and hashlib.sha256(raw).hexdigest() == data['source']['raw_sha256']
            and hashlib.sha256(nodes).hexdigest() == data['source']['nodes_sha256'],
        'historical_actual_native_Isaac_three_frames_unchanged': i.get('status') == 'PASS'
            and i.get('kind') == 'actual_isaac_saved_evidence_import' and i.get('source_kind') == 'saved_sensor_recording'
            and i.get('bundle_digest') == bundle.digest and len(frames) == len(frame_checks) == 3 and all(frame_checks)
            and i.get('world_alignment') == 'UNVERIFIED' and i.get('motion_authorized') is False
            and all(i.get(k) == 'NOT_RUN' for k in ('physics_run', 'physical_validation'))
            and all(type(i.get(k)) is int and i[k] == 0 for k in ('robot_connections', 'provider_calls')),
        'current_native_download_matches_historical_Isaac_bytes': downloaded == final['usda'].encode('utf-8')
            and nb.get('native_3d_export') == {'sha256': final['sha256'], 'frame_index': indices[-1]}
            and i.get('app_download_sha256') == final['sha256'],
        'explicit_full_regression_and_counts': reg.get('status') == 'PASS' and reg.get('app') == APP_CHECKS
            and reg.get('isaac') == 'NOT_RUN' and Path(reg.get('artifact_dir', '')).resolve() == regression.resolve()
            and len(counts) == 8 and len(web) == 1 and web[0][0] == web[0][1]
            and 'TWINPULSE_VERIFY_RESULT=PASS' in log and not re.search(r'(?m)^FAILED \(', log),
    }
    images = [(native/'native-photo-review-desktop.png', 'native-app.png'),
              (isaac/f'frame-{indices[-1]:03d}.png', 'native-isaac.png'),
              (combined/'combined-desktop.png', 'synthetic-app.png')]
    for path, _ in images:
        if not read(path).startswith(b'\x89PNG\r\n\x1a\n'): raise ValueError('PNG evidence required')
    return dict(schema_version='four-hour-handoff-1.0', created_at_utc=datetime.now(timezone.utc).isoformat(),
        status='OFFLINE_EVIDENCE_PASS' if all(checks.values()) else 'EVIDENCE_CHECK_FAILED', checks=checks,
        python_tests=sum(counts), web_tests=int(web[0][0]) if len(web)==1 else None,
        bundle_digest=bundle.digest, quality=quality, evidence=evidence,
        image_sources=[{'path': p.resolve().relative_to(repo).as_posix(), 'copy_name': name} for p,name in images],
        robot_power='OFF_USER_REPORTED_NOT_TELEMETRY', physical_demo_ready=False, motion_authorized=False,
        live_battery='UNKNOWN_NOT_READ', physical_stop='FAIL_UNCHANGED', world_alignment='UNVERIFIED',
        notice='Static evidence check, not a new runtime run, hardware test, signature or execution approval. Native Isaac captures are historical; exported bytes were recomputed and compared. No latest-PASS search.')


def render(s):
    rows = ''.join(f'<tr><td>{escape(k)}</td><td>{"PASS" if v else "FAIL"}</td></tr>' for k,v in s['checks'].items())
    if s['status'] != 'OFFLINE_EVIDENCE_PASS':
        return f'<!doctype html><html lang="ko"><meta charset="utf-8"><title>증거 확인 실패</title><h1>EVIDENCE_CHECK_FAILED</h1><p>현재 파일과 검증 기록이 일치하지 않습니다. 완료 보고로 사용하지 마세요.</p><table>{rows}</table></html>'
    return f'''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>TwinPulse · 4시간 오프라인 준비 결과</title><style>
body{{margin:0;background:#101b2d;color:#e2e8f0;font:16px/1.7 system-ui,sans-serif}}main{{max-width:1000px;margin:auto;padding:28px}}
h1{{line-height:1.3}}h2{{margin-top:32px}}a,strong{{color:#5eead4}}.notice{{padding:18px;background:#253047;border-left:4px solid #fb923c}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}figure{{margin:0}}img{{width:100%;max-height:520px;object-fit:contain;background:#07101b}}
table{{width:100%;border-collapse:collapse}}td{{padding:10px;border-bottom:1px solid #475569;overflow-wrap:anywhere}}td:last-child{{width:70px}}
code,small{{overflow-wrap:anywhere}}@media(max-width:650px){{main{{padding:16px}}.grid{{grid-template-columns:1fr}}h1{{font-size:25px}}}}
</style><main><p>TWINPULSE / 2026-09-27 / OFFLINE PREPARATION</p>
<h1>로봇을 켜지 않고<br>확인할 수 있는 준비 결과</h1>
<p class="notice"><strong>{escape(s['status'])}</strong><br>저장자료·합성 장면·실제 Isaac 검증을 구분했습니다.
전체 실물 데모 완료가 아닙니다. 새 로봇 접속·주행·배터리 조회는 없었습니다.</p>
<p>제품 회귀: <strong>Python {s['python_tests']} / Web {s['web_tests']} + 빌드</strong>.
실제 App→Isaac 합성6단계, 저장 실스캔 App9단계 통과 기록을 현재 코드와 대조했습니다.</p>
<h2>1. 실제 저장 스캔 → 검토용 3D</h2>
<p>{s['quality']['frame_count']}개 스캔, {s['quality']['sample_count']:,}개 원샘플과 사진2장을 보존합니다. 원본·내보내기·코드 해시를 재확인했습니다.
Isaac의 점들은 센서 좌표의 증거층이며, 방의 지도·바닥·충돌물체 또는 검증된 세계 좌표가 아닙니다.</p>
<div class="grid"><figure><figcaption>저장 실자료 · 최신 App 검토</figcaption><a href="native-app.png"><img src="native-app.png" alt="실제 저장 스캔 App 검토"></a></figure>
<figure><figcaption>저장 실자료 · 앞서 검증한 Isaac 프레임73 (이번에 재실행하지 않음)</figcaption><a href="native-isaac.png"><img src="native-isaac.png" alt="센서 원본축의 실제 Isaac 점군 표시"></a></figure></div>
<h2>2. 합성 보정본 → 실제 App → Isaac</h2>
<p>원본을 보존한 별도 보정본 선택 → 새 검토 승인 → 장면 적용 → 완료 표시를 단일 경로로 통과했습니다.
처음 적용 시 제어권을 얻지 못하던 문제도 수정했습니다. <strong>주행 명령은 보내지 않았습니다.</strong></p>
<p>추가 실패검사5항목: 브라우저 조회 실패·무응답3초 제한, 복구 시 자동 명령 없음,
실제 제어권 만료 시 적용 차단·자동 재획득 없음. Isaac 프로세스 고장이나 실물 정지를 검증했다는 뜻은 아닙니다.</p>
<figure><figcaption>합성 벽 위치 보정 실험 · 사용자의 방을 복원한 결과가 아님</figcaption><a href="synthetic-app.png"><img src="synthetic-app.png" alt="합성 파생장면의 실제 Isaac 적용 확인"></a></figure>
<h2>지금 재현할 수 있는 범위</h2><ol><li>이 페이지와 저장 스캔 검토는 로봇 전원 없이 가능합니다.</li>
<li>Isaac 장면 검토에서는 필요시 <code>Acquire scene control</code> → 검토 체크 → <code>Build scene geometry in Isaac</code> 순서입니다.</li>
<li>제어권 요청은 장면 적용이나 주행이 아닙니다. 보정본 채택·복원 후에는 새 검토 승인이 필요합니다.</li></ol>
<p><a href="../../docs/verification/derived-review-combined-20260927.md">통합 검사 재현 명령·실패 이력</a> ·
<a href="../../docs/verification/native-scan-3d-registration-20260927.md">실스캔 3D의 검증 범위</a></p>
<h2>실물 데모까지 남은 일</h2><ul><li>센서↔로봇↔세계 좌표와 좌우 방향의 독립 근거. 사진위=창문은 로봇전방 또는 TF가 아닙니다.</li>
<li>기존 정지 안정시간 FAIL 해결과 재검증. 합격 기준을 낮추지 않았습니다.</li>
<li>실제 Burger 로봇 모델·임무·상태/정지 조건을 묶은 통합 주행 검증.</li></ul>
<p class="notice">현재 배터리: UNKNOWN. 과거 잔량을 현재 값으로 쓰지 않습니다.
라이다가 보지 못한 케이블·단차·사각 영역 역시 UNKNOWN입니다.</p>
<h2>복귀 후 최소 순서</h2><p>먼저 이 자료를 확인하고, 새 실물 점검 승인 후 한 번의 읽기 점검으로 연결·배터리·토크·배포 상태를 묶어 확인합니다.
그 결과에 필요한 좌표·정지 확인만 준비합니다. 이동은 실행 준비가 끝난 후 별도 승인과 현장 확인을 받고 진행합니다.</p>
<p><a href="../../docs/planning/TWINPULSE_NEXT_PHYSICAL_SESSION_2026-09-27.md">다음 실물 세션 상세</a> ·
<a href="summary.json">검사 결과·파일 해시</a></p>
<h2>이 페이지의 증거 점검</h2><table>{rows}</table>
<p>PASS는 명시된 오프라인 범위에만 해당합니다. 첫 실패 기록과 이전 결과는 덮어쓰지 않았습니다.</p>
<small>생성 UTC: {escape(s['created_at_utc'])}<br>{escape(s['notice'])}</small></main></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('combined', 'native', 'isaac', 'regression', 'output'): parser.add_argument('--'+name, required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.parent != ROOT/'artifacts': parser.error('New direct artifact child required')
    s = collect(ROOT, args.combined, args.native, args.isaac, args.regression)
    s['generator_and_QA_sha256'] = {name: hashlib.sha256(read_bounded(ROOT, ROOT/name)).hexdigest() for name in (
        'scripts/summarize_four_hour_prep.py', 'tests/integration/test_four_hour_summary.py',
        'apps/twinpulse-web/e2e/native-handoff-page.mjs')}
    output.mkdir(exist_ok=False)
    for item in s['image_sources']:
        with (output/item['copy_name']).open('xb') as target:
            target.write(read_bounded(ROOT, ROOT/item['path'], 10_000_000))
    (output/'summary.json').write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding='utf-8')
    (output/'index.html').write_text(render(s), encoding='utf-8')
    print(json.dumps({'status': s['status'], 'checks': s['checks'], 'physical_demo_ready': False}))
    return 0 if s['status'] == 'OFFLINE_EVIDENCE_PASS' else 1


if __name__ == '__main__': raise SystemExit(main())
