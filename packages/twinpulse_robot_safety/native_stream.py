# Copyright 2025 ROBOTIS CO., LTD.
# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
"""Streaming COIN-D4 decoder and independently owned native capture.

Decoder arithmetic is ported from ROBOTIS lidar_data_processor.cpp (8277b288),
including its prior-interval fallback and float32 quantization. TwinPulse changes:
overlapping AA header recovery, explicit byte provenance, invalid coverage and
bounded asynchronous capture. No uniform rays or acquisition times are invented.
"""
from copy import deepcopy
import base64
import hashlib
import json
import math
from pathlib import Path
import struct
import threading
import time
from uuid import uuid4


def _f32(x):
    return struct.unpack('<f', struct.pack('<f', x))[0]


class NativeDecoder:
    def __init__(self, *, intensity=True):
        self.intensity = intensity
        self.buffer = bytearray()
        self.offset = self.node_index = self.errors = self.noise_bytes = 0
        self.previous_interval = 0.
        self.receipts = []

    def feed(self, data, received_s):
        if not isinstance(data, bytes) or len(data) > 65536 or not math.isfinite(received_s):
            raise ValueError('NATIVE_CHUNK_INVALID')
        end = self.offset + len(self.buffer) + len(data)
        self.receipts.append((end, received_s))
        self.buffer.extend(data)
        packets = []
        width, capacity = (3, 85) if self.intensity else (2, 255)
        while len(self.buffer) >= 2:
            if self.buffer[:2] != b'\xaa\x55':
                del self.buffer[0]; self.offset += 1; self.noise_bytes += 1
                continue
            if len(self.buffer) < 10:
                break
            ct, count = self.buffer[2:4]
            first_raw, last_raw, expected = struct.unpack_from('<HHH', self.buffer, 4)
            if not 0 < count <= capacity or not first_raw & 1 or not last_raw & 1:
                self.errors += 1; del self.buffer[0]; self.offset += 1
                continue
            size = 10 + count * width
            if len(self.buffer) < size:
                break
            raw = bytes(self.buffer[:size])
            checksum = 0x55aa ^ (ct | count << 8) ^ first_raw ^ last_raw
            for i in range(count):
                at = 10 + i * width
                checksum ^= (raw[at] ^ int.from_bytes(raw[at+1:at+3], 'little')) if self.intensity else int.from_bytes(raw[at:at+2], 'little')
            first, last = first_raw >> 1, last_raw >> 1
            fallback = False
            if count == 1:
                interval = 0.
            elif last < first and not (first > 270*64 and last < 90*64):
                interval = self.previous_interval; fallback = True
            else:
                interval = _f32(_f32(last-first+(360*64 if last < first else 0)) / _f32(count-1))
                self.previous_interval = interval
            start, finish = self.offset, self.offset + size
            first_receipt = next(t for end, t in self.receipts if end > start)
            last_receipt = next(t for end, t in self.receipts if end >= finish)
            nodes = []
            valid = checksum == expected
            if not valid:
                self.errors += 1
            for i in range(count):
                at = 10 + i*width
                if self.intensity:
                    distance = raw[at+2]*64 + (raw[at+1] >> 2)
                    quality = (raw[at+1] & 3)*64 + (raw[at] >> 2)
                else:
                    sample = int.from_bytes(raw[at:at+2], 'little')
                    distance, quality = sample >> 2, sample & 3
                correction = int(math.atan(19.16*(distance-90.15)/(90.15*distance))*64) if distance else 0
                angle = _f32(_f32(first + _f32(interval*i)) + correction)
                if angle < 0: angle = _f32(angle + 23040)
                elif angle > 23040: angle = _f32(angle - 23040)
                nodes.append(dict(angle_deg=(int(angle) & 0x7fff)/64 if valid else 0.,
                    distance_m=distance/1000 if valid else 0., quality=quality if valid else 10,
                    ring_start=bool(ct & 1) and valid, node_index=self.node_index,
                    source_byte_cursor=finish, valid_packet=valid))
                self.node_index += 1
            packets.append(dict(offset=start, end=finish, raw_bytes=raw, raw_sha256=hashlib.sha256(raw).hexdigest(),
                nodes=nodes, checksum_valid=valid, interval_fallback=fallback,
                receipt_start_s=first_receipt, receipt_end_s=last_receipt))
            del self.buffer[:size]; self.offset = finish
            self.receipts = [(end, t) for end, t in self.receipts if end > self.offset]
            if not self.receipts and self.buffer:
                self.receipts = [(self.offset + len(self.buffer), received_s)]
        if len(self.buffer) > 1024:
            raise ValueError('NATIVE_DECODER_BUFFER_BOUND')
        # Drop receipt entries consumed as noise, retaining the entry covering pending bytes.
        self.receipts = [(end, t) for end, t in self.receipts if end > self.offset]
        return packets


