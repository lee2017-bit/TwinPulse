# SPDX-License-Identifier: Apache-2.0
"""Local evidence report; never uploads or operates a robot."""
import html,json
from pathlib import Path
root=Path(__file__).resolve().parents[1];out=root/'outputs/environment-alignment-20261024-01'
read=lambda p:json.loads((out/p).read_text(encoding='utf-8-sig'))
gate=read('acceptance02.json')
if gate['status']!='PASS_SIM_LOCAL_ALIGNMENT_REVIEW_SCOPE':raise ValueError('SCOPED_GATE_NOT_PASSED')
ui=read('ui06/result.json');cold=read('cold05/result.json');physical=read('saved-physical01/result.json');probe=read('saved-sim02/result.json')
e=html.escape;release=gate['installed_verification'];motion=ui['motion_review']['review']['match'];initial=ui['review']['review']['match']
doc=f'''<!doctype html><html lang="ko"><meta charset="utf-8"><title>TwinPulse · 구조벽 정합 검토</title>
<style>body{{font:17px/1.7 system-ui;max-width:1100px;margin:32px auto;padding:0 24px;color:#18252c}}img,video{{max-width:100%;border:1px solid #ddd;border-radius:8px}}code{{word-break:break-all}}td,th{{border:1px solid #ccd8d8;padding:8px;text-align:left}}table{{border-collapse:collapse}}.held{{color:#a42820}}.scope{{background:#edf5fa;padding:16px}}section{{margin:32px 0}}</style>
<h1>구조벽 LiDAR 정합 검토 — SIM 한정 인수</h1><p class="scope">초기 위치를 지정한 국소 정합 → 실제 Isaac 몸체·점/광선 표시 → SIM 10cm 이동 추적 → OFF → 저장 결과 재열기를 확인했다. 실물 절대정합·전체 자율주행·모든 장애물의 정확한 위치는 아직 인수하지 않았다.</p>
<p>설치 <code>{e(release['build_id'])}</code><br>source <code>{e(release['source_manifest_sha256'])}</code> · {release['files']} exact files · data epoch1/environment-static1.1 유지.<br><a href="acceptance02.json">최종 gate {gate['passed']}/{gate['total']}</a> · <a href="acceptance01.json">원 시각 검수 실패</a></p>
<section><h2>무엇이 달라졌나</h2><p>Import space → Scan alignment에서 대략의 몸체 X/Y/yaw, 명확한 벽 span과 기준 길이, 센서 높이를 입력한다. 길이 불일치는 원형상을 임의 조절하지 않고 보류한다. SIM scale check는 실측이 아니다.</p>
<p>원 스캔의 방향·초기 pose·원 USD 벽/가림 구조만으로 fit 이전 ROI를 고정하고 원 인덱스를 보존한다. 고정 train으로 첫 보이는 벽까지의 range를 맞춘 뒤, 별도 heldout 및 후행 두 프레임으로 검토한다. missing/가림은 분모에서 버리지 않는다. 전체 원점 잔차는 별도 보존한다.</p>
<p>Show aligned scan은 제어 모델과 분리된 review-only 몸체와 보라색 점/광선을 표시한다. raw 센서→몸체 TF는 한 번만 적용한다. 오래됨·OFF·owner/장면 변경·정합 실패는 숨긴다. 재열기는 숨김/Saved부터 시작하며 실시간 권한을 복구하지 않는다.</p></section>
<section><h2>직접 대조</h2><table><tr><th>자료</th><th>결과와 한계</th></tr>
<tr><td>원 저장 SIM 표본</td><td>가까운 벽면 비용으로는 약16cm 빗나간 pose와 정답이 모두 약0.0474m였다. 첫-hit 비용은 정답0.0474m / 오답0.1665m, inlier90.5% / 32.6%로 구분했다. 새 fit은 알려진 SIM pose를 회복했다. 원 acquisition·같은 단면 ray 알고리즘이므로 실물 정밀도나 독립 데이터셋 검증이 아니다.</td></tr>
<tr><td>실제 설치 UI/SIM</td><td>초기 {e(str(initial['body_pose']))} → 단일 Forward 10 cm → {e(str(motion['body_pose']))}. 이동 후 고정 heldout 첫-hit 평균 {motion['validation']['first_hit_mean_error_m']:.4f}m / inlier {motion['validation']['first_hit_inlier_fraction']:.1%}. 원 request·새 Stop ACK epoch·후행 engine 적용 뒤 OFF/Disconnect를 확인했다. 빠른 이동/360도 정합은 이번 인수 범위 밖이다.</td></tr>
<tr><td>원 실물 frame715</td><td class="held">역사적 추정 seed [2.25,0.95,0]와 원 기록 TF {e(str(physical['extrinsic']))}만으로는 HELD. 벽 기준 실측 없음·초기 위치/방향 미확인·TF as-built 미측정이다. 원 whole-scan POOR_FIT 및 몸체 UNQUALIFIED 판정을 변경하지 않았다.</td></tr></table></section>
<section><h2>실제 화면과 녹화</h2><p>실제 installed Electron/Isaac renderer 검수다. OS 커서/실물 카메라/완성 제출 영상이 아니다. 기록용 마우스 화살표·halo는 실제 입력 위치이며 종료 시 제거했다.</p>
<video controls preload="metadata" src="ui06/recording/app-screen.mp4"></video><p>SIM 검수 {ui['recording']['wall_ms']/1000:.3f}초 · <a href="ui06/result.json">정확한 원 응답/시각·receipt</a></p>
<img src="ui06/02-aligned-current.png" alt="현재 정합 몸체와 LiDAR 점"><p>몸체와 보라색 점/광선. 이름은 몸체 아래에서 겹칠 수 있으며 origin circle을 추가하지 않는다.</p>
<img src="ui06/03b-moved-tracking.png" alt="SIM 10cm 이동 후 추적"><img src="ui06/04-off-hidden.png" alt="LiDAR OFF와 review layer 제거">
<img src="cold05/02-saved-overlay.png" alt="명시적으로 연 저장 스캔"><p>새 실행에서 같은 job·초기 scan–pose 쌍만 Saved scan으로 명시 재표시. 현재 센서나 이동 권한이 아니다.</p></section>
<section><h2>실패·보완을 감추지 않음</h2><ul><li>ui01: 실제 keyword-only fleet snapshot 호출 오류/HTTP400 → 호출·회귀 보완.</li><li>ui02: recorder는 metadata만 보고 PASS했지만 직접 PNG에서 viewport_image_invalid와 축소된 Twin을 발견해 aggregate FAIL. 화면용 UV만 간소화하고 원 8192 한도를 유지했다. 최대16로봇/긴 Unicode/동시 overlay도 검사했다.</li><li>ui03: 초기 탐색을 매번 반복하던 추적 지연/overlay 공백. 초기3개와 이후1개 국소 refinement를 분리했고 원 1초 신선도/검토 기준은 늘리지 않았다.</li><li>ui04: 검수 카메라 과확대로 점이 화면 밖에 있어 FAIL. ui05: 이전 HELD job을 새 결과로 오인한 검수 race로 FAIL. 새 정확 job/DOM frame·시각·현재 header를 결속해 ui06 전체를 재실행했다.</li><li>cold04: Control view가 아닌 layout에서 검수 camera selector가 없어 FAIL. Control view를 명시한 새 cold05 전체로 재확인했다. 원문은 남겨둔다.</li></ul></section>
<section><h2>Astra 검토·변경 범위</h2><p>Cancel/늦은 publish·초기 TF변경·추적 후 재Show scan–pose 혼합·후행 점수 부족·Unicode header 한도를 보완했다. Core/서비스·검수기를 독립 읽기 검토했으며 실제 UI/SIM은 메인이 실행했다. Python123(조건부 skip1)/UI158/TypeScript는 보조 계약 시험이다.</p>
<p>새 실물 연결/구동0, 이번 모델 호출0(기존10회 승인 중 누적1회만 사용), 신규 iOS/SDK/모델/유료 서비스/외부 업로드/GitHub/삭제0. 원 사진/USD·로봇 로그·사진 후보/adoption·원30mesh와 추정 장애물1개를 보존했다.</p></section>
<section><h2>다음 현장 시험</h2><p>같은 벽 span의 실측 길이와 대략적 초기 위치·방향을 한 번 확인하고 정지 상태의 세 스캔으로 시작한다. 원 TF는 기록값이지 실제 설치 측정이 아니다. 국소 정합이 통과하더라도 몸체 이동·제동·실물 자유공간/목표 이동 승인은 별도 검증한다. 사진 장애물은 여전히 추정 레이어이며 정확한 위치·전체 검출은 자동 완료되지 않았다.</p>
<p><a href="saved-physical01/result.json">저장 실물 보류</a> · <a href="saved-sim02/result.json">저장 SIM 대조</a> · <a href="archive-worker04/result.json">실제 패키지의 원본 로그 읽기</a> · <a href="focused10/result.json">집중 시험</a> · <a href="visual-review01.json">픽셀 검토·해시</a></p></section></html>'''
with (out/'report.html').open('x',encoding='utf-8') as stream:stream.write(doc)
print(str(out/'report.html'))
