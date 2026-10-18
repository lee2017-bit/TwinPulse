# SPDX-License-Identifier: Apache-2.0
"""OFFLINE full original-byte accounting; unknown gaps are NOT whitelisted."""
import collections
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'packages/twinpulse_robot_safety'))
from native_stream import NativeDecoder

def main():
    folder=ROOT/'outputs/robot-retest-20261018/analysis'
    raw=(folder/'native-original.raw').read_bytes()
    chunks=json.loads((folder/'native-chunks.json').read_text())
    decoder=NativeDecoder();packets=[];frame=0;complete_start=False
    total_packets=nodes=packet_bytes=0;gaps=[];bad_rings=[];fallbacks=0
    began=time.perf_counter()
    def inspect():
        nonlocal frame
        if not packets:return
        frame+=1
        gap=[dict(start=a['end'],end=b['offset'],bytes=b['offset']-a['end'],
            hex=raw[a['end']:b['offset']].hex(' ')) for a,b in zip(packets,packets[1:]) if a['end']!=b['offset']]
        gaps.extend(dict(frame=frame,**g) for g in gap)
        if not complete_start or gap or any(not p['checksum_valid'] for p in packets):
            bad_rings.append(dict(frame=frame,complete_start=complete_start,gaps=gap,
                first=packets[0]['offset'],end=packets[-1]['end'],checksum_errors=sum(not p['checksum_valid'] for p in packets)))
    for chunk in chunks:
        data=raw[chunk['offset']:chunk['offset']+chunk['length']]
        if hashlib.sha256(data).hexdigest()!=chunk['sha256']:raise ValueError('ORIGINAL_CHUNK_SHA')
        for p in decoder.feed(data,chunk['receipt_end_s']):
            total_packets+=1;nodes+=len(p['nodes']);packet_bytes+=len(p['raw_bytes']);fallbacks+=int(p['interval_fallback'])
            if p['nodes'][0]['ring_start']:
                inspect();packets=[];complete_start=True
            packets.append(p)
    if packet_bytes+decoder.noise_bytes+len(decoder.buffer)!=len(raw):raise ValueError('BYTE_ACCOUNTING')
    result=dict(method='OFFLINE_FULL_SAVED_BYTE_REPLAY_NOT_HARDWARE_PASS',
        raw_sha256=hashlib.sha256(raw).hexdigest(),raw_bytes=len(raw),chunks=len(chunks),
        packets=total_packets,nodes=nodes,checksum_errors=decoder.errors,interval_fallbacks=fallbacks,
        finalized_frames=frame,incomplete_frames=len(bad_rings),uninterpreted_bytes=decoder.noise_bytes,
        pending_decoder_bytes=len(decoder.buffer),decoded_packet_bytes=packet_bytes,byte_accounting_exact=True,
        gap_histogram=dict(collections.Counter(g['bytes'] for g in gaps)),
        unqualified_gap_examples=gaps[:8],original_failed_frame=next((r for r in bad_rings if r['frame']==393),None),
        gaps=gaps,bad_rings=bad_rings,seconds=time.perf_counter()-began,
        classification='UNKNOWN serial bytes; no checksum-valid scan packet or supported response classification invented',
        native_source_sha256=hashlib.sha256((ROOT/'packages/twinpulse_robot_safety/native_stream.py').read_bytes()).hexdigest())
    (folder/'native-replay.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in {'gaps','bad_rings','unqualified_gap_examples'}},indent=2))

if __name__=='__main__':main()
