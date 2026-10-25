# SPDX-License-Identifier: Apache-2.0
"""Local evidence index; never upgrades a failed gate or hardware outcome."""
import argparse,html,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/environment-task-loop-20261025-01'
p=argparse.ArgumentParser();p.add_argument('--attempt',required=True);args=p.parse_args()
if len(args.attempt)!=2 or not args.attempt.isdecimal():raise ValueError('TWO_DIGIT_ATTEMPT_REQUIRED')
gate=json.loads((OUT/f'acceptance{args.attempt}.json').read_bytes())
e=lambda v:html.escape(str(v));rows=[]
for role,proof in gate['roles'].items():
    relative=Path(proof['path']).relative_to(OUT.relative_to(ROOT))
    rows.append(f'<tr><td>{e(role)}</td><td><a href="{relative.as_posix()}">{e(relative)}</a></td><td><code>{e(proof["sha256"])}</code></td></tr>')
videos=[]
for run,label in [('hybrid16','원 수집→사진 basket 연결→Apply/Undo (환경 소스16)'),('survey18','최종 소스18 이동 수집·복귀'),('session18','현재 센서와 로봇 표시·회전·OFF'),('compose18','복합 자연어 명령'),('cancel18','모델 응답 중 Stop'),('open19','독립 cold 재시작')]:
    videos.append(f'<h3>{e(label)}</h3><video controls preload="metadata" src="{run}/recording/app-screen.mp4"></video>')
