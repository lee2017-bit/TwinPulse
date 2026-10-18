# SPDX-License-Identifier: Apache-2.0
"""One local report from real receipts; never opens an App/model/device."""
import argparse
from copy import deepcopy
from datetime import datetime,timezone
from hashlib import sha256
from html import escape as e
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/control-recovery-20261018'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def digest(p):return sha256(p.read_bytes()).hexdigest()
def write(p,value):
    with p.open('x',encoding='utf-8') as stream:json.dump(value,stream,ensure_ascii=False,indent=2)
def j(value):return e(json.dumps(value,ensure_ascii=False,indent=2))
def link(p):return '<a href="'+e(p.relative_to(OUT).as_posix())+'">'+e(p.relative_to(OUT).as_posix())+'</a>'
def identities(value,key):
    if isinstance(value,dict):
        for k,v in value.items():
            if k==key and isinstance(v,str):yield v
            yield from identities(v,key)
    elif isinstance(value,list):
        for v in value:yield from identities(v,key)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--attempt',required=True);parser.add_argument('--lineage-cold-attempt');args=parser.parse_args();a=args.attempt
    paths={role:OUT/f'{directory}-{a}/result.json' for role,directory in [('fresh','ui-fresh'),('cold','ui-cold'),('lineage','lineage'),('lineage_cold','lineage-cold'),('normal','normal')]}
    if args.lineage_cold_attempt:paths['lineage_cold']=OUT/f'lineage-cold-{args.lineage_cold_attempt}/result.json'
    paths.update(installation=OUT/f'installation-final-{a}.json',supplementary=OUT/f'offline-final{a}/result.json',budget=OUT/'budget-final.json')
    values={k:read(p) for k,p in paths.items()};install=values['installation'];release=install['release_id'];source=install['source_manifest_sha256']
    ablation=OUT/'offline-ablation-final.json'
    restart=read(OUT/f'normal-{a}-restart/result.json');stop=read(OUT/f'normal-{a}/shutdown.json');restart_stop=read(OUT/f'normal-{a}-restart/shutdown.json');normal=values['normal']
    lifecycle=dict(status='PASS' if stop['status']=='PASS' and restart_stop['status']=='PASS' and restart['status']=='PASS_NORMAL_START_REUSE_DEBUG_OFF' else 'FAIL',
        release_id=release,source_sha256=source,normal_start_launch_id=normal['launch_id'],shutdown_clean=stop['shutdown_clean'],
        restart_ready=restart['status']=='PASS_NORMAL_START_REUSE_DEBUG_OFF',restart_launch_id=restart['launch_id'],restart_debug_listener_count=restart['debug_listener_count'],
        restart_app_listener_count=restart['app_listener_count'],restart_authenticated_ready=restart['status']=='PASS_NORMAL_START_REUSE_DEBUG_OFF',restart_ready_wait_ms=restart['ready_wait_ms'],restart_shutdown_clean=restart_stop['shutdown_clean'],
        input_receipt='native-attempts.json',normal=normal,restart=restart,shutdown=stop,restart_shutdown=restart_stop)
    write(OUT/'normal-lifecycle.json',lifecycle);paths['lifecycle']=OUT/'normal-lifecycle.json'
    review=dict(schema='physical-readiness-review-1.0',status='NOT_READY',unresolved=['ORIGINAL_201_UNKNOWN_CONTROL_SPANS_AND_202_INCOMPLETE_RINGS','ACTUAL_PI_ROS_SOURCE_AGE_AND_TRACKER_LOAD_NOT_RETESTED','PHYSICAL_MOTION_STOPPING_LOCALIZATION_NOT_RUN_ROBOT_OFF'],
        evidence=[dict(path=p.relative_to(OUT).as_posix(),sha256=digest(p)) for p in (OUT/'astra-review.json',ablation)],
        basis='Explicit main/reviewer assessment of preserved original failure, not automatic discovery of every possible defect.')
    manifest=dict(release_id=release,source_sha256=source,physical_readiness_review=review,evidence=[dict(role=k,path=p.relative_to(OUT).as_posix(),sha256=digest(p)) for k,p in paths.items()])
    write(OUT/'evidence-manifest.json',manifest)
    subprocess.run([sys.executable,'scripts/verify_robot_focus_gate.py','--manifest',str(OUT/'evidence-manifest.json'),'--output',str(OUT/'gate-result.json')],cwd=ROOT,check=False)
    gate=read(OUT/'gate-result.json')
    # Original failed App result remains unchanged. Negative gate evidence is
    # separately labelled and can never become a user acceptance result.
    negative=deepcopy(manifest);failed=OUT/'ui-fresh-03c/result.json'
    for row in negative['evidence']:
        if row['role']=='fresh':row.update(path=failed.relative_to(OUT).as_posix(),sha256=digest(failed))
    negative['classification']='NEGATIVE_GATE_ONLY_ORIGINAL_FAILURE_NOT_CURRENT_APP_ACCEPTANCE'
    write(OUT/'negative-original-manifest.json',negative)
    subprocess.run([sys.executable,'scripts/verify_robot_focus_gate.py','--manifest',str(OUT/'negative-original-manifest.json'),'--output',str(OUT/'negative-original-result.json')],cwd=ROOT,check=False)
    neg=read(OUT/'negative-original-result.json')
    if neg.get('software_status')!='FAIL' or 'RUN_NOT_PASS:fresh' not in neg['issues']:raise ValueError('Original failure was not rejected')
    attempts=[]
    for p in sorted(OUT.glob('*/result.json')):
        v=read(p);row={k:v[k] for k in ('status','phase','project','operation_id','desktop','release_id','source_sha256','input_sha256','error','http_errors','request_failures','request_failed','ready_wait_ms') if k in v}
        row.update(path=p.relative_to(OUT).as_posix(),sha256=digest(p),steps=[{k:s[k] for k in ('name','status','elapsed_ms','error') if k in s} for s in v.get('steps',[])],
            operation_ids=sorted(set(identities(v,'operation_id'))))
        attempts.append(row)
    write(OUT/'attempt-index.json',attempts)
    budget=values['budget'];before=read(OUT/'budget-before.json');requests={k:v for k,v in budget['requests'].items() if k not in before['requests']}
    accounting=dict(http=len(requests),estimated_usd=budget['new_estimated_usd'],new_unknown_usd=budget['new_unknown_usd'],additional_50_cumulative=budget['protected_additional_50_total'],remaining_usd=str(50-float(budget['protected_additional_50_total'])),
        previous_20=budget['prior_20_campaign'],models=sorted(set(r['model_id'] for r in requests.values())),requests=requests,basis='Usage/frozen catalog estimate, not provider invoice or live provider credit balance')
    write(OUT/'accounting-summary.json',accounting)
    parts=['<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>TwinPulse 조종 화면·지연 회복·전체 사이클</title>',
      '<style>body{max-width:1160px;margin:28px auto;padding:0 20px;color:#173c46;background:#f0f5f7;font:16px/1.65 system-ui}section{background:white;border:1px solid #c7d8df;border-radius:12px;padding:20px;margin:20px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}img,video{max-width:100%;height:auto}table{border-collapse:collapse;width:100%;font-size:13px}th,td{border:1px solid #ccdbe3;padding:8px;text-align:left;vertical-align:top}a{color:#006d75}.warn{background:#fff4e4}h1{line-height:1.3}</style>',
      '<h1>TwinPulse — 조종 화면·지연 회복·전체 사이클 인수</h1><p>'+e(datetime.now(timezone.utc).isoformat())+'</p>',
      '<section class="warn"><h2>종료 판정</h2><p><strong>'+e(gate['software_status'])+' / 전체 실물 준비 '+e(gate['status'])+'</strong></p><p>로봇 OFF. 새 SSH·센서·모터 활성0. SIM 성공으로 알려진 실물 차단을 해소했다고 판정하지 않는다. 아래 성적은 같은 설치 Electron/Isaac의 실제 UI 여정이며 제품 전체·물리 제동·사진 품질·CAD/BRep 전체 완료가 아니다.</p><pre>'+j(gate)+'</pre></section>',
      '<section><h2>이번 구현</h2><ol><li>영상을 덮던 fixed overlay를 단일 하단 dock으로 교체. 조종 보기·채팅/Twin 분할 조절, 짧은 창은 Twin전체폭과 가로 압축 콘솔. Stop/방향/LiDAR/명령을 상시 노출하고 준비·센서·로그는 접힌 상세로 분리.</li>',
      '<li>창/분할 변경 때 held input 해제·자동 재생0. 단일 owner·원250ms 입력·epoch·독립Stop 유지.</li><li>표시된 이미지의 원래1초 수명 안에서만 같은 scene/stage/camera의 늦은 metadata를 허용. 화면에 실제 그린 frame ID로 카메라 요청. 중단 중 마지막 decoded image 보존·stale/카메라 잠금·복구 검증. 원 영상의 장시간 정체 원인이 이것 하나였다고 단정하지 않음.</li>',
      '<li>ROS callback에서 최신 원본 시각/상태를 직렬화보다 먼저 공개. bounded256 FIFO 전용 기록 thread, 원문/순서/offset 보존, overflow·직렬화 실패 latch와 publish 직전 재검사.</li><li>ICP는 별도 spawn process/GIL·단일 in-flight. 원80ms 계산과 결과 나이를 분리하고 원본 frame clock/stream/sequence/job ID·실패 정체·cleanup/reap을 기록. 실패 old owner를 새 tracker로 덮지 않음.</li>',
      '<li>정지/장시간 수집은 처음 invalid ring에서 종료하지 않고 원8초/300초 동안 기록. invalid가 있으면 최종INCONCLUSIVE로 남기며 성공 기준을 낮추지 않음.</li><li>손상 packet이 다음 각도 보간을 오염시키지 않도록 수정. unknown span의 원bytes SHA/offset/경계 귀속을 보존. 원201개11byte 응답은 여전히 UNKNOWN.</li>',
      '<li>설치 App에서 발견한 field_setup 빈 응답은 PC가 worker 모듈을 동적 import한 의존성 결함. 검증 규칙 AST가 같은 순수 field_config 계약으로 분리하고 격리 Python 및 실제 정확한200 ACK로 재인수.</li><li>readiness gate에 실제 크기 집합·조상 clipping/hit-test·60초 decoded-frame coverage·시간/lineage·실제invalid profile 거절·현재 실물 차단 검토를 추가. 원FAIL은 negative검사에서 소프트웨어FAIL로 거절.</li></ol><p>'+link(OUT/'field-setup-failure-analysis.json')+' · '+link(OUT/'astra-review.json')+'</p></section>',
      '<section><h2>실제 사용자 경로와 방법 차이</h2><p>저장소 root Start-TwinPulse-Test.cmd → 동일 설치 BrowserWindow의 실제 New chat·입력·Create → 실제 Flash/Nemotron → Isaac2SIM 연결/4방향·키/60초/90°/360°+scan → Stop·반출 → cold reopen·수정/Save/Undo·프로젝트 전환 → 종료. 일반 root Start는 별도로 중복 실행·debug-off·종료·재시작을 확인한다. Start 호출은 실행도구이며 Explorer 더블클릭이 아니다.</p><p>별도 Chrome·제품 변경 API 직접 호출·고정 모델 응답·내부 상태 주입0. 일반 조종 Fetch 중계0, 지연은 Stop 확인 후 별도 명시 fault창에서만 주입. Test BrowserWindow 입력과 native OS 입력을 구분한다. 다섯 CSS가용크기는 OS DPI100/125/150% 실제 변경 시험이 아니다. OS붙여넣기/전체 일반창 native 사용자 여정은 NOT_RUN.</p><p>SIM은 USD transform/AABB kinematic 및 ray 계산이며 PhysX 차체/RTX LiDAR·실물 성능 증거가 아니다. SIM 배터리 unavailable/simulated는 임의 잔량을 만들지 않은 정상 표시다. 장면 수정은 실제 검토폼을 통한 편집이며 자연어 scene-edit 모델 인수라고 부르지 않는다.</p></section>',
      '<section><h2>현재 릴리스·주요 전체 여정</h2><pre>'+j(dict(release_id=release,source_sha256=source,package_files=install['files'],normal=lifecycle))+'</pre><table><tr><th>여정</th><th>판정·원 ID</th></tr>']
    for role in ('fresh','cold','lineage','lineage_cold'):
        v=values[role];parts.append('<tr><td>'+e(role)+' · '+link(paths[role])+'</td><td><pre>'+j(dict(status=v['status'],project=v.get('project'),operation=v.get('operation_id'),desktop=v.get('desktop'),steps=[dict(name=s['name'],status=s['status'],elapsed_ms=s.get('elapsed_ms')) for s in v.get('steps',[])]))+'</pre></td></tr>')
    parts+=['</table></section><section><h2>실제 화면과 녹화</h2><p>렌더러 screencast만 녹화, 소리·native desktop·실물 로봇 영상 아님. 원 JPEG/timing도 보존. 실제 화면을 합성하지 않았다.</p>']
    for p in [OUT/f'ui-fresh-{a}/control-layout-911-512.png',OUT/f'ui-fresh-{a}/held-60s.png',OUT/f'ui-fresh-{a}/frame-gap-last-image.png',OUT/f'lineage-{a}/undo-context.png']:
        if p.exists():parts.append('<figure><img loading="lazy" src="'+p.relative_to(OUT).as_posix()+'"><figcaption>'+e(p.relative_to(OUT).as_posix())+'</figcaption></figure>')
    for p in sorted(OUT.glob('recording-*/app-screen.mp4')):
        parts.append('<details><summary>'+e(p.parent.name)+'</summary><video controls preload="none" src="'+p.relative_to(OUT).as_posix()+'"></video></details>')
    parts+=['</section><section><h2>모든 시도·실패·시간·계보</h2><p>'+link(OUT/'attempt-index.json')+'에 각 원본SHA·입력SHA·launch/project/operation ID가 있으며 원 result에 command/request/scene/stage/event 계보와 네트워크시각을 보존한다. 실패 후 이어하기를 하나의 fresh 성공으로 합치지 않는다.</p><table><tr><th>시도</th><th>판정</th><th>실패/단계</th></tr>']
    for v in attempts:
        parts.append('<tr><td><a href="'+e(v['path'])+'">'+e(v['path'])+'</a></td><td>'+e(v.get('status','RECORDED'))+'</td><td><pre>'+j(dict(project=v.get('project'),operation_ids=v['operation_ids'],steps=v['steps'],error=v.get('error')))+'</pre></td></tr>')
    parts+=['</table><p>추가 도구 시도: 잘못 선택한 개발 venv의 PyInstaller metadata 부재로 build02 첫 명령 실패(설치0), 기존 .build-venv로 재실행. fresh03은 CDP리스너 전 조기접속 ECONNREFUSED(단계0/모델0), 같은 새 창에서 별도03b 전체 시작. 03b는 접힌 상위 메뉴를 열지 않은 시험경로 오류. 03c는 설정 저장의 실제 설치 결함이며 원31단계 표시가PASS여도 전체FAIL이다. 격리시험 최초의 잘못 배치한 assertion1건도 보존·수정했다.</p></section>',
      '<section><h2>보조검증·시간 정책·원문</h2><pre>'+j(values['supplementary'])+'</pre><p>'+link(ablation)+' · '+link(OUT/'gate-unit-final-02.log')+'</p><pre>'+j(read(ablation).get('stages'))+'</pre><p>원8,336,993bytes/51,791chunk/103,514packet/2,433,198node,6,081ring 중202incomplete·CRC0·unknown2259B는 보존. Windows57쌍 계산 결과 exact/child cleanup 확인. 이것은 wall-time으로 원 취득 주기를 재현한 Pi/ROS/DDS·archive disk-load 시험이 아니다.</p><p>기존 실물 STREAMING 원본나이 평균206.921ms/SD30.927ms/p99286.043ms,200ms초과52.323%. OFF 평균30.476ms. 단순3SD 기준은 없었으며 이번에도 원200/250/350/80/400/500ms 보호를 임의 확대하거나 failure를 정상 분포로 자동학습하지 않았다. control_timing.py에 목적/clock/실패/회복을 명시했다. 실제 Pi에서 개선 후분포·원시기록 전체부하 비교는 NOT_RUN이다.</p></section>',
      '<section><h2>비용·권한·보존</h2><pre>'+j({k:v for k,v in accounting.items() if k!='requests'})+'</pre><p>새 모델 전송은 시험 텍스트와 파생 Isaac render이며 개인 사진 신규전송0. 주 모델 실제 runtime ID는 도구로 독립 확인불가, UI보조 Sol6.1 high·검토 Astra xhigh는 요청 설정 기준이다. raw/사진/프로젝트·장부·dirty 변경 보존, 새 의존성/물리/유료Cloud/공개/commit/push/삭제0. 생성한 빌드/ZIP/영상은 시험 산출물이며 Twin모델 자체 용량과 다르다. 이번 누적4후보는 자동정리된 상태가 아니고 현재·필요rollback/재현본을 구분하는 별도 보존 정책이 필요하다.</p></section>',
      '<section class="warn"><h2>정확한 잔여·다음 조건</h2><ol><li>원 type06처럼 보이는11byte 응답201개의 제조사 정의/길이/검증식 미확인. 공식 문서/SDK 근거 없이는 정상 non-scan으로 승격하지 않음. 원202incomplete와 실물 qualification 차단이 남음.</li><li>실제Pi의 ROS단독→native→tracking→fullrecord 순서 부하 측정, 개선 후sourceage/compute/IPC/fault/cleanup과 연속운전을 확인해야 함. Windows 빠른 replay를 대신 쓰지 않음.</li><li>로봇은OFF이므로 실제연결/배터리연속갱신/이동·제동·한세션360/차체정체·실제Wi-Fi·world정합·2대 실물은NOT_RUN. 지금 로봇만 켜면 모두검증완료라는 안내를 하지 않음.</li><li>일반창 전체native입력/Explorer/OS Ctrl+V/실제DPI·clean PC는 별도미검증. Test경로와 일반Start의 공통설치 검증 범위만 인정.</li><li>이전 사진품질·CAD/BRep·Library 전체/자동buildGC 등 이번 조종 UI·지연 회복 밖의 미완료는 완료로 바꾸지 않음.</li></ol><p>현 단계는 알려진 실물 차단을 해소하기 전이며 재전원을 요청하지 않는다. 다음에는 프로토콜 근거 확보 및 현재 코드의 비구동 부하 측정 준비를 먼저 진행해야 한다.</p></section></html>']
    parts.insert(-1,'<section class="warn"><h2>종료 클릭의 남은 불확실성</h2><p>lineage-cold04b는 종료 클릭 후 POST 미관찰/60초 미종료로 전체FAIL이다. 최초 pointer/활성 시계열이 없어 이벤트 미전달/버튼 활성 전환 중 어느 쪽인지 UNKNOWN이다. 이후 같은 창의 별도 클릭은202로 종료했고,04c는 별도 cold 전체4단계(pointerdown/up/click·정확202·2.888초종료)를 통과했다. 두 차례 일반 native Alt+F4 정리도 별도통과했다. 이것을 원04b 원인 해결이라고 주장하지 않는다. 후속에는 pointer·disabled/availability·POST/ACK 시계열을 계속 결속해야 한다. 이 미확정까지 포함해 전체문제해결/결함없는제품이라고 판정하지 않는다.</p><p>원04는 다른 과거 operation 기대값108/2334를 최신110/117133과 섞은 시험결함이다.04c는 새download에서 기대값을 만들지 않고 보존 원ee988...export SHA에 결속해 events/stream/worker/source context/trial을 검증했다. 원FAIL은 모두 남아 있다.</p></section>')
    target=OUT/'report.html'
    with target.open('x',encoding='utf-8') as stream:stream.write(''.join(parts))
    print(json.dumps(dict(report=str(target),software=gate['software_status'],overall=gate['status'],release_id=release),ensure_ascii=False))

if __name__=='__main__':main()
