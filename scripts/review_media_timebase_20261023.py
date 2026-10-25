# SPDX-License-Identifier: Apache-2.0
"""Inspect original VFR timestamps and decode outputs; never modifies a video."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/robot-roomplan-ready-20261023'
video = OUT / 'roomplan-sim-12/recording/app-screen.mp4'
original = video.read_bytes()
probe_command = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_packets',
                 '-show_entries', 'stream=time_base,r_frame_rate:packet=pts,dts,duration', '-of', 'json', str(video)]
probe = subprocess.run(probe_command, capture_output=True, text=True, check=True)
packets = json.loads(probe.stdout)
strict_pts = all(b['pts'] > a['pts'] for a,b in zip(packets['packets'], packets['packets'][1:]))
strict_dts = all(b['dts'] > a['dts'] for a,b in zip(packets['packets'], packets['packets'][1:]))
rounded = [int(p['dts'] / 40 + .5) for p in packets['packets']]
rounding_collisions = [dict(index=i, previous=packets['packets'][i-1], current=packets['packets'][i],
                            output_dts_at_25hz=rounded[i]) for i in range(1,len(rounded)) if rounded[i]<=rounded[i-1]]
runs = []
for label, options in (('default-null-control', []), ('original-timebase-null', ['-fps_mode','passthrough','-enc_time_base','demux'])):
    command = ['ffmpeg','-nostdin','-hide_banner','-v','error','-i',str(video),*options,'-f','null','-']
    run = subprocess.run(command, capture_output=True, text=True)
    runs.append(dict(label=label, command=command, return_code=run.returncode, stderr=run.stderr))
hash_command = ['ffmpeg','-nostdin','-hide_banner','-v','error','-i',str(video),'-map','0:v:0',
                '-fps_mode','passthrough','-enc_time_base','demux','-f','framemd5','-']
decoded = subprocess.run(hash_command, capture_output=True, text=True)
rows = [line for line in decoded.stdout.splitlines() if line and not line.startswith('#')]
passed = (strict_pts and strict_dts and bool(rounding_collisions) and runs[0]['return_code']==0
          and '3167 >= 3167' in runs[0]['stderr'] and runs[1]['return_code']==0 and not runs[1]['stderr']
          and decoded.returncode==0 and not decoded.stderr and len(rows)==len(packets['packets'])
          and video.read_bytes()==original)
value = dict(status='PASS_DIAGNOSED_VALIDATOR_TIMEBASE_ROUNDING_NOT_VIDEO_REWRITE' if passed else 'FAIL',
             original_video_sha256=sha256(original).hexdigest(), original_media_failure_sha256=sha256((OUT/'media-checks12.json').read_bytes()).hexdigest(),
             video_unchanged=True, probe=packets, input_pts_strictly_increasing=strict_pts,
             input_dts_strictly_increasing=strict_dts, default_null_25hz_rounding_collisions=rounding_collisions,
             decode_runs=runs, decoded_frame_hash_count=len(rows), decoded_frame_hashes=decoded.stdout,
             decoded_hash_return_code=decoded.returncode, decoded_hash_stderr=decoded.stderr,
             limitation='Original media12 FAIL preserved; no current App result, recording image, input timestamp or policy changed.')
with (OUT/'media-timebase-diagnosis12.json').open('x',encoding='utf-8') as stream:
    json.dump(value,stream,indent=2)
print(json.dumps({k:v for k,v in value.items() if k not in ('probe','decoded_frame_hashes','decode_runs')},indent=2))
raise SystemExit(0 if passed else 1)
