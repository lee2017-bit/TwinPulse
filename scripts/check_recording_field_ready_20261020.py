# SPDX-License-Identifier: Apache-2.0
"""Audit recorded packet clocks; no App, model or robot control."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/robot-field-ready-20261020'
folder=OUT/'ui-08/recording'
clock=json.loads((folder/'frame-times.json').read_bytes())
source=clock['frames'];first=source[0]['at'];end=clock['end']
video=folder/'app-screen.mp4'
run=subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-show_entries',
    'packet=pts_time','-show_entries','format=duration','-of','json',str(video)],capture_output=True,check=True)
probe=json.loads(run.stdout)
pts=[float(row['pts_time']) for row in probe['packets']]
expected=[(row['at']-first)/1000 for row in source]+[(end-first)/1000]
error=max(abs(a-b) for a,b in zip(pts,expected))
duration=float(probe['format']['duration'])
passed=len(pts)==len(expected) and error<=.041 and abs(duration-(end-first)/1000)<=.1
value=dict(status='PASS_PACKET_CLOCK' if passed else 'FAIL',classification='RECORDED_RENDERER_TIMING_NOT_NATIVE_OR_PHYSICAL',
    video=str(video.relative_to(OUT)),bytes=video.stat().st_size,sha256=sha256(video.read_bytes()).hexdigest(),
    recorded_frames=len(source),encoded_packets=len(pts),max_packet_error_s=error,
    original_wall_ms=end-clock['began'],first_frame_delay_ms=first-clock['began'],duration_s=duration,
    first_frame=source[0]['file'],last_frame=source[-1]['file'],source_clock_sha256=sha256((folder/'frame-times.json').read_bytes()).hexdigest(),
    observation='Original frame intervals preserved with last-frame hold; no trim/speedup/interpolation. Gaps are unobserved, not proof of robot standstill.',
    public_demo=False,reason='Full local regression includes explicit fault windows and local setup; not published as an ordinary demo.')
with (OUT/'recording-final-qa.json').open('x',encoding='utf-8') as stream:json.dump(value,stream,indent=2)
print(json.dumps(value))
raise SystemExit(0 if passed else 1)
