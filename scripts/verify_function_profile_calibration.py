# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Offline owner-thread profiler checks. Never opens a model/robot/Isaac service.

Exclusive derived output; original failed profile events/projects are hashed
before and after. This measures diagnostic integrity and overhead, not model
quality, physical readiness or uninstrumented production function latency.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import platform
import socket
import statistics
import sys
from threading import Event, Thread
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for package in ('twinpulse_core', 'twinpulse_app', 'twinpulse_provider'):
    sys.path.insert(0, str(ROOT / 'packages' / package / 'src'))
from twinpulse_core.execution_diagnostics import profile_call
from scripts.run_model_combination_benchmark import profile_snapshot


class Capture:
    span_id = 'a' * 32
    def __init__(self):
        self.store = self
        self.events = []
        self.references = []
    @contextmanager
    def span(self, *args, **kwargs):
        yield self
    def bind(self, **values):
        self.references.append(values)
    def emit(self, child, kind, values):
        self.events.append(dict(span_id=child.span_id, type=kind, metadata=values))


def cpu_leaf():
    return sum(i * i for i in range(6000))


def cpu_work():
    return sum(cpu_leaf() for _ in range(10))


def recursive_work(depth=8):
    return cpu_leaf() if not depth else recursive_work(depth - 1) + depth


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sample(function, basis='thread_cpu'):
    trace = Capture()
    wall, cpu = time.perf_counter_ns(), time.thread_time_ns()
    result = profile_call(trace, 'calibration', function, enabled=True, timer_basis=basis)
    wall, cpu = (time.perf_counter_ns() - wall) / 1e9, (time.thread_time_ns() - cpu) / 1e9
    marker = trace.references[-1]
    snapshot = profile_snapshot(dict(events=trace.events))
    if marker.get('profile_status') != 'VALID' or snapshot['status'] != 'VALID':
        raise AssertionError('PROFILE_CALIBRATION_INVALID')
    return dict(wall_s=wall, thread_cpu_s=cpu, profile_elapsed_s=marker['profiled_elapsed_s'],
                top= snapshot['rows'], row_count=len(trace.events)), result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--rounds', type=int, default=4)
    args = parser.parse_args()
    if not 3 <= args.rounds <= 10:
        raise ValueError('Use 3..10 bounded calibration rounds')
    output = args.output.resolve()
    if output.exists():
        raise ValueError('Calibration output must be new')
    campaign = ROOT / 'outputs/model-combination-benchmark-20261010/campaign.json'
    trials = ('luna-luna-2', 'luna-luna-4')
    originals = {campaign}
    projects = []
    for trial in trials:
        folder = ROOT / 'outputs/model-combination-benchmark-20261010' / trial / 'run-1/runtime'
        project = folder / 'active_project.json'
        projects.append(project)
        originals.add(project)
        originals.update((folder / 'diagnostics').rglob('events*.jsonl'))
        originals.update((folder / 'diagnostics').rglob('manifest.json'))
    before = {str(path.relative_to(ROOT)): digest(path) for path in sorted(originals)}
    sources = (Path(__file__), ROOT/'packages/twinpulse_core/src/twinpulse_core/execution_diagnostics.py',
               ROOT/'scripts/run_model_combination_benchmark.py')
    source_before = {str(path.relative_to(ROOT)): digest(path) for path in sources}
    result = dict(schema_version='function-profile-calibration-1.0', status='FAIL',
        scope='OFFLINE_INSTRUMENTATION_INTEGRITY_AND_OVERHEAD', rounds=args.rounds,
        HTTP=0, robot_connections=0, Isaac_runtime=False, physical_authority=False,
        original_hashes=before, source_hashes=source_before, cases={}, saved_compile=[],
        runtime=dict(python=sys.version.split()[0], implementation=platform.python_implementation(),
                     system=platform.system(), machine=platform.machine(), logical_cpu_count=os.cpu_count()),
        clocks={name:dict(implementation=info.implementation, resolution_s=info.resolution,
                         monotonic=info.monotonic, adjustable=info.adjustable)
                for name in ('thread_time', 'perf_counter') for info in (time.get_clock_info(name),)},
        interpretation='Instrumented rows include profiler overhead. Windows CPU may quantize short calls to zero. '
            'Cumulative rows overlap. No cross-model CPU ranking or wall/HTTP replacement.')
    try:
        with patch.object(socket.socket, 'connect', side_effect=AssertionError('NETWORK_FORBIDDEN')), \
             patch.object(socket, 'create_connection', side_effect=AssertionError('NETWORK_FORBIDDEN')):
            for name, fn, basis in (('nested_cpu',cpu_work,'thread_cpu'),('recursive_cpu',recursive_work,'thread_cpu'),
                                  ('waiting_cpu',lambda:time.sleep(.045),'thread_cpu'),
                                  ('waiting_wall',lambda:time.sleep(.045),'wall')):
                rows = []
                for _ in range(args.rounds):
                    row, value = sample(fn,basis)
                    if value != fn():
                        raise AssertionError('PROFILE_RESULT_CHANGED')
                    rows.append(row)
                result['cases'][name] = rows
            ready, stop = Event(), Event()
            def unrelated_background():
                ready.set()
                while not stop.is_set():
                    sum(i * i for i in range(400))
            worker = Thread(target=unrelated_background)
            worker.start()
            try:
                if not ready.wait(2):raise AssertionError('CALIBRATION_THREAD_NOT_READY')
                concurrent, value = sample(cpu_work)
                if value != cpu_work():raise AssertionError('PROFILE_RESULT_CHANGED')
                if any('unrelated_background' in row['function'] for row in concurrent['top']):
                    raise AssertionError('CROSS_THREAD_PROFILE_CONTAMINATION')
                result['cases']['unrelated_thread'] = concurrent
            finally:
                stop.set();worker.join(2)
            if worker.is_alive():raise AssertionError('CALIBRATION_THREAD_NOT_FINISHED')
            entered, release = Event(), Event()
            def held_call():
                entered.set();release.wait(3);return cpu_work()
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(sample,held_call)
                try:
                    if not entered.wait(2):raise AssertionError('CALIBRATION_THREAD_NOT_READY')
                    trace = Capture()
                    value = profile_call(trace, 'concurrent', cpu_work, enabled=True)
                    if value != cpu_work() or trace.references[-1].get('error_code') != 'PROFILE_TOOL_BUSY':
                        raise AssertionError('PROFILE_CONTENTION_NOT_VISIBLE')
                    result['cases']['busy_profiler'] = trace.references[-1]
                finally:
                    release.set()
                row, _ = future.result(timeout=4)
                result['cases']['owned_worker_thread'] = row
            from twinpulse_app.project_store import ProjectStore
            from twinpulse_app.site_draft import SiteDraftRecord
            for path in projects:
                saved = ProjectStore(path).load().site_draft
                kwargs = dict(request_id=saved.request_id,provider_name=saved.provider_name,model_id=saved.model_id,
                    image_count=saved.image_count,input_revision=saved.input_revision,
                    plan=saved.plan,placement_contract=saved.placement_contract)
                fn = lambda: SiteDraftRecord.create(**kwargs)
                modes = ('off','on');samples = {mode:[] for mode in modes}
                for index in range(args.rounds):
                    for mode in modes[index%2:] + modes[:index%2]:
                        if mode=='on':row, value = sample(fn)
                        else:
                            wall,cpu=time.perf_counter_ns(),time.thread_time_ns();value=fn()
                            row=dict(wall_s=(time.perf_counter_ns()-wall)/1e9,thread_cpu_s=(time.thread_time_ns()-cpu)/1e9)
                        if value.to_dict()!=saved.to_dict():raise AssertionError('SAVED_COMPILE_CHANGED')
                        samples[mode].append(row)
                result['saved_compile'].append(dict(trial=path.parents[2].name,
                    samples=samples, wall_mean_s={mode:statistics.mean(row['wall_s'] for row in values)
                        for mode,values in samples.items()},
                    cpu_zero_samples={mode:sum(row['thread_cpu_s']==0 for row in values)
                        for mode,values in samples.items()}, source_unchanged=digest(path)==before[str(path.relative_to(ROOT))]))
            result['status']='PASS'
    except Exception as error:
        result.update(error_type=type(error).__name__,error_code='CALIBRATION_INCOMPLETE')
    result['source_unchanged']=all(digest(ROOT/path)==value for path,value in before.items())
    result['instrumentation_source_unchanged']=all(digest(ROOT/path)==value for path,value in source_before.items())
    if not result['source_unchanged'] or not result['instrumentation_source_unchanged']:result['status']='FAIL'
    result['script_sha256']=digest(Path(__file__))
    output.mkdir(parents=True,exist_ok=False)
    (output/'result.json').write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({key:result[key] for key in ('status','source_unchanged','HTTP','robot_connections','Isaac_runtime')}))
    return 0 if result['status']=='PASS' else 1


if __name__=='__main__':
    raise SystemExit(main())
