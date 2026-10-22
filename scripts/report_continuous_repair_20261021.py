# SPDX-License-Identifier: Apache-2.0
"""Consolidated local evidence, not a simulator/device/provider client."""
from datetime import datetime,timezone
from hashlib import sha256
from html import escape
from decimal import Decimal
import argparse
import json
import os
import re
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/robot-continuous-repair-20261021'
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
def digest(p):
    h=sha256()
    with p.open('rb') as stream:
        for b in iter(lambda:stream.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def info(p):return dict(path=str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p),bytes=p.stat().st_size,sha256=digest(p))
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')

def memory_components(row):
    """Same-row process projection, not a disjoint physical-RAM accounting."""
    labels=('Isaac/Kit','TwinPulse Electron/host','TwinPulse backend','DWM','Memory Compression','Other processes')
    totals={label:dict(observed_processes=0,working_set_bytes=0,private_committed_bytes=0,missing_counters=0) for label in labels}
    protected=row.get('protected_process_projection') or {}
    extras={p['pid']:p for p in protected.get('rows',[]) if 0<=row['at_ms']-protected.get('at_ms',0)<=3000}
    for process in row.get('processes',[]):
        p=dict(process);role=p.get('role','');name=p['name'].lower()
        for field in ('working_set_bytes','private_committed_bytes'):
            if p.get(field) is None and field in extras.get(p['pid'],{}):p[field]=extras[p['pid']][field]
        label=('Isaac/Kit' if role.startswith('engine') or role.startswith('owner') and name=='kit.exe'
            else 'TwinPulse Electron/host' if role.startswith('owner') else 'TwinPulse backend' if role.startswith('backend')
            else 'DWM' if name=='dwm.exe' else 'Memory Compression' if name=='memory compression' else 'Other processes')
        value=totals[label];value['observed_processes']+=1
        for field in ('working_set_bytes','private_committed_bytes'):
            if p.get(field) is None:value['missing_counters']+=1
            else:value[field]+=p[field]
    return dict(at_ms=row['at_ms'],system=row['system'],components=totals,
        note='Working sets include shared pages, so these rows cannot be added to reconstruct physical RAM. Missing counters remain visible. Other processes include this diagnostic collector and unrelated apps, which were not closed.')
def selected_budget_name(attempt, name=None):
    name=name or f'budget-final{attempt}.json'
    if not re.fullmatch(r'budget-final'+re.escape(attempt)+r'[a-z]?\.json',name):
        raise ValueError('EXACT_CURRENT_ATTEMPT_BUDGET_NAME_REQUIRED')
    return name

