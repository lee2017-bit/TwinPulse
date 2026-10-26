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
from robot_journal import RobotJournal


class FrozenFrame(dict):
    """JSON-compatible read-only snapshot, shared by all local consumers."""
    def _readonly(self,*a,**k):raise TypeError('NATIVE_FRAME_READ_ONLY')
    __setitem__=__delitem__=clear=pop=popitem=setdefault=update=__ior__=_readonly
    def __deepcopy__(self,memo):return self


def freeze_frame(value):
    if isinstance(value,dict):return FrozenFrame({k:freeze_frame(v) for k,v in value.items()})
    if isinstance(value,(tuple,list)):return tuple(freeze_frame(v) for v in value)
    return value


def _f32(x):
    return struct.unpack('<f', struct.pack('<f', x))[0]


class NativeDecoder:
    def __init__(self, *, intensity=True):
        self.intensity = intensity
        self.buffer = bytearray()
        self.offset = self.node_index = self.errors = self.noise_bytes = 0
        self.previous_interval = 0.
        self.receipts = []
        self.packet_bytes = self.unframed_segments = 0
        self._unframed_start = None
        self._unframed_digest = hashlib.sha256()
        self._unframed_prefix = bytearray()
        self._unframed_framing_errors = 0

    def _discard_unframed(self):
        # The bytes remain in the raw capture. Retain bounded provenance here,
        # including a gap split over any number of serial reads.
        if self._unframed_start is None:
            self._unframed_start = self.offset
            self.unframed_segments += 1
        value = bytes(self.buffer[:1])
        self._unframed_digest.update(value)
        if len(self._unframed_prefix) < 32:self._unframed_prefix.extend(value)
        del self.buffer[0]
        self.offset += 1; self.noise_bytes += 1

    def pending_unframed(self):
        if self._unframed_start is None:return None
        return dict(start=self._unframed_start, end=self.offset,
            length=self.offset-self._unframed_start, classification='UNKNOWN',
            framing_errors=self._unframed_framing_errors,
            raw_sha256=self._unframed_digest.hexdigest(),
            prefix_hex=self._unframed_prefix.hex(' '))

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
                self._discard_unframed()
                continue
            if len(self.buffer) < 10:
                break
            ct, count = self.buffer[2:4]
            first_raw, last_raw, expected = struct.unpack_from('<HHH', self.buffer, 4)
            if not 0 < count <= capacity or not first_raw & 1 or not last_raw & 1:
                self.errors += 1; self._discard_unframed(); self._unframed_framing_errors += 1
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
            valid = checksum == expected
            fallback = False
            if count == 1:
                interval = 0.
            elif last < first and not (first > 270*64 and last < 90*64):
                interval = self.previous_interval; fallback = True
            else:
                interval = _f32(_f32(last-first+(360*64 if last < first else 0)) / _f32(count-1))
                # A corrupt packet must not poison the next valid packet's
                # prior-interval fallback. Valid-packet arithmetic is unchanged.
                if valid:self.previous_interval = interval
            start, finish = self.offset, self.offset + size
            first_receipt = next(t for end, t in self.receipts if end > start)
            last_receipt = next(t for end, t in self.receipts if end >= finish)
            nodes = []
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
            packet = dict(offset=start, end=finish, raw_bytes=raw, raw_sha256=hashlib.sha256(raw).hexdigest(),
                nodes=nodes, checksum_valid=valid, interval_fallback=fallback,
                receipt_start_s=first_receipt, receipt_end_s=last_receipt)
            if self._unframed_start is not None:
                packet['preceding_unframed'] = self.pending_unframed()
                self._unframed_start = None
                self._unframed_framing_errors = 0
                self._unframed_digest = hashlib.sha256(); self._unframed_prefix.clear()
            packets.append(packet)
            self.packet_bytes += size
            del self.buffer[:size]; self.offset = finish
            self.receipts = [(end, t) for end, t in self.receipts if end > self.offset]
            if not self.receipts and self.buffer:
                self.receipts = [(self.offset + len(self.buffer), received_s)]
        if len(self.buffer) > 1024:
            raise ValueError('NATIVE_DECODER_BUFFER_BOUND')
        # Drop receipt entries consumed as noise, retaining the entry covering pending bytes.
        self.receipts = [(end, t) for end, t in self.receipts if end > self.offset]
        return packets


