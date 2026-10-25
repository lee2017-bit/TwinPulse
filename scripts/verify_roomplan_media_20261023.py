# SPDX-License-Identifier: Apache-2.0
"""Decode local actual-renderer recordings; no product or user-source writes."""
import hashlib
import argparse
import json
import subprocess
from pathlib import Path
from recording_timestamp_contract import strictly_increasing_packet_times

parser = argparse.ArgumentParser()
parser.add_argument('--output-root', type=Path, default=Path('outputs/roomplan-import-20261023'))
parser.add_argument('--runs', nargs='+', default=['ui-import17', 'ui-edit16', 'ui-sim17', 'ui-cold14'])
parser.add_argument('--result-name', default='media-checks.json')
args = parser.parse_args()
root = args.output_root.resolve()
selected = args.runs
if any(Path(name).name != name or name in ('.', '..') for name in [*selected, args.result_name]):
    raise ValueError('Single relative evidence names required')
target = root / args.result_name
if target.exists():
    raise ValueError('New evidence result required')
videos = []
for name in selected:
    folder = root / name / 'recording'
    video = folder / 'app-screen.mp4'
    result = json.loads((root / name / 'result.json').read_text(encoding='utf-8'))
    probe = subprocess.run([
        'ffprobe', '-v', 'error', '-select_streams', 'v:0', '-count_frames',
        '-show_packets', '-show_entries', 'stream=width,height,nb_read_frames,time_base:format=duration:packet=pts,dts',
        '-of', 'json', str(video),
    ], capture_output=True, text=True, check=True)
    info = json.loads(probe.stdout)
    frames = int(info['streams'][0]['nb_read_frames'])
    duration = float(info['format']['duration'])
    decoded = subprocess.run([
        'ffmpeg', '-nostdin', '-hide_banner', '-v', 'error', '-i', str(video),
        '-fps_mode', 'passthrough', '-enc_time_base', 'demux',
        '-f', 'null', '-',
    ], capture_output=True, text=True)
    # The first, actual middle and actual last decoded frame, not an invented
    # intermediate image or an old screenshot outside this recording.
    contact_path = folder / ('encoded-contact-' + Path(args.result_name).stem + '.png')
    contact = subprocess.run([
        'ffmpeg', '-nostdin', '-hide_banner', '-v', 'error', '-y', '-i', str(video),
        '-vf', f'select=eq(n\\,0)+eq(n\\,{frames//2})+eq(n\\,{frames-1}),scale=533:-1,tile=3x1',
        '-frames:v', '1', str(contact_path),
    ], capture_output=True, text=True)
    videos.append(dict(
        name=name, path=str(video.relative_to(root)), bytes=video.stat().st_size,
        sha256=hashlib.sha256(video.read_bytes()).hexdigest(), frames=frames,
        duration_s=duration, recorded_wall_s=(result.get('video') or result['recording'])['wall_ms']/1000,
        decode_return_code=decoded.returncode, decode_stderr=decoded.stderr,
        original_packet_timestamps_strict=strictly_increasing_packet_times(info.get('packets')),
        original_time_base=info['streams'][0]['time_base'],
        decode_time_policy='Original demux timebase/passthrough; never round VFR timestamps to default25Hz null output',
        contact_return_code=contact.returncode, contact_stderr=contact.stderr,
        contact=str(contact_path.relative_to(root)),
    ))
passed = all(v['decode_return_code'] == v['contact_return_code'] == 0
             and not v['decode_stderr'] and v['frames'] > 1
             and v['original_packet_timestamps_strict']
             and abs(v['duration_s'] - v['recorded_wall_s']) < 2
             for v in videos)
value = dict(status='PASS' if passed else 'FAIL',
             basis='Full encoded decode and actual first/middle/last extraction; visual review separate',
             videos=videos)
target.write_text(json.dumps(value, indent=2), encoding='utf-8')
print(json.dumps(value, indent=2))
if not passed:
    raise SystemExit(1)
