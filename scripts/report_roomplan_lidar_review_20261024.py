# SPDX-License-Identifier: Apache-2.0
"""Publish local review artifacts, never uploads or modifies original evidence."""
from pathlib import Path
import html
import json

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/roomplan-lidar-review-20261024-02'
review=json.loads((OUT/'review.json').read_text(encoding='utf-8'))
motion=json.loads((OUT/'motion-review.json').read_text(encoding='utf-8'))
ui=json.loads((OUT/'ui01/result.json').read_text(encoding='utf-8'))
esc=lambda value:html.escape(str(value))
rows=[]
for w in motion['windows'][:2]:
    fit=w['diagnostics']['variants'][0]
    rows.append(f"<tr><td>{esc(w['direction'])}</td><td>{w['wheel']['centre_m']*1000:.3f}</td><td>{w['lidar']['dx_m']*1000:.3f}</td><td>{fit['delta'][0]*1000:.3f}</td><td>{esc(w['comparison'])}</td></tr>")
objects=''.join(f"<tr><td>{esc(o['label'])}</td><td>{esc(o['category'])}</td><td>{' × '.join(f'{v:.3f}' for v in o['dimensions_m'])}</td><td>{o['height_section_segments']}</td></tr>" for o in review['inventory'])
body=f'''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TwinPulse · RoomPlan / LiDAR 검토</title>
<style>body{{font:16px/1.65 system-ui,sans-serif;max-width:1100px;margin:auto;padding:24px;color:#182b38;background:#f6f9fa}}section{{background:white;padding:20px;border:1px solid #d6e0e6;border-radius:12px;margin:20px 0}}h1{{font-size:26px}}h2{{font-size:21px}}table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{text-align:left;border-bottom:1px solid #d6e0e6;padding:8px;overflow-wrap:anywhere}}.scroll{{overflow:auto}}img{{max-width:100%;height:auto}}.held{{color:#a33827;font-weight:650}}small,code{{overflow-wrap:anywhere}}a{{color:#08667b}}</style>
<h1>RoomPlan · 사진 · 실제 LiDAR: 원인과 수정</h1><p>2026-10-24 · 로봇 OFF · 원본 보존 / 장치·모델 호출·업로드 없음</p>
<section><h2>핵심 결론</h2><p>실물 LiDAR 표시와 RoomPlan 절대 좌표 정합은 아직 연결돼 있지 않습니다. 한 바퀴 돌리기만 하면 자동 보정되는 제품 상태가 아닙니다. 새 iPhone 앱보다 기존 scan → Twin 검토 경로를 연결하는 것이 먼저입니다.</p><p>원 USD에 가구 8개와 계산 가능한 크기는 있습니다. 다만 세부·작은 장애물과 실제 다리/열린 공간이 부족합니다. 사진 첨부가 이 USD를 자동 보완하지는 않습니다.</p><p><a href="../../docs/analysis/TWINPULSE_ROOMPLAN_LIDAR_DEMO_REVIEW_2026-10-24.md">전체 분석·Scanner 판단·최종 데모 경로·실행 방법</a></p></section>
<section><h2>이동 불일치: 정합기의 편향 확인</h2><p>단위 mm. wheel은 독립 fit 입력에 사용하지 않았습니다. 새 endpoint 결과가 가까워졌지만 유효 정지 baseline 각각1개·endpoint/chain 차이를 보존하므로 차체 정밀도는 미검증입니다.</p><div class="scroll"><table><tr><th>명령</th><th>Wheel</th><th>균등표본 기존 chain</th><th>새 offline endpoint</th><th>원 제한 판정</th></tr>{''.join(rows)}</table></div><p>이전 −2.965/−25.040mm 결과도 원파일 그대로 보존했습니다. 고정각 ray 재측정 합성 방에서 기존 ICP는 실제100mm를37.35mm로 과소 추정했습니다.</p><p><a href="motion-review.json">새 분석 원문</a> · <a href="../robot-auto-charged-20261024-01/independent-motion01.json">이전 분석 불변본</a> · <a href="../robot-auto-charged-20261024-01/astra-motion-analysis01.json">Astra 독립 재현</a></p></section>
<section><h2>저장 스캔 → 원 USD 단면의 실패 후보</h2><p class="held">{esc(review['match']['status'])} · capped mean {review['match']['mean_error_m']:.6f}m &gt; 기존 기준0.12m</p><p>명령 전 frame715 한 개. 센서 높이0.182m는 nominal URDF이며 실측 장착값이 아닙니다. 회색/황색=원 메시 단면, 청록=실스캔을 가설 좌표로 변환한 점입니다. 실제 앱 world overlay·live TF·360° 누적맵·현재 stage 대응 증명이 아닙니다.</p><img src="overlay-hypothesis.svg" alt="정합 불량인 오프라인 후보. 실측 정합 또는 적용 완료 아님"><p>검색 상자는 free space가 아닙니다. first-hit/가림/별도 검증 프레임/실측 scale 미검증. 기준 완화나 기하 Apply 없이 실패로 남겼습니다.</p><p><a href="review.json">기하·원본·코드 SHA와 결과</a> · <a href="height-section.json">원 triangle의 센서 높이 단면</a></p></section>
<section><h2>현재 가진 입력과 Scanner 결정</h2><p>RoomPlan은 기본 구조로 유지하고 사진의 의미 정보·누락 장애물 관측을 별도 레이어로 다루는 것이 짧은 경로입니다. 치수 JSON 때문에 새 앱을 먼저 만들 필요는 없습니다. RoomPlan만 감싼 새 앱은 단순화 문제도 그대로 가질 수 있습니다.</p><p>세부 형상이 필요하면 ARKit scene mesh/depth·공유좌표·카메라 pose/시각을 확보하는 경로를 검토하되, 현재 앱의 실제 export 가능 여부부터 확인해야 합니다. Mac/Xcode·실기기 개발 접근성은 미확인입니다.</p><p><a href="https://developer.apple.com/augmented-reality/roomplan/">Apple RoomPlan</a> · <a href="https://developer.apple.com/documentation/roomplan/capturedroom/object/dimensions">객체 dimensions의 의미</a> · <a href="https://developer.apple.com/documentation/arkit/arconfiguration/scenereconstruction">ARKit scene reconstruction</a></p></section>
<section><h2>적용한 최소 수정과 검증</h2><p>offline full-ring sampling·수렴/최종 residual·endpoint/chain/phase 차이, 실제 triangle 단면, Import의 접힌 Objects and size, physical Alignment 설명을 추가했습니다. 실시간 ICP·모터·입력/센서/출력·10°·배터리 기준은 변경하지 않았습니다.</p><p>집중 Python40 / UI unit37 / TS·제품 build 확인. 설치 <code>{esc(ui['identity']['engine']['release_id'])}</code> / 1684개 검증. 실제 같은 Electron UI에서 원 프로젝트 재열기·30개 크기 목록·1280×720/1024×768 가로 overflow0·명시 Exit를 확인했습니다. 전체 SIM·실물·Alignment 도움말의 native 입력 인수는 별개입니다.</p><p><a href="ui01/result.json">설치 UI 한정 결과</a> · <a href="ui01/size-1280x720.png">실제1280 화면</a> · <a href="ui01/size-1024x768.png">실제1024 화면</a></p></section>
<section><h2>최초 목적에 맞는 최종 데모</h2><p>실제 입력 → 구조/치수 검토 → 센서와 불일치 한 곳 확인 → 검토된 수정 → Isaac 재계획/이동·Stop → Undo/저장·재열기.</p><p>아직 남은 구현: 사진→누락 장애물 레이어, RoomPlan 정합 review의 제품 연결/독립 검증, 센서 후보→import mesh transaction 결속. 현재 automatic matching·사진 자동 복원·전체 제출 데모가 완료됐다는 뜻이 아닙니다. 불확실한 자동 정합은 수동 독립 기준점+명시 검토 보정으로 좁히고 실제 성공 근거를 보여줍니다.</p></section>
<details><summary>원본 객체와 계산 크기</summary><p>선택한 meters의 장면 축 AABB(X×Y×Z). 회전 물체의 실제 길이/너비 또는 실측 치수가 아닙니다. 마지막 열은0.182m 단면의 triangle 교차선 수입니다.</p><div class="scroll"><table><tr><th>원 객체</th><th>분류</th><th>계산 크기(m)</th><th>교차선</th></tr>{objects}</table></div></details>
<p><small>원USD SHA: {esc(review['source_sha256'])} · 원 operation: {esc(review['operation_id'])} · physical/world verified=false · original unchanged=true</small></p></html>'''
with (OUT/'report.html').open('x',encoding='utf-8') as stream:stream.write(body)
print(OUT/'report.html')
