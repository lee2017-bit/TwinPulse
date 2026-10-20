# SPDX-License-Identifier: Apache-2.0
"""Local Git/private-archive and exact cleanup receipt; no network or runtime."""
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/github-preservation-20261020'
PRUNE = ROOT / 'outputs/build-retention-20261020-applied'


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def link(path, label=None):
    return '<a href="'+escape(path, quote=True)+'">'+escape(label or path)+'</a>'


if __name__ == '__main__':
    remote = read(OUT/'remote-verification.json')
    plan = read(PRUNE/'plan.json')
    result = read(PRUNE/'result.json')
    after = read(OUT/'protected-after.json')
    if remote['status'] != 'REMOTE_SOURCE_AND_ARCHIVE_VERIFIED' or after['status'] != 'PASS':
        raise ValueError('REMOTE_PRESERVATION_AND_LOCAL_INTEGRITY_REQUIRED')
    removed = [r for r in result['results'] if r['status'] == 'REMOVED']
    failed = [r for r in result['results'] if r['status'] != 'REMOVED']
    outside = [r['path'] for r in result['results'] if not any(Path(r['path']).is_relative_to(Path(a)) and Path(r['path']) != Path(a) for a in plan['allowed_roots'])]
    if outside:
        raise ValueError('OUTSIDE_BOUNDARY_RESULT')
    roles = ['Current scoped SIM/PC package', 'Latest compact-UI passing rollback',
             'Last full9-role integration rollback', 'Required original failed reproduction']
    summary = dict(schema='scoped-git-preservation-and-retention-report-1.0',at=datetime.now(timezone.utc).isoformat(),
        status='PASS_PRESERVATION_AND_SCOPED_CLEANUP' if not failed else 'PARTIAL_CLEANUP_WITH_PROTECTED_DATA_VERIFIED',
        remote=remote, allowed_roots=plan['allowed_roots'], removed=len(removed), failed=failed,
        before_free_bytes=result['before_free_bytes'], after_free_bytes=result['after_free_bytes'],
        observed_free_increase_bytes=result['observed_free_increase_bytes'], outside_targets=outside,
        pins=[dict(release_id=i,role=r) for i,r in zip(plan['pins'],roles)],
        protected_running_references=after.get('protected_running_references',[]),
        protected_files=len(after['protected']),protected_bytes=sum(v['bytes'] for v in after['protected'].values()),
        remaining_installed=after['remaining_installed'],source_maps=len(list((PRUNE/'source-maps').glob('*-resources.json'))),
        unique_source_objects=len(list((PRUNE/'source-objects').iterdir())),
        source_and_physical_scope='Same frozen package,1668 files; scoped earlier SIM/PC acceptance,not new full-product/native or physical acceptance.',
        limitations=['No runtime/model/robot restart or new physical test in this maintenance task.',
            'Frames/videos/sensor originals/projects remain local. No data outside the exact TwinPulse deletion roots is removed.',
            'Obsolete EXE bytes are not promised recoverable. Exact owned source/resource objects and manifests are kept; four full pinned packages remain.',
            'Two older packages still referenced by running processes are protected rather than force-terminated.',
            'This fixed-checkpoint command is not an installed-app automatic GC service; future checkpoint pins/proof require review.'],
        provider_http=0,provider_usd=0,last_recorded_additional50_remaining_usd='46.8551834')
    (OUT/'result.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    html='''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>TwinPulse 소스 보존과 경로 제한 정리</title><style>body{font:16px/1.65 system-ui;max-width:1100px;margin:32px auto;padding:0 22px;background:#f4f7f9;color:#193441}section{background:white;border:1px solid #d5e1e6;border-radius:12px;padding:22px;margin:22px 0}th,td{padding:9px;border-bottom:1px solid #ddd;text-align:left;vertical-align:top}table{width:100%;border-collapse:collapse}code,td{overflow-wrap:anywhere}a{color:#087768}</style><h1>TwinPulse 소스 보존과 경로 제한 정리</h1>'''
    html+='<p>2026-10-20 · '+escape(summary['status'])+'</p><section><h2>GitHub 보존</h2><p>기존 비공개 저장소를 유지했습니다. 최신 runtime 소스와 검토된 유지보수 도구를 main에 보존하고, 원1668-file 설치본 ZIP189,173,012B를 비공개 prerelease 복구 자료로 올렸습니다. 다시 내려받아 SHA <code>6458ee3803a2a8a4e2a5d8b44997efebc313b290f09ff32c85222f3662d596a5</code> 일치를 확인한 뒤 삭제를 시작했습니다.</p><p>'+link('https://github.com/lee2017-bit/TwinPulse/commit/'+remote['source_commit'],'보존된 소스 commit')+' · '+link(remote['release_url'],'복구 ZIP Release')+' · '+link('remote-verification.json','원격 재다운로드 검증')+'</p><p>SIM/PC 범위의 복구 checkpoint입니다. 새 full-generation/전체9-role/native/실물 성공으로 승격하지 않았고, package의 원 dirty-build manifest도 고치지 않았습니다. 키·개인사진·프로젝트·센서 원문·실패 영상은 업로드하지 않았습니다.</p></section>'
    html+='<section><h2>삭제 범위</h2><ul>'+''.join('<li><code>'+escape(p)+'</code></li>' for p in plan['allowed_roots'])+'</ul><p>유효한 TwinPulse package manifest로 식별한 오래된 설치본/배포 복사본,해당 builder work/staging/desktop-build와 같은 build ID의 ZIP만 제거했습니다. 경로 경계·부모/구성원 reparse·실행 참조·현재 포인터를 검사했습니다. 경로 guard의 외부/root/비정규8개 거절·정상2개 통과,새 보조75tests(1skip)를 확인했습니다. 원본 upstream LICENSE의 공백은 변경하지 않았습니다.</p><p><b>'+str(len(removed))+'개 target 제거 / '+str(len(failed))+'개 실패 / 범위 밖0</b>. '+link('../build-retention-20261020-applied/plan.json','정확한 절대경로 계획')+' · '+link('../build-retention-20261020-applied/result.json','실제 삭제 결과')+'</p></section>'
    html+='<section><h2>실제 공간 변화</h2><table><tr><th>측정</th><th>GB(10⁹ bytes)</th></tr>'+''.join('<tr><td>'+name+'</td><td>'+format(value/1e9,'.3f')+'</td></tr>' for name,value in [('삭제 직전 여유',result['before_free_bytes']),('삭제 후 여유',result['after_free_bytes']),('관측 여유 증가',result['observed_free_increase_bytes'])])+'</table><p>파일 길이 합과 회수 공간은 다릅니다. 압축/hardlink 공유와 Windows paging 등 동시 변화가 있으므로 실제 free-space 차이를 보고합니다. 이전 감사의 outputs/설치본 외에 artifacts에도 generated ZIP/빌드가 있어 이번 명세에 포함했습니다. Docker/WSL·Isaac·Windows pagefile·이전 Codex 경로는 삭제 대상이 아닙니다.</p></section>'
    html+='<section><h2>보호와 사후 검사</h2><table><tr><th>보호본</th><th>범위</th></tr>'+''.join('<tr><td><code>'+escape(i)+'</code></td><td>'+escape(r)+'</td></tr>' for i,r in zip(plan['pins'],roles))+'</table><p>추가 실행 참조 보호: '+escape(', '.join(after.get('protected_running_references',[])))+'. 강제 종료하지 않았습니다. 총 설치본 '+str(len(after['remaining_installed']))+'개를 남겼습니다.</p><p>프로젝트·장비 센서 원문·원 ITM0018 사진·기존 검증 PNG 등 '+str(summary['protected_files'])+'개 / '+str(summary['protected_bytes'])+'B의 전후 SHA가 동일합니다. runtime 소스는 원 설치 manifest와 일치하며 유지한 package를 다시 전체 hash 검증했습니다. 원 로그·녹화 PNG/MP4·사용자 사진/프로젝트는 삭제하지 않았습니다.</p><p>'+link('protected-before.json','원본 hash 목록')+' · '+link('protected-after.json','사후 동일/유지 package 검사')+'</p><p>옛 package의 source/resources는 SHA별 '+str(summary['unique_source_objects'])+'개 object와 '+str(summary['source_maps'])+'개 version map으로 따로 보존했습니다. 삭제된 EXE의 정확한 bytes 복원을 보장하지 않습니다.</p></section>'
    html+='<section><h2>남은 범위</h2><ul>'+''.join('<li>'+escape(x)+'</li>' for x in summary['limitations'])+'</ul><p>새 LLM HTTP/USD0,마지막 추가USD50 장부잔여46.8551834/이전USD20 별도 불변. 이 유지보수 작업은 API 모델 시험·새 설치·로봇 조작이 아닙니다. 경로 제한을 AGENTS와 프로젝트 메모리에 남깁니다.</p><p>'+link('result.json','전체 집계')+' · '+link('../robot-protocol-prep-20261020/report.html','이전 실제 설치 SIM/PC 시험과 녹화')+'</p></section></html>'
    (OUT/'report.html').write_text(html,encoding='utf-8')
    print(json.dumps(dict(status=summary['status'],removed=len(removed),failed=len(failed),free_after=result['after_free_bytes'],recovered=result['observed_free_increase_bytes']),ensure_ascii=False))