class NativeCaptureSink:
    """Single archive-thread owner of the unchanged raw/chunks file format.

    Original serial timestamps and bytes are frozen before enqueue. Only this
    sink rotates, writes, hashes and closes files; never the serial reader.
    Buffered writes are not a final persistence receipt until close succeeds.
    """
    def __init__(self,directory,segment_bytes):
        self.directory=Path(directory);self.segment_bytes=segment_bytes
        self.stream=self.chunks=None;self.segment=-1;self.offset=self.segment_start=self.chunk_index=0
        self.stream_id=None;self.segments=[];self.raw_digest=self.timing_digest=None

    def _finish(self):
        if self.stream is None and self.chunks is None:return
        streams=(self.stream,self.chunks);self.stream=self.chunks=None;errors=[]
        for stream in streams:
            if stream is None:continue
            try:stream.flush()
            except Exception as error:errors.append(error)
            try:stream.close()
            except Exception as error:errors.append(error)
        if errors:raise errors[0]
        self.segments.append(dict(index=self.segment,offset=self.segment_start,bytes=self.offset-self.segment_start,
            raw_sha256=self.raw_digest.hexdigest(),chunks_sha256=self.timing_digest.hexdigest()))

    def write(self,line):
        metadata=json.loads(line);data=base64.b64decode(metadata.pop('base64'),validate=True)
        if (metadata['offset']!=self.offset or metadata['chunk_index']!=self.chunk_index
                or metadata['length']!=len(data) or hashlib.sha256(data).hexdigest()!=metadata['sha256']
                or self.stream_id is not None and metadata['stream_id']!=self.stream_id):
            raise ValueError('NATIVE_ARCHIVE_IDENTITY')
        self.stream_id=metadata['stream_id']
        if self.stream is None or self.offset-self.segment_start+len(data)>self.segment_bytes:
            self._finish();self.segment+=1;self.segment_start=self.offset
            self.raw_digest=hashlib.sha256();self.timing_digest=hashlib.sha256()
            self.stream=(self.directory/('raw-%06d.bin'%self.segment)).open('xb')
            self.chunks=(self.directory/('chunks-%06d.jsonl'%self.segment)).open('xb')
        encoded=(json.dumps(metadata,separators=(',',':'))+'\n').encode()
        if self.stream.write(data)!=len(data) or self.chunks.write(encoded)!=len(encoded):
            raise OSError('NATIVE_SHORT_WRITE')
        self.raw_digest.update(data);self.timing_digest.update(encoded)
        self.offset+=len(data);self.chunk_index+=1
        return len(line)

    def flush(self):
        # Rotation/final close flush both handles. The native journal uses
        # flush_each=False to retain the original buffered-file write policy.
        if self.stream:self.stream.flush()
        if self.chunks:self.chunks.flush()

    def close(self):self._finish()


