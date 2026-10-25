# SPDX-License-Identifier: Apache-2.0
"""Local projection of immutable acceptance records; never publishes or runs devices."""
import argparse
from hashlib import sha256
from html import escape
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--attempt', required=True)
    parser.add_argument('--roomplan-attempt', required=True)
    parser.add_argument('--reproduction-attempt', required=True)
    parser.add_argument('--supplementary', required=True)
    parser.add_argument('--media-checks', default='')
    args = parser.parse_args()
    root = args.output_root.resolve()
    a, r, b = args.attempt, args.roomplan_attempt, args.reproduction_attempt
    media_name = args.media_checks or f'media-checks{r}.json'
    if Path(media_name).name != media_name:
        raise ValueError('One explicit media evidence name required')
    if any(len(v) != 2 or not v.isascii() or not v.isdecimal() for v in (a, r, b)):
        raise ValueError('Two-digit attempts required')

    def read(name):
        p = root / name
        return json.loads(p.read_text(encoding='utf-8-sig')) if p.is_file() else {}

    def link(name, label=None):
        return f'<a href="{escape(name, quote=True)}">{escape(label or name)}</a>'

    base = read(f'gate-result{a}.json')
    room = read(f'roomplan-gate-result{r}.json')
    cycle = read(f'roomplan-saved-cycle{r}.json')
    visual_name = f'media-visual-review{r}.json'
    visual = read(visual_name)
    installed = read(f'installed-files{a}.json')
    raw_review = read(f'astra-raw-review{a}.json')
    raw_bound = (raw_review.get('status') == 'NO_ADDITIONAL_CONFIRMED_BLOCKER_IN_REVIEWED_CURRENT_SOFTWARE_EVIDENCE'
                 and raw_review.get('read_only') is True and raw_review.get('unresolved') == []
                 and raw_review.get('release_id') == installed.get('release_id')
                 and raw_review.get('source_sha256') == installed.get('source_manifest_sha256')
                 and bool(raw_review.get('reviewed_raw_sha256'))
                 and all((root/name).is_file() and sha256((root/name).read_bytes()).hexdigest() == digest
                         for name,digest in raw_review.get('reviewed_raw_sha256',{}).items()))
    visual_bound = (visual.get('status') == 'PASS_SCOPED_WITH_DOCUMENTED_CAPTURE_LIMITS'
                    and visual.get('release_id') == installed.get('release_id')
                    and visual.get('source_sha256') == installed.get('source_manifest_sha256')
                    and visual.get('media_checks') == dict(path=media_name,sha256=sha256((root/media_name).read_bytes()).hexdigest()))
    ready = (all(v.get('status') == 'READY_FOR_SUPERVISED_POWERED_TEST' and not v.get('issues') for v in (base, room))
             and cycle.get('status') == 'PASS' and not cycle.get('issues')
             and read(f'gate-additional-negatives{a}.json').get('status') == 'PASS'
             and read(f'roomplan-gate-negatives{r}.json').get('status') == 'PASS'
             and read(media_name).get('status') == 'PASS' and visual_bound and raw_bound)
    status = 'READY_FOR_SUPERVISED_POWERED_TEST' if ready else 'NOT_READY'
    names = [f'normal{a}/result.json', f'normal{a}-restart/result.json',
             f'ui-{a}/result.json', f'ui-cold-{a}/result.json',
             f'lineage-{a}/result.json', f'lineage-cold-{a}/result.json',
             f'ui-reproduction-{b}/result.json', f'{args.supplementary}/result.json',
             *[f'roomplan-{phase}-{r}/result.json' for phase in ('import', 'ai-edit', 'sim', 'cold')]]
    rows = []
    selected = set(names)
    for name in names:
        value = read(name)
        engine = value.get('versions', {}).get('engine', value.get('desktop', {}).get('engine', {}))
        rows.append('<tr><td>' + link(name) + '</td><td>' + escape(str(value.get('status', 'NOT_RUN'))) +
                    '</td><td>' + escape(str(value.get('release_id', engine.get('release_id', '')))) +
                    '</td><td>' + str(len([s for s in value.get('steps', []) if s.get('status') == 'PASS'])) + '</td></tr>')
    attempts = []
    for p in sorted(root.glob('*/result.json')):
        name = p.relative_to(root).as_posix()
        if name in selected:
            continue
        value = read(name)
        attempts.append('<li>' + link(name) + ': ' + escape(str(value.get('status', 'IN_PROGRESS'))) + '</li>')
    videos = []
    for name in names:
        value = read(name)
        video = value.get('video') or value.get('recording')
        if isinstance(video, dict) and isinstance(video.get('path'), str):
            p = root / Path(name).parent / video['path']
            if p.is_file() and p.resolve().is_relative_to(root):
                rel = p.relative_to(root).as_posix()
                videos.append('<li>' + link(rel) + f' · {p.stat().st_size:,} bytes · SHA256 <code>{sha256(p.read_bytes()).hexdigest()}</code></li>')
    budget = read(f'budget-final{a}.json')
    gate_links = [f'evidence-manifest{a}.json', f'gate-result{a}.json',
                  f'roomplan-evidence-manifest{r}.json', f'roomplan-gate-result{r}.json',
                  f'gate-additional-negatives{a}.json', f'roomplan-gate-negatives{r}.json',
                  f'astra-review{a}.json', f'roomplan-saved-cycle{r}.json', f'budget-final{a}.json', media_name, visual_name,
                  f'astra-native-boundary-review{a}.json', f'astra-raw-review{a}.json']
    gate_links += [f'gate-result{a}-independent.json', f'roomplan-gate-result{r}-independent.json',
                   f'final-local-state{a}.json', f'installed-files{a}-final.json']
    evidence = ''.join('<li>' + link(name) + '</li>' for name in gate_links)
    document = f'''<!doctype html><html lang="ko"><meta charset="utf-8"><title>TwinPulse 로봇 시험 준비</title>
<style>body{{max-width:1180px;margin:32px auto;padding:0 20px;font:16px/1.6 system-ui;color:#172a2d}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #cad8d7;padding:7px;text-align:left;overflow-wrap:anywhere}}code{{overflow-wrap:anywhere}}a{{color:#086f70}}h1{{font-size:25px}}h2{{margin-top:30px}}li{{margin:7px 0}}.state{{background:#e3f2ee;padding:15px}}</style>
<h1>TwinPulse · 감독된 로봇 시험 진입 준비</h1><p class="state">{status} · PC/SIM 소프트웨어 경로의 준비 판정이며 실물 성공 판정이 아닙니다.</p>
<p>현재 원문 게이트 두 개의 상태를 그대로 투영합니다. 보조시험·이전 설치의 성공·실패 뒤 이어하기로 전체 PASS를 만들지 않습니다. 로봇은 OFF이며 이번 준비에서 SSH·실제 센서·모터 명령은 실행하지 않았습니다.</p>
<h2>최종 선택 여정</h2><table><tr><th>원문</th><th>상태</th><th>설치</th><th>PASS 단계</th></tr>{''.join(rows)}</table>
<h2>판정·해시·독립 검토·비용</h2><ul>{evidence}</ul>
<p>원 RoomPlan의 30 mesh와 source SHA/객체 ID를 유지합니다. missing unit을 선택한 Meters는 <code>selected_for_sim</code> 미보정이며 실측 정확도가 아닙니다. 선택 Chair0 자연어 이동은 실제 설정 Nemotron 호출이고, 소파 목표 주행은 기존 bounded planner입니다. 모델이 매 제어 주기를 운전한다고 설명하지 않습니다.</p>
<p>과거 RoomPlan05의 expected Stop409는 정확히 2건이며, 각각 실제 입력 해제 뒤 Stop200·새 epoch·적용 ACK 결속으로만 분류했습니다. 현행 선택 여정의 응답은 위 원문에 별도 보존하며 삭제하거나 held 입력 실패를 예외로 처리하지 않습니다. 일반 Start/restart는 소유 supervisor의 인증 ready와 native AltF4 종료·PID 생성시각/port/lock 정리를 별도 확인합니다. 과거05 Windows 캡처는 두 차례 timeout이고 restart AX에 Home는 있으나 connected 상태는 확인되지 않았습니다. 선택한 새 여정의 native 관측은 각 normal 디렉터리 원문을 따릅니다. 일반 전체 native 입력 통과라고 주장하지 않습니다.</p>
<p>lineage-cold05의 원 engine-result 최상위 <code>FAIL</code>은 그대로입니다. 이 GET-only 이력 재열기는 Build/render를 실행하지 않아 applied_revision=null·capture=NOT_RUN·prim_count=0이며, 원 이력 보존 및 정상 종료 PASS와 별도입니다. 필수 보존 원문 SHA와 optional liveness <code>ORIGINAL_UNAVAILABLE</code>도 구분합니다.</p>
<h2>실제 화면 기록</h2><ul>{''.join(videos) or '<li>선택된 기록 없음</li>'}</ul>
<p>설치 Electron의 실제 renderer 기록입니다. 실제 pointer-event 커서 주석은 OS 커서·실물 촬영이 아니며 일반 전체 native 입력/Explorer/OS 붙여넣기/다른 PC 시험은 별도 NOT_RUN입니다. 인수용 resize·fault 화면을 제출 데모로 부르지 않습니다.</p>
<p>원 {link('media-checks12.json','영상검사12 FAIL')}도 보존했습니다. RoomPlan SIM의 원 두 frame시간126680ms/126681ms는 단조증가하지만 기본 null 출력25Hz가 둘을3167로 반올림해 경고를 냈습니다. {link('media-timebase-diagnosis12.json','원 packet/197개 decoded hash·동일원본 대조')} 후 원 timebase를 유지해 다시 검사했습니다. 입력PTS/DTS의 단조증가를 별도 강제하며 경고를 무시하거나 영상을 다시 찍어 원FAIL을 없애지 않았습니다. 최신 선택 검사와 시각검수는 별도이고 원영상 bytes는 그대로입니다.</p>
<p>{link(visual_name,'실제 첫·중간·끝 화면 시각검수')}에서 cold12 영상 마지막은 첫 현재렌더 직전까지 찍힌 한계를 확인했습니다. {link('roomplan-cold-12/02-cold-render.png','별도 원현재화면 Frame2')}에는 원RoomPlan·live5.8FPS가 보입니다. 실제 소프트웨어 표시 PASS와 모든 단계가 촬영됐다는 주장은 다르며, 그 PNG를 가짜시각으로 영상에 붙이거나 cold 클립을 완성된cold데모라고 부르지 않았습니다. 일반 restart12의 {link('normal12-restart/native-connected-observation.json','이후 실제 AX Home+connected/버튼활성화')}도 확인했지만 이전0:32정체의 원인/실제전이시각은UNKNOWN이고, 좌표도구 실패 때문에 전체 native포인터입력/화면캡처는 통과하지 않았습니다.</p>
<h2>보존된 다른 시도</h2><ul>{''.join(attempts)}</ul>
<p>후보02는 새 모델 schema의 라우터 누락으로 no-dispatch 실패했고 그 경계만 수정했습니다. 후보03의 static preview 교체409 wholeFAIL과 Undo 원응답 부족은 그대로 보존했습니다. 새 전체 clean 결과는 과거 race 제거·단일 원인 해결·무재발을 증명하지 않습니다. 센서/입력/출력 시간·속도·기하 안전 한도는 완화하지 않았습니다.</p>
<p>후보03의 다음 독립04는 실제 INPUT_STALE가 후속 Stop보다 먼저 발생한 제어 실패였습니다. 조회 hot-path를 좁게 보완했으며 {link('snapshot-cost-before04.json','원자료 격리 보조측정 전')}·{link('snapshot-cost-after05.json','보완 후')}은 원 abort의 단독 원인이나 설치 통과 증거가 아닙니다. 추가 범위의 approval/inference 보조26개는 {link('approval-extra-baseline03.log','수정 전03')}과 {link('approval-extra-source05.log','수정 후05')}에서 같은 구 observer-contract/호출수 fixture 5실패가 남았습니다. 이번 집중 회귀 통과를 전체 저장소/사진 품질 PASS라고 부르지 않습니다.</p>
<p>추가 원기하06은 stale wrapper 기본값이 다른 오래된 project를 골랐고21단계/60초 뒤 bed취소 전 경로가 거절돼 wholeFAIL·후반NOT_RUN입니다. {link('reproduction06-diagnosis.json','원FAIL·정확pose·저장 primitive/도출 gap·원로그')}를 보존했습니다. source-derived chair leg gap 약0.204762m가 기존 planner .25m 안이라는 계산은 실제 engine BBox 직접관측이 아닙니다. 정확한 최신33/58의 project/revision을 명시한 새07 전체는06의 성공 대체나 과거 원인 해결 증명이 아닙니다. 시작점 숨은 초기화·다른 목표·안전 한도 완화는 하지 않았습니다.</p>
<p>정확한 원기하07도21단계/60초 뒤 bed취소 전 같은 이유로 wholeFAIL입니다. {link('reproduction07-diagnosis.json','원07·도출 gap .240115m·두 operation')}는 이전 의자 도착 위치에서 앞선 수동조작 후 기존 planner 시작점 범위 안에 들어간 상황을 보존합니다. {link('reproduction09-start-preparation/predeclared.json','실행 전 고정한 위치 준비')}·{link('reproduction09-start-preparation/result.json','실제 UI 회전90°/전진40cm·자기 Stop/적용/정지/current frame')}·{link('cleanup-preparation09.json','별도 정상 종료')} 후 새 전체08을 처음부터 수행했습니다. 숨은 teleport나 pose 파일 수정, 실패 뒤 후반 이어붙이기는 없습니다. 중단된 준비 기록기08은 {link('reproduction08-start-preparation/aborted-recorder-native-exit.json','Stop observer 필드 오류 발견 뒤 own recorder 중단/실제 정상 창 종료')}로 별도 보존하며 성공으로 세지 않습니다.</p>
<p>전체08은 정상·명시 fault35단계 PASS 뒤 마지막 Stop 수집 경합으로 wholeFAIL이며 원문을 바꾸지 않았습니다. 실제 마지막 Stop200/revision8107·후행8118의 두 새epoch 적용이 있지만 기록기가 이전8104를 저장한 오류입니다. {link('stop-receipt-observer-fix.log','기록기 보조8개')}는 이전 정지 상태가 새 Stop을 승인하지 못함을 검사하며 제품코드·기준은 바꾸지 않았습니다. {link('reproduction10-start-preparation/predeclared.json','다음 고정 준비')}·{link('reproduction10-start-preparation/result.json','실제 right160°/forward40cm/Stop')}와 종료 뒤 새 전체{b}를 처음부터 수행한 결과를 선택했습니다. 원08을 사후 보충하거나 성공으로 승격하지 않았습니다.</p>
<p>그 뒤 전체11은16단계 PASS 뒤 상태파일 읽기 errno13 세 번→None→감독기 안전종료로 wholeFAIL입니다. 당시 broker heartbeat 신선도와 정확 Windows 충돌 주체는 UNKNOWN이며, fleet telemetry가 존재했다는 이유로 정상 heartbeat를 관측했다고 바꾸지 않습니다. {link('ui-reproduction-11/result.json','원11')}와 exact launch f3b68…의 원문을 보존했습니다. 감독기 reader만 Windows READ/WRITE/DELETE 공유·bounded read·정확 close로 보완했고 파일 취득 실패 메시지를 분리했습니다. {link('status-reader-tests03.log','실제 rename DELETE handle 경합/원 writer200발행·기존 probe29보조PASS')}는 공유 호환성을 검증할 뿐 원11의 단독 원인 해결·무재발 증거가 아닙니다. {link('status-reader-development-failures.json','초기 과도한 overwrite 기대와 CRT 오류기대 실패·raw 한계')}도 보존했습니다. writer·3시도·1MiB·3초freeze·None/physical unknown 즉시 실패·모든 제어 한도는 유지합니다.</p>
<p>선택된 원기하 전체{b}는 원11 종료 뒤 저장된 두 SIM pose를 그대로 사용합니다. {link(f'ui-reproduction-{b}/predeclared-start-pin.json','입력 전 고정한 old11 SHA/시작 pose')}와 현재 decoded frame/engine/stage·새 operation/connection·기존 신선도·XY0.001m/yaw0.001rad를 결속하며 숨은 pose 초기화/teleport/자동 탈출을 하지 않습니다. 동일 저장기하의 새 전체 재시험이지 과거 최초 pose의 정확 재현이나 실패 후반 이어붙이기가 아닙니다.</p>
<h2>전원을 켠 뒤 한 번의 현장 세션</h2><ol><li>같은 LAN·충전선 분리·현장 감독/즉시 차단 확인 → 실제 App에서 저장 로봇 선택, Check Connection.</li><li>PC 준비와 명시 Prepare → 원 source에 맞는 Pi 컴파일/loader/readback 확인. 기존 Pi ROS를 사용하며 새 PC SDK를 필수로 요구하지 않습니다.</li><li>이동 없이 boot·전압·odom·LiDAR 원문 수집/저장 → 실제 Pi 부하와 동시 처리 간격 확인.</li><li>원 안전 기준에서 낮은 속도의 전후/회전·입력 해제·Stop → odom과 정지 노이즈 대비 독립 LiDAR를 함께 분석. 인간에게 움직임을 반복 확인시키거나 바이트 변화만으로 성공 처리하지 않습니다.</li><li>통과한 같은 세션에서 90도·한바퀴 스캔·안전한 연속 조종·Stop/OFF·원 로그 반출/Disconnect. 실패 시 exact operation ID로 중단 사유와 출력 원문을 보존합니다.</li></ol>
<p>실제 Pi 부하/저장·제동/주행·RoomPlan과 odom의 세계 정합은 NOT_RUN입니다. 이 결과가 없다는 이유로 그 시험 자체를 순환 차단하지 않습니다. 정합 전에는 물리 'Go near sofa' 성공을 약속하지 않습니다. 사진-only 충실도·전체 CAD·공개 제출/새 Git 업로드 완료도 이번 준비 판정에 포함하지 않습니다.</p>
</html>'''
    target = root / 'report.html'
    with target.open('x', encoding='utf-8') as stream:
        stream.write(document)
    print(json.dumps(dict(status=status, report=str(target), budget_record_present=bool(budget))))


if __name__ == '__main__':
    main()
