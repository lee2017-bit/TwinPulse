# SPDX-License-Identifier: Apache-2.0
"""Decode actual renderer recordings and extract encoded representative frames."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/robot-continuous-repair-20261021'
target=OUT/'recording-review57';target.mkdir(exist_ok=False);rows=[]
for name in ('ui-57','ui-reproduction-58'):
    video=OUT/name/'recording/app-screen.mp4'
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(video)],text=True))
    with (target/(name+'-full-decode.log')).open('xb') as stream:
        decoded=subprocess.run(['ffmpeg','-nostdin','-v','error','-xerror','-i',str(video),'-f','null','-'],stdout=stream,stderr=subprocess.STDOUT,timeout=120)
    if decoded.returncode:raise ValueError('ENCODED_FULL_DECODE_FAILED:'+name)
    duration=float(probe['format']['duration']);step=duration/8
    contact=target/(name+'-contact.jpg')
    subprocess.run(['ffmpeg','-nostdin','-v','error','-i',str(video),'-vf',f'fps=1/{step},scale=600:-2,tile=2x4','-frames:v','1',str(contact)],check=True,timeout=120)
    last=target/(name+'-last.jpg')
    subprocess.run(['ffmpeg','-nostdin','-v','error','-sseof','-1','-i',str(video),'-frames:v','1',str(last)],check=True,timeout=60)
    times=json.loads((video.parent/'frame-times.json').read_text(encoding='utf-8'))
    rows.append(dict(journey=name,video=video.relative_to(OUT).as_posix(),video_sha256=sha256(video.read_bytes()).hexdigest(),
        bytes=video.stat().st_size,duration_s=duration,encoded_frames=probe['streams'][0].get('nb_frames'),
        original_renderer_frames=len(times['frames']),renderer_source=times['source'],pointer=times.get('pointer'),
        full_decode_exit=decoded.returncode,contact=contact.relative_to(OUT).as_posix(),last=last.relative_to(OUT).as_posix()))
value=dict(classification='ENCODED_ACTUAL_RENDERER_MEDIA_QA_NOT_NATIVE_OS_OR_ROBOT_FOOTAGE',
           status='PASS_FULL_DECODE_VISUAL_INSPECTION_PENDING',recordings=rows)
with (target/'result.json').open('x',encoding='utf-8') as stream:json.dump(value,stream,indent=2)
print(json.dumps(dict(status=value['status'],durations=[r['duration_s'] for r in rows])))