RAW_COALESCE_BYTES=8192   # one raw event per <=8 KiB or 100 ms of serial bytes instead of one per read
RAW_COALESCE_S=.1         # (50-100 events/s filled the 512-message PC outbox in seconds; phys09 review)


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
        self.frame = None; self.complete_frame = None; self.stream_id = None
        self.archive=None;self.archive_failure=None
        self._frame_packets = []; self._complete_start = False
        self.raw_coalesce_bytes=RAW_COALESCE_BYTES;self.raw_coalesce_s=RAW_COALESCE_S

    def snapshot(self):
        with self.lock:
            result=deepcopy(self.state)
            if self.archive is not None:result['archive']=self.archive.status()
            result['archive_failure']=self.archive_failure
            return result

    def latest_frame(self):
        # Published frames are recursively read-only: no repeated full-ring
        # deepcopy on the heartbeat, tracker and motor boundary threads.
        with self.lock:return self.frame

    def control_frames(self):
        # One atomic pair, same stream. This is storage, not admission: the
        # consumer must enforce the ORIGINAL complete frame's age and inspect
        # newer partial returns for stop-only hazards. Never restamp a frame.
        with self.lock:
            if self.cancel.is_set() or self.state.get('lidar_state')!='STREAMING' or self.state.get('reason'):
                return None,None
            return self.frame,self.complete_frame

    def start(self):
        with self.lock:
            if self.thread and self.thread.is_alive():return self.snapshot()
            if self.archive is not None and self.archive.status()['writer_alive']:
                raise ValueError('NATIVE_ARCHIVE_PREVIOUS_OWNER_NOT_REAPED')
            if self.archive_failure is not None:
                raise ValueError('NATIVE_ARCHIVE_PREVIOUS_FAILURE_RECONNECT_REQUIRED')
            self.stream_id = uuid4().hex; self.cancel.clear(); self.frame = self.complete_frame = None
            self.archive=None
            self._frame_packets = []; self._complete_start = False
            self.state = dict(lidar_state='STARTING', recording_state='RECORDING', reason=None,
                bytes_received=0, frame_count=0, stream_id=self.stream_id)
            self.thread = threading.Thread(target=self._run, daemon=True, name='TwinPulseNativeStream')
            self.thread.start()
            return self.snapshot()

    def stop(self):
        self.cancel.set()
        with self.lock:
            self.frame=self.complete_frame=None
            if self.thread and self.thread.is_alive():self.state['lidar_state'] = 'STOPPING'
        return self.snapshot()

    def close(self):
        self.stop()
        # STOP/quiet/port restore happen before waiting for archive drainage.
        if self.thread:self.thread.join(timeout=20)
        return self.snapshot()

    def _run(self):
        from lidar_capture import SerialChannel, START, STOP
        channel = None
        directory = self.directory / self.stream_id
        offset=chunk_index=0;sink=archive=None
        decoder = NativeDecoder(); last_emit = -math.inf
        manifest = dict(schema='native-stream-manifest-1.0', stream_id=self.stream_id, segments=[], complete=False)
        error = None; started = False;archive_fault_emitted=False
        try:
            directory.mkdir(parents=True, exist_ok=False)
            sink=NativeCaptureSink(directory,self.segment_bytes)
            archive=RobotJournal(directory/'unused',capacity=4096,max_bytes=self.maximum_bytes*16,
                max_pending_bytes=4*1024*1024,buffered=True,flush_each=False,opener=lambda _:sink)
            with self.lock:self.archive=archive
            channel = (self.channel_factory or SerialChannel)()
            channel.configure(); started = True
            if channel.write(START) != len(START):raise ValueError('NATIVE_START_INCOMPLETE')
            with self.lock:self.state['lidar_state'] = 'STREAMING'
            pending=bytearray();pending_reads=[];coalesce_bytes=min(self.raw_coalesce_bytes,self.segment_bytes);coalesce_s=self.raw_coalesce_s
            def flush_pending(end):
                # One archived/emitted chunk per coalesced run of reads. Every original read keeps
                # its own receipt window and length in `reads`; bytes, offsets and SHA are exact.
                nonlocal pending,pending_reads,chunk_index,offset
                if not pending:return
                data=bytes(pending)
                metadata = dict(stream_id=self.stream_id, chunk_index=chunk_index, offset=offset,
                    length=len(data), receipt_start_s=pending_reads[0][0], receipt_end_s=end,
                    reads=pending_reads[:64],read_count=len(pending_reads),
                    sha256=hashlib.sha256(data).hexdigest())
                raw_event=dict(metadata,base64=base64.b64encode(data).decode())
                # Queue admission precedes decode; bounded capacity and sticky
                # writer errors remain fail-closed. No disk call on this path.
                archive.append_prepared(json.dumps(raw_event,separators=(',',':'))+'\n','native_chunk')
                self.emit('raw',raw_event)
                chunk_index += 1; offset += len(data)
                pending=bytearray();pending_reads=[]
            while not self.cancel.is_set():
                archive.check()
                before = self.clock(); data = channel.read(.05); received = self.clock()
                if data:
                    if len(data) > 65536 or offset+len(pending)+len(data) > self.maximum_bytes:
                        raise ValueError('NATIVE_RECORDING_CAPACITY')
                    pending+=data;pending_reads.append([before,received,len(data)])
                if pending and (not data or len(pending)>=coalesce_bytes or received-pending_reads[0][0]>=coalesce_s):
                    flush_pending(received)
                if not data:continue
                decode_started=time.perf_counter()
                packets=decoder.feed(data, received)
                decode_s=time.perf_counter()-decode_started
                self._accept_packets(packets)
                with self.lock:
                    self.state.update(bytes_received=offset+len(pending), checksum_errors=decoder.errors, unframed_bytes=decoder.noise_bytes,
                        unframed_segments=decoder.unframed_segments,
                        last_read_wait_s=received-before,last_decode_s=decode_s)
                    frame = self.frame
                if frame is not None and received-last_emit >= .2:
                    points = [[b['distance_m']*math.cos(math.radians(b['angle_deg'])),
                               b['distance_m']*math.sin(math.radians(b['angle_deg']))]
                              for b in frame['beams'] if b['distance_m'] > 0 and b['valid_packet']]
                    self.emit('scan', dict(stream_id=self.stream_id, frame_sequence=frame['frame_sequence'],
                        points=points, source='physical_native_sensor_unaligned', frame_id='native_sensor',
                        aligned=False, complete=frame['complete'], timing=frame['timing'],
                        raw_sha256=frame['raw_sha256'],raw_digest_basis=frame['raw_digest_basis'],
                        source_byte_span=frame['source_byte_span'],nodes_sha256=frame['nodes_sha256'],quality=frame['quality']))
                    last_emit = received
            flush_pending(self.clock())
        except BaseException as exc:
            error = str(exc) if isinstance(exc, (ValueError, OSError)) else type(exc).__name__
            archive_error=archive.status()['error'] if archive is not None else None
            with self.lock:
                self.frame=self.complete_frame=None
                if archive_error:self.archive_failure=self.archive_failure or 'NATIVE_ARCHIVE_'+archive_error
                self.state.update(lidar_state='FAULT',reason=error[:120])
            archive_fault_emitted=archive_error is not None
            self.emit('fault', dict(reason=self.archive_failure if archive_fault_emitted else error[:120],
                subsystem='native_archive' if archive_fault_emitted else 'native_sensor'))
        finally:
            with self.lock:self.frame=self.complete_frame=None
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
                    except BaseException as exc:stop['close_error']=type(exc).__name__;error=error or 'NATIVE_CLOSE_FAILED'
            try:
                archived=archive.close(timeout=15.) if archive is not None else None
                if (archived is None or archived['error'] or archived['writer_alive']
                        or archived['accepted']!=archived['saved'] or archived['queued']):
                    error=error or 'NATIVE_ARCHIVE_INCOMPLETE'
                    with self.lock:
                        self.archive_failure=self.archive_failure or 'NATIVE_ARCHIVE_'+str((archived or {}).get('error') or 'INCOMPLETE')
                if archived is not None and not archived['writer_alive']:
                    manifest['segments']=deepcopy(sink.segments)
                    if sink.offset!=offset or sink.chunk_index!=chunk_index:
                        error=error or 'NATIVE_ARCHIVE_COUNTS'
                        with self.lock:self.archive_failure=self.archive_failure or 'NATIVE_ARCHIVE_COUNTS'
                manifest['archive']=archived
                manifest.update(bytes_received=offset, chunks=chunk_index, pending_decoder_bytes=len(decoder.buffer),
                    decoded_packet_bytes=decoder.packet_bytes, unframed_bytes=decoder.noise_bytes,
                    unframed_segments=decoder.unframed_segments, unframed_tail=decoder.pending_unframed(),
                    byte_accounting_exact=offset==decoder.packet_bytes+decoder.noise_bytes+len(decoder.buffer),
                    incomplete_tail_nodes=sum(len(p['nodes']) for p in self._frame_packets), cleanup=stop, reason=error,
                    complete=error is None and stop['write_complete'] and stop['data_quiet'] and stop['port_restored'])
                (directory/'manifest.json').write_text(json.dumps(manifest, allow_nan=False, indent=2), encoding='utf-8')
            except BaseException as exc:
                finalize_error='NATIVE_FINALIZE_'+type(exc).__name__
                error=error or finalize_error
                manifest.update(complete=False,reason=error,finalize_error=finalize_error)
                with self.lock:self.archive_failure=self.archive_failure or finalize_error
            with self.lock:
                self.frame = self.complete_frame = None
                self.state.update(lidar_state='FAULT' if error or not manifest['complete'] else 'OFF',
                    recording_state='INCOMPLETE' if error or not manifest['complete'] else 'COMPLETE', reason=error,
                    manifest=manifest)
            if self.archive_failure and not archive_fault_emitted:
                self.emit('fault',dict(subsystem='native_archive',reason=self.archive_failure))
            self.emit('cleanup', dict(subsystem='native_sensor', **manifest))

    def _accept_packets(self, packets):
        """Assemble original rings; boundary unknown bytes taint the closing ring.

        The next validated ring-start establishes a new boundary. Its preceding
        gap belongs to the ring being closed, exactly once; no scan is removed.
        """
        for packet in packets:
            if packet['nodes'][0]['ring_start']:
                if self._frame_packets:
                    self._frame(self._frame_packets, self._complete_start,
                                trailing_unframed=packet.get('preceding_unframed'))
                    packet = dict(packet)
                    packet.pop('preceding_unframed', None)
                self._frame_packets = []; self._complete_start = True
            self._frame_packets.append(packet)
            if sum(len(p['nodes']) for p in self._frame_packets) > 4096:
                self._frame(self._frame_packets, False)
                self._frame_packets = []; self._complete_start = False

    def _frame(self, packets, complete, *, trailing_unframed=None):
        began=time.perf_counter()
        beams = [b for packet in packets for b in packet['nodes']]
        first, last = packets[0]['receipt_start_s'], packets[-1]['receipt_end_s']
        timing = dict(receipt_start_s=first, receipt_end_s=last, acquisition_earliest_s=None,
            acquisition_latest_s=None, basis='serial_receipt_unqualified', uncertainty_s=None, evidence_sha256=None)
        if self.timing_profile is not None:
            p = self.timing_profile
            timing.update(acquisition_earliest_s=first-p['maximum_pipeline_age_s'], acquisition_latest_s=last,
                basis='conservative_measured_interval', uncertainty_s=p['maximum_pipeline_age_s'], evidence_sha256=p['measurement_sha256'])
        # Canonical hashing and freezing never own the publication lock.
        unframed = [p['preceding_unframed'] for p in packets if p.get('preceding_unframed')]
        if trailing_unframed is not None:unframed.append(trailing_unframed)
        contiguous = all(a['end']==b['offset'] for a,b in zip(packets,packets[1:]))
        quality = dict(schema='native-frame-quality-1.0', complete_start=complete,
            checksum_invalid_packets=sum(not p['checksum_valid'] for p in packets),
            interval_fallback_packets=sum(bool(p['interval_fallback']) for p in packets),
            packet_contiguous=contiguous, unframed_spans=unframed,
            unframed_bytes=sum(g['length'] for g in unframed),
            unknown_boundary_policy='GAP_BEFORE_VALID_RING_START_BELONGS_TO_CLOSING_RING')
        value=freeze_frame(dict(beams=beams, source_kind='live_sensor', stream_id=self.stream_id,
                complete=complete and all(p['checksum_valid'] for p in packets)
                    and contiguous and not unframed, timing=timing, quality=quality,
                interval_fallback=any(p['interval_fallback'] for p in packets),
                raw_sha256=hashlib.sha256(b''.join(p['raw_bytes'] for p in packets)).hexdigest(),
                raw_digest_basis='ordered_original_packet_bytes',
                source_byte_span={'start':packets[0]['offset'],'end':packets[-1]['end']},
                nodes_sha256=hashlib.sha256(json.dumps(beams, sort_keys=True, separators=(',', ':')).encode()).hexdigest()))
        build_s=time.perf_counter()-began;waiting=time.perf_counter()
        with self.lock:
            self.state['frame_count'] += 1
            self.frame=FrozenFrame(value,frame_sequence=self.state['frame_count'])
            if self.frame['complete'] and not self.frame['interval_fallback']:self.complete_frame=self.frame
            self.state.update(last_frame_build_s=build_s,last_publication_lock_wait_s=time.perf_counter()-waiting,
                last_frame_publish_age_s=max(0.,self.clock()-last),
                maximum_frame_build_s=max(build_s,self.state.get('maximum_frame_build_s',0.)))
