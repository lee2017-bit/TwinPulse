# SPDX-License-Identifier: Apache-2.0
"""Derive time-qualified clips without replacing original frames or recordings.

The source is sampled installed-renderer capture, not native video. A held frame
represents a gap with no new observation; it never proves stationary pixels or
continued motion. No test verdicts, product state or original receipts change.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def derive(folder: Path) -> dict:
    clock = folder / 'frame-times.json'
    concat = folder / 'screen.ffconcat'
    original = folder / 'app-screen.mp4'
    output = folder / 'app-screen-clock-linear.mp4'
    times = json.loads(clock.read_text(encoding='utf-8'))
    frames = times['frames']
    if not frames or times['end'] < frames[-1]['at']:
        raise ValueError('Original frame clocks missing or invalid')
    if not output.exists():
        subprocess.run([
            'ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
            '-copyts', '-start_at_zero', '-f', 'concat', '-safe', '0', '-i', str(concat),
            '-vf', 'scale=1600:900:force_original_aspect_ratio=decrease,pad=1600:900:(ow-iw)/2:(oh-ih)/2',
            '-fps_mode', 'passthrough', '-enc_time_base', '1/1000', '-c:v', 'libx264',
            '-bf', '0', '-preset', 'fast', '-crf', '24', '-pix_fmt', 'yuv420p',
            '-video_track_timescale', '1000', '-movflags', '+faststart', str(output),
        ], check=True)
    probe = json.loads(subprocess.check_output([
        'ffprobe', '-v', 'error', '-select_streams', 'v', '-show_packets',
        '-show_entries', 'packet=pts_time:format=duration', '-of', 'json', str(output),
    ], text=True))
    pts = [float(packet['pts_time']) for packet in probe['packets']]
    expected = [(frame['at']-frames[0]['at'])/1000 for frame in frames]
    expected.append((times['end']-frames[0]['at'])/1000)
    if len(pts) != len(expected):
        raise ValueError(f'Frame count changed: {folder} {len(pts)} != {len(expected)}')
    errors = [abs(actual-wanted) for actual, wanted in zip(pts, expected)]
    duration = float(probe['format']['duration'])
    if max(errors) > .05 or abs(duration-expected[-1]) > .1:
        raise ValueError(f'Derived timing failed: {folder}: PTS {max(errors)}, duration {duration-expected[-1]}')
    gaps = [b-a for a, b in zip(expected, expected[1:])]
    return {
        'status': 'ORIGINAL_FRAME_PTS_AND_END_HOLD_QUALIFIED_NOT_PRODUCT_PASS',
        'path': folder.name+'/'+output.name,
        'sha256': digest(output), 'bytes': output.stat().st_size,
        'original_video_sha256': digest(original),
        'original_frame_times_sha256': digest(clock), 'original_concat_sha256': digest(concat),
        'original_frame_count': len(frames), 'encoded_frame_count': len(pts),
        'first_frame_to_recording_end_s': expected[-1], 'duration_s': duration,
        'maximum_pts_error_s': max(errors), 'maximum_no_new_observation_s': max(gaps, default=0),
        'scope': 'Same original sampled renderer images with recorded inter-frame and final holds; no interpolated motion, no unseen frames, no native/physical video. Original MP4 and failed journeys remain unchanged.',
        'encoding': 'Original concat PTS, H264 B-frames disabled, 1/1000 time base, no frame interpolation',
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    parser.add_argument('folders', nargs='+')
    args = parser.parse_args()
    records = []
    for name in args.folders:
        folder = (args.root/name).resolve()
        if folder.parent != args.root.resolve():
            raise ValueError('Recording must be an immediate child of the evidence root')
        record = derive(folder)
        records.append(record)
        print(json.dumps({key: record[key] for key in ('path', 'duration_s', 'maximum_pts_error_s')}, ensure_ascii=False), flush=True)
    receipt = args.root/'derived-video-receipts.json'
    payload = json.dumps(records, ensure_ascii=False, indent=2)+'\n'
    if receipt.exists() and receipt.read_text(encoding='utf-8') != payload:
        raise ValueError('Refusing to replace a different derivative receipt')
    receipt.write_text(payload, encoding='utf-8')


if __name__ == '__main__':
    main()
