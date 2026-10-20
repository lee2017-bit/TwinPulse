# SPDX-License-Identifier: Apache-2.0
"""Local derived repair report; no App requests, SSH or provider calls."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib
import html
import json

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/robot-input-stop-recovery-20261019'


def load(name):return json.loads((OUT/name).read_text(encoding='utf-8-sig'))
def sha(p):
    with p.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    install=load('installation02.json');offline=load('offline-final02/result.json')
    replay=load('original-replay.json');sim=load('sim-original-goals02/result.json')
    if install['status']!='PASS' or offline.get('status')!='PASS' or not offline.get('source_unchanged'):
        raise ValueError('CURRENT_INSTALL_OR_OFFLINE_EVIDENCE_FAILED')
    if sim['status']!='PASS_ORIGINAL_SAVED_SCENE_GOALS':raise ValueError('CURRENT_SIM_REGRESSION_FAILED')
    operation=load('sim-cold-operation.json')
    # Cold byte/value preservation is the first candidate's independent journey.
    if load('sim-original-goals/result.json')['operation_id']!=operation['operation_id']:raise ValueError('ACTUAL_OPERATION_ID_MISMATCH')
    if not operation.get('manifest',{}).get('complete'):raise ValueError('ACTUAL_SIM_OPERATION_NOT_COMPLETE')
    if sim['identity']['engine']['release_id']!=install['release_id']:raise ValueError('ACTUAL_INSTALLED_ID_MISMATCH')
    final_operation=load('sim-final-operation02.json')
    if final_operation['operation_id']!=sim['operation_id'] or not final_operation['manifest']['complete']:
        raise ValueError('FINAL_INSTALLED_OPERATION_NOT_FINALIZED')
    evidence=[]
    for name in ('installation.json','installation02.json','original-replay.json','offline-final/result.json','offline-final02/result.json','safety-tests.log','safety-tests02.log',
            'sim-original-goals/result.json','sim-closed-operation.json','sim-cold-operation.json','sim-original-goals/app-screen.mp4',
            'sim-original-goals02/result.json','sim-original-goals02/app-screen.mp4','sim-final-operation02.json','cold-receipt.json','cold-byte-comparison.json',
            'ui-session/session.json','ui-session/app-screen.mp4','ui-cold-cleanup/shutdown.json','final-cleanup/shutdown.json',
            'after-first-exit/receipt.json','after-final-exit/receipt.json'):
        p=OUT/name
        evidence.append(dict(path=name,sha256=sha(p),bytes=p.stat().st_size) if p.is_file() else dict(path=name,status='NOT_CREATED'))
    zipfile=next((OUT/'build-02').glob('*.zip'))
    evidence.append(dict(path=zipfile.relative_to(OUT).as_posix(),sha256=sha(zipfile),bytes=zipfile.stat().st_size))
    result=dict(schema='input-stop-recovery-report-1.0',updated_at=datetime.now(timezone.utc).isoformat(),
        status='IMPLEMENTED_INSTALLED_PC_SIM_SCOPED_PHYSICAL_RETEST_PENDING',
        installation=install,offline=offline,sim=sim,evidence=evidence,
        original_physical_operations=[a['operation_id'] for a in replay['attempts']],
        physical=dict(robot_connections=0,motion_commands=0,reason='CURRENT_ONSITE_SUPERVISION_REPLY_PENDING',
            bootstrap='NOT_RUN',manual='NOT_RUN',chat='NOT_RUN',full_turn='NOT_RUN',
            old_failure_status='Preserved; new passing device-free/SIM results do not replace failed powered trials.'),
        change=dict(input_lifetime_s=.25,input_lifetime_changed=False,small_control_window_period_s=.05,
            final_cleanup_previous_fixed_observation_s=.25,
            final_cleanup_observation_s=.9,observation_basis='Existing release OBSERVE_S .8 + sample gap .1',
            stable_encoder_s=.2,stable_encoder_changed=False,stop_or_off_dispatch_delayed=False),
        raw_replay=dict(status=replay['status'],source_schema=replay['source_schema'],
            third_attempt_last_stable_s=replay['attempts'][2]['stable_at_last_original_sensor_s'],
            source_bytes_unchanged=True,no_sample_extrapolation=True),
        unknown=['Exact old nonce issue/accept/deadline at the physical expiry',
            'Whether the new reply path sustains the original input bound on the actual Pi under full load',
            'Actual new-build Stop readback, chassis stopping and physical navigation'],
        test_limits=['Same installed explicit Test BrowserWindow; Start file invoked through execution tool, not Explorer',
            'Saved-room SIM regression, not fresh generation/photo quality or a new full-start demo',
            'Original failed physical exports kept; sensor unknown bytes and strict incomplete rings retained',
            'Full F01-F12 readiness gate and all fresh/cold journeys were not rerun for this targeted physical repair'],
        cost=dict(new_llm_http=0,new_llm_usd='0',additional_50_ledger_remaining='46.8551834',
            provider_balance='NOT_QUERIED',prior_20_campaign='UNCHANGED'),
        early_test_corrections=['Initial supplementary run found missing math import; fixed before installation',
            'One supplementary invocation lacked sibling-test import path; corrected discovery invocation passed',
            'Early chat click saw disabled Isaac-startup button and executed no project action; later actual click succeeded',
            'First export was clicked before Disconnect completion refreshed the logs and retains IN_PROGRESS; cold App export is separate'])
    (OUT/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    rows=''.join('<tr><td>'+html.escape(g['name'])+'</td><td>'+g['status']+'</td><td><a href="offline-final02/'+g['log']+'">원문 log</a></td></tr>' for g in offline['groups'])
    sources=''.join('<li><a href="'+html.escape(e['path'])+'">'+html.escape(e['path'])+'</a> · '+str(e.get('bytes','missing'))+' bytes · <code>'+e.get('sha256',e.get('status',''))+'</code></li>' for e in evidence if 'sha256' in e)
    report='''<!doctype html><html lang="ko"><meta charset="utf-8"><title>TwinPulse 입력 갱신·정지 확인 수정</title>
<style>body{max-width:1080px;margin:36px auto;padding:0 22px;font:16px/1.65 system-ui;color:#18303c;background:#f5f8fa}article{background:white;padding:28px;border-radius:14px}h1{font-size:26px}h2{font-size:20px;margin-top:30px}table{border-collapse:collapse;width:100%}th,td{border:1px solid #cad7dd;padding:9px;text-align:left}code{overflow-wrap:anywhere}img,video{width:100%;border-radius:8px}li{margin:10px 0}.status{padding:14px;background:#fff1ce;border-radius:8px}a{color:#006e73}</style><article>
<h1>TwinPulse 입력 갱신·정지 확인 수정 및 설치 검증</h1>
<p class="status">구현·설치와 PC/SIM 한정 회귀 확인. 실제 로봇의 수정 후 주행·정지·풀사이클은 아직 미실행입니다. 현재 현장 감독 상태를 묻는 답변을 기다렸으며 새 로봇 연결·명령은 0회입니다.</p>
<p>최종 설치 <code>RELEASE</code> · source <code>SOURCE</code> · launch <code>LAUNCH</code>. 기존 실제 실패는 <a href="../robot-powered-20261019-fix/report.html">세 전원 시험 원보고서</a>에 그대로 보존했습니다. 첫 후보 9a7d6529a63d와 전체 진단을 반복 heartbeat에서 제외한 최종 후보를 구분합니다.</p>
<h2>원인과 이번 변경</h2><ol>
<li>준비 후 입력을 받도록 한 수정에 이어, 원격 제어 갱신을 큰 화면 상태 heartbeat에서 분리했습니다. 작은 현재 입력 창을 50ms 주기로 보내고 PC가 수신 즉시 회신합니다. 기존 100ms PC 주기 타이머를 기다리지 않습니다. 수동 방향 입력과 존재 확인은 서로 다른 nonce를 사용하며 원래 250ms·세대·순서·Stop 검사는 유지합니다. 오래된 heartbeat가 새 제어 nonce를 덮지 못하게 했습니다.</li>
<li>기존 최종 정리의 고정 250ms 관측 대신, 이미 버튼 해제에 쓰던 최대 900ms 관측을 재사용합니다. Stop·토크 OFF 요청은 즉시 보내며, 200ms 안정성·최신 센서·explicit_stop·바퀴 이동 한도는 그대로 확인합니다. 이 변경은 관측 시간을 명시적으로 바꾼 것이며 모든 timeout을 그대로 두었다고 주장하지 않습니다.</li>
<li>입력 발급·수락·원 생성 시각·deadline·남은 시간과 단계별 48개 최근 기록을 메모리에서 포착하고 Stop 뒤 같은 trial/operation에 저장합니다. 정지 서비스 각각의 응답·토크·센서 시각·마지막 엔코더 변화·관측 결과를 정리 기록에 넣습니다. nonce 원문은 보관하지 않습니다.</li></ol>
<p>ROBOTIS의 <a href="SCHEMA_URL">공식 SensorState 정의</a>로 기존 센서 CDR 원문을 SHA 대조해 읽었습니다. 세 번째 시도의 마지막 원 표본에 확인된 엔코더 안정 시간은 <b>142.662ms</b>로 요구 200ms에 못 미쳤습니다. 토크 OFF와 이후 바퀴 감속 기록을 확인했지만 이후 미수집 구간을 보간하지 않았고, 기존 실패를 PASS로 바꾸지 않았습니다. 정확한 과거 입력 nonce 나이와 단일 지연 원인은 원기록 부족으로 여전히 미확정입니다.</p>
<h2>시험과 범위</h2><table><tr><th>시험</th><th>결과</th><th>원문</th></tr>ROWS
<tr><td>장치 없는 safety 전체 160</td><td>PASS</td><td><a href="safety-tests02.log">최종 log</a></td></tr>
<tr><td>원 센서 저장자료 3시도</td><td>SHA 일치·센서 1508/1212/961개 해석 오류 0</td><td><a href="original-replay.json">원문 연결·재계산</a></td></tr>
<tr><td>실제 설치 App: 원 거실 복원·Isaac 표시·PC 준비</td><td>확인</td><td><a href="ui-session/session.json">실제 UI 기록</a></td></tr>
<tr><td>최종 설치 App: 원 SIM 실패 장면·시작 pose·침대 동일 목표 → 의자 → Stop/OFF/Disconnect·JSON 반출</td><td>두 목표 ARRIVED·FINALIZED 360이벤트</td><td><a href="sim-original-goals02/result.json">최종 결과</a> · <a href="sim-final-operation02.json">최종 반출</a></td></tr>
<tr><td>첫 후보: Stop/OFF/Disconnect → cold 재열기·JSON 반출</td><td>최종 cold 반출 complete·427개 이벤트/값 일치. raw JSON SHA는 숫자 표현 차이로 다름</td><td><a href="cold-receipt.json">비교 결과</a> · <a href="sim-cold-operation.json">실제 다운로드</a></td></tr>
<tr><td>새 빌드 실제 Pi 입력 유지·정지·수동/채팅/360/목적지</td><td>NOT_RUN</td><td>현재 현장 확인 응답 대기</td></tr></table>
<p>보조 그룹은 중복을 포함하므로 합산해 사용자 여정 수로 표시하지 않습니다. 입출력·고장 모델 시험은 실제 ROS/Pi 성적이 아닙니다. 초기 math import 및 보조시험 import 경로 오류는 설치 전에 수정했습니다. 시작 중 disabled 버튼을 일찍 누르려던 첫 시도는 실제 전환이 없었고, 준비 완료 뒤 성공한 클릭과 구분했습니다. 첫 JSON 반출은 Disconnect 처리 완료가 로그 화면에 갱신되기 전에 클릭해 IN_PROGRESS였습니다. 이 원본을 보존하고 cold 재열기에서 최종 기록을 별도로 반출했습니다. 별도 일반 모드·Explorer·전체 native 입력·OS 붙여넣기와 F01~F12 전체 재인수는 이번 한정 회귀에 포함하지 않습니다.</p>
<h2>실제 화면과 영상</h2><p>아래는 같은 설치 Test BrowserWindow의 실제 녹화입니다. 저장된 방의 회귀시험이며 새 생성 데모나 실물 촬영이 아닙니다.</p>
<img src="sim-original-goals02/chair-result.png" alt="최종 실제 SIM 의자 도착"><video controls preload="metadata" src="sim-original-goals02/app-screen.mp4"></video>
<details><summary>원 거실 및 PC 준비 화면</summary><img src="ui-session/restored-living-room.png"><img src="ui-session/pc-preparation.png"></details>
<h2>실행 ID·SHA·잔여</h2><p>최종 SIM operation <code>OP</code>; bed request <code>BED</code>, chair request <code>CHAIR</code>. 새 모델 호출·비용 0, 추가 USD50 장부 잔여 <b>USD46.8551834</b> 그대로이며 공급자 계정 잔액은 조회하지 않았습니다. 기존 USD20 장부도 변경하지 않았습니다. 새 의존성·ROS/OS 변경·삭제·Git 게시·영상 업로드 없음. 다음 실물 확인은 새 기능 추가 없이 같은 앱의 첫 저속 정지 관측부터 시작합니다.</p>
<ul>SOURCES</ul><p><a href="result.json">전체 기계 판독 결과</a></p></article></html>'''
    for key,value in [('RELEASE',install['release_id']),('SOURCES',sources),('SOURCE',install['source_manifest_sha256']),('SCHEMA_URL',replay['source_schema']),('ROWS',rows),
            ('LAUNCH',sim['identity']['engine']['launch_id']),('OP',sim['operation_id']),('BED',sim['steps'][0]['command']['request_id']),('CHAIR',sim['steps'][1]['command']['request_id'])]:report=report.replace(key,value)
    (OUT/'report.html').write_text(report,encoding='utf-8')
    print(json.dumps(dict(status=result['status'],report=str(OUT/'report.html'),operation_complete=final_operation['manifest']['complete'])))


if __name__=='__main__':main()