def final_binding_issues(folder,a,b,current,gate,budget_name=None):
    """A different attempt on the same release cannot lend this report READY."""
    issues=[]
    roles=dict(fresh=f'ui-{a}/result.json',cold=f'ui-cold-{a}/result.json',
        lineage=f'lineage-{a}/result.json',lineage_cold=f'lineage-cold-{a}/result.json',
        normal=f'normal{a}/result.json',installation=f'installed-files{a}.json',
        supplementary=f'supplementary{a}/result.json',budget=selected_budget_name(a,budget_name),
        lifecycle=f'normal-lifecycle{a}.json')
    entries=gate.get('evidence',[])
    if not isinstance(entries,list):return ['FINAL_GATE_EVIDENCE_INVALID']
    if len(entries)!=len(roles) or {e.get('role') for e in entries if isinstance(e,dict)}!=set(roles):
        issues.append('FINAL_GATE_ROLE_SET_INVALID')
    for role,relative in roles.items():
        p=folder/relative
        found=[e for e in entries if isinstance(e,dict) and e.get('role')==role]
        if not p.is_file() or len(found)!=1 or found[0].get('path')!=relative or found[0].get('sha256')!=digest(p):
            issues.append('FINAL_GATE_ATTEMPT_BINDING:'+role)
    required=[*(roles[k] for k in ('fresh','cold','lineage','lineage_cold','installation','supplementary','lifecycle')),
        f'ui-reproduction-{b}/result.json',f'cleanup-reproduction-{b}.json',
        *(f'cleanup-{branch}-{a}.json' for branch in ('fresh','cold','lineage','history')),
        f'normal{a}/shutdown.json',f'normal{a}-restart/shutdown.json']
    for relative in required:
        p=folder/relative
        if not p.is_file() or read(p).get('status')!='PASS':issues.append('FINAL_REQUIRED_NOT_PASS:'+relative)
    for relative in (f'normal{a}/result.json',f'normal{a}-restart/result.json'):
        p=folder/relative
        if not p.is_file() or read(p).get('status')!='PASS_NORMAL_START_REUSE_DEBUG_OFF':
            issues.append('FINAL_NORMAL_NOT_PASS:'+relative)
    p=folder/f'ui-reproduction-{b}/result.json'
    if p.is_file():
        reproduction=read(p);engine=reproduction.get('desktop',{}).get('engine',{})
        source=reproduction.get('source_sha256',engine.get('source_manifest_sha256'))
        # BrowserWindow metadata exposes release, not the source manifest. The
        # exact installed-file role binds that unique immutable release to source.
        if (reproduction.get('release_id',engine.get('release_id'))!=current['release_id']
                or (source is not None and source!=current['source_manifest_sha256'])):
            issues.append('FINAL_REPRODUCTION_WRONG_RELEASE')
    review_path=folder/f'physical-readiness-review{a}.json'
    if not review_path.is_file():issues.append('FINAL_REVIEW_MISSING')
    else:
        review=read(review_path)
        if review!=gate.get('physical_readiness_review') or review.get('unresolved') or review.get('status')!='SOFTWARE_NO_KNOWN_BLOCKER':
            issues.append('FINAL_REVIEW_NOT_EXACT_OR_BLOCKED')
        references=review.get('evidence',[])
        selected=folder/f'ui-reproduction-{b}/result.json'
        if not selected.is_file() or review.get('reproduction')!={'path':selected.relative_to(folder).as_posix(),'sha256':digest(selected)}:
            issues.append('FINAL_REPRODUCTION_SHUTDOWN_SELECTION_MISMATCH')
        for relative in (f'ui-reproduction-{b}/result.json',f'cleanup-reproduction-{b}.json'):
            p=folder/relative
            if not p.is_file() or not any(e.get('path')==relative and e.get('sha256')==digest(p) for e in references):
                issues.append('FINAL_REPRODUCTION_NOT_BOUND:'+relative)
    if gate.get('release_id')!=current['release_id'] or gate.get('source_sha256')!=current['source_manifest_sha256']:
        issues.append('FINAL_GATE_NOT_ACTIVE_RELEASE')
    return issues

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--attempt',default='15');parser.add_argument('--reproduction-attempt',default='16')
    parser.add_argument('--budget-name',help='Exact current-attempt final snapshot basename; preserve earlier immutable snapshots.')
    args=parser.parse_args()
    a=args.attempt;b=args.reproduction_attempt
    if any(len(v)!=2 or not v.isascii() or not v.isdecimal() for v in (a,b)):raise ValueError('TWO_DIGIT_ATTEMPTS_REQUIRED')
    budget_name=selected_budget_name(a,args.budget_name)
    OUT.mkdir(parents=True,exist_ok=True)
    old=ROOT/'outputs/sim-zoom-demo-20261021'
    attempts=[]
    for name in ('original-contention-red.log','original-contention-red-clean.log','contention-green.log','safety-suite-candidate01.log',
        'pc-candidate01.log','pc-candidate02.log','control-candidate03.log','control-candidate04.log','pre-freeze05.log','final-boundary06.log','continuous-build01.log'):
        p=old/name
        if p.exists():attempts.append(info(p))
    for d in sorted(OUT.iterdir()):
        if d.is_dir() and (d/'result.json').is_file():
            v=read(d/'result.json');attempts.append(dict(**info(d/'result.json'),status=v.get('status','INCOMPLETE'),
                phase=v.get('phase'),release_id=v.get('release_id') or v.get('desktop',{}).get('engine',{}).get('release_id'),
                groups=v.get('groups'),steps=[dict(name=s.get('name','Unnamed record'),status=s.get('status','NOT_AN_ACCEPTANCE_VERDICT'),elapsed_ms=s.get('elapsed_ms')) for s in v.get('steps',[])],
                error=v.get('error'),operation_id=v.get('operation_id'),project=v.get('project')))
            attempts[-1].update(input_sha256=v.get('input_sha256'),launch_id=v.get('launch_id') or v.get('desktop',{}).get('engine',{}).get('launch_id'))
    original=ROOT/'outputs/robot-powered-20261020-guard05'
    receipt=read(original/'receipt.json');rawfiles=[]
    for member in receipt['segments']:
        p=original/member['path'];actual=info(p)
        if actual['sha256']!=member['sha256'] or actual['bytes']!=member['bytes']:raise ValueError('ORIGINAL_ARCHIVE_CHANGED')
        rawfiles.append(actual)
    current=read(Path(os.environ['LOCALAPPDATA'])/'TwinPulse/installed/active-release.json')
    normal=OUT/'normal03/result.json';restart=OUT/'normal03-restart/result.json'
    if all(p.exists() for p in (normal,restart,normal.parent/'shutdown.json',restart.parent/'shutdown.json')):
        n,r=read(normal),read(restart);s,t=read(normal.parent/'shutdown.json'),read(restart.parent/'shutdown.json')
        lifecycle=dict(status='PASS_SCOPED_LIFECYCLE' if s['shutdown_clean'] and t['shutdown_clean'] else 'FAIL',
            release_id=n['release_id'],source_sha256=n['source_sha256'],normal_launch=n['launch_id'],restart_launch=r['launch_id'],
            normal_ready_ms=n['ready_wait_ms'],restart_ready_ms=r['ready_wait_ms'],shutdown_clean=s['shutdown_clean'],restart_shutdown_clean=t['shutdown_clean'],
            native_input='Actual Computer Use selected returned normal window Alt_L+F4 both times',
            normal_visible_home='NOT_RUN_UNCONFIRMED: final normal AX trees had no document; prior native image capture FrameArrived timed out. Backend ready is not full visible native acceptance.',
            explorer_doubleclick='NOT_RUN: identical root entry invoked by execution tool',
            references=[info(p) for p in (normal,restart,normal.parent/'shutdown.json',restart.parent/'shutdown.json')])
        write(OUT/'historical-normal03-lifecycle.json',lifecycle)
    builds=[]
    for number in sorted(p.name[5:] for p in OUT.glob('build[0-9][0-9]') if p.is_dir()):
        p=OUT/('build'+number)/'dist/TwinPulse/windows-release-manifest.json'
        if p.exists():
            manifest=read(p);installation=OUT/('installation'+number+'.json')
            builds.append(dict(candidate=number,build_id=manifest.get('build_id'),manifest=info(p),
                installation=read(installation) if installation.exists() else 'NOT_INSTALLED'))
    for p in sorted(OUT.glob('*.log')):attempts.append(info(p))
    result=dict(schema='continuous-control-repair-20261021-1.0',generated_utc=datetime.now(timezone.utc).isoformat(),
        overall='PARTIAL_NOT_READY_CURRENT_FULL_UI_ACCEPTANCE_REQUIRED',current_installed=current,
        physical_operation_id='65fe078b1975404886704c2df728a33f',original_receipt=info(original/'receipt.json'),
        original_archive=rawfiles,original_records=receipt['saved'],attempts=attempts,builds=builds,
        changes=[
            'Large event deepcopy/JSON preparation outside the robot event-order lock; exact bounded FIFO, UTF-8 caps and nonce redaction retained.',
            'Copy-on-write robot status and root snapshot; small control flags do not copy display histories.',
            'PC display/report/recording-manifest copies outside Stop/input admission lock.',
            'Sensor row receipt/source-age pairing corrected; fresh() still evaluates current original header age.',
            'Bounded command/pause preparation and order-lock timing; original issued/source clocks preserved.',
            'Wheel observation first/latest request, operation/Twin/epoch/generation and output count; receipt/source clocks separate; body UNKNOWN.',
            'Cancel/Stop/cleanup ends observations; diagnostic send failure cannot skip independent cleanup.',
            'Operation log projects original failed check separately from cleanup/current telemetry.',
            'Read-only bounded Kit phase ledger retains first/worst/recent slow phases beyond stdout history; original HTTP failures retain elapsed/callback/raw-wait clocks and pending join state.',
            'Terminal wheel observation projects exact same-context ENDED result without mutating original heartbeat/fault, refreshing authority, reviving an old gesture or blocking cleanup on malformed optional diagnostics.',
            'Compact historical operation summary pins the immutable original failed check independently of later clean heartbeat/cleanup.',
            'SIM raycast uses one no-queue read-only worker with fair robot selection, cooperative cancellation and explicit close; USD access remains on Kit. Late epoch/OFF/expired results are discarded without retimestamping.',
            'Sensor-pose, section cache and raycast wall/thread-CPU clocks are separately bounded in operation diagnostics; invalid optional numbers are rejected without throwing.',
            'Cleanup owners proceed independently; original exception and final APP.close failure remain visible and cannot produce a successful host exit.',
            'Persist launch-bound inner cleanup before expected Isaac fast-shutdown nonreturn; the owner separately records root exit versus terminate/kill and Job descendant reaping.',
            'Current gate requires exact handoff/owner/cleanup SHA for seven launches including the selected reproduction, rejects incomplete joins, forced/unknown exit, evidence-store failures, host exceptions, schema downgrade and cross-launch substitution.',
            'Live viewport uses one atomic metadata/JPEG receipt instead of serial metadata then image requests; saved-history fallback adopts last_frame only, never pairing history.frame with a different JPEG. Original one-second expiry and disabled stale camera remain.',
            'Slow host-tail spans preserve same-scope child timings, wall/thread CPU and Kit/process GC; optional diagnostic-copy failures cannot mask the body result or original exception.',
            'The final report binds its selected attempt, nine gate roles and reproduction to exact paths and SHA; another attempt READY on the same release cannot replace a current missing or failed journey.',
            'The atomic no-current-frame 204 response now drains exactly zero bytes and rechecks context inside the unchanged two-second bound. Actual Electron alternating diagnostic21b observed four drained loadingFinished versus four unconsumed native aborts. Ordinary aborts still fail the recorder and gate.',
            'Workflow polling uses a small display-only provider observation cached at startup/explicit refresh, not repeated credential-file reads under the workflow lock. Fresh generation credentials and authorization are not cached or bypassed.',
            'Provider refresh performs fallible factory/file work outside the hot workflow lock; unconfirmed initial/save failures block new model requests, preserve prior state and retain the original exception. Late older refresh cannot commit; gateway cancellation precedes mutation.',
            'SIM conversation avoids a full workflow snapshot only needed by completed REAL room generation. Read-only GETs carry separate canonical UUID diagnostics with bounded route/stack logs, not authority or a new timeout.'
        ],unchanged=dict(input_ttl_ms=350,input_renewal_target_ms=100,odom_interval_ms=300,
            sensor_and_guard_receipt_ms=200,final_output_ms=450,geometry_and_speed_limits=True,
            manual_recalculate_then_explicit_apply=True),
        review=dict(agent='gpt-6-astra',effort='xhigh',read_only=True,
            found_and_fixed=['nested recording-manifest copy under PC admission lock','cancelled observation left OBSERVING',
                'receipt/source clock ambiguity','publication generation identity','optional terminal diagnostic failure skipping cleanup',
                'terminal viewport observation after stop/join','failed HTTP elapsed and capture subphases','APP.update/tail exception duration',
                'terminal wheel-result PC projection','malformed optional diagnostic must not prevent cleanup'],
            independence='No App, network, SSH, installation or device use by reviewer.'),
        attribution=dict(confirmed='Deterministic lock contention and original clock-pair bugs reproduced before fixes.',
            unknown='These defects are not proved to be the sole cause of original05. Guard producer versus executor delay remains UNKNOWN.',
            remaining_load='Own payload preparation and copy-on-write work still consumes CPU. PC replay is not actual Pi load/storage qualification.'),
        not_run=['Fresh powered App Connect/Prepare and Pi load on this release','Physical continuous four directions/chat90/single360',
            'Physical braking, chassis displacement, obstacle clearance and world alignment',
            'Automatic independent LiDAR motion verdict without same-session stationary comparison',
            'Explorer double click, OS paste and full native pointer acceptance'],
        boundaries=['No robot SSH/connection/sensor/motor request in this repair turn.',
            'No timeout relaxation, original-input retimestamp/replay, mock model or hidden product-state injection.',
            'No SDK/global/ROS install, existing-data/build deletion, commit/push or public upload.'],
        demo=dict(scope='Previous explicitly requested SIM media, not current physical acceptance',**info(old/'TwinPulse-SIM-Demo-60s-2026-10-21.mp4')))
    result['frozen_original_failures']=[dict(receipt=info(p),value=read(p)) for p in sorted(OUT.glob('failed-*-original-logs/receipt.json'))]
    result['actual_current_turn_recordings']=[info(p) for p in sorted(OUT.glob('ui-*/recording/app-screen.mp4'))]
    result['sim_stall']=dict(original_ui03='FAIL at nearest-bed destination after normal directions/60s hold/chat90/single360; Kit log has 6.530s frame gap. Current ledger instrumentation is not itself a performance fix.',
        original_ui03_launch='20dce8dc24ab428f81a7bf49e1b90722',root_cause='UNKNOWN until current original phase ledger and actual new journey are inspected',
        prebuild05_available_ram_kib=629812,prebuild05_dwm_working_mib=4265,
        resource_caveat='Read-only host samples, not proof of memory paging as the sole original cause; OS and unrelated applications were not changed.')
    result['no_content_diagnostic']=[dict(reference=info(p),value=read(p)) for p in (OUT/'no-content-diagnostic21.json',OUT/'no-content-diagnostic21b.json') if p.is_file()]
    result['no_content_diagnostic_limits']='Diagnostic21 query/context mistake returned400 and is not product/user acceptance. Corrected21b is a read-only exact BrowserWindow transport comparison, not a full journey. Original whole19 FAIL and all raw canceled records remain unchanged; no recorder exception was added.'
    result['state_poll_contention23']=dict(
        status='ORIGINAL_FAIL_PRESERVED_SOLE_CAUSE_UNKNOWN',
        original=info(OUT/'ui-reproduction-23/result.json'),
        frozen=info(OUT/'failed-ui-reproduction23-original-logs/receipt.json'),
        observed='During the explicit final fault window, conversation and workflow GETs aborted after 3001.791ms and3000.849ms. A saved stack at1792532754545 shows workflow reading stage-routing/key-registry files under its lock and conversation waiting for that lock.',
        concurrent_load='Snapshot materialization/encoding took about1.0–1.19s in nearby observations; actual file writes10–18ms. Viewport responses continued and browser-to-automation receipt gaps were small. This does not prove a sole disk, CPU, network or harness cause.',
        change='Removed confirmed polling file-I/O/lock coupling; added exact read UUID, route phases and response receipt collection. Original3s/expiry/fault criteria and ordinary error classification retained.',
        no_overclaim='A clean final whole/reproduction is current-release evidence only, not proof that the original sole cause has been identified or cannot recur.')
    result['supplementary_initial_failures']=dict(
        original=info(OUT/'workflow25-tests.log'),
        baseline=info(OUT/'legacy-installed19-comparison25.log'),
        fixture_correction=info(OUT/'workflow25-supplementary-tests-fixed.log'),
        interpretation='Initial new-fixture imports were corrected. Four legacy chat-navigation expectations also fail against the exact prior installed19 baseline: they bypass the current explicit robot-selection precondition. They remain recorded as test/contract failures, not silently passed or fixed by weakening product preconditions. Discarded-response Mock supplied no real headers; realistic Message/GET/HTTP1.1 fixture gives28PASS. The selected final five-group results are reported separately, not an all-repository PASS.')
    if (OUT/'resources-after25.json').is_file():
        result['resource_stall25']=dict(status='FAIL_PRESERVED_UNRESOLVED_NOT_READY',
            references=[info(OUT/p) for p in ('ui-25/result.json','failed-ui25-original-logs/receipt.json','runtime-final25/receipt.json','resources-after25.json')],
            original_launch='e631c8a84c6b443da3f8518f3f1e7b5f',original_project='chat_mvh8rm7k_4dafa4c1',
            original_operation='15a7ffdb0bcc4727af6895ece625af04',
            first_causal_order='APP.update921ms, GC0, available RAM452.64MiB, combined page faults+14897 precede the chair failure. Robot event1275 records ISAAC_UPDATE_STALLED dt969ms; original frame1857 age1039.895751953125ms is correctly stale.',
            subsequent_not_initial_cause='Fleet update1689.6ms/threadCPU640.6ms, JPEG1219ms and backend snapshot1657ms occur after the first failed condition. Recording finalization also begins after failure.',
            resource_snapshot=read(OUT/'resources-after25.json'),
            interpretation='Memory pressure is observed, not proof of a DWM leak, paging or any sole cause. DWM private committed bytes are neither actual physical RAM use nor Twin model file size. No DWM termination, reboot, GPU/driver change or threshold relaxation was performed.',
            next='User was asked once to save work and restart PC when possible. Recheck resources before the same frozen-release whole journey and original geometry reproduction. A clean rerun cannot prove the historical sole cause.')
        p=OUT/'resources-after23-offline.json'
        if p.is_file():result['resource_stall25']['latest_after_offline_tests']=dict(reference=info(p),value=read(p))
    result['motion_review_source']=dict(status='IMPLEMENTED_SOURCE_ONLY_FINAL_INSTALLED_UI_AND_COLD_NOT_RUN',
        scope='Explicit offline analysis of a closed saved physical recording; never a new robot permission or live command.',
        source_files={name:digest(ROOT/name) for name in ('packages/twinpulse_app/src/twinpulse_app/physical_motion_analysis.py',
            'packages/twinpulse_app/src/twinpulse_app/physical_motion_review.py','scripts/twinpulse_motion_review_worker.py',
            'apps/twinpulse-web/src/RobotMotionReview.tsx')},
        changes=['One named below-normal subprocess, bounded immutable archive SHA/context/sequence verification; no model/SSH/robot access.',
            'Each command has its actual applied epoch and strict before/after wheel and independent scan brackets. Adjacent yaw accumulates without folding a full revolution to zero.',
            'Incomplete/fallback rings and gaps cannot be bridged into a qualified comparison; later or mixed extrinsics are not borrowed for earlier scans.',
            'Duration-matched same-session zero-output noise remains observed correlated noise, not a statistical confidence bound or proof of physical immobility.',
            'Connect/chat preparation cancels the helper without joining; Stop/Disconnect never wait on it. Late results cannot publish across cancellation/context changes.',
            'Explicit Analyze recording plus historical Details/cold GET restore UI; exact job/receipt/segments/robot/connection/Twin/complete/error required in the next actual frozen installed journeys.',
            'Shared Job close errors remain sticky without hiding original assign/wait/tool errors; later cleanup owners still run. Optional CPU diagnostics cannot mask APP.update.'],
        supplementary=[dict(reference=info(p),value=read(p)) for p in sorted(OUT.glob('motion-review-replay[0-9][0-9].json'))],
        frozen_candidate_groups=[dict(reference=info(p),value=read(p)) for p in sorted(OUT.glob('candidate*-supplementary/result.json'))],
        limitation='Actual original05 pipeline replay is supplementary, not App UI acceptance or successful chassis motion. Three current replay04 windows have WHEEL_INTERVAL_GAP; the fourth has insufficient matched baseline. All body results UNKNOWN, authority false. The earlier frozen22 role runs an older draft, not the final source.')
    for name in ('source-review-candidate23.json','motion-review-frozen23.json'):
        p=OUT/name
        if p.is_file():result['motion_review_source'][name]=dict(reference=info(p),value=read(p))
    frozen=OUT/'motion-review-frozen23.json'
    if frozen.is_file():
        review=read(frozen).get('review') or {}
        exact=review.get('input_receipt_sha256')==digest(original/'receipt.json') and review.get('input_segments')==receipt['segments'] and review.get('input_rows')==receipt['saved']
        if not exact:raise ValueError('FROZEN_REVIEW_NOT_EXACT_PROTECTED_ORIGINAL05')
        result['motion_review_source']['frozen_input_matches_protected_original05_receipt_segments_rows']=True
    result['resume_plan']=dict(first='Save work and restart PC when possible; then remeasure resources, do not restart or kill DWM from the agent.',
        frozen_candidate='build23/dist/TwinPulse, not installed; preserve active21 and its original25 FAIL.',
        actual_next='Install/verify this exact candidate locally, run installed five-group checks, fresh27/cold27/lineage27/history27; reproduce original stored geometry28; normal27 and normal27-restart via native Computer Use, archive all exact launch logs and run current gate.',
        constraints='Do not start hardware, relax deadlines, join split/shortened trials or borrow previous release PASS. Stop and freeze any original failure before another Start. Missing branches remain NOT_RUN.')
    result['changes'].extend(result['motion_review_source']['changes'])
    result['supplementary_initial_failures']['motion_review_limits']='Original unit/UI fixture failures and wrong default-Python missing-Pillow/cwd invocations remain in logs. The existing pinned build venv was used for corrected runs; no installation or product precondition relaxation. No all-repository PASS is claimed.'
    analysis=OUT/'original08-stall-analysis.json'
    if analysis.exists():result['sim_stall']['original08']=dict(reference=info(analysis),value=read(analysis))
    analysis=OUT/'followup15-17-analysis.json'
    if analysis.exists():result['sim_stall']['original15_and17']=dict(reference=info(analysis),value=read(analysis))
    result['implementation_scope']=dict(
        R1='Original failure and new same-clock phase evidence preserved; historical producer/executor sole causality still UNKNOWN.',
        R2='Reproduced lock/serialization contention repaired; physical original-load validation remains NOT_RUN.',
        R3='Latest-value/copy/serialization paths separated and SIM raycast no longer synchronously waits on Kit; real Pi load comparison remains NOT_RUN. No blanket thread-performance guarantee.',
        R4='Source implements explicit per-command wheel/independent LiDAR/duration-matched same-session noise review. Original pipeline replay is supplementary; final installed Analyze and cold GET restore NOT_RUN. Generalized automatic qualified chassis verdict is NOT_IMPLEMENTED; body stays UNKNOWN.',
        R5='Current installed software journeys and gate are recorded separately below; powered App whole cycle remains NOT_RUN, not replaced by SIM.')
    result['main_model_setting']='Requested Sol6.1 very-high; exact serving model/effort is not independently exposed by local tools. Reviewer explicitly gpt-6-astra/xhigh.'
    for filename,key in ((budget_name,'budget_final'),(f'gate-result{a}.json','gate_result'),(f'normal-lifecycle{a}.json','normal_lifecycle')):
        p=OUT/filename
        if p.is_file():result[key]=read(p);result[key+'_reference']=info(p)
    if result.get('budget_final'):
        value=result['budget_final']
        value['remaining_additional_50_usd']=str(Decimal(value['limit_usd'])-Decimal(value['protected_additional_50_total']))
    result['final_attempt']=a;result['final_reproduction_attempt']=b
    result['final_binding_issues']=final_binding_issues(OUT,a,b,current,result.get('gate_result',{}),budget_name)
    if (result.get('gate_result',{}).get('status')=='READY_FOR_SUPERVISED_POWERED_TEST'
            and not result['final_binding_issues']):
        result['overall']='READY_FOR_SUPERVISED_POWERED_TEST_SOFTWARE_SCOPE_ONLY_PHYSICAL_NOT_RUN'
    amendment=OUT/'post-gate-review12.json'
    if amendment.is_file():
        result['post_gate_review12']=read(amendment)
        if result['post_gate_review12']['release_id']==current['release_id'] and result['post_gate_review12']['unresolved']:
            result['overall']='NOT_READY_POST_GATE_SHUTDOWN_DIAGNOSTIC_REPAIR_PENDING'
    result['remaining']=dict(
        physical='Actual App Connect/Prepare/readback/Pi load/storage/continuous driving/braking/world alignment remain NOT_RUN on these repaired sources.',
        automatic_lidar_body_verdict='Generalized qualified chassis verdict NOT_IMPLEMENTED. Explicit offline per-command comparison implemented in source and real original replay, but final installed UI/cold restore NOT_RUN; no body PASS.',
        root_cause='Original05 producer/executor causality and original ui03 6.53s stall sole cause remain UNKNOWN. Current clean re-execution is not proof of that old cause or a success guarantee.',
        deployment='No new public distribution, Git commit/push or cleanup; all work is local.')
    memory_review=OUT/'memory-failure29-review.json'
    if a=='27' and b=='29' and memory_review.is_file():
        result['memory_retry27_29']=dict(reference=info(memory_review),value=read(memory_review),
            summaries=[dict(reference=info(OUT/name),value=read(OUT/name)) for name in (
                'memory-before-reboot27-summary-b.json','memory-before-reboot29-summary.json','memory-after-failure29-tail-summary.json')],
            stages=[dict(reference=info(OUT/name),value=read(OUT/name)) for name in (
                'memory-before27-stage.json','memory-after-ui27-stage.json','memory-failure29-stage.json','memory-after-failure29-stage.json')],
            limitation='Original raw JSONL and receipts remain immutable. System1s/process5s/GPU30s are target periods, not gapless peaks; sample timestamps/collector cost and missed intervals remain visible. Post-failure idle is not chair-motion time. Reboot comparison NOT_RUN.',
            official_counter_references=[
                'https://learn.microsoft.com/en-us/windows/win32/api/psapi/ns-psapi-performance_information',
                'https://learn.microsoft.com/en-us/windows/win32/api/psapi/ns-psapi-process_memory_counters_ex2',
                'https://learn.microsoft.com/en-us/windows/win32/api/psapi/ns-psapi-enum_page_file_information'])
        fail=result['memory_retry27_29']['value']
        near=max((r for r in fail['process_window'] if r['at_ms']<=fail['failure_at_ms']),key=lambda r:r['at_ms'])
        tail=None
        with (OUT/'memory-after-failure29-tail/samples.jsonl').open(encoding='utf-8') as stream:
            for line in stream:
                row=json.loads(line)
                if 'processes' in row:tail=row
        result['memory_retry27_29']['component_snapshots']=dict(failure_preceding_5s_sample=memory_components(near),post_close_tail_last_5s_sample=memory_components(tail))
        result['motion_review_source']['status']='INSTALLED27_EXPLICIT_ANALYZE_AND_NEXT_COLD_GET_RESTORE_PASS_BODY_UNKNOWN'
        result['motion_review_source']['installed_ui']=[info(OUT/name) for name in ('lineage-27/result.json','lineage-cold-27/result.json')]
        result['implementation_scope']['R4']='Installed27 explicit per-command Analyze and next separate cold GET-only exact job/receipt/segments/results restore PASS. Original05 remains body UNKNOWN; no physical outcome is manufactured.'
        result['remaining']['automatic_lidar_body_verdict']='Generalized qualified chassis verdict NOT_IMPLEMENTED. Installed27 explicit offline analysis/cold restore PASS; saved original05 movement remains UNKNOWN.'
        result['remaining']['current_blocker']='Original25 saved geometry29 chair ISAAC_UPDATE_STALLED516ms. Resource diagnostics allowlist mismatch loses same-scope CPU fields. Reboot comparison and final normal/restart27 NOT_RUN.'
        result['resume_plan']=dict(first='No reboot performed. Same frozen23 is already installed and verified1674files; retry27 four journeys passed, original geometry29 failed.',
            frozen_candidate='Keep20261020T230430Z-77b57c434631/source77b57c4346316db99bebc616bb82ca9b42ec47b72b5304f28fb1ee1af74372d6 unchanged for A/B.',
            actual_next=result['memory_retry27_29']['value']['after_reboot'],
            afterward='Repair checked_work host CPU/resource allowlist contract, add exact failed-event negative/round-trip tests, freeze a new build and rerun original condition/full acceptance separately.',
            constraints='No automatic reboot or unrelated process termination, no physical robot access. Preserve original failure and unknown exact516ms cause. No timeout, geometry or evidence relaxation.')
    result['next_supervised_session_not_run']=[
        'Confirm current supervision, charger removal, clear space and immediate power-off availability; do not infer these from this robot-OFF report.',
        'Open the saved Twin and select the registered physical robot in the App; explicit Connect, then Prepare with zero motion, source-bound build/loader/timing readback.',
        'Collect stationary original sensor data and same-session noise; run the existing Bootstrap Stop observation. Preserve incomplete/unknown results without inventing PASS.',
        'On the same admitted session run the original four directions and release/Stop, chat90 and one360 scan in sequence; use command/output, odometry and independent LiDAR evidence, not repeated human-motion questions.',
        'Stop, LiDAR OFF, export the exact operation and raw sources; disconnect, exit and reopen history without restoring authority.',
        'If a required branch fails, stop additional movement, retain its operation/Twin/epoch and original clocks, diagnose before retry; never join a shorter continuation into a whole-cycle PASS.'
    ]
    result['final_actual_scope']={}
    for name in (f'ui-{a}',f'ui-cold-{a}',f'lineage-{a}',f'lineage-cold-{a}',f'ui-reproduction-{b}'):
        p=OUT/name/'result.json'
        if p.is_file():
            v=read(p);result['final_actual_scope'][name]=dict(status=v['status'],steps=len(v['steps']),
                project=v.get('project'),reference=info(p),fresh_generation=name==f'ui-{a}',
                original_saved_geometry_only=name==f'ui-reproduction-{b}',
                http_error_count=len(v.get('http_errors',[])),page_error_count=len(v.get('errors',[])),
                unclassified_request_failures=sum(not r.get('fault') and not r.get('exiting') for r in v.get('request_failures',[])))
            ages=[r['frame_age_ms'] for r in v.get('display_samples',[]) if type(r.get('frame_age_ms')) in (int,float)]
            if ages:result['final_actual_scope'][name]['decoded_display_samples']=dict(count=len(ages),max_age_ms=max(ages),
                limit='Sampled assertions in this journey, not proof of every instant or other hardware; original1000ms check unchanged.')
    result['final_negative_attempts']=[dict(reference=info(p),value=read(p)) for p in sorted(OUT.glob('gate-additional-negatives*.json'))]
    p=OUT/f'gate-negative-original03-result{a}.json';result['original_failure_negative']=read(p) if p.is_file() else 'NOT_RUN'
    result['native_normal_evidence']=[]
    for name in (f'normal{a}',f'normal{a}-restart'):
        folder=OUT/name
        native=folder/'native-home.json' if (folder/'native-home.json').is_file() else folder/'native-ready.json'
        if native.is_file():
            result['native_normal_evidence'].append(dict(directory=name,ready=info(native),
                actual_home=read(native).get('observation_method','Computer Use accessibility Home + authenticated Isaac connected after observed root Raise'),
                close_method='Actual Computer Use Alt_L+F4, refreshed returned native window; method/failed attempts retained in native evidence if any',
                close_receipt=info(folder/'shutdown.json'),
                native_close=info(folder/'native-close.json') if (folder/'native-close.json').is_file() else None,
                limits='No native screenshot/full pointer or Explorer double-click proof. Root Start invoked with execution tool; hidden shell parent and explicit Raise differ from Explorer.',
                startup_load='Software tests/replay completed before this normal Start; timing remains this PC observation, not a clean-PC benchmark.'))
    p=OUT/'sim-retest-analysis13.json'
    if p.is_file():result['saved_geometry_comparison']=dict(reference=info(p),value=read(p))
    p=OUT/f'runtime-final{a}/receipt.json'
    if p.is_file():
        result['final_runtime_archive']=dict(reference=info(p),value=read(p))
        result['final_engine_cleanup']=[]
        for row in read(p)['launches']:
            archive=OUT/f'runtime-final{a}'/row['launch_id']/'engine-result.json'
            if archive.is_file():
                v=read(archive);result['final_engine_cleanup'].append(dict(launch_id=row['launch_id'],
                    cleanup_status=v.get('cleanup_status'),cleanup_errors=v.get('cleanup_errors'),
                    app_close=v.get('app_close'),join_status=v.get('viewport_phase_diagnostics',{}).get('join_status')))
                owner=archive.parent/'owned-exit-observations.json'
                result['final_engine_cleanup'][-1]['owner_exit']=read(owner) if owner.is_file() else 'MISSING'
    p=OUT/f'astra-review{a}.json';result['final_source_review']=read(p) if p.is_file() else 'PENDING'
    p=OUT/'runtime-final21/receipt.json'
    if p.is_file():result['diagnostic_runtime_archive']=dict(reference=info(p),classification='OLDER_RELEASE_READ_ONLY_204_TRANSPORT_DIAGNOSTICS_NOT_FINAL_ACCEPTANCE')
    reboot=OUT/'memory-reboot-comparison30.json'
    if reboot.is_file():
        current_trial=read(OUT/'ui-reproduction-30/result.json')
        result['reboot_comparison30']=dict(reference=info(reboot),value=read(reboot),
            same_source_ui=dict(status=current_trial['status'],steps=len(current_trial['steps']),reference=info(OUT/'ui-reproduction-30/result.json'),
                project=current_trial.get('project'),desktop=current_trial.get('desktop'),fresh_generation=False,
                limitations='Same saved original25 geometry and identical UI test/source, not an exact initial robot-pose or request-time replay. Actual same BrowserWindow Test; root Start-Test invoked by execution tool, not Explorer/native full input.'),
            references=[info(OUT/p) for p in ('start-reproduction-30.json','installed-files30.json','cleanup-reproduction-30.json','runtime-final30/receipt.json',
                'memory-after-reboot30/metadata.json','memory-after-reboot30/receipt.json','budget-final30.json')])
        result['reboot_comparison30']['historical_other_release']=current_trial.get('desktop',{}).get('engine',{}).get('release_id')!=current['release_id']
        if a=='27' and b=='29':
            result['overall']='PARTIAL_NOT_READY_DIAGNOSTIC_CONTRACT_AND_FINAL_REACCEPTANCE_PENDING'
            result['resume_plan']=dict(completed='User reboot observed2026-10-21T20:57:50.5+09:00; exact frozen23/source1674files/collector+UI hashes unchanged. Original29 chair FAIL10708ms versus30 chair PASS55876ms; entire30 36steps PASS and normal cleanup PASS.',
                findings='Closed-App system commit50.191GB to9.662GB, DWM privatecommit25.498GB to67.854MB, nonpagedpool3.231GB to747MB. Changed background apps/driver state/uptime remain confounders; exact leaking function and sole cause unknown.',
                next='Comparison is complete. The known checked_work host CPU/resource allowlist defect remains unfixed intentionally in this same-source A/B. Repair and round-trip/negative tests require a separate build and original-condition/final acceptance; do not call reboot a permanent fix.',
                constraints='Original29/25/05 failures and raw SHA remain immutable. No robot/SSH/model call/system change/installation/cleanup/Git write during reboot comparison; old selected gate27 remains NOT_READY, not backfilled from30.')
            result['remaining']['current_blocker']='Same-source reboot comparison30 PASS, but failed-check resource-diagnostic allowlist contract remains broken; final ordinary/restart and repaired-source whole acceptance are not yet complete. No physical qualification.'
        result['budget_reboot30']=read(OUT/'budget-final30.json')
    diagnostic=OUT/f'diagnostic-installed-roundtrip{a}.json'
    if diagnostic.is_file():
        result['diagnostic_contract_fix']=dict(reference=info(diagnostic),value=read(diagnostic),
            evidence=[info(OUT/name) for name in ('diagnostic-contract-red31.log','diagnostic-contract-green31.log','diagnostic-source-review31.json')])
        result['changes'].append('Exact UpdateProbe fast/slow CPU, working-set and before-resources fields now survive strict host validation, first-fault and operation export. Unknown/malformed/nonfinite data remain rejected; no timing, authority or safety change. Original29 lost fields stay unavailable.')
        if all(result['final_actual_scope'].get(name,{}).get('status')=='PASS' for name in (f'lineage-{a}',f'lineage-cold-{a}')):
            result['motion_review_source']['status']='INSTALLED_EXPLICIT_ANALYZE_AND_NEXT_COLD_GET_RESTORE_PASS_BODY_UNKNOWN'
            result['implementation_scope']['R4']='Current installed explicit Analyze and next separate cold GET-only exact identity/result restoration PASS. Original physical05 body remains UNKNOWN; no physical verdict manufactured.'
            result['remaining']['automatic_lidar_body_verdict']='Explicit installed offline review/cold restore verified. Generalized qualified chassis verdict NOT_IMPLEMENTED; original physical movement remains UNKNOWN.'
        ready=result['overall'].startswith('READY_FOR_') and result['diagnostic_contract_fix']['value']['status']=='PASS'
        result['remaining']['current_blocker']='NO_KNOWN_SOFTWARE_TEST_ENTRY_BLOCKER_PHYSICAL_NOT_RUN' if ready else 'CURRENT_FINAL_GATE_OR_DIAGNOSTIC_NOT_READY'
        result['resume_plan']=dict(completed='Diagnostic contract fixed; actual current installed evidence and exact selected gate are recorded, without borrowing old-source or split-trial PASS.',
            next='Begin one supervised powered App test using the sequence below.' if ready else 'Finish the explicitly missing/failed current final-binding issues before asking for robot power.',
            constraints='No physical robot/SSH/sensor/motor request in this repair. No memory-leak or sole-cause guarantee; historical original failures remain preserved. Scope is supervised-test software entry, not chassis qualification.')
    failed_review=OUT/f'final-failure-review{a}.json'
    if failed_review.is_file():
        value=read(failed_review)
        if (value.get('actual_attempt')!=a or value.get('reproduction_attempt')!=b
                or value.get('release_id')!=current['release_id']
                or value.get('source_sha256')!=current['source_manifest_sha256']
                or value.get('status')!='PARTIAL_NOT_READY_FINAL_UI_FAILED_ENVIRONMENT_UNRESOLVED'):
            raise ValueError('FAILED_REVIEW_NOT_BOUND_TO_SELECTED_CURRENT_ATTEMPT')
        for entry in value['references']:
            path=OUT/entry['path']
            if not path.is_file() or digest(path)!=entry['sha256']:raise ValueError('FAILED_REVIEW_ORIGINAL_CHANGED:'+entry['path'])
        if result['final_actual_scope'].get(f'ui-{a}',{}).get('status')!='FAIL':raise ValueError('FAILED_REVIEW_WITHOUT_FAILED_UI')
        result['current_failed_review']=dict(reference=info(failed_review),value=value)
        result['overall']=value['status']
        result['changes'].append('CPU/resource diagnostic acceptance fixed in one product file; actual producer/fault/operation RED/GREEN and119 persisted installed CPU host rows observed. Required completed UI download/cold roundtrip remains NOT_RUN after the whole-UI failure. No deadline/authority/geometry change.')
        result['remaining']['current_blocker']='CURRENT_FRESH_UI_FAIL_ERR_NETWORK_CHANGED_AND_UNRESOLVED_OS_DWM_RESOURCE_ACCUMULATION'
        result['resume_plan']=dict(
            completed='Frozen24/source5fcf: one-file diagnostic fix, exact1674file installation, actual normal/native Home/AltF4 and restart cleanup PASS. Supplementary31 and33 PASS. Fresh31 original FAIL and119 actual installed persisted CPU rows retained; this is not a completed UI-download roundtrip.',
            next=value['next_scope'],
            constraints='No further App Start under the current resource pressure. During the diagnostic-fix/final31 work, no additional reboot, driver/network/OS change, DWM termination, deletion, robot/SSH or Git write was performed; the earlier actual user reboot30 remains separately recorded. The supported own Computer Use JS reset did not materially release DWM memory; it does not establish causality.')
    background_audit=OUT/'background-process-audit35.json'
    if background_audit.is_file():
        audit=read(background_audit)
        if audit.get('source_memory_reference',{}).get('sha256')!=digest(OUT/'memory-final31/samples.jsonl'):
            raise ValueError('BACKGROUND_AUDIT_MEMORY_SOURCE_CHANGED')
        result['background_process_audit']=dict(reference=info(background_audit),value=audit,
            interpretation='Tracked old TwinPulse PID+creation identities are absent, but Codex Computer Use/REA transports remain resident. Their necessity and causal relation to DWM are not established. The earlier JS kernel reset is not proof of terminating every MCP transport.')
        result['resume_plan']['next']='Before any driver change, inspect the remaining tool-client ownership/lifecycle and, only within explicit change authority, release confirmed finished tool sessions and compare memory. Do not kill every Node/Codex/DWM process. This read-only audit did not stop or disable anything and does not grant whole-UI readiness.'
    cleanup_observation=OUT/'authorized-tool-cleanup36.json'
    if cleanup_observation.is_file():
        cleanup=read(cleanup_observation)
        for entry in cleanup['references']:
            if digest(OUT/entry['path'])!=entry['sha256']:raise ValueError('TOOL_CLEANUP_ORIGINAL_CHANGED')
        result['authorized_tool_cleanup']=dict(reference=info(cleanup_observation),value=cleanup)
        result['resume_plan']['next']=cleanup['next']
    reopened=OUT/'codex-reopen-comparison37.json'
    if reopened.is_file():
        value=read(reopened)
        for entry in value['references']:
            if digest(OUT/entry['path'])!=entry['sha256']:raise ValueError('CODEX_REOPEN_ORIGINAL_CHANGED')
        result['codex_reopen37']=dict(reference=info(reopened),value=value,
            scope='Historical immediate/idle comparison, not current readiness. Later RAM recovery and actual App results are recorded separately.')
        result.setdefault('resume_plan',{})['next']='The user normal Codex reopen is already complete: all observed old51 tool and old17 Codex process identities are gone. Do not request the same restart again. Use the selected current App/gate results below; no driver change or robot request inferred.'
    probe=OUT/'capture-probe-review38.json'
    if probe.is_file():
        value=read(probe)
        for entry in value['references']:
            if digest(OUT/entry['path'])!=entry['sha256']:raise ValueError('CAPTURE_PROBE_ORIGINAL_CHANGED')
        result['native_capture_probe38']=dict(reference=info(probe),value=value)
    gc_failure=OUT/'gc-failure-review33.json'
    if gc_failure.is_file():
        value=read(gc_failure)
        for entry in value['references']:
            if digest(OUT/entry['path'])!=entry['sha256']:raise ValueError('ORIGINAL_GC_FAILURE33_CHANGED')
        result['gc_failure33']=dict(reference=info(gc_failure),value=value,
            historical_other_release=value['release_id']!=current['release_id'])
    gc_review=OUT/'gc-source-review35.json'
    if gc_review.is_file():
        value=read(gc_review)
        result['gc_diagnostic_source_review35']=dict(reference=info(gc_review),value=value,
            is_current_release=value['release_id']==current['release_id'])
        result['changes'].append('Host-only bounded GC origin ledger added after original33: collector generation/thread/bounded stack/CPU, separate slow-cycle retention and exception-safe phase restoration. Diagnosis only; no GC policy, watchdog or physical outcome change.')
    gc_failure=OUT/'gc-failure-review35.json'
    if gc_failure.is_file():
        value=read(gc_failure)
        for entry in value['references']:
            if digest(OUT/entry['path'])!=entry['sha256']:raise ValueError('ORIGINAL_GC_FAILURE35_CHANGED')
        result['gc_failure35']=dict(reference=info(gc_failure),value=value,
            historical_other_release=value['release_id']!=current['release_id'])
    raycast_review=OUT/'raycast-source-review37.json'
    if raycast_review.is_file():
        result['raycast_cycle_fix']=dict(reference=info(raycast_review),value=read(raycast_review))
        result['changes'].append('Confirmed per-ray recursive-closure cycles removed with explicit left-first DFS and a module-level stable builder. Original epsilons, first-hit/cancellation/maximum semantics remain; isolated RED/GREEN and actual current whole-condition evidence are separate.')
    preview_original=OUT/'ui-37/result.json'
    if preview_original.is_file():
        value=read(preview_original)
        result['original_preview_failure37']=dict(reference=info(preview_original),status=value['status'],
            step_count=len(value['steps']),step_pass=sum(s['status']=='PASS' for s in value['steps']),
            project=value.get('project'),http_errors=value.get('http_errors'),
            limitation='Original overall FAIL remains immutable. Missing original request/context/preview flags are not backfilled. Typed cache replacement is not physical/control qualification.')
    wrong_python=OUT/'supplementary39-wrong-interpreter-original/result.json'
    if wrong_python.is_file():result['wrong_interpreter_supplementary39']=dict(reference=info(wrong_python),value=read(wrong_python),
        cause='Main selected system Python without project dependencies; original failure retained. Rerun uses pre-existing project .venv; no new install.')
    snapshot_review=OUT/'snapshot-failure39-review.json'
    if snapshot_review.is_file():
        result['snapshot_failure39']=dict(reference=info(snapshot_review),value=read(snapshot_review))
        result['snapshot_encoder_fix']=dict(reference=info(OUT/'snapshot-source-review41.json'),value=read(OUT/'snapshot-source-review41.json'))
        result['changes'].append('Whole-history Python JSON iteration replaced by per-event encoding, with exact original bytes/hash and no mutable identity cache. Saved3.8MB isolated CPU/time reduction verified; peer-gap improvement and historical sole cause not proven.')
    viewport_review=OUT/'viewport-failure41-review.json'
    if viewport_review.is_file():
        result['viewport_failure41']=dict(reference=info(viewport_review),value=read(viewport_review))
        result['viewport_owned_channel_fix']=dict(reference=info(OUT/'viewport-source-review43.json'),value=read(OUT/'viewport-source-review43.json'))
        result['changes'].append('Dedicated owner-thread display HTTP reuse removes per-frame new connections, separate from control. Original2s/POST retry0/auth/frame clocks retained. Typed response/cleanup and per-frame diagnostic binding verified; original OS/connect/send cause remains unknown.')
    history_review=OUT/'history-failure43-review.json'
    if history_review.is_file():
        result['history_failure43']=dict(reference=info(history_review),value=read(history_review))
        result['history_tail_fix']=dict(reference=info(OUT/'history-source-review45.json'),value=read(OUT/'history-source-review45.json'))
        result['changes'].append('Cold history still validates every original row, segment SHA, source/Twin/sequence and incomplete verdict. Deep copies/redaction are deferred to the retained100 entries; identical output bytes/hash with less CPU are supplementary evidence, not a proof of the historical20s cause. Read/encode diagnostics cannot mask the original result or error.')
    scan_review=OUT/'scan-failure45-review.json'
    if scan_review.is_file():
        result['scan_failure45']=dict(reference=info(scan_review),value=read(scan_review))
        result['scan_display_expiry_fix']=dict(reference=info(OUT/'scan-source-review47.json'),value=read(OUT/'scan-source-review47.json'))
        result['changes'].append('Scan display uses its original700ms deadline and current render clock; image1000ms, pose/epoch and control clocks are unchanged. Same-renderer DOM/age plus separate request/receipt clocks share the existing5s visibility budget; only explicit absence may wait. Any visible invalid sample is terminal and independently rejected by the gate.')
    if a in ('53','57'):
        result['preserved_late_failures_and_preparations']=[]
        for name in ('navigation-failure48-review.json','body-frame-failure50-review.json',
                     'gate-result47.json','shutdown-contract47.json','ui-reproduction-48/result.json',
                     'clearance-preparation49/result.json','ui-reproduction-50/result.json',
                     'ui-reproduction-52/result.json','ui-53/result.json','clearance-preparation59/result.json'):
            path=OUT/name
            if path.is_file():
                value=read(path)
                result['preserved_late_failures_and_preparations'].append(dict(reference=info(path),
                    status=value.get('status'),classification=value.get('classification'),
                    historical_not_current_acceptance=name!='clearance-preparation59/result.json'))
        result['diagnostic_worker_wake_fix']=dict(
            product_file='scripts/twinpulse_live_viewport.py',
            mechanism='Nonblocking private queue wake on stop, with pre-print stop check; actual blocked stdout remains alive/unconfirmed and vetoes readiness.',
            unchanged='Original viewport3s/fleet3s/diagnostic100ms joins, motion/input/sensor deadlines, speed and geometry guards.',
            original47='Whole UI47/52 PASS did not override cold/restart diagnostic_alive=true/PRE_CLOSE_FAILED; rejected gate47 preserved.',
            unknown='Original diagnostic wait versus stdout blocking was not captured; clean current acceptance cannot prove the historical sole cause.',
            supplementary=[info(OUT/name) for name in ('diagnostic-wake-red53.log','diagnostic-wake-final53.log','final-gate-binding53.log') if (OUT/name).is_file()])
        result['saved_geometry_preparation_limit']='Original48 failed navigation before a UI Stop request; explicit49/59 SIM movement is separate visible preparation, not original-pose replay. Original50 failed a world-axis test assertion despite measured body-frame reverse; original FAILs remain unchanged.'
        result['catalog_read53']=dict(original='Actual fresh53 all39steps PASS yet wholeFAIL from ordinary projects read abort after6.027s; no exemption, retry or threshold change.',
            cause_boundary='Original server thread was enumerating directory metadata while system memory pressure overlapped; exact single-request CPU and sole cause remain UNKNOWN.',
            change='DirEntry metadata only for candidate ranking; selected64, active and open paths retain fresh containment/identity checks. Exact projects read-ID and snapshot phase diagnostics added with optional error isolation.',
            comparison=[dict(reference=info(OUT/name),value=read(OUT/name)) for name in ('catalog53-before/result.json','catalog53-after/result.json')],
            limits='Offline response hashes match. Timing differences are observations, not complete attribution or actual loaded HTTP acceptance. Legacy private asset/strict-listing unit failures recur in exact installed32 comparison and remain failures.')
        if (OUT/'catalog-failure53-review.json').is_file():
            result['catalog_read53']['original_review']=dict(reference=info(OUT/'catalog-failure53-review.json'),value=read(OUT/'catalog-failure53-review.json'))
    if a in ('33','35','37','39','41','43','45','47','53','57'):
        result.setdefault('resume_plan',{})['next']=f'Normal{a}/restart and current fresh/cold/lineage/history{a} plus saved-geometry{b} determine readiness. Prior failed31/33/35 or the supplementary capture probe are not relabelled PASS; actual missing current branches still veto the gate.'
        if result.get('overall','').startswith('READY_FOR_'):
            result['remaining'].pop('current_blocker',None)
            result['resume_plan']['next']='Software entry gate passed on the exact current installed release above. Next is one supervised powered-robot App session; physical acquisition/motion/braking/world alignment remain NOT_RUN.'
    media=OUT/f'recording-review{a}/result.json'
    if media.is_file():result['final_media_qa']=dict(reference=info(media),value=read(media))
    write(OUT/'result.json',result)
    def href(p):return os.path.relpath(p,OUT).replace('\\','/')
    def link(p,label=None):return '<a href="'+escape(href(p))+'">'+escape(label or p.name)+'</a>'
    rows=''.join('<tr><td>'+link(ROOT/r['path'])+'</td><td>'+escape(str(r.get('status','원 로그')))+'</td><td>'+escape(str(r.get('release_id','')))+'<br>'+escape(str(r.get('error','')))+ '</td></tr>' for r in attempts)
    shots=''
    for directory in sorted(p for p in OUT.iterdir() if p.is_dir() and p.name.startswith(('ui-','lineage-'))):
        folder=directory.name;files=sorted(directory.glob('*.png'))
        for p in (files[:2]+files[-1:] if len(files)>2 else files):shots+='<figure><img src="'+href(p)+'"><figcaption>'+escape(folder+'/'+p.name)+'</figcaption></figure>'
    html='''<!doctype html><html lang="ko"><meta charset="utf-8"><title>TwinPulse continuous-control repair</title>
<style>body{font:16px system-ui;max-width:1280px;margin:28px auto;padding:0 24px;color:#16313b}table{border-collapse:collapse;width:100%}td,th{border:1px solid #cbd5df;padding:9px;text-align:left;word-break:break-word}img,video{max-width:100%}pre{white-space:pre-wrap;overflow-wrap:anywhere}figure{margin:24px 0}.warn{background:#fff1dc;padding:18px}</style>
<h1>TwinPulse 연속 조종 수정·검증</h1><p class="warn">제품 수정·PC/SIM 인수와 실제 Pi/주행 결과는 별개입니다. 원05 실패는 보존하며 이 보고서는 실물 연속주행 성공을 선언하지 않습니다.</p>'''
    html+='<p>'+escape(result['generated_utc'])+' · '+escape(current['release_id'])+'</p><h2>수정한 범위</h2><ul>'+''.join('<li>'+escape(x)+'</li>' for x in result['changes'])+'</ul>'
    title='PC·SIM 시험 진입 준비 확인 — 실물 결과는 NOT_RUN' if result['overall'].startswith('READY_FOR_') else '미완료 — 현재 설치본의 전체 재인수·진단 중'
    lead='<h2>'+title+'</h2><p class="warn">'+escape(result['overall'])+'</p>'
    if 'current_failed_review' in result:
        lead+='<p>진단 누락 수정과 실제 일반 시작·재시작은 통과했습니다. 그러나 현재 설치24의 새 생성31은60초 연속 조종37.596초에서 FAIL입니다. Windows Wi-Fi 끊김·재연결과 세 GET의 ERR_NETWORK_CHANGED가 겹쳤고, 앱 연결 미확인→live/이름 비활성화→원 INPUT_STALE를 보존했습니다. 그때 화면은767.767ms로 원1000ms 기준 안이며, 타임아웃 초과로 설명하지 않습니다. 종료 뒤에도 DWM의 RAM·privatecommit이 증가했고 제 조작 세션 reset 뒤에도 해소되지 않았습니다. 특정 드라이버·앱·RAM을 단독 원인으로 확정하거나, 이전30의 PASS로 전체 완료를 선언하지 않습니다. 후속cold·원장면32·실제 UI다운로드/재열기 진단·실물 시험은 NOT_RUN입니다.</p>'
    elif 'diagnostic_contract_fix' in result:
        lead+='<p>실패진단의 CPU·working-set·before-resources 필드 누락을 엄격한 계약 안에서 수정했습니다. 실제 생산자→검증→원실패/operation export의 RED/GREEN 및 Astra 읽기 검토를 보존했고, 현재 설치본의 실제 UI 다운로드에서도 CPU 진단 보존을 검사했습니다. 아래 일반Start/재시작·fresh/cold/lineage/history·원장면 재현과 최종SHA gate가 현재 판정의 근거입니다. 타임아웃·속도·기하·권한은 바꾸지 않았고, 원29의 이미 누락된 자료나 실물 성공을 복구한 것으로 표시하지 않습니다.</p>'
    elif 'reboot_comparison30' in result:
        lead+='<p>사용자 재부팅(20:57:50KST) 후 같은 설치23·1674파일·같은 수집기/시험 SHA로 원25 저장 장면을 재시험했습니다. 의자 이동은55.876초 후 도착했고,36단계 전체와 정상 종료/정리가 PASS입니다. 재부팅 전29의 같은 목표는10.708초 후 ISAAC_UPDATE_STALLED516ms로 실패했습니다. DWM privatecommit·커널 풀·시스템 commit 누적량이 크게 줄었지만 특정 누수 함수나 RAM 단독 원인은 미확정입니다. 확인된 실패진단 allowlist 계약 결함은 같은-source 비교를 위해 그대로 두었고, 전체 준비 완료·실물 성공으로 판정하지 않습니다. 원29/27 gate는 원문 그대로 보존합니다.</p>'
    elif 'memory_retry27_29' in result:
        lead+='<p>재부팅 없이 설치23의 실제 fresh27/cold27/lineage27/history27은 각각39/14/10/5 통과했습니다. 그러나 원25 저장 장면의29 시험은 의자 이동 중 ISAAC_UPDATE_STALLED516ms로 실패했습니다. 당시 가용RAM650.9/600.8MiB를 기록했고, 정확한 실패 CPU 진단이 누락되는 allowlist 계약 결함도 확인했습니다. RAM·DWM·페이징 중 단독 원인은 아직 미확정입니다. 같은 버전·같은 장면의 재부팅 비교는 NOT_RUN이며 자동 재부팅하지 않았습니다. App/Isaac은 정상 종료했습니다. 실제 센서 분석·cold GET 복원은 이번 설치에서 통과했지만, 저장 원자료의 차체 이동은 여전히 UNKNOWN입니다.</p>'
    else:
        lead+='<p>선택된 실제 여정과 최종 게이트를 기준으로 판정합니다. 일부 통과는 전체 완료나 실제 로봇 성공을 뜻하지 않습니다.</p>'
    lead+='<pre>'+escape(json.dumps(result['final_actual_scope'],ensure_ascii=False,indent=2))+'</pre>'
    for folder,label in ((f'ui-{a}','최종 설치본 · 새 채팅부터 전체 SIM 시험'),(f'ui-reproduction-{b}','별도 원 저장 장면 · 전체 재시험')):
        video=OUT/folder/'recording/app-screen.mp4'
        if video.is_file():lead+='<h3>'+label+'</h3><video controls preload="metadata" src="'+href(video)+'"></video><p>'+link(video,label+' MP4')+'</p>'
    if 'final_media_qa' in result:lead+='<p>'+link(media,'원 인코딩 전체 디코딩·대표 화면 검토')+'</p>'
    html=html.replace('<h2>수정한 범위</h2>',lead+'<h2>수정한 범위</h2>',1)
    if 'background_process_audit' in result:
        audit=result['background_process_audit']['value']
        html+='<h2 id="background-audit">후속 백그라운드 프로세스 감사 — 드라이버 변경 전</h2><p>'+link(background_audit,'PID·생성 시각·도구 분류·메모리 원자료')+'</p><p>추적된 과거 TwinPulse 소유 식별자 중 현재 생존 '+str(len(audit['historical_owned_still_alive']))+'개, 현재 TwinPulse App/엔진과 시험·녹화 후보는0개입니다. 재사용 PID4개는 과거 프로세스로 오인하지 않았습니다. 그러나 Computer Use/Node 도구19개와 REA 전송12개는 남아 있습니다. 이것만으로 불필요한 종료 누락이나 DWM 원인이라고 확정할 수 없습니다.</p>'
        html+='<table><tr><th>관측 분류</th><th>프로세스 수</th><th>WS 단순합 MiB</th><th>Private commit 단순합 MiB</th></tr>'
        for group in audit['groups']:
            html+='<tr><td>'+escape(group['role'])+'</td><td>'+str(group['process_count'])+'</td><td>'+format(group['observed_working_set_sum_bytes']/1048576,',.2f')+'</td><td>'+format(group['observed_private_commit_sum_bytes']/1048576,',.2f')+'</td></tr>'
        html+='</table><p>WS 합은 공유 페이지 중복이 있어 실제 사용 RAM의 정확한 합이 아닙니다. privatecommit도 RAM/pagefile 실사용량이 아닙니다. <a href="https://learn.chatgpt.com/docs/extend/mcp?surface=cli">OpenAI Docs</a>는 STDIO 도구가 로컬 프로세스로 실행됨을 설명하지만, 이PC의 여러 클라이언트가 모두 필요한지나 누수 여부까지 증명하지 않습니다. 앞선 JS reset은 kernel/bindings 초기화이지 모든 MCP 서버 종료를 뜻하지 않습니다. 이번 감사는 읽기 전용이며 프로세스 종료·플러그인 비활성화·드라이버 설치0입니다.</p>'
    if 'authorized_tool_cleanup' in result:
        html+='<h2 id="authorized-cleanup">종료 승인 후 실제 수행·남은 한계</h2><p>개별 소유/사용 종료가 확정된 시험 프로세스는 현재 없었습니다. 지원되는 own JS kernel reset만 수행했고, MCP 전송 강제종료0·31/20합51개는 전후 그대로입니다. 이전 감사35의19/12합31개보다 늘었지만 이것만으로 누수나 원31 네트워크 오류 원인을 확정하지 않습니다. DWM privatecommit도 reset 전후 동일합니다. 현재 대화·다른 작업과의 공유 여부가 불명확해 일괄 종료하지 않았습니다. Codex만 정상 종료·재실행한 뒤 비교하는 다음 확인이 필요하며 PC재부팅/driver변경은 아직 제안된 필수조건이 아닙니다.</p><pre>'+escape(json.dumps(result['authorized_tool_cleanup'],ensure_ascii=False,indent=2))+'</pre>'
    if 'codex_reopen37' in result:
        html+='<h2 id="codex-reopen">사용자 정상 재실행 후 비교 — 위 종료 한계의 후속 결과</h2><p>Codex 정상 종료·재열기 후 기존 도구51개와 Codex17개는 PID+생성 시각 대조에서 모두 사라졌고 새 도구는11개였습니다. 도구 WS 단순합은2.43→0.586GB로 감소했습니다(공유 중복 가능). DWM privatecommit 약7.63GB는 남았으나 상주 WS는 이후 감소했고, 일반33 시작 직전 가용RAM은 약6.11GB까지 회복했습니다. 도구 잔류만으로 DWM 전체나 원31 네트워크 실패의 단독 원인을 확정하지 않습니다. 이미 재실행한 상태이므로 같은 재시작을 다시 요구하지 않습니다.</p><pre>'+escape(json.dumps(result['codex_reopen37'],ensure_ascii=False,indent=2))+'</pre>'
    if 'original_preview_failure37' in result:
        html+='<h2 id="original-preview37">원37 — 39단계 수행과 전체 실패를 분리</h2><p>설치26에서 원 장애물 접근·후진을 포함한39단계는 통과했지만, 최종 명시 fault 구간의 보관된 미리보기 교체409 때문에 whole FAIL이었습니다. 원37을 소급 PASS로 바꾸지 않습니다. 제품의1장cache·정확SHA 거절·픽셀유지·1초freshness는 변경하지 않고, 새 기록기에 정확 context/native 시각·static권한·동일장면 새decode를 보존하도록 했습니다. 일반 오류/abort와 Stop 증명은 별도 필수입니다.</p><pre>'+escape(json.dumps(result['original_preview_failure37'],ensure_ascii=False,indent=2))+'</pre>'
    if 'snapshot_failure39' in result:
        html+='<h2 id="snapshot39">원39 — 도착 직후 기록 저장과 화면 차단</h2><p>침대 명령은 이미도착했지만 실제stale204 뒤 static-preview로만복구되어 whole FAIL이었습니다. 원체크707ms를단순age만료로설명하지않습니다. 동시에1234event/3.8MB 저장에1.438초가걸렸습니다. per-event 인코딩은오프라인CPU/시간을줄이고정확bytes/SHA를유지했지만 단독원인·최대지연개선의증거는아닙니다. 현재전체시험은이전실패와분리합니다.</p><pre>'+escape(json.dumps(result['snapshot_failure39'],ensure_ascii=False,indent=2))+'</pre>'
    if 'viewport_failure41' in result:
        html+='<h2 id="viewport41">원41 — 다음 프레임의 연결·전송 지연</h2><p>60초hold 약39초에서기존613프레임이1183ms로만료됐습니다. 다음614프레임HTTP는2047ms후URLError였고JPEG16/raw대기15ms였습니다. 다른GET은응답했으며전체backend정체로단정하지않습니다. 당시snapshot은실패뒤시작했으므로원인에서제외합니다. 원errno/OS근본원인은UNKNOWN입니다. 영상전용owner연결재사용/원2초·POST재시도0/독립정리·진단결속을새설치에서별도검증합니다.</p><pre>'+escape(json.dumps(result['viewport_failure41'],ensure_ascii=False,indent=2))+'</pre>'
    if 'history_failure43' in result:
        html+='<h2 id="history43">원43 — 동작·재열기 통과와 이력 조회 실패를 분리</h2><p>설치28의 새 생성39단계·재열기14단계는 통과했지만 원 실물 로그 조회가20초 뒤 실패해 전체는미완료였습니다. 원GET 서버단계·응답시작 기록이없어 단독원인은UNKNOWN입니다. 전체119.5MB/42484행 검증은유지하며 마지막100개만깊게복사하도록줄였습니다. 격리실행5.2–5.4→2.91–2.92초·반환1101367바이트/SHA동일은CPU개선증거일뿐 원20초문제의해결증명은아닙니다. 새설치전체여정은별도로판정하고 이전FAIL을지우지않습니다.</p><pre>'+escape(json.dumps(result['history_failure43'],ensure_ascii=False,indent=2))+'</pre>'
    if 'scan_failure45' in result:
        html+='<h2 id="scan45">원45 — 스캔 표시 만료와 비원자 시험 시각</h2><p>21단계 뒤 스캔 표시 검사에서 실패했습니다. 원827ms는 단계 시간이고 scan age가 아닙니다. 원stamp/원자 관측시각이 없어 이전100ms age tick과 도구IPC 중 정확한 기여는UNKNOWN입니다. 제품은 원scan700ms 전용 만료 요청과 렌더 시각 검사를 보완했고, 시험은 같은renderer 순간의DOM·시각과 별도의요청/수신시각을 보존합니다. 기존5초창에서명시absence만재관측하며 visible stale/preview/다른epoch는후행fresh로덮지않습니다. 이벤트루프정체에서hard-real-time만료를보장한다는뜻은아닙니다.</p><pre>'+escape(json.dumps(result['scan_failure45'],ensure_ascii=False,indent=2))+'</pre>'
    if 'wrong_interpreter_supplementary39' in result:
        html+='<h3>보조39 최초 실행환경 오류도 보존</h3><pre>'+escape(json.dumps(result['wrong_interpreter_supplementary39'],ensure_ascii=False,indent=2))+'</pre>'
    if 'native_capture_probe38' in result:
        html+='<h2 id="capture-probe">로봇·Isaac 없는 제한 캡처 분리 시험</h2><p>사용자가 화면 켜짐·잠금 해제를 확인했습니다. 직접 만든 작은 Tk 창의 접근성 조회는 됐지만 native 캡처는 FrameArrived/캡처 시간 초과2회로 실패했고 더 반복하지 않았습니다. 창은120초 후 자동 종료됐습니다. 이118개 DWM 표본에서 종전의 지속적인 privatecommit 증가를 재현하지 못했으므로 캡처=누수 원인으로 확정하지 않습니다. 이 시험은 Electron/Isaac 인수나 native AltF4 경로 재현이 아닙니다. 실제 앱은 별도 AX·동일 BrowserWindow 시험으로 검증했습니다.</p><pre>'+escape(json.dumps(result['native_capture_probe38'],ensure_ascii=False,indent=2))+'</pre>'
    if 'gc_failure33' in result:
        html+='<h2 id="gc-failure33">원33 새 전체시험 실패 — 실제625ms 정체와 GC 시간 결속</h2><p>새생성·두SIM등록·네방향·60초연속·90도·360도 등16단계 뒤 Beta 장애물접근 중 ISAAC_UPDATE_STALLED625ms가 발생했습니다. 직전tail577ms 중 idle570ms/process GC563ms가 겹쳤고 Kit threadCPU/gc는0이었습니다. collector세대·촉발코드·CPU는 당시 기록하지 않아 근본원인은미확정입니다. 이전release구간409를 이실패의원인으로 잘못 안내한 점을 정정합니다. 원문·ID·시각·영상과 실제정상종료는보존했고 후속cold/원장면34는미실행입니다. 보조raw replay를실제UI중병렬실행한부하도혼입되었으며 단독원인으로확정하지않습니다.</p><pre>'+escape(json.dumps(result['gc_failure33'],ensure_ascii=False,indent=2))+'</pre>'
    if 'gc_diagnostic_source_review35' in result:
        html+='<h2 id="gc-origin-ledger">GC 원인 추적 보완 — 성능 해결 선언 아님</h2><p>Host 한곳만상세채집하고bounded32개 slow별도보존·collector세대/thread/함수위치/CPU·phase복원을추가했습니다. Astra가발견한들여쓰기·예외경계·음성시험누락을설치전에보완했습니다. GC설정/수집시점/입력·출력만료/속도·안전기준은바꾸지않았습니다. 현재설치실제whole조건이확인되기전READY로표시하지않습니다.</p><pre>'+escape(json.dumps(result['gc_diagnostic_source_review35'],ensure_ascii=False,indent=2))+'</pre>'
    if 'gc_failure35' in result:
        html+='<h2 id="gc-failure35">원35 원인 좁힘 — raycast 스레드의 실제2세대GC</h2><p>보조계산을겹치지않은새35도16단계뒤828ms로실패했습니다. GC cycle2434는TwinPulseSimRaycast/세대2/MATCHED, wall735ms·collector CPU734.375ms이며visit→cast→scan에서촉발됐습니다. 원nested재귀함수가ray당자기closure순환1개를남기는결함을격리시험RED로확인했습니다. 수집된1856개전부의출처나전체GC비용을이결함만으로단정하지않습니다.</p><pre>'+escape(json.dumps(result['gc_failure35'],ensure_ascii=False,indent=2))+'</pre>'
    if 'raycast_cycle_fix' in result:
        html+='<h2 id="raycast-cycle-fix">반복 순환 garbage 제거·동일기하 검증</h2><p>builder는module함수로옮기고ray는right먼저push/left먼저pop하는명시DFS로변경했습니다. node앞취소검사/최초hit/기존epsilon·range·rounding은유지합니다. GC정책·watchdog을바꾸지않았습니다. source검토/격리시험과아래현재설치실제whole성적을분리합니다.</p><pre>'+escape(json.dumps(result['raycast_cycle_fix'],ensure_ascii=False,indent=2))+'</pre>'
    if 'memory_retry27_29' in result:
        memory=result['memory_retry27_29'];failure=memory['value']
        html+='<h2 id="memory-reboot">재부팅 전 메모리 원자료·동일본 비교 준비</h2><p>물리 RAM과 private commit은 다릅니다. 시스템1초·전체 프로세스5초·GPU30초 목표 표본이며 중간 피크와 수집 공백은 확정할 수 없습니다.27 최저281.7MiB는 엔진 시작 중으로, 같은 의자 주행 통과 대조군이 아닙니다.29 실패 뒤 idle 약10분이 마지막 UI 단계명에 포함되므로 exact request/event 시간창만 주행 비교에 사용합니다.900초 기록 종료부터 native 종료까지 공백은 별도 stage/tail과 구분했습니다.</p>'
        html+='<p>'+link(memory_review,'원29 실패 시각·명령·CPU/RAM 표본·재부팅 후 순서')+'</p>'
        snapshots=memory['component_snapshots'];before=snapshots['failure_preceding_5s_sample'];after=snapshots['post_close_tail_last_5s_sample']
        def mib(value):return format(value/1048576,',.2f')+' MiB'
        html+='<p>아래는 실패 직전5초 프로세스 표본('+escape(datetime.fromtimestamp(before['at_ms']/1000,timezone.utc).isoformat())+')과 종료 후45초 tail의 마지막 프로세스 표본('+escape(datetime.fromtimestamp(after['at_ms']/1000,timezone.utc).isoformat())+')입니다. 실패 그516ms 전체의 메모리 피크는 아닙니다.</p><table><tr><th>부문</th><th>실패 직전 WS / private commit</th><th>종료 후 WS / private commit</th></tr>'
        for label,before_value in before['components'].items():
            after_value=after['components'][label]
            html+='<tr><td>'+escape(label)+'</td><td>'+mib(before_value['working_set_bytes'])+' / '+mib(before_value['private_committed_bytes'])+' (누락 '+str(before_value['missing_counters'])+')</td><td>'+mib(after_value['working_set_bytes'])+' / '+mib(after_value['private_committed_bytes'])+' (누락 '+str(after_value['missing_counters'])+')</td></tr>'
        for field,label in (('PhysicalAvailable_bytes','시스템 가용 물리 RAM'),('CommitTotal_bytes','시스템 commit'),('SystemCache_bytes','시스템 cache (가용량과 중첩)'),('KernelPaged_bytes','커널 paged pool'),('KernelNonpaged_bytes','커널 nonpaged pool')):
            html+='<tr><td>'+label+'</td><td>'+mib(before['system'][field])+'</td><td>'+mib(after['system'][field])+'</td></tr>'
        html+='</table><p>WS는 공유 페이지가 포함돼 행별 합을 물리 RAM 사용량으로 계산하지 않습니다. private commit은 실제 RAM·현재 pagefile 사용량과 다릅니다. GPU·pagefile·표본 누락·원 timestamp는 아래 원자료에 보존했습니다. 권한상 읽지 못한 기타 프로세스는 누락 수로 표시하며0 사용으로 해석하지 않습니다.</p>'
        for entry in memory['summaries']+memory['stages']:
            html+='<p>'+link(ROOT/entry['reference']['path'])+'</p>'
        html+='<pre>'+escape(json.dumps({k:failure[k] for k in ('launch_id','original_event','trace_bounds','diagnostic_defect','interpretation','after_reboot')},ensure_ascii=False,indent=2))+'</pre>'
        html+='<p>카운터 정의: '+''.join('<a href="'+escape(url)+'">Microsoft 공식 설명</a> ' for url in memory['official_counter_references'])+'</p>'
    if 'reboot_comparison30' in result:
        current_comparison=result['reboot_comparison30'];value=current_comparison['value'];before=value['before_reboot_app_closed'];after=value['after_reboot_app_not_started']
        section='<h2 id="reboot-result">재부팅 후 동일본·동일장면 실제 결과</h2><p>20:57:50KST 실제 boot 변경·Windows/설치/collector/UI SHA 일치 검사를 통과했습니다.36단계 전체 PASS·의자 도착55.876초·정상Exit/root0/Job2/backend0·lock/포트0입니다. 명시 fault 주입은 정상 조종과 구분했고 일반 조종 interception0을 유지했습니다. 새 모델HTTP/USD0·실물접속0. 최종 진단 결함 수정/새설치 인수·물리 시험까지 완료한 판정은 아닙니다.</p>'
        section+='<table><tr><th>앱 닫힘 기준 카운터</th><th>재부팅 전</th><th>재부팅 후·앱 실행 전</th></tr>'
        for label,old_value,new_value,unit in (
            ('가용 물리 RAM',before['memory']['AvailableMBytes'],after['memory']['AvailableMBytes'],'MiB'),
            ('시스템 commit',before['memory']['CommittedBytes']/1e9,after['memory']['CommittedBytes']/1e9,'GB'),
            ('DWM private commit (실제 RAM 아님)',before['dwm']['private_committed_bytes']/1e9,after['dwm']['private_committed_bytes']/1e9,'GB'),
            ('DWM working set',before['dwm']['working_set_bytes']/1e6,after['dwm']['working_set_bytes']/1e6,'MB'),
            ('커널 nonpaged pool',before['memory']['PoolNonpagedBytes']/1e9,after['memory']['PoolNonpagedBytes']/1e9,'GB'),
            ('커널 paged pool',before['memory']['PoolPagedBytes']/1e9,after['memory']['PoolPagedBytes']/1e9,'GB')):
            section+='<tr><td>'+label+'</td><td>'+format(old_value,',.3f')+' '+unit+'</td><td>'+format(new_value,',.3f')+' '+unit+'</td></tr>'
        section+='</table><p>background 앱 수·캐시·uptime 및 자원 상태가 달라졌습니다. 드라이버 버전 변경은 하지 않았습니다. 주로 줄어든 카운터 범주는 확인했지만 TwinPulse만의 누수나 정확한 allocator를 확정할 수 없습니다. 재부팅 직후/앱 종료후·실제 chair 요청창은 따로 비교합니다.</p><p>'+link(reboot,'실제 재부팅 비교·exact chair 창·모든 SHA')+' · '+link(OUT/'ui-reproduction-30/recording/app-screen.mp4','같은 설치 앱 실제 시험 전체 녹화')+'</p><figure><img loading="lazy" src="ui-reproduction-30/destination-chair-arrived.png"><figcaption>재부팅 후 원 장면·실제 의자 도착 화면 (SIM)</figcaption></figure>'
        section+='<details><summary>원29/새30 exact 비교·한계·인수 범위</summary><pre>'+escape(json.dumps(current_comparison,ensure_ascii=False,indent=2))+'</pre></details>'
        # The old before-reboot record intentionally retains its then-NOT_RUN
        # status. Present the completed comparison first; never rewrite originals.
        if '<h2 id="memory-reboot">' in html:html=html.replace('<h2 id="memory-reboot">',section+'<h2 id="memory-reboot">재부팅 전 당시 기록 — ',1)
        else:html+='<p>다음은 이전 설치23의 재부팅 비교 이력이며, 현재 수정본의 인수와 구분합니다.</p>'+section
    if 'diagnostic_contract_fix' in result:
        html+='<h2 id="diagnostic-final">현재 설치본 진단 계약 수정·실제 반출 검증</h2><pre>'+escape(json.dumps(result['diagnostic_contract_fix'],ensure_ascii=False,indent=2))+'</pre>'
    if 'current_failed_review' in result:
        review=result['current_failed_review']['value']
        html+='<h2 id="current-failed-review">현재31 실패·OS 재연결·DWM 추세</h2><p>'+link(failed_review,'정확한 ID·원 시각·원 SHA·미실행 범위')+'</p>'
        html+='<p>아래 DWM 값은 해당 시각에 가장 가까운 보호 프로세스 표본입니다. WS는 resident/shared를 포함하고 privatecommit은 실제 RAM·pagefile bytes가 아닙니다. 이름·PID는 관측 식별이지 종료 권한 증거가 아닙니다.</p><table><tr><th>단계</th><th>표본 UTC / 목표와 차이</th><th>DWM WS MiB</th><th>Private commit MiB</th></tr>'
        for point in review['dwm']['stages']:
            row=point['dwm']
            html+='<tr><td>'+escape(point['label'])+'</td><td>'+datetime.fromtimestamp(point['at_ms']/1000,timezone.utc).isoformat()+' / '+format(point['sample_offset_ms'],'.1f')+'ms</td><td>'+format(row['working_set_bytes']/1048576,',.2f')+'</td><td>'+format(row['private_committed_bytes']/1048576,',.2f')+'</td></tr>'
        html+='</table><p>현재 설치된 Intel27.20.100.8935/10세대CPU는 <a href="https://www.intel.com/content/www/us/en/support/articles/000058381/graphics.html">Intel의 알려진 DWM 메모리 누수 안내</a>와 버전·플랫폼상 부합합니다. 이 PC 원인 확정이나 업데이트 성공 보장은 아닙니다. 호환 OEM 패키지 검토·새 드라이버 설치는 이번 실행에서 하지 않았습니다.</p>'
        html+='<pre>'+escape(json.dumps({k:review[k] for k in ('failure_interpretation','diagnostic_fix','actual_independent_review','not_run','next_scope')},ensure_ascii=False,indent=2))+'</pre>'
    html+='<h2>원 실패·변경하지 않은 기준</h2><p>원 operation '+result['physical_operation_id']+' / '+str(receipt['saved'])+'행, 모든 segment bytes/SHA 재검사. '+link(ROOT/'outputs/robot-powered-20261021-report/report.html','원 실패·센서 이동량 분석')+'</p><pre>'+escape(json.dumps(result['unchanged'],indent=2))+'</pre>'
    html+='<details><summary>모든 시도 '+str(len(attempts))+'개 · 원 실패·보조 시험 포함</summary><table><tr><th>원 자료</th><th>판정</th><th>설치·오류</th></tr>'+rows+'</table></details><h2>실제 설치 화면</h2>'+shots.replace('<img src=','<img loading="lazy" src=')
    html+='<h2>실제 재시험 녹화·실패 원문</h2>'
    for entry in result['actual_current_turn_recordings']:html+='<p>'+link(ROOT/entry['path'])+'</p>'
    html+='<pre>'+escape(json.dumps(result['sim_stall'],ensure_ascii=False,indent=2))+'</pre>'
    html+='<h2>빈 프레임 응답의 실제 원인 비교</h2><p>원19는39단계 통과 뒤 빈204 응답57개의 native abort 때문에 전체FAIL로 보존했습니다. 별도 읽기 전용 진단21b는 같은 Electron에서 본문을 끝까지 읽은4회 loadingFinished, 읽지 않은4회 native abort를 기록했습니다. 제품은 원2초 이내0바이트 소비·context 재검사를 추가했고 시험기의 일반 abort FAIL 기준은 유지했습니다. 이 비교를 과거 다른 정체의 해결 증거로 쓰지 않습니다.</p>'
    html+='<p>'+escape(result['no_content_diagnostic_limits'])+'</p><ul>'+''.join('<li>'+link(ROOT/x['reference']['path'])+'</li>' for x in result['no_content_diagnostic'])+'</ul>'
    html+='<h2>상태 조회 지연·수정 경계와 보존한 보조 실패</h2><pre>'+escape(json.dumps({k:result[k] for k in ('state_poll_contention23','supplementary_initial_failures')},ensure_ascii=False,indent=2))+'</pre>'
    html+='<h2>원25 전체 시험 실패·현재 자원 관측</h2><pre>'+escape(json.dumps(result.get('resource_stall25'),ensure_ascii=False,indent=2))+'</pre>'
    html+='<h2>명령별 센서 비교 — 구현·원문 재생과 미인수 구분</h2><pre>'+escape(json.dumps(result['motion_review_source'],ensure_ascii=False,indent=2))+'</pre>'
    html+='<h2>현재 판정</h2><p class="warn">'+escape(result['overall'])+'</p>'
    if 'catalog_read53' in result:
        html+='<h2>원47 종료 거절·48/50/53 실패와 별도 준비</h2><pre>'+escape(json.dumps({k:result[k] for k in ('preserved_late_failures_and_preparations','diagnostic_worker_wake_fix','catalog_read53','saved_geometry_preparation_limit')},ensure_ascii=False,indent=2))+'</pre>'
    html+='<h2>최종 설치본 실제 여정·일반 창</h2><pre>'+escape(json.dumps({k:result.get(k) for k in ('final_actual_scope','normal_lifecycle','native_normal_evidence','final_engine_cleanup')},ensure_ascii=False,indent=2))+'</pre>'
    html+='<h2>별도 원 장면·시험기 오류·음성시험</h2><pre>'+escape(json.dumps({k:result.get(k) for k in ('saved_geometry_comparison','final_negative_attempts')},ensure_ascii=False,indent=2))+'</pre>'
    html+='<h2>승인한 R1–R5의 구현과 남은 검증 범위</h2><pre>'+escape(json.dumps(result['implementation_scope'],ensure_ascii=False,indent=2))+'</pre>'
    html+='<h2>비용·최종 게이트·미검증</h2><pre>'+escape(json.dumps({k:result.get(k) for k in ('budget_final','gate_result','final_binding_issues','attribution','remaining','not_run','boundaries')},ensure_ascii=False,indent=2))+'</pre>'
    html+='<h2>현재 재개 조건·정확한 다음 작업</h2><pre>'+escape(json.dumps(result['resume_plan'],ensure_ascii=False,indent=2))+'</pre>'
    html+='<h2>다음 현장 세션 순서 — 이번에는 미실행</h2><ol>'+''.join('<li>'+escape(x)+'</li>' for x in result['next_supervised_session_not_run'])+'</ol>'
    html+='<p>'+link(OUT/'result.json','모든 ID·SHA·기능별 판정 JSON')+'</p><h2>기존 요청 60초 SIM 데모</h2><p>이번 수정 설치본의 물리 검증 영상이 아닙니다.</p><video controls preload="metadata" src="'+href(old/'TwinPulse-SIM-Demo-60s-2026-10-21.mp4')+'"></video></html>'
    (OUT/'report.html').write_text(html,encoding='utf-8')
    print(json.dumps(dict(status=result['overall'],release_id=current['release_id'],attempts=len(attempts),raw_verified=len(rawfiles),report=str(OUT/'report.html'))))

if __name__=='__main__':main()
