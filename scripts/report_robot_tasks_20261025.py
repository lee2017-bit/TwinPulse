# SPDX-License-Identifier: Apache-2.0
"""Render local evidence as a report, never change the original verdicts."""
import html,json
from pathlib import Path
OUT=Path(__file__).resolve().parents[1]/'outputs/robot-task-20261025-01'
read=lambda p:json.loads(p.read_bytes());esc=lambda v:html.escape(str(v))
gate=read(OUT/'acceptance06.json');media=read(OUT/'media-checks03.json')
titles={'ui03':'이전 설치: 이동 측정·XY 복귀 (yaw 미복원)','compose01':'원 실패: 모델 복귀 누락을 앱이 잘못 완료 처리','compose02':'이전 설치: 같은 복합 명령 수정 후 성공',
    'survey04':'원 실패: 경계 waypoint 후 START_OR_GOAL_BLOCKED','survey05':'모델 survey 누락을 이동 전에 거절',
    'survey06':'동일 이동 측정 성공 / OFF 적용 관측 미분리','survey07':'최종 설치: 동일 출발 위치·동일 이동 측정·OFF 적용 관측','compose04':'최종 설치: 전진·회전·위치/방향 복귀·정지','cancel07':'최종 설치: 모델 응답 대기 중 Stop','cold04':'최종 설치: 재열기 후 자동 연결/실행 없음'}
rows=[]
for name,title in titles.items():
    c=read(OUT/name/'result.json');job=c.get('final_task') or c.get('cancelled') or c.get('planning_result') or (c.get('task_snapshots') or [{}])[-1].get('job') or {}
    measured=job.get('measured_coverage') or {}
    values=[title,c['status'],job.get('state','NO_TASK_RESUMED'),job.get('segments',0),f"{job.get('distance_m',0):.3f}",measured.get('observations',0)]
    rows.append('<tr>'+''.join('<td>'+esc(v)+'</td>' for v in values)+f'<td><a href="{name}/result.json">원문</a></td></tr>')
def video(name):
    v=next(v for v in media['videos'] if v['name']==name)
    return f'<h3>{esc(titles[name])}</h3><p>{v["duration_s"]:.3f}초. 실제 설치 Electron/Isaac 검수 녹화이며 완성 제출 영상·OS 커서·실물 카메라 영상이 아닙니다.</p><video controls preload="metadata" src="{name}/recording/app-screen.mp4"></video><p><a href="{name}/recording/app-screen.mp4">영상 파일</a> · <a href="{name}/result.json">명령·원 응답·단계</a></p>'