class NativeStream:
    def __init__(self, directory, emit, *, channel_factory=None, clock=time.monotonic,
                 timing_profile=None, segment_bytes=1024*1024, maximum_bytes=256*1024*1024):
        self.directory, self.emit, self.clock = Path(directory), emit, clock
        self.channel_factory = channel_factory
        self.timing_profile = timing_profile
        self.segment_bytes, self.maximum_bytes = segment_bytes, maximum_bytes
        if (type(segment_bytes) is not int or type(maximum_bytes) is not int
                or not 1024 <= segment_bytes <= maximum_bytes <= 1024*1024*1024):
            raise ValueError('NATIVE_STORAGE_BOUND')
        self.lock = threading.RLock(); self.cancel = threading.Event(); self.thread = None
        self.state = dict(lidar_state='OFF', recording_state='IDLE', reason=None, bytes_received=0, frame_count=0)
        self.frame = None; self.stream_id = None

    def snapshot(self):
        with self.lock:return deepcopy(self.state)

    def latest_frame(self):
        with self.lock:return deepcopy(self.frame)

    def start(self):
        with self.lock:
            if self.thread and self.thread.is_alive():return self.snapshot()
            self.stream_id = uuid4().hex; self.cancel.clear(); self.frame = None
            self.state = dict(lidar_state='STARTING', recording_state='RECORDING', reason=None,
                bytes_received=0, frame_count=0, stream_id=self.stream_id)
            self.thread = threading.Thread(target=self._run, daemon=True, name='TwinPulseNativeStream')
            self.thread.start()
            return self.snapshot()

    def stop(self):
        self.cancel.set()
        with self.lock:
            if self.thread and self.thread.is_alive():self.state['lidar_state'] = 'STOPPING'
        return self.snapshot()

    def close(self):
        self.stop()
        if self.thread:self.thread.join(timeout=8)
        return self.snapshot()

    def _run(self):
        from lidar_capture import SerialChannel, START, STOP
        channel = None
        directory = self.directory / self.stream_id
        stream = chunks = None; segment = -1; offset = 0; segment_start = 0; chunk_index = 0
        decoder = NativeDecoder(); frame_packets = []; complete_start = False; last_emit = -math.inf
        manifest = dict(schema='native-stream-manifest-1.0', stream_id=self.stream_id, segments=[], complete=False)
        raw_digest = hashlib.sha256(); timing_digest = hashlib.sha256()
        error = None; started = False
        def close_segment():
            nonlocal stream, chunks
            if stream is None:return
            stream.flush(); chunks.flush(); stream.close(); chunks.close()
            manifest['segments'].append(dict(index=segment, offset=segment_start, bytes=offset-segment_start,
                raw_sha256=raw_digest.hexdigest(), chunks_sha256=timing_digest.hexdigest()))
            stream = chunks = None
        try:
            directory.mkdir(parents=True, exist_ok=False)
            channel = (self.channel_factory or SerialChannel)()
            channel.configure(); started = True
            if channel.write(START) != len(START):raise ValueError('NATIVE_START_INCOMPLETE')
            with self.lock:self.state['lidar_state'] = 'STREAMING'
            while not self.cancel.is_set():
                before = self.clock(); data = channel.read(.05); received = self.clock()
                if not data:continue
                if len(data) > 65536 or offset+len(data) > self.maximum_bytes:
                    raise ValueError('NATIVE_RECORDING_CAPACITY')
                if stream is None or offset-segment_start+len(data) > self.segment_bytes:
                    close_segment(); segment += 1; segment_start = offset
                    raw_digest = hashlib.sha256(); timing_digest = hashlib.sha256()
                    stream = (directory / ('raw-%06d.bin' % segment)).open('xb')
                    chunks = (directory / ('chunks-%06d.jsonl' % segment)).open('xb')
                metadata = dict(stream_id=self.stream_id, chunk_index=chunk_index, offset=offset,
                    length=len(data), receipt_start_s=before, receipt_end_s=received,
                    sha256=hashlib.sha256(data).hexdigest())
                line = (json.dumps(metadata, separators=(',', ':'))+'\n').encode()
                if stream.write(data) != len(data) or chunks.write(line) != len(line):raise OSError('NATIVE_SHORT_WRITE')
                raw_digest.update(data); timing_digest.update(line)
                self.emit('raw', dict(metadata, base64=base64.b64encode(data).decode()))
                chunk_index += 1; offset += len(data)
                for packet in decoder.feed(data, received):
                    if packet['nodes'][0]['ring_start']:
                        if frame_packets:self._frame(frame_packets, complete_start)
                        frame_packets = []; complete_start = True
                    frame_packets.append(packet)
                    if sum(len(p['nodes']) for p in frame_packets) > 4096:
                        self._frame(frame_packets, False); frame_packets = []; complete_start = False
                with self.lock:
                    self.state.update(bytes_received=offset, checksum_errors=decoder.errors, unframed_bytes=decoder.noise_bytes)
                    frame = self.frame
                if frame is not None and received-last_emit >= .2:
                    points = [[b['distance_m']*math.cos(math.radians(b['angle_deg'])),
                               b['distance_m']*math.sin(math.radians(b['angle_deg']))]
                              for b in frame['beams'] if b['distance_m'] > 0 and b['valid_packet']]
                    self.emit('scan', dict(stream_id=self.stream_id, frame_sequence=frame['frame_sequence'],
                        points=points, source='physical_native_sensor_unaligned', frame_id='native_sensor',
                        aligned=False, complete=frame['complete'], timing=frame['timing'],
                        raw_sha256=frame['raw_sha256'],raw_digest_basis=frame['raw_digest_basis'],
                        source_byte_span=frame['source_byte_span'],nodes_sha256=frame['nodes_sha256']))
                    last_emit = received
        except BaseException as exc:
            error = str(exc) if isinstance(exc, (ValueError, OSError)) else type(exc).__name__
            self.emit('fault', dict(reason=error[:120], subsystem='native_sensor'))
        finally:
            stop = dict(write_complete=False, data_quiet=False, port_restored=False, physical_rotor_stopped='UNCONFIRMED')
            try:
                if channel is None:raise ValueError('NATIVE_PORT_NOT_OPENED')
                with channel.cleanup():
                    if started:
                        for _ in range(2):
                            stop['write_complete'] = channel.write(STOP) == len(STOP)
                            channel.drain(2.)
                            stop['data_quiet'] = channel.drain(1.) == 0
                            if stop['write_complete'] and stop['data_quiet']:break
                    stop['port_restored'] = channel.restore()
            except BaseException as exc:stop['error'] = type(exc).__name__
            finally:
                if channel is not None:
                    try:channel.close()
                    except BaseException as exc:stop['close_error']=type(exc).__name__;error='NATIVE_CLOSE_FAILED'
            try:
                close_segment()
                manifest.update(bytes_received=offset, chunks=chunk_index, pending_decoder_bytes=len(decoder.buffer),
                    incomplete_tail_nodes=sum(len(p['nodes']) for p in frame_packets), cleanup=stop, reason=error,
                    complete=error is None and stop['write_complete'] and stop['data_quiet'] and stop['port_restored'])
                (directory/'manifest.json').write_text(json.dumps(manifest, allow_nan=False, indent=2), encoding='utf-8')
            except BaseException as exc:error = 'NATIVE_FINALIZE_'+type(exc).__name__
            with self.lock:
                self.frame = None
                self.state.update(lidar_state='FAULT' if error or not manifest['complete'] else 'OFF',
                    recording_state='INCOMPLETE' if error or not manifest['complete'] else 'COMPLETE', reason=error,
                    manifest=manifest)
            self.emit('cleanup', dict(subsystem='native_sensor', **manifest))

    def _frame(self, packets, complete):
        beams = [deepcopy(b) for packet in packets for b in packet['nodes']]
        first, last = packets[0]['receipt_start_s'], packets[-1]['receipt_end_s']
        timing = dict(receipt_start_s=first, receipt_end_s=last, acquisition_earliest_s=None,
            acquisition_latest_s=None, basis='serial_receipt_unqualified', uncertainty_s=None, evidence_sha256=None)
        if self.timing_profile is not None:
            p = self.timing_profile
            timing.update(acquisition_earliest_s=first-p['maximum_pipeline_age_s'], acquisition_latest_s=last,
                basis='conservative_measured_interval', uncertainty_s=p['maximum_pipeline_age_s'], evidence_sha256=p['measurement_sha256'])
        with self.lock:
            self.state['frame_count'] += 1
            self.frame = dict(beams=beams, source_kind='live_sensor', stream_id=self.stream_id, frame_sequence=self.state['frame_count'],
                complete=complete and all(p['checksum_valid'] for p in packets)
                    and all(a['end']==b['offset'] for a,b in zip(packets,packets[1:])), timing=timing,
                interval_fallback=any(p['interval_fallback'] for p in packets),
                raw_sha256=hashlib.sha256(b''.join(p['raw_bytes'] for p in packets)).hexdigest(),
                raw_digest_basis='ordered_original_packet_bytes',
                source_byte_span={'start':packets[0]['offset'],'end':packets[-1]['end']},
                nodes_sha256=hashlib.sha256(json.dumps(beams, sort_keys=True, separators=(',', ':')).encode()).hexdigest())
