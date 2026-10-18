# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Analyze saved trial text without connecting to a robot or changing criteria."""
import argparse
import json
import math
from pathlib import Path
import re


def analyze(text):
    samples = [(int(t), int(left), int(right)) for t, left, right in
               re.findall(r'SENSOR t=(\d+) left=(-?\d+) right=(-?\d+)', text)]
    silence = re.findall(r'INPUT_SILENT t=(\d+)', text)
    delays = re.findall(r'TIMEOUT_OBSERVED after_last_send_ms=(\d+)', text)
    if len(samples) < 2 or len(silence) != 1 or len(delays) != 1:
        raise ValueError('Require one trial with sensor rows, input silence and timeout receipt')
    if any(a[0] >= b[0] for a, b in zip(samples, samples[1:])):
        raise ValueError('Samples must have strictly increasing elapsed timestamps')
    seen = int(silence[0]) + int(delays[0])
    # Reconstruct the previously fixed anchor-band criterion, never relax it.
    anchor = samples[0][1:]
    last_change = samples[0][0]
    for t, left, right in samples:
        if t > seen + 500:
            break
        if abs(left - anchor[0]) > 2 or abs(right - anchor[1]) > 2:
            anchor, last_change = (left, right), t
    before = [row for row in samples if row[0] <= seen]
    after = [row for row in samples if seen < row[0] <= seen + 500]
    relevant = before[-1:] + after
    # Missing telemetry must not turn silence into apparent physical stability.
    coverage = bool(before and after and seen - before[-1][0] < 200
                    and seen + 500 - after[-1][0] < 200
                    and all(b[0] - a[0] < 200 for a, b in zip(relevant, relevant[1:])))
    mm_tick = 2 * math.pi * 33 / 4096
    # Last pre-timeout sample to last observation is an upper sampled interval,
    # NOT an exact stop distance; wheel slip and timestamp latency are unmeasured.
    travel = [round(abs(after[-1][i] - before[-1][i]) * mm_tick, 3) for i in (1, 2)] if before and after else None
    return {'source': 'saved_text_samples_may_be_excerpted', 'sample_count': len(samples),
            'timeout_receipt_after_last_send_ms': int(delays[0]),
            'reconstructed_timeout_receipt_t_ms': seen,
            'nominal_mm_per_encoder_tick': round(mm_tick, 6),
            'stationary_band_ticks': 2, 'stationary_required_ms': 200,
            'post_timeout_observation_ms': 500,
            'last_anchor_reset_t_ms': last_change,
            'reconstructed_stable_age_at_window_end_ms': seen + 500 - last_change,
            'sample_coverage_sufficient': coverage,
            'reconstructed_settling_pass': (seen + 500 - last_change >= 200) if coverage else None,
            'nominal_wheel_interval_travel_mm': travel,
            'limits': 'Timing reconstruction from logged samples, not independent floor motion or a cause diagnosis.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('record', type=Path)
    args = parser.parse_args()
    print(json.dumps(analyze(args.record.read_text(encoding='utf-8')), indent=2))
