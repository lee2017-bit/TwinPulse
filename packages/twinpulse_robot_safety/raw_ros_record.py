# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Bounded loss-explicit ROS message recording for a single observation window.

The recorder is a subscriber only. It stores the exact serialized message bytes
before any TwinPulse validation, including messages later rejected by that
validation. Each frame has a JSON metadata length, payload length, metadata,
and payload. The footer is separate so a truncated recording is never complete.
"""
import hashlib
import json
from pathlib import Path
import queue
import struct
import threading
import time


MAGIC = b'TPROSRAW1\n'
HEADER = struct.Struct('>II')
MAX_BYTES = 64 * 1024 * 1024
MAX_MESSAGE_BYTES = 8 * 1024 * 1024
MAX_PENDING_BYTES = 16 * 1024 * 1024
TOPICS = {
    'sensor_state': 'turtlebot3_msgs/msg/SensorState',
    'motion_guard/status': 'std_msgs/msg/String',
    'odom': 'nav_msgs/msg/Odometry',
    'scan': 'sensor_msgs/msg/LaserScan',
    '/tf': 'tf2_msgs/msg/TFMessage',
    '/tf_static': 'tf2_msgs/msg/TFMessage',
    'guarded_cmd_vel': 'geometry_msgs/msg/TwistStamped',
}


class RawRosRecorder:
    def __init__(self, path, *, serializer, max_bytes=MAX_BYTES,
                 max_pending_bytes=MAX_PENDING_BYTES, monotonic_ns=time.monotonic_ns):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.path.open('xb')
        if self.stream.write(MAGIC) != len(MAGIC):
            self.stream.close()
            raise OSError('RAW_MAGIC_WRITE_INCOMPLETE')
        self.serializer = serializer
        self.max_bytes = max_bytes
        self.max_pending_bytes = max_pending_bytes
        self.monotonic_ns = monotonic_ns
        self.bytes_written = len(MAGIC)
        self.bytes_reserved = len(MAGIC)
        self.pending_bytes = 0
        self.next_sequence = 0
        self.counts = {topic: 0 for topic in TOPICS}
        self.drop_counts = {topic: 0 for topic in TOPICS}
        self.dropped = 0
        self.pending_high_water_bytes = 0
        self.errors = []
        self.writer_failed = False
        self.closed = False
        self.closed_result = None
        self.digest = hashlib.sha256()
        self.digest.update(MAGIC)
        self.lock = threading.RLock()
        self.pending = queue.Queue()
        self.writer = threading.Thread(target=self._write_pending, name='twinpulse-raw-writer', daemon=True)
        self.writer.start()

    def _write_pending(self):
        while True:
            item = self.pending.get()
            if item is None:
                try:
                    self.stream.flush()
                except Exception as exc:
                    with self.lock:
                        self.writer_failed = True
                        self.dropped += 1
                        if len(self.errors) < 8:self.errors.append(type(exc).__name__+':RAW_FLUSH_FAILED')
                finally:
                    try:self.stream.close()
                    except Exception:
                        with self.lock:
                            self.writer_failed=True
                            self.dropped+=1
                return
            topic, frame = item
            try:
                with self.lock:
                    healthy = not self.writer_failed
                if healthy:
                    if self.stream.write(frame) != len(frame):
                        raise OSError('RAW_FRAME_WRITE_INCOMPLETE')
                    with self.lock:
                        self.digest.update(frame)
                        self.bytes_written += len(frame)
                        self.counts[topic] += 1
                else:
                    with self.lock:
                        self.dropped += 1
                        self.drop_counts[topic] += 1
            except Exception as exc:
                with self.lock:
                    self.dropped += 1
                    self.drop_counts[topic] += 1
                    self.writer_failed = True
                    if len(self.errors) < 8:
                        self.errors.append(type(exc).__name__ + ':' + str(exc)[:120])
            finally:
                with self.lock:
                    self.pending_bytes -= len(frame)

    def record(self, topic, message, *, receipt_monotonic_ns=None):
        if topic not in TOPICS:
            raise ValueError('RAW_TOPIC_NOT_ALLOWLISTED')
        try:
            payload = bytes(self.serializer(message))
            if len(payload) > MAX_MESSAGE_BYTES:
                raise ValueError('RAW_MESSAGE_TOO_LARGE')
            received_at = self.monotonic_ns() if receipt_monotonic_ns is None else receipt_monotonic_ns
            if type(received_at) is not int or not 0 <= received_at < 2**63:
                raise ValueError('RAW_RECEIPT_CLOCK_INVALID')
            with self.lock:
                if self.closed:
                    raise ValueError('RAW_RECORDER_CLOSED')
                if self.writer_failed:
                    raise ValueError('RAW_WRITER_FAILED')
                metadata = json.dumps({'sequence': self.next_sequence, 'topic': topic,
                                       'type': TOPICS[topic], 'receipt_monotonic_ns': received_at},
                                      sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
                frame = HEADER.pack(len(metadata), len(payload)) + metadata + payload
                if self.bytes_reserved + len(frame) > self.max_bytes:
                    raise ValueError('RAW_RECORDING_CAP_REACHED')
                if self.pending_bytes + len(frame) > self.max_pending_bytes:
                    raise ValueError('RAW_QUEUE_CAP_REACHED')
                self.pending_bytes += len(frame)
                self.pending_high_water_bytes = max(self.pending_high_water_bytes, self.pending_bytes)
                self.bytes_reserved += len(frame)
                self.next_sequence += 1
                self.pending.put_nowait((topic, frame))
            return True
        except Exception as exc:
            with self.lock:
                self.dropped += 1
                self.drop_counts[topic] += 1
                if len(self.errors) < 8:
                    self.errors.append(type(exc).__name__ + ':' + str(exc)[:120])
            return False

    def close(self, timeout=2.):
        with self.lock:
            if self.closed_result is not None:
                return self.closed_result
            if not self.closed:
                self.closed = True
                self.pending.put_nowait(None)
        self.writer.join(timeout)
        if self.writer.is_alive():
            # Only the writer owns close/flush. Never wait indefinitely during
            # motor cleanup or publish a footer for a still-changing byte file.
            with self.lock:
                self.closed_result={'schema_version':'tp-ros-raw-1','path':self.path.name,
                    'complete':False,'errors':['RAW_WRITER_CLOSE_TIMEOUT'],
                    'counts':dict(self.counts),'dropped':self.dropped,
                    'pending_bytes':self.pending_bytes,'writer_alive':True}
                return self.closed_result
        result = {'schema_version': 'tp-ros-raw-1', 'path': self.path.name,
                  'bytes': self.bytes_written, 'sha256': self.digest.hexdigest(),
                  'counts': dict(self.counts), 'dropped': self.dropped, 'drop_counts': dict(self.drop_counts),
                  'queue_high_water_bytes': self.pending_high_water_bytes,
                  'queue_limit_bytes': self.max_pending_bytes, 'record_limit_bytes': self.max_bytes,
                  'errors': list(self.errors),
                  'complete': self.dropped == 0 and not self.writer_failed}
        self.path.with_suffix(self.path.suffix + '.footer.json').write_text(
            json.dumps(result, sort_keys=True, indent=2), encoding='utf-8')
        with self.lock:
            self.closed_result = result
        return result


def inspect_recording(path):
    """Validate a closed bundle offline and return complete bytes for re-parsing."""
    path = Path(path)
    footer_path = path.with_suffix(path.suffix + '.footer.json')
    if path.is_symlink() or footer_path.is_symlink():
        raise ValueError('RAW_SYMLINK_REJECTED')
    if path.stat().st_size > MAX_BYTES or footer_path.stat().st_size > 16 * 1024:
        raise ValueError('RAW_BUNDLE_SIZE_INVALID')
    footer = json.loads(footer_path.read_text(encoding='utf-8'))
    frames = []
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        magic = stream.read(len(MAGIC))
        if magic != MAGIC:
            raise ValueError('RAW_MAGIC_INVALID')
        digest.update(magic)
        sequence = 0
        while True:
            head = stream.read(HEADER.size)
            if not head:
                break
            if len(head) != HEADER.size:
                raise ValueError('RAW_FRAME_TRUNCATED')
            meta_size, payload_size = HEADER.unpack(head)
            if not 0 < meta_size <= 4096 or payload_size > MAX_MESSAGE_BYTES:
                raise ValueError('RAW_FRAME_SIZE_INVALID')
            meta_bytes = stream.read(meta_size)
            payload = stream.read(payload_size)
            if len(meta_bytes) != meta_size or len(payload) != payload_size:
                raise ValueError('RAW_FRAME_TRUNCATED')
            digest.update(head + meta_bytes + payload)
            meta = json.loads(meta_bytes)
            if (not isinstance(meta, dict)
                    or set(meta) != {'sequence', 'topic', 'type', 'receipt_monotonic_ns'}
                    or type(meta['sequence']) is not int or meta['sequence'] != sequence
                    or type(meta['receipt_monotonic_ns']) is not int
                    or meta['receipt_monotonic_ns'] < 0
                    or not isinstance(meta['topic'], str)
                    or TOPICS.get(meta['topic']) != meta['type']):
                raise ValueError('RAW_FRAME_METADATA_INVALID')
            frames.append((meta, payload))
            sequence += 1
    if (footer.get('schema_version') != 'tp-ros-raw-1'
            or footer.get('path') != path.name
            or footer.get('bytes') != path.stat().st_size
            or footer.get('sha256') != digest.hexdigest()):
        raise ValueError('RAW_DIGEST_OR_SIZE_MISMATCH')
    counts = {topic: 0 for topic in TOPICS}
    for meta, _ in frames:
        counts[meta['topic']] += 1
    drop_counts = footer.get('drop_counts')
    recorded_counts = footer.get('counts')
    if (not isinstance(recorded_counts, dict) or set(recorded_counts) != set(TOPICS)
            or any(type(value) is not int or value < 0 for value in recorded_counts.values())
            or not isinstance(drop_counts, dict) or set(drop_counts) != set(TOPICS)
            or any(type(value) is not int or value < 0 for value in drop_counts.values())
            or counts != recorded_counts or type(footer.get('dropped')) is not int
            or footer['dropped'] != 0 or any(drop_counts.values())
            or footer.get('errors') != [] or footer.get('complete') is not True):
        raise ValueError('RAW_INCOMPLETE')
    return frames


def replay_recording(path, decoder):
    """Validate first, then decode every original frame with an injected ROS decoder.

    The decoder receives (serialized_bytes, fully_qualified_ros_type). No JSON
    normalization of NaN/Inf or partial-frame recovery occurs here. On a PC
    without compatible ROS message packages, byte-level inspection remains
    available but message-level replay must be reported unavailable.
    """
    if not callable(decoder):
        raise TypeError('RAW_DECODER_REQUIRED')
    result = []
    for metadata, payload in inspect_recording(path):
        try:
            decoded = decoder(payload, metadata['type'])
        except Exception as exc:
            raise ValueError('RAW_MESSAGE_DECODE_FAILED_SEQUENCE_' + str(metadata['sequence'])) from exc
        result.append((metadata, decoded))
    return result