body=f'''<!doctype html><html lang="ko"><meta charset="utf-8"><title>TwinPulse · 현장시험 준비</title>
<style>body{{font:16px/1.65 system-ui;max-width:1150px;margin:36px auto;padding:0 24px;color:#172b35;background:#f7faf9}}h1,h2{{line-height:1.3}}section{{background:white;border:1px solid #d6e5df;border-radius:12px;padding:22px;margin:20px 0}}video{{width:100%;max-height:650px;background:#10191d}}table{{border-collapse:collapse;width:100%;font-size:13px}}td,th{{text-align:left;border-bottom:1px solid #ddd;padding:8px;overflow-wrap:anywhere}}code{{font-size:12px}}.warn{{color:#8b3b00}}a{{color:#006f70}}</style>
<h1>TwinPulse — 현장시험 준비 검수</h1><p><b>{e(gate['status'])}</b> · gate {gate['passed']}/{gate['total']} · <a href="acceptance{args.attempt}.json">원 판정</a></p>
<section><h2>실제 확인한 범위</h2><p>원 RoomPlan USD·30개 메시 보존 → 여러 위치의 실제 SIM 관측 → 고정 구조 정합·잔차 XY 후보 → 실제 사진 모델의 종류 후보와 명시 연결 → 공통 Preview/Apply·Undo·재적용 → 변경된 장면에서 새 자연어 계획·이동 수집·복귀·정지 → 현재 센서 표시·취소·cold 재시작.</p>
<p>설치 {e(gate['release_id'])}, Python574/Web1234 및 receiver114 검사는 보조 근거다. 환경 소스16과 최종 소스18의 3파일 차이를 전체 source manifest로 검사했다. 환경의 실제 사진/Apply 영상을 소스18 실행으로 바꿔 부르지 않는다.</p>
<p>추가 모델 승인50회 중 {gate['calls']['reserved']}회 사용/예약(실패·취소도 포함), {gate['calls']['remaining']}회 미사용. 실물 접속·이동·새 SDK/시스템 변경·삭제·GitHub 업로드는0.</p></section>
<section><h2>다음 현장시험</h2><ol><li>새로 로봇 ON·충전선 분리·현장 감독·즉시 차단 가능을 확인한다. 잠든 동안 무인 접속하지 않는다.</li>
<li>Start-TwinPulse-Test.cmd → 기존 거실 프로젝트 → 실물 등록 선택 → Connect / Prepare / LiDAR ON. 전압·정지 센서 baseline·명시 Arm·bootstrap Stop readback을 확인한다.</li>
<li>Robot command/채팅에서 이동 측정·복귀·정지와 거리/시간 예산을 요청한다. 모델이 제안한 정확한 계획을 검토한 뒤 Run task를 누른다. 한 문장마다 코드를 새로 만들지 않는다. Arm 잔여시간은 계획 전체 예산 이상이어야 한다.</li>
<li>처음에는 짧은 bounded 수집·귀환을 확인하고, 원 command/native ring/wheel/Stop·저장 지연을 기록한다. USD 정합 부재만으로 로컬 수집을 중단하지 않는다. 실제 충돌·불완전 센서·저전압·Stop/기록 실패는 차단한다.</li>
<li>수집 후 Import space → Collected survey에서 Task를 선택한다. 같은 벽 span 실측·초기 pose·센서 높이/TF를 확인하고 Check survey → 명시 Show / Use session alignment를 검토한다. 의미상 가구 목적지 이동은 현재 등록이 필요하다. 누락 후보는 사진 종류·높이를 검토하고 Preview/Apply한다.</li>
<li>Stop / LiDAR OFF / Disconnect / 정상 Exit까지 확인하고 원 로그를 보존한다.</li></ol></section>
<section class="warn"><h2>현장에서만 판정할 것</h2><p>실물 주행·차체/제동·세계 좌표 정합은 NOT_RUN/UNQUALIFIED다. 이전 physical POOR_FIT와 wheel/LiDAR 불일치를 SIM 성공으로 지우지 않는다. 입력 USD에 authored metersPerUnit이 없어 선택 metres는 실측이 아니다. 실제 벽 길이·초기 방향·센서 TF 확인이 필요하다.</p>
<p>회전 한 번/이동했다고 자동으로 세계 정합이 보장되거나 방 전체를 완주하는 것은 아니다. 도달 가능 공간만 수집하며 현재 결과는 PARTIAL/whole-room=false다. 사진은 종류·이미지 영역 후보이지 metric 위치·높이 측정이 아니다. 현재 정합의 기준·검증 실패를 자동 적용하지 않는다.</p>
<p>SIM에서 원문 저장 후 최신 snapshot 1회 재조회로 자기 만료를 보완했다. physical native 신선도·출력 보호는 그대로이며 느린 실제 저장장치에서 중단 가능성은 첫 현장시험의 확인 항목이다. 수동조종은 동결. 복잡한 부정·모호 문장의 상대 이동 의미는 완전 보장하지 않으며 정확한 제안 계획을 별도로 승인한다.</p></section>
<section><h2>보존한 실패와 수정</h2><p>원 디스크0/소스13 UNKNOWN·유지보수 ABORT, 사진 basket 누락, 소스16 모델의 요청하지 않은 상대 waypoint/경로 차단, 소스17 지도 원문 저장 후 신선도 만료는 모두 보존했다. source17 session 비동기 references/frame 관측 경합은 검사 도구 문제로 분리했다. 최종 검수는 원 request/epoch·새 scan capture·현재 frame·동일 영상 SHA·정상 inner/root 종료를 대조하며 오래된 Stop/누락 단계/잘못된 영상 반례를 거절한다.</p><p>초기 heartbeat 지연의 단일 원인은 여전히 미확정이다. 늦은 receipt의 큐 교착 보강은 원 UNKNOWN을 성공으로 승격하지 않는다. 정상 Recover 실제 근거는 소스15 한정이며 최종 소스18은 별도 cold/실행 검수를 따른다.</p></section>
<section><h2>검수 영상</h2><p>아래는 실제 설치 renderer의 원 시간축 시험 녹화다. 실제 마우스 이벤트를 표시한 녹화용 포인터이며 OS 커서나 실물 카메라 영상은 아니다. 완성 제출용 1분 데모도 아니다.</p>{''.join(videos)}</section>
<section><h2>해시 결속 근거</h2><table><tr><th>역할</th><th>원 결과</th><th>SHA-256</th></tr>{''.join(rows)}</table></section></html>'''
with (OUT/'report.html').open('x',encoding='utf-8') as f:f.write(body)
print(json.dumps(dict(status='WRITTEN',gate_status=gate['status'],path=str(OUT/'report.html'))))