body=f'''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TwinPulse 공통 자연어 task 검증</title>
<style>body{{font:16px/1.7 system-ui,sans-serif;max-width:1100px;margin:36px auto;padding:0 22px;color:#1c2833}}h1{{line-height:1.3}}.notice{{background:#fff4d2;padding:18px;border-left:5px solid #bd8600}}table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{border:1px solid #dce3e8;padding:9px;vertical-align:top;text-align:left}}.table{{overflow:auto}}video,img{{width:100%;max-height:800px;background:#111}}code{{overflow-wrap:anywhere}}a{{color:#006578}}details{{margin:16px 0}}</style>
<h1>공통 자연어 로봇 작업 — SIM 검증</h1><p>2026-10-25 · 설치 <code>{esc(gate['build_id'])}</code> · <a href="acceptance06.json">최종 gate {gate['passed']}/{gate['total']}</a>: {esc(gate['status'])}</p>
<div class="notice"><strong>실물 방 전체 순회 준비 완료는 아닙니다.</strong> 새 실물 task는 현재 handoff·local-map/pose 계약 미구현으로 HELD입니다. 원 몸체 UNQUALIFIED·USD 정합/치수 미인증·whole-room coverage 미검증은 유지합니다. 이번 로봇 접속/구동은 0회입니다.</div>
<h2>무엇이 바뀌었나</h2><p>TwinPulse 채팅/Robot command → text-only configured Nemotron 계획 → 정확한 단계 Review → 별도 Run → 기존 유한 동작과 실제 관측 → 현재 기하 재계획 → 출발 위치/방향 복귀·Stop. 새 문장마다 Codex가 순회 함수를 추가하는 방식이 아닙니다. 지원 능력은 observe, move_relative, navigate, survey, return_to_start, stop입니다. 모델 생성 코드 실행·자동 연결/Prepare·자동 재시도는 없습니다.</p>
<p>명령을 입력한 뒤 Enter까지 3초 대기했으며 제출 후 입력창은 비워집니다. 모델 호출 동의와 실행 동의는 별개입니다. 실제 모델 응답을 사용했고 고정 응답·request interception·직접 제품 API 쓰기는 사용하지 않았습니다.</p>
<h2>같은 실패를 보존하고 재시험</h2><div class="table"><table><thead><tr><th>시험</th><th>검수</th><th>App 작업 상태</th><th>유한 동작</th><th>명령 거리(m)</th><th>관측</th><th>근거</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<p>거리와 복귀 오차는 ISAAC 기구학 값이며 실물 정밀도 증거가 아닙니다. 이전 ui03은 XY만 복귀했고 yaw는 복원하지 않았으므로 최종 자세 복귀 인수로 합치지 않습니다. 원 compose01의 잘못된 COMPLETED도 수정하거나 삭제하지 않았습니다.</p>
<h2>발견·수정한 핵심 문제</h2><ol><li>설명에는 복귀가 있지만 실제 step에 없던 모델 응답: 명시 요구 누락·return 뒤 이동·nonfinal Stop을 거절하고 실제 XY/yaw 복귀를 별도 검사합니다. 자연어 의미 전체를 보증하는 검사는 아닙니다.</li><li>여유 없는 접경 경로와 실제 yaw의 차이: 원 장면 별도 OpenUSD 재생에서도 거절을 재현했습니다. 실행 최소 30cm는 유지하고 계획에 2cm 여유를 더했으며, 직렬화된 실제 이동 구간과 위치/지도/다른 로봇의 상태를 발행 직전에 재확인합니다. pose 스냅·충돌 epsilon 완화는 하지 않았습니다.</li><li>survey를 고정 사각 순찰로 바꾼 모델 출력: 실행 전에 거절했습니다. 필수 capability 이름을 모델 입력에 명시했고 원 출력은 보존했습니다.</li></ol>
<p>Astra가 잠금/취소·늦은 child·Stop UNKNOWN·귀환 예산·경계 경로·다른 로봇의 이동 경합을 독립 대조했습니다. 원 실패 재생은 <a href="route-replay01/result.json">별도 OpenUSD 재생</a>이며 원 live map 캡처로 설명하지 않습니다. 최종 task는 map/scan·pose 원문을 해시와 함께 별도로 보존합니다.</p>
<p>survey07은 연결 상태의 OFF 적용·새 프레임·PNG를 확인했지만 원 DOM frame ID는 기록하지 않았습니다. <a href="off-dom02/result.json">off-dom02</a>는 모델0·이동0의 독립 센서 표시 시험으로, 자체 operation/ACK와 실제 DOM canvas·프레임·PNG의 ON 점→OFF 제거/몸체 유지를 확인했습니다. survey07의 연속 증거나 누락 기록의 소급 보완으로 합치지 않습니다. off-dom01의 frame ID 숫자/문자열 검수 오류도 보존했습니다.</p>
{video('survey07')}{video('compose04')}{video('cancel07')}
<h2>호출·검증·종료</h2><p>승인 슬롯 {gate['approved_slots']}, 소비 claim {gate['claimed_slots']}, ledger 예약 {gate['reserved_requests']}. 실제 사용량 응답 {gate['responses_with_usage']}건, 사용량 UNKNOWN {gate['unknown_usage_requests']}건, 확인 토큰 합계 {gate['known_total_tokens']}. 예약/UNKNOWN을 확인된 HTTP 응답이나 0비용으로 바꾸지 않습니다. 외부로는 텍스트·기능명·SIM/REAL 구분만 전송했습니다.</p>
<p><a href="focused-final04/result.json">Python150</a>·Web120·TypeScript/build는 보조 회귀입니다. 실제 실행 근거는 위 설치본 UI/Isaac 원문이며, 모든 소유 launch의 필수9개 로그(Kit 포함) 바이트·SHA와 두 root 자연 종료를 검사했습니다. 선택 liveness 파일 원문 부재는 원문 부재로 남기며 건강 증거로 사용하지 않습니다. 최종 App은 정상 종료했습니다.</p>
<p>검사기 acceptance01의 선택 파일 취급 오류, acceptance04의 LiDAR OFF 추가 zero-epoch 추적 누락, acceptance05의 survey06 OFF 적용 관측 미확인, startup07의 설치/Start 겹침 관찰 실패도 보존했습니다. 기록기를 보완하고 원 출발 위치·같은 명령의 전체 survey07을 다시 실행해 Stop·OFF ACK/새 epoch·연결 상태에서 OFF 프레임을 확인했습니다. 성공적인 후속 검사로 원 실패를 지우지 않습니다. 원 USD·사진·사용자 프로젝트/로봇 로그를 삭제하거나 GitHub에 업로드하지 않았습니다.</p>
<h2>남은 실제 목표</h2><p>실물 current local-map·pose epoch·Stop handoff 연결, 실제 센서/바퀴·독립 몸체 검증, 미정합/누락 장애물의 국소 수집과 귀환, 실제 방 전체 coverage는 아직 남았습니다. world 정합 오차만으로 수집을 막지 않는 방향은 유지하되, 유효한 국소 관측·충돌/제어/배터리 보호를 제거하지 않습니다.</p>
<p><a href="../../docs/analysis/TWINPULSE_COMMON_ROBOT_TASKS_2026-10-25.md">구현·한계·실행 방법</a> · <a href="media-checks03.json">영상 해시·decode/시각 검수</a> · <a href="acceptance01.json">원 검사 실패</a> · <a href="startup07-observer-error.json">시작 관찰기 원 실패</a></p></html>'''
(OUT/'report.html').write_text(body,encoding='utf-8')
print(OUT/'report.html')
