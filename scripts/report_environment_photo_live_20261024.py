# SPDX-License-Identifier: Apache-2.0
"""Generate a local evidence report, not a public upload or hardware verdict."""
import html,json
from pathlib import Path
root=Path(__file__).resolve().parents[1];out=root/'outputs/environment-photo-live-20261024-01'
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
e=lambda v:html.escape(str(v))
gate=read(out/'acceptance02.json');audit=read(out/'job-audit03/audit.json');job=audit['jobs'][0]
proposal=read(out/'job-audit03'/job['job_id']/'result.json');usd=read(out/'usd02/result.json')
def link(path,label):return f'<a href="{e(path)}">{e(label)}</a>'
candidates=''.join(f'<tr><td>{e(c["id"])}</td><td>{e(c["label"])}</td><td>{e(c["confidence"])}</td><td>{"明示 검토·시험 배치" if c["id"]=="Candidate_2" else "제안만·미적용"}</td></tr>' for c in proposal['candidates'])
checks=''.join(f'<tr><td>{e(k)}</td><td>{"PASS" if v else "FAIL"}</td></tr>' for k,v in gate['checks'].items())
body=f'''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>TwinPulse v638 · 사진 후보와 원 RoomPlan 혼합 검증</title><style>
body{{font:16px/1.65 system-ui,sans-serif;max-width:1120px;margin:36px auto;padding:0 20px;color:#172a35;background:#f7fafb}}h1,h2{{line-height:1.3}}section{{background:white;padding:22px;margin:18px 0;border:1px solid #d3e0e5;border-radius:12px}}table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{text-align:left;border-bottom:1px solid #d3e0e5;padding:9px;overflow-wrap:anywhere}}img,video{{width:100%;height:auto;border-radius:8px;background:#10232d}}code{{overflow-wrap:anywhere}}a{{color:#006b83}}.limit{{border-left:5px solid #ae620b;padding-left:15px}}small{{color:#4b626d}}</style>
<h1>TwinPulse · 실제 사진 후보 → 검토 → 원 RoomPlan에 추가</h1>
<p>2026-10-24 · 로컬 설치·SIM 한정 결과: <strong>{e(gate['status'])}</strong></p>
<p class="limit">자동 metric 사진 배치·실물 LiDAR 세계정합·몸체 주행/제동 qualification·완성 제출 영상은 아직 아니다. 원 POOR_FIT/UNQUALIFIED와 이전 실패를 그대로 보존했다.</p>
<section><h2>이번에 확인한 것</h2>
<p>추가 승인 최대10회 중 실제 configured observer HTTP <strong>1회</strong>, 2,607 tokens. 선풍기·바구니·가방 3개 후보를 받았으며, 바구니만 빈 XY 검토란에 시험 좌표를 입력하고 중복 확인 → Preview → Apply했다. 자동 재시도·자동 적용은 없다. 나머지9회는 사용하지 않았다.</p>
<table><tr><th>후보</th><th>관찰명</th><th>인식 confidence</th><th>상태</th></tr>{candidates}</table>
<p>bbox/class는 단일 사진의 근사 제안이다. metric 위치·치수·전 장애물 검출률을 증명하지 않는다. 카탈로그 크기와 test 배치를 실제 측정으로 부르지 않는다.</p>
<p>원 USD 38,339 bytes·30 meshes는 불변이다. USD SHA <code>{e(job['source_sha256'])}</code><br>사진 SHA <code>{e(job['photo_sha256'])}</code><br>모델 응답 SHA <code>{e(job['response_sha256'])}</code></p>
<p>원본에는 authored metersPerUnit이 없어 명시 선택한 m은 미교정 SIM scale이다. USD의 기하 bounds/치수를 계산할 수 있다는 사실과 실제 단위 교정 완료는 구별한다.</p>
<p>{link('ui01/result.json','일반 Home→New chat→원 USD→Build→실제 분석 원문')} · {link('job-audit03/audit.json','실제 HTTP/응답/적용 영수증 해시')} · {link('adopt04/result.json','마지막 명시 적용 원문')} · {link('cold07/result.json','마지막 독립 재열기')}</p></section>
<section><h2>실제 SIM 로봇·LiDAR 표시</h2>
<img src="sim05/02-enlarged-model-lidar.png" alt="실제 설치 SIM 화면의 로봇과 LiDAR ON">
<p>원본을 숨기거나 삭제하지 않았다. 이전 시험 위치 위 원본 Storage2가 카메라를 가려 body를 못 보거나 검게 보인 경우를 원문에 남겼다. 새 공개 test 위치 [1.35,1.15,0], 바구니 [2.35,1.15]는 SIM 내부에서 선택했으며 사진 정합 결과가 아니다. Top view와 수직→Orbit 복귀를 보완했다.</p>
<img src="sim05/04-lidar-off.png" alt="같은 연결에서 LiDAR OFF 뒤 점과 광선이 제거된 실제 화면">
<p>별도 Stage에 같은 저자화·레이 알고리즘으로 재구성한 SIM 비교: 센서 높이 {usd['height_m']}m, 전방 바구니 첫 hit {usd['first_hit'][0]}m, 반환점 {usd['ray_count']}개, 최대 재현 차이 {usd['max_ray_error_m']:.7f}m. 독립 알고리즘·광학 정확도·누락 ray 또는 실물 정밀도 평가가 아니다.</p>
<p>{link('sim05/result.json','새 전체 SIM 여정·정확 Stop ACK/적용 epoch')} · {link('usd02/result.json','별도 Stage SIM 수치')} · {link('visual-review02.json','실제 픽셀 검수')}</p>
<video controls preload="metadata" src="sim05/recording/app-screen.mp4"></video>
<small>실제 설치 Electron renderer 검수 녹화. 이벤트 위치 arrow/halo 표시이며 OS 마우스·실물 카메라 영상이 아니다. 전체 제출용 1분 데모가 아니다.</small>
<details><summary>원본 입력·분석 검수 녹화</summary><video controls preload="none" src="ui01/recording/app-screen.mp4"></video></details></section>
<section><h2>발견·보완·보존한 실패</h2><table>
<tr><th>기록</th><th>상태와 처리</th></tr>
<tr><td>이전 v637 schema 누락</td><td>전송 전 원 실패·requests0는 별도 그대로 보존. 이번 실제 성공으로 바꾸지 않음.</td></tr>
<tr><td>sim01/02·view01</td><td>원 수납장 가림·검은 카메라 화면. 이전 PASS_SCOPED라는 검수기 표기를 시각 인수로 사용하지 않음.</td></tr>
<tr><td>sim04 Stop</td><td>기존 PAUSED snapshot을 잘못 저장해 새 Stop 적용 epoch 미확인. 원 결과 유지, 검수기를 새 ACK epoch 후행 적용 대기 방식으로 수정 후 sim05 전체 재실행.</td></tr>
<tr><td>cold05 Build409</td><td>capability만이 아니라 lease-dependent permission도 같은 오류로 묶였음. 원 단독 인과는 미확정. 무거운 저장 검증/ack를 workflow lock 안에서 lease 획득 전으로 옮기고 만료/identity/submit 보호는 유지. 새 설치 cold06/SIM05/cold07로 확인.</td></tr>
<tr><td>SDK probe 후 startup 거절</td><td>제 진단 실행이 불변 설치 내부에 pyc114개/2,390,858 bytes를 만들어 strict manifest가 정확히 차단함. 정확 extras만 SHA 검증해 격리 이동(삭제0). 원 파일/manifest/검증 불변. SDK -B/dont_write_bytecode 보완 후1690 exact 재검사. prelaunch 거절은 engine/robot 실패가 아님.</td></tr>
<tr><td>검수/빌드 보조 오류</td><td>초반 TS exact 옵션·포즈 선택 helper·모듈 경로/명령 구문·일반venv PyInstaller 부재·준비 전 cold04 ECONNREFUSED 원 도구출력 보존. 기존 .build-venv 사용, 의존성 신규설치0. sim02의 초기 null출력 DTS경고는 원timebase/passthrough 재검수와 구분하며 최종 인수는 별도 sim05다.</td></tr></table>
<p>{link('acceptance01.json','거절된 원 aggregate FAIL')} · {link('cold05/result.json','원 Build409')} · {link('sim04-review.json','원 Stop 검수 누락')} · {link('probe-startup-incident.json','SDK cache 사고/복구 한계')} · {link('cache-quarantine-inventory.json','격리 원경로·SHA 목록')}</p></section>
<section><h2>최종 설치·인수와 한계</h2><p>현재 <code>{e(gate['installed_verification']['build_id'])}</code> · 1690 exact files · data epoch1/environment-static1.1 유지. 최종 집중 Python159(조건부 skip1)/Web155/TypeScript는 보조 계약 검사이며 실제 모델 품질/세계정합을 대신하지 않는다. 현재 설치의 cold06/SIM05/cold07과 각 정확 launch 종료 archive를 결속했다. 모든7개 소유 실행은 정상 Exit, roots 자연0·원 Kit/runtime 9개 exact 해시 동결이며 선택적 engine-liveness 원본 부재1개는 별도 기록했다. 실패 cold05도 정상 종료였다는 사실이 Build 실패를 면제하지 않는다.</p>
<p>다음 핵심은 안정 벽/구조 중심 LiDAR 정합 후보와 held-out 검증, 사진 후보의 사용자 확인 위치/추가 관측 연결이다. 지금 단계 때문에 iOS 앱·USDZ 변환·새 모델/SDK·유료 GPU가 필수인 것은 아니다. 실물 연결/이동·GitHub 업로드는 이번에0이다.</p>
<details><summary>최종 evidence gate 전체 검사</summary><table>{checks}</table></details><p>{link('acceptance02.json','최종 machine-readable 판정')} · {link('focused05/result.json','집중 회귀')} · {link('../../docs/analysis/TWINPULSE_ROOMPLAN_LIDAR_DEMO_REVIEW_2026-10-24.md','프로젝트 분석/재현 경로')}</p></section></html>'''
(out/'report.html').write_text(body.replace('明示','명시'),encoding='utf-8')
print(json.dumps({'report':str(out/'report.html'),'status':gate['status']},ensure_ascii=False))
