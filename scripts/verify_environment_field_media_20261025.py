# SPDX-License-Identifier: Apache-2.0
"""Actual field renderer video, full decode and original packet time checks."""
import json,hashlib,subprocess
from pathlib import Path
from recording_timestamp_contract import strictly_increasing_packet_times
out=Path(__file__).resolve().parents[1]/'outputs/robot-environment-field-20261025-01'
folder=out/'session03';video=folder/'app-screen.mp4';session=json.loads((folder/'session.json').read_bytes())
record=next(e['evidence'] for e in reversed(session['events']) if e['name']=='VIDEO_ENCODE')
info=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-count_frames','-show_packets','-show_entries','stream=nb_read_frames,time_base:format=duration:packet=pts,dts','-of','json',str(video)],text=True))
decoded=subprocess.run(['ffmpeg','-nostdin','-hide_banner','-v','error','-i',str(video),'-fps_mode','passthrough','-enc_time_base','demux','-f','null','-'],capture_output=True,text=True)
frames=int(info['streams'][0]['nb_read_frames']);duration=float(info['format']['duration'])
contact=folder/'encoded-contact01.png'
if contact.exists():raise ValueError('NEW_CONTACT_REQUIRED')
render=subprocess.run(['ffmpeg','-nostdin','-hide_banner','-v','error','-i',str(video),'-vf',f'select=eq(n\\,0)+eq(n\\,{frames//2})+eq(n\\,{frames-1}),scale=533:-1,tile=3x1','-frames:v','1',str(contact)],capture_output=True,text=True)
checks=dict(decode=decoded.returncode==0 and not decoded.stderr,contact=render.returncode==0,
    original_pts=strictly_increasing_packet_times(info.get('packets')),wall_duration=abs(duration-record['wall_ms']/1000)<2,not_empty=frames>1)
value=dict(status='PASS' if all(checks.values()) else 'FAIL',scope='POST_RECORDER_RECOVERY_RENDERER_VIDEO_NOT_FULL_STARTUP_OR_PHYSICAL_CAMERA',checks=checks,
    path='session03/app-screen.mp4',bytes=video.stat().st_size,sha256=hashlib.sha256(video.read_bytes()).hexdigest(),duration_s=duration,recorded_wall_s=record['wall_ms']/1000,frames=frames,
    time_base=info['streams'][0]['time_base'],decode_stderr=decoded.stderr,contact_stderr=render.stderr,contact='session03/encoded-contact01.png')
with (out/'media01.json').open('x',encoding='utf-8') as f:json.dump(value,f,indent=2)
print(json.dumps(value));raise SystemExit(0 if all(checks.values()) else 1)
