# SPDX-License-Identifier: Apache-2.0
"""Original archived line stream, lossless zlib sync-flush byte/CPU probe.

This approximates SSH compression, not an SSH benchmark or hardware success.
It never opens a connection, sends a command, or changes original evidence.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
import zlib


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('archive',type=Path)
    parser.add_argument('result',type=Path)
    args=parser.parse_args()
    receipt=json.loads((args.archive/'receipt.json').read_text(encoding='utf-8-sig'))
    compressor=zlib.compressobj(6);decompressor=zlib.decompressobj()
    original_hash=hashlib.sha256();decoded_hash=hashlib.sha256()
    original_bytes=compressed_bytes=decoded_bytes=lines=0
    start=time.perf_counter();cpu=time.process_time()
    for entry in receipt['segments']:
        raw=(args.archive/entry['path']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=entry['sha256']:raise ValueError('ORIGINAL_SHA_MISMATCH')
        for line in raw.splitlines(keepends=True):
            original_hash.update(line);original_bytes+=len(line);lines+=1
            encoded=compressor.compress(line)+compressor.flush(zlib.Z_SYNC_FLUSH)
            compressed_bytes+=len(encoded)
            decoded=decompressor.decompress(encoded)
            decoded_bytes+=len(decoded);decoded_hash.update(decoded)
    tail=compressor.flush();compressed_bytes+=len(tail)
    decoded=decompressor.decompress(tail)+decompressor.flush()
    decoded_bytes+=len(decoded);decoded_hash.update(decoded)
    if original_bytes!=decoded_bytes or original_hash.hexdigest()!=decoded_hash.hexdigest():
        raise ValueError('ROUNDTRIP_MISMATCH')
    result=dict(status='PASS_LOSSLESS_ORIGINAL_STREAM_ONLY',segments=len(receipt['segments']),lines=lines,
        original_bytes=original_bytes,compressed_bytes=compressed_bytes,decoded_bytes=decoded_bytes,
        reduction_percent=100*(1-compressed_bytes/original_bytes),
        source_sha256=original_hash.hexdigest(),decoded_sha256=decoded_hash.hexdigest(),
        wall_s=time.perf_counter()-start,cpu_s=time.process_time()-cpu,
        mode='zlib level6 per-original-line Z_SYNC_FLUSH; approximate SSH compression, not live SSH measurement',
        limits='No hardware, Pi CPU, negotiated compression or control latency measured; no driving success claimed.')
    with args.result.open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
    print(json.dumps(result))


if __name__=='__main__':main()
