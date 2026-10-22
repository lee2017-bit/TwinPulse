# SPDX-License-Identifier: Apache-2.0
"""Offline failure-window projection; never starts an App or changes raw evidence."""
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/robot-continuous-repair-20261021'


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def ref(path):
    return dict(path=path.relative_to(OUT).as_posix(), sha256=sha256(path.read_bytes()).hexdigest())


def projection(row):
    return dict(at_ms=row['at_ms'], system=row['system'], sampler_wall_ms=row['sampler_wall_ms'],
                binding=row['binding'], processes=row.get('processes'),
                protected_process_projection=row.get('protected_process_projection'))


def main():
    trace = OUT / 'memory-before-reboot29'
    receipt = read(trace / 'receipt.json')
    assert ref(trace / 'samples.jsonl')['sha256'] == receipt['samples_sha256']
    operation = OUT / 'failed-ui-reproduction29-original-logs/11-57b746ea797e4d6d8e013bbdcf268746.json'
    events = read(operation)['events']
    event = next(e for e in events if e.get('event_sequence') == 1182)
    assert event['kind'] == 'motion_result' and event['reason'] == 'ISAAC_UPDATE_STALLED'
    failure_ms = datetime.fromisoformat(event['utc']).timestamp() * 1000
    ui = read(OUT / 'ui-reproduction-29/result.json')
    failed = next(s for s in ui['steps'] if s['status'] == 'FAIL')
    # Exact event time, not the indefinitely retained final ui_step caption.
    rows = []
    with (trace / 'samples.jsonl').open(encoding='utf-8') as stream:
        for line in stream:
            rows.append(json.loads(line))
    before = max((r for r in rows if r['at_ms'] <= failure_ms), key=lambda r: r['at_ms'])
    after = min((r for r in rows if r['at_ms'] > failure_ms), key=lambda r: r['at_ms'])
    local = [r for r in rows if failure_ms - 5000 <= r['at_ms'] <= failure_ms + 5000]
    process_rows = [r for r in rows if 'processes' in r and failure_ms - 6000 <= r['at_ms'] <= failure_ms + 6000]
    value = dict(schema='memory-failure-window-1.0', status='FAIL_OBSERVED_CAUSE_UNRESOLVED',
        launch_id='bf35d5f9b7284c1a80546e470689c931', original_event=event,
        failure_at_ms=failure_ms, failed_ui_step=failed,
        references=[ref(operation), ref(trace / 'metadata.json'), ref(trace / 'receipt.json'), ref(trace / 'samples.jsonl'), ref(OUT / 'ui-reproduction-29/result.json')],
        failure_bracketing_samples=[projection(before), projection(after)],
        system_window=[dict(at_ms=r['at_ms'], delta_failure_ms=r['at_ms']-failure_ms,
            system=r['system'], sampler_wall_ms=r['sampler_wall_ms']) for r in local],
        process_window=[projection(r) for r in process_rows],
        trace_bounds=dict(first_ms=rows[0]['at_ms'], last_ms=rows[-1]['at_ms'], termination=receipt['status'],
            max_system_sample_gap_ms=max(b['at_ms']-a['at_ms'] for a,b in zip(rows,rows[1:]))),
        diagnostic_defect=dict(status='CONFIRMED_NOT_FIXED_IN_FROZEN23',
            files=['scripts/twinpulse_engine_host.py:447', 'packages/twinpulse_core/src/twinpulse_core/fleet_diagnostics.py:41'],
            cause='UpdateProbe new CPU/resource fields are rejected by the older checked_work host-key allowlist. The exact failed event runtime_work/runtime_fault are null.',
            limits='First/worst host672ms is195s before this failure, not its same-scope cause. Recent32 entries rotated during post-failure idle; exact516ms thread/GC attribution is unavailable.'),
        interpretation=[
            'Memory pressure and Kit working-set reduction are observed, not proof that DWM, hard paging or RAM alone caused this exact stall.',
            'Per-process CPU is summed across threads. PageFaultCount includes soft and hard faults, not disk-only paging.',
            'The27 minimum281.7MiB belongs to engine_start, not a same-chair-motion PASS control.',
            'The29 last UI caption persists after failure: aggregate chair-phase statistics include idle. Use exact event/request windows here and original raw timestamps.',
            'The29 trace reached900s before native close. Later stage/tail samples are separate; the unobserved gap is not continuous evidence.',
            'DWM at failure has52.46MiB working set and stable25.509GB private commit. The29 post-close working set grows to~2.557GB; do not borrow the27 post-close54MB value.',
            'No reboot yet. Keep frozen23, collector hashes and identical original25 geometry/UI scenario for the reboot comparison, then fix diagnostics in a separate build.'],
        after_reboot=dict(status='NOT_RUN', reserved_attempt='30',
            release_id='20261020T230430Z-77b57c434631', source_sha256='77b57c4346316db99bebc616bb82ca9b42ec47b72b5304f28fb1ee1af74372d6',
            project='chat_mvh8rm7k_4dafa4c1', scene_revision='37ba75c8f38889ac556d49af289203e42e3376a2c6822be8cf31ecf93459453e',
            sequence=['After saved-work reboot, verify uptime reset, source1674 files and no active launch; preserve collector and UI-contract SHA.',
                'Stage baseline; same recorder at1s/5s/30s with1800s bound,30s baseline, then same actual installed Start-Test reproduction30.',
                'On failure immediately freeze request/event/Kit/engine logs before recent ring rotates. No arbitrary model/input changes.',
                'Normal native close, matching owned-exit receipt, stage snapshot and30s post-close samples; stop only the owned recorder.',
                'Run offline --before memory-before-reboot29 --after memory-after-reboot30; compare actual motion window separately from post-failure idle.',
                'Review background-app/driver/cache/pool/commit/pagefile/GPU differences. A successful post-boot run is not sole-cause or no-recurrence proof.'],
            limits='No automatic reboot, scheduled startup or system/process/driver change. Different1800s duration avoids prior900s cutoff; collection periods/counters remain unchanged. Diagnostics contract repair and new-source acceptance follow this same-source comparison separately.'))
    target = OUT / 'memory-failure29-review.json'
    with target.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
    print(json.dumps(dict(status=value['status'], event_sequence=1182, failure_at_ms=failure_ms,
        before_available_mib=before['system']['PhysicalAvailable_bytes']/1048576,
        after_available_mib=after['system']['PhysicalAvailable_bytes']/1048576,
        reboot_comparison='NOT_RUN', output=str(target))))


if __name__ == '__main__':
    main()
