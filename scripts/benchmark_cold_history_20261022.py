# SPDX-License-Identifier: Apache-2.0
"""Read-only original-history cost probe, not installed UI or motion evidence."""
import argparse
import cProfile
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import pstats
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
for name in ('twinpulse_app', 'twinpulse_core', 'twinpulse_provider'):
    sys.path.insert(0, str(ROOT / 'packages' / name / 'src'))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--module', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--profile', action='store_true')
    args = parser.parse_args()
    directory = Path(os.environ['LOCALAPPDATA']) / 'TwinPulse/runtime/devices/local/physical-live/65fe078b1975404886704c2df728a33f'
    raw = (directory / 'receipt.json').read_bytes()
    receipt = json.loads(raw)
    with (directory / 'events-00000.jsonl').open('rb') as stream:
        first = json.loads(stream.readline(256 * 1024 + 1))
    identity = {key: first[key] for key in ('operation_id', 'project_id', 'robot_id', 'connection_epoch', 'binding_sha256', 'source_twin_context')}
    spec = importlib.util.spec_from_file_location('cold_history_probe', args.module)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = []
    for index in range(3):
        began = time.perf_counter()
        cpu = time.process_time()
        # Existing adapter performs this independent first pass. Preserve it
        # in both probes; the delta under review is only tail copying.
        for segment in receipt['segments']:
            member = directory / segment['path']
            assert member.stat().st_size == segment['bytes']
            assert hashlib.sha256(member.read_bytes()).hexdigest() == segment['sha256']
        verified = time.perf_counter()
        profile = cProfile.Profile() if args.profile and index == 0 else None
        if profile: profile.enable()
        value = module.recover_live_history(directory, receipt, **identity)
        if profile: profile.disable()
        finished = time.perf_counter()
        canonical = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()
        row = dict(index=index, first_pass_ms=(verified-began)*1000,
                   recover_ms=(finished-verified)*1000, total_ms=(finished-began)*1000,
                   process_cpu_s=time.process_time()-cpu, output_bytes=len(canonical),
                   output_sha256=hashlib.sha256(canonical).hexdigest(),
                   runtime_event_count=value['runtime_event_count'], returned_events=len(value['events']))
        if profile:
            target = io.StringIO()
            pstats.Stats(profile, stream=target).strip_dirs().sort_stats('cumulative').print_stats(20)
            row['profile'] = target.getvalue()
        rows.append(row)
    result = dict(classification='ORIGINAL_READ_ONLY_CPU_PROBE_NOT_UI_OR_SOLE_ROOT_CAUSE',
                  receipt_sha256=hashlib.sha256(raw).hexdigest(),
                  module_sha256=hashlib.sha256(args.module.read_bytes()).hexdigest(),
                  segments=len(receipt['segments']), bytes=receipt['bytes'], rows=rows)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps(result))

if __name__ == '__main__':
    main()
