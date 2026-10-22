# SPDX-License-Identifier: Apache-2.0
"""Local, no-device evidence for the Prepare diagnostic/loader changes."""
from datetime import datetime,timezone
import hashlib
import html
import json
import os
from pathlib import Path
import shutil
import sys
import time
from types import SimpleNamespace
from uuid import uuid4
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/guard-diagnostics-20261020'
for name in ('twinpulse_app','twinpulse_core','twinpulse_provider'):
    sys.path.insert(0,str(ROOT/'packages'/name/'src'))
sys.path.insert(0,str(ROOT/'packages/twinpulse_robot_safety'))
from twinpulse_app.physical_live_session import reviewed_bundle
from twinpulse_app.physical_live_history import recover_live_history
from twinpulse_app.windows_package import verify_package
from twinpulse_core.robot_lineage import twin_context
from fleet_control import RobotControl
from fleet_worker import export_sources
import guard_runtime


def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def write(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
def identity(path):
    path=Path(path);raw=path.read_bytes()
    return dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def no_device_capture():
    directory=OUT/'offline01'
    if (directory/'result.json').exists():return read(directory/'result.json')
    directory.mkdir(exist_ok=False)
    source_sha,_,source_files=reviewed_bundle(ROOT)
    operation=uuid4().hex;request=uuid4().hex
    twin=twin_context('offline_guard_diagnostic','offline_conversation',dict(engine_connected=True,
        snapshot=dict(applied_revision='offline_revision_not_a_user_twin'),
        engine_session_id='offline_engine',stage_epoch='offline_stage'))
    context=dict(schema='physical-live-start-2.0',operation_id=operation,robot_id=uuid4().hex,
        project_id=twin['project_id'],connection_epoch=uuid4().hex,binding_sha256='a'*64,
        worker_sha256=source_sha,source_twin_context=twin)
    events=[dict(context,schema='physical-live-pc-start-2.0',worker_sources=source_files,
        evidence_origin='LOCAL_NO_DEVICE_FAILURE_INJECTION')]
    def emit(kind,data):
        events.append(dict(schema='physical-live-event-2.0',**{k:context[k] for k in
            ('operation_id','robot_id','project_id','connection_epoch')},
            sequence=len(events),kind=kind,robot_monotonic_s=time.monotonic(),
            source_twin_context_id=twin['context_id'],data=data))
    local=directory/'operation';local.mkdir()
    owner=RobotControl(context,local,emit,SimpleNamespace())
    original_bytes=b'LOCAL FAULT INPUT ONLY: simulated compiler output\n'+bytes(range(256))*300
    def missing(command,log,env):
        log.write_bytes(original_bytes)
        raise FileNotFoundError(2,'No such file',str(log.parent/'build/libturtlebot3_node_lib.so'))
    try:
        guard_runtime.ensure(ROOT/'packages/twinpulse_robot_safety',directory/'isolated-home',runner=missing,
            diagnostic=lambda row,log:owner._guard_diagnostic(request,'EXPLICIT_PREPARE',row,log))
        raise AssertionError('Injected original failure was not raised')
    except FileNotFoundError as exc:
        assert exc.filename.endswith('libturtlebot3_node_lib.so')
    exported=export_sources(local,emit,required_members=('output-guard-build.jsonl','output-guard-build.log'))
    emit('cleanup',dict(subsystem='session',confirmed=False))
    raw=b''.join((json.dumps(event,ensure_ascii=False)+'\n').encode() for event in events)
    segment=directory/'events-00000.jsonl';segment.write_bytes(raw)
    receipt=dict(event_count=len(events),bytes=len(raw),complete=False,
        segments=[dict(path=segment.name,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())])
    write(directory/'receipt.json',receipt)
    restored=recover_live_history(directory,receipt,**{k:context[k] for k in
        ('operation_id','project_id','robot_id','connection_epoch','binding_sha256','source_twin_context')})
    diagnostic=next(e['data']['build_diagnostic'] for e in reversed(restored['events'])
        if e['data'].get('action')=='output_guard_diagnostic')
    assert diagnostic['binding']['request_id']==request
    assert diagnostic['binding']['source_twin_context_id']==twin['context_id']
    assert diagnostic['error']['exception_type']=='FileNotFoundError'
    assert diagnostic['active_step']=='CONFIGURE_GUARD'
    assert restored['source_export']==exported and restored['cleanup_confirmed'] is False
    assert restored['field_trial_resolution']['authority_restored'] is False
    tail=diagnostic['log_tail'];copied=(local/'output-guard-build.log').read_bytes()
    copied=copied[tail['operation_log_offset']:tail['operation_log_offset']+tail['exported_bytes']]
    assert copied==original_bytes[-65536:]
    assert hashlib.sha256(copied).hexdigest()==tail['sha256']
    result=dict(scope='LOCAL_NO_DEVICE_FAILURE_INJECTION_NOT_USER_ACCEPTANCE',
        operation_id=operation,request_id=request,source_twin_context=twin,worker_sha256=source_sha,
        event_count=len(events),exception_preserved=True,export_and_cold_exact=True,
        log_tail_bytes=len(copied),log_tail_original_offset=tail['source_offset'],
        log_tail_sha256=tail['sha256'],original_log_complete=False,authority_restored=False,
        files=[identity(segment),identity(local/'output-guard-build.jsonl'),identity(local/'output-guard-build.log')],
        diagnostic=diagnostic)
    write(directory/'result.json',result)
    return result


def main():
    OUT.mkdir(exist_ok=True)
    offline=no_device_capture()
    active=read(Path(os.environ['LOCALAPPDATA'])/'TwinPulse/installed/active-release.json')
    package=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/installed'/Path(active['exe']).parent
    verified=verify_package(package)
    manifest=read(package/'windows-release-manifest.json')
    assert manifest['capabilities']['physical_robot'] is True
    sources=read(package/'_internal/resources/source-manifest.json')
    # The builder maps this locked dependency into a virtual packaged path;
    # verify_package checks those bytes, while checkout comparison uses repo paths.
    repository={name:sha for name,sha in sources.items()
        if not name.startswith('apps/twinpulse-desktop/testing/playwright-core/')}
    for name,sha in repository.items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==sha,name
    ui=read(OUT/'ui01/session.json')
    assert ui['identity']['engine']['release_id']==active['release_id']
    assert not ui['errors']
    original=ROOT/'outputs/robot-powered-20261020-final01b'
    actual=read(OUT/'ui01/restored-operation.json');expected=read(original/'final-operation.json')
    assert actual['operation_id']==expected['operation_id']
    assert actual['events']==expected['events']
    assert actual['manifest']['worker_sources']==expected['manifest']['worker_sources']
    exact=[]
    for name in ('raw-receipt.json','raw-events-00011.jsonl'):
        assert (OUT/'ui01'/name).read_bytes()==(original/name).read_bytes()
        exact.append(identity(OUT/'ui01'/name))
    http=read(OUT/'ui01/fleet-http-receipts.json')
    assert all(row['action']=='focus' for row in http['requests'])
    launch=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime/launches'/ui['identity']['engine']['launch_id']
    frozen=OUT/'launch-logs';frozen.mkdir(exist_ok=True)
    logs=[]
    for name in ('backend.log','desktop-host.log','engine.log','engine-result.json','engine-status.json','supervisor-status.json','cleanup-receipt.json'):
        target=frozen/name
        if not target.exists():shutil.copy2(launch/name,target)
        assert target.read_bytes()==(launch/name).read_bytes()
        logs.append(identity(target))
    shutdown=read(frozen/'cleanup-receipt.json')
    assert shutdown['launch_id']==ui['identity']['engine']['launch_id'] and shutdown['owned_processes_stopped'] is True
    assert not (launch.parents[1]/'launcher.lock').exists()
    tests=[]
    for name in ('tests-initial.xml','tests-final.xml','contracts.xml','ui-tests.xml'):
        document=ET.parse(OUT/name).getroot()
        suites=[document] if document.tag=='testsuite' else document.findall('testsuite')
        count={key:sum(int(s.get(key,'0')) for s in suites) for key in ('tests','failures','errors','skipped')}
        assert count['failures']==count['errors']==0
        tests.append(dict(file=name,**count))
    rejected=read(ROOT/'outputs/robot-field-ready-20261020/build11/dist/TwinPulse/windows-release-manifest.json')
    assert rejected['capabilities']['physical_robot'] is False
    result=dict(generated_at=datetime.now(timezone.utc).isoformat(),
        verdict='THREE_CHANGES_IMPLEMENTED_PC_VERIFIED_TARGET_NOT_RUN',active_install=active,installed=verified,
        capability=manifest['capabilities'],source_files_match_checkout=True,
        repository_files_compared=len(repository),locked_dependency_files_verified=len(sources)-len(repository),
        original_failure_operation=expected['operation_id'],cold_ui=dict(launch_id=ui['identity']['engine']['launch_id'],
            original_events=len(expected['events']),restored_events=len(actual['events']),events_exact=True,
            worker_sources_exact=len(actual['manifest']['worker_sources']),raw_downloads=exact,
            robot_actions=[row['action'] for row in http['requests']],new_connection_or_motion=0,
            product_http_or_page_errors=ui['errors'],
            mode='Same installed Electron Test BrowserWindow; exec root Start, not Explorer/native'),
        offline_diagnostic=offline,tests=tests,logs=logs,
        shutdown=shutdown,
        changed_files=[identity(ROOT/name) for name in ('packages/twinpulse_robot_safety/guard_runtime.py',
            'packages/twinpulse_robot_safety/fleet_control.py','packages/twinpulse_robot_safety/fleet_worker.py',
            'apps/twinpulse-web/src/RobotFleet.tsx')],
        astra_review=dict(agent='astra_prepare_fix_review21',requested_model='gpt-6-astra',effort='xhigh',
            findings_fixed=['Atomic receipt replacement','Preserve original exception through child cleanup',
                'Reject linked cache/evidence paths','Latch diagnostic export incompleteness',
                'Bind computed source ID, receipt ID and final directory'],
            final='No unresolved confirmed source defect found in reviewed changes; actual Pi target remains NOT_RUN'),
        attempts=[dict(kind='Initial guard fixture',result='7 passed/1 failed: Windows C: split as Linux path separator; fixture corrected'),
            dict(kind='Build11',build_id=rejected['build_id'],result='Wrong default SIM channel; pre-install physical-capability check rejected; never installed'),
            dict(kind='Build12',build_id=active['release_id'],result='Development channel; 1669 files verified and installed'),
            dict(kind='Report first run',result='Naive checkout comparison encountered virtual packaged Playwright path; corrected to compare repository sources and verify packaged dependency bytes separately'),
            dict(kind='UI selector recovery',result='2 caption/ARIA timeouts, 1 transient row timeout, 1 hidden nested summary timeout; no product HTTP/page error')],
        not_run=['Actual new Pi ROS/ARM build','Actual target -h/ELF loader','Device readback','Sensor acquisition',
            'Physical driving/braking','Full new-release SIM journey','Native Explorer/OS paste'],
        budget=dict(new_nebius_http=0,new_usd='0',additional_50_cumulative='3.5109468',additional_50_remaining='46.4890532',
            previous_20_separate_total='14.9450973',previous_20_unknown_included='0.4770432'),
        preserved=dict(original_photos=True,user_projects=True,original_failure_bytes=True,no_git_publication=True,no_dependencies_installed=True),
        disk=dict(before_build_bytes_free=40206213120,after_app_exit_bytes_free=39169785856,
            scope='Observed whole-volume free-space difference, not claimed package allocation; no deletion'),
        media=[identity(OUT/'ui01/app-screen.mp4'),identity(OUT/'ui01/03-history-id.png')])
    write(OUT/'analysis.json',result)
    dump=html.escape(json.dumps(result,ensure_ascii=False,indent=2))
    (OUT/'report.html').write_text('''<!doctype html><html lang="ko"><meta charset="utf-8"><title>TwinPulse Prepare 보완 검증</title>
<style>body{font:16px/1.65 system-ui;max-width:1080px;margin:36px auto;padding:0 22px;color:#172b35}img,video{max-width:100%}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f5f6;padding:18px}h1{font-size:27px}</style>
<h1>Prepare 세 보완 · 구현/설치 및 PC 검증 완료</h1>
<p>원 예외 보존, operation에 결속한 빌드 진단 반출, 최종 위치의 실제 실행파일 로더 검사를 구현했습니다. 실제 Pi에서 새 ROS/ARM 빌드·로더·장치 readback·주행을 수행한 성적은 아닙니다.</p>
<p>명시 Prepare는 source SHA의 새 빌드를 검사하고, 캐시 재사용도 -h/LD_BIND_NOW=1 검사를 거칩니다. -h는 ROS 초기화와 장치 생성 전에 종료합니다. 검사 실패는 원래 오류·단계·종료코드·누락 경로·소스 ID를 남기며 장치 lease 전에 거절합니다. 원자 receipt 갱신, 정리 오류 분리, 링크 경로 거절, 진단 저장 실패의 incomplete 유지, source ID 결속도 Astra 검토 후 보완했습니다.</p>
<p>output-guard-build.jsonl과 output-guard-build.log는 기존 runtime 원문 분할에 들어갑니다. 로그 복사는 마지막 64KiB·원 offset·SHA·잘림 여부를 기록하고 전체 원문으로 위장하지 않습니다. 예전 실패 실행에 없던 진단을 새로 채워 넣지 않았습니다.</p>
<p>실제 설치 Electron Test의 Home→원 거실→Reopen/View→로봇 과거 로그→JSON/receipt/실패 분할 다운로드→Exit를 확인했습니다. 원 107/107 기록·84 sources와 원 bytes/SHA가 정확합니다. 새 connect/Prepare/센서/바퀴 요청은 0건입니다. 이 검증은 새 진단 파이프라인의 무장치 실패 주입·cold 재생과 구분합니다.</p>
<p>로컬 tests-final 61, 별도 contracts56, UI136은 각각의 보조 집합이며 중복 합산하지 않습니다. 잘못된 Windows fixture와 잘못된 첫 빌드 채널은 시도 이력에 남겼습니다. 올바른 현장 기능이 없는 패키지는 설치 전 거절했습니다.</p>
<p>다음 실제 검증은 현재 설치 App의 Connect→Prepare(새 빌드/최종 loader/readback)부터입니다. 현재 전체 실물 준비/주행 성공으로 표시하지 않습니다. 원 FileNotFoundError의 실제 누락 파일은 당시 반출에 없어 단독 원인 확정도 계속 미완료입니다.</p>
<p><a href="ui01/app-screen.mp4">이번 실제 설치 앱 검증 녹화</a> · <a href="offline01/result.json">무장치 실패 원문·ID 연결 검증</a> · <a href="analysis.json">모든 ID/SHA·시도·검증·비용</a> · <a href="../robot-powered-20261020-final01b/report.html">원 실물 실패와 Astra 검토</a></p>
<img src="ui01/03-history-id.png" alt="같은 설치 앱에서 원 실패 operation을 열어 확인한 화면">
<p>새 Nebius HTTP/USD0, 추가50 잔여 USD46.4890532. 기존 사진·프로젝트·실패 기록 보존. 새 의존성/ROS/Isaac 설치·삭제·Git 게시 없음.</p><pre>'''+dump+'</pre></html>',encoding='utf-8')
    print(json.dumps(dict(verdict=result['verdict'],release=active['release_id'],offline_operation=offline['operation_id'],ui_launch=result['cold_ui']['launch_id'])))


if __name__=='__main__':main()
