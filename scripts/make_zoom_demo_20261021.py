# SPDX-License-Identifier: Apache-2.0
"""Edit original timestamped renderer samples; never alter product or evidence.

The edit list explicitly maps each 60-second presentation segment back to its
original recording window. Motion is not interpolated. Faster/slower playback
and cuts are labelled; source images, raw recording and failed attempts remain.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import html
import json
from pathlib import Path
import subprocess


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('root', type=Path)
    a = p.parse_args()
    root = a.root.resolve()
    edit = json.loads((root/'edit-list.json').read_text(encoding='utf-8'))
    clock_path = root/edit['recording']/'frame-times.json'
    clock = json.loads(clock_path.read_text(encoding='utf-8'))
    frames = clock['frames']
    source = root/edit['recording']/'app-screen.mp4'
    if len(frames) < 2 or not source.is_file():
        raise ValueError('Finalized original recording required')
    if abs(sum(s['duration_s'] for s in edit['segments'])-60) > .0001:
        raise ValueError('Edit must be exactly 60 seconds')
    work = root/'edited-clips'
    work.mkdir(exist_ok=True)
    receipts = []
    for i, segment in enumerate(edit['segments']):
        start, end, duration = segment['start_at'], segment['end_at'], segment['duration_s']
        if not frames[0]['at'] <= start < end <= clock['end']:
            raise ValueError('Segment outside original clock')
        before = [f for f in frames if f['at'] <= start]
        selected = [before[-1]] if before else []
        selected += [f for f in frames if start < f['at'] < end]
        if not selected:
            raise ValueError('No original samples for segment')
        factor = duration/((end-start)/1000)
        lines = ['ffconcat version 1.0']
        for n, frame in enumerate(selected):
            begin = max(start, frame['at'])
            next_at = min(end, selected[n+1]['at'] if n+1 < len(selected) else end)
            if next_at <= begin:
                continue
            file = (root/edit['recording']/frame['file']).as_posix()
            lines += [f"file '{file}'", f'duration {(next_at-begin)/1000*factor:.6f}']
        last_file = (root/edit['recording']/selected[-1]['file']).as_posix()
        lines.append(f"file '{last_file}'")
        concat = work/f'{i:02}.ffconcat'
        concat.write_text('\n'.join(lines)+'\n', encoding='utf-8')
        speed = 1/factor
        pace = 'real time' if abs(speed-1)<.03 else f'{speed:.1f}x playback'
        label = f"{segment['title']}  |  {pace}"
        title = work/f'{i:02}-title.txt'
        title.write_text(label, encoding='utf-8')
        note = work/f'{i:02}-note.txt'
        note.write_text('SIM DEMO  |  Actual app recording, edited  |  Estimated layout, not physical robot footage', encoding='utf-8')
        def escaped(path):
            return path.as_posix().replace(':', r'\:')
        vf = ('scale=1600:830:force_original_aspect_ratio=decrease,'
              'pad=1600:900:(ow-iw)/2:58+(830-ih)/2:color=0x101b27,'
              f"drawtext=fontfile='C\\:/Windows/Fonts/segoeuib.ttf':textfile='{escaped(title)}':fontsize=26:fontcolor=white:x=28:y=8,"
              f"drawtext=fontfile='C\\:/Windows/Fonts/segoeui.ttf':textfile='{escaped(note)}':fontsize=16:fontcolor=0xb5cbdc:x=28:y=39,"
              'fps=30,setsar=1')
        target = work/f'{i:02}.mp4'
        cmd = ['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(concat),
               '-vf',vf,'-t',str(duration),'-an','-c:v','libx264','-bf','0','-preset','fast','-crf','21',
               '-pix_fmt','yuv420p','-video_track_timescale','30000','-movflags','+faststart',str(target)]
        log = work/f'{i:02}-encode.log'
        with log.open('w',encoding='utf-8') as stream:
            subprocess.run(cmd,stdout=stream,stderr=stream,check=True)
        receipts.append(dict(**segment,source_window_s=(end-start)/1000,playback_speed=speed,
                             samples=len(selected),source_frames=[f['file'] for f in selected],clip_sha256=digest(target)))
        print(json.dumps(dict(segment=i,title=segment['title'],playback_speed=speed)),flush=True)
    join = work/'join.ffconcat'
    join.write_text('ffconcat version 1.0\n'+'\n'.join(f"file '{(work/f'{i:02}.mp4').as_posix()}'" for i in range(len(receipts)))+'\n',encoding='utf-8')
    output = root/'TwinPulse-SIM-Demo-60s-2026-10-21.mp4'
    subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(join),
                    '-c','copy','-an','-movflags','+faststart',str(output)],check=True)
    probe = json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries',
             'format=duration,size:stream=codec_name,width,height,nb_frames,r_frame_rate','-of','json',str(output)],text=True))
    duration = float(probe['format']['duration'])
    if abs(duration-60)>.001:
        raise ValueError(f'Not a 60-second demo: {duration}')
    subprocess.run(['ffmpeg','-nostdin','-v','error','-i',str(output),'-f','null','-'],check=True)
    proof = dict(status='ENCODED_AND_DECODED_VISUAL_REVIEW_PENDING',video=output.name,bytes=output.stat().st_size,
                 sha256=digest(output),duration_s=duration,original_video_sha256=digest(source),
                 original_clock_sha256=digest(clock_path),segments=receipts,probe=probe,
                 real_generation=True,physical_robot=False,product_changed=False,uploaded=False,
                 note='Actual installed Test BrowserWindow. Source timestamped samples only; cuts/playback rates are labelled. No motion interpolation or fake model reply.')
    (root/'media-review.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:proof[k] for k in ('video','duration_s','bytes','sha256')},ensure_ascii=False))


if __name__ == '__main__':
    main()
