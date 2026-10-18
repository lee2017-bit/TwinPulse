# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Bounded offline comparison of the existing pure compile diagnostic boundary.

No HTTP, model, engine, robot or replay. Timing excludes trace start/finish and
flush; asynchronous writer contention inside the call is included in wall time.
Memory is a separate traced-allocation sample, NOT RSS, GPU or a leak verdict.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import time
import tracemalloc

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for package in ('twinpulse_core', 'twinpulse_app', 'twinpulse_provider'):
    sys.path.insert(0, str(ROOT/'packages'/package/'src'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--rounds', type=int, default=60)
    args = parser.parse_args()
    if not 10 <= args.rounds <= 100:
        raise SystemExit('Use 10..100 bounded rounds')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    from twinpulse_app.project_store import ProjectStore
    from twinpulse_app.site_draft import SiteDraftRecord
    from twinpulse_core.execution_diagnostics import ExecutionStore, profile_call

    before = args.project.read_bytes()
    saved = ProjectStore(args.project).load().site_draft
    if saved is None:
        raise SystemExit('A saved site draft is required')
    kwargs = dict(request_id=saved.request_id, provider_name=saved.provider_name,
                  model_id=saved.model_id, image_count=saved.image_count,
                  input_revision=saved.input_revision, plan=saved.plan,
                  placement_contract=saved.placement_contract)
    modes = ('diagnostics_off', 'events_on', 'profile_on')
    stores = {mode:ExecutionStore(output/mode, 'offline-comparison') for mode in modes[1:]}
    result = dict(status='FAIL', scope='pure_SiteDraftRecord_create_boundary', rounds=args.rounds,
                  fixture_plan_sha256=saved.plan_sha256, source_sha256=hashlib.sha256(before).hexdigest(),
                  paid_calls=0, robot_connections=0, automatic_dispatch=False, physical_authority=False,
                  timing_scope='compile_and_span_emission_only_excludes_trace_start_finish_flush',
                  cpu_timer_note='Short calls may quantize to zero on Windows; compare aggregate mean, not a zero median.',
                  memory_scope='separate_tracemalloc_sample_not_RSS_GPU_or_leak_verdict', cases={})
    timings = {mode:[] for mode in modes}
    executions = {mode:[] for mode in modes[1:]}

    def call(mode, *, measure):
        store = stores.get(mode)
        trace = store.begin('compile_comparison', durable=False, mode=mode) if store else None
        if trace:
            executions[mode].append(trace.execution_id)
        wall, cpu = time.perf_counter_ns(), time.thread_time_ns()
        value = (profile_call(trace, 'site_validation_compile', SiteDraftRecord.create,
                              enabled=mode=='profile_on', **kwargs)
                 if trace else SiteDraftRecord.create(**kwargs))
        sample = dict(wall_s=(time.perf_counter_ns()-wall)/1e9,
                      thread_cpu_s=(time.thread_time_ns()-cpu)/1e9)
        if trace:
            trace.finish()
        if value.to_dict() != saved.to_dict():
            raise AssertionError('Diagnostics changed the compiled draft')
        if measure:
            timings[mode].append(sample)

    try:
        # Same inputs; rotate the order to avoid assigning warm/cold bias to ON.
        for _ in range(3):
            for mode in modes:call(mode, measure=False)
        for index in range(args.rounds):
            order = modes[index%3:] + modes[:index%3]
            for mode in order:call(mode, measure=True)
            for store in stores.values():
                if not store.flush(5.):raise AssertionError('Diagnostic flush incomplete')
        for mode in modes:
            for store in stores.values():store.flush(5.)
            tracemalloc.start()
            memory_before = tracemalloc.get_traced_memory()[0]
            for _ in range(10):call(mode, measure=False)
            current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            rows = timings[mode]
            case = dict(samples=rows,
                        memory_current_delta_bytes=current-memory_before,
                        memory_peak_above_initial_bytes=peak-memory_before)
            for metric in ('wall_s', 'thread_cpu_s'):
                values = sorted(row[metric] for row in rows)
                case[metric] = dict(median=statistics.median(values),
                                    mean=statistics.mean(values), total=sum(values), zero_samples=values.count(0.),
                                    p95=values[math.ceil(.95*len(values))-1], minimum=values[0], maximum=values[-1])
            if mode in stores:
                store = stores[mode]
                if not store.flush(10.) or store.health['diagnostics_degraded']:
                    raise AssertionError('Diagnostic records degraded')
                details = [store.detail(identity) for identity in executions[mode]]
                if any(value['status']!='succeeded' or value['health']['diagnostics_degraded'] for value in details):
                    raise AssertionError('Incomplete diagnostic evidence')
                case.update(event_count=sum(value['event_count'] for value in details),
                            stored_bytes=sum(path.stat().st_size for path in store.root.rglob('*') if path.is_file()),
                            health=store.health, execution_count=len(details))
            else:
                case.update(event_count=0, stored_bytes=0, execution_count=0)
            result['cases'][mode] = case
        result['source_unchanged'] = args.project.read_bytes()==before
        if not result['source_unchanged']:raise AssertionError('Source project changed')
        result['status'] = 'PASS'
    except Exception as error:
        result.update(error_type=type(error).__name__, error_code='COMPARISON_INCOMPLETE')
    finally:
        if tracemalloc.is_tracing():tracemalloc.stop()
        for store in stores.values():store.flush(10.)
        result['script_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        (output/'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print('DIAGNOSTIC_COMPILE_COMPARISON='+result['status'])
    return 0 if result['status']=='PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
