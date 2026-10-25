# SPDX-License-Identifier: Apache-2.0
"""Decode actual recordings and preserve original packet times; visual review separate."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from recording_timestamp_contract import strictly_increasing_packet_times


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--manifest',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();root=a.root.resolve();manifest=json.loads(a.manifest.read_text(encoding='utf-8-sig'))
    clips=[]
    def ref(path):return {'path':path.relative_to(root).as_posix(),'sha256':sha256(path.read_bytes()).hexdigest()}
    for role in ('import','edit','sim','cold','marker','extra','restore'):
        session=root/manifest['refs'][role]['path'];row=json.loads(session.read_text(encoding='utf-8-sig'))
        folder=session.parent/('recording' if role in ('import','edit','sim','cold') else '.')
        video=folder/'app-screen.mp4'
        probe=subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-count_frames','-show_packets','-show_entries','stream=width,height,nb_read_frames,time_base:format=duration:packet=pts,dts','-of','json',str(video)],capture_output=True,text=True,check=True)
        info=json.loads(probe.stdout);frames=int(info['streams'][0]['nb_read_frames'])
        decode=subprocess.run(['ffmpeg','-nostdin','-hide_banner','-v','error','-i',str(video),'-fps_mode','passthrough','-enc_time_base','demux','-f','null','-'],capture_output=True,text=True)
        contact=folder/'encoded-contact04.png';last=folder/'encoded-last04.png'
        for target,filter_value in ((contact,f'select=eq(n\\,0)+eq(n\\,{frames//2})+eq(n\\,{frames-1}),scale=533:-1,tile=3x1'),(last,f'select=eq(n\\,{frames-1})')):
            subprocess.run(['ffmpeg','-nostdin','-hide_banner','-v','error','-i',str(video),'-vf',filter_value,'-frames:v','1',str(target)],capture_output=True,text=True,check=True)
        wall=(row.get('video') or row.get('recording') or {}).get('wall_ms',row.get('elapsed_ms',0))/1000
        if role in ('marker','extra','restore'):
            times=json.loads((folder/'frame-times.json').read_text(encoding='utf-8'))
            wall=(times['end']-times['began'])/1000
        duration=float(info['format']['duration']);identity=row.get('versions',row.get('identity',{}))['engine']
        clips.append(dict(role=role,launch_id=identity['launch_id'],session_sha256=sha256(session.read_bytes()).hexdigest(),video=ref(video),frames=[ref(contact),ref(last)],decode_return_code=decode.returncode,decode_stderr=decode.stderr,encoded_frame_count=frames,duration_s=duration,recorded_wall_s=wall,original_packet_timestamps_strict=strictly_increasing_packet_times(info.get('packets')),reviewed=False))
    value=dict(status='PASS_DECODE_ONLY' if all(c['decode_return_code']==0 and not c['decode_stderr'] and c['original_packet_timestamps_strict'] and c['encoded_frame_count']>1 and abs(c['duration_s']-c['recorded_wall_s'])<2 for c in clips) else 'FAIL',release_id=manifest['release_id'],source_sha256=manifest['source_sha256'],encoded_frames_visually_reviewed=False,clips=clips)
    with a.output.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2)
    print(json.dumps({k:v for k,v in value.items() if k!='clips'}));return value['status']!='PASS_DECODE_ONLY'


if __name__=='__main__':raise SystemExit(main())
