# SPDX-License-Identifier: Apache-2.0
"""Append a hash-bound follow-up without erasing any earlier failed evidence.

No App/model/robot calls. Historical root-cause uncertainty and current-release
acceptance are separate verdicts; a later PASS never rewrites an original FAIL.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import subprocess
import sys

from verify_robot_lineage_offline import source_receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    parser.add_argument('--tag', default='09')
    parser.add_argument('--final-review', action='store_true')
    args = parser.parse_args()
    root = args.root.resolve()
    tag = args.tag
    if not tag.isdigit() or len(tag) != 2:
        raise ValueError('Explicit two-digit evidence suffix required')

    def read(name):
        return json.loads((root/name).read_text(encoding='utf-8-sig'))

    def digest(name):
        return sha256((root/name).read_bytes()).hexdigest()

    def save(name, value):
        path = root/name
        if path.exists():
            if read(name) != value:
                raise ValueError('Different existing evidence: '+name)
            return
        with path.open('x', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)

    identity = source_receipt()
    audit_note = ''
    if args.final_review:
        audit=read(f'astra-final-audit{tag}.json')
        snapshot=root/'report-before-final-review.html'
        if not snapshot.exists():
            if digest('report.html')!=audit['reviewed_report_sha256']:
                raise ValueError('Current report is not the independently reviewed version')
            with snapshot.open('xb') as stream:stream.write((root/'report.html').read_bytes())
        if digest(snapshot.name)!=audit['reviewed_report_sha256']:
            raise ValueError('Reviewed report snapshot SHA mismatch')
        audit_note='<p>최종 독립 읽기감사: 현재 감독시험 진입판정에 반하는 확정 누락/숨은FAIL을 찾지 못했다.35근거/원보고서/새4영상 SHA를 대조했다. 실제Pi/제동/주행PASS나 과거원인해결이 아니다. <a href="astra-final-audit'+tag+'.json">감사 범위·원보고서SHA</a>. 영상 표시50개는 고유44파일이며 이전파생6개가 이력에서 중복표시된다.</p>'
    roles = dict(fresh=f'ui-fresh-{tag}/result.json', cold=f'ui-cold-{tag}/result.json',
                 lineage=f'lineage-{tag}/result.json', lineage_cold=f'lineage-cold-{tag}/result.json',
                 normal='normal-08/result.json', lifecycle='normal-lifecycle.json',
                 installation='installation-final08.json', supplementary='offline-final08/result.json',
                 budget=f'budget-final{tag}.json')
    records = {role: read(name) for role, name in roles.items() if (root/name).is_file()}
    for role in ('fresh', 'cold', 'lineage', 'lineage_cold'):
        value = records.get(role)
        if value and (value.get('status') not in ('PASS', 'FAIL') or
                      value.get('desktop', {}).get('engine', {}).get('release_id') != identity['release_id']):
            raise ValueError('In-progress/wrong-release journey: '+role)
    if 'fresh' not in records or 'budget' not in records:
        raise ValueError('Fresh result and final budget required')
    current = [role for role in ('fresh', 'cold', 'lineage', 'lineage_cold')
               if records.get(role, {}).get('status') != 'PASS']
    review = read('evidence-manifest.json')['physical_readiness_review']
    review['status'] = 'KNOWN_RUNTIME_BLOCKER' if current else 'SOFTWARE_NO_KNOWN_BLOCKER'
    review['unresolved'] = ['CURRENT_REQUIRED_JOURNEY_NOT_PASS:'+role for role in current]
    review['historical_root_causes_still_unknown'] = [
        'ISAAC_NATIVE_ACCESS_VIOLATION', 'ISAAC_STARTUP_120S_TIMEOUT', 'ORDINARY_DRIVE_REPLY_ABORT',
        'FRESH08_DISPLAY_FRAME_AGE_1014_789MS',
    ]
    review['scope_qualification'] = (
        'Current full installed journeys retain the original criteria. Historical failures and unknown causes remain open risks, '
        'not claimed fixed by rerun. Current failures/missing original conditions still veto; physical NOT_RUN is not its own prerequisite.'
    )
    review['evidence'].append(dict(path=f'astra-followup-review{tag}.json', sha256=digest(f'astra-followup-review{tag}.json')))
    review['evidence'].append(dict(path='evidence-gap09-review.json', sha256=digest('evidence-gap09-review.json')))
    manifest = dict(**identity, physical_readiness_review=review,
                    evidence=[dict(role=role, path=name, sha256=digest(name)) for role, name in roles.items() if role in records])
    manifest_name = f'evidence-manifest{tag}.json'
    save(manifest_name, manifest)
    gate_path = root/f'gate-result{tag}.json'
    if not gate_path.exists():
        code = subprocess.run([sys.executable, str(Path(__file__).with_name('verify_robot_focus_gate.py')),
                               '--manifest', str(root/manifest_name), '--output', str(gate_path)],
                              capture_output=True, text=True).returncode
        if code not in (0, 1):
            raise ValueError('Evidence gate execution error')
    gate = read(gate_path.name)
    for label, broken_role in (('broken-stop', None), ('original-fresh08', 'fresh')):
        negative = json.loads(json.dumps(manifest))
        if broken_role:
            negative['evidence'] = [dict(entry, path='ui-fresh-08/result.json', sha256=digest('ui-fresh-08/result.json'))
                                    if entry['role'] == broken_role else entry for entry in negative['evidence']]
        else:
            negative['physical_readiness_review']['unresolved'] = ['LIVE_STOP_BROKEN_NEGATIVE_GATE_TEST']
        negative_name = f'gate-negative-{label}-{tag}-manifest.json'
        negative_result = f'gate-negative-{label}-{tag}-result.json'
        save(negative_name, negative)
        if not (root/negative_result).exists():
            code = subprocess.run([sys.executable, str(Path(__file__).with_name('verify_robot_focus_gate.py')),
                                   '--manifest', str(root/negative_name), '--output', str(root/negative_result)],
                                  capture_output=True, text=True).returncode
            if code != 1:
                raise ValueError('Negative evidence was not rejected: '+label)
        issues = read(negative_result)['issues']
        if (broken_role and 'RUN_NOT_PASS:fresh' not in issues) or (not broken_role and 'KNOWN_PHYSICAL_BLOCKER:LIVE_STOP_BROKEN_NEGATIVE_GATE_TEST' not in issues):
            raise ValueError('Negative evidence rejection is missing its original condition: '+label)
    fresh = records['fresh']
    trace = fresh.get('viewport_receipt_trace', {})
    receipts = trace.get('receipts', [])
    displays = fresh.get('display_samples', [])
    trace_review = dict(enabled=trace.get('enabled'), metadata_count=sum(v.get('path') == '/v1/product/viewport' for v in receipts),
                        jpeg_receipt_count=sum(v.get('path') == '/v1/product/viewport/current' for v in receipts),
                        display_count=len(displays), maximum_sampled_frame_age_ms=max((v['frame_age_ms'] for v in displays), default=None),
                        frame_age_at_least_1s=sum(v['frame_age_ms'] >= 1000 for v in displays),
                        note='Existing GET bodies/headers only. captured_at_ms is capture scheduling time, not GPU callback completion. No extra fetch/Fetch interception; no claim of phase timings absent from original logs.')
    save(f'viewport-trace-review{tag}.json', trace_review)
    originals = []
    source_by_release = {value['release_id']:value['source_sha256'] for value in read('build-identities.json') if value.get('release_id')}
    for folder in sorted(root.iterdir()):
        if not folder.is_dir() or not (folder/'result.json').is_file():
            continue
        value = read(folder.name+'/result.json')
        engine = value.get('desktop', value.get('identity', {})).get('engine', {})
        release = engine.get('release_id', value.get('release_id'))
        originals.append(dict(path=folder.name+'/result.json', sha256=digest(folder.name+'/result.json'),
                              status=value.get('status'), launch_id=engine.get('launch_id', value.get('launch_id')),
                              release_id=release, source_sha256=value.get('source_sha256', source_by_release.get(release)),
                              project=value.get('project'), conversation=value.get('conversation'), input_sha256=value.get('input_sha256'),
                              operation_id=value.get('operation_id'),
                              elapsed_step_ms=sum(step.get('elapsed_ms', 0) for step in value.get('steps', []))))
    save(f'all-attempts{tag}.json', originals)
    current_videos = []
    for folder in (f'recording-fresh{tag}', f'recording-cold{tag}', f'recording-lineage{tag}', f'recording-lineage-cold{tag}'):
        video = root/folder/'app-screen.mp4'
        if not video.is_file():
            continue
        clock = read(folder+'/frame-times.json')
        expected = [(frame['at']-clock['frames'][0]['at'])/1000 for frame in clock['frames']]
        expected.append((clock['end']-clock['frames'][0]['at'])/1000)
        probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-select_streams', 'v', '-show_packets',
                            '-show_entries', 'packet=pts_time:format=duration', '-of', 'json', str(video)], text=True))
        pts = [float(packet['pts_time']) for packet in probe['packets']]
        if len(pts) != len(expected):
            raise ValueError('New recording frame count changed: '+folder)
        maximum = max(abs(a-b) for a, b in zip(pts, expected))
        duration = float(probe['format']['duration'])
        if maximum > .05 or abs(duration-expected[-1]) > .1:
            raise ValueError('New recording clock is not qualified: '+folder)
        current_videos.append(dict(path=folder+'/app-screen.mp4', sha256=digest(folder+'/app-screen.mp4'),
                            frame_times_sha256=digest(folder+'/frame-times.json'), source_frames=len(clock['frames']),
                            encoded_frames=len(pts), duration_s=duration, expected_s=expected[-1], maximum_pts_error_s=maximum,
                            maximum_no_new_observation_s=max((b-a for a, b in zip(expected, expected[1:])), default=0),
                            scope='Actual sampled renderer frames, recorded holds, no interpolated or unseen motion; not native or physical video'))
    save(f'video-receipts{tag}.json', current_videos)
    base = root/f'report-before{tag}.html'
    if not base.exists():
        with base.open('xb') as stream:
            stream.write((root/'report.html').read_bytes())
    esc = html.escape
    link = lambda name, title: '<a href="'+esc(name)+'">'+esc(title)+'</a>'
    parts = ['<!doctype html><html lang="ko"><meta charset="utf-8"><title>TwinPulse 사전 준비 최종 검증</title>',
             '<style>body{font:16px/1.65 system-ui;max-width:1200px;margin:30px auto;padding:0 22px;color:#182c39;background:#f7f9fa}table{border-collapse:collapse;width:100%}th,td{border:1px solid #bdcbd3;padding:8px;text-align:left;overflow-wrap:anywhere}img,video{max-width:100%;background:#122028}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#e8eef2;padding:12px}a{color:#005c83}</style>',
             '<h1>로봇 OFF 사전 준비 · 재개 후 최종 검증</h1>',
             '<p>현재 판정: <strong>'+esc(gate['status'])+'</strong>. 다음은 같은 동결 설치08의 새 전체 여정'+esc(tag)+' 결과다. 과거08 실패를 수정·삭제하거나 별도 진단 성공을 합친 성적이 아니다. 현재 구체적 실패/필수 누락은 계속 차단한다. 반대로 과거 원인 UNKNOWN이라는 문자열만으로 무한 재시험하지 않는다. 새 PASS는 과거 원인 해결의 증거가 아니다.</p>',
             audit_note,
             '<pre>'+esc(json.dumps(identity, ensure_ascii=False, indent=2))+'</pre>',
             '<p>'+link(gate_path.name, '현재 SHA결속 인수 gate')+' · '+link(manifest_name, '현재 근거 명세')+' · '+link(f'all-attempts{tag}.json', '모든 시도·실행 ID·입력 SHA')+' · '+link(f'astra-followup-review{tag}.json', 'Astra 독립 재검토의 범위·판정 정정')+'</p>',
             '<h2>현재 설치 필수 여정</h2><table><tr><th>여정</th><th>판정</th><th>단계/실행ID</th></tr>']
    for role in ('fresh', 'cold', 'lineage', 'lineage_cold', 'normal', 'lifecycle', 'supplementary'):
        value = records.get(role, {})
        desktop = value.get('desktop', {}).get('engine', {})
        role_label = link(roles[role], role) if role in records else esc(role)
        parts.append('<tr><td>'+role_label+'</td><td>'+esc(value.get('status', 'NOT_RUN'))+'</td><td>'+esc(str(len(value.get('steps', []))))+' / '+esc(desktop.get('launch_id', value.get('launch_id', '')))+'</td></tr>')
    parts += ['</table><p>같은08의 진단08b7단계(최초 읽기3초 만료·회복/전환 회복·native닫기1POST202), 일반 native닫기 두 번과 설치1619파일exact는 별도 원문으로 결속한다. Test BrowserWindow의 클릭/키 입력이지 전체 native/Explorer더블클릭/OS붙여넣기/실제Windows DPI 시험은 아니다.</p>',
              '<p>09의 기능 단계32/13/8/4 PASS와 달리 최종 증거 gate는 Stop all 응답의 result_robots 누락을 실제 거절했다. 원인은 시험 observer가 단일Stop일 때만 ACK본문을 보존한 조건문이었다. 제품의 정지 실패나 원09 증거 보완으로 위장하지 않았다. 실제stop/stop_all 보존을 공통화하고 fresh마감 자체검사를 추가한 뒤 새'+esc(tag)+' 전체 여정을 실행했다. 원09 result/게이트FAIL은 불변이다. '+link('evidence-gap09-review.json', '기록 누락 원인·정확한 수정 범위')+'</p>',
              '<h2>새 화면 추적 / 기준 유지</h2><pre>'+esc(json.dumps(trace_review, ensure_ascii=False, indent=2))+'</pre>',
              '<p>원fresh08의 마지막JPEG뒤 metadata GET200/약3.6–15ms와 위치 telemetry는 계속 갱신됐지만 추가 JPEG요청이 없었다. 전체Wi-Fi/Kit정체로 단정할 근거가 없다. 새 추적은 기존metadata/frame identity와JPEG header를 기록할 뿐, 관측하지 않은GPU callback/encode/서버접수 시각을 만들어내지 않는다. 원1초·200/250/350/400ms, 속도·기하 조건을 늘리지 않았다.</p>',
              '<h2>실제 현재 화면</h2>']
    for name in ('two-connected.png', 'held-60s.png', 'turn-scan-complete.png', 'failure-15.png', 'field-setup.png'):
        path = f'ui-fresh-{tag}/'+name
        if (root/path).is_file():
            parts.append('<h3>'+esc(path)+'</h3><img loading="lazy" alt="실제 설치 App 화면" src="'+esc(path)+'">')
    parts.append('<h2>시간축을 대조한 실제 화면 녹화</h2><p>무음·같은 Electron renderer 표본 녹화다. 원본30개 중29개는 긴 정지화면 유지 구간을 MP4 트랙 길이에 반영하지 못해 시간 판정에 부적합했다. 원본은 보존하고 현재08의6개는 B-frame 없이 원 PTS와 종료 유지시간을 반영한 파생본을 만들었다. 프레임PTS 오차는 최대20ms였다. 표본 사이 빈 구간은 마지막 화면을 유지하며, 그동안 실제 화면이 정지했거나 움직였다는 증거는 아니다. '+link('derived-video-receipts.json', '원본/파생 SHA·시계·누락 구간')+' · '+link('video-clock-review.json', '원30개 시간 한계')+'</p>')
    parts.append('<p>'+link(f'video-receipts{tag}.json', '새4개 녹화의 원 frame clock·PTS·SHA 대조')+'</p>')
    for video in current_videos:
        parts.append('<h3>'+esc(video['path'])+' · '+esc(str(video['duration_s']))+'초 / 원 clock 직접 대조</h3><video controls preload="none" src="'+esc(video['path'])+'"></video>')
    parts.append('<details><summary>이전08 실패·독립 진단의 시간축 보존 파생 영상6개</summary>')
    for video in read('derived-video-receipts.json'):
        parts.append('<h3>'+esc(video['path'])+' · '+esc(str(video['duration_s']))+'초</h3><video controls preload="none" src="'+esc(video['path'])+'"></video>')
    parts.append('</details>')
    budget = records['budget']
    parts.append('<h2>누적 비용 원장 구분</h2><table><tr><th>구간</th><th>새 HTTP</th><th>새 추정/미확정 USD</th><th>추가50 캠페인 누적 USD</th></tr>')
    for name in ('budget-final08.json','budget-final09.json',f'budget-final{tag}.json'):
        value=read(name)
        parts.append('<tr><td>'+link(name,name)+'</td><td>'+esc(str(value['new_http']))+'</td><td>'+esc(value['new_estimated_usd'])+' / '+esc(value['new_unknown_usd'])+'</td><td>'+esc(value['protected_additional_50_total'])+'</td></tr>')
    parts.append('</table><p>공급자 사용량/catalog 기반 추정이며 최종 청구서가 아니다. 이전20 캠페인의14.9450973(미확정.4770432포함)은 별도 불변이며 현재추가50의 누적에 중복 합산하지 않는다.</p>')
    parts += ['<h2>비용·실물·잔여</h2><pre>'+esc(json.dumps({key: value for key, value in budget.items() if key not in ('files', 'requests', 'new_requests')}, ensure_ascii=False, indent=2))+'</pre>',
              '<p>실물 로봇은 OFF이며 SSH·센서·모터0. 실제Pi부하/저장·물리제동/주행·세계정합은 NOT_RUN이며 그 시험 자체를 시작하기 위한 선행PASS가 아니다. 현장 충전선분리/둘레30cm/감독·즉시전원차단 확인 뒤 앱의 현재guard에 따라 첫시험을 진행한다. strict tracker가 불확실하면 stall 등은 INCONCLUSIVE로 남을 수 있다. 센서인증·물리성공·정밀자율주행을 약속하지 않는다.</p>',
              '<p>과거 native AV·120초 startup·정상drive abort와fresh08 화면공백의 근본원인은 여전히 UNKNOWN이다. 현재여정 PASS가 그 원인을 고쳤다는 뜻은 아니다. 재발하면 추가Start전에 원engine/launcher/matchingKit 로그를 즉시동결해야 한다. 오래된Kit로그1개는 원경로부재로 exact사본을 확보하지 못했고6원파일은 SHA대조보존했다. 새의존성/OS·driver·Isaac변경/삭제/Cloud/공개/Git쓰기0. 기존사진/프로젝트/실패/장부/dirty를 보존했다.</p>',
              '<h2>이전 마감 전 모든 시도·상세 구현·원FAIL 이력</h2><details><summary>이전 보고 내용 펼치기 — 아래 NOT_READY는 재개 전 시점의 판정</summary>']
    old = base.read_text(encoding='utf-8')
    parts.append(old[old.index('<h1>'):].removesuffix('</html>'))
    parts.append('</details></html>')
    report = '\n'.join(parts)
    (root/'report.html').write_text(report, encoding='utf-8')

    class Links(HTMLParser):
        def __init__(self):
            super().__init__(); self.refs = []
        def handle_starttag(self, tag, attrs):
            self.refs.extend(value for key, value in attrs if key in ('href', 'src') and value and not value.startswith(('http://', 'https://')))

    links = Links(); links.feed(report)
    missing = sorted(set(value for value in links.refs if not (root/value).is_file()))
    # Missing required roles are recorded as NOT_RUN text, not broken links.
    if missing:
        raise ValueError('Report references absent evidence: '+str(missing))
    video_refs={ref for ref in links.refs if ref.lower().endswith('.mp4')}
    qa_name='artifact-qa-final.json' if args.final_review else f'artifact-qa{tag}.json'
    save(qa_name, dict(status='PASS_LOCAL_ARTIFACTS_NOT_PHYSICAL_ACCEPTANCE', **identity,
         report_sha256=digest('report.html'), local_links=len(links.refs), images=report.count('<img '), videos=report.count('<video '),
         video_elements=report.count('<video '), unique_video_files=len(video_refs),
         source_unchanged=source_receipt() == identity, gate=gate['status'], physical_actions=0, missing=[],
         previous_report_path=base.name, previous_report_sha256=digest(base.name)))
    if args.final_review and not (root/'completion-verification-final.json').exists():
        runtime=Path(os.environ['LOCALAPPDATA'])/'TwinPulse/runtime'
        if (runtime/'launcher.lock').exists():
            raise ValueError('App still owns the runtime; do not close out as normally stopped')
        save('completion-verification-final.json',dict(checked_at_utc=datetime.now(timezone.utc).isoformat(), **identity,
             status=gate['status'], scope='SUPERVISED_TEST_ENTRY_NOT_PHYSICAL_QUALIFICATION',
             current_whole_journeys={role:records[role]['status'] for role in ('fresh','cold','lineage','lineage_cold')},
             report='report.html',report_sha256=digest('report.html'),gate=gate_path.name,gate_sha256=digest(gate_path.name),
             source_unchanged=source_receipt()==identity,launcher_lock_absent=True,physical_actions=0,
             physical_outcomes='NOT_RUN_ROBOT_OFF',historical_roots='UNKNOWN_OPEN_RISKS_NOT_CLAIMED_REPAIRED',
             prior_completion='completion-verification.json preserved as original NOT_READY'))
    print(json.dumps(dict(status=gate['status'], report=str(root/'report.html'), issues=gate['issues']), ensure_ascii=False))


if __name__ == '__main__':
    main()
