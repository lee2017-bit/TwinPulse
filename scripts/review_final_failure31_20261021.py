# SPDX-License-Identifier: Apache-2.0
"""Read-only analysis of immutable failed UI/OS evidence; never starts the App."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/robot-continuous-repair-20261021'
sys.path.insert(0, str(ROOT / 'packages/twinpulse_core/src'))
from twinpulse_core.fleet_diagnostics import checked_work


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def ref(path):
    return dict(path=path.relative_to(OUT).as_posix(), bytes=path.stat().st_size,
                sha256=sha256(path.read_bytes()).hexdigest())


def main():
    ui_path = OUT / 'ui-31/result.json'
    ui = read(ui_path)
    assert ui['status'] == 'FAIL'
    final_step = ui['steps'][-1]
    display = json.loads(final_step['error'].split('Motion display is not current: ', 1)[1])
    failures = [r for r in ui['request_failures'] if r['error'] == 'net::ERR_NETWORK_CHANGED']
    assert len(failures) == 3 and all(r['method'] == 'GET' and not r.get('exiting') for r in failures)
    operation_path = OUT / 'failed-ui31-original-logs/09-3d4008c014b54d6397782b094c5b2ef7.json'
    operation = read(operation_path)
    failed = next(e for e in operation['events'] if e['event_sequence'] == 570)
    assert failed['reason'] == 'INPUT_STALE' and failed['runtime_work'] is not None
    assert checked_work(failed['runtime_work']) == failed['runtime_work']
    assert {'thread_cpu_s', 'process_cpu_s'} <= failed['runtime_work']['host'].keys()
    cpu = [e for e in operation['events'] if isinstance(e.get('runtime_work'), dict)
           and {'thread_cpu_s', 'process_cpu_s'} <= (e['runtime_work'].get('host') or {}).keys()]
    network_path = OUT / 'network-events31.json'
    network = read(network_path)
    os_events = [e for e in network['events'] if e['Id'] in (8001, 8003, 10000, 10001)]
    assert {8001, 8003, 10000, 10001} <= {e['Id'] for e in os_events}
    protected_path = OUT / 'memory-final31/protected-processes.jsonl'
    protected = [json.loads(line) for line in protected_path.read_text(encoding='utf-8').splitlines()]
    sample_path = OUT / 'memory-final31/samples.jsonl'
    samples = [json.loads(line) for line in sample_path.read_text(encoding='utf-8').splitlines()]
    points = []
    for label, at in (
        ('FIRST_NORMAL_BEFORE_CLOSE', '2026-10-21T21:42:51.936+09:00'),
        ('FIRST_NORMAL_AFTER_CLEANUP', '2026-10-21T21:42:57+09:00'),
        ('BEFORE_NEXT_START', '2026-10-21T21:43:58+09:00'),
        ('RESTART_AFTER_CLEANUP', '2026-10-21T21:46:14+09:00'),
        ('FRESH_FAILURE', '2026-10-21T21:50:02.093+09:00'),
        ('FINAL_AFTER_CLEANUP', '2026-10-21T21:51:44.931+09:00'),
        ('FINAL_RECORD_END', '2026-10-21T21:54:44.775+09:00'),
    ):
        target = datetime.fromisoformat(at).timestamp() * 1000
        p = min(protected, key=lambda r: abs(r['at_ms'] - target))
        s = min(samples, key=lambda r: abs(r['at_ms'] - target))
        points.append(dict(label=label, target=at, at_ms=p['at_ms'], sample_offset_ms=p['at_ms']-target,
                           dwm=next(r for r in p['rows'] if r['name'].lower() == 'dwm'),
                           system_at_ms=s['at_ms'], system=s['system']))
    before_path = OUT / 'dwm-before-own-session-reset33.json'
    after_path = OUT / 'dwm-after-own-session-reset33.json'
    before, after = read(before_path), read(after_path)
    assert not before['twinpulse_or_kit'] and not after['twinpulse_or_kit']
    assert before['boot_at'] == after['boot_at']
    before_dwm, after_dwm = before['dwm'][0], after['dwm'][0]
    source_review_path = OUT / 'diagnostic-source-review31.json'
    source_review = read(source_review_path)
    release = source_review['release_id']
    assert ui['desktop']['engine']['release_id'] == release
    value = dict(
        schema='current-final-failed-ui-review-1.0', generated_utc=datetime.now(timezone.utc).isoformat(),
        status='PARTIAL_NOT_READY_FINAL_UI_FAILED_ENVIRONMENT_UNRESOLVED',
        release_id=release, source_sha256=source_review['source_manifest_sha256'],
        actual_attempt='31', reproduction_attempt='32',
        launch_id=ui['desktop']['engine']['launch_id'], project_id=operation['project_id'],
        scene_revision=display['scene_revision'], operation_id=operation['operation_id'], input_sha256=ui['input_sha256'],
        final_step=final_step, preceding_pass_steps=sum(s['status']=='PASS' for s in ui['steps']),
        failed_display=display, latest_good_display=ui['display_samples'][-1], network_failures=failures,
        windows_network_events=os_events,
        failure_interpretation=dict(
            observed_chain='Windows WLAN disconnect/reconnect overlaps three native ERR_NETWORK_CHANGED GETs; App connection is unconfirmed, so live/anchors drop and renewal stops. Original INPUT_STALE is retained before later Stop completion.',
            frame_age_within_original_1000_ms=display['frame_age_ms'] < 1000,
            scope='This attempt failed. No continuation or old-release PASS replaces it. The OS reconnect trigger remains UNKNOWN.',
            not_proved=['DWM or memory pressure caused ERR_NETWORK_CHANGED', 'A past host stall caused this failure', 'A graphics driver is the confirmed allocator or sole cause']),
        diagnostic_fix=dict(
            status='STRICT_SOURCE_CONTRACT_FIXED_ACTUAL_INSTALLED_PERSISTED_FIELDS_OBSERVED',
            exact_product_delta=source_review['exact_product_delta_from_frozen23'],
            actual_cpu_event_count=len(cpu), failed_event={k:failed[k] for k in ('event_sequence','utc','reason','runtime_timing','runtime_work','runtime_fault')},
            original_operation=ref(operation_path),
            limitation='This is an actual installed persisted-operation read, not a completed UI download/cold roundtrip. That required branch remains NOT_RUN. No natural host-stall branch PASS is inferred. Original29 null diagnostics are unrecoverable.'),
        dwm=dict(
            stages=points, before_own_session_reset=before, after_own_session_reset=after,
            reset_elapsed_s=(datetime.fromisoformat(after['sampled_at'])-datetime.fromisoformat(before['sampled_at'])).total_seconds(),
            reset_private_change_bytes=after_dwm['PrivateMemorySize64']-before_dwm['PrivateMemorySize64'],
            reset_working_set_change_bytes=after_dwm['WorkingSet64']-before_dwm['WorkingSet64'],
            reset_outcome='NO_MATERIAL_RELEASE_OBSERVED_NOT_PROOF_OF_CAUSAL_ATTRIBUTION',
            meaning='Working set includes resident/shared pages. Private commit is not physical RAM or actual pagefile bytes. First post-close increase precedes the OS reconnect; the trigger/allocator remains UNKNOWN.',
            official_candidate=dict(url='https://www.intel.com/content/www/us/en/support/articles/000058381/graphics.html',
                article_id='000058381', last_reviewed='2022-08-29', affected='Windows10, 6th-10th-generation Intel, driver27.20.100.8587 or newer',
                official_resolution='Intel DCH30.0.101.1191 or newer; actual compatible OEM/current package must be checked before any installation.',
                local_intel='27.20.100.8935', local_cpu=before['cpu'],
                inference='VERSION_AND_PLATFORM_MATCH_A_KNOWN_RISK_NOT_THIS_PC_CAUSAL_PROOF')),
        actual_independent_review=dict(agent='/root/astra_continuous_path_review21', model='gpt-6-astra', effort='xhigh', read_only=True,
            recorded_by='Main transcription of actual collaboration reviews; no new external data transmission by reviewer.',
            conclusion='Diagnostic delta has no additional confirmed source defect. Full current UI acceptance is incomplete; NOT_READY. DWM commit and resident growth after App cleanup are observed, but allocator and sole cause remain UNKNOWN. No source24 deadline/authority relaxation recommended.'),
        not_run=['Current cold UI','Current installed Analyze and next cold restore','Original saved geometry reproduction32',
                 'Full current UI-downloaded diagnostic roundtrip','New whole attempt33 and saved-geometry34 (deferred before App Start)',
                 'Physical robot/SSH/sensors/motors','Graphics/Wi-Fi driver update or OS setting changes'],
        next_scope='Review a compatible OEM Intel graphics update and OS reconnect cause before another memory-heavy session; driver installation/system changes require explicit authority. After environment is stable, rerun unchanged full final UI criteria from the beginning. Do not ask for robot power yet.',
        references=[ref(p) for p in (ui_path, operation_path, network_path, protected_path, sample_path,
            before_path, after_path, source_review_path, OUT/'memory-final31/receipt.json', OUT/'runtime-final31/receipt.json',
            OUT/'supplementary31/result.json', OUT/'supplementary33/result.json', OUT/'installed-files31.json')],
        actions=dict(robot=0, driver_install=0, system_setting_change=0, forced_process_termination=0, deletion=0, git_publish=0))
    target = OUT / 'final-failure-review31.json'
    with target.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
    print(json.dumps(dict(status=value['status'], operation_id=value['operation_id'],
                         cpu_events=len(cpu), frame_age_ms=display['frame_age_ms'],
                         reset_private_change_bytes=value['dwm']['reset_private_change_bytes'])))


if __name__ == '__main__':
    main()
