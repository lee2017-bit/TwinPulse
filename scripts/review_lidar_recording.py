# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Offline COIN-D4 recording integrity/preview; no robot or ROS imports.

Does not invent TF, uniform angular spacing, free space or calibrated range.
Sensor-native angle zero/direction are not yet qualified against the robot.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import struct


def packets(data, *, max_bytes=512*1024):
    if type(max_bytes) is not int or not 1 <= max_bytes <= 1024*1024:
        raise ValueError('Invalid recording audit bound')
    if len(data) > max_bytes:
        raise ValueError('Raw recording exceeds capture budget')
    offset = 0
    result = {'good_packets': 0, 'bad_checksum': 0, 'invalid_header': 0,
              'skipped_bytes': 0, 'trailing_bytes': 0, 'samples': 0, 'ring_packets': 0}
    while offset < len(data):
        start = data.find(b'\xaa\x55', offset)
        if start < 0:
            result['trailing_bytes'] += len(data) - offset
            break
        result['skipped_bytes'] += start - offset
        if len(data) - start < 10:
            result['trailing_bytes'] += len(data) - start
            break
        ct, count, first, last, checksum = struct.unpack_from('<BBHHH', data, start + 2)
        if not 1 <= count <= 85 or not first & 1 or not last & 1:
            result['invalid_header'] += 1
            offset = start + 2
            continue
        end = start + 10 + count * 3
        if end > len(data):
            result['trailing_bytes'] += len(data) - start
            break
        actual = 0x55AA ^ (count << 8 | ct) ^ first ^ last
        for p in range(start + 10, end, 3):
            actual ^= data[p] ^ (data[p+1] | data[p+2] << 8)
        if actual == checksum:
            result['good_packets'] += 1
            result['samples'] += count
            result['ring_packets'] += ct & 1
        else:
            result['bad_checksum'] += 1
        offset = end
    return result


def summarize(raw, nodes, report):
    if hashlib.sha256(raw).hexdigest() != report['raw_sha256']:
        raise ValueError('Raw file differs from robot receipt')
    parsed = packets(raw)
    if parsed['bad_checksum'] or parsed['invalid_header'] or parsed['samples'] != len(nodes):
        raise ValueError('Packet integrity/vendor decoder count disagreement: ' + str(parsed))
    if not nodes or len(nodes) > 200000:
        raise ValueError('Decoded sample budget')
    for node in nodes:
        if not (0 <= node['angle_deg'] <= 360 and 0 <= node['distance_m'] <= 65.535
                and 0 <= node['quality'] <= 255):
            raise ValueError('Decoded sample outside representation bounds')
    starts = [i for i, n in enumerate(nodes) if n['ring_start']]
    frames = [nodes[a:b] for a, b in zip(starts, starts[1:]) if b-a > 1]
    if not frames:
        raise ValueError('No complete ring-to-ring scan')
    frame = frames[-1]
    def usable(n):
        return n['distance_m'] > 0 and not (n['distance_m'] <= .15 and n['quality'] <= 65)
    points = [dict(n, x_m=n['distance_m'] * math.cos(math.radians(n['angle_deg'])),
                   y_m=n['distance_m'] * math.sin(math.radians(n['angle_deg'])))
              for n in frame if usable(n)]
    increments = [(b['angle_deg'] - a['angle_deg']) % 360 for a, b in zip(frame, frame[1:])]
    angles = sorted(p['angle_deg'] for p in points)
    gaps = [b-a for a, b in zip(angles, angles[1:])] + ([angles[0]+360-angles[-1]] if angles else [])
    result = {'status': 'SAVED_SENSOR_NATIVE_SCAN_DECODED', 'raw_sha256': report['raw_sha256'],
              'provenance': 'real robot serial recording; offline pinned vendor parser',
              'packets': parsed, 'decoded_samples': len(nodes), 'complete_scans': len(frames),
              'scan_size_min': min(map(len, frames)), 'scan_size_max': max(map(len, frames)),
              'selected_complete_scan': len(frames)-1, 'selected_samples': len(frame),
              'selected_usable_returns': len(points), 'selected_invalid_returns': len(frame)-len(points),
              'positive_return_min_m': min((p['distance_m'] for p in points), default=None),
              'positive_return_max_m': max((p['distance_m'] for p in points), default=None),
              'max_no_return_angular_gap_deg': max(gaps, default=None),
              'angle_increment_deg': {'min': min(increments), 'max': max(increments),
                                      'median': statistics.median(increments)},
              'physical_rotor_stopped': report['physical_rotor_stopped'],
              'world_tf': 'UNVERIFIED', 'robot_axis_alignment': 'UNVERIFIED',
              'obstacle_clearance': 'UNKNOWN', 'navigation_authorized': False,
              'limits': ['No ROS LaserScan runtime', 'No world/base transform or range calibration',
                         'Invalid returns are not free space', 'Host receipt times are not beam times',
                         'No physical rotor-stop claim from serial silence']}
    return result, points


def preview(summary, points):
    # Static scientific scatter plot. Retain raw/native orientation, no room labels.
    extent, centre, scale = 5, 350, 60
    elements = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 700 790" role="img">',
                '<rect width="700" height="790" fill="#101b2d"/>',
                '<g stroke="#334155" fill="none">']
    for radius in range(1, extent+1):
        elements.append(f'<circle cx="350" cy="350" r="{radius*scale}"/>')
    elements.extend(['<path d="M50 350H650 M350 50V650"/></g>', '<g fill="#5eead4">'])
    for p in points:
        if abs(p['x_m']) <= extent and abs(p['y_m']) <= extent:
            elements.append(f'<circle cx="{centre+p["x_m"]*scale:.2f}" cy="{centre-p["y_m"]*scale:.2f}" r="2"/>')
    elements.extend(['</g><circle cx="350" cy="350" r="6" fill="#fb923c"/>',
        '<g fill="#e2e8f0" font-family="sans-serif" font-size="15">',
        '<text x="30" y="30">Actual saved LiDAR returns / sensor-native polar frame</text>',
        '<text x="515" y="340">0 deg (not robot front)</text>',
        '<text x="360" y="64">90 deg</text>',
        f'<text x="30" y="690">{summary["selected_usable_returns"]} returns / {summary["selected_samples"]} samples. Rings: 1 metre.</text>',
        '<text x="30" y="720">TF, orientation and range calibration UNVERIFIED.</text>',
        '<text x="30" y="750">Missing points are UNKNOWN, not clear floor. No drive approval.</text>',
        '</g></svg>'])
    return '\n'.join(elements)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('capture', type=Path)
    ap.add_argument('nodes', type=Path)
    ap.add_argument('output', type=Path)
    args = ap.parse_args()
    if args.nodes.stat().st_size > 40 * 1024 * 1024:
        raise ValueError('Decoder output exceeds budget')
    lines = args.nodes.read_text().splitlines()
    if any(not line.startswith('{') for line in lines):
        raise ValueError('Vendor decoder printed a diagnostic; review before preview')
    nodes = [json.loads(line) for line in lines]
    summary, points = summarize((args.capture / 'raw.bin').read_bytes(), nodes,
                               json.loads((args.capture / 'report.json').read_text()))
    args.output.mkdir(parents=True, exist_ok=True)
    for name, value in [('summary.json', summary), ('native-points.json', points)]:
        (args.output / name).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    (args.output / 'preview.svg').write_text(preview(summary, points))
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
